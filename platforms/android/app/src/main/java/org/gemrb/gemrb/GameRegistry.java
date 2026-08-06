package org.gemrb.gemrb;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class GameRegistry {
    static final class Entry {
        final String gameId;
        final String displayName;

        Entry(String gameId, String displayName) {
            this.gameId = gameId;
            this.displayName = displayName;
        }
    }

    private static final String PREFS = "bootstrap";
    private static final String KEY_GAMES = "importedGames";
    private static final String KEY_SELECTED_ID = "selectedGameId";
    private static final String KEY_SELECTED_NAME = "selectedGameName";

    private GameRegistry() {
    }

    static List<Entry> load(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        ArrayList<Entry> entries = new ArrayList<>();
        String raw = prefs.getString(KEY_GAMES, "[]");
        try {
            JSONArray array = new JSONArray(raw);
            for (int i = 0; i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item == null) {
                    continue;
                }
                String gameId = item.optString("id", "");
                String displayName = item.optString("name", "Imported game");
                try {
                    GamePaths.validateGameId(gameId);
                    entries.add(new Entry(gameId, displayName));
                } catch (IllegalArgumentException ignored) {
                }
            }
        } catch (JSONException ignored) {
        }

        String legacyId = prefs.getString(KEY_SELECTED_ID, null);
        if (legacyId != null && find(entries, legacyId) == null) {
            try {
                GamePaths.validateGameId(legacyId);
                entries.add(new Entry(
                        legacyId,
                        prefs.getString(KEY_SELECTED_NAME, "Imported game")
                ));
                save(context, entries);
            } catch (IllegalArgumentException ignored) {
            }
        }
        return entries;
    }

    static void add(Context context, String gameId, String displayName) {
        GamePaths.validateGameId(gameId);
        List<Entry> entries = load(context);
        Entry existing = find(entries, gameId);
        if (existing != null) {
            entries.remove(existing);
        }
        entries.add(new Entry(gameId, displayName));
        save(context, entries);
        select(context, gameId, displayName);
    }

    static void select(Context context, String gameId, String displayName) {
        GamePaths.validateGameId(gameId);
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_SELECTED_ID, gameId)
                .putString(KEY_SELECTED_NAME, displayName)
                .apply();
    }

    private static Entry find(List<Entry> entries, String gameId) {
        for (Entry entry : entries) {
            if (entry.gameId.equals(gameId)) {
                return entry;
            }
        }
        return null;
    }

    private static void save(Context context, List<Entry> entries) {
        JSONArray array = new JSONArray();
        for (Entry entry : entries) {
            JSONObject item = new JSONObject();
            try {
                item.put("id", entry.gameId);
                item.put("name", entry.displayName);
                array.put(item);
            } catch (JSONException ignored) {
            }
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_GAMES, array.toString())
                .apply();
    }
}
