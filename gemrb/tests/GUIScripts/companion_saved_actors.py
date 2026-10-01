# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Inspect companion bodies in original-format demo saves without engine APIs.

Include unnamed bodies and every saved area: name lookup alone cannot detect a
retired actor that lost its name before being incorrectly serialized again.
"""
import hashlib
from pathlib import Path
import struct
import zlib

MAX_RESOURCE = 64 * 1024 * 1024


def span(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError("Truncated saved resource")
    return data[offset:offset + size]


def number(data, offset, fmt="I"):
    return struct.unpack("<" + fmt, span(data, offset, struct.calcsize("<" + fmt)))[0]


def creature_token(cre):
    if span(cre, 0, 8) != b"CRE V1.0":
        raise ValueError("Unsupported saved creature format")
    span(cre, 0, 0x2d4)
    extended = number(cre, 0x33, "B")
    offset, count = number(cre, 0x2c4), number(cre, 0x2c8)
    if extended not in (0, 1):
        raise ValueError("Unsupported saved effect format")
    stride = 264 if extended else 48
    span(cre, offset, count * stride)
    tokens = []
    for index in range(count):
        effect = offset + stride * index
        if extended and number(cre, effect + 8) == 187:
            name = span(cre, effect + 160, 32).split(b"\0", 1)[0].upper()
            if name == b"GMC_TOKEN":
                tokens.append(number(cre, effect + 20))
    if not tokens:
        return None
    if len(set(tokens)) != 1 or not tokens[0]:
        raise ValueError("Invalid saved companion token")
    return {"token": tokens[0], "hp": number(cre, 0x24, "h"),
            "state": number(cre, 0x20),
            "name": span(cre, 0x280, 32).split(b"\0", 1)[0].decode("ascii")}


def area_bodies(data, name):
    if span(data, 0, 8) != b"AREAV1.0":
        raise ValueError("Unsupported saved area format")
    offset, count = number(data, 0x54), number(data, 0x58, "H")
    span(data, offset, count * 0x110)
    for index in range(count):
        row = offset + index * 0x110
        cre_offset, cre_size = number(data, row + 136), number(data, row + 140)
        if cre_offset and not number(data, row + 40) & 1:
            body = creature_token(span(data, cre_offset, cre_size))
            if body:
                yield dict(body, source=name, index=index)


def archive_bodies(data):
    if span(data, 0, 8) != b"SAV V1.0":
        raise ValueError("Unsupported save archive format")
    offset = 8
    names = set()
    expanded = 0
    while offset < len(data):
        size = number(data, offset)
        offset += 4
        if not 1 < size <= 256:
            raise ValueError("Invalid save member name length")
        raw_name = span(data, offset, size)
        if raw_name[-1:] != b"\0":
            raise ValueError("Unterminated save member name")
        name = raw_name[:-1].decode("ascii").upper()
        if name in names or "/" in name or "\\" in name:
            raise ValueError("Duplicate or unsafe save member name")
        names.add(name)
        offset += size
        unpacked, packed = number(data, offset), number(data, offset + 4)
        offset += 8
        if unpacked > MAX_RESOURCE or not 0 < packed <= MAX_RESOURCE:
            raise ValueError("Save member exceeds bounded resource size")
        expanded += unpacked
        if expanded > 8 * MAX_RESOURCE:
            raise ValueError("Save archive exceeds bounded expanded size")
        compressed = span(data, offset, packed)
        offset += packed
        if not name.endswith(".ARE"):
            continue
        decoder = zlib.decompressobj()
        area = decoder.decompress(compressed, unpacked + 1)
        if (len(area) != unpacked or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
            raise ValueError("Saved area decompression mismatch")
        yield from area_bodies(area, name)


def saved_bodies(gam, sav):
    paths = [Path(gam), Path(sav)]
    if any(path.stat().st_size > MAX_RESOURCE for path in paths):
        raise ValueError("Save exceeds bounded input size")
    game, archive = [path.read_bytes() for path in paths]
    if span(game, 0, 8) not in (b"GAMEV1.0", b"GAMEV1.1", b"GAMEV2.0", b"GAMEV2.1"):
        raise ValueError("Unsupported game save format")
    bodies = []
    for kind, header in (("party", 0x20), ("npc", 0x30)):
        offset, count = number(game, header), number(game, header + 4)
        span(game, offset, count * 0x160)
        for index in range(count):
            row = offset + index * 0x160
            cre_offset, cre_size = number(game, row + 4), number(game, row + 8)
            body = creature_token(span(game, cre_offset, cre_size))
            if body:
                bodies.append(dict(body, source="GAM:" + kind, index=index))
    bodies.extend(archive_bodies(archive))
    return {"bodies": bodies, "sha256": {
        path.name: hashlib.sha256(data).hexdigest()
        for path, data in zip(paths, (game, archive))}}
