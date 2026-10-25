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
import re
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
    poison = definition(effect, "int fx_set_poisoned_state(Scriptable* /*Owner*/, Actor* target, Effect* fx)")
    percentage_branch = definition(poison, "if (fx->Parameter2 == RPD_PERCENT)")
    returns_path = args.source_root / "gemrb/core/EffectQueue.h"
    returns_text = returns_path.read_text(encoding="utf-8")
    returns = "\n".join(re.findall(r"^#define FX_(?:ABORT|NOT_APPLIED|APPLIED)\s+\d+.*$", returns_text, re.MULTILINE))
    prefix = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include "opcode_params.h"
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
struct Game { uint32_t GameTime = 0; };
struct Core {
    struct { unsigned int defaultTicksPerSec = 15; } Time;
    Game game;
    Game* GetGame() { return &game; }
} coreStorage;
Core* core = &coreStorage;
@RETURNCODES@
struct Effect {
    ieDword Parameter1 = 2, Parameter2 = RPD_PERCENT, Parameter4 = 0, Parameter5 = 20;
    bool FirstApply = false;
};
'''
    poison_check = "int CheckPoisonPercentage(Actor* target, Effect* fx, int totalDamage, tick_t& timeStep) {\n" + percentage_branch + "\nreturn FX_APPLIED;\n}\n"
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
    unsigned int poisonCount = 0;
    for (int mode : {0, 1, 2}) {
        Actor actor{{mode}};
        for (ieDword frequency : {0u, 1u, 3u}) {
            uint64_t expected = uint64_t(frequency ? frequency : 1) * 15;
            if (mode == 1) expected /= 2;
            if (mode == 2) expected *= 2;
            for (unsigned int sample = 0; sample < 4; ++sample) {
                Effect effect;
                effect.Parameter4 = frequency;
                tick_t timeStep = actor.GetAdjustedTime(tick_t(frequency ? frequency : 1) * 15);
                core->game.GameTime = sample == 0 ? 0 : sample == 1 ? expected : expected + 1;
                if (sample == 3) {
                    effect.FirstApply = true;
                    effect.Parameter1 = 0;
                }
                assert(CheckPoisonPercentage(&actor, &effect, 20, timeStep) == FX_APPLIED);
                assert(timeStep == expected);
                if (effect.FirstApply) assert(effect.Parameter5 == 20 && effect.Parameter1 == 1);
                else assert(effect.Parameter5 == (sample < 2 ? 18u : 20u));
                ++poisonCount;
            }
        }
    }
    std::cout << count << " ordinary timing cases passed\n";
    std::cout << poisonCount << " ordinary poison percentage branch cases passed\n";
}
'''
    prefix = prefix.replace("@RETURNCODES@", returns)
    report = {"scope": "ordinary normal, haste and slow interval compatibility plus selected actual poison-percentage branch; actual opcode parameter and return definitions; no full engine or invalid-input execution", "sources": {str(effect_path): hashlib.sha256(effect.encode("utf-8")).hexdigest(), str(actor_path): hashlib.sha256(actor.encode("utf-8")).hexdigest(), str(returns_path): hashlib.sha256(returns_text.encode("utf-8")).hexdigest(), "opcode_params.h": hashlib.sha256((args.source_root / "gemrb/includes/opcode_params.h").read_text(encoding="utf-8").encode("utf-8")).hexdigest()}, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "variants": []}
    with tempfile.TemporaryDirectory(prefix="gemrb-periodic-") as temporary:
        directory = Path(temporary)
        for width in (32, 64):
            source = directory / f"periods{width}.cpp"
            binary = directory / f"periods{width}"
            source.write_text(prefix.replace("TICK_TYPE", f"uint{width}_t") + adjustment + "\n" + helper + "\n" + poison_check + checks, encoding="utf-8")
            command = [args.compiler, "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-I", str(args.source_root / "gemrb/includes"), str(source), "-o", str(binary)]
            subprocess.run(command, check=True, timeout=60)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=15)
            report["variants"].append({"tick_bits": width, "ordinary_cases": 90, "ordinary_poison_branch_cases": 36, "output": result.stdout.strip(), "passed": True})
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
