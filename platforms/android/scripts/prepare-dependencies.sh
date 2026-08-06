#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_DIR="${ANDROID_DIR}/.deps"
DOWNLOAD_DIR="${DEPS_DIR}/downloads"
BUILD_DIR="${DEPS_DIR}/build"

SDL_VERSION="2.32.10"
SDL_ARCHIVE="SDL2-${SDL_VERSION}.tar.gz"
SDL_URL="https://www.libsdl.org/release/${SDL_ARCHIVE}"
SDL_SHA256="5f5993c530f084535c65a6879e9b26ad441169b3e25d789d83287040a9ca5165"

PYTHON_VERSION="3.14.7"
PYTHON_ARCHIVE="python-${PYTHON_VERSION}-aarch64-linux-android.tar.gz"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_ARCHIVE}"
PYTHON_SHA256="6d50cc3aa66e414a439594089bcdfb5f1264358155c70c1f00471c24cfb477fb"

ICONV_VERSION="1.19"
ICONV_ARCHIVE="libiconv-${ICONV_VERSION}.tar.gz"
ICONV_URL="https://ftp.gnu.org/gnu/libiconv/${ICONV_ARCHIVE}"
ICONV_SHA256="88dd96a8c0464eca144fc791ae60cd31cd8ee78321e67397e25fc095c4a19aa6"

ANDROID_API="28"
NDK_VERSION="29.0.14206865"

mkdir -p "${DOWNLOAD_DIR}" "${BUILD_DIR}" "${DEPS_DIR}/jniLibs/arm64-v8a"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

download() {
    local url="$1"
    local destination="$2"
    local expected="$3"
    if [[ ! -f "${destination}" ]]; then
        curl --fail --location --retry 3 --output "${destination}" "${url}"
    fi
    local actual
    actual="$(sha256_file "${destination}")"
    if [[ "${actual}" != "${expected}" ]]; then
        echo "SHA-256 mismatch for ${destination}" >&2
        echo "expected: ${expected}" >&2
        echo "actual:   ${actual}" >&2
        exit 1
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

resolve_host_tag() {
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) echo "linux-x86_64" ;;
        Darwin-x86_64|Darwin-arm64) echo "darwin-x86_64" ;;
        *) echo "Unsupported NDK host: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
    esac
}

download "${SDL_URL}" "${DOWNLOAD_DIR}/${SDL_ARCHIVE}" "${SDL_SHA256}"
download "${PYTHON_URL}" "${DOWNLOAD_DIR}/${PYTHON_ARCHIVE}" "${PYTHON_SHA256}"
download "${ICONV_URL}" "${DOWNLOAD_DIR}/${ICONV_ARCHIVE}" "${ICONV_SHA256}"

if [[ ! -f "${DEPS_DIR}/sdl2/.gemrb-ready-${SDL_VERSION}" ]]; then
    rm -rf "${DEPS_DIR}/sdl2" "${BUILD_DIR}/SDL2-${SDL_VERSION}"
    tar -xzf "${DOWNLOAD_DIR}/${SDL_ARCHIVE}" -C "${BUILD_DIR}"
    mv "${BUILD_DIR}/SDL2-${SDL_VERSION}" "${DEPS_DIR}/sdl2"
    touch "${DEPS_DIR}/sdl2/.gemrb-ready-${SDL_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/python/.gemrb-ready-${PYTHON_VERSION}" ]]; then
    rm -rf "${DEPS_DIR}/python" "${BUILD_DIR}/python-${PYTHON_VERSION}"
    mkdir -p "${DEPS_DIR}/python" "${BUILD_DIR}/python-${PYTHON_VERSION}"
    tar -xzf "${DOWNLOAD_DIR}/${PYTHON_ARCHIVE}" -C "${BUILD_DIR}/python-${PYTHON_VERSION}"
    python_prefix="$(find "${BUILD_DIR}/python-${PYTHON_VERSION}" -type d -name prefix -print -quit)"
    if [[ -z "${python_prefix}" ]]; then
        echo "Python Android archive does not contain a prefix directory" >&2
        exit 1
    fi
    mv "${python_prefix}" "${DEPS_DIR}/python/prefix"
    find "${DEPS_DIR}/python/prefix/lib" -maxdepth 1 -type f -name '*.so*' -exec cp -L {} "${DEPS_DIR}/jniLibs/arm64-v8a/" \;
    touch "${DEPS_DIR}/python/.gemrb-ready-${PYTHON_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/libiconv/.gemrb-ready-${ICONV_VERSION}" ]]; then
    NDK_ROOT="$(resolve_ndk)"
    HOST_TAG="$(resolve_host_tag)"
    TOOLCHAIN="${NDK_ROOT}/toolchains/llvm/prebuilt/${HOST_TAG}/bin"
    ICONV_SRC="${BUILD_DIR}/libiconv-${ICONV_VERSION}"
    ICONV_PREFIX="${DEPS_DIR}/libiconv/prefix"

    rm -rf "${DEPS_DIR}/libiconv" "${ICONV_SRC}"
    mkdir -p "${DEPS_DIR}/libiconv"
    tar -xzf "${DOWNLOAD_DIR}/${ICONV_ARCHIVE}" -C "${BUILD_DIR}"

    pushd "${ICONV_SRC}" >/dev/null
    CC="${TOOLCHAIN}/aarch64-linux-android${ANDROID_API}-clang" \
    CXX="${TOOLCHAIN}/aarch64-linux-android${ANDROID_API}-clang++" \
    AR="${TOOLCHAIN}/llvm-ar" \
    RANLIB="${TOOLCHAIN}/llvm-ranlib" \
    STRIP="${TOOLCHAIN}/llvm-strip" \
    CFLAGS="-fPIC" \
    CXXFLAGS="-fPIC" \
    ./configure \
        --host=aarch64-linux-android \
        --prefix="${ICONV_PREFIX}" \
        --disable-shared \
        --enable-static \
        --disable-nls
    make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu)"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/libiconv/.gemrb-ready-${ICONV_VERSION}"
fi

echo "Android dependencies are ready in ${DEPS_DIR}"
