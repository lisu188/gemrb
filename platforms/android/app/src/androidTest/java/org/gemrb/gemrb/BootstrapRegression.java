package org.gemrb.gemrb;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicBoolean;

/** No test-library dependency: exercise bootstrap UI boundaries on an emulator. */
public final class BootstrapRegression extends Instrumentation {
    @Override
    public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        BootstrapActivity activity = null;
        try {
            Context context = getTargetContext();
            File legacy = new File(context.getFilesDir(), "runtime/m3-1");
            write(legacy, ".complete", "m3-1\n");
            write(legacy, "gemrb/GUIScripts/GUICommon.py", "old scripts");
            write(legacy, "python/lib/python3.14/os.py", "old stdlib");
            write(legacy, "demo/chitin.key", "old demo");
            File customization = write(legacy, "custom-mod.py", "preserved customization");
            File save = write(context.getExternalFilesDir(null), "saves/protected/save/slot.sav", "preserved save");
            activity = (BootstrapActivity) startActivitySync(new Intent(context, BootstrapActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            final BootstrapActivity target = activity;
            await(() -> ((Button) field(target, "launchDemoButton")).getVisibility() == View.VISIBLE
                    && ((Button) field(target, "launchDemoButton")).isEnabled());
            File active = (File) field(target, "runtimeDir");
            require(active.getName().startsWith("sha256-") && !active.equals(legacy), "legacy payload reused");
            require(customization.isFile() && save.isFile(), "upgrade deleted protected data");
            require(context.getSharedPreferences("bootstrap", Context.MODE_PRIVATE)
                    .getString("activeRuntime", "").equals(active.getAbsolutePath()), "runtime activation missing");

            ImportCoordinator operation = new ImportCoordinator();
            runOnMainSync(() -> {
                try {
                    setField(target, "currentImport", operation);
                    invoke(target, "setImporting", new Class<?>[] { boolean.class }, true);
                    operation.cancel(); // Completion arrives after the copy's last cancellation check.
                    invoke(target, "finishImport", new Class<?>[] { ImportCoordinator.class, boolean.class, Exception.class }, operation, false, null);
                    require(((Button) field(target, "importButton")).isEnabled(), "cancel left import disabled");
                    require(((Button) field(target, "launchDemoButton")).isEnabled(), "cancel left launch disabled");
                    require(((Button) field(target, "cancelButton")).getVisibility() == View.GONE, "cancel controls stuck");
                    require(((TextView) field(target, "statusView")).getText().toString().contains("cancelled"), "cancel completion missing");
                } catch (Exception error) { throw new RuntimeException(error); }
            });

            // A failed config promotion must also restore ordinary launch controls.
            File blocker = write(context.getFilesDir(), "config", "injected config failure");
            runOnMainSync(() -> {
                try { invoke(target, "launchDemo", new Class<?>[0]); }
                catch (Exception error) { throw new RuntimeException(error); }
            });
            await(() -> ((TextView) field(target, "statusView")).getText().toString().contains("Cannot launch GemRB")
                    && ((Button) field(target, "launchDemoButton")).isEnabled());
            Files.delete(blocker.toPath());
            require(customization.isFile() && save.isFile(), "launch failure deleted protected data");
            result.putString("stream", "BOOTSTRAP_REGRESSIONS_OK: legacy runtime upgrade, cancellation completion, launch failure controls\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            android.util.Log.e("GemRB", "Bootstrap instrumentation failed", error);
            result.putString("stream", "BOOTSTRAP_REGRESSIONS_FAILED: " + error + "\n");
            finish(Activity.RESULT_CANCELED, result);
        } finally {
            if (activity != null) {
                Activity target = activity;
                runOnMainSync(target::finish);
            }
        }
    }

    private interface Condition { boolean ready() throws Exception; }
    private void await(Condition condition) throws Exception {
        for (int i = 0; i < 240; ++i) {
            AtomicBoolean ready = new AtomicBoolean();
            runOnMainSync(() -> {
                try { ready.set(condition.ready()); }
                catch (Exception error) { throw new RuntimeException(error); }
            });
            if (ready.get()) return;
            Thread.sleep(500);
        }
        throw new AssertionError("bootstrap UI timed out");
    }

    private static Object field(Object object, String name) throws Exception {
        Field field = BootstrapActivity.class.getDeclaredField(name);
        field.setAccessible(true);
        return field.get(object);
    }

    private static void setField(Object object, String name, Object value) throws Exception {
        Field field = BootstrapActivity.class.getDeclaredField(name);
        field.setAccessible(true);
        field.set(object, value);
    }

    private static void invoke(Object object, String name, Class<?>[] types, Object... args) throws Exception {
        Method method = BootstrapActivity.class.getDeclaredMethod(name, types);
        method.setAccessible(true);
        method.invoke(object, args);
    }

    private static File write(File root, String relative, String contents) throws Exception {
        File file = new File(root, relative);
        file.getParentFile().mkdirs();
        Files.write(file.toPath(), contents.getBytes(StandardCharsets.UTF_8));
        return file;
    }

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
