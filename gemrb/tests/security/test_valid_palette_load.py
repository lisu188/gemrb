#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary shipped palette assets with the production LoadPalette template."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header-root', type=Path)
    parser.add_argument('--resource-root', type=Path)
    parser.add_argument('--config-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    headers = args.header_root or root
    resources = args.resource_root or headers
    source_path = root / 'gemrb/core/Interface.h'
    source = source_path.read_text(encoding='utf-8')
    signature = source.index('bool LoadPalette(')
    start = source.rfind('\ttemplate<int SIZE>', 0, signature)
    cursor = source.index('{', signature) + 1
    depth = 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    method = textwrap.dedent(source[start:cursor])
    template_path = Path(__file__).with_name('valid_palette_load.cpp.in')
    fixture = template_path.read_text(encoding='utf-8').replace('@LOAD_PALETTE@', method)
    api = ['gemrb/core/Sprite2D.cpp', 'gemrb/core/Region.cpp', 'gemrb/core/Video/Pixels.cpp',
           'gemrb/core/Palette.cpp', 'gemrb/core/MurmurHash.cpp']
    assets = ['demo/override/pal16.png', 'demo/override/palette.png',
              'gemrb/tests/minimal/data/palette0.png']
    compiler = shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise SystemExit('A host C++ compiler is required')
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'sdl2', 'libpng'], text=True).split()
    with tempfile.TemporaryDirectory(prefix='gemrb-valid-palettes-') as scratch:
        scratch = Path(scratch)
        cpp, binary = scratch / 'palette.cpp', scratch / 'palette'
        cpp.write_text(fixture, encoding='utf-8')
        command = [compiler, '-std=c++14', '-O1', '-g', '-fsanitize=address,undefined',
                   '-fno-sanitize-recover=all', '-DFMT_HEADER_ONLY', '-I', str(args.config_directory),
                   '-I', str(headers / 'gemrb/core'), '-I', str(headers / 'gemrb/includes'),
                   str(cpp)] + [str(headers / p) for p in api] + ['-o', str(binary)] + flags
        compile_result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if compile_result.returncode:
            print((compile_result.stdout + compile_result.stderr)[-6000:])
            raise SystemExit(compile_result.returncode)
        run = subprocess.run([str(binary)] + [str(resources / p) for p in assets],
                             capture_output=True, text=True, timeout=15)
        print(run.stdout + run.stderr, end='')
    api += ['gemrb/core/Sprite2D.h', 'gemrb/core/Video/Pixels.h', 'gemrb/core/Region.h',
            'gemrb/includes/RGBAColor.h']
    report = {
        'passed': 6 if run.returncode == 0 else 0, 'total': 6, 'exit_code': run.returncode,
        'output': (run.stdout + run.stderr)[-3000:],
        'production_sha256': {'gemrb/core/Interface.h': hashlib.sha256(source.encode('utf-8')).hexdigest()},
        'actual_api_sha256': {p: hashlib.sha256((headers / p).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for p in api},
        'resource_sha256': {p: hashlib.sha256((resources / p).read_bytes()).hexdigest() for p in assets},
        'runner_sha256': hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
        'fixture_sha256': hashlib.sha256(template_path.read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
        'limits': 'Production LoadPalette template with bounded resource lookup; complete actual Sprite2D/Pixels/Region/Palette/MurmurHash implementations and headers, libpng-decoded shipped assets, real SDL byte pitch, no display. No full Interface construction, plugin/engine build, asset-free library mode, malformed input or baseline execution.',
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
