package org.gemrb.gemrb;

import org.libsdl.app.SDLActivity;

import java.io.File;

public final class GemRBActivity extends SDLActivity {
    @Override
    protected String[] getArguments() {
        File config = new File(getFilesDir(), "config/GemRB.cfg");
        return new String[] { "-c", config.getAbsolutePath() };
    }
}
