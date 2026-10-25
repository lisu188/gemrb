#!/usr/bin/env python3
"""Check ordinary timing compatibility using the production helper and Actor method.

Compile in a temporary directory. The small effect-queue stand-in selects normal,
haste or slow, while the adjustment method itself is extracted from Actor.cpp.
This does not execute the engine or test invalid effect data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def definition(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    ending = opening + 1
    while depth:
        depth += (text[ending] == "{") - (text[ending] == "}")
        ending += 1
    return text[start:ending]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--effect-source", type=Path)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    effect_path = args.effect_source or args.source_root / "gemrb/plugins/FXOpcodes/FXOpcodes.cpp"
    actor_path = args.source_root / "gemrb/core/Scriptable/Actor.cpp"
    effect = effect_path.read_text(encoding='utf-8')
    actor = actor_path.read_text(encoding='utf-8')
    helper = definition(effect, "static tick_t GetPeriodicEffectInterval(")
    adjustment = definition(actor, "tick_t Actor::GetAdjustedTime(tick_t time) const")
    prefix = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
using tick_t = TICK_TYPE;
using ieDword = uint32_t;
constexpr int fx_set_haste_state_ref = 1;
constexpr int fx_set_slow_state_ref = 2;
struct Queue {
    int mode;
    bool HasEffectWithParam(int, int parameter) const { return mode == 1 && parameter == 0; }
    bool HasEffect(int) const { return mode == 2; }
};
struct Actor { Queue fxqueue; tick_t GetAdjustedTime(tick_t time) const; };
struct Core { struct { unsigned int defaultTicksPerSec = 15; } Time; } coreStorage;
Core* core = &coreStorage;
'''
    checks = r'''
int main() {
    unsigned int count = 0;
    for (int mode : {0, 1, 2}) {
        Actor actor{{mode}};
        for (ieDword frequency : {0u, 1u, 2u, 3u, 60u, 1000u}) {
            for (ieDword seconds : {1u, 2u, 6u, 60u, 600u}) {
                uint64_t expected = uint64_t(frequency ? frequency : 1) * 15 * seconds;
                if (mode == 1) expected /= 2;
                if (mode == 2) expected *= 2;
                tick_t actual = GetPeriodicEffectInterval(&actor, frequency, seconds);
                assert(actual == expected && actual != 0);
                // Check due/not-due decisions for a modest range of ordinary game ticks.
                for (unsigned int now = 0; now < 300; ++now)
                    assert((now % actual == 0) == (now % expected == 0));
                ++count;
            }
        }
    }
    std::cout << count << " ordinary timing cases passed\n";
}
'''
    report = {"scope": "ordinary normal, haste and slow interval compatibility; no full engine or invalid-input execution", "sources": {str(effect_path): hashlib.sha256(effect.encode()).hexdigest(), str(actor_path): hashlib.sha256(actor.encode()).hexdigest()}, "variants": []}
    with tempfile.TemporaryDirectory(prefix="gemrb-periodic-") as temporary:
        directory = Path(temporary)
        for width in (32, 64):
            source = directory / f"periods{width}.cpp"
            binary = directory / f"periods{width}"
            source.write_text(prefix.replace("TICK_TYPE", f"uint{width}_t") + adjustment + "\n" + helper + "\n" + checks)
            command = [args.compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", str(source), "-o", str(binary)]
            subprocess.run(command, check=True, timeout=60)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=15)
            report["variants"].append({"tick_bits": width, "ordinary_cases": 90, "output": result.stdout.strip(), "passed": True})
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
