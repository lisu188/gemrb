package org.gemrb.gemrb;

import android.content.res.AssetManager;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class RuntimeArchive {
    private static final String TAG = "GemRB";
    private static final int BUFFER_SIZE = 128 * 1024;
    private static final int PROGRESS_INTERVAL = 256;

    private RuntimeArchive() {
    }

    static void extract(AssetManager assets, String assetName, File destination) throws IOException {
        String destinationPath = destination.getCanonicalPath() + File.separator;
        byte[] buffer = new byte[BUFFER_SIZE];
        int filesExtracted = 0;
        long startedAt = System.nanoTime();
        Log.i(TAG, "GEMRB_ANDROID_RUNTIME_EXTRACT_START");

        try (InputStream assetInput = assets.open(assetName);
             ZipInputStream input = new ZipInputStream(new BufferedInputStream(assetInput, BUFFER_SIZE))) {
            ZipEntry entry;
            while ((entry = input.getNextEntry()) != null) {
                if (entry.getName().isEmpty()) {
                    input.closeEntry();
                    continue;
                }

                File target = new File(destination, entry.getName());
                String targetPath = target.getCanonicalPath();
                if (!targetPath.startsWith(destinationPath)) {
                    throw new IOException("Runtime archive entry escapes destination: " + entry.getName());
                }

                if (entry.isDirectory()) {
                    if (!target.isDirectory() && !target.mkdirs()) {
                        throw new IOException("Cannot create " + target);
                    }
                    input.closeEntry();
                    continue;
                }

                File parent = target.getParentFile();
                if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
                    throw new IOException("Cannot create " + parent);
                }

                try (BufferedOutputStream output = new BufferedOutputStream(
                        new FileOutputStream(target),
                        BUFFER_SIZE
                )) {
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        output.write(buffer, 0, count);
                    }
                }
                input.closeEntry();
                filesExtracted++;
                if (filesExtracted % PROGRESS_INTERVAL == 0) {
                    Log.i(TAG, "GEMRB_ANDROID_RUNTIME_EXTRACT_PROGRESS files=" + filesExtracted);
                }
            }
        }

        long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000L;
        Log.i(
                TAG,
                "GEMRB_ANDROID_RUNTIME_EXTRACT_DONE files=" + filesExtracted + " elapsedMs=" + elapsedMs
        );
    }
}
