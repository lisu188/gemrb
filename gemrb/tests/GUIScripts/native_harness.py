# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate a native test source or exercise its CMake-built executable."""

import argparse
from pathlib import Path
import unittest


def run_tests(test_class, generate):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", type=Path, metavar="SOURCE")
    mode.add_argument("--binary", type=Path, metavar="EXECUTABLE")
    args, unittest_args = parser.parse_known_args()
    if args.generate:
        args.generate.parent.mkdir(parents=True, exist_ok=True)
        args.generate.write_text(generate(), encoding="utf-8")
        return
    test_class.binary = args.binary.resolve()
    if not test_class.binary.is_file():
        parser.error("build the native CMake test target before running this suite")
    unittest.main(argv=[str(test_class.binary)] + unittest_args)
