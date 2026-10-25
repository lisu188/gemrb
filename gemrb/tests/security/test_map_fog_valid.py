#!/usr/bin/env python3
"""Exercise the production fog loop with ordinary map and renderer stand-ins."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    path = args.source_root / 'gemrb/core/GUI/MapControl.cpp'
    source = path.read_text(encoding='utf-8')
    first = source.index('void MapControl::DrawFog(const Region& rgn) const')
    last = source.index('\nPoint MapControl::ConvertPointToGame', first)
    method = source[first:last]
    fixture = r'''
#include <cassert>
#include <cstddef>
#include <vector>
struct Size { int w, h; };
struct BasePoint {
    int x = 0, y = 0;
    BasePoint operator+(const BasePoint& other) const { return {x + other.x, y + other.y}; }
};
using Point = BasePoint;
struct Region { int w, h; Point origin; };
struct Map {
    bool explored = false;
    Size GetSize() const { return {120, 90}; }
    bool IsExplored(const Point&) const { return explored; }
};
constexpr int ColorBlack = 0;
struct Renderer {
    std::vector<BasePoint> captured;
    void DrawPoints(const std::vector<BasePoint>& points, int) { captured = points; }
} renderer;
Renderer* VideoDriver = &renderer;
struct MapControl {
    Map* MyMap;
    Region mosRgn;
    void DrawFog(const Region&) const;
};
'''
    checks = r'''
int main() {
    Map map;
    unsigned int cases = 0;
    for (Size dimensions : {Size{1, 1}, Size{4, 3}, Size{16, 12}, Size{40, 30}}) {
        for (Point origin : {Point{0, 0}, Point{-20, 10}}) {
            Region region{dimensions.w, dimensions.h, origin};
            MapControl control{&map, region};
            for (bool explored : {false, true}) {
                map.explored = explored;
                renderer.captured.clear();
                control.DrawFog(region);
                assert(renderer.captured.size() == (explored ? 0u : size_t(dimensions.w) * dimensions.h));
                if (!explored) {
                    size_t at = 0;
                    for (int y = 0; y < dimensions.h; ++y)
                        for (int x = 0; x < dimensions.w; ++x, ++at) {
                            assert(renderer.captured[at].x == x + origin.x);
                            assert(renderer.captured[at].y == y + origin.y);
                        }
                }
                ++cases;
            }
        }
    }
    assert(cases == 16);
}
'''
    with tempfile.TemporaryDirectory(prefix='gemrb-fog-') as temporary:
        directory = Path(temporary)
        cpp, binary = directory / 'fog.cpp', directory / 'fog'
        cpp.write_text(fixture + method + checks, encoding='utf-8')
        subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', str(cpp), '-o', str(binary)], check=True, timeout=60)
        subprocess.run([str(binary)], check=True, timeout=15)
    report = {'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'ordinary_cases': 16, 'passed': True, 'scope': 'Actual DrawFog loop with map/renderer/coordinate stand-ins; full UI, empty/invalid/large allocations and engine runtime unexecuted'}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
