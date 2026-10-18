package org.gemrb.gemrb;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.UUID;

/** Content-addressed installation; older runtimes may contain user changes. */
final class RuntimeInstaller {
    interface Extractor { void extract(File destination) throws IOException; }
    private RuntimeInstaller() { }

    static String readIdentity(InputStream input) throws IOException {
        byte[] bytes = new byte[66];
        int count = 0;
        int read;
        while (count < bytes.length && (read = input.read(bytes, count, bytes.length - count)) != -1) count += read;
        String value = new String(bytes, 0, count, StandardCharsets.US_ASCII).trim();
        if (count == bytes.length || !value.matches("[0-9a-f]{64}")) {
            throw new IOException("Invalid packaged runtime digest");
        }
        return value;
    }

    static File ensure(File root, String digest, Extractor extractor) throws IOException {
        if (!digest.matches("[0-9a-f]{64}")) throw new IOException("Invalid runtime digest");
        ManagedFiles.mkdir(root);
        String name = "sha256-" + digest;
        File target = ManagedFiles.child(root, name);
        if (ManagedFiles.exists(target)) {
            File marker = ManagedFiles.child(target, ".complete");
            if (!marker.isFile() || !new String(Files.readAllBytes(marker.toPath()), StandardCharsets.US_ASCII).trim().equals(digest)) {
                throw new IOException("Incomplete runtime preserved for recovery: " + target);
            }
            validate(target);
            return target;
        }
        File staging = ManagedFiles.child(root, name + ".tmp-" + UUID.randomUUID());
        ManagedFiles.mkdir(staging);
        try {
            extractor.extract(staging);
            validate(staging);
            ManagedFiles.atomicWrite(ManagedFiles.child(staging, ".complete"), digest + "\n");
            Files.move(staging.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE);
            return target;
        } catch (IOException | RuntimeException error) {
            try { ManagedFiles.removeFreshTree(root, staging); }
            catch (IOException cleanup) { error.addSuppressed(cleanup); }
            throw error;
        }
    }

    static void validate(File runtime) throws IOException {
        for (String relative : new String[] { "gemrb/GUIScripts/GUICommon.py", "python/lib/python3.14/os.py", "demo/chitin.key" }) {
            File file = ManagedFiles.child(runtime, relative);
            if (!file.isFile() || file.length() == 0) throw new IOException("Runtime file missing: " + relative);
        }
    }
}
