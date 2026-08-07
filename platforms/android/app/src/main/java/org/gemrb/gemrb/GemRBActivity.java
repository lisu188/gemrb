package org.gemrb.gemrb;

import android.content.res.Configuration;
import android.os.Bundle;
import android.system.ErrnoException;
import android.system.Os;
import android.util.Log;

import org.libsdl.app.SDLActivity;

import java.io.File;

public final class GemRBActivity extends SDLActivity {
    private static final String LOG_TAG = "GemRB";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        String runtimePath = getSharedPreferences("bootstrap", MODE_PRIVATE)
                .getString("activeRuntime", null);
        if (runtimePath == null) {
            throw new IllegalStateException("Android runtime has not been bootstrapped");
        }

        File runtime = new File(runtimePath);
        File pythonHome = new File(runtime, "python");
        File pythonPath = new File(pythonHome, "lib/python3.14");
        File gemrbData = new File(runtime, "gemrb");
        try {
            Os.setenv("PYTHONHOME", pythonHome.getAbsolutePath(), true);
            Os.setenv("PYTHONPATH", pythonPath.getAbsolutePath(), true);
            Os.setenv("PYTHONNOUSERSITE", "1", true);
            Os.setenv("PYTHONDONTWRITEBYTECODE", "1", true);
            Os.setenv("GEMRB_DATA", gemrbData.getAbsolutePath(), true);
        } catch (ErrnoException error) {
            throw new IllegalStateException("Cannot configure GemRB native environment", error);
        }

        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onPause() {
        super.onPause();
        Log.i(LOG_TAG, "GEMRB_ANDROID_ACTIVITY_PAUSED");
    }

    @Override
    protected void onResume() {
        super.onResume();
        Log.i(LOG_TAG, "GEMRB_ANDROID_ACTIVITY_RESUMED");
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        Log.i(LOG_TAG, "GEMRB_ANDROID_CONFIGURATION_CHANGED");
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        Log.i(LOG_TAG, hasFocus
                ? "GEMRB_ANDROID_WINDOW_FOCUS_GAINED"
                : "GEMRB_ANDROID_WINDOW_FOCUS_LOST");
    }

    @Override
    protected void onDestroy() {
        Log.i(LOG_TAG, "GEMRB_ANDROID_ACTIVITY_DESTROYED");
        super.onDestroy();
    }

    @Override
    protected String[] getArguments() {
        File config = new File(getFilesDir(), "config/GemRB.cfg");
        return new String[] { "-c", config.getAbsolutePath() };
    }
}
