package org.gemrb.gemrb;

import android.os.Bundle;
import android.system.ErrnoException;
import android.system.Os;

import org.libsdl.app.SDLActivity;

import java.io.File;

public final class GemRBActivity extends SDLActivity {
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
    protected String[] getArguments() {
        File config = new File(getFilesDir(), "config/GemRB.cfg");
        return new String[] { "-c", config.getAbsolutePath() };
    }
}
