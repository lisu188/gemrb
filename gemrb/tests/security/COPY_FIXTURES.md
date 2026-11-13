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

The 23 ordinary fixtures cover:

- The existing `sample.bmp` and `sample_8bit.bmp` resources and repaired complete
  `sample_v3.bmp` and `sample_v5.bmp` resources.
- Complete 24-bit bottom-up and top-down BMPs with padded rows.
- 8-bit full and reduced palettes, and odd-width 4-bit BMPs in both orientations.
- Complete 32-bit BMPs with 56-byte bitfield and 124-byte headers.
- BAM V1 raw and RLE frames, retained RLE data, and an ordinary lookup table.
- BAM V2 and MOS V2 source rows with a 16-byte pitch for 12 bytes of pixels,
  copied into a destination subrectangle.
- Empty BAM V1/V2 glyphs with zero width, zero height, or both; concrete SDL
  surfaces retain each glyph's original bounds and V1 palette.
- MOS V1 64x64 and 65x65 images, including partial right and bottom tiles.

The old `sample_v3.bmp` and `sample_v5.bmp` declared a 10x10 32-bit raster but
retained only the 320 raster bytes from the 24-bit sample. Both fixtures now have
complete 400-byte BGRA rasters converted from the valid 24-bit sample and updated
file/raster sizes, so the existing BMPImporter parameterized smoke suite retains
its successful-open contract. The strict full-raster decoder check remains.

Empty glyphs do not read stream pixels. A checked zero-area frame keeps its
original metrics in the concrete sprite factory with a one-byte owned backing
allocation. Font loading disables encoded RLE (`allowCompression=false`), so its
V1 glyphs are decoded paletted bytes and V2 glyphs use ARGB32. A failed factory
result is rejected before BAMFontManager dereferences the animation factory.

The source changes use the shared `CheckedImageByteCount` helper from the BIF,
TIS and PNG follow-up. Its row limit reserves three bytes for SDL alignment before
the pitch is stored in Sprite2D's uint16 field. File wire widths are unchanged.
Animation frame/cycle counts and FLT lengths remain strictly below the factory's
reserved index value 65535; cycle endpoints are widened before addition.

The fixtures do not provide malformed-input, baseline, whole-plugin, complete
engine, decompression-wrapper, game rendering or owner acceptance evidence.
