# Ordinary image compatibility fixtures

These checks extract the selected production functions and run small, ordinary
valid inputs using bounded dependency adapters. They do not require an engine,
renderer or imported game assets.

```sh
python3 gemrb/tests/security/test_valid_png_import.py --output png-result.json
python3 gemrb/tests/security/test_valid_image_streams.py --output image-stream-result.json
```

The PNG check needs the libpng development package. It covers grayscale,
indexed, RGB, grayscale-alpha and RGBA PNGs, low and high supported bit depths,
and explicit transparency. It verifies the production import transforms and
decoded byte layout with libpng. The TIS/BIF check verifies a valid tile copy
from padded source rows and a valid archive tile span. Both compile their host
harness with AddressSanitizer and UndefinedBehaviorSanitizer.

Receipts identify the production source hashes. Stream, sprite and resource
adapters keep the check bounded and are not complete engine implementations.
No malformed-input or baseline cases are run by these two scripts. Passing
these checks is not full plugin-build, renderer, gameplay, or content acceptance.
