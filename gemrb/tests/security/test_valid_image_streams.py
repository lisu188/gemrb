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
    start = text.index("\n" + signature) + 1
    cursor = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[cursor] == "{") - (text[cursor] == "}")
        cursor += 1
    return text[start:cursor]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--header-root", type=Path, help="Complete GemRB checkout (defaults to this checkout)")
    parser.add_argument("--config-directory", type=Path, required=True, help="CMake build directory containing generated config.h")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    headers = args.header_root or root
    if not (args.config_directory / "config.h").is_file():
        raise SystemExit("Configure GemRB first; --config-directory must contain its generated config.h")
    paths = {"TIS": "gemrb/plugins/TISImporter/TISImporter.cpp", "BIF": "gemrb/plugins/BIFImporter/BIFImporter.cpp", "SIZE": "gemrb/core/Video/ImageBufferSize.h", "RECT": "gemrb/core/Video/ImageCopyBounds.h"}
    source = {key: (root / path).read_text(encoding='utf-8') for key, path in paths.items()}
    template = Path(__file__).with_name("valid_image_streams.cpp.in").read_text(encoding='utf-8')
    for key, text in {"TIS_GET": function(source["TIS"], "Holder<Sprite2D> TISImporter::GetTilePVR("), "TIS_BLIT": function(source["TIS"], "void TISImporter::Blit("), "BIF_GET": function(source["BIF"], "DataStream* BIFImporter::GetStream(")}.items():
        template = template.replace("@" + key + "@", text)
    sprite_source = (headers / "gemrb/core/Sprite2D.cpp").read_text(encoding='utf-8')
    sprite_signatures = [
        "Sprite2D::Sprite2D(const Region& rgn, void* pixels, const PixelFormat& fmt, uint16_t pitch)",
        "Sprite2D::Sprite2D(const Sprite2D& obj)",
        "Sprite2D::~Sprite2D()",
        "bool Sprite2D::HasTransparency()",
        "const void* Sprite2D::LockSprite() const",
        "void* Sprite2D::LockSprite()",
    ]
    template = template.replace("@SPRITE_METHODS@", "\n".join(function(sprite_source, signature) for signature in sprite_signatures))
    region_source = (headers / "gemrb/core/Region.cpp").read_text(encoding='utf-8')
    template = template.replace("@REGION_METHODS@", "\n".join(function(region_source, signature) for signature in [
        "Region::Region(int x, int y, int w, int h)", "Region::Region(const Region& r)",
    ]))
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise SystemExit("A host C++ compiler is required")
    sdl_flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "sdl2"], text=True).split()
    with tempfile.TemporaryDirectory(prefix="gemrb-valid-image-streams-") as scratch:
        scratch = Path(scratch)
        path, executable = scratch / "valid_image_streams.cpp", scratch / "valid_image_streams"
        path.write_text(template, encoding='utf-8')
        compile_result = subprocess.run([compiler, "-std=c++14", "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-DFMT_HEADER_ONLY", "-I", str(args.config_directory), "-I", str(root / "gemrb/core"), "-I", str(headers / "gemrb/core"), "-I", str(headers / "gemrb/includes"), str(path), "-o", str(executable)] + sdl_flags, capture_output=True, text=True, timeout=60)
        if compile_result.returncode:
            print((compile_result.stdout + compile_result.stderr)[-6000:])
            raise SystemExit(compile_result.returncode)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        print(run.stdout + run.stderr, end="")
    actual_headers = ["gemrb/core/Sprite2D.h", "gemrb/core/Video/Pixels.h", "gemrb/core/Region.h", "gemrb/core/Sprite2D.cpp", "gemrb/core/Region.cpp"]
    report = {"passed": 3 if run.returncode == 0 else 0, "total": 3, "exit_code": run.returncode, "output": (run.stdout + run.stderr)[-2000:], "source_sha256": {paths[key]: hashlib.sha256(text.encode('utf-8')).hexdigest() for key, text in source.items()}, "api_sha256": {path: hashlib.sha256((headers / path).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for path in actual_headers}, "fixture_sha256": hashlib.sha256(Path(__file__).with_name("valid_image_streams.cpp.in").read_text(encoding="utf-8").encode("utf-8")).hexdigest(), "runner_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest(), "pitch_units": "bytes: SDL_CreateRGBSurfaceFrom reports 260 for a padded 64-pixel ARGB32 row; SDL allocated RGB24 rows report 65536 at width 21845 and 65532 at width 21844", "limits": "Production TIS/BIF selected functions, actual Sprite2D/PixelFormat/Region headers and selected constructors/accessors, real SDL surfaces, bounded stream/resource/factory/conversion adapters and ordinary valid data; no malformed-input, baseline, complete plugin, engine or renderer acceptance."}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
