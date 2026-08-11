#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <apk>" >&2
    exit 2
fi

APK="$(realpath "$1")"
PACKAGE="org.gemrb.gemrb"
BOOTSTRAP_ACTIVITY=".BootstrapActivity"
LOG_FILE="${GEMRB_ANDROID_SMOKE_LOG:-gemrb-emulator.log}"
UI_DUMP="$(mktemp)"
trap 'rm -f "${UI_DUMP}"' EXIT

if [[ ! -f "${APK}" ]]; then
    echo "APK not found: ${APK}" >&2
    exit 1
fi

find_demo_center() {
    adb shell uiautomator dump /sdcard/gemrb-window.xml >/dev/null 2>&1 || return 1
    adb pull /sdcard/gemrb-window.xml "${UI_DUMP}" >/dev/null 2>&1 || return 1
    python3 - "${UI_DUMP}" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
for node in root.iter("node"):
    if node.attrib.get("text", "").casefold() != "Launch bundled demo".casefold():
        continue
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds", ""))
    if match is None:
        continue
    left, top, right, bottom = map(int, match.groups())
    print((left + right) // 2, (top + bottom) // 2)
    raise SystemExit(0)
raise SystemExit(1)
PY
}

capture_log() {
    adb logcat -d -v threadtime > "${LOG_FILE}"
}

dump_app_threads() {
    local pid
    pid="$(adb shell pidof "${PACKAGE}" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
    if [[ -n "${pid}" ]]; then
        adb shell kill -3 "${pid}" || true
        sleep 1
    fi
    capture_log
}

adb install -r "${APK}"
adb shell pm clear "${PACKAGE}" >/dev/null
adb logcat -c
adb shell am start -W -n "${PACKAGE}/${BOOTSTRAP_ACTIVITY}"

runtime_extracted=false
for _ in $(seq 1 240); do
    capture_log
    if grep -aFq "GEMRB_ANDROID_RUNTIME_EXTRACT_DONE" "${LOG_FILE}"; then
        runtime_extracted=true
        break
    fi
    if grep -aFq "Android runtime bootstrap failed" "${LOG_FILE}"; then
        break
    fi
    sleep 1
done

if [[ "${runtime_extracted}" != true ]]; then
    dump_app_threads
    echo "GemRB runtime extraction did not complete" >&2
    grep -aF "GEMRB_ANDROID_RUNTIME_EXTRACT_" "${LOG_FILE}" >&2 || true
    exit 1
fi

button_center=""
for _ in $(seq 1 10); do
    if button_center="$(find_demo_center)"; then
        break
    fi
    sleep 1
done

if [[ -z "${button_center}" ]]; then
    dump_app_threads
    echo "Bundled demo launch button did not become available after runtime extraction" >&2
    exit 1
fi

read -r button_x button_y <<<"${button_center}"
adb shell input tap "${button_x}" "${button_y}"

markers=(
    GEMRB_ANDROID_NATIVE_START
    GEMRB_ANDROID_CONFIGURED_START
    GEMRB_ANDROID_ENGINE_INIT
    GEMRB_ANDROID_PYTHON_INIT
    GEMRB_ANDROID_GUI_INIT
    GEMRB_ANDROID_DEMO_READY
)

all_markers=false
for _ in $(seq 1 180); do
    capture_log
    all_markers=true
    for marker in "${markers[@]}"; do
        if ! grep -aFq "${marker}" "${LOG_FILE}"; then
            all_markers=false
            break
        fi
    done
    if [[ "${all_markers}" == true ]]; then
        break
    fi
    sleep 1
done

if [[ "${all_markers}" != true ]]; then
    dump_app_threads
    echo "GemRB did not reach all startup markers" >&2
    for marker in "${markers[@]}"; do
        if ! grep -aFq "${marker}" "${LOG_FILE}"; then
            echo "Missing marker: ${marker}" >&2
        fi
    done
    exit 1
fi

sleep 5
capture_log
if [[ -z "$(adb shell pidof "${PACKAGE}" 2>/dev/null | tr -d '\r')" ]]; then
    echo "GemRB process exited after startup" >&2
    exit 1
fi

if [[ -n "${GEMRB_ANDROID_SMOKE_SCREENSHOT:-}" ]]; then
    resumed_activity="$(adb shell dumpsys activity activities \
        | grep -aEm1 'mResumedActivity|topResumedActivity' || true)"
    if [[ "${resumed_activity}" != *"${PACKAGE}/.GemRBActivity"* ]]; then
        echo "GemRBActivity is not the top-resumed activity: ${resumed_activity}" >&2
        exit 1
    fi

    mkdir -p "$(dirname "${GEMRB_ANDROID_SMOKE_SCREENSHOT}")"
    adb exec-out screencap -p > "${GEMRB_ANDROID_SMOKE_SCREENSHOT}"
    python3 - "${GEMRB_ANDROID_SMOKE_SCREENSHOT}" <<'PY'
import struct
import sys
import zlib

payload = open(sys.argv[1], "rb").read()
if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
    raise SystemExit("GemRB emulator screenshot is not a PNG")

offset = 8
dimensions = None
image_data = []
saw_iend = False
while offset + 12 <= len(payload):
    length = struct.unpack(">I", payload[offset:offset + 4])[0]
    chunk_type = payload[offset + 4:offset + 8]
    chunk_end = offset + 12 + length
    if chunk_end > len(payload):
        raise SystemExit("GemRB emulator screenshot has a truncated PNG chunk")
    chunk_data = payload[offset + 8:offset + 8 + length]
    expected_crc = struct.unpack(">I", payload[offset + 8 + length:chunk_end])[0]
    actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise SystemExit("GemRB emulator screenshot has an invalid PNG checksum")
    if chunk_type == b"IHDR":
        dimensions = struct.unpack(">II", chunk_data[:8])
    elif chunk_type == b"IDAT":
        image_data.append(chunk_data)
    elif chunk_type == b"IEND":
        if length != 0:
            raise SystemExit("GemRB emulator screenshot has an invalid PNG end chunk")
        saw_iend = True
        break
    offset = chunk_end

if dimensions is None or min(dimensions) <= 0 or not image_data or not saw_iend:
    raise SystemExit("GemRB emulator screenshot is missing required PNG chunks")
zlib.decompress(b"".join(image_data))
PY
fi

echo "GemRB emulator smoke test reached the bundled demo and remained alive"
