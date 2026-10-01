#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Serialized companion census regressions using small synthetic save records."""
from collections import Counter
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from companion_saved_actors import archive_bodies, area_bodies, creature_token, saved_bodies


def creature(tokens=(), name="", hp=7, state=0, extended=True):
    data = bytearray(0x2d4)
    data[:8] = b"CRE V1.0"
    data[0x33] = int(extended)
    struct.pack_into("<Ih", data, 0x20, state, hp)
    data[0x280:0x2a0] = name.encode("ascii").ljust(32, b"\0")
    struct.pack_into("<II", data, 0x2c4, len(data), len(tokens))
    for token in tokens:
        effect = bytearray(264 if extended else 48)
        if extended:
            struct.pack_into("<I", effect, 8, 187)
            struct.pack_into("<I", effect, 20, token)
            struct.pack_into("<H", effect, 64, 1)
            effect[160:192] = b"GMC_TOKEN".ljust(32, b"\0")
        data.extend(effect)
    return bytes(data)


def game(party=(), npcs=()):
    data = bytearray(0xb4 + (len(party) + len(npcs)) * 0x160)
    data[:8] = b"GAMEV2.1"
    struct.pack_into("<II", data, 0x20, 0xb4, len(party))
    struct.pack_into("<II", data, 0x30, 0xb4 + len(party) * 0x160, len(npcs))
    for index, cre in enumerate((*party, *npcs)):
        row = 0xb4 + index * 0x160
        struct.pack_into("<II", data, row + 4, len(data), len(cre))
        data.extend(cre)
    return bytes(data)


def area(*creatures):
    data = bytearray(0x11c)
    data[:8] = b"AREAV1.0"
    rows = []
    for cre in creatures:
        row = bytearray(0x110)
        struct.pack_into("<II", row, 0x88, len(data), len(cre))
        rows.append(row)
        data.extend(cre)
    struct.pack_into("<IH", data, 0x54, len(data), len(rows))
    for row in rows:
        data.extend(row)
    return bytes(data)


def member(name, data, declared_size=None):
    encoded = name.encode("ascii") + b"\0"
    compressed = zlib.compress(data)
    return (struct.pack("<I", len(encoded)) + encoded
            + struct.pack("<II", len(data) if declared_size is None else declared_size, len(compressed))
            + compressed)


class SavedCompanionTests(unittest.TestCase):
    def test_token_is_read_without_requiring_a_script_name_or_living_actor(self):
        self.assertEqual(creature_token(creature((4,), hp=0, state=0x800)),
                         {"token": 4, "hp": 0, "state": 0x800, "name": ""})
        self.assertEqual(creature_token(creature((5,), hp=2))["token"], 5)
        self.assertIsNone(creature_token(creature(name="ordinary actor")))
        self.assertIsNone(creature_token(creature(extended=False)))

    def test_duplicate_identical_local_records_are_one_actor(self):
        self.assertEqual(creature_token(creature((2, 2)))["token"], 2)
        for tokens in ((0,), (1, 2)):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                creature_token(creature(tokens))

    def test_party_npcs_and_every_saved_area_are_counted_separately(self):
        gam = game(party=[creature((1,), "gmcrabbit00000001")],
                   npcs=[creature((2,), "gmcrabbit00000002")])
        sav = (b"SAV V1.0" + member("AR0100.ARE", area(creature((1,), hp=0)))
               + member("AR0110.ARE", area(creature((1,), hp=2)))
               + member("default.tot", b""))
        with tempfile.TemporaryDirectory(prefix="gemrb-companion-census-") as temporary:
            folder = Path(temporary)
            gam_path, sav_path = folder / "gem-demo.gam", folder / "gem-demo.sav"
            gam_path.write_bytes(gam)
            sav_path.write_bytes(sav)
            result = saved_bodies(gam_path, sav_path)
        self.assertEqual(Counter(body["token"] for body in result["bodies"]), {1: 3, 2: 1})
        self.assertEqual([body["source"] for body in result["bodies"]],
                         ["GAM:party", "GAM:npc", "AR0100.ARE", "AR0110.ARE"])
        self.assertEqual(result["sha256"], {"gem-demo.gam": hashlib.sha256(gam).hexdigest(),
                                            "gem-demo.sav": hashlib.sha256(sav).hexdigest()})

    def test_area_header_and_embedded_cre_count_once_but_duplicate_rows_count_twice(self):
        cre = creature((3,), "gmcrabbit00000003")
        self.assertEqual(len(list(area_bodies(area(cre), "AR0100.ARE"))), 1)
        duplicate = list(area_bodies(area(cre, cre), "AR0100.ARE"))
        self.assertEqual([body["token"] for body in duplicate], [3, 3])
        self.assertEqual([body["index"] for body in duplicate], [0, 1])

    def test_all_retired_bodies_disappear_from_clean_second_roundtrip(self):
        sav = b"SAV V1.0" + member("AR0100.ARE", area(creature())) + member("AR0110.ARE", area())
        self.assertEqual(list(archive_bodies(sav)), [])

    def test_invalid_cre_headers_effect_bounds_and_formats_fail_closed(self):
        base = creature((1,))
        invalid = bytearray(base)
        struct.pack_into("<I", invalid, 0x2c8, 0xffffffff)
        format_ = bytearray(base)
        format_[0x33] = 2
        for data in (base[:20], b"CRE V2.2" + base[8:], invalid, format_):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                creature_token(data)

    def test_invalid_area_headers_and_actor_bounds_fail_closed(self):
        base = area(creature((1,)))
        invalid = bytearray(base)
        struct.pack_into("<I", invalid, 0x54, len(base) - 1)
        for data in (base[:50], b"AREAV9.1" + base[8:], invalid):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                list(area_bodies(data, "AR0100.ARE"))

    def test_archive_rejects_duplicate_members_truncation_and_wrong_expansion_size(self):
        are = area(creature((1,)))
        invalid = [
            b"SAV V1.0" + member("AR0100.ARE", are) + member("ar0100.are", are),
            b"SAV V1.0" + member("../AR0100.ARE", are),
            b"SAV V1.0" + member("AR0100.ARE", are, declared_size=len(are) - 1),
            b"SAV V1.0" + member("AR0100.ARE", are)[:-1],
            b"SAV V1.0\x01",
        ]
        for data in invalid:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                list(archive_bodies(data))


if __name__ == "__main__":
    unittest.main()
