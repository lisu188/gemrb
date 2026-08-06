# Android Implementation Roadmap

Status: Draft implementation plan
Branch: `android-modernization`
Design: `platforms/android/ANDROID_MODERNIZATION.md`

## Objective

Restore Android as a reproducible first-class GemRB target in small, independently testable slices. The integration branch is `android-modernization`; commits should remain easy to split/cherry-pick for upstreaming.

Current mandatory configure/link dependencies mean the first native milestone is not Python-free. M0 must satisfy SDL2, Python development files, zlib, iconv, static plugins, and the Android shared-library entry model before an APK can load `libmain.so`.

## Pinned baseline

- AGP `9.4.0`
- Gradle `9.6.0`
- JDK `17`
- compile/target SDK `36`
- min SDK `28` initially
- NDK `29.0.14206865`
- SDL2 `2.32.10`
- CPython Android `3.14.7`
- GNU libiconv `1.19`
- ABI `arm64-v8a`

## M0 — Native APK

### Goal

Produce an installable arm64 debug APK that starts SDL, loads GemRB `libmain.so`, emits `GEMRB_ANDROID_NATIVE_START`, and exits cleanly before requiring the complete runtime asset set.

### 0.1 Gradle shell

Create/maintain the modern Gradle application under `platforms/android` and pin SDK/NDK/CMake/JDK/ABI values.

Acceptance:

- Gradle configuration succeeds from a clean checkout.
- new build does not depend on Ant/ndk-build.

### 0.2 SDL2

Fetch SDL2 `2.32.10` reproducibly with checksum verification. Expose SDL2 and SDL2main to GemRB CMake and compile the SDL Android Java activity sources.

Acceptance:

- SDL2 builds for arm64.
- `GemRBActivity extends SDLActivity` compiles.

### 0.3 Android GemRB target

Change Android from `ADD_EXECUTABLE` to `ADD_LIBRARY(... SHARED)` with `OUTPUT_NAME main`.

Acceptance:

- build produces `libmain.so`.
- SDL loads the application library.

### 0.4 SDL CMake compatibility

Reuse Android/in-tree SDL2 targets without requiring host-installed SDL2. Preserve non-Android `find_package(SDL2)` behavior. Keep SDL2main at the final application target, not in `SDLVideo`.

### 0.5 Python development/native libraries

Use official CPython Android `3.14.7` target-ABI headers and native libraries. `GUIScript` remains enabled.

Acceptance:

- Python configuration succeeds.
- `GUIScript` compiles/links.
- packaged Python native libraries resolve for arm64.

### 0.6 zlib

Resolve GemRB's mandatory zlib requirement with one intentional Android implementation.

### 0.7 GNU libiconv

Build GNU libiconv `1.19` from pinned source for Android and expose it to GemRB's existing iconv discovery.

Acceptance:

- configure succeeds.
- representative Infinity Engine legacy-codepage conversion test passes.

### 0.8 Static plugins

Use `STATIC_LINK=ON` and preserve whole-archive semantics for required GemRB plugins.

Acceptance:

- no runtime GemRB plugin `.so` discovery is required.
- `libmain.so` has no unresolved plugin symbols.

### 0.9 Native startup marker

Emit deterministic `GEMRB_ANDROID_NATIVE_START` immediately after SDL reaches GemRB's native entry point. An Android-only guarded M0 early exit is permitted until M1 runtime data exists.

### 0.10 16 KB validation

Validate every packaged shared library for 16 KB page compatibility and packaging alignment.

### M0 done when

- clean arm64 APK assembly succeeds;
- `libmain.so`, SDL2, Python, zlib/iconv linkage, and static plugins are valid;
- app launches on Android;
- logcat contains `GEMRB_ANDROID_NATIVE_START`;
- all packaged native libraries pass 16 KB checks;
- CI reproduces and uploads the APK.

## M1 — Runtime bootstrap and configured startup

### Goal

Install GemRB/Python assets into app-private storage, generate a valid managed config, explicitly pass that config to native GemRB, and reach GUI-script initialization.

### 1.1 BootstrapActivity

Launcher responsibilities:

```text
BootstrapActivity
  -> validate/install versioned runtime
  -> validate/install Python stdlib
  -> generate/update managed GemRB.cfg
  -> validate selected game when present
  -> start GemRBActivity
```

`GemRBActivity` stays a thin SDL host.

### 1.2 Versioned runtime installer

Install into:

```text
filesDir/runtime/<runtime-version>/
```

Use temporary directory -> validation -> atomic promotion. Never remove the last known-good runtime first.

Assets include GUIScripts, override, unhardcoded, Python stdlib, required shaders/data, and config template.

### 1.3 Explicit configuration loading

Canonical config path:

```text
<filesDir>/config/GemRB.cfg
```

`BootstrapActivity` must finish generating and validating this file before launching the SDL activity.

`GemRBActivity` overrides SDL2 `getArguments()` and passes:

```text
-c <absolute filesDir/config/GemRB.cfg>
```

Implementation contract:

```java
@Override
protected String[] getArguments() {
    return new String[] { "-c", configPath };
}
```

The path must come from trusted app-private state, not arbitrary external intent data.

Acceptance:

- native argv contains the explicit `-c` argument;
- GemRB logs/uses the managed config;
- managed `GamePath`, `SavePath`, `CachePath`, and runtime paths take effect;
- missing/invalid managed config fails visibly instead of silently selecting a different config.

### 1.4 Python runtime paths

Configure Python home/search paths to the installed private runtime before `GUIScript` initializes Python. No system Python, pip, or subprocess dependency.

Acceptance:

- Python initializes.
- GemRB imports GUI bootstrap modules.
- logcat reaches the M1 GUI-init marker.

### 1.5 Android path model

Target layout:

```text
filesDir/
├── runtime/
├── config/
└── metadata/

cacheDir/
└── gemrb/

externalFilesDir/
├── games/
└── saves/
```

Runtime is internal; large game data and saves are app-specific external storage; cache is internal.

## M2 — GemRB demo

### Goal

Reach an interactive GemRB demo before importing commercial game data.

Sequence:

1. pinned FreeType
2. pinned PNG
3. pinned Ogg/Vorbis
4. package/install demo resources
5. launch demo

Acceptance:

- demo reaches interactive GUI;
- fonts/PNG/resources render;
- required demo audio format support works.

## M3 — Real games

### Goal

Import at least one Infinity Engine game, reach its main menu, and verify save/load isolation.

### 3.1 SAF picker

Use Android directory picker for the source tree. Do not expose SAF `content://` directly to existing C++ filesystem APIs in the first implementation.

### 3.2 Game importer

Assign each imported installation a stable application-managed `game-id` and copy into:

```text
externalFilesDir/games/<game-id>/
```

Requirements:

- source-size/free-space preflight;
- progress/cancellation;
- temporary destination;
- essential-file validation;
- atomic promotion;
- stale temporary cleanup.

### 3.3 Game detection/configuration

Detect game type and update the managed config for the selected imported installation.

Required values:

```text
GamePath = externalFilesDir/games/<game-id>/
SavePath = externalFilesDir/saves/<game-id>/
```

A shared `externalFilesDir/saves` must never be used as `SavePath`.

### 3.4 Save isolation

GemRB may append the game's own `SaveDir` below `SavePath`, therefore the Android-provided root must already be unique per imported `game-id`.

Acceptance:

- two imported games with overlapping `save`/`quicksave`/`autosave` directory names cannot see or overwrite each other's slots;
- switching games updates `SavePath` to the selected game ID;
- new save can be created/reloaded;
- automated or integration test covers at least two distinct game IDs.

### 3.5 Save durability

Document that app-specific storage is removed on uninstall and add explicit export/import before release quality is claimed.

## M4 — Platform completeness

### 4.1 OpenAL Soft

Restore pinned OpenAL Soft after core game loading works.

### 4.2 Lifecycle

Required behavior:

```text
pause/resume              required
surface recreation        required
background/foreground     required
window resize             required
process death             clean restart
```

Do not attempt live in-memory session restoration after process death.

### 4.3 Input

Audit touch, mouse emulation, soft keyboard/IME, physical keyboard, and controller behavior exposed through SDL.

### 4.4 Movies/optional codecs

Restore only after core gameplay works.

## M5 — Secondary ABI, CI hardening, cleanup, upstreaming

1. add `x86_64` using matching CPython package;
2. add emulator smoke test;
3. assert progressive log markers;
4. produce APK/AAB artifacts;
5. add save export/import;
6. remove obsolete Ant/ndk-build pipeline;
7. split integration commits into upstream-ready changes.

Progressive markers:

```text
M0 GEMRB_ANDROID_NATIVE_START
M1 GEMRB_ANDROID_GUI_INIT
M2 GEMRB_ANDROID_DEMO_READY
```

## First implementation sequence

```text
1  Gradle shell
2  SDL2 source/targets
3  libmain.so
4  Android SDL CMake compatibility
5  Python development/native files
6  zlib
7  GNU libiconv
8  STATIC_LINK=ON
9  native startup marker
10 arm64 APK
11 16 KB validation
12 CI assembly/artifact
13 BootstrapActivity
14 versioned runtime installer
15 explicit -c managed-config argument
16 Python stdlib/runtime initialization
17 internal runtime/cache path model
18 FreeType
19 PNG
20 Ogg/Vorbis
21 GemRB demo
22 SAF importer + stable game-id
23 per-game GamePath/SavePath
24 real game main menu + save/load isolation
25 OpenAL
26 lifecycle/input hardening
27 x86_64 + emulator CI
28 obsolete build cleanup
```

## Testing gates

### Gate A — Configure

Android configuration resolves SDL2, Python, zlib, GNU libiconv, Threads, and static linking.

### Gate B — Link

`libmain.so` links all required static GemRB plugins.

### Gate C — Package

Gradle assembles an arm64 debug APK with all required `.so` files.

### Gate D — Native launch

APK launch emits `GEMRB_ANDROID_NATIVE_START`.

### Gate E — Configured runtime launch

Managed `GemRB.cfg` is passed explicitly with `-c` and GemRB reaches Python/GUI initialization.

### Gate F — Demo

Demo reaches an interactive screen.

### Gate G — Real game

A supported game reaches main menu and save/load works with per-game save isolation.

## Risks to validate early

1. CPython package interaction with GemRB `FindPython`.
2. CPython companion native-library packaging/loading.
3. SDL2 target naming and Android Java integration.
4. static plugin registration/link order under LLD.
5. GNU libiconv discovery/linkage.
6. 16 KB compatibility of prebuilt Python libraries.
7. Android whole-archive linker behavior.
8. runtime/Python path assumptions.
9. explicit config-argument propagation through SDLActivity.
10. multi-gigabyte import performance/free-space behavior.
11. lifecycle behavior after surface recreation.
12. per-game save identity/migration correctness.
