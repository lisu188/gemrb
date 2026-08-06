# Android Implementation Roadmap

Status: Draft implementation plan
Branch: `android-modernization`
Design: `platforms/android/ANDROID_MODERNIZATION.md`

## Objective

Restore Android as a reproducible first-class GemRB build target in small, independently testable slices that can later be split into upstreamable pull requests.

The implementation order is constrained by current GemRB CMake behavior:

- Python development files are mandatory at configure time.
- Zlib is mandatory at configure time.
- Iconv is mandatory at configure time.
- `GUIScript` is always built.
- static GemRB plugins are the preferred Android packaging model.
- the Android application target must be a shared library loaded through SDL2.

The first useful milestone is therefore not a Python-free GemRB build. It is a native Android APK that satisfies all mandatory link-time dependencies, loads `libmain.so`, emits a deterministic startup marker, and exits before requiring the full runtime data set.

## Branch strategy

Use `android-modernization` as the integration branch.

Implementation slices should be committed so they can later be split or cherry-picked into smaller upstream PRs.

Recommended commit families:

1. Android Gradle shell
2. SDL2 integration
3. GemRB Android CMake target
4. mandatory native dependencies
5. static plugin linkage
6. CI and native validation
7. runtime bootstrap
8. demo dependencies
9. game import and storage
10. lifecycle/input/audio completion

## M0 — Native APK builds

### Goal

Produce an installable `arm64-v8a` debug APK that starts the SDL Android activity, loads GemRB's `libmain.so`, emits a known logcat marker, and exits cleanly before full GemRB initialization.

### Slice 0.1 — Gradle project skeleton

Create a conventional Android Gradle project under `platforms/android`.

Expected files:

```text
platforms/android/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/
│   └── wrapper/
├── gradlew
├── gradlew.bat
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/org/gemrb/gemrb/
        └── res/
```

Pin:

- Android Gradle Plugin
- Gradle wrapper
- JDK requirement
- compile SDK
- target SDK
- min SDK
- NDK version
- CMake version used by Gradle
- supported ABI list

Initial ABI:

```text
arm64-v8a
```

Do not enable additional ABIs until arm64 is stable.

Acceptance criteria:

- `./gradlew tasks` succeeds.
- `./gradlew assembleDebug` reaches native configuration.
- no Ant/ndk-build files are required by the new Gradle build.

### Slice 0.2 — Pin and integrate SDL2

Use a pinned SDL2 release/tag, not an unpinned branch.

Preferred structure:

```text
platforms/android/third_party/SDL2
```

or an equivalent reproducible pinned source mechanism.

The Gradle native build should invoke CMake with SDL2 available as actual CMake targets.

Required target model:

```text
SDL2::SDL2
SDL2::SDL2main
```

If upstream SDL2 exposes un-namespaced targets for the selected release, normalize them in the Android CMake glue instead of spreading target-name conditionals through GemRB.

Acceptance criteria:

- SDL2 builds for `arm64-v8a`.
- Java/Kotlin sources compile against SDL2's Android activity classes.
- an SDL-hosted native library can be loaded by the APK.

### Slice 0.3 — Convert GemRB Android target to `libmain.so`

Modify `gemrb/CMakeLists.txt`.

Current Android behavior:

```text
ADD_EXECUTABLE(gemrb ...)
```

Target behavior:

```text
ADD_LIBRARY(gemrb SHARED ...)
OUTPUT_NAME main
```

Keep the existing Android entry sources:

```text
platforms/android/GemRB.cpp
platforms/android/AndroidLogger.cpp
```

Link `SDL2main` on Android explicitly at the application target level.

Do not attach `SDL2main` to the SDL video plugin.

Acceptance criteria:

- build produces `libmain.so`.
- APK packages `libmain.so` and SDL2 correctly.
- SDLActivity resolves and loads the expected application library.

### Slice 0.4 — Android-aware SDL CMake configuration

Current GemRB configuration assumes `find_package(SDL2)`.

Add an Android-specific path that accepts already-existing SDL2 CMake targets when SDL2 is included by the Android build.

Desired behavior:

```text
ANDROID + existing SDL2 target
    -> reuse target
    -> populate GemRB's internal SDL variables
else
    -> preserve current desktop find_package behavior
```

Do not regress non-Android platforms.

Acceptance criteria:

- Android does not require a host-installed SDL2 package.
- desktop/macOS/Windows behavior is unchanged.
- `SDLVideo` links to SDL2 without inheriting `SDL2main`.

### Slice 0.5 — Integrate mandatory Python development files

Current GemRB always runs Python configuration and always builds `GUIScript`.

Use the official CPython Android distribution for the target ABI.

M0 requires only what is necessary for configure/link:

```text
Python headers
libpython3.14.so
required companion native libraries
CMake variables/targets needed by GemRB
```

The Python standard library and Python runtime extraction are M1 work.

Prefer an Android-specific imported CMake target or compatibility variables so GemRB does not need a parallel source list.

Acceptance criteria:

- `CONFIGURE_PYTHON()` succeeds for the Android target ABI.
- `GUIScript` compiles and links.
- packaged Python native libraries have no unresolved target-ABI dependencies.

### Slice 0.6 — Integrate Zlib

GemRB requires Zlib during CMake configuration.

Prefer either:

- Android/NDK-provided zlib if compatible with GemRB's usage and CMake discovery; or
- a pinned source build exposed as a standard CMake target.

Do not add a custom GemRB-only zlib API layer.

Acceptance criteria:

- `find_package(ZLIB REQUIRED)` succeeds in the Android configuration.
- the final native dependency graph contains one intentional zlib implementation.

### Slice 0.7 — Integrate GNU libiconv

Do not rely on Bionic's limited iconv implementation for GemRB's legacy game encodings.

Build GNU libiconv from pinned source for Android and expose it to GemRB's existing Iconv discovery or through a small Android compatibility layer.

Target model:

```text
libiconv static library
    -> GemRB core/plugins
    -> libmain.so
```

Acceptance criteria:

- `find_package(Iconv REQUIRED)` succeeds.
- test conversions for at least one Windows code page used by Infinity Engine games pass on Android.
- no dependency on unrestricted system iconv behavior remains.

### Slice 0.8 — Static GemRB plugins

Enable:

```text
STATIC_LINK=ON
```

Verify every Android-required plugin is included in the final whole-archive linkage.

Pay particular attention to:

- `GUIScript`
- `SDLVideo`
- filesystem/resource plugins needed before GUI startup

Do not attempt dynamic plugin discovery inside the APK for the first implementation.

Acceptance criteria:

- no required GemRB plugin `.so` files are expected at runtime.
- plugin registration succeeds in static-link mode.
- `libmain.so` has no unresolved GemRB plugin symbols.

### Slice 0.9 — Native startup marker

Add a deterministic Android-native startup marker immediately after SDL transfers control to GemRB's `main()` and before full engine initialization.

Example semantic marker:

```text
GEMRB_ANDROID_NATIVE_START
```

For M0, allow a temporary guarded early-exit path after the marker if full runtime data is not installed yet.

The guard must be Android-only and explicitly temporary so it cannot affect desktop targets.

Acceptance criteria:

```text
adb install -r app-debug.apk
adb logcat
```

shows the marker after launching the app.

### Slice 0.10 — 16 KB page-size validation

Validate every packaged native library, including prebuilt Python libraries.

CI must inspect:

- `libmain.so`
- SDL2
- Python
- companion Python native libraries
- any prebuilt dependency

Acceptance criteria:

- packaged ELF segments meet current Android 16 KB page-size alignment requirements.
- validation runs automatically in CI.

## M1 — Runtime bootstrap and Python initialization

### Goal

Install GemRB/Python runtime assets into app-private storage, generate a valid configuration, start GemRB normally, and reach GUI script initialization.

### Slice 1.1 — Introduce `BootstrapActivity`

Create:

```text
BootstrapActivity
    -> validates runtime installation
    -> installs/updates runtime assets
    -> creates config
    -> starts GemRBActivity
```

`GemRBActivity` should remain a thin SDL2 host.

The old `GemRB.java` extraction behavior should not be copied directly because it:

- extracts on every SDL activity start;
- deletes directories eagerly;
- mixes setup and engine lifecycle;
- uses obsolete storage assumptions.

Acceptance criteria:

- native SDL activity never starts before runtime installation is complete.
- rotation/recreation of the bootstrap screen does not corrupt installation.

### Slice 1.2 — Versioned runtime installer

Package and install:

```text
GUIScripts/
override/
unhardcoded/
Python standard library
required engine shaders/data
configuration template
```

Install into an internal versioned directory:

```text
files/runtime/<runtime-version>/
```

Use atomic installation:

```text
runtime.tmp/
    -> fully install
    -> validate
    -> rename to final version
```

Never delete the last known-good runtime before the replacement is valid.

Acceptance criteria:

- first launch installs once.
- second launch skips unnecessary extraction.
- app update installs the new version safely.

### Slice 1.3 — Python runtime paths

Before `GUIScript` initialization, configure Python to use the installed Android runtime.

Required behavior:

- no dependency on system Python;
- no pip requirement;
- no subprocess requirement;
- target-specific Python search path points into internal app storage.

Acceptance criteria:

- Python interpreter initializes.
- GemRB imports its GUI bootstrap modules.
- logcat shows a deterministic GUI initialization marker.

### Slice 1.4 — Android path model

Replace the current Android entry-point behavior that maps `GEMRB_DATA` to external storage.

Target layout:

```text
internal filesDir
├── runtime/
├── config/
└── metadata/

internal cacheDir
└── gemrb-cache/

app-specific external files
├── games/
└── saves/
```

Use SDL Android storage helpers where they are sufficient; add JNI only where Android framework APIs are actually needed.

Acceptance criteria:

- GemRB engine runtime data resolves from internal storage.
- cache uses internal cache storage.
- no broad storage permission is requested.

### Slice 1.5 — Configuration generation

Generate `GemRB.cfg` from a versioned template.

Android owns platform paths.

GemRB owns game/engine settings.

Initial Android-managed values:

```text
GamePath
CachePath
SavePath
GUIScriptsPath / engine data path
Python runtime path
```

Acceptance criteria:

- no ADB manual editing required.
- invalid/old path configuration can be regenerated safely.

## M2 — GemRB demo

### Goal

Run the GemRB demo on Android before importing commercial game data.

### Slice 2.1 — FreeType

Build pinned FreeType for Android and expose it through existing GemRB discovery.

### Slice 2.2 — PNG

Build pinned libpng for Android and expose it through existing GemRB discovery.

### Slice 2.3 — Ogg/Vorbis

Build pinned Ogg/Vorbis for Android and expose `vorbisfile` to GemRB.

### Slice 2.4 — Demo assets and launch

Package/install demo resources as needed and launch the GemRB demo.

Acceptance criteria:

- demo reaches interactive GUI.
- text renders correctly.
- PNG resources load.
- audio format support required by the demo works.

## M3 — Real game loading

### Goal

Import an Infinity Engine game and reach its main menu.

### Slice 3.1 — Storage Access Framework picker

Use Android's directory picker to obtain a source tree.

Do not expose document-provider URIs directly to GemRB's existing filesystem APIs yet.

### Slice 3.2 — Game importer

Copy selected game data into:

```text
externalFilesDir/games/<game-id>/
```

Requirements:

- preflight required size;
- preflight available space;
- progress reporting;
- cancellation;
- temporary destination;
- atomic rename on success;
- cleanup on failure.

### Slice 3.3 — Game detection

Detect supported game type from imported files and generate/update configuration accordingly.

### Slice 3.4 — Saves and cache

Use:

```text
externalFilesDir/saves
cacheDir/gemrb-cache
```

Document that app-specific external data is deleted on uninstall.

Plan explicit save export/import later.

Acceptance criteria:

- at least one supported Infinity Engine game reaches main menu.
- new save can be created and reloaded.

## M4 — Platform completeness

### Slice 4.1 — OpenAL Soft

Build pinned OpenAL Soft from source for Android.

Acceptance criteria:

- music/SFX work.
- background/foreground transitions do not leave audio stuck.

### Slice 4.2 — Lifecycle

Required supported behavior:

```text
pause/resume                 required
surface recreation           required
background/foreground        required
window resize                required
process death                clean restart
```

Do not attempt restoration of live in-memory game state after process death.

### Slice 4.3 — Input

Audit:

- touch
- mouse emulation
- soft keyboard / IME
- physical keyboard
- gamepad behavior if SDL exposes it cleanly

Do not redesign the entire GemRB UI during platform restoration.

### Slice 4.4 — Movies and optional codecs

Only add movie playback dependencies after core gameplay works.

## M5 — CI, secondary ABI, cleanup, upstreaming

### Slice 5.1 — Android GitHub Actions build

CI should:

1. install pinned JDK/SDK/NDK/CMake;
2. fetch pinned dependencies;
3. assemble debug APK;
4. validate native libraries;
5. upload APK artifact.

### Slice 5.2 — x86_64

Add x86_64 after arm64 is stable.

Acceptance criteria:

- same dependency set builds for x86_64.
- official CPython x86_64 package integrates cleanly.

### Slice 5.3 — Emulator smoke test

Run x86_64 emulator CI and assert log markers.

Progressive markers:

```text
M0: GEMRB_ANDROID_NATIVE_START
M1: GEMRB_ANDROID_GUI_INIT
M2: GEMRB_ANDROID_DEMO_READY
```

### Slice 5.4 — Remove obsolete Android pipeline

After the Gradle/CMake build is proven:

Remove or archive obsolete:

```text
prep_env.sh
GEMRB_Android.mk
GEMRB_Application.mk
Ant project files
legacy README instructions
```

Do this separately from initial bring-up so regressions are easier to diagnose.

### Slice 5.5 — Save export/import

Add a user-visible mechanism to export and restore saves outside app-specific storage.

### Slice 5.6 — Upstream PR split

Recommended upstream order:

1. CMake: Android shared target + SDL target compatibility
2. Android Gradle/SDL shell
3. Python/Zlib/Iconv Android dependency integration
4. runtime bootstrap/storage
5. demo dependencies
6. game importer
7. lifecycle/audio/input
8. CI and obsolete-build cleanup

## First implementation branch sequence

Within `android-modernization`, implement in this exact order:

```text
1. Gradle shell
2. SDL2 source/targets
3. libmain.so
4. Android SDL CMake compatibility
5. Python development/native files
6. Zlib
7. GNU libiconv
8. STATIC_LINK=ON
9. native startup marker
10. arm64 APK
11. 16 KB validation
12. CI assembly
13. BootstrapActivity
14. runtime installer
15. Python stdlib/runtime initialization
16. Android path/config generation
17. FreeType
18. PNG
19. Ogg/Vorbis
20. GemRB demo
21. SAF importer
22. real game main menu
23. OpenAL
24. lifecycle/input hardening
25. x86_64 + emulator CI
26. obsolete Android build cleanup
```

## M0 file-level change map

Likely existing files to modify:

```text
gemrb/CMakeLists.txt
cmake/GemRBFunctions.cmake or equivalent SDL/Python configuration helpers
platforms/android/GemRB.cpp
platforms/android/AndroidLogger.cpp
```

New Android Gradle/CMake files will live under:

```text
platforms/android/app/
platforms/android/gradle/
platforms/android/cmake/
platforms/android/third_party/ or equivalent dependency location
```

Avoid replacing GemRB's top-level CMake project with an Android-specific native source manifest.

## Testing gates

### Gate A — Configure

Android CMake configure succeeds with:

```text
Python
Zlib
GNU libiconv
SDL2
Threads
STATIC_LINK
```

### Gate B — Link

`libmain.so` links successfully with all required static GemRB plugins.

### Gate C — Package

Gradle assembles an arm64 debug APK containing all required native `.so` files.

### Gate D — Native launch

APK launches and prints:

```text
GEMRB_ANDROID_NATIVE_START
```

### Gate E — Runtime launch

After M1, GemRB reaches GUI script initialization.

### Gate F — Demo

After M2, GemRB demo reaches an interactive screen.

### Gate G — Real game

After M3, a supported Infinity Engine game reaches main menu and can save/load.

## Risks to validate early

1. CPython Android package compatibility with GemRB's current CMake `FindPython` behavior.
2. CPython companion native library packaging and loading order.
3. SDL2 target naming/version differences.
4. static plugin registration/link order on Android/LLD.
5. GNU libiconv CMake discovery integration.
6. 16 KB compatibility of every prebuilt Python library.
7. Android linker behavior around whole-archive static plugins.
8. runtime path assumptions in GemRB core and Python initialization.
9. game size and import performance for multi-gigabyte installs.
10. lifecycle behavior after SDL surface recreation.

## Definition of M0 done

M0 is complete only when all of the following are true:

- Gradle build is reproducible from a clean checkout.
- toolchain and dependency versions are pinned.
- `arm64-v8a` APK assembles.
- GemRB is built as `libmain.so`.
- SDL2/SDL2main are linked correctly.
- Python target headers/libraries are present.
- Zlib is resolved.
- GNU libiconv is resolved.
- static GemRB plugins link successfully.
- app launches on Android.
- logcat shows `GEMRB_ANDROID_NATIVE_START`.
- all packaged native libraries pass 16 KB page-size validation.
- CI reproduces the APK build.

Only after this gate should implementation proceed to runtime extraction and actual Python/GemRB startup.
