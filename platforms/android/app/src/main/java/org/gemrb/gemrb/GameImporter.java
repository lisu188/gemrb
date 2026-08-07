package org.gemrb.gemrb;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

final class GameImporter {
    interface ProgressListener {
        void onProgress(long copiedBytes, long totalBytes, String currentName);
    }

    static final class Result {
        final String gameId;
        final String displayName;
        final File gamePath;
        final File savePath;
        final long totalBytes;

        Result(String gameId, String displayName, File gamePath, File savePath, long totalBytes) {
            this.gameId = gameId;
            this.displayName = displayName;
            this.gamePath = gamePath;
            this.savePath = savePath;
            this.totalBytes = totalBytes;
        }
    }

    private static final class ScanResult {
        long totalBytes;
        boolean hasChitinKey;
    }

    private static final class CopyState {
        long copiedBytes;
        long lastReportedBytes;
    }

    private GameImporter() {
    }

    static Result importTree(
            Context context,
            Uri treeUri,
            AtomicBoolean cancelled,
            ProgressListener listener
    ) throws IOException {
        ContentResolver resolver = context.getContentResolver();
        String rootDocumentId = DocumentsContract.getTreeDocumentId(treeUri);
        Uri rootDocument = DocumentsContract.buildDocumentUriUsingTree(treeUri, rootDocumentId);
        String displayName = queryDisplayName(resolver, rootDocument);

        ScanResult scan = new ScanResult();
        scanTree(resolver, treeUri, rootDocumentId, true, cancelled, scan);
        if (!scan.hasChitinKey) {
            throw new IOException("Selected folder does not contain chitin.key");
        }

        File externalRoot = context.getExternalFilesDir(null);
        if (externalRoot == null) {
            throw new IOException("App-specific external storage is unavailable");
        }
        File gamesRoot = new File(externalRoot, "games");
        File savesRoot = new File(externalRoot, "saves");
        if ((!gamesRoot.isDirectory() && !gamesRoot.mkdirs())
                || (!savesRoot.isDirectory() && !savesRoot.mkdirs())) {
            throw new IOException("Cannot create managed game/save directories");
        }

        long freeBytes = externalRoot.getUsableSpace();
        long safetyMargin = 64L * 1024L * 1024L;
        if (scan.totalBytes > 0 && freeBytes < scan.totalBytes + safetyMargin) {
            throw new IOException(
                    "Not enough free space: need at least " + formatBytes(scan.totalBytes + safetyMargin)
            );
        }

        String gameId = UUID.randomUUID().toString();
        File staging = new File(gamesRoot, gameId + ".tmp");
        File target = GamePaths.gamePath(externalRoot, gameId);
        File saveStaging = GamePaths.saveStagingPath(externalRoot, gameId);
        File saveTarget = GamePaths.savePath(externalRoot, gameId);
        if (target.exists() || saveTarget.exists()) {
            throw new IOException("Generated managed game id already exists");
        }
        deleteTree(staging);
        deleteTree(saveStaging);
        if (!staging.mkdirs() || !saveStaging.mkdirs()) {
            throw new IOException("Cannot create game import staging directories");
        }

        CopyState copyState = new CopyState();
        boolean gamePromoted = false;
        boolean savesPromoted = false;
        try {
            copyTree(
                    resolver,
                    treeUri,
                    rootDocumentId,
                    staging,
                    cancelled,
                    scan.totalBytes,
                    copyState,
                    listener
            );
            File copiedKey = findCaseInsensitive(staging, "chitin.key");
            if (copiedKey == null || copiedKey.length() == 0) {
                throw new IOException("Imported game failed chitin.key validation");
            }

            migrateImportedSaveDirectories(staging, saveStaging);
            checkCancelled(cancelled);

            Files.move(staging.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE);
            gamePromoted = true;
            checkCancelled(cancelled);

            Files.move(saveStaging.toPath(), saveTarget.toPath(), StandardCopyOption.ATOMIC_MOVE);
            savesPromoted = true;
            checkCancelled(cancelled);
        } catch (Exception error) {
            deleteTree(staging);
            deleteTree(saveStaging);
            if (savesPromoted) {
                deleteTree(saveTarget);
            }
            if (gamePromoted) {
                deleteTree(target);
            }
            if (error instanceof IOException) {
                throw (IOException) error;
            }
            throw new IOException("Game import failed", error);
        }

        return new Result(gameId, displayName, target, saveTarget, scan.totalBytes);
    }

    static void discardImportedResult(Result result) throws IOException {
        IOException failure = null;
        try {
            deleteTree(result.gamePath);
        } catch (IOException error) {
            failure = error;
        }
        try {
            deleteTree(result.savePath);
        } catch (IOException error) {
            if (failure == null) {
                failure = error;
            } else {
                failure.addSuppressed(error);
            }
        }
        if (failure != null) {
            throw failure;
        }
    }

    private static void migrateImportedSaveDirectories(File gameStaging, File saveStaging) throws IOException {
        File[] children = gameStaging.listFiles();
        if (children == null) {
            throw new IOException("Cannot inspect imported game staging directory");
        }
        for (File child : children) {
            if (!child.isDirectory()) {
                continue;
            }
            String destinationName = GamePaths.importedSaveDirectoryName(child.getName());
            if (destinationName == null) {
                continue;
            }
            File destination = new File(saveStaging, destinationName);
            if (destination.exists()) {
                throw new IOException("Duplicate imported save directory: " + destinationName);
            }
            Files.move(child.toPath(), destination.toPath(), StandardCopyOption.ATOMIC_MOVE);
        }
    }

    private static void scanTree(
            ContentResolver resolver,
            Uri treeUri,
            String documentId,
            boolean root,
            AtomicBoolean cancelled,
            ScanResult result
    ) throws IOException {
        checkCancelled(cancelled);
        Uri childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, documentId);
        String[] projection = {
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_SIZE
        };

        try (Cursor cursor = resolver.query(childrenUri, projection, null, null, null)) {
            if (cursor == null) {
                throw new IOException("Cannot enumerate selected folder");
            }
            int idColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID);
            int nameColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DISPLAY_NAME);
            int typeColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE);
            int sizeColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_SIZE);
            while (cursor.moveToNext()) {
                checkCancelled(cancelled);
                String childId = cursor.getString(idColumn);
                String name = cursor.getString(nameColumn);
                String mimeType = cursor.getString(typeColumn);
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mimeType)) {
                    scanTree(resolver, treeUri, childId, false, cancelled, result);
                } else {
                    if (!cursor.isNull(sizeColumn)) {
                        long size = cursor.getLong(sizeColumn);
                        if (size > 0) {
                            result.totalBytes += size;
                        }
                    }
                    if (root && "chitin.key".equalsIgnoreCase(name)) {
                        result.hasChitinKey = true;
                    }
                }
            }
        }
    }

    private static void copyTree(
            ContentResolver resolver,
            Uri treeUri,
            String documentId,
            File destination,
            AtomicBoolean cancelled,
            long totalBytes,
            CopyState state,
            ProgressListener listener
    ) throws IOException {
        checkCancelled(cancelled);
        Uri childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, documentId);
        String[] projection = {
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE
        };

        try (Cursor cursor = resolver.query(childrenUri, projection, null, null, null)) {
            if (cursor == null) {
                throw new IOException("Cannot enumerate selected folder during copy");
            }
            int idColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID);
            int nameColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DISPLAY_NAME);
            int typeColumn = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE);
            while (cursor.moveToNext()) {
                checkCancelled(cancelled);
                String childId = cursor.getString(idColumn);
                String name = cursor.getString(nameColumn);
                String mimeType = cursor.getString(typeColumn);
                File childDestination = safeChild(destination, name);
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mimeType)) {
                    if (!childDestination.isDirectory() && !childDestination.mkdirs()) {
                        throw new IOException("Cannot create " + childDestination.getName());
                    }
                    copyTree(
                            resolver,
                            treeUri,
                            childId,
                            childDestination,
                            cancelled,
                            totalBytes,
                            state,
                            listener
                    );
                } else {
                    Uri childUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, childId);
                    copyFile(resolver, childUri, childDestination, cancelled, totalBytes, state, listener);
                }
            }
        }
    }

    private static void copyFile(
            ContentResolver resolver,
            Uri source,
            File destination,
            AtomicBoolean cancelled,
            long totalBytes,
            CopyState state,
            ProgressListener listener
    ) throws IOException {
        try (InputStream input = resolver.openInputStream(source);
             FileOutputStream output = new FileOutputStream(destination)) {
            if (input == null) {
                throw new IOException("Cannot open " + destination.getName());
            }
            byte[] buffer = new byte[256 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                checkCancelled(cancelled);
                output.write(buffer, 0, count);
                state.copiedBytes += count;
                if (listener != null
                        && (state.copiedBytes - state.lastReportedBytes >= 16L * 1024L * 1024L
                        || state.copiedBytes >= totalBytes)) {
                    state.lastReportedBytes = state.copiedBytes;
                    listener.onProgress(state.copiedBytes, totalBytes, destination.getName());
                }
            }
        }
    }

    private static String queryDisplayName(ContentResolver resolver, Uri documentUri) throws IOException {
        String[] projection = { DocumentsContract.Document.COLUMN_DISPLAY_NAME };
        try (Cursor cursor = resolver.query(documentUri, projection, null, null, null)) {
            if (cursor == null || !cursor.moveToFirst()) {
                throw new IOException("Cannot read selected folder metadata");
            }
            String value = cursor.getString(0);
            return value == null || value.isEmpty() ? "Imported game" : value;
        }
    }

    private static File safeChild(File parent, String displayName) throws IOException {
        if (displayName == null || displayName.isEmpty()
                || ".".equals(displayName) || "..".equals(displayName)
                || displayName.indexOf('/') >= 0 || displayName.indexOf('\\') >= 0) {
            throw new IOException("Invalid document name in selected tree");
        }
        File child = new File(parent, displayName);
        String parentPath = parent.getCanonicalPath() + File.separator;
        if (!child.getCanonicalPath().startsWith(parentPath)) {
            throw new IOException("Document path escapes managed game directory");
        }
        return child;
    }

    private static File findCaseInsensitive(File directory, String name) {
        File[] children = directory.listFiles();
        if (children == null) {
            return null;
        }
        for (File child : children) {
            if (child.isFile() && name.equalsIgnoreCase(child.getName())) {
                return child;
            }
        }
        return null;
    }

    private static void checkCancelled(AtomicBoolean cancelled) throws IOException {
        if (cancelled.get()) {
            throw new IOException("Game import cancelled");
        }
    }

    private static void deleteTree(File file) throws IOException {
        if (!file.exists()) {
            return;
        }
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteTree(child);
            }
        }
        if (!file.delete()) {
            throw new IOException("Cannot delete " + file);
        }
    }

    private static String formatBytes(long bytes) {
        double gib = bytes / (1024.0 * 1024.0 * 1024.0);
        return String.format(Locale.US, "%.2f GiB", gib);
    }
}
