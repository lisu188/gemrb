# Android Modernization Design

Status: Draft
Branch: `android-modernization`

## Problem

GemRB still contains an Android port, but its packaging and dependency layer is obsolete. The existing Android build uses Ant, `ndk-build`, old SDK/NDK assumptions, Python 2-era integration, legacy ABIs, and unrestricted external-storage paths. Current GemRB CMake also creates the Android entry target with `add_executable`, while SDL2's Android model expects the target containing `main()` to be a shared library loaded by `SDLActivity`.

The goal is to restore Android as a first-class, reproducible build target while preserving GemRB's cross-platform architecture and keeping Android-specific engine changes small enough to upstream.

## Goals

1. Build current GemRB master into an installable APK with Gradle and CMake.
2. Keep the top-level GemRB CMake project authoritative for native compilation.
3. Use SDL2's supported Android activity, lifecycle, input, and JNI infrastructure.
4. Embed a supported Python 3 runtime using the official CPython Android distribution.
5. provide a full iconv implementation suitable for Infinity Engine legacy encodings.
6. Package GemRB runtime data reproducibly and install it atomically before native startup.
7. Support modern Android storage without `MANAGE_EXTERNAL_STORAGE`.
8. Start with `arm64-v8a`; add `x86_64` for emulator/CI after the first working build.
9. Make 16 KB page-size compatibility a build requirement from the beginning.
10. Add CI that proves APK assembly and native-library validity on every Android change.

## Non-goals for initial restoration

- Google Play publishing.
- Supporting every Android ABI immediately.
- Reworking the GemRB UI into a touch-first interface.
- Migrating SDL2 to SDL3.
- Restoring every optional media codec before the engine and one game work.
- Direct VFS access to arbitrary Storage Access Framework document-provider URIs.
- Restoring a live game session after Android kills the application process.

## Toolchain baseline

The initial toolchain is pinned rather than described as "latest" so builds remain reproducible.

- Android Gradle Plugin: `9.4.0`
- Gradle: `9.6.0`
- JDK: `17`
- compile SDK: API `37`
- target SDK: API `37`
- minimum SDK: API `28` initially
- Android NDK: r29 (`29.0.14206865`)
- CMake: pin an Android SDK CMake version satisfying GemRB's `>= 3.25` requirement
- C++ runtime: libc++
- Python: `3.14.6` official Android embeddable distribution
- ABI: `arm64-v8a` first, `x86_64` second

API 28 is a conservative compatibility baseline, not a dependency on Android's libc `iconv`. The minimum SDK can be lowered later only after all native dependencies and runtime behavior are validated.

SDL2, libiconv, and all additional source dependencies must also be pinned to exact versions or commits.

## High-level architecture

```text
Android application
|
+-- BootstrapActivity
|   +-- verify/install versioned GemRB runtime
|   +-- verify/install Python standard library
|   +-- generate/update Android-owned configuration
|   +-- game selection/import UI
|   +-- validate required files and free storage
|   +-- start GemRBActivity only after bootstrap succeeds
|
+-- GemRBActivity : SDLActivity
|   +-- minimal Android-specific behavior
|   +-- lifecycle/input/window handling delegated to SDL2
|   +-- loads native application library
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
|   +-- CPython companion native libraries where required
|   +-- optional feature libraries added in later milestones
|
+-- APK assets
    +-- gemrb/GUIScripts
    +-- gemrb/override
    +-- gemrb/unhardcoded
    +-- shaders when required
    +-- Python standard library
    +-- version metadata
    +-- GemRB configuration template
```

The Android shell has two distinct responsibilities: bootstrap/storage UX and native engine hosting. Asset installation or game importing must not occur concurrently with GemRB startup.

## Build-system design

### Gradle owns Android packaging

The modern Android application remains under `platforms/android`. Gradle owns:

- SDK, NDK, JDK, and CMake selection;
- APK assembly;
- ABI selection;
- manifest and Android resources;
- Kotlin/Java compilation;
- native CMake invocation;
- packaging native libraries and assets;
- debug/release Android build variants.

The old Ant/`ndk-build` implementation should remain untouched until the modern APK reaches the first useful runtime milestone. It should then be removed in a separate cleanup change.

### GemRB CMake remains authoritative

Android must not maintain a second manually curated list of GemRB source files. Gradle's external native build should enter the existing top-level GemRB CMake project.

The Android GemRB entry target changes from an executable to the SDL Android application shared library:

```cmake
ELSEIF(ANDROID)
    ADD_LIBRARY(gemrb SHARED
        ${PLATFORM_DIR}/android/GemRB.cpp
        ${PLATFORM_DIR}/android/AndroidLogger.cpp
    )
    SET_TARGET_PROPERTIES(gemrb PROPERTIES OUTPUT_NAME main)
```

The resulting `libmain.so` is loaded by SDL's Android activity infrastructure.

### Static GemRB plugins

Android initially uses:

```text
STATIC_LINK=ON
```

GemRB's plugin CMake machinery already converts plugins into static libraries in this mode and links the complete plugin set into the application target. This avoids APK runtime plugin discovery and `dlopen` path problems.

Dynamic GemRB plugins are not part of the restoration plan unless a concrete future requirement justifies them.

## SDL2 strategy

SDL2 remains the platform/rendering/input layer during restoration. SDL3 migration is independent work.

### Source integration

Use an exact pinned SDL2 release/commit. Preferred order:

1. pinned git submodule;
2. pinned source archive with checksum;
3. CMake `FetchContent` only if reproducibility and offline CI remain acceptable.

A floating branch is not acceptable.

### CMake integration

Simply adding SDL2 with `add_subdirectory()` is not enough because current GemRB's `CONFIGURE_SDL()` expects `find_package(SDL2)` variables. Android needs a small explicit integration path so an existing SDL2 CMake target can satisfy GemRB's abstraction without performing a second package search.

Conceptually:

```cmake
IF(ANDROID AND TARGET SDL2::SDL2)
    SET(SDL2_FOUND TRUE)
    SET(SDL_FOUND TRUE)
    SET(SDL_INCLUDE_DIR ...)
    SET(SDL_LIBRARY SDL2::SDL2)
ELSE()
    FIND_PACKAGE(SDL2 REQUIRED)
ENDIF()
```

The exact implementation should reuse upstream SDL target names available in the pinned SDL release rather than hardcoding paths.

### SDL2main

The Android application target containing `main()` must link SDL2's Android main glue explicitly. `SDLVideo` must continue to link the normal SDL library without accidentally owning `SDL2main`.

Conceptually:

```cmake
TARGET_LINK_LIBRARIES(gemrb
    SDL2::SDL2
    SDL2::SDL2main
)
```

The actual target names must be verified against the pinned SDL2 release during M0.

### Activity layer

`GemRBActivity` subclasses `SDLActivity` and remains deliberately thin. It must not contain large import, migration, or extraction workflows.

Any custom JNI bridge should be introduced only for functionality SDL2 and Android configuration cannot already provide.

## Required native dependencies in M0

A native compile of current GemRB cannot defer all non-SDL dependencies.

### Python development library

GemRB calls `CONFIGURE_PYTHON()` unconditionally and requires Python development headers/libraries at CMake configure time. Therefore Python is an M0 link-time dependency even though interpreter startup and the Python standard library belong to M1.

M0 provides CMake with the official CPython Android package's:

- headers;
- `libpython3.14.so`;
- required companion native libraries;
- explicit `Python_INCLUDE_DIRS`/`Python_LIBRARIES` or an Android-specific imported target.

Do not make Python optional merely to obtain an earlier Android build.

### zlib

GemRB requires zlib during CMake configuration, so zlib is also an M0 dependency.

Prefer the NDK/platform zlib when its API and linkage satisfy GemRB. Otherwise use a pinned source build. Avoid unnecessary private copies.

### iconv

Do not use Android Bionic `iconv` as GemRB's full iconv implementation.

Bionic exposes `iconv` from API 28 but supports only a narrow encoding set centered around UTF/ASCII encodings. GemRB must support legacy Infinity Engine text encodings such as Windows code pages and East Asian encodings. A build that merely links Bionic `iconv` can therefore succeed while failing at runtime on real game data.

Android will bundle a pinned GNU libiconv build with the encodings GemRB requires. Prefer static linkage into `libmain.so`/the relevant static libraries unless licensing or technical validation indicates another packaging model is preferable.

## Python runtime strategy

Use the official CPython Android embeddable distribution, initially Python `3.14.6` for `aarch64`; add the matching `x86_64` package when emulator support is introduced.

Separate build-time and runtime responsibilities:

### M0: build-time

- Python headers are available to GemRB CMake.
- `libpython3.14.so` and required native companion libraries are packaged correctly.
- GemRB and `GUIScript` link successfully.

### M1: runtime

- Package the Python standard library in APK assets.
- Install/extract it atomically to app-private internal storage before `GemRBActivity` starts.
- Configure Python home/module search paths before `GUIScript` initializes the interpreter.
- Verify imports required by GemRB's GUI scripts.
- Do not rely on `pip`, subprocesses, shell tools, or a system Python installation.

A future optimization may load suitable resources without full extraction, but initial restoration should use normal filesystem paths for predictability.

## Runtime bootstrap design

### BootstrapActivity

`BootstrapActivity` is the Android launcher activity. It performs all prerequisites before native GemRB starts.

Responsibilities:

1. compare installed runtime metadata with APK runtime version;
2. install/update GemRB runtime assets into a temporary versioned directory;
3. install/update Python runtime assets into the same versioned runtime root;
4. fsync/validate required sentinel files;
5. atomically promote the temporary runtime directory;
6. generate/update Android-managed `GemRB.cfg` values;
7. validate a selected/imported game when applicable;
8. start `GemRBActivity` only when the runtime is internally consistent.

An interrupted installation must leave either the previous valid runtime or no active runtime, never a partially updated active tree.

### GemRBActivity

`GemRBActivity` hosts SDL/native GemRB. It should contain only the Android glue necessary to start and stop the native application and expose narrowly scoped platform functions not already available through SDL2.

## GemRB runtime data

The following files belong to the engine runtime, not to a game installation:

- `GUIScripts`;
- `override`;
- `unhardcoded`;
- shaders when an OpenGL/GLES backend requires them;
- generated/default configuration templates;
- Python standard library.

Keep runtime data in app-private internal storage because it is relatively small, version-controlled by the application, and should not be modified externally.

Suggested layout:

```text
/data/user/0/org.gemrb.gemrb/files/
+-- runtime/
|   +-- current -> <runtime-version> or equivalent metadata
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

Do not rely on an actual filesystem symlink for `current` unless Android/filesystem behavior is validated; a metadata pointer is sufficient.

## Game data, saves, and cache

Do not request `MANAGE_EXTERNAL_STORAGE` and do not use unrestricted `/sdcard/...` paths.

Large game installations should not be copied into internal `filesDir` by default.

Suggested ownership:

```text
internal filesDir
+-- runtime/
+-- config/
+-- metadata/

internal cacheDir
+-- gemrb/

externalFilesDir
+-- games/
+-- saves/
```

### Development

Use `externalFilesDir/games` so ADB can place test installations at deterministic app-specific paths without storage-wide permissions.

### User-facing import

Use Android's Storage Access Framework to select a source game directory. Initial restoration imports/copies the selected installation into `externalFilesDir/games/<game-id>` rather than teaching GemRB's C++ VFS to consume document-provider URIs.

The importer must:

- calculate approximate source size before copying;
- verify available destination space;
- expose progress and cancellation;
- copy into a temporary destination;
- validate essential game files;
- atomically rename/promote only after successful validation;
- clean stale temporary imports.

A later VFS-backed SAF implementation may eliminate the copy if the complexity and performance trade-off are worthwhile.

### Save durability

App-specific storage is removed when the app is uninstalled. Before distribution quality is claimed, provide save export/import or another explicit user-controlled backup path.

## Android platform paths

The existing Android entry point sets `GEMRB_DATA` from `SDL_AndroidGetExternalStoragePath()`. That conflicts with the new runtime layout and must be removed.

Prefer SDL2's Android path functions where they accurately represent the desired storage location, particularly `SDL_AndroidGetInternalStoragePath()` and `SDL_AndroidGetExternalStoragePath()`. Use a small Android bridge only for paths or operations SDL cannot provide.

The runtime contract should be:

```text
GEMRB_DATA     -> internal versioned GemRB runtime
Python runtime -> internal versioned Python runtime
GemRB.cfg      -> internal config directory
GamePath       -> app-specific external game directory
SavePath       -> app-specific external save directory
CachePath      -> internal cache directory
```

The bootstrap layer owns platform paths. GemRB continues to own game and engine semantics.

## Feature dependency sequence

The build/runtime sequence must reflect GemRB's real required dependencies.

### Native application bring-up

1. SDL2 + SDL2main
2. Python development library
3. zlib
4. GNU libiconv
5. static GemRB core/plugins
6. `libmain.so` load and Android log output

### Runtime bring-up

7. versioned GemRB asset installation
8. Python standard library installation
9. Python/GUIScript initialization
10. minimal GemRB startup path

### Demo dependencies

The GemRB demo requires FreeType, PNG, and Vorbis in current GemRB configuration. Therefore these must be restored before "demo boots" is an acceptance criterion:

11. FreeType
12. PNG
13. Vorbis
14. GemRB demo

### Later feature dependencies

15. OpenAL Soft
16. movies/optional codecs
17. GLES backend only if it provides measurable value over the initial SDL2 renderer

Optional dependencies should be disabled during earlier milestones only where GemRB actually permits them to be absent.

## Android lifecycle contract

SDL2 owns the standard activity/window/input lifecycle bridge. GemRB-specific requirements are deliberately bounded.

Required:

- background/foreground transitions do not corrupt state;
- pause/resume audio once audio is restored;
- surface destruction/recreation is handled correctly;
- supported window-size changes do not leave rendering unusable;
- activity recreation either resumes safely where SDL supports it or restarts cleanly;
- configuration and logs are flushed where appropriate.

Process death:

- no requirement exists to restore an in-memory live game session after Android kills the process;
- the application must restart cleanly into a valid runtime/configuration state;
- normal GemRB save files remain the persistence mechanism for game state.

## Configuration

Users should not need ADB to edit `GemRB.cfg`.

`BootstrapActivity`/`ConfigManager` generates a versioned configuration from a template and owns Android-specific path values. User/game settings should survive runtime upgrades where compatible.

Android-managed values initially include:

- engine runtime/data path;
- Python runtime path where needed;
- `GamePath`;
- `CachePath`;
- `SavePath`.

Configuration migration must preserve unknown GemRB options rather than blindly regenerating the entire file after every app update.

## 16 KB page-size compatibility

16 KB page-size support is an M0 build requirement, not a later optimization.

NDK-built native code should use the modern linker defaults supplied by the pinned NDK, but all packaged native libraries must be validated, including:

- `libmain.so`;
- `libSDL2.so`;
- `libpython3.14.so`;
- CPython companion `.so` libraries;
- any prebuilt third-party dependency.

CI should inspect ELF segment alignment and APK packaging so a dependency update cannot silently reintroduce a 4 KB-only native library.

If an official prebuilt dependency fails the requirement, replace it with a compatible build or source-build it rather than disabling the check.

## CI design

Introduce CI as soon as M0 exists.

### M0 CI gate

1. install/pin JDK 17, Android SDK 37, NDK r29, and the selected CMake version;
2. verify dependency versions/checksums;
3. assemble the `arm64-v8a` debug APK;
4. inspect packaged native libraries;
5. verify 16 KB-compatible ELF alignment;
6. retain the APK as a workflow artifact.

### Later CI

- add `x86_64` build;
- boot an Android emulator;
- install the APK;
- launch through `BootstrapActivity`/`GemRBActivity`;
- assert a stable GemRB startup marker from logcat;
- eventually launch the packaged demo as a smoke test.

Emulator execution should not block the first M0 build-system change because it introduces significantly more failure modes than compilation and packaging.

## Milestones

### M0 - Native APK builds

- [ ] conventional Gradle project under `platforms/android`
- [ ] exact SDL2 version pinned and integrated
- [ ] Android-aware SDL CMake integration without duplicate `find_package` assumptions
- [ ] Android target changed from executable to `libmain.so`
- [ ] `SDL2` and `SDL2main` linked correctly
- [ ] `STATIC_LINK=ON` works for Android GemRB plugins
- [ ] official Python 3.14.6 Android headers/native libraries wired into CMake
- [ ] zlib resolved
- [ ] GNU libiconv built and linked
- [ ] `arm64-v8a` APK assembles
- [ ] `libmain.so` loads and emits a known Android log marker
- [ ] packaged native libraries pass 16 KB page-size validation
- [ ] CI builds and retains the APK

### M1 - GemRB runtime boots

- [ ] `BootstrapActivity` created
- [ ] versioned/atomic runtime installer implemented
- [ ] GemRB `GUIScripts`, `override`, and `unhardcoded` installed internally
- [ ] Python standard library installed internally
- [ ] Android-managed configuration generated
- [ ] old external-storage `GEMRB_DATA` assumption removed
- [ ] Python interpreter initializes
- [ ] `GUIScript` loads required Python modules
- [ ] GemRB reaches the first stable GUI-script startup point
- [ ] logcat diagnostics are useful for bootstrap and native failures

### M2 - Demo boots

- [ ] FreeType restored
- [ ] PNG restored
- [ ] Vorbis restored
- [ ] GemRB demo packaged/selected appropriately for Android testing
- [ ] demo reaches a stable interactive screen

### M3 - Real game loading

- [ ] development game directory under `externalFilesDir/games`
- [ ] game detection/validation implemented
- [ ] first Infinity Engine game reaches main menu
- [ ] `CachePath` uses Android internal cache
- [ ] saves use Android-safe app-specific external storage
- [ ] save/load tested on device

### M4 - User-facing import and platform behavior

- [ ] Storage Access Framework directory picker
- [ ] capacity-aware atomic game importer
- [ ] import progress/cancel/error recovery
- [ ] configuration UI for imported/discovered games
- [ ] OpenAL Soft restored
- [ ] pause/resume/background behavior tested
- [ ] surface recreation/window resizing tested
- [ ] touch, hardware keyboard, and IME behavior audited
- [ ] save export/import provided

### M5 - Additional compatibility and upstreamability

- [ ] `x86_64` build
- [ ] emulator launch smoke test
- [ ] demo emulator smoke test if stable enough
- [ ] movies/optional codecs evaluated independently
- [ ] runtime migration behavior covered by tests
- [ ] obsolete Ant/`ndk-build` port removed
- [ ] Android changes split into upstream-reviewable commits/PRs

## First implementation slice

The first implementation PR should prove the native architecture, not runtime asset handling.

It should contain:

1. pinned Gradle/AGP/JDK/SDK/NDK/CMake project configuration;
2. pinned SDL2 source integration;
3. explicit GemRB Android SDL target integration;
4. `add_library(... SHARED)` Android GemRB target producing `libmain.so`;
5. correct `SDL2main` linkage on the application target;
6. Python 3.14.6 Android headers/native library wired at build time;
7. zlib and GNU libiconv available to GemRB;
8. static GemRB plugins;
9. `arm64-v8a` debug APK assembly;
10. one deterministic native startup log marker;
11. CI assembly plus 16 KB native-library checks.

Python standard-library extraction, `BootstrapActivity`, game importing, FreeType/PNG/Vorbis, and actual game startup follow in subsequent slices.

This keeps the first implementation focused while still satisfying the dependencies current GemRB requires to configure and link.

## Open decisions

1. Exact SDL2 release/commit to pin.
2. SDL2 source delivery: submodule versus checksummed source archive.
3. Exact GNU libiconv version and whether it links fully statically into `libmain.so`.
4. Whether Python runtime files can later be partially loaded without extraction; full extraction remains the initial design.
5. Exact Android SDK CMake package version to pin above GemRB's minimum.
6. Lowest viable `minSdk` after complete dependency validation; API 28 remains provisional.
7. Whether OpenAL Soft should be built inside the Android CMake graph or from a separately pinned source build.
8. Whether game data should eventually be accessed directly through a SAF-backed GemRB VFS.
9. Whether Android-only UI code remains minimal Java or uses Kotlin; Kotlin is preferred if the bootstrap/import UI grows beyond trivial glue.

## Design principles

- Keep Android platform code thin and separable from GemRB engine logic.
- Keep bootstrap/storage UX separate from SDL/native application lifetime.
- Prefer upstream-supported Android and SDL mechanisms over custom JNI infrastructure.
- Pin every build tool and externally supplied native dependency.
- Treat successful compilation and successful runtime dependency behavior as separate requirements.
- Do not use Bionic `iconv` as a substitute for GemRB's required legacy encodings.
- Make Python a build dependency from M0 rather than temporarily weakening GemRB's architecture.
- Keep large imported games out of internal storage by default.
- Never expose a partially installed runtime or partially imported game as valid.
- Avoid Android-wide filesystem permissions.
- Validate 16 KB page-size compatibility continuously.
- Preserve GemRB's cross-platform CMake source graph instead of maintaining an Android-specific source manifest.
- Structure changes so individual build-system and platform pieces can be upstreamed independently.
