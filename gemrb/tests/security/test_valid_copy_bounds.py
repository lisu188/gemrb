#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary BMP/BAM/MOS compatibility fixtures; no malformed inputs or baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def function(text, signature):
    start = text.index('\n' + signature) + 1
    cursor = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[cursor] == '{') - (text[cursor] == '}')
        cursor += 1
    return text[start:cursor]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header-root', required=True, type=Path)
    parser.add_argument('--config-directory', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    headers = args.header_root
    source = {}
    template = Path(__file__).with_name('valid_copy_bounds.cpp.in').read_text(encoding='utf-8')
    methods = {
        'BMP': ['bool BMPImporter::Import('],
        'BAM': ['bool BAMImporter::Import(', 'Holder<Sprite2D> BAMImporter::GetFrameInternal(', 'Holder<Sprite2D> BAMImporter::GetV2Frame(', 'bool BAMImporter::Blit(', 'bool BAMImporter::CacheFLT('],
        'MOS': ['bool MOSImporter::Import(', 'bool MOSImporter::Blit(', 'Holder<Sprite2D> MOSImporter::GetSprite2Dv1(', 'Holder<Sprite2D> MOSImporter::GetSprite2Dv2('],
    }
    for name, signatures in methods.items():
        path = f'gemrb/plugins/{name}Importer/{name}Importer.cpp'
        source[path] = (root / path).read_text(encoding='utf-8')
        template = template.replace('@' + name + '_METHODS@', '\n'.join(function(source[path], signature) for signature in signatures))
    api = ['gemrb/core/Sprite2D.h', 'gemrb/core/Video/Pixels.h', 'gemrb/core/Region.h', 'gemrb/core/Sprite2D.cpp', 'gemrb/core/Region.cpp', 'gemrb/core/Palette.cpp', 'gemrb/core/MurmurHash.cpp']
    sprite = (headers / 'gemrb/core/Sprite2D.cpp').read_text(encoding='utf-8')
    template = template.replace('@SPRITE_METHODS@', '\n'.join(function(sprite, signature) for signature in [
        'Sprite2D::Sprite2D(const Region& rgn, void* pixels, const PixelFormat& fmt, uint16_t pitch)',
        'Sprite2D::Sprite2D(const Sprite2D& obj)', 'Sprite2D::~Sprite2D()', 'bool Sprite2D::HasTransparency()',
        'const void* Sprite2D::LockSprite() const', 'void* Sprite2D::LockSprite()',
    ]))
    region = (headers / 'gemrb/core/Region.cpp').read_text(encoding='utf-8')
    template = template.replace('@REGION_METHODS@', '\n'.join(function(region, signature) for signature in [
        'BasePoint::BasePoint(int x, int y)', 'Size::Size(int w, int h)',
        'Region::Region(int x, int y, int w, int h)', 'Region::Region(const Region& r)',
        'Region& Region::operator=(const Region& rhs)',
    ]))
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'sdl2'], text=True).split()
    fixture_sources = {}
    for name in ['sample.bmp', 'sample_8bit.bmp', 'sample_v3.bmp', 'sample_v5.bmp']:
        relative = 'gemrb/tests/resources/BMPImporter/' + name
        fixture_sources[name] = root / relative if (root / relative).is_file() else headers / relative
    with tempfile.TemporaryDirectory(prefix='gemrb-valid-copy-', dir='/dev/shm') as scratch:
        scratch = Path(scratch)
        cpp, exe = scratch / 'valid_copy.cpp', scratch / 'valid_copy'
        cpp.write_text(template, encoding='utf-8')
        command = ['g++', '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-DFMT_HEADER_ONLY', '-I', str(args.config_directory), '-I', str(root / 'gemrb/core'), '-I', str(headers / 'gemrb/core'), '-I', str(headers / 'gemrb/includes'), str(cpp), str(headers / 'gemrb/core/Palette.cpp'), str(headers / 'gemrb/core/MurmurHash.cpp'), '-o', str(exe)] + flags
        build = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if build.returncode:
            print((build.stdout + build.stderr)[-10000:])
            raise SystemExit(build.returncode)
        fixture_directory = scratch / 'BMPImporter'
        fixture_directory.mkdir()
        for name, path in fixture_sources.items():
            shutil.copyfile(path, fixture_directory / name)
        run = subprocess.run([str(exe), str(fixture_directory)], capture_output=True, text=True, timeout=20)
    print(run.stdout + run.stderr, end='')
    for helper in ['gemrb/core/Video/ImageBufferSize.h', 'gemrb/core/Video/ImageCopyBounds.h']:
        source[helper] = (root / helper).read_text(encoding='utf-8')
    output = run.stdout + run.stderr
    report = {
        'passed': output.count(': PASS'), 'exit_code': run.returncode,
        'output': output[-5000:], 'command': command,
        'source_sha256': {path: hashlib.sha256(text.encode('utf-8')).hexdigest() for path, text in source.items()},
        'api_sha256': {path: hashlib.sha256((headers / path).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for path in api},
        'fixture_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in fixture_sources.items()},
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'template_sha256': hashlib.sha256(Path(__file__).with_name('valid_copy_bounds.cpp.in').read_bytes()).hexdigest(),
        'limits': 'Production selected import/decode/blit functions, actual Sprite2D/PixelFormat/Region declarations and selected implementations, actual Palette/MurmurHash, real SDL surfaces. Bounded stream/resource/factory adapters with ordinary valid data only. No malformed-input, baseline, full plugin/engine/rendering acceptance.',
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
