#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_DIR="${ANDROID_DIR}/.deps"
DOWNLOAD_DIR="${DEPS_DIR}/downloads"
BUILD_DIR="${DEPS_DIR}/build"

OPENAL_VERSION="1.25.2"
OPENAL_ARCHIVE="openal-soft-${OPENAL_VERSION}.tar.bz2"
OPENAL_URL="https://openal-soft.org/openal-releases/${OPENAL_ARCHIVE}"
OPENAL_SHA256="1dbaac44e7579d5bc8847ca8db4b2e8b9fd3961041f35ee20def4958301e1089"

NDK_VERSION="29.0.14206865"
ANDROID_API="28"
ANDROID_ABI="${GEMRB_ANDROID_ABI:-arm64-v8a}"

case "${ANDROID_ABI}" in
    arm64-v8a|x86_64) ;;
    *)
        echo "Unsupported Android ABI: ${ANDROID_ABI}" >&2
        exit 2
        ;;
esac

ABI_DEPS_DIR="${DEPS_DIR}/abi/${ANDROID_ABI}"
ABI_BUILD_DIR="${BUILD_DIR}/${ANDROID_ABI}"
OPENAL_ROOT="${ABI_DEPS_DIR}/openal"
OPENAL_PREFIX="${OPENAL_ROOT}/prefix"

mkdir -p "${DOWNLOAD_DIR}" "${ABI_BUILD_DIR}"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

resolve_ndk() {
    if [[ -n "${ANDROID_NDK_HOME:-}" && -d "${ANDROID_NDK_HOME}" ]]; then
        printf '%s\n' "${ANDROID_NDK_HOME}"
        return
    fi
    if [[ -n "${ANDROID_NDK_ROOT:-}" && -d "${ANDROID_NDK_ROOT}" ]]; then
        printf '%s\n' "${ANDROID_NDK_ROOT}"
        return
    fi
    local sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
    if [[ -n "${sdk}" && -d "${sdk}/ndk/${NDK_VERSION}" ]]; then
        printf '%s\n' "${sdk}/ndk/${NDK_VERSION}"
        return
    fi
    echo "Android NDK ${NDK_VERSION} not found" >&2
    exit 1
}

archive="${DOWNLOAD_DIR}/${OPENAL_ARCHIVE}"
temporary="${archive}.tmp"
if [[ -f "${archive}" && "$(sha256_file "${archive}")" != "${OPENAL_SHA256}" ]]; then
    echo "Discarding corrupt cached download: ${archive}" >&2
    rm -f "${archive}"
fi
if [[ ! -f "${archive}" ]]; then
    rm -f "${temporary}"
    if ! curl \
        --fail \
        --location \
        --retry 8 \
        --retry-all-errors \
        --retry-delay 2 \
        --connect-timeout 20 \
        --output "${temporary}" \
        "${OPENAL_URL}"; then
        rm -f "${temporary}"
        exit 1
    fi
    actual="$(sha256_file "${temporary}")"
    if [[ "${actual}" != "${OPENAL_SHA256}" ]]; then
        echo "SHA-256 mismatch for ${OPENAL_URL}" >&2
        echo "expected: ${OPENAL_SHA256}" >&2
        echo "actual:   ${actual}" >&2
        rm -f "${temporary}"
        exit 1
    fi
    mv "${temporary}" "${archive}"
fi

if [[ -f "${OPENAL_ROOT}/.gemrb-ready-${OPENAL_VERSION}" ]]; then
    echo "OpenAL Soft ${OPENAL_VERSION} for ${ANDROID_ABI} is ready"
    exit 0
fi

NDK_ROOT="$(resolve_ndk)"
OPENAL_SRC="${ABI_BUILD_DIR}/openal-soft-${OPENAL_VERSION}"
OPENAL_BUILD="${ABI_BUILD_DIR}/openal-soft-${OPENAL_VERSION}-build"

rm -rf "${OPENAL_ROOT}" "${OPENAL_SRC}" "${OPENAL_BUILD}"
mkdir -p "${OPENAL_ROOT}"
tar -xjf "${archive}" -C "${ABI_BUILD_DIR}"

cmake \
    -S "${OPENAL_SRC}" \
    -B "${OPENAL_BUILD}" \
    -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="${NDK_ROOT}/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="${ANDROID_ABI}" \
    -DANDROID_PLATFORM="android-${ANDROID_API}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${OPENAL_PREFIX}" \
    -DLIBTYPE=STATIC \
    -DALSOFT_WERROR=OFF \
    -DALSOFT_ENABLE_MODULES=OFF \
    -DALSOFT_UTILS=OFF \
    -DALSOFT_EXAMPLES=OFF \
    -DALSOFT_TESTS=OFF \
    -DALSOFT_DLOPEN=OFF \
    -DALSOFT_RTKIT=OFF \
    -DALSOFT_EAX=OFF \
    -DALSOFT_BACKEND_OBOE=OFF \
    -DALSOFT_BACKEND_OPENSL=ON \
    -DALSOFT_REQUIRE_OPENSL=ON \
    -DALSOFT_BACKEND_PIPEWIRE=OFF \
    -DALSOFT_BACKEND_PULSEAUDIO=OFF \
    -DALSOFT_BACKEND_ALSA=OFF \
    -DALSOFT_BACKEND_OSS=OFF \
    -DALSOFT_BACKEND_SNDIO=OFF \
    -DALSOFT_BACKEND_JACK=OFF \
    -DALSOFT_BACKEND_PORTAUDIO=OFF \
    -DALSOFT_BACKEND_SDL2=OFF \
    -DALSOFT_BACKEND_SDL3=OFF \
    -DALSOFT_BACKEND_WAVE=OFF \
    -DALSOFT_INSTALL_CONFIG=OFF \
    -DALSOFT_INSTALL_HRTF_DATA=OFF \
    -DALSOFT_INSTALL_AMBDEC_PRESETS=OFF \
    -DALSOFT_INSTALL_EXAMPLES=OFF \
    -DALSOFT_INSTALL_UTILS=OFF \
    -DALSOFT_UPDATE_BUILD_VERSION=OFF

cmake --build "${OPENAL_BUILD}" --parallel
cmake --install "${OPENAL_BUILD}"

if [[ ! -f "${OPENAL_PREFIX}/lib/libopenal.a" || ! -f "${OPENAL_PREFIX}/include/AL/al.h" ]]; then
    echo "OpenAL Soft static install is incomplete" >&2
    exit 1
fi

touch "${OPENAL_ROOT}/.gemrb-ready-${OPENAL_VERSION}"
echo "OpenAL Soft ${OPENAL_VERSION} for ${ANDROID_ABI} is ready in ${OPENAL_PREFIX}"
