# BMP, BAM and MOS copy-boundary compatibility fixtures

Run from a normal GemRB checkout or supply an actual header checkout:

```sh
python3 gemrb/tests/security/test_valid_copy_bounds.py \
  --header-root /path/to/gemrb \
  --config-directory /path/to/configured-build \
  --output /tmp/gemrb-valid-copy.json
```

The runner needs C++14, SDL2 development files, and GemRB's generated `config.h`.
It compiles selected production importer functions with address and undefined
behavior sanitizers. Sprite2D, PixelFormat and Region declarations are the real
project headers; selected Sprite2D/Region implementations, complete Palette and
MurmurHash implementations, and actual SDL surfaces supply the relevant APIs.
Bounded stream, resource and sprite-factory adapters supply ordinary valid data.
The full importer translation units must also pass the normal project build or a
syntax-only compilation against the actual headers.

The 15 ordinary fixtures cover:

- The existing `sample.bmp` and `sample_8bit.bmp` resources.
- Complete 24-bit bottom-up and top-down BMPs with padded rows.
- 8-bit full and reduced palettes, and odd-width 4-bit BMPs in both orientations.
- Complete 32-bit BMPs with 56-byte bitfield and 124-byte headers.
- BAM V1 raw and RLE frames, retained RLE data, and an ordinary lookup table.
- BAM V2 and MOS V2 source rows with a 16-byte pitch for 12 bytes of pixels,
  copied into a destination subrectangle.
- MOS V1 64x64 and 65x65 images, including partial right and bottom tiles.

Only the two complete existing BMP resources are executed. Header/length
inspection of the repository's `sample_v3.bmp` and `sample_v5.bmp` shows each
declares a 10x10 32-bit raster but retains only 320 raster bytes; 400 are required.
Their stale file-size fields also describe the original 24-bit file. Complete
generated 56-byte and 124-byte header fixtures provide the corresponding ordinary
format checks. The decoder requires the full raster before reading it.

The source changes use the shared `CheckedImageByteCount` helper from the BIF,
TIS and PNG follow-up. Its row limit reserves three bytes for SDL alignment before
the pitch is stored in Sprite2D's uint16 field. File wire widths are unchanged.
Animation frame/cycle counts and FLT lengths remain strictly below the factory's
reserved index value 65535; cycle endpoints are widened before addition.

The fixtures do not provide malformed-input, baseline, whole-plugin, complete
engine, decompression-wrapper, game rendering or owner acceptance evidence.
