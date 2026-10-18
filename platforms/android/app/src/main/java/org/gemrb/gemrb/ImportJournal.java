package org.gemrb.gemrb;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/** Durable ownership evidence, deliberately separate from copied user data. */
final class ImportJournal {
    static final Object LOCK = new Object();
    enum Phase { COPYING, COPIED, GAME_PROMOTED, SAVES_PROMOTED, REGISTERED, ABORTED }
    interface Registry {
        boolean contains(String id);
        void add(String id, String name) throws IOException;
    }
    static final class Recovery {
        final List<String> notices = new ArrayList<>();
        final List<String> removedFiles = new ArrayList<>();
        long removedBytes;
    }
    private static final class Copy {
        final long size;
        final String hash;
        Copy(long size, String hash) { this.size = size; this.hash = hash; }
    }

    final String id;
    final String name;
    final File gameStaging;
    final File gameTarget;
    final File saveStaging;
    final File saveTarget;
    private final File externalRoot;
    private final File metadata;
    private final File copies;
    private final File journalRoot;
    private final String source;
    private Phase phase;
    private boolean gameTargetOwned;
    private boolean saveTargetOwned;

    private ImportJournal(File external, File journals, String id, String name, String source, Phase phase) throws IOException {
        if (!isId(id)) throw new IOException("Invalid import journal id");
        this.id = id;
        this.name = name;
        this.source = source;
        this.phase = phase;
        externalRoot = external.getCanonicalFile();
        journalRoot = journals.getCanonicalFile();
        metadata = ManagedFiles.child(journals, id + ".properties");
        copies = ManagedFiles.child(journals, id + ".copies");
        gameStaging = ManagedFiles.child(externalRoot, "games/" + id + ".tmp");
        gameTarget = ManagedFiles.child(externalRoot, "games/" + id);
        saveStaging = ManagedFiles.child(externalRoot, "saves/" + id + ".tmp");
        saveTarget = ManagedFiles.child(externalRoot, "saves/" + id);
    }

    static ImportJournal begin(File external, File journals, String id, String name, String source) throws IOException {
        ManagedFiles.mkdir(journals);
        ImportJournal journal = new ImportJournal(external, journals, id, name, source, Phase.COPYING);
        if (ManagedFiles.exists(journal.metadata) || ManagedFiles.exists(journal.copies)
                || ManagedFiles.exists(journal.gameStaging) || ManagedFiles.exists(journal.gameTarget)
                || ManagedFiles.exists(journal.saveStaging) || ManagedFiles.exists(journal.saveTarget)) {
            throw new IOException("Import id already exists");
        }
        journal.setPhase(Phase.COPYING); // Provenance exists before any destination is created.
        ManagedFiles.mkdir(journal.gameStaging);
        ManagedFiles.mkdir(journal.saveStaging);
        return journal;
    }

    void setPhase(Phase next) throws IOException {
        validateRoots();
        if (next == Phase.GAME_PROMOTED || next == Phase.SAVES_PROMOTED || next == Phase.REGISTERED) gameTargetOwned = true;
        if (next == Phase.SAVES_PROMOTED || next == Phase.REGISTERED) saveTargetOwned = true;
        Properties values = new Properties();
        values.setProperty("schema", "1");
        values.setProperty("id", id);
        values.setProperty("name", name);
        values.setProperty("source", source);
        values.setProperty("phase", next.name());
        values.setProperty("gameTargetOwned", Boolean.toString(gameTargetOwned));
        values.setProperty("saveTargetOwned", Boolean.toString(saveTargetOwned));
        java.io.StringWriter text = new java.io.StringWriter();
        values.store(text, "GemRB import transaction");
        ManagedFiles.atomicWrite(metadata, text.toString());
        phase = next;
    }

    void copied(File file, String hash) throws IOException {
        validateRoots();
        String relative = gameStaging.toPath().relativize(file.toPath()).toString().replace(File.separatorChar, '/');
        ManagedFiles.child(gameStaging, relative);
        if (protectedPath(relative)) return;
        String line = Base64.getEncoder().encodeToString(relative.getBytes(StandardCharsets.UTF_8))
                + "\t" + file.length() + "\t" + hash + "\n";
        try (FileOutputStream output = new FileOutputStream(copies, true)) {
            output.write(line.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
    }

    void promote() throws IOException {
        validateRoots();
        promoteOne(gameStaging, gameTarget);
        gameTargetOwned = true;
        setPhase(Phase.GAME_PROMOTED);
        promoteOne(saveStaging, saveTarget);
        saveTargetOwned = true;
        setPhase(Phase.SAVES_PROMOTED);
    }

    private static void promoteOne(File staging, File target) throws IOException {
        if (ManagedFiles.exists(target)) {
            if (ManagedFiles.exists(staging)) throw new IOException("Ambiguous import destinations: " + target);
            return; // The process may have stopped between the rename and journal update.
        }
        if (!staging.isDirectory()) throw new IOException("Missing import staging directory: " + staging);
        Files.move(staging.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE);
    }

    void registered() throws IOException {
        setPhase(Phase.REGISTERED);
        forget();
    }

    private void forget() throws IOException {
        validateRoots();
        Files.deleteIfExists(copies.toPath());
        Files.deleteIfExists(metadata.toPath());
    }

    Recovery abort() throws IOException {
        setPhase(Phase.ABORTED);
        Recovery report = new Recovery();
        cleanCopies(report);
        return report;
    }

    private Map<String, Copy> readCopies() throws IOException {
        validateRoots();
        Map<String, Copy> result = new HashMap<>();
        if (!ManagedFiles.exists(copies)) return result;
        for (String line : Files.readAllLines(copies.toPath(), StandardCharsets.UTF_8)) {
            // A torn last append has no ownership authority. Preserve that file.
            try {
                String[] fields = line.split("\t", -1);
                if (fields.length != 3 || !fields[2].matches("[0-9a-f]{64}")) continue;
                String relative = new String(Base64.getDecoder().decode(fields[0]), StandardCharsets.UTF_8);
                long size = Long.parseLong(fields[1]);
                if (size < 0 || protectedPath(relative)) continue;
                ManagedFiles.child(gameStaging, relative);
                if (result.containsKey(relative)) throw new IOException("Duplicate import provenance: " + relative);
                result.put(relative, new Copy(size, fields[2]));
            } catch (IllegalArgumentException malformed) {
                // Invalid/incomplete provenance never authorizes deletion.
            }
        }
        return result;
    }

    private boolean completeGame(File game) throws IOException {
        validateRoots();
        File key = null;
        for (File child : list(game)) {
            if (child.getName().equalsIgnoreCase("chitin.key") && child.isFile()) key = child;
        }
        if (key == null || key.length() == 0) return false;
        Map<String, Copy> expected = readCopies();
        Set<String> actual = new HashSet<>();
        if (!verifyTree(game, game, expected, actual)) return false;
        return actual.equals(expected.keySet());
    }

    private static boolean verifyTree(File root, File directory, Map<String, Copy> expected, Set<String> actual) throws IOException {
        for (File file : list(directory)) {
            String relative = root.toPath().relativize(file.toPath()).toString().replace(File.separatorChar, '/');
            ManagedFiles.child(root, relative);
            if (protectedPath(relative)) continue;
            if (file.isDirectory()) {
                if (!verifyTree(root, file, expected, actual)) return false;
            } else {
                Copy copy = expected.get(relative);
                if (!matches(file, copy)) return false;
                actual.add(relative);
            }
        }
        return true;
    }

    private static boolean matches(File file, Copy copy) throws IOException {
        if (copy == null || !file.isFile() || file.length() != copy.size) return false;
        java.nio.file.attribute.BasicFileAttributes before = Files.readAttributes(file.toPath(),
                java.nio.file.attribute.BasicFileAttributes.class, java.nio.file.LinkOption.NOFOLLOW_LINKS);
        if (!before.isRegularFile() || !ManagedFiles.hash(file).equals(copy.hash)) return false;
        java.nio.file.attribute.BasicFileAttributes after = Files.readAttributes(file.toPath(),
                java.nio.file.attribute.BasicFileAttributes.class, java.nio.file.LinkOption.NOFOLLOW_LINKS);
        return after.isRegularFile() && before.size() == after.size()
                && before.lastModifiedTime().equals(after.lastModifiedTime())
                && java.util.Objects.equals(before.fileKey(), after.fileKey());
    }

    private void cleanCopies(Recovery report) throws IOException {
        validateRoots();
        Map<String, Copy> allowlist = readCopies();
        for (File root : new File[] { gameStaging, gameTarget }) {
            if (root.equals(gameTarget) && !gameTargetOwned) continue;
            for (Map.Entry<String, Copy> entry : allowlist.entrySet()) {
                File file;
                try { file = ManagedFiles.child(root, entry.getKey()); }
                catch (IOException unsafe) { report.notices.add(unsafe.getMessage()); continue; }
                if (!ManagedFiles.exists(file)) continue;
                if (matches(file, entry.getValue())) {
                    long size = file.length();
                    Files.delete(file.toPath());
                    report.removedBytes += size;
                    report.removedFiles.add(file + " (" + size + " bytes)");
                }
            }
            pruneEmpty(root, root);
        }
        // Empty transaction-owned save roots have no save data to preserve.
        for (File root : new File[] { saveStaging, saveTarget }) {
            if (root.equals(saveTarget) && !saveTargetOwned) continue;
            ManagedFiles.child(externalRoot, externalRoot.toPath().relativize(root.toPath()).toString());
            if (root.isDirectory() && list(root).length == 0) Files.delete(root.toPath());
        }
        boolean remnants = false;
        for (File path : new File[] { gameStaging, gameTarget, saveStaging, saveTarget }) {
            if (ManagedFiles.exists(path)) {
                remnants = true;
                report.notices.add("Preserved interrupted import: " + path + " (" + measure(path) + " bytes)");
            }
        }
        if (!remnants) forget();
    }

    private void validateRoots() throws IOException {
        // Keep the original external root as the anchor. Canonicalizing a cached
        // game root alone would follow a replaced `games` ancestor outside it.
        for (String relative : new String[] { "games/" + id, "games/" + id + ".tmp",
                "saves/" + id, "saves/" + id + ".tmp" }) {
            ManagedFiles.child(externalRoot, relative);
        }
        ManagedFiles.child(journalRoot, metadata.getName());
        ManagedFiles.child(journalRoot, copies.getName());
    }

    private static void pruneEmpty(File root, File directory) throws IOException {
        if (Files.isSymbolicLink(directory.toPath())) return;
        if (!ManagedFiles.exists(directory)) return;
        for (File child : list(directory)) {
            String relative = root.toPath().relativize(child.toPath()).toString().replace(File.separatorChar, '/');
            try { ManagedFiles.child(root, relative); }
            catch (IOException unsafe) { continue; }
            if (child.isDirectory() && !protectedPath(relative)) pruneEmpty(root, child);
        }
        if (list(directory).length == 0) Files.delete(directory.toPath());
    }

    static Recovery recover(File external, File journals, Registry registry) throws IOException {
        Recovery report = new Recovery();
        Set<String> journalIds = new HashSet<>();
        if (journals.isDirectory()) {
            for (File file : list(journals)) {
                if (!file.getName().endsWith(".properties")) continue;
                try {
                    ManagedFiles.child(journals, file.getName());
                    Properties values = new Properties();
                    try (java.io.Reader input = Files.newBufferedReader(file.toPath(), StandardCharsets.UTF_8)) {
                        values.load(input);
                    }
                    String id = values.getProperty("id", "");
                    if (!"1".equals(values.getProperty("schema")) || !file.getName().equals(id + ".properties")) {
                        throw new IOException("Unrecognized import journal: " + file);
                    }
                    ImportJournal journal = new ImportJournal(external, journals, id,
                            values.getProperty("name", "Recovered game"), values.getProperty("source", ""),
                            Phase.valueOf(values.getProperty("phase", "")));
                    journal.gameTargetOwned = Boolean.parseBoolean(values.getProperty("gameTargetOwned", "false"));
                    journal.saveTargetOwned = Boolean.parseBoolean(values.getProperty("saveTargetOwned", "false"));
                    journalIds.add(id);
                    if (registry.contains(id)) {
                        journal.registered(); // Never clean registered game/save data.
                    } else if (journal.phase != Phase.COPYING && journal.phase != Phase.ABORTED) {
                        File game = ManagedFiles.exists(journal.gameTarget) ? journal.gameTarget : journal.gameStaging;
                        if (!journal.completeGame(game)) {
                            report.notices.add("Changed or incomplete import preserved: " + game + " (" + measure(game) + " bytes)");
                            continue;
                        }
                        journal.promote();
                        registry.add(id, journal.name);
                        journal.registered();
                        report.notices.add("Recovered imported game: " + journal.name);
                    } else {
                        journal.cleanCopies(report);
                    }
                } catch (IOException | IllegalArgumentException error) {
                    report.notices.add("Import recovery requires attention: " + file + ": " + error.getMessage());
                }
            }
        }
        for (String category : new String[] { "games", "saves" }) {
            File directory;
            try { directory = ManagedFiles.child(external, category); }
            catch (IOException unsafe) { report.notices.add(unsafe.getMessage()); continue; }
            if (!directory.isDirectory()) continue;
            for (File child : list(directory)) {
                String id = child.getName().replaceFirst("\\.tmp$", "");
                if (isId(id) && !registry.contains(id) && !journalIds.contains(id)) {
                    try {
                        ManagedFiles.child(external, category + "/" + child.getName());
                        report.notices.add("Legacy import preserved for review: " + child + " (" + measure(child) + " bytes)");
                    } catch (IOException unsafe) { report.notices.add(unsafe.getMessage()); }
                }
            }
        }
        return report;
    }

    private static boolean isId(String id) {
        return id != null && id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
    }

    private static boolean protectedPath(String relative) {
        for (String part : relative.toLowerCase(java.util.Locale.ROOT).split("/")) {
            if (part.equals("save") || part.equals("mpsave") || part.equals("backup") || part.equals("backups")
                    || part.endsWith(".sav") || part.endsWith(".gam") || part.endsWith(".chr")
                    || part.endsWith(".bak") || part.endsWith(".log")) return true;
        }
        return false;
    }

    private static File[] list(File directory) throws IOException {
        File[] children = directory.listFiles();
        if (children == null) throw new IOException("Cannot inspect " + directory);
        return children;
    }

    private static long measure(File file) throws IOException {
        if (Files.isSymbolicLink(file.toPath())) return 0;
        if (!file.isDirectory()) return file.length();
        long bytes = 0;
        for (File child : list(file)) bytes += measure(child);
        return bytes;
    }
}
