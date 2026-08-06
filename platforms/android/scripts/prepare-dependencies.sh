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

FREETYPE_VERSION="2.14.3"
FREETYPE_ARCHIVE="freetype-${FREETYPE_VERSION}.tar.gz"
FREETYPE_URL="https://download.savannah.gnu.org/releases/freetype/${FREETYPE_ARCHIVE}"
FREETYPE_SHA256="e61b31ab26358b946e767ed7eb7f4bb2e507da1cfefeb7a8861ace7fd5c899a1"

PNG_VERSION="1.6.58"
PNG_ARCHIVE="libpng-${PNG_VERSION}.tar.gz"
PNG_URL="https://download.sourceforge.net/libpng/${PNG_ARCHIVE}"
PNG_SHA256="8c9b05b675ca7301a458df2c2e46f26e1d41ff36b8863f8c33530bc58c2e6225"

OGG_VERSION="1.3.6"
OGG_ARCHIVE="libogg-${OGG_VERSION}.tar.gz"
OGG_URL="https://downloads.xiph.org/releases/ogg/${OGG_ARCHIVE}"
OGG_SHA256="83e6704730683d004d20e21b8f7f55dcb3383cdf84c0daedf30bde175f774638"

VORBIS_VERSION="1.3.7"
VORBIS_ARCHIVE="libvorbis-${VORBIS_VERSION}.tar.gz"
VORBIS_URL="https://downloads.xiph.org/releases/vorbis/${VORBIS_ARCHIVE}"
VORBIS_SHA256="0e982409a9c3fc82ee06e08205b1355e5c6aa4c36bca58146ef399621b0ce5ab"

ANDROID_API="28"
NDK_VERSION="29.0.14206865"
TARGET_TRIPLE="aarch64-linux-android"

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
    local temporary="${destination}.tmp"

    if [[ -f "${destination}" ]]; then
        local cached
        cached="$(sha256_file "${destination}")"
        if [[ "${cached}" == "${expected}" ]]; then
            return
        fi
        echo "Discarding corrupt cached download: ${destination}" >&2
        rm -f "${destination}"
    fi

    rm -f "${temporary}"
    if ! curl \
        --fail \
        --location \
        --retry 8 \
        --retry-all-errors \
        --retry-delay 2 \
        --connect-timeout 20 \
        --output "${temporary}" \
        "${url}"; then
        rm -f "${temporary}"
        return 1
    fi

    local actual
    actual="$(sha256_file "${temporary}")"
    if [[ "${actual}" != "${expected}" ]]; then
        echo "SHA-256 mismatch for ${url}" >&2
        echo "expected: ${expected}" >&2
        echo "actual:   ${actual}" >&2
        rm -f "${temporary}"
        exit 1
    fi
    mv "${temporary}" "${destination}"
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

make_jobs() {
    getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu
}

download "${SDL_URL}" "${DOWNLOAD_DIR}/${SDL_ARCHIVE}" "${SDL_SHA256}"
download "${PYTHON_URL}" "${DOWNLOAD_DIR}/${PYTHON_ARCHIVE}" "${PYTHON_SHA256}"
download "${ICONV_URL}" "${DOWNLOAD_DIR}/${ICONV_ARCHIVE}" "${ICONV_SHA256}"
download "${FREETYPE_URL}" "${DOWNLOAD_DIR}/${FREETYPE_ARCHIVE}" "${FREETYPE_SHA256}"
download "${PNG_URL}" "${DOWNLOAD_DIR}/${PNG_ARCHIVE}" "${PNG_SHA256}"
download "${OGG_URL}" "${DOWNLOAD_DIR}/${OGG_ARCHIVE}" "${OGG_SHA256}"
download "${VORBIS_URL}" "${DOWNLOAD_DIR}/${VORBIS_ARCHIVE}" "${VORBIS_SHA256}"

NDK_ROOT="$(resolve_ndk)"
HOST_TAG="$(resolve_host_tag)"
TOOLCHAIN="${NDK_ROOT}/toolchains/llvm/prebuilt/${HOST_TAG}/bin"
CC="${TOOLCHAIN}/${TARGET_TRIPLE}${ANDROID_API}-clang"
CXX="${TOOLCHAIN}/${TARGET_TRIPLE}${ANDROID_API}-clang++"
AR="${TOOLCHAIN}/llvm-ar"
RANLIB="${TOOLCHAIN}/llvm-ranlib"
STRIP="${TOOLCHAIN}/llvm-strip"
JOBS="$(make_jobs)"

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
    ICONV_SRC="${BUILD_DIR}/libiconv-${ICONV_VERSION}"
    ICONV_PREFIX="${DEPS_DIR}/libiconv/prefix"

    rm -rf "${DEPS_DIR}/libiconv" "${ICONV_SRC}"
    mkdir -p "${DEPS_DIR}/libiconv"
    tar -xzf "${DOWNLOAD_DIR}/${ICONV_ARCHIVE}" -C "${BUILD_DIR}"

    pushd "${ICONV_SRC}" >/dev/null
    CC="${CC}" CXX="${CXX}" AR="${AR}" RANLIB="${RANLIB}" STRIP="${STRIP}" \
    CFLAGS="-fPIC" CXXFLAGS="-fPIC" \
    ./configure \
        --host="${TARGET_TRIPLE}" \
        --prefix="${ICONV_PREFIX}" \
        --disable-shared \
        --enable-static \
        --disable-nls
    make -j"${JOBS}"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/libiconv/.gemrb-ready-${ICONV_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/freetype/.gemrb-ready-${FREETYPE_VERSION}" ]]; then
    FREETYPE_SRC="${BUILD_DIR}/freetype-${FREETYPE_VERSION}"
    FREETYPE_PREFIX="${DEPS_DIR}/freetype/prefix"

    rm -rf "${DEPS_DIR}/freetype" "${FREETYPE_SRC}"
    tar -xzf "${DOWNLOAD_DIR}/${FREETYPE_ARCHIVE}" -C "${BUILD_DIR}"
    pushd "${FREETYPE_SRC}" >/dev/null
    CC="${CC}" CXX="${CXX}" AR="${AR}" RANLIB="${RANLIB}" STRIP="${STRIP}" \
    CFLAGS="-fPIC" CXXFLAGS="-fPIC" \
    ./configure \
        --host="${TARGET_TRIPLE}" \
        --prefix="${FREETYPE_PREFIX}" \
        --disable-shared \
        --enable-static \
        --without-zlib \
        --without-bzip2 \
        --without-png \
        --without-harfbuzz \
        --without-brotli
    make -j"${JOBS}"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/freetype/.gemrb-ready-${FREETYPE_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/libpng/.gemrb-ready-${PNG_VERSION}" ]]; then
    PNG_SRC="${BUILD_DIR}/libpng-${PNG_VERSION}"
    PNG_PREFIX="${DEPS_DIR}/libpng/prefix"

    rm -rf "${DEPS_DIR}/libpng" "${PNG_SRC}"
    tar -xzf "${DOWNLOAD_DIR}/${PNG_ARCHIVE}" -C "${BUILD_DIR}"
    pushd "${PNG_SRC}" >/dev/null
    CC="${CC}" CXX="${CXX}" AR="${AR}" RANLIB="${RANLIB}" STRIP="${STRIP}" \
    CFLAGS="-fPIC" CXXFLAGS="-fPIC" LIBS="-lz" \
    ./configure \
        --host="${TARGET_TRIPLE}" \
        --prefix="${PNG_PREFIX}" \
        --disable-shared \
        --enable-static
    make -j"${JOBS}"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/libpng/.gemrb-ready-${PNG_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/libogg/.gemrb-ready-${OGG_VERSION}" ]]; then
    OGG_SRC="${BUILD_DIR}/libogg-${OGG_VERSION}"
    OGG_PREFIX="${DEPS_DIR}/libogg/prefix"

    rm -rf "${DEPS_DIR}/libogg" "${OGG_SRC}"
    tar -xzf "${DOWNLOAD_DIR}/${OGG_ARCHIVE}" -C "${BUILD_DIR}"
    pushd "${OGG_SRC}" >/dev/null
    CC="${CC}" CXX="${CXX}" AR="${AR}" RANLIB="${RANLIB}" STRIP="${STRIP}" \
    CFLAGS="-fPIC" CXXFLAGS="-fPIC" \
    ./configure \
        --host="${TARGET_TRIPLE}" \
        --prefix="${OGG_PREFIX}" \
        --disable-shared \
        --enable-static
    make -j"${JOBS}"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/libogg/.gemrb-ready-${OGG_VERSION}"
fi

if [[ ! -f "${DEPS_DIR}/libvorbis/.gemrb-ready-${VORBIS_VERSION}" ]]; then
    VORBIS_SRC="${BUILD_DIR}/libvorbis-${VORBIS_VERSION}"
    VORBIS_PREFIX="${DEPS_DIR}/libvorbis/prefix"
    OGG_PREFIX="${DEPS_DIR}/libogg/prefix"

    rm -rf "${DEPS_DIR}/libvorbis" "${VORBIS_SRC}"
    tar -xzf "${DOWNLOAD_DIR}/${VORBIS_ARCHIVE}" -C "${BUILD_DIR}"
    pushd "${VORBIS_SRC}" >/dev/null
    CC="${CC}" CXX="${CXX}" AR="${AR}" RANLIB="${RANLIB}" STRIP="${STRIP}" \
    CFLAGS="-fPIC" CXXFLAGS="-fPIC" \
    CPPFLAGS="-I${OGG_PREFIX}/include" \
    LDFLAGS="-L${OGG_PREFIX}/lib" \
    PKG_CONFIG_PATH="${OGG_PREFIX}/lib/pkgconfig" \
    ./configure \
        --host="${TARGET_TRIPLE}" \
        --prefix="${VORBIS_PREFIX}" \
        --disable-shared \
        --enable-static
    make -j"${JOBS}"
    make install
    popd >/dev/null
    touch "${DEPS_DIR}/libvorbis/.gemrb-ready-${VORBIS_VERSION}"
fi

echo "Android dependencies are ready in ${DEPS_DIR}"
