#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later

"""Compile and exercise the actual legacy extractor with a host JDK."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile


class LegacyAssetExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = shutil.which("java")
        javac = shutil.which("javac")
        if not cls.java or not javac:
            raise RuntimeError("A host JDK with java and javac is required")
        cls.compilation = tempfile.TemporaryDirectory(prefix="gemrb-legacy-extractor-")
        cls.addClassCleanup(cls.compilation.cleanup)
        cls.classes = Path(cls.compilation.name)
        source = (Path(__file__).resolve().parents[1] / "GemRB.java").read_text(encoding="utf-8")
        match = re.search(
            r"  private static void extractFolder\(.*?(?=\n  public void onConfigurationChanged)",
            source,
            re.DOTALL,
        )
        if match is None:
            raise AssertionError("Cannot locate the production extraction method")
        # Keep the complete production method unchanged. Only the Android
        # activity shell is replaced so host tests need no Android SDK/stubs.
        wrapper = (
            "import java.io.*;\nimport java.util.*;\nimport java.util.zip.*;\n"
            "public class LegacyExtractorUnderTest {\n"
            + match.group(0)
            + "\n  public static void main(String[] args) throws Exception {\n"
            "    try { extractFolder(args[0], args[1]); }\n"
            "    catch (IOException failure) {\n"
            "      File original = new File(args[0]);\n"
            "      File renamed = new File(args[0] + \".closed\");\n"
            "      if (!original.renameTo(renamed) || !renamed.renameTo(original))\n"
            "        throw new AssertionError(\"Cannot rename archive after failure\", failure);\n"
            "      throw failure;\n    }\n  }\n}\n"
        )
        java_source = cls.classes / "LegacyExtractorUnderTest.java"
        java_source.write_text(wrapper, encoding="utf-8")
        subprocess.run(
            [javac, "--release", "8", "-d", str(cls.classes), str(java_source)],
            check=True,
            capture_output=True,
            text=True,
        )

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="gemrb-legacy-assets-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.destination = self.root / "output"
        self.archive = self.root / "fixture.zip"

    def extract(self, entries):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, contents in entries:
                archive.writestr(name, contents)
        return subprocess.run(
            [self.java, "-cp", str(self.classes), "LegacyExtractorUnderTest", str(self.archive), str(self.destination)],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_refused(self, entry):
        result = self.extract([(entry, b"malicious overwrite")])
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("IOException", result.stderr)
        # The Java wrapper also checks rename while its process is still alive.
        renamed = self.archive.with_suffix(".closed.zip")
        self.archive.rename(renamed)

    def test_nested_assets_and_directory_entries(self):
        result = self.extract([
            ("assets/", b""),
            ("assets/GUIScripts/", b""),
            ("assets/GUIScripts/test.py", b"print('fixture')\n"),
            ("assets/override/za\u017c\u00f3\u0142\u0107.txt", b"unicode asset"),
        ])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"print('fixture')\n", (self.destination / "GUIScripts/test.py").read_bytes())
        self.assertEqual(b"unicode asset", (self.destination / "override/za\u017c\u00f3\u0142\u0107.txt").read_bytes())

    def test_only_exact_assets_prefix_is_extracted(self):
        result = self.extract([
            ("assets/normal.txt", b"normal"),
            ("classes.dex", b"ignored"),
            ("myasset/../not-an-asset.txt", b"ignored"),
            ("assetsSibling/not-an-asset.txt", b"ignored"),
        ])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["normal.txt"], sorted(p.name for p in self.destination.iterdir()))

    def test_normalized_root_directory_entries_are_allowed(self):
        result = self.extract([
            ("assets/./", b""),
            ("assets/folder/../", b""),
            ("assets/normal.txt", b"normal"),
        ])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"normal", (self.destination / "normal.txt").read_bytes())

    def test_root_resolving_file_entries_are_rejected(self):
        self.destination.mkdir()
        canary = self.destination / "existing.txt"
        canary.write_bytes(b"keep existing data")
        for entry in ("assets/.", "assets/folder/.."):
            with self.subTest(entry=entry):
                self.assert_refused(entry)
                self.assertEqual(b"keep existing data", canary.read_bytes())

    def test_parent_traversal_preserves_outside_file(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"keep existing data")
        self.assert_refused("assets/../outside.txt")
        self.assertEqual(b"keep existing data", outside.read_bytes())

    def test_nested_parent_traversal_preserves_outside_file(self):
        outside = self.root / "outside.txt"
        outside.write_bytes(b"keep existing data")
        self.assert_refused("assets/GUIScripts/../../outside.txt")
        self.assertEqual(b"keep existing data", outside.read_bytes())

    def test_sibling_with_same_path_prefix_is_rejected(self):
        sibling = self.root / "output-sibling"
        sibling.mkdir()
        outside = sibling / "outside.txt"
        outside.write_bytes(b"keep existing data")
        self.assert_refused("assets/../output-sibling/outside.txt")
        self.assertEqual(b"keep existing data", outside.read_bytes())

    def test_absolute_asset_name_is_rejected(self):
        outside = self.root / "absolute.txt"
        outside.write_bytes(b"keep existing data")
        self.assert_refused("assets/" + outside.as_posix())
        self.assertEqual(b"keep existing data", outside.read_bytes())

    def test_backslash_traversal_is_rejected_on_all_hosts(self):
        self.assert_refused("assets/..\\outside.txt")
        self.assertFalse((self.root / "outside.txt").exists())

    def test_existing_file_target_cannot_be_an_output_directory(self):
        self.destination.write_bytes(b"keep existing data")
        self.assert_refused("assets/file.txt")
        self.assertEqual(b"keep existing data", self.destination.read_bytes())

    def test_existing_child_symlink_cannot_escape(self):
        self.destination.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        canary = outside / "canary.txt"
        canary.write_bytes(b"keep existing data")
        link = self.destination / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Host cannot create the symlink fixture: {error}")
        self.assert_refused("assets/link/canary.txt")
        self.assertEqual(b"keep existing data", canary.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
