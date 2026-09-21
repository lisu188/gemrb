#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run persistent companion acceptance against the distributable GemRB demo."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

LIVE = r'''
import GemRB
import json
import os
import traceback
from pathlib import Path
from GUIDefines import SELECT_REPLACE
from ie_stats import IE_HITPOINTS, IE_MAXHITPOINTS, IE_MC_FLAGS

report_path = Path(os.environ["GEMRB_COMPANION_REPORT"])
phase = 0
expected = {}


def schedule():
    GemRB.SetTimer(run, 200, 0)


def reload_save(label):
    result = GemRB.SaveGame(None, label)
    assert result == 0, ("save failed", result)
    saves = [save for save in GemRB.GetSaveGames() if save.GetName() == label]
    assert len(saves) == 1, ("save not found", label)
    GemRB.LoadGame(saves[0])
    GemRB.SetNextScript("CompanionReload")


def run():
    global phase
    try:
        if phase == 0:
            assert GemRB.GetPartySize() == 2
            assert GemRB.ManageCompanion(1, "rabbit", 0) is None
            first = GemRB.ManageCompanion(1, "rabbit", 1)
            second = GemRB.ManageCompanion(2, "rabbit", 1)
            assert first["Created"] and second["Created"]
            assert first["ActorID"] != second["ActorID"]
            for row, hp in ((first, 3), (second, 7)):
                body = row["ActorID"]
                # Demo rabbits have MC_HIDE_HP, for which GetPlayerStat returns '?'.
                GemRB.SetPlayerStat(body, IE_MC_FLAGS, GemRB.GetPlayerStat(body, IE_MC_FLAGS, 1) & ~0x1000)
                GemRB.SetPlayerStat(body, IE_MAXHITPOINTS, 10)
                GemRB.SetPlayerStat(body, IE_HITPOINTS, hp)
                assert GemRB.GetPlayerStat(body, IE_HITPOINTS) == hp, ("fixture HP", body, GemRB.GetPlayerStat(body, IE_HITPOINTS), hp)
            expected["names"] = [GemRB.GetPlayerName(row["ActorID"], 2) for row in (first, second)]
            recalled = GemRB.ManageCompanion(1, "rabbit", 1)
            assert recalled["ActorID"] == first["ActorID"] and not recalled["Created"]
            assert GemRB.GetPlayerStat(first["ActorID"], IE_HITPOINTS) == 3
            GemRB.GameSelectPC(1, 1, SELECT_REPLACE)
            GemRB.MoveToArea("ar0110")
            assert not GemRB.ManageCompanion(1, "rabbit", 0)["InArea"]
            assert GemRB.ManageCompanion(1, "rabbit", 3)["InArea"]
            phase = 1
            reload_save("Companion Roundtrip A")
        elif phase == 1:
            first = GemRB.ManageCompanion(1, "rabbit", 3)
            second = GemRB.ManageCompanion(2, "rabbit", 3)
            assert first and second and first["Alive"] and second["Alive"]
            assert [GemRB.GetPlayerName(row["ActorID"], 2) for row in (first, second)] == expected["names"]
            assert GemRB.GetPlayerStat(first["ActorID"], IE_HITPOINTS) == 3
            assert GemRB.GetPlayerStat(second["ActorID"], IE_HITPOINTS) == 7
            GemRB.SetPlayerStat(first["ActorID"], IE_HITPOINTS, 0)
            assert not GemRB.ManageCompanion(1, "rabbit", 0)["Alive"]
            replacement = GemRB.ManageCompanion(1, "rabbit", 1)
            assert replacement["Created"] and replacement["ActorID"] != first["ActorID"]
            assert GemRB.GetPlayerName(replacement["ActorID"], 2) == expected["names"][0]
            GemRB.ManageCompanion(1, "rabbit", 2)
            assert GemRB.ManageCompanion(1, "rabbit", 0) is None
            assert GemRB.ManageCompanion(2, "rabbit", 0)["ActorID"] == second["ActorID"]
            phase = 2
            reload_save("Companion Roundtrip B")
        elif phase == 2:
            assert GemRB.ManageCompanion(1, "rabbit", 3) is None
            second = GemRB.ManageCompanion(2, "rabbit", 3)
            assert second and second["Alive"]
            assert GemRB.GetPlayerName(second["ActorID"], 2) == expected["names"][1]
            assert GemRB.GetPlayerStat(second["ActorID"], IE_HITPOINTS) == 7
            report_path.write_text(json.dumps({"passed": True, "save_roundtrips": 2,
                "checks": ["two owners", "injured recall", "area transfer", "saved names and locals",
                           "dead replacement", "dismissal persistence", "other owner preserved"]}, indent=2))
            GemRB.Quit()
    except Exception:
        report_path.write_text(json.dumps({"passed": False, "phase": phase, "error": traceback.format_exc()}, indent=2))
        GemRB.Quit()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--plugins", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    engine, output = args.engine.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit("Use a new output directory for companion acceptance")
    output.mkdir(parents=True)
    game, gui = output / "demo", output / "GUIScripts"
    shutil.copytree(engine / "demo", game)
    shutil.copytree(engine / "gemrb/GUIScripts", gui)
    (output / "cache").mkdir()
    (gui / "CompanionLive.py").write_text(LIVE)
    (gui / "demo/CompanionReload.py").write_text("import GemRB\n\ndef OnLoad():\n    GemRB.EnterGame()\n")
    setup = gui / "demo/SetupGame.py"
    setup.write_text(setup.read_text().replace('GemRB.EnterGame()', 'GemRB.CreatePlayer("protagon", 2|0x8000)\n\tGemRB.EnterGame()', 1))
    message = gui / "demo/MessageWindow.py"
    message.write_text(message.read_text().replace('def OnLoad():', 'def OnLoad():\n\timport CompanionLive\n\tCompanionLive.schedule()', 1))
    config = output / "GemRB.cfg"
    config.write_text(f"GameType=demo\nGamePath={game}\nGemRBPath={engine / 'gemrb'}\n"
                      f"GUIScriptsPath={gui.parent}\nPluginsPath={args.plugins.resolve()}\n"
                      f"CachePath={output / 'cache'}\nSavePath={game}\n"
                      "AudioDriver=none\nVideoDriver=SDL2\nWidth=800\nHeight=600\n"
                      "SkipIntroVideos=1\nSaveAsOriginal=1\n")
    report = output / "companion-report.json"
    env = os.environ.copy()
    env["GEMRB_COMPANION_REPORT"] = str(report)
    env["SDL_AUDIODRIVER"] = "dummy"
    with (output / "engine.log").open("w") as log:
        result = subprocess.run([str(args.binary.resolve()), "-c", str(config)],
                                stdout=log, stderr=subprocess.STDOUT, env=env, timeout=120)
    if not report.exists():
        raise SystemExit(f"No companion acceptance report; engine exit {result.returncode}; see {output / 'engine.log'}")
    data = json.loads(report.read_text())
    print(json.dumps(data, indent=2))
    if result.returncode != 0 or not data.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
