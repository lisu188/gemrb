package org.gemrb.gemrb;

import android.app.Activity;
import android.content.Intent;
import android.content.res.AssetManager;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;

public final class BootstrapActivity extends Activity {
    private static final String TAG = "GemRB";
    private static final String RUNTIME_VERSION = "m1-1";
    private TextView statusView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        statusView = new TextView(this);
        statusView.setGravity(Gravity.CENTER);
        statusView.setText("Preparing GemRB runtime…");
        setContentView(statusView);

        Thread bootstrapThread = new Thread(this::bootstrap, "GemRB-bootstrap");
        bootstrapThread.start();
    }

    private void bootstrap() {
        try {
            File runtimeDir = ensureRuntime();
            File configFile = writeManagedConfig(runtimeDir);
            getSharedPreferences("bootstrap", MODE_PRIVATE)
                    .edit()
                    .putString("activeRuntime", runtimeDir.getAbsolutePath())
                    .putString("configPath", configFile.getAbsolutePath())
                    .apply();

            runOnUiThread(() -> {
                Intent intent = new Intent(BootstrapActivity.this, GemRBActivity.class);
                startActivity(intent);
                finish();
            });
        } catch (Exception error) {
            Log.e(TAG, "Android runtime bootstrap failed", error);
            runOnUiThread(() -> statusView.setText("GemRB bootstrap failed:\n" + error.getMessage()));
        }
    }

    private File ensureRuntime() throws IOException {
        File runtimeRoot = new File(getFilesDir(), "runtime");
        if (!runtimeRoot.isDirectory() && !runtimeRoot.mkdirs()) {
            throw new IOException("Cannot create runtime directory");
        }

        File runtimeDir = new File(runtimeRoot, RUNTIME_VERSION);
        File completeMarker = new File(runtimeDir, ".complete");
        if (completeMarker.isFile()) {
            validateRuntime(runtimeDir);
            return runtimeDir;
        }

        File stagingDir = new File(runtimeRoot, RUNTIME_VERSION + ".tmp");
        deleteTree(stagingDir);
        if (!stagingDir.mkdirs()) {
            throw new IOException("Cannot create runtime staging directory");
        }

        copyAssetTree(getAssets(), "runtime", stagingDir);
        validateRuntime(stagingDir);
        writeFile(new File(stagingDir, ".complete"), RUNTIME_VERSION + "\n");

        if (runtimeDir.exists()) {
            deleteTree(runtimeDir);
        }
        Files.move(
                stagingDir.toPath(),
                runtimeDir.toPath(),
                StandardCopyOption.ATOMIC_MOVE
        );
        return runtimeDir;
    }

    private void validateRuntime(File runtimeDir) throws IOException {
        requireFile(runtimeDir, "gemrb/GUIScripts/GUICommon.py");
        requireFile(runtimeDir, "python/lib/python3.14/os.py");
    }

    private File writeManagedConfig(File runtimeDir) throws IOException {
        File configDir = new File(getFilesDir(), "config");
        File cacheDir = new File(getCacheDir(), "gemrb");
        File externalRoot = getExternalFilesDir(null);
        if (externalRoot == null) {
            throw new IOException("App-specific external storage is unavailable");
        }
        File saveDir = new File(externalRoot, "saves/bootstrap");
        if ((!configDir.isDirectory() && !configDir.mkdirs())
                || (!cacheDir.isDirectory() && !cacheDir.mkdirs())
                || (!saveDir.isDirectory() && !saveDir.mkdirs())) {
            throw new IOException("Cannot create Android GemRB data directories");
        }

        File gemrbData = new File(runtimeDir, "gemrb");
        String config =
                "GameType=test\n" +
                "GamePath=" + gemrbData.getAbsolutePath() + "\n" +
                "GemRBPath=" + gemrbData.getAbsolutePath() + "\n" +
                "GUIScriptsPath=" + gemrbData.getAbsolutePath() + "\n" +
                "GemRBOverridePath=" + gemrbData.getAbsolutePath() + "\n" +
                "GemRBUnhardcodedPath=" + gemrbData.getAbsolutePath() + "\n" +
                "SavePath=" + saveDir.getAbsolutePath() + "\n" +
                "CachePath=" + cacheDir.getAbsolutePath() + "\n" +
                "AudioDriver=none\n" +
                "Logging=1\n" +
                "SkipIntroVideos=1\n" +
                "TouchInput=1\n" +
                "MouseFeedback=3\n" +
                "CaseSensitive=1\n";

        File target = new File(configDir, "GemRB.cfg");
        File staging = new File(configDir, "GemRB.cfg.tmp");
        writeFile(staging, config);
        Files.move(
                staging.toPath(),
                target.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING
        );
        return target;
    }

    private static void copyAssetTree(AssetManager assets, String assetPath, File destination) throws IOException {
        String[] children = assets.list(assetPath);
        if (children != null && children.length > 0) {
            if (!destination.isDirectory() && !destination.mkdirs()) {
                throw new IOException("Cannot create " + destination);
            }
            for (String child : children) {
                copyAssetTree(assets, assetPath + "/" + child, new File(destination, child));
            }
            return;
        }

        File parent = destination.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IOException("Cannot create " + parent);
        }
        try (InputStream input = assets.open(assetPath);
             FileOutputStream output = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        }
    }

    private static void requireFile(File root, String relativePath) throws IOException {
        File file = new File(root, relativePath);
        if (!file.isFile() || file.length() == 0) {
            throw new IOException("Runtime file missing: " + relativePath);
        }
    }

    private static void writeFile(File file, String value) throws IOException {
        try (FileOutputStream output = new FileOutputStream(file)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
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
}
