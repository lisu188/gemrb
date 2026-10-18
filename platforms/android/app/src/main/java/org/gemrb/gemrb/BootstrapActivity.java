package org.gemrb.gemrb;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.HashSet;
import java.util.Set;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class BootstrapActivity extends Activity {
    private static final String TAG = "GemRB";
    private static final int REQUEST_IMPORT_GAME = 1001;
    private static final Object RUNTIME_INSTALL_LOCK = new Object();

    private final AtomicBoolean destroyed = new AtomicBoolean(false);
    private final AtomicBoolean launchStarted = new AtomicBoolean(false);

    private TextView statusView;
    private TextView recoveryView;
    private Button recoveryDetailsButton;
    private volatile String recoverySummary = "";
    private Button launchDemoButton;
    private LinearLayout importedGamesLayout;
    private Button importButton;
    private Button cancelButton;
    private volatile File runtimeDir;
    private volatile ImportCoordinator currentImport;
    private volatile Thread importThread;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        createUi();
        Thread bootstrapThread = new Thread(this::prepareRuntime, "GemRB-bootstrap");
        bootstrapThread.start();
    }

    @Override
    protected void onDestroy() {
        destroyed.set(true);
        ImportCoordinator operation = currentImport;
        if (operation != null) operation.cancel();
        Thread worker = importThread;
        if (worker != null) {
            worker.interrupt();
        }
        super.onDestroy();
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
        ImportCoordinator operation = new ImportCoordinator();
        currentImport = operation;
        Thread worker = new Thread(() -> importGame(treeUri, operation), "GemRB-game-import");
        importThread = worker;
        worker.start();
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

        recoveryView = new TextView(this);
        recoveryView.setMaxLines(8);

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
            ImportCoordinator operation = currentImport;
            if (operation != null && operation.cancel()) setStatus("Cancelling import…");
        });
        layout.addView(cancelButton);
        // Keep recovery details below ordinary controls and collapsed initially.
        recoveryDetailsButton = new Button(this);
        recoveryDetailsButton.setText("Show recovery details");
        recoveryDetailsButton.setVisibility(View.GONE);
        recoveryDetailsButton.setOnClickListener(view -> {
            boolean expand = recoveryView.getMaxLines() == 8;
            recoveryView.setMaxLines(expand ? Integer.MAX_VALUE : 8);
            recoveryDetailsButton.setText(expand ? "Hide recovery details" : "Show recovery details");
        });
        layout.addView(recoveryDetailsButton);
        layout.addView(recoveryView);

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.addView(layout, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));
        setContentView(scrollView);
    }

    private void prepareRuntime() {
        try {
            File preparedRuntime;
            synchronized (RUNTIME_INSTALL_LOCK) {
                preparedRuntime = ensureRuntimeLocked();
            }
            if (!isActivityUsable()) {
                return;
            }
            runtimeDir = preparedRuntime;
            recoverImports();
            if (!isActivityUsable()) return;
            if (!getSharedPreferences("bootstrap", MODE_PRIVATE).edit()
                    .putString("activeRuntime", preparedRuntime.getAbsolutePath()).commit()) {
                throw new IOException("Cannot activate the prepared runtime");
            }
            postIfActive(this::showReadyUi);
        } catch (Exception error) {
            fail("Android runtime bootstrap failed", error);
        }
    }

    private void showReadyUi() {
        setStatus("GemRB runtime ready.");
        displayRecovery();
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

    private void displayRecovery() {
        recoveryView.setText(recoverySummary);
        recoveryDetailsButton.setVisibility(recoverySummary.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void recoverImports() throws IOException {
        File external = getExternalFilesDir(null);
        if (external == null) throw new IOException("App-specific external storage is unavailable");
        File journals = ManagedFiles.child(getFilesDir(), "imports");
        Set<String> registered = new HashSet<>();
        ImportJournal.Recovery report;
        synchronized (ImportJournal.LOCK) {
            for (GameRegistry.Entry entry : GameRegistry.load(this)) registered.add(entry.gameId);
            report = ImportJournal.recover(external, journals, new ImportJournal.Registry() {
                public boolean contains(String id) { return registered.contains(id); }
                public void add(String id, String name) throws IOException {
                    GameRegistry.add(BootstrapActivity.this, id, name);
                    registered.add(id);
                }
            });
        }
        StringBuilder summary = new StringBuilder();
        if (report.removedBytes > 0) summary.append("Cleaned verified interrupted copies: ")
                .append(report.removedBytes).append(" bytes.\n");
        for (String notice : report.notices) {
            summary.append(notice).append('\n');
            Log.i(TAG, notice);
        }
        for (String removed : report.removedFiles) Log.i(TAG, "Removed verified copied asset: " + removed);
        File runtimeRoot = ManagedFiles.child(getFilesDir(), "runtime");
        File[] runtimes = runtimeRoot.listFiles();
        if (runtimes != null) {
            for (File previous : runtimes) {
                if (runtimeDir == null || !previous.getCanonicalFile().equals(runtimeDir.getCanonicalFile())) {
                    String notice = "Previous runtime preserved: " + previous;
                    summary.append(notice).append('\n');
                    Log.i(TAG, notice);
                }
            }
        }
        recoverySummary = summary.toString();
    }

    private void importGame(Uri treeUri, ImportCoordinator operation) {
        synchronized (ImportJournal.LOCK) { importGameLocked(treeUri, operation); }
    }

    private void importGameLocked(Uri treeUri, ImportCoordinator operation) {
        AtomicBoolean cancellation = operation.cancellation();
        GameImporter.Result result = null;
        boolean handedToLaunch = false;
        Exception failure = null;
        ImportJournal.Recovery aborted = null;
        try {
            result = GameImporter.importTree(this, treeUri, cancellation,
                    (copied, total, currentName) -> postIfActive(() -> {
                        if (cancellation.get()) return;
                        String progress = total > 0
                                ? String.format(Locale.US, "Importing %d%% — %s", Math.min(100, copied * 100L / total), currentName)
                                : "Importing — " + currentName;
                        setStatus(progress);
                    }));
            if (!isActivityUsable()) operation.cancel();
            final GameImporter.Result imported = result;
            // Cancellation and registry persistence have one serialized boundary.
            if (!operation.commit(() -> GameRegistry.add(this, imported.gameId, imported.displayName))) return;
            synchronized (ImportJournal.LOCK) { result.journal.registered(); }
            if (beginLaunch(null)) {
                handedToLaunch = true;
                launchGame(result.gamePath, result.gameId, "auto", null,
                        (started, error) -> finishImport(operation, started, error));
            }
        } catch (Exception error) {
            failure = error;
            if (error instanceof GameImporter.ImportFailure) aborted = ((GameImporter.ImportFailure) error).recovery;
        } finally {
            if (!operation.isCommitted() && result != null && !isRegistered(result.gameId)) {
                try { aborted = GameImporter.discardImportedResult(result); }
                catch (IOException cleanup) {
                    if (failure == null) failure = cleanup;
                    else failure.addSuppressed(cleanup);
                }
            }
            if (!handedToLaunch) {
                try { recoverImports(); }
                catch (IOException recovery) { Log.w(TAG, "Import recovery requires attention", recovery); }
                if (aborted != null) {
                    if (aborted.removedBytes > 0) recoverySummary = "Cleaned verified cancelled/failed copies: "
                            + aborted.removedBytes + " bytes.\n" + recoverySummary;
                    for (String notice : aborted.notices) {
                        if (!recoverySummary.contains(notice)) recoverySummary += notice + "\n";
                    }
                }
                finishImport(operation, false, failure);
            }
            if (importThread == Thread.currentThread()) importThread = null;
        }
    }

    private boolean isRegistered(String id) {
        for (GameRegistry.Entry entry : GameRegistry.load(this)) {
            if (entry.gameId.equals(id)) return true;
        }
        return false;
    }

    private void finishImport(ImportCoordinator operation, boolean started, Exception error) {
        if (!operation.finish()) return;
        if (error != null) Log.e(TAG, "Game import/launch failed", error);
        postIfActive(() -> {
            if (currentImport != operation || started) return;
            currentImport = null;
            launchStarted.set(false);
            setImporting(false);
            refreshImportedGames();
            displayRecovery();
            if (!operation.isCommitted() && operation.cancellation().get()) setStatus("Game import cancelled.");
            else if (error != null) setStatus("Game import/launch failed:\n" + error.getMessage());
            else if (operation.isCommitted()) setStatus("Imported game ready.");
            else setStatus("Game import cancelled.");
        });
    }

    private void launchDemo() {
        File currentRuntime = runtimeDir;
        if (currentRuntime == null || !isActivityUsable()) {
            return;
        }
        if (!beginLaunch(null)) {
            return;
        }
        File demoPath = new File(currentRuntime, "demo");
        new Thread(
                () -> launchGame(demoPath, "demo-bootstrap", "demo", null, this::finishLaunch),
                "GemRB-demo-launch"
        ).start();
    }

    private void launchImportedGame(GameRegistry.Entry entry) {
        File gamePath = managedGamePath(entry.gameId);
        if (gamePath == null || findCaseInsensitive(gamePath, "chitin.key") == null) {
            setStatus("Imported game storage is unavailable.");
            refreshImportedGames();
            return;
        }
        if (!beginLaunch(null)) {
            return;
        }
        GameRegistry.select(this, entry.gameId, entry.displayName);
        new Thread(
                () -> launchGame(gamePath, entry.gameId, "auto", null, this::finishLaunch),
                "GemRB-game-launch"
        ).start();
    }

    private interface LaunchCompletion { void finished(boolean started, Exception error); }

    private void finishLaunch(boolean started, Exception error) {
        if (error != null) Log.e(TAG, "Cannot launch GemRB", error);
        if (started) return;
        postIfActive(() -> {
            launchStarted.set(false);
            setImporting(false);
            refreshImportedGames();
            setStatus(error == null ? "Launch cancelled." : "Cannot launch GemRB:\n" + error.getMessage());
        });
    }

    private void launchGame(File gamePath, String saveId, String gameType,
                            AtomicBoolean cancellation, LaunchCompletion completion) {
        try {
            if (!isOperationUsable(cancellation)) {
                completion.finished(false, null);
                return;
            }
            File configFile = writeManagedConfig(runtimeDir, gamePath, saveId, gameType, cancellation);
            getSharedPreferences("bootstrap", MODE_PRIVATE).edit()
                    .putString("configPath", configFile.getAbsolutePath()).apply();
            runOnUiThread(() -> {
                if (!isOperationUsable(cancellation)) {
                    completion.finished(false, null);
                    return;
                }
                try {
                    startActivity(new Intent(BootstrapActivity.this, GemRBActivity.class));
                    completion.finished(true, null);
                    finish();
                } catch (Exception error) { completion.finished(false, error); }
            });
        } catch (Exception error) { completion.finished(false, error); }
    }

    private boolean beginLaunch(AtomicBoolean cancellation) {
        if (!isOperationUsable(cancellation) || !launchStarted.compareAndSet(false, true)) {
            return false;
        }
        postIfActive(() -> {
            launchDemoButton.setEnabled(false);
            setImportedButtonsEnabled(false);
            importButton.setEnabled(false);
            cancelButton.setVisibility(View.GONE);
            setStatus("Starting GemRB…");
        });
        return true;
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

    private File ensureRuntimeLocked() throws IOException {
        String identity;
        try (InputStream input = getAssets().open("runtime.sha256")) {
            identity = RuntimeInstaller.readIdentity(input);
        }
        File runtimeRoot = ManagedFiles.child(getFilesDir(), "runtime");
        File runtime = RuntimeInstaller.ensure(runtimeRoot, identity,
                destination -> RuntimeArchive.extract(getAssets(), "runtime.zip", destination));
        Log.i(TAG, "GEMRB_ANDROID_RUNTIME_ID=" + identity);
        return runtime;
    }

    private File writeManagedConfig(
            File runtime,
            File gamePath,
            String saveId,
            String gameType,
            AtomicBoolean cancellation
    ) throws IOException {
        if (runtime == null || gamePath == null || !gamePath.isDirectory()) {
            throw new IOException("Runtime or game path is unavailable");
        }
        File configDir = ManagedFiles.child(getFilesDir(), "config");
        File cacheDir = ManagedFiles.child(getCacheDir(), "gemrb");
        File externalRoot = getExternalFilesDir(null);
        if (externalRoot == null) {
            throw new IOException("App-specific external storage is unavailable");
        }

        File saveDir;
        try {
            saveDir = ManagedFiles.child(externalRoot, "saves/" + GamePaths.validateGameId(saveId));
        } catch (IllegalArgumentException error) {
            throw new IOException("Invalid managed game id", error);
        }

        if ((!configDir.isDirectory() && !configDir.mkdirs())
                || (!cacheDir.isDirectory() && !cacheDir.mkdirs())
                || (!saveDir.isDirectory() && !saveDir.mkdirs())) {
            throw new IOException("Cannot create Android GemRB data directories");
        }

        String config = ManagedConfig.build(runtime, gamePath, saveDir, cacheDir, gameType);
        File target = ManagedFiles.child(configDir, "GemRB.cfg");
        File staging = ManagedFiles.child(configDir, "GemRB.cfg.tmp");
        writeFile(staging, config);
        if (!isOperationUsable(cancellation)) {
            Files.deleteIfExists(staging.toPath());
            throw new IOException("Launch cancelled before config promotion");
        }
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
            return ManagedFiles.child(externalRoot, "games/" + GamePaths.validateGameId(gameId));
        } catch (IllegalArgumentException | IOException error) {
            Log.w(TAG, "Ignoring invalid managed game path", error);
            return null;
        }
    }

    private boolean isOperationUsable(AtomicBoolean cancellation) {
        return isActivityUsable() && (cancellation == null || !cancellation.get());
    }

    private boolean isActivityUsable() {
        return !destroyed.get() && !isFinishing() && !isDestroyed();
    }

    private void postIfActive(Runnable action) {
        if (!isActivityUsable()) {
            return;
        }
        runOnUiThread(() -> {
            if (isActivityUsable()) {
                action.run();
            }
        });
    }

    private void fail(String message, Exception error) {
        Log.e(TAG, message, error);
        postIfActive(() -> setStatus(message + ":\n" + error.getMessage()));
    }

    private void setStatus(String text) {
        statusView.setText(text);
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

}
