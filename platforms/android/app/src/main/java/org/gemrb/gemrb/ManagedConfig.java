package org.gemrb.gemrb;

import java.io.File;

final class ManagedConfig {
    private ManagedConfig() {
    }

    static String build(
            File runtime,
            File gamePath,
            File savePath,
            File cachePath,
            String gameType
    ) {
        File gemrbData = new File(runtime, "gemrb");
        return "GameType=" + gameType + "\n"
                + "GamePath=" + gamePath.getAbsolutePath() + "\n"
                + "GemRBPath=" + gemrbData.getAbsolutePath() + "\n"
                + "GUIScriptsPath=" + gemrbData.getAbsolutePath() + "\n"
                + "GemRBOverridePath=" + gemrbData.getAbsolutePath() + "\n"
                + "GemRBUnhardcodedPath=" + gemrbData.getAbsolutePath() + "\n"
                + "SavePath=" + savePath.getAbsolutePath() + "\n"
                + "CachePath=" + cachePath.getAbsolutePath() + "\n"
                + "AudioDriver=openal\n"
                + "Logging=1\n"
                + "SkipIntroVideos=1\n"
                + "TouchInput=1\n"
                + "MouseFeedback=3\n"
                + "CaseSensitive=1\n"
                + "Width=640\n"
                + "Height=480\n";
    }
}
