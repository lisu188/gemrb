#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise production save creation through the preview image writer boundary.

The real save entry points, path preparation and serialization orchestration
run with controlled rendering and storage. Missing previews must be captured
before existing saves can be pruned or deleted. Real image encoding and game
serialization remain integration checks.
"""

from pathlib import Path
import subprocess
import unittest

from native_harness import run_tests


ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


BOUNDARIES = r'''
#include <algorithm>
#include <cassert>
#include <iostream>
#include <memory>
#include <string>
#include <utility>
#include <vector>
template<class T> using Holder = std::shared_ptr<T>;
template<class T> using PluginHolder = std::shared_ptr<T>;
using path_t = std::string;
struct StringView {
    std::string value;
    StringView() = default;
    StringView(const char* text) : value(text) {}
    explicit operator bool() const { return !value.empty(); }
};
namespace fmt {
template<class... Args> std::string format(const char* text, const Args&...) { return text; }
}
constexpr int GEM_ERROR = -1, GEM_OK = 0, ERROR = 1;
constexpr int FT_ANY = 0, PLUGIN_IMAGE_WRITER_BMP = 0, IE_BMP_CLASS_ID = 0;
namespace GUIColors { constexpr int XPCHANGE = 0; }
enum class HCStrings { CantSave, SaveSuccess, QSaveSuccess };
enum class GFFlags { HAS_EE_EFFECTS };
template<class... Args> void Log(int, const char*, const char*, const Args&...) {}
static std::vector<std::string> events;
static int denied = 0;
static int CanSave() { events.emplace_back("can-save"); return denied; }
struct Sprite2D {};
static Holder<Sprite2D> captured = std::make_shared<Sprite2D>();
static Holder<Sprite2D> supplied = std::make_shared<Sprite2D>();
static std::vector<Holder<Sprite2D>> written;
struct WindowManager {
    bool captureFails = false;
    Holder<Sprite2D> GetScreenshotPreview() {
        events.emplace_back("capture");
        return captureFails ? nullptr : captured;
    }
} windowManager;
struct SaveGame {
    int id = 1;
    int GetSaveID() const { return id; }
};
struct Extractor {
    bool isRunningSaveGame(const SaveGame&) const { return false; }
    int createCacheBlob() { events.emplace_back("cache"); return GEM_OK; }
};
struct Map {};
struct Actor {
    Holder<Sprite2D> CopyPortrait(bool) const { return nullptr; }
} actor;
struct Game {
    int GetLoadedMapCount() const { return 0; }
    Map* GetMap(int) const { return nullptr; }
    int GetPartySize(bool) const { return 1; }
    const Actor* GetPC(int, bool) const { return &actor; }
} game;
struct Core {
    struct { path_t SavePath = "saves", CachePath = "cache"; } config;
    Extractor saveGameAREExtractor;
    std::string GameNameResRef = "baldur";
    WindowManager* manager = &windowManager;
    WindowManager* GetWindowManager() const { return manager; }
    const Game* GetGame() const { return &game; }
    bool SwapoutArea(Map*) const { return false; }
    bool HasFeature(GFFlags) const { return true; }
    int WriteWorldMap(const path_t&) const { events.emplace_back("worldmap"); return 0; }
    int CompressSave(const path_t&, bool) const { events.emplace_back("compress"); return 0; }
    int WriteGame(const path_t&) const { events.emplace_back("game"); return 0; }
} coreStorage;
static Core* core = &coreStorage;
struct Table {
    StringView QueryField(int, int) const { return "Quick-Save"; }
    template<class T> T QueryFieldSigned(int, int) const { return 1; }
    int GetRowCount() const { return 6; }
};
using AutoTable = std::shared_ptr<Table>;
struct GameData {
    AutoTable LoadTable(const char*, bool = false) const { return std::make_shared<Table>(); }
    void SaveAllStores() { events.emplace_back("stores"); }
} gameDataStorage;
static GameData* gamedata = &gameDataStorage;
struct DisplayMessage {
    void DisplayMsgCentered(HCStrings, int, int) {}
} messageStorage;
static DisplayMessage* displaymsg = &messageStorage;
static path_t SaveDir() { return "save"; }
static path_t PathJoin(const path_t& first, const path_t& second) { return first + "/" + second; }
static bool MakeDirectory(const path_t&) { events.emplace_back("mkdir"); return true; }
static void DelTree(const path_t&, bool) { events.emplace_back("delete-tree"); }
static bool DirExists(const path_t&) { return false; }
struct FileStream {
    void Create(const path_t&, const path_t&, int) { events.emplace_back("create-image"); }
};
struct ImageWriter {
    void PutImage(FileStream*, Holder<Sprite2D> image) {
        // BMPWriter's production contract dereferences its image argument.
        assert(image);
        events.emplace_back("write-image");
        written.push_back(std::move(image));
    }
};
template<class T> PluginHolder<T> MakePluginHolder(int) { return std::make_shared<T>(); }
struct SaveGameIterator {
    std::vector<Holder<SaveGame>> save_slots;
    void DeleteSaveGame(const Holder<SaveGame>&) const { events.emplace_back("delete-save"); }
    void PruneQuickSave(StringView) const { events.emplace_back("prune"); }
    int CreateSaveGame(int, bool, Holder<Sprite2D>) const;
    int CreateSaveGame(Holder<SaveGame>, StringView, Holder<Sprite2D>, bool) const;
};
'''

SCENARIOS = r'''
static int count(const char* event) {
    return static_cast<int>(std::count(events.begin(), events.end(), event));
}
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string name = argv[1];
    const bool quick = name.find("quick") == 0;
    const bool explicitPreview = name.find("explicit") != std::string::npos;
    const bool missingManager = name.find("no_manager") != std::string::npos;
    const bool captureFailure = name.find("capture_fail") != std::string::npos;
    const bool rejected = name.find("denied") != std::string::npos;
    const bool force = name.find("forced") != std::string::npos;
    const bool rotating = name.find("rotating") != std::string::npos;
    const bool newSlot = name.find("new") != std::string::npos;
    SaveGameIterator iterator;
    auto existing = std::make_shared<SaveGame>();
    iterator.save_slots.push_back(existing);
    if (missingManager || explicitPreview) core->manager = nullptr;
    windowManager.captureFails = captureFailure;
    if (rejected || force) denied = 3;
    Holder<Sprite2D> preview = explicitPreview ? supplied : nullptr;
    const int result = quick ? iterator.CreateSaveGame(1, rotating, preview)
        : iterator.CreateSaveGame(newSlot ? nullptr : existing, "Named save", preview, force);
    const bool failed = missingManager || captureFailure || rejected;
    if (failed) {
        assert(result == (rejected ? denied : GEM_ERROR));
        for (const char* mutation : {"prune", "delete-save", "delete-tree", "mkdir",
                                     "stores", "worldmap", "compress", "game", "write-image"}) {
            assert(count(mutation) == 0);
        }
        assert(written.empty());
    } else {
        assert(result == GEM_OK);
        assert(written.size() == 1);
        assert(written.front() == (explicitPreview ? supplied : captured));
        assert(count("delete-save") == (newSlot ? 0 : 1));
        assert(count("prune") == (rotating ? 1 : 0));
        assert(count("compress") == 1 && count("game") == 1);
        if (!explicitPreview) {
            const auto capture = std::find(events.begin(), events.end(), "capture");
            for (const char* mutation : {"prune", "delete-save", "delete-tree", "mkdir", "write-image"}) {
                assert(capture < std::find(events.begin(), events.end(), mutation));
            }
        }
    }
    assert(count("can-save") == 1);
    assert(count("capture") == ((!explicitPreview && !missingManager && !rejected) ? 1 : 0));
    std::cout << name << " passed\n";
}
'''


def generate_harness():
    source = (ROOT / "core/SaveGameIterator.cpp").read_text()
    signatures = (
        "static bool DoSaveGame(",
        "static bool CreateSavePath(",
        "static bool PrepareSavePreview(",
        "int SaveGameIterator::CreateSaveGame(int index,",
        "int SaveGameIterator::CreateSaveGame(Holder<SaveGame> save, StringView",
    )
    return BOUNDARIES + "\n".join(function(source, signature) for signature in signatures) + SCENARIOS


class SavePreviewTests(unittest.TestCase):
    def scenario(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(name + " passed", result.stdout)

    def test_quicksave_captures_missing_preview(self): self.scenario("quick_omitted")
    def test_named_save_captures_missing_preview(self): self.scenario("named_omitted")
    def test_new_slot_captures_missing_preview(self): self.scenario("named_new")
    def test_rotating_quicksave_captures_before_pruning(self): self.scenario("quick_rotating")
    def test_quicksave_preserves_explicit_preview(self): self.scenario("quick_explicit")
    def test_named_save_preserves_explicit_preview(self): self.scenario("named_explicit")
    def test_quicksave_failed_capture_preserves_prior_save(self): self.scenario("quick_capture_fail_rotating")
    def test_named_failed_capture_preserves_prior_save(self): self.scenario("named_capture_fail")
    def test_quicksave_without_window_manager_preserves_prior_save(self): self.scenario("quick_no_manager")
    def test_named_without_window_manager_preserves_prior_save(self): self.scenario("named_no_manager")
    def test_denied_quicksave_does_not_capture_or_mutate(self): self.scenario("quick_denied")
    def test_denied_rotating_quicksave_preserves_prior_saves(self): self.scenario("quick_denied_rotating")
    def test_denied_named_save_does_not_capture_or_mutate(self): self.scenario("named_denied")
    def test_forced_named_save_still_captures_preview(self): self.scenario("named_forced")
    def test_forced_named_save_failed_capture_preserves_prior_save(self): self.scenario("named_forced_capture_fail")


if __name__ == "__main__":
    run_tests(SavePreviewTests, generate_harness)
