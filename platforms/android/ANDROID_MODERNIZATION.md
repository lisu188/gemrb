# Android Modernization Design

Status: Draft
Branch: `android-modernization`

## Problem

GemRB still contains an Android port, but the packaging layer is obsolete. The current Android README is based on Ant, `ndk-build`, very old SDK/NDK assumptions, and legacy external-storage behavior. Current GemRB CMake also creates the Android entry target with `add_executable`, while SDL2's Android Gradle/CMake integration expects the target containing `main()` to be a shared library loaded by `SDLActivity`.

The goal is to restore Android as a first-class, reproducible build target without maintaining a separate fork of the GemRB engine.

## Goals

1. Build current GemRB master into an installable APK with the Android Gradle plugin and CMake.
2. Keep Android-specific code thin and upstreamable.
3. Use SDL2's supported Android lifecycle/input/JNI layer instead of maintaining a custom activity implementation where possible.
4. Embed Python 3 using the official Android CPython distribution.
5. Package GemRB runtime data (`GUIScripts`, `override`, `unhardcoded`, shaders where required) reproducibly.
6. Support modern Android storage rules without broad filesystem permissions.
7. Start with `arm64-v8a`; add `x86_64` for emulator/CI after the first working build.
8. Add CI that proves native compilation and APK assembly on every Android change.

## Non-goals for the first milestone

- Google Play publishing.
- Supporting every ABI immediately.
- Reworking GemRB UI for touch-first interaction.
- Replacing SDL2 with SDL3.
- Enabling every optional media dependency before the engine boots.
- Directly running games from arbitrary shared-storage paths.

## Toolchain baseline

Initial baseline:

- Android Gradle Plugin: current stable version used by the project bootstrap.
- Android SDK: current stable compile SDK.
- Android NDK: r29 (`29.0.14206865`).
- CMake: GemRB already requires CMake 3.25 or newer.
- C++ runtime: libc++.
- ABI: `arm64-v8a` first, `x86_64` second.
- Minimum SDK: API 28 for the first prototype. This is intentionally conservative and can be lowered after dependency validation.

Versions should be pinned in the Gradle project and updated deliberately rather than resolved implicitly.

## High-level architecture

```text
Android APK
|
+-- Kotlin/Java Android shell
|   +-- GemRBActivity : SDLActivity
|   +-- game import / directory picker
|   +-- first-run asset extraction
|   +-- lifecycle integration delegated to SDL2
|
+-- native libraries
|   +-- libSDL2.so
|   +-- libmain.so
|   |   +-- GemRB entry point
|   |   +-- gemrb_core
|   |   +-- statically linked GemRB plugins
|   +-- libpython3.14.so
|   +-- optional native dependencies
|
+-- APK assets
    +-- gemrb/GUIScripts
    +-- gemrb/override
    +-- gemrb/unhardcoded
    +-- python standard library
    +-- initial GemRB configuration/template
```

## Build-system design

### Gradle owns APK packaging

The Android application should live under `platforms/android` and use a conventional Gradle project. Gradle is responsible for:

- SDK/NDK selection;
- APK assembly;
- ABI selection;
- Java/Kotlin compilation;
- manifest/resources;
- native CMake invocation;
- packaging native libraries and assets.

The old Ant/`ndk-build` pipeline should remain only until the new pipeline boots, then be removed in a separate cleanup commit.

### CMake owns native GemRB compilation

The existing top-level GemRB CMake project remains authoritative for engine compilation. Android should not maintain a giant manually curated source list.

The key Android-specific change is to build the GemRB entry target as a shared library rather than an executable:

```cmake
ELSEIF(ANDROID)
    ADD_LIBRARY(gemrb SHARED
        ${PLATFORM_DIR}/android/GemRB.cpp
        ${PLATFORM_DIR}/android/AndroidLogger.cpp
    )
    SET_TARGET_PROPERTIES(gemrb PROPERTIES OUTPUT_NAME main)
```

This follows SDL2's Android model: `SDLActivity` loads the native application library and SDL invokes the program entry point.

### Static GemRB plugins

Android should initially use:

```text
STATIC_LINK=ON
```

This avoids runtime plugin discovery/load-path problems inside an APK. GemRB already supports linking plugins into the application target.

Dynamic plugins can be reconsidered later only if they provide a concrete benefit.

## SDL strategy

Use SDL2's supported Android Gradle/CMake project model.

Preferred integration:

1. Vendor SDL2 as a pinned git submodule or use a pinned source archive.
2. Add SDL2 as a CMake subdirectory from the Android Gradle native build.
3. Subclass `SDLActivity` as `GemRBActivity` instead of editing SDL's Java sources.
4. Keep custom JNI calls isolated in a small Android bridge.

SDL2 remains the rendering/input/platform layer for milestone 1. SDL3 migration is independent work and should not block Android restoration.

## Python strategy

GemRB GUI logic requires Python. Android has no system Python, so Python must be embedded.

Use the official CPython Android embeddable distribution. The initial target is Python 3.14.x because official aarch64 and x86_64 Android packages are available.

Runtime model:

1. Package `libpython3.14.so` for each supported ABI.
2. Package the Python standard library with the app.
3. On first launch, install/extract Python runtime data into app-private storage if normal filesystem paths are required by CPython/GemRB.
4. Set Python home/search paths before GemRB initializes `GUIScript`.
5. Do not rely on `pip`, subprocesses, or an external Python installation.

A later optimization can avoid extracting modules that can be loaded directly from packaged resources.

## GemRB data strategy

The following engine resources must be available independently of the user's game install:

- `GUIScripts`
- `override`
- `unhardcoded`
- shaders when an OpenGL/GLES backend requires them
- a generated/default configuration template

Milestone 1 will package these under APK assets and extract them into app-private storage on first launch/version change.

The extraction process must be versioned so app updates refresh engine data without destroying user saves or imported games.

Suggested layout:

```text
files/
+-- runtime/<gemrb-version>/
|   +-- GUIScripts/
|   +-- override/
|   +-- unhardcoded/
|   +-- python/
+-- games/
+-- saves/
+-- cache/
```

## Game-data/storage design

Do not depend on unrestricted `/sdcard` access and do not request `MANAGE_EXTERNAL_STORAGE`.

Two-phase design:

### Development

Use app-specific external storage so ADB can copy test game installations into a predictable location.

### User-facing

Use Android's Storage Access Framework to let the user choose a game directory. The first implementation should import/copy the game into GemRB-managed app storage. This avoids forcing the C++ VFS layer to understand Android document-provider URIs.

A future optimization may add a document-provider-backed VFS instead of copying game data.

## Audio/media dependency sequence

Do not solve every dependency before proving the native application boots.

Bring-up order:

1. SDL2 video/input
2. Python + GUIScripts
3. GemRB demo/engine startup
4. zlib
5. FreeType
6. PNG
7. Vorbis
8. OpenAL Soft
9. movies/optional codecs
10. GLES backend if it materially improves rendering

For the first executable prototype, optional dependencies should be disabled where GemRB permits it.

## Android lifecycle

SDL2 should own the standard Android lifecycle bridge. GemRB-specific behavior should be limited to engine semantics:

- pause/resume audio;
- save/flush configuration when appropriate;
- survive surface destruction/recreation;
- handle activity restart without corrupting engine state;
- avoid assuming process lifetime equals activity lifetime.

These cases need explicit device/emulator tests because the old port predates modern Android process/lifecycle behavior.

## Configuration

The Android shell should generate a minimal configuration rather than requiring users to edit `GemRB.cfg` through ADB.

Configuration should be stored in app-private storage and generated from a versioned template. The Android shell owns platform paths; GemRB continues to own game/engine settings.

Initial Android-managed values include:

- `GamePath`
- `CachePath`
- `SavePath`
- engine data path
- Python runtime path

## CI design

Add an Android GitHub Actions job after the project skeleton exists.

CI stages:

1. install JDK/Android SDK/NDK/CMake;
2. assemble `arm64-v8a` debug APK;
3. retain APK as an artifact;
4. run host-side/static checks;
5. later add an x86_64 emulator smoke test that launches GemRB and checks logcat for a startup marker.

The first CI gate is APK assembly. Emulator execution should be a second milestone because it adds substantially more moving parts.

## Milestones

### M0 - Build-system skeleton

- [ ] Gradle project under `platforms/android`
- [ ] SDL2 integrated with CMake
- [ ] Android target becomes `libmain.so`
- [ ] `arm64-v8a` native compile succeeds
- [ ] empty/minimal SDL activity launches

### M1 - GemRB boots

- [ ] static GemRB plugins
- [ ] Python 3.14 embedded
- [ ] engine runtime assets installed
- [ ] GemRB reaches GUI script initialization
- [ ] logcat diagnostics usable

### M2 - Demo/game loading

- [ ] GemRB demo launches
- [ ] app-specific game directory works
- [ ] first Infinity Engine game reaches main menu
- [ ] saves/cache use Android-safe paths

### M3 - Feature completeness

- [ ] FreeType/PNG/Vorbis
- [ ] OpenAL Soft
- [ ] movies if practical
- [ ] lifecycle pause/resume/restart tested
- [ ] touch/keyboard behavior audited

### M4 - User-facing install flow

- [ ] Storage Access Framework directory picker
- [ ] game import UX
- [ ] configuration UI for discovered games
- [ ] upgrade-safe runtime data migration

### M5 - CI and upstreamability

- [ ] APK build in GitHub Actions
- [ ] x86_64 emulator smoke test
- [ ] remove obsolete Ant build
- [ ] split commits/PRs into upstream-reviewable units

## First implementation slice

The first code PR should do only enough to prove the architecture:

1. add the Gradle Android shell;
2. integrate pinned SDL2;
3. change GemRB's Android CMake target from executable to shared library;
4. build `libmain.so` for `arm64-v8a` with optional dependencies disabled;
5. launch and log from the Android entry point.

Python, asset extraction, and game importing should follow after this compiles. Keeping the first slice narrow will make failures attributable to the build/platform layer rather than runtime-data dependencies.

## Open decisions

1. SDL2 source integration: git submodule vs FetchContent vs vendored archive.
2. Whether Python runtime assets can stay compressed in the APK or require full extraction.
3. Lowest realistic `minSdk` after all dependencies compile; API 28 is the provisional baseline, not a permanent compatibility promise.
4. Whether OpenAL Soft should be built from source inside the Android project or supplied as a pinned prebuilt dependency.
5. Whether the final Android UI should be Kotlin or minimal Java. Kotlin is preferred for new Android-only UI code, but the shell should remain very small.
6. Whether game data should eventually be accessed through SAF directly rather than imported into app-managed storage.

## Design principles

- Keep platform code thin.
- Prefer upstream-supported Android mechanisms over custom JNI infrastructure.
- Pin toolchain/dependency versions for reproducibility.
- Get a minimal engine booting before restoring optional features.
- Avoid Android-wide filesystem permissions.
- Preserve GemRB's cross-platform CMake architecture rather than maintaining an Android-specific source manifest.
- Structure changes so they can be submitted upstream independently.
