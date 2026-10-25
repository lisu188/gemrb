#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the production loader's early wall-group result contract with stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    text = (root / "gemrb/plugins/AREImporter/AREImporter.cpp").read_text()
    start = text.index("Map* AREImporter::GetMap(")
    end = text.index("\n\tResRef TmpResRef;", start)
    prefix = text[start:end]
    assert "map->SetWallGroups(std::move(wallGroups));" in text[start:]
    assert "map->SetWallGroups(tmm->GetWallGroups());" not in text[start:]
    template = r'''
#include <iostream>
#include <vector>
using ResRef = int;
constexpr int AT_EXTENDED_NIGHT = 1, IE_WED_CLASS_ID = 1, ERROR = 1;
struct Map {} acceptedMap;
struct TileMap {} tileMap;
struct DataStream {} dataStream;
struct TileMapMgr {
    bool opened = true, hasWallGroups = true;
    int wallCalls = 0, tileCalls = 0;
    bool Open(DataStream*) { return opened; }
    std::vector<std::vector<int>> GetWallGroups() { ++wallCalls; return hasWallGroups ? std::vector<std::vector<int>>(1) : std::vector<std::vector<int>>(); }
    TileMap* GetTileMap(TileMap*) { ++tileCalls; return &tileMap; }
} manager;
template<typename T> using PluginHolder = T*;
template<typename T> T* MakePluginHolder(int) { return &manager; }
struct GameData { DataStream* GetResourceStream(ResRef, int) { return &dataStream; } } gameData;
GameData* gamedata = &gameData;
template<typename... T> void Log(T&&...) {}
struct AREImporter {
    int AreaFlags = 0;
    ResRef WEDResRef = 0;
    Map* GetMap(const ResRef&, bool);
};
@PREFIX@
    return &acceptedMap;
}
int main() {
    AREImporter importer;
    manager = {};
    manager.opened = false;
    if (importer.GetMap(0, true) || manager.wallCalls || manager.tileCalls) return 1;
    manager = {};
    manager.hasWallGroups = false;
    if (importer.GetMap(0, true) || manager.wallCalls != 1 || manager.tileCalls) return 2;
    manager = {};
    if (importer.GetMap(0, true) != &acceptedMap || manager.wallCalls != 1 || manager.tileCalls != 1) return 3;
    std::cout << "loader contract: 3/3 passed\n";
}
'''.replace("@PREFIX@", prefix)
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host C++ compiler is required")
    with tempfile.TemporaryDirectory(prefix="gemrb-wall-contract-") as scratch:
        scratch = Path(scratch)
        source, binary = scratch / "wall_contract.cpp", scratch / "wall_contract"
        source.write_text(template)
        build = subprocess.run([compiler, "-std=c++17", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", str(source), "-o", str(binary)], capture_output=True, text=True, timeout=60)
        if build.returncode:
            print((build.stdout + build.stderr)[-6000:])
            raise SystemExit(build.returncode)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        print(run.stdout + run.stderr, end="")
    receipt = {"passed": 3 if run.returncode == 0 else 0, "total": 3, "exit_code": run.returncode, "production_sha256": hashlib.sha256(text.encode()).hexdigest(), "limits": "Actual ARE GetMap prefix with dependency adapters, before tile-map/map construction; not complete map loading or rendering, no malformed file or baseline run."}
    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
