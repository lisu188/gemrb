#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 <apk> [abi]" >&2
    exit 2
fi

APK="$(realpath "$1")"
ANDROID_ABI="${2:-${GEMRB_ANDROID_ABI:-arm64-v8a}}"
case "${ANDROID_ABI}" in
    arm64-v8a|x86_64) ;;
    *)
        echo "Unsupported Android ABI: ${ANDROID_ABI}" >&2
        exit 2
        ;;
esac

if [[ ! -f "${APK}" ]]; then
    echo "APK not found: ${APK}" >&2
    exit 1
fi

NDK_VERSION="29.0.14206865"
SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
NDK_ROOT="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}"
if [[ -z "${NDK_ROOT}" && -n "${SDK_ROOT}" ]]; then
    NDK_ROOT="${SDK_ROOT}/ndk/${NDK_VERSION}"
fi

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) HOST_TAG="linux-x86_64" ;;
    Darwin-x86_64|Darwin-arm64) HOST_TAG="darwin-x86_64" ;;
    *) echo "Unsupported host" >&2; exit 1 ;;
esac

READELF="${NDK_ROOT}/toolchains/llvm/prebuilt/${HOST_TAG}/bin/llvm-readelf"
if [[ ! -x "${READELF}" ]]; then
    echo "llvm-readelf not found under NDK ${NDK_ROOT}" >&2
    exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
if ! unzip -q "${APK}" "lib/${ANDROID_ABI}/*.so" -d "${TMP}"; then
    echo "No native libraries for ${ANDROID_ABI} found in APK" >&2
    exit 1
fi
LIB_DIR="${TMP}/lib/${ANDROID_ABI}"

for required in libmain.so libSDL2.so libpython3.14.so; do
    if [[ ! -f "${LIB_DIR}/${required}" ]]; then
        echo "Required native library missing from APK for ${ANDROID_ABI}: ${required}" >&2
        exit 1
    fi
done

for required_marker in \
    GEMRB_ANDROID_NATIVE_START \
    GEMRB_ANDROID_CONFIGURED_START \
    GEMRB_ANDROID_ENGINE_INIT \
    GEMRB_ANDROID_PYTHON_INIT \
    GEMRB_ANDROID_GUI_INIT; do
    if ! grep -aFq "${required_marker}" "${LIB_DIR}/libmain.so"; then
        echo "Required startup marker missing from libmain.so: ${required_marker}" >&2
        exit 1
    fi
done

RUNTIME_ARCHIVE="${TMP}/runtime.zip"
if ! unzip -p "${APK}" assets/runtime.zip > "${RUNTIME_ARCHIVE}" || [[ ! -s "${RUNTIME_ARCHIVE}" ]]; then
    echo "Required runtime archive missing from APK: assets/runtime.zip" >&2
    exit 1
fi

RUNTIME_LIST="${TMP}/runtime.list"
unzip -Z1 "${RUNTIME_ARCHIVE}" > "${RUNTIME_LIST}"
for required_asset in \
    VERSION \
    gemrb/GUIScripts/GUICommon.py \
    python/lib/python3.14/os.py \
    demo/chitin.key; do
    if ! grep -Fxq "${required_asset}" "${RUNTIME_LIST}"; then
        echo "Required runtime asset missing from runtime archive: ${required_asset}" >&2
        exit 1
    fi
done

runtime_version="$(unzip -p "${RUNTIME_ARCHIVE}" VERSION | tr -d '\r\n')"
if [[ "${runtime_version}" != "m3-1" ]]; then
    echo "Unexpected runtime archive version: ${runtime_version}" >&2
    exit 1
fi

status=0
while IFS= read -r -d '' library; do
    echo "Checking 16 KB ELF alignment for ${ANDROID_ABI}: $(basename "${library}")"
    while read -r alignment; do
        value=$((alignment))
        if (( value < 0x4000 )); then
            echo "LOAD segment alignment ${alignment} is below 0x4000 in ${library}" >&2
            status=1
        fi
    done < <("${READELF}" -lW "${library}" | awk '$1 == "LOAD" {print $NF}')
done < <(find "${LIB_DIR}" -type f -name '*.so' -print0)

if [[ -n "${SDK_ROOT}" ]]; then
    ZIPALIGN="$(find "${SDK_ROOT}/build-tools" -type f -name zipalign -print 2>/dev/null | sort -V | tail -n1 || true)"
    if [[ -n "${ZIPALIGN}" ]]; then
        "${ZIPALIGN}" -c -P 16 -v 4 "${APK}"
    fi
fi

exit "${status}"
