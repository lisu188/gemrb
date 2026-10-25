#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary table and traversal-cache initialization compatibility checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def function(text, signature):
    start = text.index("\n" + signature) + 1
    cursor = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[cursor] == "{") - (text[cursor] == "}")
        cursor += 1
    return text[start:cursor]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header-root", type=Path)
    parser.add_argument("--config-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    headers = args.header_root or root
    if not (args.config_directory / "config.h").is_file():
        raise SystemExit("--config-directory must contain GemRB's CMake-generated config.h")
    paths = ["gemrb/core/GameData.cpp", "gemrb/core/TraversabilityCache.cpp", "gemrb/core/TraversabilityCache.h", "gemrb/core/PathFinder.cpp"]
    sources = {path: (root / path).read_text(encoding="utf-8") for path in paths}
    traversal = sources["gemrb/core/TraversabilityCache.cpp"]
    update = function(traversal, "bool TraversabilityCache::Update()")
    update_prefix = update[:update.index("\n\t// determine all changes")] + "\n\treturn true;\n}"
    substitutions = {
        "SIZE_CTOR": function((headers / "gemrb/core/Region.cpp").read_text(encoding="utf-8"), "Size::Size(int w, int h)"),
        "TABLE_FUNCTION": function(sources["gemrb/core/GameData.cpp"], "int GameData::GetWeaponStyleAPRBonus("),
        "CELL_INDEX": function(traversal, "static size_t TraversalCellIndex("),
        "CACHED_CTOR": function(traversal, "TraversabilityCache::CachedActorsState::CachedActorsState("),
        "CACHED_RESERVE": function(traversal, "void TraversabilityCache::CachedActorsState::reserve("),
        "CACHED_CLEAR": function(traversal, "void TraversabilityCache::CachedActorsState::clear()"),
        "CACHE_VALIDATE": function(traversal, "bool TraversabilityCache::ValidateTraversabilityCacheSize()"),
        "CACHE_UPDATE_PREFIX": update_prefix,
    }
    fixture = Path(__file__).with_name("valid_container_caches.cpp.in").read_text(encoding="utf-8")
    unit = fixture
    for key, value in substitutions.items():
        unit = unit.replace("@" + key + "@", value)
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host C++ compiler is required")
    with tempfile.TemporaryDirectory(prefix="gemrb-valid-container-caches-") as scratch:
        scratch = Path(scratch)
        source, executable = scratch / "valid.cpp", scratch / "valid"
        source.write_text(unit, encoding="utf-8")
        command = [compiler, "-std=c++14", "-DNDEBUG", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-DFMT_HEADER_ONLY", "-I", str(args.config_directory), "-I", str(root / "gemrb/core"), "-I", str(headers / "gemrb/core"), "-I", str(headers / "gemrb/includes"), "-I/usr/include/SDL2", str(source), "-o", str(executable)]
        build = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if build.returncode:
            print((build.stdout + build.stderr)[-6000:])
            raise SystemExit(build.returncode)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        print(run.stdout + run.stderr, end="")
    api_paths = ["gemrb/core/TableMgr.h", "gemrb/core/Region.h", "gemrb/core/Region.cpp", "gemrb/core/Scriptable/Actor.h"]
    report = {"passed": 3 if run.returncode == 0 else 0, "total": 3, "exit_code": run.returncode, "source_sha256": {path: hashlib.sha256(text.encode()).hexdigest() for path, text in sources.items()}, "api_sha256": {path: hashlib.sha256((headers / path).read_text(encoding="utf-8").encode()).hexdigest() for path in api_paths}, "fixture_sha256": hashlib.sha256(fixture.encode()).hexdigest(), "runner_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(), "output": run.stdout + run.stderr, "limits": "Actual TableMgr/TraversabilityCache/geometry declarations with selected production table/size/index methods and actual Update prefix. Bounded resource/map/GameData field adapters replace the engine. Ordinary valid data and row/spare-cell addressing only; existing FitRegion uint16 wrapped-origin representation retained. No malformed/overflow/baseline probes, full actor update/pathfinding, engine or content acceptance."}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
