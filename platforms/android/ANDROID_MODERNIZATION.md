# Android Modernization Design

Status: Draft
Branch: `android-modernization`

## Problem

GemRB still contains an Android port, but its packaging and dependency layer is obsolete. The old build uses Ant, `ndk-build`, legacy SDK/NDK assumptions, Python 2-era integration, obsolete ABIs, and broad external-storage paths. Current GemRB also creates the Android entry target as an executable, while SDL2 Android expects the target containing `main()` to be a shared library loaded by `SDLActivity`.

The goal is to restore Android as a first-class, reproducible build target while keeping Android-specific engine changes small and upstreamable.

## Goals

1. Build current GemRB into an installable APK with Gradle and CMake.
2. Keep GemRB's top-level CMake project authoritative for native compilation.
3. Use SDL2 lifecycle, input, window, and JNI infrastructure.
4. Embed supported CPython for Android.
5. Bundle a full iconv implementation for Infinity Engine legacy encodings.
6. Install GemRB/Python runtime data atomically before native startup.
7. Use scoped/app-specific Android storage without `MANAGE_EXTERNAL_STORAGE`.
8. Start with `arm64-v8a`; add `x86_64` later.
9. Require 16 KB page-size compatibility from M0.
10. Add CI that assembles and validates the Android package.

## Non-goals

- Play Store publishing in the first restoration phase.
- Supporting all Android ABIs immediately.
- Touch-first GemRB UI redesign.
- SDL3 migration.
- Restoring all optional codecs before the engine boots.
- Direct C++ VFS access to arbitrary SAF `content://` URIs in the first implementation.
- Restoring live in-memory game state after Android process death.

## Toolchain baseline

The implementation uses exact pins rather than floating versions.

- Android Gradle Plugin: `9.4.0`
- Gradle: `9.6.0`
- JDK: `17`
- compile SDK: API `36`
- target SDK: API `36`
- minimum SDK: API `28` initially
- Android NDK: r29 (`29.0.14206865`)
- CMake: exact installed Android SDK CMake version satisfying GemRB `>= 3.25`
- C++ runtime: libc++
- SDL2: `2.32.10`
- Python: `3.14.7` official Android `aarch64` distribution
- GNU libiconv: `1.19`
- initial ABI: `arm64-v8a`

API 36 is used because the stable Android SDK channel used by CI exposes it. API 37 can be reconsidered when it is available through the stable toolchain used by this project.

## High-level architecture

```text
Android application
|
+-- BootstrapActivity
|   +-- verify/install versioned GemRB runtime
|   +-- verify/install Python standard library
|   +-- generate/update Android-owned GemRB.cfg
|   +-- select/import game
|   +-- validate paths and free storage
|   +-- launch GemRBActivity only after bootstrap succeeds
|
+-- GemRBActivity : SDLActivity
|   +-- deliberately thin
|   +-- SDL lifecycle/input/window handling
|   +-- passes explicit native command-line arguments
|
+-- native libraries
|   +-- libSDL2.so
|   +-- libmain.so
|   |   +-- GemRB Android entry point
|   |   +-- gemrb_core
|   |   +-- statically linked GemRB plugins
|   |   +-- zlib
|   |   +-- GNU libiconv
|   +-- libpython3.14.so
|   +-- required CPython companion native libraries
|
+-- APK assets
    +-- GemRB runtime data
    +-- Python standard library
    +-- configuration template
    +-- version manifests
```

Bootstrap/storage work must complete before `GemRBActivity` starts. Long extraction/import work does not belong in `SDLActivity`.

## Build-system design

### Gradle

Gradle owns:

- SDK/NDK/JDK/CMake selection;
- Android manifest/resources;
- Java compilation;
- ABI selection;
- CMake invocation;
- native-library/assets packaging;
- APK assembly.

The obsolete Ant/`ndk-build` files remain until the new pipeline reaches a useful runtime milestone, then are removed separately.

### GemRB CMake

Android uses the existing GemRB native source graph. It must not maintain a second Android-only source manifest.

Android target model:

```cmake
ELSEIF(ANDROID)
    ADD_LIBRARY(gemrb SHARED
        ${PLATFORM_DIR}/android/GemRB.cpp
        ${PLATFORM_DIR}/android/AndroidLogger.cpp
    )
    SET_TARGET_PROPERTIES(gemrb PROPERTIES OUTPUT_NAME main)
ENDIF()
```

The resulting application library is `libmain.so`.

### Static GemRB plugins

Android initially uses `STATIC_LINK=ON`. Existing static-plugin registration and whole-archive linkage must remain semantically equivalent to desktop static builds. Dynamic APK plugin discovery is not part of initial restoration.

## SDL2 integration

SDL2 `2.32.10` is pinned and supplied reproducibly. GemRB's current `find_package(SDL2)` abstraction must be satisfied by the Android build without requiring host SDL installation.

`libmain.so` links SDL2 Android main glue at the final application target. `SDLVideo` links normal SDL2 and must not own `SDL2main`.

`GemRBActivity` subclasses `SDLActivity`. Custom JNI is added only where SDL/Android framework APIs cannot provide the needed operation.

## Mandatory native dependencies in M0

### Python

Python cannot be deferred from the first native build. GemRB runs Python configuration unconditionally, always builds `GUIScript`, and links Python development libraries.

M0 therefore provides target-ABI:

- Python headers;
- `libpython3.14.so`;
- required native companions;
- CMake discovery inputs/imported targets.

M1 adds the Python standard library installation and runtime search-path setup.

### zlib

Zlib is mandatory at configure time. Prefer Android/NDK zlib if validated; otherwise use a pinned source build.

### GNU libiconv

Do not rely on Bionic's restricted iconv encoding set. Bundle pinned GNU libiconv and validate conversions required by localized Infinity Engine games, including representative Windows and East Asian code pages.

## Runtime bootstrap

`BootstrapActivity` owns installation/migration and is the launcher activity.

Required flow:

1. compare installed runtime metadata with APK version metadata;
2. install GemRB/Python assets into a temporary versioned directory;
3. validate required files;
4. atomically promote the new runtime;
5. generate/update Android-managed configuration;
6. validate the selected game when applicable;
7. launch `GemRBActivity` only after the runtime/configuration is valid.

Never delete the last known-good runtime before its replacement is complete.

## Configuration loading contract

The Android bootstrap must not merely write `GemRB.cfg`; it must explicitly tell GemRB to load that file.

Canonical internal location:

```text
<filesDir>/config/GemRB.cfg
```

`GemRBActivity` overrides SDL2's `getArguments()` and supplies the configuration argument to native `SDL_main`:

```java
@Override
protected String[] getArguments() {
    return new String[] { "-c", configPath };
}
```

`configPath` is the absolute path to the validated Android-managed configuration produced by `BootstrapActivity`. The activity receives or derives this path from app-private state; it must never accept an arbitrary external path from an untrusted intent.

This is the preferred contract because pinned SDL2 already exposes `getArguments()` specifically for native application arguments. No JNI bridge is required solely for configuration selection.

Acceptance requirements for M1:

- `GemRB.cfg` exists before `GemRBActivity` starts;
- native argv contains `-c <filesDir>/config/GemRB.cfg`;
- GemRB logs the selected configuration path;
- generated `GamePath`, `SavePath`, `CachePath`, and runtime paths are observed by the engine;
- startup fails clearly rather than silently falling back to another config when the managed config is missing or invalid.

## Runtime data layout

Engine-owned runtime data stays in app-private internal storage:

```text
filesDir/
+-- runtime/
|   +-- <runtime-version>/
|       +-- gemrb/
|       |   +-- GUIScripts/
|       |   +-- override/
|       |   +-- unhardcoded/
|       +-- python/
+-- config/
|   +-- GemRB.cfg
+-- metadata/
```

Use metadata to identify the active runtime; do not require a filesystem symlink.

## Game data, saves, and cache

Do not request `MANAGE_EXTERNAL_STORAGE` and do not use unrestricted `/sdcard/...` paths.

Target ownership:

```text
internal filesDir
+-- runtime/
+-- config/
+-- metadata/

internal cacheDir
+-- gemrb/

externalFilesDir
+-- games/
|   +-- <game-id>/
+-- saves/
    +-- <game-id>/
```

### Game identity

Every imported installation receives a stable application-managed `game-id`. It must remain stable across launches and configuration regeneration for that imported installation. The ID is metadata, not a user-editable path fragment.

### Game import

Use `ACTION_OPEN_DOCUMENT_TREE`/SAF to choose a source directory, then copy the selected installation into managed app-specific storage:

```text
externalFilesDir/games/<game-id>/
```

The importer must preflight source size/free space, expose progress/cancellation, copy to a temporary destination, validate essential files, and atomically promote only a valid import.

### Per-game save isolation

A shared `SavePath=externalFilesDir/saves` is forbidden because GemRB appends the game-provided save directory beneath `SavePath`; multiple games could otherwise enumerate or overwrite identically named save slots.

For a selected game, configuration must use:

```text
GamePath = externalFilesDir/games/<game-id>/
SavePath = externalFilesDir/saves/<game-id>/
```

GemRB may then append its game-specific `SaveDir` beneath that isolated root.

Acceptance requirements:

- two imported games never share an effective save root;
- quicksave/autosave names from one game cannot overwrite another game's saves;
- switching selected games regenerates/updates `SavePath` to the selected `game-id`;
- tests cover at least two imported game IDs with overlapping slot directory names.

### Save durability

App-specific external storage is deleted on uninstall. Before distribution quality is claimed, provide explicit save export/import or another user-controlled backup mechanism.

## Android platform path contract

The existing Android entry point currently maps `GEMRB_DATA` to external storage; that must be removed.

Runtime contract:

```text
GEMRB_DATA     -> internal versioned GemRB runtime
Python runtime -> internal versioned Python runtime
GemRB.cfg      -> <filesDir>/config/GemRB.cfg, passed explicitly with -c
GamePath       -> externalFilesDir/games/<game-id>/
SavePath       -> externalFilesDir/saves/<game-id>/
CachePath      -> internal cacheDir/gemrb/
```

The Android shell owns platform paths. GemRB continues to own game/engine semantics.

## Python runtime strategy

M0 supplies headers/native libraries. M1 installs the Python standard library into app-private storage and configures Python home/search paths before `GUIScript` initializes the interpreter.

`GUIScript` remains the owner of `Py_Initialize()`. Do not create a second Java/JNI Python initialization path.

No system Python, pip, subprocess, or external shell dependency is permitted.

## Feature dependency sequence

### M0 native bring-up

1. SDL2 + SDL2main
2. Python development/native libraries
3. zlib
4. GNU libiconv
5. static GemRB core/plugins
6. `libmain.so` load and deterministic Android startup marker
7. arm64 APK assembly
8. 16 KB validation

### M1 runtime

9. `BootstrapActivity`
10. versioned GemRB/Python runtime installation
11. explicit `-c <managed-config>` argument contract
12. Python search paths / `GUIScript` initialization
13. internal runtime and cache paths

### M2 demo

14. FreeType
15. PNG
16. Ogg/Vorbis
17. GemRB demo

### M3 games

18. SAF picker/importer
19. stable imported `game-id`
20. per-game `GamePath` and `SavePath`
21. first supported game main menu
22. save/load isolation tests

### M4 platform completeness

23. OpenAL Soft
24. lifecycle/surface handling
25. Android window resizing/orientation
26. keyboard/IME/touch/controller audit
27. optional movies/codecs

### M5 release/upstreaming

28. x86_64
29. emulator smoke tests
30. APK/AAB artifacts
31. save export/import
32. licenses/notices
33. obsolete Ant/ndk-build cleanup
34. upstream-ready commit split

## Lifecycle contract

SDL2 owns standard Android lifecycle/input/window bridging. Required GemRB behavior:

- background/foreground transitions do not corrupt state;
- audio pauses/resumes when audio is restored;
- surface destruction/recreation is tolerated;
- window-size changes do not leave rendering unusable;
- activity recreation resumes safely where supported or restarts cleanly;
- process death results in a clean application restart, not live-memory restoration.

Normal GemRB saves remain the game-state persistence mechanism.

## 16 KB page-size compatibility

16 KB compatibility is an M0 gate. CI validates every packaged shared library, including:

- `libmain.so`;
- `libSDL2.so`;
- `libpython3.14.so`;
- Python companion `.so` files;
- optional later native libraries.

Validation must cover ELF load alignment and APK packaging alignment. Any incompatible prebuilt fails the build.

## CI

Initial Android CI must:

1. install pinned JDK/SDK/NDK/CMake;
2. checksum/fetch pinned native dependencies;
3. build `arm64-v8a` debug APK;
4. verify required packaged libraries;
5. run 16 KB validation;
6. upload the APK artifact.

Later CI adds x86_64 emulator smoke tests and progressive log markers.

## Open decisions

1. Final minimum SDK after dependency/runtime validation.
2. Future move from copied SAF imports to direct VFS-backed SAF access.
3. OpenAL source/build strategy.
4. Final application ID compatibility policy with the historical Android package.
5. Release packaging/AAB policy.

## Design principles

- Keep Android-specific engine changes small.
- Make mandatory dependencies explicit rather than hiding them behind bootstrap shortcuts.
- Use exact versions/checksums.
- Keep extraction/import separate from SDL lifecycle hosting.
- Pass managed configuration explicitly; never depend on accidental working-directory lookup.
- Isolate save data per imported game identity.
- Avoid broad storage permissions.
- Preserve desktop CMake behavior.
- Treat all prebuilts as ABI/alignment inputs that CI must validate.
