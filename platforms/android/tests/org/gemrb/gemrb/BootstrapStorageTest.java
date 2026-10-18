package org.gemrb.gemrb;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/** Host-JDK tests exercise the same storage/state helpers as the Android UI. */
public final class BootstrapStorageTest {
    private static final String OLD = "1111111111111111111111111111111111111111111111111111111111111111";
    private static final String NEW = "2222222222222222222222222222222222222222222222222222222222222222";
    private static final class Registry implements ImportJournal.Registry {
        final Map<String, String> games = new HashMap<>();
        public boolean contains(String id) { return games.containsKey(id); }
        public void add(String id, String name) { games.put(id, name); }
    }
    private interface Test { void run(File root) throws Exception; }
    private interface Failing { void run() throws Exception; }

    public static void main(String[] args) throws Exception {
        fixture(BootstrapStorageTest::runtimeUpgrade);
        fixture(BootstrapStorageTest::runtimeFailure);
        coordinatorBoundaries();
        for (ImportJournal.Phase phase : ImportJournal.Phase.values()) fixture(root -> interrupted(root, phase));
        fixture(BootstrapStorageTest::interruptedRenames);
        fixture(BootstrapStorageTest::preserveUncertain);
        fixture(BootstrapStorageTest::registeredCleanupFailure);
        fixture(BootstrapStorageTest::containment);
        fixture(BootstrapStorageTest::legacyRemnants);
        System.out.println("Android bootstrap storage and cancellation regressions: OK");
    }

    private static void fixture(Test test) throws Exception {
        File parent = Files.createTempDirectory("gemrb-bootstrap-test-").toFile();
        File root = new File(parent, "case");
        root.mkdir();
        try { test.run(root); }
        finally { removeTestFiles(parent); }
    }

    private static void removeTestFiles(File file) throws IOException {
        if (!Files.isSymbolicLink(file.toPath()) && file.isDirectory()) {
            for (File child : file.listFiles()) removeTestFiles(child);
        }
        Files.delete(file.toPath());
    }

    private static File write(File root, String path, String value) throws IOException {
        File file = ManagedFiles.child(root, path);
        ManagedFiles.mkdir(file.getParentFile());
        Files.write(file.toPath(), value.getBytes(StandardCharsets.UTF_8));
        return file;
    }

    private static void runtimeFiles(File destination) throws IOException {
        write(destination, "gemrb/GUIScripts/GUICommon.py", "stock scripts");
        write(destination, "python/lib/python3.14/os.py", "stdlib");
        write(destination, "demo/chitin.key", "demo");
    }

    private static void runtimeUpgrade(File root) throws Exception {
        write(root, "m3-1/user-customization.py", "keep legacy");
        File old = RuntimeInstaller.ensure(root, OLD, BootstrapStorageTest::runtimeFiles);
        write(old, "user-customization.py", "keep old");
        File latest = RuntimeInstaller.ensure(root, NEW, destination -> {
            runtimeFiles(destination);
            write(destination, "gemrb/GUIScripts/GUICommon.py", "fixed scripts");
        });
        require(!latest.equals(old), "updated payload reused old runtime");
        require(new File(root, "m3-1/user-customization.py").isFile(), "legacy customization deleted");
        require(new File(old, "user-customization.py").isFile(), "old customization deleted");
        require(RuntimeInstaller.ensure(root, NEW, destination -> { throw new AssertionError("extracted unchanged payload"); }).equals(latest), "runtime not reused");
        require(RuntimeInstaller.readIdentity(new ByteArrayInputStream((NEW + "\n").getBytes(StandardCharsets.US_ASCII))).equals(NEW), "digest parsing failed");
        fails(() -> RuntimeInstaller.readIdentity(new ByteArrayInputStream("../escape".getBytes(StandardCharsets.US_ASCII))));
        write(root, "sha256-" + NEW + "/.complete", OLD);
        fails(() -> RuntimeInstaller.ensure(root, NEW, BootstrapStorageTest::runtimeFiles));
        require(new File(old, "user-customization.py").isFile(), "bad marker damaged old runtime");
    }

    private static void runtimeFailure(File root) throws Exception {
        File old = RuntimeInstaller.ensure(root, OLD, BootstrapStorageTest::runtimeFiles);
        write(old, "demo/save/slot.bak", "save");
        fails(() -> RuntimeInstaller.ensure(root, NEW, destination -> {
            write(destination, "partial", "partial");
            throw new IOException("injected extraction failure");
        }));
        require(new File(old, "demo/save/slot.bak").isFile(), "failure damaged previous save");
        require(root.listFiles().length == 1, "orderly extraction failure leaked scratch");
    }

    private static void coordinatorBoundaries() throws Exception {
        ImportCoordinator cancelled = new ImportCoordinator();
        require(cancelled.cancel(), "ready cancellation rejected");
        AtomicInteger writes = new AtomicInteger();
        require(!cancelled.commit(writes::incrementAndGet) && writes.get() == 0, "cancelled result registered");
        require(cancelled.finish() && !cancelled.finish(), "completion delivered twice");
        ImportCoordinator operation = new ImportCoordinator();
        CountDownLatch entering = new CountDownLatch(1);
        CountDownLatch persist = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            try {
                operation.commit(() -> {
                    entering.countDown();
                    try { persist.await(); } catch (InterruptedException error) { throw new IOException(error); }
                    writes.incrementAndGet();
                });
            } catch (IOException error) { throw new AssertionError(error); }
        });
        worker.start();
        entering.await();
        require(!operation.cancel(), "cancellation crossed commit boundary");
        persist.countDown();
        worker.join();
        require(operation.isCommitted() && !operation.cancel(), "registered result became cancellable");
        ImportCoordinator failed = new ImportCoordinator();
        fails(() -> failed.commit(() -> { throw new IOException("registry failure"); }));
        require(!failed.isCommitted() && failed.finish(), "registry failure stuck operation");
    }

    private static ImportJournal begin(File root) throws IOException {
        return ImportJournal.begin(root, new File(root, "journals"), UUID.randomUUID().toString(), "Baldur — próba", "content://source");
    }

    private static File record(ImportJournal journal, String path, String text) throws IOException {
        File file = write(journal.gameStaging, path, text);
        journal.copied(file, ManagedFiles.hash(file));
        return file;
    }

    private static ImportJournal.Recovery recover(File root, Registry registry) throws IOException {
        return ImportJournal.recover(root, new File(root, "journals"), registry);
    }

    private static void interrupted(File root, ImportJournal.Phase phase) throws Exception {
        ImportJournal journal = begin(root);
        record(journal, "chitin.key", "key");
        record(journal, "data/one.bif", "copied assets");
        write(journal.saveStaging, "save/slot/baldur.sav", "valuable save");
        Registry registry = new Registry();
        if (phase == ImportJournal.Phase.COPIED) journal.setPhase(phase);
        if (phase == ImportJournal.Phase.GAME_PROMOTED) {
            journal.setPhase(ImportJournal.Phase.COPIED);
            Files.move(journal.gameStaging.toPath(), journal.gameTarget.toPath());
            journal.setPhase(phase);
        }
        if (phase == ImportJournal.Phase.SAVES_PROMOTED || phase == ImportJournal.Phase.REGISTERED) {
            journal.setPhase(ImportJournal.Phase.COPIED);
            journal.promote();
            if (phase == ImportJournal.Phase.REGISTERED) {
                registry.add(journal.id, journal.name);
                journal.setPhase(phase);
            }
        }
        if (phase == ImportJournal.Phase.ABORTED) journal.setPhase(phase);
        ImportJournal.Recovery first = recover(root, registry);
        boolean aborted = phase == ImportJournal.Phase.COPYING || phase == ImportJournal.Phase.ABORTED;
        require(registry.contains(journal.id) != aborted, "wrong recovery outcome for " + phase);
        File saveRoot = aborted ? journal.saveStaging : journal.saveTarget;
        require(new File(saveRoot, "save/slot/baldur.sav").isFile(), "save deleted at " + phase);
        if (aborted) {
            require(first.removedBytes == 16 && !new File(journal.gameStaging, "data/one.bif").exists(), "copies not reclaimed");
            require(!first.notices.isEmpty(), "preserved save not reported");
        } else {
            require("Baldur — próba".equals(registry.games.get(journal.id)), "journal damaged Unicode display name");
            require(new File(journal.gameTarget, "data/one.bif").isFile(), "recovery damaged imported game");
        }
        require(recover(root, registry).removedBytes == 0, "recovery is not idempotent");
    }

    private static void interruptedRenames(File root) throws Exception {
        ImportJournal journal = begin(root);
        record(journal, "chitin.key", "key");
        journal.setPhase(ImportJournal.Phase.COPIED);
        Files.move(journal.gameStaging.toPath(), journal.gameTarget.toPath());
        Files.move(journal.saveStaging.toPath(), journal.saveTarget.toPath());
        Registry registry = new Registry();
        recover(root, registry);
        require(registry.contains(journal.id), "rename-before-journal crash was not recovered");
    }

    private static void preserveUncertain(File root) throws Exception {
        ImportJournal journal = begin(root);
        record(journal, "unchanged.bif", "safe");
        File modified = record(journal, "changed.bif", "before");
        Files.write(modified.toPath(), "after!".getBytes(StandardCharsets.UTF_8));
        File unknown = write(journal.gameStaging, "partial.bif", "unrecorded");
        File save = record(journal, "SAVE/slot/file.dat", "save");
        File looseSave = record(journal, "loose.sav", "save");
        ImportJournal.Recovery report = recover(root, new Registry());
        require(report.removedBytes == 4, "cleanup exceeded provenance allowlist");
        require(modified.isFile() && unknown.isFile() && save.isFile() && looseSave.isFile(), "uncertain data removed");
        require(report.notices.stream().anyMatch(s -> s.contains(journal.gameStaging.toString())), "retained path invisible");
        require(recover(root, new Registry()).removedBytes == 0, "cleanup repeated bytes");
    }

    private static void registeredCleanupFailure(File root) throws Exception {
        ImportJournal journal = begin(root);
        record(journal, "chitin.key", "key");
        journal.setPhase(ImportJournal.Phase.COPIED);
        journal.promote();
        Registry registry = new Registry();
        ImportCoordinator operation = new ImportCoordinator();
        operation.commit(() -> registry.add(journal.id, journal.name));
        File metadata = new File(root, "journals/" + journal.id + ".properties");
        Files.delete(metadata.toPath());
        metadata.mkdir();
        write(metadata, "unexpected", "preserve");
        fails(journal::registered);
        require(operation.isCommitted(), "journal failure reverted registry commit");
        recover(root, registry);
        require(new File(journal.gameTarget, "chitin.key").isFile(), "recovery cleaned registered data");
    }

    private static void containment(File root) throws Exception {
        fails(() -> ManagedFiles.child(root, "../outside"));
        ImportJournal journal = begin(root);
        record(journal, "chitin.key", "key");
        File outside = write(root, "outside/file", "outside").getParentFile();
        Files.createSymbolicLink(new File(journal.gameStaging, "escape").toPath(), outside.toPath());
        recover(root, new Registry());
        require(new File(outside, "file").isFile(), "cleanup followed child link");
        File games = new File(root, "games");
        Files.move(games.toPath(), new File(root, "preserved-games").toPath());
        File outsideStage = new File(outside, journal.id + ".tmp");
        write(outsideStage, "chitin.key", "key");
        Files.createSymbolicLink(games.toPath(), outside.toPath());
        fails(journal::abort);
        require(new File(outsideStage, "chitin.key").isFile(), "cleanup followed replaced ancestor");
        require(!recover(root, new Registry()).notices.isEmpty(), "unsafe ancestor not reported");
    }

    private static void legacyRemnants(File root) throws Exception {
        String id = UUID.randomUUID().toString();
        File orphan = write(root, "games/" + id + ".tmp/data.bif", "unproven");
        ImportJournal.Recovery report = recover(root, new Registry());
        require(orphan.isFile() && report.removedBytes == 0 && report.notices.size() == 1, "legacy remnant deleted or hidden");
    }

    private static void fails(Failing action) throws Exception {
        try { action.run(); throw new AssertionError("expected IOException"); }
        catch (IOException expected) { }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
