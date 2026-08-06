package org.gemrb.gemrb;

import android.app.Activity;
import android.content.Intent;
import android.content.res.AssetManager;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class BootstrapActivity extends Activity {
    private static final String TAG = "GemRB";
    private static final String RUNTIME_VERSION = "m3-1";
    private static final int REQUEST_IMPORT_GAME = 1001;

    private TextView statusView;
    private Button launchDemoButton;
    private LinearLayout importedGamesLayout;
    private Button importButton;
    private Button cancelButton;
    private File runtimeDir;
    private AtomicBoolean importCancelled;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        createUi();
        new Thread(this::prepareRuntime, "GemRB-bootstrap").start();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_IMPORT_GAME || resultCode != RESULT_OK || data == null) {
            return;
        }
        Uri treeUri = data.getData();
        if (treeUri == null) {
            setStatus("No game folder was selected.");
            return;
        }

        try {
            getContentResolver().takePersistableUriPermission(
                    treeUri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION
            );
        } catch (SecurityException error) {
            Log.w(TAG, "Document provider did not grant persistent read access", error);
        }

        setImporting(true);
        importCancelled = new AtomicBoolean(false);
        new Thread(() -> importGame(treeUri), "GemRB-game-import").start();
    }

    private void createUi() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int padding = Math.round(24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);

        statusView = new TextView(this);
        statusView.setGravity(Gravity.CENTER);
        statusView.setText("Preparing GemRB runtime…");
        layout.addView(statusView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        ));

        launchDemoButton = new Button(this);
        launchDemoButton.setText("Launch bundled demo");
        launchDemoButton.setVisibility(View.GONE);
        launchDemoButton.setOnClickListener(view -> launchDemo());
        layout.addView(launchDemoButton);

        importedGamesLayout = new LinearLayout(this);
        importedGamesLayout.setOrientation(LinearLayout.VERTICAL);
        layout.addView(importedGamesLayout, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        ));

        importButton = new Button(this);
        importButton.setText("Import game folder");
        importButton.setVisibility(View.GONE);
        importButton.setOnClickListener(view -> chooseGameFolder());
        layout.addView(importButton);

        cancelButton = new Button(this);
        cancelButton.setText("Cancel import");
        cancelButton.setVisibility(View.GONE);
        cancelButton.setOnClickListener(view -> {
            if (importCancelled != null) {
                importCancelled.set(true);
                setStatus("Cancelling import…");
            }
        });
        layout.addView(cancelButton);

        setContentView(layout);
    }

    private void prepareRuntime() {
        try {
            runtimeDir = ensureRuntime();
            getSharedPreferences("bootstrap", MODE_PRIVATE)
                    .edit()
                    .putString("activeRuntime", runtimeDir.getAbsolutePath())
                    .apply();
            runOnUiThread(this::showReadyUi);
        } catch (Exception error) {
            fail("Android runtime bootstrap failed", error);
        }
    }

    private void showReadyUi() {
        setStatus("GemRB runtime ready.");
        launchDemoButton.setVisibility(View.VISIBLE);
        importButton.setVisibility(View.VISIBLE);
        refreshImportedGames();
    }

    private void refreshImportedGames() {
        importedGamesLayout.removeAllViews();
        List<GameRegistry.Entry> entries = GameRegistry.load(this);
        for (GameRegistry.Entry entry : entries) {
            File gamePath = managedGamePath(entry.gameId);
            if (gamePath == null || findCaseInsensitive(gamePath, "chitin.key") == null) {
                continue;
            }
            Button launchButton = new Button(this);
            launchButton.setText("Launch " + entry.displayName);
            launchButton.setOnClickListener(view -> launchImportedGame(entry));
            importedGamesLayout.addView(launchButton);
        }
    }

    private void chooseGameFolder() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, REQUEST_IMPORT_GAME);
    }

    private void importGame(Uri treeUri) {
        try {
            GameImporter.Result result = GameImporter.importTree(
                    this,
                    treeUri,
                    importCancelled,
                    (copied, total, currentName) -> runOnUiThread(() -> {
                        String progress;
                        if (total > 0) {
                            int percent = (int) Math.min(100, (copied * 100L) / total);
                            progress = String.format(Locale.US, "Importing %d%% — %s", percent, currentName);
                        } else {
                            progress = "Importing — " + currentName;
                        }
                        setStatus(progress);
                    })
            );

            GameRegistry.add(this, result.gameId, result.displayName);
            launchGame(result.gamePath, result.gameId, "auto");
        } catch (Exception error) {
            fail("Game import failed", error);
            runOnUiThread(() -> {
                setImporting(false);
                refreshImportedGames();
            });
        }
    }

    private void launchDemo() {
        if (runtimeDir == null) {
            return;
        }
        File demoPath = new File(runtimeDir, "demo");
        new Thread(() -> launchGame(demoPath, "demo-bootstrap", "demo"), "GemRB-demo-launch").start();
    }

    private void launchImportedGame(GameRegistry.Entry entry) {
        File gamePath = managedGamePath(entry.gameId);
        if (gamePath == null || findCaseInsensitive(gamePath, "chitin.key") == null) {
            setStatus("Imported game storage is unavailable.");
            refreshImportedGames();
            return;
        }
        GameRegistry.select(this, entry.gameId, entry.displayName);
        new Thread(
                () -> launchGame(gamePath, entry.gameId, "auto"),
                "GemRB-game-launch"
        ).start();
    }

    private void launchGame(File gamePath, String saveId, String gameType) {
        try {
            File configFile = writeManagedConfig(runtimeDir, gamePath, saveId, gameType);
            getSharedPreferences("bootstrap", MODE_PRIVATE)
                    .edit()
                    .putString("configPath", configFile.getAbsolutePath())
                    .apply();
            runOnUiThread(() -> {
                Intent intent = new Intent(BootstrapActivity.this, GemRBActivity.class);
                startActivity(intent);
                finish();
            });
        } catch (Exception error) {
            fail("Cannot launch GemRB", error);
        }
    }

    private void setImporting(boolean importing) {
        launchDemoButton.setEnabled(!importing);
        setImportedButtonsEnabled(!importing);
        importButton.setEnabled(!importing);
        cancelButton.setVisibility(importing ? View.VISIBLE : View.GONE);
        if (importing) {
            setStatus("Scanning selected game folder…");
        }
    }

    private void setImportedButtonsEnabled(boolean enabled) {
        for (int i = 0; i < importedGamesLayout.getChildCount(); i++) {
            importedGamesLayout.getChildAt(i).setEnabled(enabled);
        }
    }

    private File ensureRuntime() throws IOException {
        File runtimeRoot = new File(getFilesDir(), "runtime");
        if (!runtimeRoot.isDirectory() && !runtimeRoot.mkdirs()) {
            throw new IOException("Cannot create runtime directory");
        }

        File runtime = new File(runtimeRoot, RUNTIME_VERSION);
        File completeMarker = new File(runtime, ".complete");
        if (completeMarker.isFile()) {
            validateRuntime(runtime);
            return runtime;
        }

        File stagingDir = new File(runtimeRoot, RUNTIME_VERSION + ".tmp");
        deleteTree(stagingDir);
        if (!stagingDir.mkdirs()) {
            throw new IOException("Cannot create runtime staging directory");
        }

        copyAssetTree(getAssets(), "runtime", stagingDir);
        validateRuntime(stagingDir);
        writeFile(new File(stagingDir, ".complete"), RUNTIME_VERSION + "\n");

        if (runtime.exists()) {
            deleteTree(runtime);
        }
        Files.move(stagingDir.toPath(), runtime.toPath(), StandardCopyOption.ATOMIC_MOVE);
        return runtime;
    }

    private void validateRuntime(File runtime) throws IOException {
        requireFile(runtime, "gemrb/GUIScripts/GUICommon.py");
        requireFile(runtime, "python/lib/python3.14/os.py");
        requireFile(runtime, "demo/chitin.key");
    }

    private File writeManagedConfig(
            File runtime,
            File gamePath,
            String saveId,
            String gameType
    ) throws IOException {
        if (runtime == null || gamePath == null || !gamePath.isDirectory()) {
            throw new IOException("Runtime or game path is unavailable");
        }
        File configDir = new File(getFilesDir(), "config");
        File cacheDir = new File(getCacheDir(), "gemrb");
        File externalRoot = getExternalFilesDir(null);
        if (externalRoot == null) {
            throw new IOException("App-specific external storage is unavailable");
        }

        File saveDir;
        try {
            saveDir = GamePaths.savePath(externalRoot, saveId);
        } catch (IllegalArgumentException error) {
            throw new IOException("Invalid managed game id", error);
        }

        if ((!configDir.isDirectory() && !configDir.mkdirs())
                || (!cacheDir.isDirectory() && !cacheDir.mkdirs())
                || (!saveDir.isDirectory() && !saveDir.mkdirs())) {
            throw new IOException("Cannot create Android GemRB data directories");
        }

        String config = ManagedConfig.build(runtime, gamePath, saveDir, cacheDir, gameType);
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

    private File managedGamePath(String gameId) {
        File externalRoot = getExternalFilesDir(null);
        if (externalRoot == null) {
            return null;
        }
        try {
            return GamePaths.gamePath(externalRoot, gameId);
        } catch (IllegalArgumentException error) {
            Log.w(TAG, "Ignoring invalid managed game id", error);
            return null;
        }
    }

    private void fail(String message, Exception error) {
        Log.e(TAG, message, error);
        runOnUiThread(() -> setStatus(message + ":\n" + error.getMessage()));
    }

    private void setStatus(String text) {
        statusView.setText(text);
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
