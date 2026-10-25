Android bootstrap regressions
=============================

The legacy `GemRB.java` APK asset extractor has a separate host regression:

```sh
python3 -B platforms/android/tests/test_legacy_asset_extraction.py
```

It compiles the complete production extraction method unchanged with a host
JDK (`java` and `javac` on `PATH`, Java 8 target) and replaces only its Android
activity shell. Synthetic ZIP fixtures verify exact `assets/` filtering, nested
and Unicode assets, normalized root directory entries (but not root-resolving
files), parent/sibling traversal, absolute and
backslash names, an invalid output root, and an existing symlink escape when
the host permits creating one. Rejected entries preserve outside canaries.
Fixtures and compiler output live only in test-owned temporary directories.
This covers the retained legacy activity; the current Gradle app instead uses
the separate `org.gemrb.gemrb` bootstrap and runtime installer below. It does
not establish Android packaging or runtime acceptance.

`GamePathsTest` and `BootstrapStorageTest` run with a host JDK, without an
Android SDK or game assets. They exercise the production path, runtime,
transaction journal and cancellation helpers. The Android workflow runs them
before preparing native dependencies.

The storage tests cover changed/unchanged runtime identities, preservation of
legacy runtimes/customizations/saves, failed extraction, cancellation around
durable registration, interruption at every journal phase and between rename
and phase persistence, repeated recovery, Unicode names, preserved save files,
modified/unrecorded data, legacy remnants and child/ancestor symlink escapes.
Scratch fixtures are created with `Files.createTempDirectory` and removed by
the test that owns them.

`BootstrapRegression` is a dependency-free Android instrumentation runner. In
the disposable CI emulator it seeds a valid legacy `m3-1` runtime, verifies
activation of the packaged digest without removing custom files or saves,
checks the late-cancellation completion UI and forces a config/launch error
to verify that ordinary buttons become usable again. The workflow builds its
test APK and invokes `scripts/bootstrap-emulator.sh` before the demo smoke.

Recovery policy
---------------

New imports record a private, fsynced phase journal before staging creation and
append a size/SHA-256 ownership record after each complete, fsynced non-save
copy. Startup recovery completes before enabling imports or launches. It can
finish validated promotions and register a fully copied game, or clean only
individually recorded files that still match their size and hash. Registration
is synchronous and precedes deletion of its journal. A journal-maintenance
failure after registration never rolls back the registered data.

Saves, backups, changed files, incomplete/unrecorded files, unexpected entries,
symbolic links and journal-less legacy remnants are preserved. Runtime
installations and interrupted runtime extraction directories are also kept:
older directories can contain user-modified GUI scripts and there is no old
per-file baseline proving those files disposable. The bootstrap reports retained
paths below the launch controls, with expandable details, and logs exact cleanup
paths/bytes. Prior runtime customizations are preserved in their original
directories; they are not automatically copied over changed packaged scripts.

Native builds, APK packaging and emulator execution are CI validation. A host
JDK pass alone does not establish Android lifecycle or gameplay acceptance.
