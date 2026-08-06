#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOWNLOAD_DIR="${ANDROID_DIR}/.deps/downloads"

FREETYPE_VERSION="2.14.3"
FREETYPE_ARCHIVE="freetype-${FREETYPE_VERSION}.tar.gz"
FREETYPE_URL="https://sourceforge.net/projects/freetype/files/freetype2/${FREETYPE_VERSION}/${FREETYPE_ARCHIVE}/download"
FREETYPE_SHA256="e61b31ab26358b946e767ed7eb7f4bb2e507da1cfefeb7a8861ace7fd5c899a1"

mkdir -p "${DOWNLOAD_DIR}"
destination="${DOWNLOAD_DIR}/${FREETYPE_ARCHIVE}"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

if [[ -f "${destination}" ]] && [[ "$(sha256_file "${destination}")" == "${FREETYPE_SHA256}" ]]; then
    exit 0
fi

rm -f "${destination}"
curl --fail --location --retry 5 --retry-all-errors --output "${destination}" "${FREETYPE_URL}"
actual="$(sha256_file "${destination}")"
if [[ "${actual}" != "${FREETYPE_SHA256}" ]]; then
    echo "SHA-256 mismatch for ${destination}" >&2
    echo "expected: ${FREETYPE_SHA256}" >&2
    echo "actual:   ${actual}" >&2
    exit 1
fi
