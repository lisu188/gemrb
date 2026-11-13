#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary PNG-format compatibility fixtures using the production import path."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib


def function(text, signature):
    start = text.index(signature)
    cursor = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[cursor] == "{") - (text[cursor] == "}")
        cursor += 1
    return text[start:cursor]


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data))


def fixture(color, depth, transparency=False):
    rows, expected = [], bytearray()
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    maximum = (1 << depth) - 1
    for y in range(2):
        samples = []
        for x in range(3):
            index = y * 3 + x
            if color in (0, 3):
                value = index % (maximum + 1) if depth < 8 else (17 + index * 37) % 256
                sample = value * 256 + 41 if depth == 16 else value
                samples.append(sample)
                if color == 3:
                    expected.append(value)
                else:
                    grey = value if depth >= 8 else value * 255 // maximum
                    expected.extend((grey, grey, grey, 255))
            else:
                values = [(17 + index * 37 + c * 13) % 256 for c in range(channels)]
                samples.extend(v * 256 + 41 if depth == 16 else v for v in values)
                if color == 2:
                    expected.extend(values + [255])
                elif color == 4:
                    expected.extend([values[0]] * 3 + [values[1]])
                else:
                    expected.extend(values)
            if transparency and index == 0:
                expected[-1] = 0
        if depth < 8:
            encoded = bytearray((len(samples) * depth + 7) // 8)
            for i, sample in enumerate(samples):
                encoded[i * depth // 8] |= sample << (8 - depth - (i * depth % 8))
        else:
            encoded = b"".join(struct.pack(">H", v) for v in samples) if depth == 16 else bytes(samples)
        rows.append(b"\0" + encoded)
    header = struct.pack(">IIBBBBB", 3, 2, depth, color, 0, 0, 0)
    palette = chunk(b"PLTE", bytes(c for i in range(1 << depth) for c in (i, i, i))) if color == 3 else b""
    key = [17] if color == 0 else [17, 30, 43]
    trns = chunk(b"tRNS", b"".join(struct.pack(">H", v * 256 + 41 if depth == 16 else v) for v in key)) if transparency else b""
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + palette + trns + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""), expected.hex()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    production = root / "gemrb/plugins/PNGImporter/PNGImporter.cpp"
    text = production.read_text()
    template = Path(__file__).with_name("valid_png_import.cpp.in").read_text()
    for key, signature in {"READ_CALLBACK": "static void DataStream_png_read_data(", "CLOSE": "void PNGImporter::Close(", "IMPORT": "bool PNGImporter::Import("}.items():
        template = template.replace("@" + key + "@", function(text, signature))
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host C++ compiler and libpng development package are required")
    results = []
    formats = [(0, d, False) for d in (1, 2, 4, 8, 16)] + [(3, d, False) for d in (1, 2, 4, 8)] + [(c, d, False) for c in (2, 4, 6) for d in (8, 16)]
    formats += [(c, d, True) for c in (0, 2) for d in (8, 16)]
    with tempfile.TemporaryDirectory(prefix="gemrb-valid-png-") as scratch:
        scratch = Path(scratch)
        source, binary = scratch / "valid_png.cpp", scratch / "valid_png"
        source.write_text(template)
        command = [compiler, "-std=c++17", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-I", str(root / "gemrb/core"), str(source), "-lpng", "-o", str(binary)]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        for color, depth, transparency in formats:
            path = scratch / f"color{color}-depth{depth}-trns{int(transparency)}.png"
            data, expected = fixture(color, depth, transparency)
            path.write_bytes(data)
            run = subprocess.run([str(binary), str(path), expected], capture_output=True, text=True, timeout=15)
            results.append({"color_type": color, "bit_depth": depth, "transparency": transparency, "exit_code": run.returncode, "output": (run.stdout + run.stderr)[-2000:]})
            print(f"color{color}-depth{depth}-trns{int(transparency)}: {'PASS' if run.returncode == 0 else 'FAIL'}")
    report = {"production_sha256": hashlib.sha256(text.encode()).hexdigest(), "passed": sum(r["exit_code"] == 0 for r in results), "total": len(results), "results": results, "limits": "Production PNG import/transform callback with a bounded stream adapter and ordinary valid PNGs; no renderer, full engine, malformed-input or baseline run."}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
