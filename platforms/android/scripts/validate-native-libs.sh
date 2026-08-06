#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <apk>" >&2
    exit 2
fi

APK="$(realpath "$1")"
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
unzip -q "${APK}" 'lib/arm64-v8a/*.so' -d "${TMP}"
LIB_DIR="${TMP}/lib/arm64-v8a"

for required in libmain.so libSDL2.so libpython3.14.so; do
    if [[ ! -f "${LIB_DIR}/${required}" ]]; then
        echo "Required native library missing from APK: ${required}" >&2
        exit 1
    fi
done

for required_asset in \
    assets/runtime/VERSION \
    assets/runtime/gemrb/GUIScripts/GUICommon.py \
    assets/runtime/python/lib/python3.14/os.py \
    assets/runtime/demo/chitin.key; do
    if ! unzip -Z1 "${APK}" | grep -Fxq "${required_asset}"; then
        echo "Required runtime asset missing from APK: ${required_asset}" >&2
        exit 1
    fi
done

status=0
while IFS= read -r -d '' library; do
    echo "Checking 16 KB ELF alignment: $(basename "${library}")"
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
