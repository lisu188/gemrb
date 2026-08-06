package org.gemrb.gemrb;

import java.io.File;

final class GamePaths {
    private GamePaths() {
    }

    static File gamePath(File externalRoot, String gameId) {
        return new File(new File(externalRoot, "games"), validateGameId(gameId));
    }

    static File savePath(File externalRoot, String gameId) {
        return new File(new File(externalRoot, "saves"), validateGameId(gameId));
    }

    static String validateGameId(String gameId) {
        if (gameId == null
                || gameId.isEmpty()
                || gameId.length() > 128
                || !gameId.matches("[A-Za-z0-9][A-Za-z0-9._-]*")) {
            throw new IllegalArgumentException("Invalid game id");
        }
        return gameId;
    }
}
