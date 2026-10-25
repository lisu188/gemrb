# Ordinary image compatibility fixtures

These checks extract the selected production functions and run small, ordinary
valid inputs using bounded dependency adapters. They do not require an engine,
renderer or imported game assets.

```sh
python3 gemrb/tests/security/test_valid_png_import.py --output png-result.json
python3 gemrb/tests/security/test_valid_image_streams.py \
  --config-directory build --output image-stream-result.json
```

The PNG check needs the libpng development package. It covers grayscale,
indexed, RGB, grayscale-alpha and RGBA PNGs, low and high supported bit depths,
and explicit transparency. It verifies the production import transforms and
decoded byte layout with libpng. The TIS/BIF check also needs SDL2 development
files and a CMake build directory containing GemRB's generated `config.h`.
It includes the actual `Sprite2D`, `PixelFormat` and geometry headers, extracts
the used production constructors/accessors, and creates real SDL surfaces.
The TIS crop also checks the source image dimensions before requesting a sprite;
the fixture's image adapter reports the actual source sprite size.
It verifies a valid tile copy from padded source rows, a valid archive tile
span, and SDL's row-alignment representation. SDL reports a 260-byte pitch for
the 64-pixel ARGB32 source row with four padding bytes. An ordinary one-row
RGB24 surface of width 21845 has pitch 65536 after alignment, exceeding GemRB's
uint16 pitch representation; width 21844 yields pitch 65532 and fits. The size
helper reserves three bytes for this alignment, including later sprite copies.
Both checks compile their host harness with AddressSanitizer and
UndefinedBehaviorSanitizer. For an isolated source overlay, `--header-root` can
identify the complete checkout supplying the actual project headers.

Receipts identify the production source hashes; the TIS/BIF receipt also records
the actual project API hashes. Stream, resource, factory and conversion adapters
keep the checks bounded and are not complete engine implementations. The sprite
adapter uses the real class declaration and SDL's measured byte pitch.
No malformed-input or baseline cases are run by these two scripts. Passing
these checks is not full plugin-build, renderer, gameplay, or content acceptance.
