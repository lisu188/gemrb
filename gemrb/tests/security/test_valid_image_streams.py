#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary TIS row-copy and BIF substream compatibility fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def function(text, signature):
    start = text.index(signature)
    cursor = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[cursor] == "{") - (text[cursor] == "}")
        cursor += 1
    return text[start:cursor]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    paths = {"TIS": "gemrb/plugins/TISImporter/TISImporter.cpp", "BIF": "gemrb/plugins/BIFImporter/BIFImporter.cpp"}
    source = {key: (root / path).read_text() for key, path in paths.items()}
    template = Path(__file__).with_name("valid_image_streams.cpp.in").read_text()
    for key, text in {"TIS_GET": function(source["TIS"], "Holder<Sprite2D> TISImporter::GetTilePVR("), "TIS_BLIT": function(source["TIS"], "void TISImporter::Blit("), "BIF_GET": function(source["BIF"], "DataStream* BIFImporter::GetStream(")}.items():
        template = template.replace("@" + key + "@", text)
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host C++ compiler is required")
    with tempfile.TemporaryDirectory(prefix="gemrb-valid-image-streams-") as scratch:
        scratch = Path(scratch)
        path, executable = scratch / "valid_image_streams.cpp", scratch / "valid_image_streams"
        path.write_text(template)
        compile_result = subprocess.run([compiler, "-std=c++17", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-I", str(root / "gemrb/core"), str(path), "-o", str(executable)], capture_output=True, text=True, timeout=60)
        if compile_result.returncode:
            print((compile_result.stdout + compile_result.stderr)[-6000:])
            raise SystemExit(compile_result.returncode)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        print(run.stdout + run.stderr, end="")
    report = {"passed": 2 if run.returncode == 0 else 0, "total": 2, "exit_code": run.returncode, "output": (run.stdout + run.stderr)[-2000:], "source_sha256": {paths[key]: hashlib.sha256(text.encode()).hexdigest() for key, text in source.items()}, "limits": "Production TIS/BIF selected functions with bounded dependency adapters and ordinary valid data; no malformed-input, baseline, engine or renderer acceptance."}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
