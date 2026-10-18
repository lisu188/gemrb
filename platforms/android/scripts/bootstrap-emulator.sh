#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <app-apk> <test-apk>" >&2
    exit 2
fi

# This runs only in the dedicated disposable CI emulator, before demo smoke.
adb install -r "$1"
adb install -r "$2"
adb shell pm clear org.gemrb.gemrb >/dev/null
log="${GEMRB_ANDROID_BOOTSTRAP_LOG:-gemrb-bootstrap-regressions.log}"
adb shell am instrument -w org.gemrb.gemrb.test/org.gemrb.gemrb.BootstrapRegression | tee "${log}"
grep -Fq BOOTSTRAP_REGRESSIONS_OK "${log}"
if grep -Fq BOOTSTRAP_REGRESSIONS_FAILED "${log}"; then exit 1; fi
