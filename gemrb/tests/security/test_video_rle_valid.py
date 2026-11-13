#!/usr/bin/env python3
"""Compile ordinary RLE/scaling/format flows from production method definitions.

Sprite ownership, formats and pixel reads use small stand-ins; the actual methods
and image-size helper are compiled. This is not an SDL engine or malformed-input test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def definition(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    level, ending = 1, opening + 1
    while level:
        level += (text[ending] == '{') - (text[ending] == '}')
        ending += 1
    return text[start:ending]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    names = ['gemrb/core/Video/RLE.h', 'gemrb/core/Video/Video.cpp', 'gemrb/core/Sprite2D.cpp', 'gemrb/core/Video/ImageBufferSize.h']
    sources = {name: (args.source_root / name).read_text(encoding='utf-8') for name in names}
    definitions = [definition(sources[names[0]], 'inline uint8_t* DecodeRLEData('), definition(sources[names[1]], 'Video::Video() noexcept'), definition(sources[names[1]], 'Holder<Sprite2D> Video::SpriteScaleDown('), definition(sources[names[1]], 'Color Video::SpriteGetPixelSum('), definition(sources[names[2]], 'bool Sprite2D::ConvertFormatTo(')]
    prefix = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <vector>
using namespace GemRB;
using colorkey_t = uint32_t;
struct Size { int w, h; bool IsInvalid() const { return w <= 0 || h <= 0; } };
struct Point { int x, y; Point(int x, int y) : x(x), y(y) {} };
struct Region {
    int x, y;
    Size size;
    int &w = size.w, &h = size.h;
    Region(int x, int y, int w, int h) : x(x), y(y), size{w,h} {}
    Region(const Region& other) : x(other.x), y(other.y), size(other.size) {}
};
struct Color { unsigned char r = 0, g = 0, b = 0, a = 0; };
struct PixelFormat {
    int Bpp = 1;
    bool RLE = false;
    bool palette = true;
    colorkey_t ColorKey = 0;
    PixelFormat() = default;
    PixelFormat(int bpp, uint32_t, uint32_t, uint32_t, uint32_t) : Bpp(bpp) {}
};
template<class T> using Holder = std::shared_ptr<T>;
struct Sprite2D {
    Region Frame;
    void* pixels;
    PixelFormat format;
    bool freePixels = true;
    Sprite2D(const Region& frame, void* pixels, const PixelFormat& format) : Frame(frame), pixels(pixels), format(format) {}
    ~Sprite2D() { if (freePixels) free(pixels); }
    bool ConvertFormatTo(const PixelFormat&) noexcept;
    Color GetPixel(const Point& p) const {
        assert(p.x >= 0 && p.x < Frame.w && p.y >= 0 && p.y < Frame.h);
        const uint32_t value = static_cast<uint32_t*>(pixels)[size_t(p.y) * Frame.w + p.x];
        return {uint8_t(value), uint8_t(value >> 8), uint8_t(value >> 16), uint8_t(value >> 24)};
    }
};
struct Video {
    unsigned char Gamma22toGamma10[256], Gamma10toGamma22[256];
    Video() noexcept;
    Holder<Sprite2D> CreateSprite(const Region& frame, void* pixels, const PixelFormat& format) { return std::make_shared<Sprite2D>(frame, pixels, format); }
    Holder<Sprite2D> SpriteScaleDown(const Holder<Sprite2D>& sprite, unsigned int ratio);
    Color SpriteGetPixelSum(const Holder<Sprite2D>& sprite, unsigned int xbase, unsigned int ybase, unsigned int ratio) const;
};
'''
    checks = r'''
int main() {
    struct RleCase { Size size; std::vector<uint8_t> encoded, expected; };
    const std::vector<RleCase> cases {
        {{2, 2}, {1, 0, 1, 2}, {1, 0, 0, 2}},
        {{4, 1}, {0, 3}, {0, 0, 0, 0}},
        {{4, 2}, {1, 2, 0, 3, 5, 6}, {1, 2, 0, 0, 0, 0, 5, 6}}
    };
    PixelFormat decoded;
    for (const auto& test : cases) {
        uint8_t* pixels = DecodeRLEData(test.encoded.data(), test.size, 0);
        assert(pixels && memcmp(pixels, test.expected.data(), test.expected.size()) == 0);
        free(pixels);
        auto* encoded = static_cast<uint8_t*>(malloc(test.encoded.size()));
        memcpy(encoded, test.encoded.data(), test.encoded.size());
        PixelFormat format;
        format.RLE = true;
        Sprite2D sprite(Region(0, 0, test.size.w, test.size.h), encoded, format);
        assert(sprite.ConvertFormatTo(decoded));
        assert(!sprite.format.RLE && sprite.pixels != encoded);
        assert(memcmp(sprite.pixels, test.expected.data(), test.expected.size()) == 0);
    }
    Video video;
    PixelFormat rgba(4, 0xff, 0xff00, 0xff0000, 0xff000000);
    auto* red = static_cast<uint32_t*>(malloc(12 * 12 * 4));
    std::fill_n(red, 12 * 12, 0xff0000ffu);
    auto sprite = video.CreateSprite(Region(12, 24, 12, 12), red, rgba);
    for (unsigned int ratio : {1u, 2u, 3u, 4u}) {
        const auto small = video.SpriteScaleDown(sprite, ratio);
        assert(small && small->Frame.w == 12 / int(ratio) && small->Frame.h == 12 / int(ratio));
        assert(small->Frame.x == 12 / int(ratio) && small->Frame.y == 24 / int(ratio));
        for (int y = 0; y < small->Frame.h; ++y)
            for (int x = 0; x < small->Frame.w; ++x) {
                const Color color = small->GetPixel(Point(x, y));
                assert(color.r == 255 && color.g == 0 && color.b == 0 && color.a == 255);
            }
    }
    auto* checker = static_cast<uint32_t*>(malloc(4 * 4));
    checker[0] = checker[3] = 0xffffffffu;
    checker[1] = checker[2] = 0xff000000u;
    const auto mixed = video.SpriteScaleDown(video.CreateSprite(Region(0, 0, 2, 2), checker, rgba), 2);
    assert(mixed);
    const Color color = mixed->GetPixel(Point(0, 0));
    assert(color.r == 186 && color.g == 186 && color.b == 186 && color.a == 255);
    // A valid narrow image may have more rows than the old ushort sample index.
    auto* tall = static_cast<uint32_t*>(malloc(65537 * sizeof(uint32_t)));
    std::fill_n(tall, 65537, 0xff0000ffu);
    tall[65536] = 0xff00ff00u;
    const auto tallResult = video.SpriteScaleDown(video.CreateSprite(Region(0, 0, 1, 65537), tall, rgba), 1);
    assert(tallResult && tallResult->Frame.h == 65537);
    const Color finalRow = tallResult->GetPixel(Point(0, 65536));
    assert(finalRow.r == 0 && finalRow.g == 255 && finalRow.b == 0 && finalRow.a == 255);
}
'''
    with tempfile.TemporaryDirectory(prefix='gemrb-video-rle-') as temporary:
        directory = Path(temporary)
        cpp, binary = directory / 'valid.cpp', directory / 'valid'
        cpp.write_text(sources[names[3]] + prefix + '\n'.join(definitions) + checks, encoding='utf-8')
        subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', str(cpp), '-o', str(binary)], check=True, timeout=60)
        subprocess.run([str(binary)], check=True, timeout=15)
    report = {'ordinary_cases': 12, 'passed': True, 'source_sha256': {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name,text in sources.items()}, 'scope': '3 valid RLE decodes,3 valid format conversions,4 constant-color scale factors,1 gamma-correct mixed scale,1 valid tall image preserving row65536; sprite/API stand-ins; no full SDL/engine or invalid-input execution'}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
