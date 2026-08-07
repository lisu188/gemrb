package org.gemrb.gemrb;

import java.io.File;

public final class GamePathsTest {
    public static void main(String[] args) throws Exception {
        File root = new File("/tmp/gemrb-android-path-test");
        File runtime = new File(root, "runtime");
        File cache = new File(root, "cache");
        String firstId = "11111111-1111-1111-1111-111111111111";
        String secondId = "22222222-2222-2222-2222-222222222222";

        File firstGame = GamePaths.gamePath(root, firstId);
        File secondGame = GamePaths.gamePath(root, secondId);
        File firstSave = GamePaths.savePath(root, firstId);
        File secondSave = GamePaths.savePath(root, secondId);

        require(!firstGame.getCanonicalPath().equals(secondGame.getCanonicalPath()), "game roots collide");
        require(!firstSave.getCanonicalPath().equals(secondSave.getCanonicalPath()), "save roots collide");
        require(firstSave.getPath().endsWith("saves" + File.separator + firstId), "first save root is not per-game");
        require(secondSave.getPath().endsWith("saves" + File.separator + secondId), "second save root is not per-game");

        String firstConfig = ManagedConfig.build(runtime, firstGame, firstSave, cache, "auto");
        String secondConfig = ManagedConfig.build(runtime, secondGame, secondSave, cache, "auto");
        require(firstConfig.contains("SavePath=" + firstSave.getAbsolutePath() + "\n"), "first config SavePath missing");
        require(secondConfig.contains("SavePath=" + secondSave.getAbsolutePath() + "\n"), "second config SavePath missing");
        require(firstConfig.contains("AudioDriver=openal\n"), "OpenAL audio driver missing");
        require(secondConfig.contains("AudioDriver=openal\n"), "OpenAL audio driver missing");
        require(!firstConfig.equals(secondConfig), "per-game configs are identical");

        expectInvalid("");
        expectInvalid("../escape");
        expectInvalid("a/b");
        expectInvalid("a\\b");
        expectInvalid(".hidden");
    }

    private static void expectInvalid(String gameId) {
        try {
            GamePaths.validateGameId(gameId);
            throw new AssertionError("accepted invalid game id: " + gameId);
        } catch (IllegalArgumentException expected) {
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
