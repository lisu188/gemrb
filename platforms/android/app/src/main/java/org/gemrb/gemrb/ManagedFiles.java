package org.gemrb.gemrb;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** Files below a trusted app directory. Never follow a link during recovery. */
final class ManagedFiles {
    private ManagedFiles() { }

    static File child(File root, String relative) throws IOException {
        if (Files.isSymbolicLink(root.toPath())) throw new IOException("Preserving symbolic link: " + root);
        Path base = root.getCanonicalFile().toPath();
        Path path = base.resolve(relative).normalize();
        if (path.equals(base) || !path.startsWith(base)) {
            throw new IOException("Path escapes managed directory: " + relative);
        }
        Path current = base;
        for (Path part : base.relativize(path)) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) {
                throw new IOException("Preserving symbolic link: " + current);
            }
        }
        return path.toFile();
    }

    static void mkdir(File directory) throws IOException {
        if (Files.isSymbolicLink(directory.toPath())) throw new IOException("Preserving symbolic link: " + directory);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IOException("Cannot create " + directory);
        }
    }

    static void atomicWrite(File file, String text) throws IOException {
        File temporary = child(file.getParentFile(), file.getName() + ".new");
        try (FileOutputStream output = new FileOutputStream(temporary)) {
            output.write(text.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING);
    }

    static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new AssertionError(error);
        }
    }

    static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }

    static String hash(File file) throws IOException {
        MessageDigest digest = sha256();
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[128 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        return hex(digest.digest());
    }

    static boolean exists(File file) {
        return Files.exists(file.toPath(), LinkOption.NOFOLLOW_LINKS);
    }

    // Only for a fresh, task-owned runtime extraction; imported user data uses
    // the individual provenance allowlist in ImportJournal instead.
    static void removeFreshTree(File root, File file) throws IOException {
        File checked = child(root, root.getCanonicalFile().toPath()
                .relativize(file.toPath().toAbsolutePath().normalize()).toString());
        if (!exists(checked)) return;
        File[] children = checked.listFiles();
        if (children != null) {
            for (File child : children) removeFreshTree(root, child);
        }
        Files.delete(checked.toPath());
    }
}
