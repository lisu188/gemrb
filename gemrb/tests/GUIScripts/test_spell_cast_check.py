#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile the real cast dispatch/check bodies with controlled engine boundaries.

This exercises Python reference ownership and exception conversion with CPython,
and actual actor/point/instant dispatch, without requiring proprietary game data.
It is not a replacement for the full engine build or live spell-casting tests.
"""

from pathlib import Path
import os
import subprocess
import unittest

from native_harness import run_tests


ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


BOUNDARIES = r'''
#include <Python.h>
#include <cassert>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
using ieDword = unsigned int;
using StringView = std::string;
struct ResRef : std::string {
    using std::string::string;
    ResRef(const std::string& text) : std::string(text) {}
    bool IsEmpty() const { return empty(); }
    void Reset() { clear(); }
    void Format(const char*, const StringView& prefix, int number) {
        std::ostringstream text;
        text << prefix << std::setfill('0') << std::setw(3) << number;
        assign(text.str());
    }
};
using String = std::string;
template<class T> using Holder = std::shared_ptr<T>;
constexpr int GA_POINT=1, GA_NO_DEAD=2, GA_NO_HIDDEN=4, GA_NO_UNSCHEDULED=8;
constexpr int UI_SILENT=1, UI_NOAURA=2, UI_NOCHARGE=4;
enum class TargetMode { None, Cast };
namespace SpecialSpell { constexpr int AreaTarget=1; }
constexpr int TARGET_INVALID=0, TARGET_SELF=1, TARGET_NONE=2, TARGET_AREA=3,
              TARGET_CREA=4, TARGET_DEAD=5, TARGET_INV=6;
constexpr int MESSAGE=0, ERROR=1, WARNING=2;
constexpr int SC_NO_DEAD=1, SC_RANGE_CHECK=2, SC_DEPLETE=4, SC_SETLEVEL=8,
              SC_INSTANT=16, SC_AURA_CHECK=32, SC_NOINTERRUPT=64;
constexpr int ST_ACTOR=1, ST_DOOR=2, IE_STATE_ID=0, IE_AVATARREMOVAL=1;
constexpr int STATE_DEAD=1, IF_ACTIVE=1, IF_VISIBLE=2;
constexpr int SF_TARGETS_INVISIBLE=1, SF_NO_LOS=2, IE_ANI_READY=0;
namespace AUTOPAUSE { constexpr int NOTARGET=0; }
namespace GFFlags { constexpr int RULES_3ED=0; }
enum class Modal { None };
namespace MNT { constexpr int FinalDistance=0; }
namespace HCStrings { constexpr int NoSeeNoCast=0; }
namespace GUIColors { constexpr int RED=0; }
namespace fmt { struct WideToChar { String value; }; }
template<class... T> void Log(T...) {}
struct Point { int x=0, y=0; bool IsInvalid() const { return false; } };
struct Action {
    inline static int live = 0;
    Action() { ++live; }
    ~Action() { --live; }
    ResRef resref0Parameter;
    Point pointParameter;
    int int0Parameter=0, int1Parameter=0, int2Parameter=0, actionID=0;
};
struct Actor;
using SearchmapPoint = Point;
struct Map {
    bool visible=true;
    bool IsVisibleLOS(const Point&, const Point&, const Actor*) const { return visible; }
} area;
struct Scriptable {
    int Type=ST_ACTOR, CurrentActionTicks=0, CurrentActionState=0, SpellHeader=-1;
    bool CurrentActionInterruptible=true, aura=false;
    unsigned id=4242;
    Point Pos, SMPos;
    ResRef SpellResRef;
    Action* CurrentAction=nullptr;
    struct { unsigned LastMarkedSpell=0, LastSpellTarget=0; Point LastTargetPos; } objects;
    template<class T> static T* As(Scriptable* sender) {
        return sender && sender->Type==ST_ACTOR ? static_cast<T*>(sender) : nullptr;
    }
    unsigned GetGlobalID() const { return id; }
    unsigned GetInternalFlag() const { return IF_ACTIVE | IF_VISIBLE; }
    Map* GetCurrentArea() const { return &area; }
    bool AuraPolluted() const { return aura; }
    void SetSpellResRef(const ResRef& spell) { SpellResRef=spell; }
    void ReleaseCurrentAction() { CurrentAction=nullptr; CurrentActionTicks=CurrentActionState=0; }
    void AddTrigger(int) {}
    int CastSpell(Scriptable*, bool, bool, bool, int);
    int CastSpellPoint(const Point&, bool, bool, bool, int);
    void CastSpellEnd(int, bool);
    void CastSpellPointEnd(int, bool);
};
struct CREMemorizedSpell { ResRef SpellResRef="actual"; };
struct SpellExtHeader {
    ResRef spellName="selected";
    int Target=TARGET_SELF, TargetNumber=1, type=0, level=0, slot=0, strref=0, Range=0;
};
struct Spellbook {
    CREMemorizedSpell memorized;
    SpellExtHeader info;
    bool present=true;
    int cleared=0;
    const CREMemorizedSpell* GetMemorizedSpell(int, int, int) const {
        return present ? &memorized : nullptr;
    }
    void ClearSpellInfo() { ++cleared; }
    void SetCustomSpellInfo(const std::vector<ResRef>& spells, const ResRef&, int) {
        if (!spells.empty()) { info.spellName=spells[0]; info.slot=-1; }
    }
    void GetSpellInfo(SpellExtHeader& out, int, int) const { out=info; }
    void FindSpellInfo(SpellExtHeader& out, const ResRef&, int) const { out=info; }
};
struct PCStatsType { ResRef QuickSpells[1]; int QuickSpellBookType[1]={1}; };
struct Actor : Scriptable {
    unsigned int InParty=1;
    Spellbook spellbook;
    PCStatsType* PCStats=nullptr;
    bool untargetable=false;
    bool immobile=false, moving=false;
    std::vector<Holder<Action>> actions;
    bool Immobile() const { return immobile; }
    bool InMove() const { return moving; }
    int GetStat(int) const { return 0; }
    bool IsInvisibleTo(const Scriptable*, int) const { return false; }
    void SetStance(int) {}
    void SetOrientation(const Point&, const Point&, bool) {}
    void SetModal(Modal) {}
    bool Untargetable(const ResRef&, const Actor*) const { return untargetable; }
    void Stop() {}
    void AddAction(Action* action) { actions.emplace_back(action); }
};
static Action* GenerateAction(std::string) { return new Action; }
static Action* GenerateActionDirect(std::string, const Actor*) { return new Action; }
struct Display {
    void DisplayConstantStringName(int, int, Scriptable*) {}
} displayStorage;
Display* displaymsg=&displayStorage;
struct Spell { unsigned Flags=0; int header=0, duration=2; };
struct GameData {
    std::map<std::string, Spell> spells{{"base", {}}, {"SPWI101", {}}, {"variant", {0, 2, 2}}};
    int loads=0, releases=0;
    int GetSpecialSpell(const ResRef&) const { return 0; }
    bool Exists(const ResRef& name, int) const { return name=="broken" || spells.count(name); }
    const Spell* GetSpell(const ResRef& name, bool=false) {
        ++loads;
        auto spell=spells.find(name);
        return spell==spells.end() ? nullptr : &spell->second;
    }
    void FreeSpell(const Spell*, const ResRef&, bool) { ++releases; }
} gameDataStorage;
constexpr int IE_SPL_CLASS_ID=0;
GameData* gamedata=&gameDataStorage;
struct GameControl {
    std::function<bool(ieDword, const ResRef&)> spellCastCheck;
    std::function<bool(ieDword, const ResRef&, ResRef&)> nonPartySpellCastCheck;
    ResRef spellName="prepared";
    int spellOrItem=0, spellSlot=0, spellIndex=0, spellCount=1, targetTypes=GA_POINT;
    TargetMode targetMode=TargetMode::Cast;
    void SetSpellCastCheck(std::function<bool(ieDword, const ResRef&)>);
    bool CheckSpellCast(const Actor*, const ResRef&) const;
    void SetNonPartySpellCastCheck(std::function<bool(ieDword, const ResRef&, ResRef&)>);
    bool CheckNonPartySpellCast(const Actor*, ResRef&) const;
    void TryToCast(Actor*, const Point&);
    void TryToCast(Actor*, const Actor*);
    void ResetTargetMode();
    void SetTargetMode(TargetMode mode) { targetMode=mode; } // omit cursor rendering only
    void DispatchGround(Actor* selectedActor, const Point& p);
    void SetupCasting(const ResRef& name, int type, int level, int index, int targets, int count) {
        spellName=name; spellOrItem=type; spellSlot=level; spellIndex=index;
        targetTypes=targets; spellCount=count; SetTargetMode(TargetMode::Cast);
    }
};
Actor caster;
GameControl control;
struct Dictionary { int Get(const char*, int fallback) const { return fallback; } };
struct Core {
    int applied=0;
    ResRef appliedSpell;
    bool third=false;
    bool HasFeature(int) const { return third; }
    GameControl* GetGameControl() const { return &control; }
    void Autopause(int, Scriptable*) {}
    Dictionary GetDictionary() const { return {}; }
    String GetString(int) const { return {}; }
    void ApplySpell(const ResRef& spell, Actor*, Actor*, int) { ++applied; appliedSpell=spell; }
} coreStorage;
Core* core=&coreStorage;
#define PARSE_ARGS(args, ...) if (!PyArg_ParseTuple(args, __VA_ARGS__)) return nullptr
#define GET_GAME()
#define GET_ACTOR_GLOBAL() Actor* actor=&caster
#define GET_GAMECONTROL() GameControl* gc=&control
static PyObject* RuntimeError(const char* message) {
    PyErr_SetString(PyExc_RuntimeError, message);
    return nullptr;
}
static ResRef ResRefFromPy(PyObject* value) {
    // Match the production strict ASCII conversion, including its error state.
    PyObject* encoded=PyUnicode_AsEncodedString(value,"ascii","strict");
    if (!encoded) return {};
    ResRef result(PyBytes_AsString(encoded));
    Py_DECREF(encoded);
    return result;
}
static unsigned distanceToTarget=0;
static Actor victim;
static bool interrupted=false;
static unsigned GetSpellDistance(const ResRef&, Scriptable*, const Point& = {}) { return 10; }
static unsigned PersonalDistance(const Scriptable*, const Scriptable*) { return distanceToTarget; }
static unsigned PersonalDistance(const Point&, const Scriptable*) { return distanceToTarget; }
template<class... T> static void MoveNearerTo(T...) {}
static Scriptable* GetStoredActorFromObject(Scriptable*, Action*, int) { return &victim; }
static int TriggerEntry(int, unsigned) { return 0; }
constexpr int trigger_targetunreachable=0;
static bool InterruptSpellcasting(Scriptable*) { return interrupted; }
struct CastRecord { ResRef spell; int header, level; bool point, deplete; };
static std::vector<CastRecord> started, finished;
int Scriptable::CastSpell(Scriptable* target, bool deplete, bool instant, bool, int level) {
    const Spell* spell=gamedata->GetSpell(SpellResRef);
    assert(spell); // forced casts rely on the acceptance boundary validating this
    SpellHeader=spell->header;
    objects.LastSpellTarget=target->GetGlobalID();
    started.push_back({SpellResRef, SpellHeader, level, false, deplete});
    int duration=instant ? 0 : spell->duration;
    gamedata->FreeSpell(spell, SpellResRef, false);
    return duration;
}
int Scriptable::CastSpellPoint(const Point&, bool deplete, bool instant, bool noInterrupt, int level) {
    int duration=CastSpell(&victim,deplete,instant,noInterrupt,level);
    objects.LastSpellTarget=0;
    started.back().point=true;
    return duration;
}
void Scriptable::CastSpellEnd(int level, bool) {
    finished.push_back({SpellResRef, SpellHeader, level, false, false});
    SpellResRef.Reset();
}
void Scriptable::CastSpellPointEnd(int level, bool keepStance) {
    CastSpellEnd(level, keepStance);
    finished.back().point=true;
}
'''


SCENARIOS = r'''
PyObject* globals;
static void runPython(const char* code) {
    PyObject* result=PyRun_String(code, Py_file_input, globals, globals);
    if (!result) PyErr_Print();
    assert(result); Py_DECREF(result);
}
static void install(const char* body) {
    runPython(body);
    PyObject* args=PyTuple_Pack(1, PyDict_GetItemString(globals, "check"));
    PyObject* result=GemRB_SetSpellCastCheck(nullptr, args);
    assert(result); Py_DECREF(result); Py_DECREF(args);
}
static void installNonParty(const char* body) {
    runPython(body);
    PyObject* args=PyTuple_Pack(1, PyDict_GetItemString(globals, "check"));
    PyObject* result=GemRB_SetNonPartySpellCastCheck(nullptr, args);
    assert(result); Py_DECREF(result); Py_DECREF(args);
}
static int calls() { return PyList_Size(PyDict_GetItemString(globals, "events")); }
static void cast(int target, int type=1) {
    caster.spellbook.info.Target=target;
    PyObject* args=type==-3 ? Py_BuildValue("(iiis)",1,type,0,"variant") : Py_BuildValue("(iii)", 1, type, 0);
    PyObject* result=GemRB_SpellCast(nullptr, args);
    assert(result); Py_DECREF(result); Py_DECREF(args);
}
const char* allow="events=[]\ndef check(actor, spell):\n events.append((actor,spell)); return True\n";
const char* veto="events=[]\ndef check(actor, spell):\n events.append((actor,spell)); return False\n";
static void checkEvents(const char* expected) {
    PyObject* result=PyRun_String(expected, Py_eval_input, globals, globals);
    assert(result && PyObject_IsTrue(result)); Py_DECREF(result);
}
static void scriptCast(bool point, Action& action, int flags) {
    if (point) SpellPointCore(&caster,&action,flags);
    else SpellCore(&caster,&action,flags);
}
static void finishCast(bool point, Action& action, int flags) {
    for (int tick=0; caster.CurrentAction && tick<8; ++tick) {
        ++caster.CurrentActionTicks;
        scriptCast(point,action,flags);
    }
    assert(!caster.CurrentAction);
}
static void scriptScenario(const std::string& test) {
    caster.InParty=0;
    victim.id=43;
    const bool point=test.find("point")!=std::string::npos;
    const bool marked=test.find("marked")!=std::string::npos;
    const bool numeric=marked || test.find("numeric")!=std::string::npos;
    const bool instant=test.find("instant")!=std::string::npos;
    const bool pending=test.find("pending")!=std::string::npos;
    const bool native=test.find("native")!=std::string::npos;
    const bool party=test.find("party")!=std::string::npos;
    const bool invalid=test.find("invalid")!=std::string::npos;
    const bool vetoed=test.find("veto")!=std::string::npos;
    core->third=marked; // SpellCore caches this for each process, like the real engine
    if (!native) {
        installNonParty(invalid
            ? "events=[]\ndef check(actor,spell):\n events.append((actor,spell)); return 'missing'\n"
            : vetoed ? veto
            : "events=[]\ndef check(actor,spell):\n events.append((actor,spell)); return 'variant'\n");
    }
    if (party) caster.InParty=1;
    Action action;
    action.resref0Parameter=numeric ? "" : "SPWI101";
    action.int0Parameter=numeric ? (marked ? 0 : 2101) : 7;
    action.int1Parameter=11;
    const ResRef originalResource=action.resref0Parameter;
    const int originalNumber=action.int0Parameter;
    const int expectedLevel=numeric ? 11 : 7;
    const int flags=SC_SETLEVEL | SC_NOINTERRUPT | SC_RANGE_CHECK | SC_AURA_CHECK |
        (instant ? SC_INSTANT : 0);
    caster.objects.LastMarkedSpell=2101;
    caster.CurrentAction=&action;
    if (pending) {
        distanceToTarget=100;
        scriptCast(point,action,flags);
        assert(calls()==0 && started.empty());
        ++caster.CurrentActionTicks;
        distanceToTarget=0;
        area.visible=false;
        scriptCast(point,action,flags);
        assert(calls()==0 && started.empty());
        ++caster.CurrentActionTicks;
        area.visible=true;
        caster.aura=true;
        scriptCast(point,action,flags);
        assert(calls()==0 && started.empty());
        ++caster.CurrentActionTicks;
        caster.aura=false;
    }
    scriptCast(point,action,flags);
    if (invalid || vetoed) {
        assert(!caster.CurrentAction && started.empty() && finished.empty());
        assert(calls()==1);
        return;
    }
    const ResRef expected=native || party ? "SPWI101" : "variant";
    assert(started.size()==1 && started.back().spell==expected);
    assert(started.back().level==expectedLevel && started.back().point==point);
    if (marked) caster.objects.LastMarkedSpell=0; // accepted casts must not re-read a new mark
    finishCast(point,action,flags);
    assert(finished.size()==1 && finished.back().spell==expected);
    assert(finished.back().header==started.back().header && finished.back().level==expectedLevel);
    assert(finished.back().point==point);
    if (!native) {
        assert(calls()==(party ? 0 : 1));
        if (!party) checkEvents("events == [(4242,'SPWI101')]");
    }
    // Scripts retain their Action objects. Reuse the exact same object with
    // a different callback result and verify it still starts from the original.
    assert(action.resref0Parameter==originalResource && action.int0Parameter==originalNumber);
    assert(action.int1Parameter==11);
    control.SetNonPartySpellCastCheck(nullptr);
    caster.objects.LastMarkedSpell=2101;
    caster.CurrentAction=&action;
    scriptCast(point,action,flags);
    finishCast(point,action,flags);
    assert(started.size()==2 && finished.size()==2);
    assert(started.back().spell=="SPWI101" && finished.back().spell=="SPWI101");
    assert(started.back().level==expectedLevel && finished.back().level==expectedLevel);
}
int main(int argc, char** argv) {
    assert(argc==2);
    Py_Initialize();
    globals=PyModule_GetDict(PyImport_AddModule("__main__"));
    const std::string test=argv[1];
    if (test.rfind("script_",0)==0) {
        scriptScenario(test);
    } else if (test=="unchanged") {
        cast(TARGET_SELF); assert(caster.actions.size()==1);
        cast(TARGET_NONE); assert(core->applied==1);
        cast(TARGET_AREA); assert(caster.actions.size()==1);
        control.TryToCast(&caster, Point{}); assert(caster.actions.size()==2);
    } else if (test=="accepted") {
        install(allow);
        cast(TARGET_NONE); assert(core->applied==1 && calls()==1);
        assert(core->appliedSpell=="selected");
        cast(TARGET_SELF); assert(caster.actions.size()==1 && calls()==2);
        for (int target : {TARGET_CREA, TARGET_DEAD, TARGET_AREA}) {
            cast(target); int before=calls();
            if (target==TARGET_AREA) control.TryToCast(&caster, Point{});
            else { Actor victim; control.TryToCast(&caster, &victim); }
            assert(calls()==before+1);
        }
        assert(caster.actions.size()==4);
        checkEvents("events == [(1,'selected')] + [(1,'actual')]*4");
    } else if (test=="direct_substitution") {
        install(allow);
        caster.spellbook.present=false;
        cast(TARGET_SELF,-3); cast(TARGET_NONE,-3); cast(TARGET_AREA,-3);
        control.TryToCast(&caster,Point{});
        assert(caster.actions.size()==2 && core->applied==1);
        assert(caster.actions[0]->resref0Parameter=="variant");
        assert(caster.actions[1]->resref0Parameter=="variant");
        assert(core->appliedSpell=="variant");
        checkEvents("events == [(1,'variant')]*3");
    } else if (test=="veto") {
        install(veto);
        for (int target : {TARGET_NONE,TARGET_SELF,TARGET_CREA,TARGET_AREA}) {
            cast(target);
            if (target==TARGET_CREA) { Actor victim; control.TryToCast(&caster,&victim); }
            if (target==TARGET_AREA) control.TryToCast(&caster, Point{});
            assert(control.targetMode==TargetMode::None);
        }
        assert(calls()==4 && core->applied==0 && caster.actions.empty());
    } else if (test=="not_accepted") {
        install(allow);
        cast(TARGET_AREA); control.ResetTargetMode();
        assert(control.spellCount==1 && control.targetMode==TargetMode::None);
        control.DispatchGround(&caster,Point{}); // actual accepted-cast dispatch guard
        cast(TARGET_CREA); Actor victim; victim.untargetable=true;
        control.TryToCast(&caster,&victim);
        cast(TARGET_CREA); control.TryToCast(&caster,Point{}); // wrong target kind
        caster.spellbook.present=false;
        cast(TARGET_SELF); cast(TARGET_AREA); control.TryToCast(&caster,Point{});
        cast(TARGET_INV); cast(TARGET_INVALID); cast(TARGET_SELF,-1);
        assert(calls()==0 && core->applied==0 && caster.actions.empty());
        assert(caster.spellbook.cleared==1);
    } else if (test=="multitarget_veto") {
        install(veto);
        caster.spellbook.info.TargetNumber=2;
        cast(TARGET_AREA);
        control.DispatchGround(&caster,Point{});
        assert(calls()==1 && caster.actions.empty());
        // Native reset changes the cursor/mode, not the remaining target count.
        assert(control.spellCount==1 && control.targetMode==TargetMode::None);
        control.DispatchGround(&caster,Point{});
        assert(calls()==1 && caster.actions.empty());
    } else if (test=="items") {
        install(veto);
        for (bool point : {false,true}) {
            control.spellOrItem=-1; control.spellCount=1;
            control.targetTypes=GA_POINT; control.SetTargetMode(TargetMode::Cast);
            if (point) control.TryToCast(&caster,Point{});
            else control.TryToCast(&caster,&caster);
        }
        assert(calls()==0 && caster.actions.size()==2);
    } else if (test=="identity_and_targets") {
        install(allow);
        caster.InParty=0;
        control.spellIndex=-1; control.spellCount=2;
        control.TryToCast(&caster,Point{});
        assert(control.spellCount==1);
        control.TryToCast(&caster,Point{});
        assert(control.spellCount==0 && caster.actions.size()==2);
        checkEvents("events == [(4242,'prepared')]*2");
    } else if (test=="exceptions") {
        install("def check(*args): raise RuntimeError('callback veto')\n");
        cast(TARGET_NONE); cast(TARGET_SELF);
        assert(!PyErr_Occurred() && core->applied==0 && caster.actions.empty());
        install("class BadBool:\n def __bool__(self): raise RuntimeError('truth veto')\ndef check(*args): return BadBool()\n");
        cast(TARGET_AREA); control.TryToCast(&caster,Point{});
        assert(!PyErr_Occurred() && caster.actions.empty());
    } else if (test=="nonparty_substitution") {
        caster.InParty=0;
        installNonParty("events=[]\ndef check(actor,spell):\n events.append((actor,spell)); return 'variant'\n");
        ResRef spell="base";
        const int loads=gamedata->loads, releases=gamedata->releases;
        assert(control.CheckNonPartySpellCast(&caster, spell));
        assert(spell=="variant");
        assert(gamedata->loads==loads+1 && gamedata->releases==releases+1);
        checkEvents("events == [(4242,'base')]");
        caster.InParty=1;
        spell="party";
        assert(control.CheckNonPartySpellCast(&caster, spell));
        assert(spell=="party" && calls()==1);
    } else if (test=="nonparty_veto") {
        caster.InParty=0;
        installNonParty("events=[]\ndef check(actor,spell):\n events.append((actor,spell)); return False\n");
        ResRef spell="base";
        assert(!control.CheckNonPartySpellCast(&caster, spell));
        assert(spell=="base" && calls()==1);
        installNonParty("def check(*args): raise RuntimeError('npc veto')\n");
        assert(!control.CheckNonPartySpellCast(&caster, spell));
        assert(!PyErr_Occurred());
        installNonParty("class BadBool:\n def __bool__(self): raise RuntimeError('npc truth veto')\ndef check(*args): return BadBool()\n");
        assert(!control.CheckNonPartySpellCast(&caster, spell));
        assert(!PyErr_Occurred());
    } else if (test=="nonparty_results") {
        caster.InParty=0;
        installNonParty(allow);
        ResRef spell="base";
        const int loads=gamedata->loads;
        assert(control.CheckNonPartySpellCast(&caster,spell) && spell=="base");
        assert(calls()==1 && gamedata->loads==loads);
        installNonParty("def check(actor,spell): return None\n");
        assert(!control.CheckNonPartySpellCast(&caster,spell) && spell=="base");
        assert(!PyErr_Occurred());
    } else if (test=="nonparty_invalid") {
        caster.InParty=0;
        for (const char* result : {"''", "'missing'", "'broken'", "'\\u2603'"}) {
            std::string callback="def check(actor,spell): return ";
            installNonParty((callback+result+"\n").c_str());
            ResRef spell="base";
            assert(!control.CheckNonPartySpellCast(&caster,spell));
            assert(spell=="base" && !PyErr_Occurred());
        }
        // Native callbacks have the same boundary: failed candidates must not
        // escape to forced casts that omit CanCast's resource checks.
        control.SetNonPartySpellCastCheck([](ieDword,const ResRef&,ResRef& out) {
            out="missing"; return true;
        });
        ResRef spell="base";
        assert(!control.CheckNonPartySpellCast(&caster,spell) && spell=="base");
        control.SetNonPartySpellCastCheck([](ieDword,const ResRef&,ResRef& out) {
            out="variant"; return false;
        });
        assert(!control.CheckNonPartySpellCast(&caster,spell) && spell=="base");
        control.SetNonPartySpellCastCheck([](ieDword,const ResRef&,ResRef& out) {
            out.Reset(); return true;
        });
        assert(!control.CheckNonPartySpellCast(&caster,spell) && spell=="base");
    } else if (test=="lifetime") {
        install(allow);
        PyObject* callback=PyDict_GetItemString(globals,"check");
        const Py_ssize_t installedRefs=Py_REFCNT(callback);
        control.SetSpellCastCheck(nullptr);
        assert(Py_REFCNT(callback)==installedRefs-1);
        {
            GameControl temporary;
            temporary.SetSpellCastCheck(PythonSpellCastCheck(callback));
            assert(Py_REFCNT(callback)==installedRefs);
        }
        assert(Py_REFCNT(callback)==installedRefs-1);
        static PyMethodDef clear={"clear_check", GemRB_SetSpellCastCheck, METH_VARARGS, nullptr};
        PyObject* method=PyCFunction_New(&clear,nullptr);
        PyDict_SetItemString(globals,"clear_check",method); Py_DECREF(method);
        install("def check(*args):\n clear_check(None)\n return True\n");
        cast(TARGET_SELF); cast(TARGET_NONE);
        assert(caster.actions.size()==1 && core->applied==1 && !control.spellCastCheck);
        PyObject* args=Py_BuildValue("(i)",7);
        assert(GemRB_SetSpellCastCheck(nullptr,args)==nullptr && PyErr_Occurred());
        Py_DECREF(args); PyErr_Clear();
    } else { assert(false); }
    caster.actions.clear();
    assert(Action::live == 0); // vetoes and invalid targets must release unqueued actions
    control.SetSpellCastCheck(nullptr); // release Python state before finalization
    control.SetNonPartySpellCastCheck(nullptr);
    Py_Finalize();
    std::cout << test << " passed\n";
}
'''


def generate_harness():
    game_control = (ROOT / "core/GUI/GameControl.cpp").read_text()
    gui_script = (ROOT / "plugins/GUIScript/GUIScript.cpp").read_text()
    callbacks = (ROOT / "plugins/GUIScript/PythonCallbacks.h").read_text()
    scripts = (ROOT / "core/GameScript/GSUtils.cpp").read_text()
    pieces = [BOUNDARIES]
    # Keep the production CPython ownership/error handling, not a fake callback.
    pieces.append(callbacks[callbacks.index("template<typename R>"):callbacks.index("template<class R, class ARG_T>")])
    for signature in (
        "void GameControl::SetSpellCastCheck(",
        "bool GameControl::CheckSpellCast(",
        "void GameControl::SetNonPartySpellCastCheck(",
        "bool GameControl::CheckNonPartySpellCast(",
        "void GameControl::ResetTargetMode(",
        "void GameControl::TryToCast(Actor* source, const Point&",
        "void GameControl::TryToCast(Actor* source, const Actor*",
    ):
        pieces.append(function(game_control, signature))
    # Compile the exact ground-cast branch of the real input dispatcher.
    # Actor lookup and unrelated door/travel branches remain boundaries;
    # cancellation must be proved by this mode guard, not a fake count reset.
    dispatch = function(game_control, "void GameControl::PerformSelectedAction(")
    ground_cast = function(dispatch, "if (targetMode == TargetMode::Cast && !(gamedata->GetSpecialSpell")
    pieces.append("void GameControl::DispatchGround(Actor* selectedActor, const Point& p) {\n" + ground_cast + "\n}")
    pieces.append(function(gui_script, "struct PythonSpellCastCheck") + ";")
    pieces.append(function(gui_script, "struct PythonNonPartySpellCastCheck") + ";")
    pieces.append(function(gui_script, "static PyObject* GemRB_SetSpellCastCheck("))
    pieces.append(function(gui_script, "static PyObject* GemRB_SetNonPartySpellCastCheck("))
    pieces.append(function(gui_script, "static PyObject* GemRB_SpellCast("))
    # Exercise the complete production action state machines, including the
    # later ticks that consume an accepted replacement and its header/level.
    prefixes = next(line for line in scripts.splitlines() if line.startswith("static const StringView spell_suffices"))
    pieces.append(prefixes)
    for signature in (
        "bool ResolveSpellName(",
        "void ResolveSpellName(",
        "void SpellCore(",
        "void SpellPointCore(",
    ):
        pieces.append(function(scripts, signature))
    pieces.append(SCENARIOS)
    return "\n".join(pieces)


class SpellCastCheckTests(unittest.TestCase):
    def scenario(self, name):
        environment = os.environ.copy()
        python_home = environment.pop("GEMRB_TEST_PYTHONHOME", None)
        if python_home:
            environment["PYTHONHOME"] = python_home
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True,
                                timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(name + " passed", result.stdout)

    def test_no_hook_preserves_native_dispatch(self): self.scenario("unchanged")
    def test_actor_point_self_none_after_validation(self): self.scenario("accepted")
    def test_direct_unknown_substitution_uses_effective_resref(self): self.scenario("direct_substitution")
    def test_false_vetoes_queue_and_instant_effect(self): self.scenario("veto")
    def test_multitarget_veto_resets_mode_without_falsely_clearing_count(self): self.scenario("multitarget_veto")
    def test_canceled_invalid_untargetable_and_unmemorized_do_not_commit(self): self.scenario("not_accepted")
    def test_items_do_not_invoke_spell_check(self): self.scenario("items")
    def test_actual_substitution_global_actor_id_and_multiple_targets(self): self.scenario("identity_and_targets")
    def test_python_and_truth_conversion_exceptions_fail_closed(self): self.scenario("exceptions")
    def test_nonparty_callback_can_substitute_and_skips_party(self): self.scenario("nonparty_substitution")
    def test_nonparty_callback_veto_and_exceptions_fail_closed(self): self.scenario("nonparty_veto")
    def test_nonparty_true_preserves_spell_and_none_vetoes(self): self.scenario("nonparty_results")
    def test_nonparty_invalid_replacements_fail_without_mutation_or_python_error(self): self.scenario("nonparty_invalid")
    def test_script_casts_keep_replacement_header_level_and_reusable_action(self):
        for target in ("actor", "point"):
            for encoding in ("res", "numeric"):
                for timing in ("delayed", "instant"):
                    with self.subTest(target=target, encoding=encoding, timing=timing):
                        self.scenario(f"script_{target}_{encoding}_{timing}")
    def test_marked_script_cast_keeps_accepted_spell_after_mark_changes(self): self.scenario("script_actor_marked")
    def test_script_checks_wait_for_range_los_and_aura(self):
        for target in ("actor", "point"):
            with self.subTest(target=target):
                self.scenario(f"script_{target}_pending")
    def test_script_native_party_veto_and_invalid_paths(self):
        for target in ("actor", "point"):
            for mode in ("native", "party", "veto", "invalid", "invalid_instant"):
                with self.subTest(target=target, mode=mode):
                    self.scenario(f"script_{target}_{mode}")
    def test_unregister_gamecontrol_lifetime_and_invalid_registration(self): self.scenario("lifetime")


if __name__ == "__main__":
    run_tests(SpellCastCheckTests, generate_harness)
