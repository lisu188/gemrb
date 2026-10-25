#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded host probes of unchanged production parser functions and statements."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


CASES = [
    "plt-valid", "plt-wrap", "plt-truncated", "plt-palette", "plt-zero", "plt-preserve",
    "mve-valid", "mve-wrap", "mve-zero", "mve-truncate", "bam-valid", "bam-frame-limit", "bam-cycle-limit",
    "bam-frames", "bam-cycles", "mos-many", "mos-truncated", "wed-valid", "wed-wide",
    "wed-span", "wed-polygon", "spec-empty", "spec-space", "spec-eof", "spec-name",
    "spec-values", "spec-partial",
]


def function(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    cursor = opening + 1
    # These selected functions contain no braces in string literals/comments.
    while depth:
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
        cursor += 1
    return text[start:cursor]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="Read production source from this Git ref without changing the checkout")
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host GCC or Clang C++ compiler is required")
    receipts = {}

    def read(path):
        if args.baseline:
            text = subprocess.check_output(["git", "-C", str(repository), "show", args.baseline + ":" + path], text=True)
        else:
            text = (repository / path).read_text(encoding="utf-8")
        receipts[path] = hashlib.sha256(text.encode()).hexdigest()
        return text

    plt = read("gemrb/plugins/PLTImporter/PLTImporter.cpp")
    mve = read("gemrb/plugins/MVEPlayer/MVEPlayer.cpp")
    bam = read("gemrb/plugins/BAMImporter/BAMImporter.cpp")
    mos = read("gemrb/plugins/MOSImporter/MOSImporter.cpp")
    wed = read("gemrb/plugins/WEDImporter/WEDImporter.cpp")
    ini = read("gemrb/core/IniSpawn.cpp")
    spec_start = ini.index("\t\tieByte x[9];", ini.index('GetKeyAsString(crittername, "spec")'))
    spec_end = ini.index("\n\t}\n\n\tAssignScripts", spec_start)
    replacements = {
        "PLT_IMPORT": function(plt, "bool PLTImporter::Import("),
        "MVE_LIMIT": re.search(r"constexpr size_t MAX_BACKBUFSIZE = .*?;", mve).group(),
        "MVE_INITIALIZE": function(mve, "MVEPlayer::FrameResult MVEPlayer::InitializeVideo("),
        "BAM_IMPORT": function(bam, "bool BAMImporter::Import("),
        "MOS_IMPORT": function(mos, "bool MOSImporter::Import("),
        "MOS_SPRITE": function(mos, "Holder<Sprite2D> MOSImporter::GetSprite2Dv2("),
        "WED_GROUPS": function(wed, "std::vector<WallPolygonGroup> WEDImporter::GetWallGroups("),
        "INI_SPEC": ini[spec_start:spec_end],
    }
    fixture_template = Path(__file__).with_name("parser_bounds_probe.cpp.in").read_text(encoding="utf-8")
    template = fixture_template
    for key, text in replacements.items():
        template = template.replace("@" + key + "@", text)
    results = []
    with tempfile.TemporaryDirectory(prefix="gemrb-parser-bounds-") as scratch:
        root = Path(scratch)
        source = root / "probe.cpp"
        executable = root / "probe"
        source.write_text(template, encoding="utf-8")
        compile_command = [compiler, "-std=c++17", "-O1", "-g", "-fsanitize=address,undefined",
                           "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-o", str(executable), str(source)]
        subprocess.run(compile_command, check=True, capture_output=True, text=True, timeout=60)
        for case in args.case or CASES:
            result = subprocess.run([str(executable), case], capture_output=True, text=True, timeout=15)
            results.append({"case": case, "exit_code": result.returncode, "output": (result.stdout + result.stderr)[-5000:]})
            print(f"{case}: {'PASS' if result.returncode == 0 else 'FAIL'}")
    report = {"baseline": args.baseline, "compiler": compiler, "source_sha256": receipts,
              "fixture_sha256": hashlib.sha256(fixture_template.encode()).hexdigest(),
              "runner_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
              "passed": sum(r["exit_code"] == 0 for r in results), "total": len(results), "results": results,
              "limits": "Actual parser functions/statements with bounded dependency adapters; no complete engine, renderer, package or gameplay proof."}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failed = [r for r in results if r["exit_code"] != 0]
    for result in failed:
        print(result["output"])
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
