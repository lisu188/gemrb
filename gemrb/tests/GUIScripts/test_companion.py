#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile the production companion binding with controlled actor/map storage."""
import os
from pathlib import Path
import subprocess
import unittest
from native_harness import run_tests

ROOT = Path(__file__).resolve().parents[2]
BOUNDARIES = r'''
#include <Python.h>
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using ieDword = unsigned int;
struct ResRef : std::string {
    explicit ResRef(const char* s): std::string(s) { for (auto& c : *this) c = std::tolower(c); }
};
struct ieVariable : std::string {
    using std::string::string;
    void Reset() { clear(); }
    void Format(const char*, const ResRef& r) { assign("GMC_" + r); }
    void Format(const char*, const ResRef& r, unsigned t) {
        std::ostringstream s; s << "gmc" << r << std::hex << std::setw(8) << std::setfill('0') << t; assign(s.str());
    }
};
struct Point { int x=10, y=20; };
struct Size { Size(int, int) {} };
constexpr int IE_STATE_ID=0, IE_HITPOINTS=1, IE_EA=2, IE_XPVALUE=3;
constexpr unsigned STATE_DEAD=0x800, IF_CLEANUP=0x4000;
constexpr int EA_CONTROLLED=5, SELECT_NORMAL=0;
struct EffectRef { const char* name; int opcode; };
struct Effect {
    unsigned Opcode=187, IsVariable=1, Parameter1=0;
    ieVariable VariableName;
};
struct EffectQueue {
    std::vector<Effect> effects;
    static int ResolveEffect(EffectRef&) { return 187; }
    auto GetFirstEffect() const { return effects.cbegin(); }
    const Effect* GetNextEffect(std::vector<Effect>::const_iterator& iterator) const {
        return iterator==effects.cend() ? nullptr : &*iterator++;
    }
};
struct Map;
struct Actor {
    unsigned id=1001, InParty=0, flags=0;
    std::map<std::string, unsigned> locals;
    std::map<int, unsigned> stats{{IE_HITPOINTS,10}};
    EffectQueue fxqueue;
    ieVariable name;
    struct { ieVariable origScriptName; } ignoredFields;
    Map* area=nullptr;
    Point Pos;
    struct { unsigned LastSummoner=0; } objects;
    int persistence=-1, clears=0;
    static std::set<Actor*> allocated;
    ~Actor() { allocated.erase(this); }
    unsigned GetLocal(const ieVariable& k, unsigned f) const { auto i=locals.find(k); return i==locals.end()?f:i->second; }
    unsigned GetStat(int s) const { auto i=stats.find(s); return i==stats.end()?0:i->second; }
    unsigned GetInternalFlag() const { return flags; }
    unsigned GetGlobalID() const { return id; }
    Map* GetCurrentArea() const { return area; }
    void SetScriptName(const ieVariable& n) { name=n; }
    void SetPersistent(int v) { persistence=v; }
    void SetBase(int s, unsigned v) { stats[s]=v; }
    void SetPosition(const Point& p, bool, Size) { Pos=p; }
    void RefreshEffects() {}
    void CreateStats() {}
    void DestroySelf() { flags |= IF_CLEANUP; }
    void ClearActions() { ++clears; }
};
std::set<Actor*> Actor::allocated;
struct Map {
    ResRef name;
    std::vector<Actor*> actors;
    explicit Map(const char* n): name(n) {}
    Actor* GetActor(const ieVariable& n, int) const { for(auto* a:actors) if(a->name==n) return a; return nullptr; }
    void AddActor(Actor* a, bool) { actors.push_back(a); a->area=this; }
    ResRef GetScriptRef() const { return name; }
} areaA("ar0001"), areaB("ar0002");
struct Game {
    std::map<std::string,unsigned> locals;
    std::vector<Actor*> pcs,npcs;
    bool rejectNPC=false;
    unsigned GetGlobal(const ieVariable& k,unsigned f) const { auto i=locals.find(k); return i==locals.end()?f:i->second; }
    int GetPartySize(bool) const { return pcs.size(); }
    int GetNPCCount() const { return npcs.size(); }
    Actor* GetPC(int i,bool) const { return pcs.at(i); }
    Actor* GetNPC(int i) const { return npcs.at(i); }
    Actor* FindNPC(const ieVariable& n) const { for(auto* a:npcs) if(a->name==n) return a; return nullptr; }
    Actor* FindPC(const ieVariable& n) const { for(auto* a:pcs) if(a->name==n) return a; return nullptr; }
    Actor* FindPC(int slot) const { for(auto* a:pcs) if(a->InParty==unsigned(slot)) return a; return nullptr; }
    Actor* GetActorByGlobalID(int id) const { for(auto* a:pcs) if(a->id==unsigned(id)) return a; for(auto* a:npcs) if(a->id==unsigned(id)) return a; return nullptr; }
    int InStore(Actor* a) const { auto i=std::find(npcs.begin(),npcs.end(),a); return i==npcs.end()?-1:int(i-npcs.begin()); }
    void SelectActor(Actor*,bool,int) {}
    int DelNPC(int slot) { assert(slot>=0); npcs.erase(npcs.begin()+slot); return 0; }
    int AddNPC(Actor* a) { if(rejectNPC) return -1; npcs.push_back(a); a->SetPersistent(0); return npcs.size()-1; }
} storage;
struct GameData {
    bool missing=false;
    unsigned next=2001;
    Actor* GetCreature(const ResRef&) { if(missing) return nullptr; auto* a=new Actor; a->id=next++; Actor::allocated.insert(a); return a; }
} dataStorage;
GameData* gamedata=&dataStorage;
#define PARSE_ARGS(args,format,...) if(!PyArg_ParseTuple(args,format,__VA_ARGS__)) return nullptr
#define GET_GAME() Game* game=&storage
#define GET_ACTOR_GLOBAL() Actor* actor=globalID>1000?game->GetActorByGlobalID(globalID):game->FindPC(globalID); if(!actor) return RuntimeError("Actor not found")
static PyObject* RuntimeError(const char* s) { PyErr_SetString(PyExc_RuntimeError,s); return nullptr; }
static void MoveBetweenAreasCore(Actor* a,const ResRef& area,const Point& p,int,bool) {
    if(a->area) { auto& v=a->area->actors; v.erase(std::remove(v.begin(),v.end(),a),v.end()); }
    (area==areaA.name?areaA:areaB).AddActor(a,true); a->Pos=p;
}
'''
SCENARIOS = r'''
static PyObject* invoke(int owner,const char* resource="pscrbody",int mode=0) {
    PyObject* args=Py_BuildValue("(isi)",owner,resource,mode);
    PyObject* result=GemRB_ManageCompanion(nullptr,args); Py_DECREF(args); return result;
}
static unsigned actorId(PyObject* r) { assert(r && r!=Py_None); return PyLong_AsUnsignedLong(PyDict_GetItemString(r,"ActorID")); }
static bool flag(PyObject* r,const char* name) { assert(r && r!=Py_None); return PyObject_IsTrue(PyDict_GetItemString(r,name)); }
static void rejected(PyObject* r) { assert(!r && PyErr_Occurred()); PyErr_Clear(); }
int main(int argc,char** argv) {
    assert(argc==2); Py_Initialize();
    Actor owner,other; owner.InParty=1; other.InParty=2; other.id=1002;
    storage.pcs={&owner,&other}; areaA.AddActor(&owner,true); areaA.AddActor(&other,true);
    const std::string test=argv[1];
    if(test=="inspect") {
        PyObject* r=invoke(1); assert(r==Py_None); Py_DECREF(r);
        r=invoke(1,"pscrbody",3); assert(r==Py_None); Py_DECREF(r);
        assert(owner.locals.empty() && storage.locals.empty() && storage.npcs.empty());
    } else if(test=="create_recall") {
        PyObject* r=invoke(1,"pscrbody",1); assert(flag(r,"Created") && flag(r,"Alive") && flag(r,"InArea"));
        unsigned id=actorId(r); Py_DECREF(r); auto* a=storage.npcs.at(0);
        a->stats[IE_HITPOINTS]=3; a->locals["unrelated"]=42;
        r=invoke(1,"PSCRBODY",1); assert(actorId(r)==id && !flag(r,"Created")); Py_DECREF(r);
        assert(a->GetStat(IE_HITPOINTS)==3 && a->locals["unrelated"]==42 && storage.npcs.size()==1);
        assert(a->persistence==0 && a->GetStat(IE_EA)==EA_CONTROLLED && a->GetStat(IE_XPVALUE)==0);
    } else if(test=="two_owners") {
        PyObject* r=invoke(1,"pscrbody",1); unsigned first=actorId(r); Py_DECREF(r);
        r=invoke(2,"pscrbody",1); assert(actorId(r)!=first); Py_DECREF(r);
        assert(storage.npcs.size()==2 && owner.locals["GMC_pscrbody"]!=other.locals["GMC_pscrbody"]);
        owner.InParty=2; other.InParty=1; std::swap(storage.pcs[0],storage.pcs[1]);
        r=invoke(2); assert(actorId(r)==first); Py_DECREF(r);
        r=invoke(2,"pscrbody",2); assert(r==Py_None); Py_DECREF(r); assert(storage.npcs.size()==1);
    } else if(test=="reload") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); auto* a=storage.npcs.at(0);
        a->id=9009; owner.id=8008; a->objects.LastSummoner=0; a->name=a->ignoredFields.origScriptName;
        r=invoke(1,"pscrbody",3); assert(actorId(r)==9009); Py_DECREF(r);
        assert(a->objects.LastSummoner==8008 && storage.npcs.size()==1);
    } else if(test=="transition") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); auto* a=storage.npcs.at(0);
        a->stats[IE_HITPOINTS]=4; owner.area=&areaB; owner.Pos={70,90};
        r=invoke(1); assert(!flag(r,"InArea")); Py_DECREF(r); assert(a->area==&areaA);
        r=invoke(1,"pscrbody",3); assert(flag(r,"InArea") && !flag(r,"Created")); Py_DECREF(r);
        assert(a->area==&areaB && a->GetStat(IE_HITPOINTS)==4 && a->Pos.x==70);
    } else if(test=="reload_unloaded") {
        PyObject* r=invoke(1,"pscrbody",1); unsigned id=actorId(r); Py_DECREF(r); auto* a=storage.npcs.at(0);
        unsigned token=a->locals["GMC_TOKEN"];
        a->locals.clear(); a->area=nullptr;
        a->fxqueue.effects.push_back({187,1,token,"GMC_TOKEN"});
        r=invoke(1); assert(actorId(r)==id && !flag(r,"InArea")); Py_DECREF(r);
        assert(a->area==nullptr && a->locals.empty() && a->fxqueue.effects.size()==1);
        r=invoke(1,"pscrbody",3); assert(actorId(r)==id && flag(r,"InArea") && !flag(r,"Created")); Py_DECREF(r);
        assert(storage.npcs.size()==1 && a->objects.LastSummoner==owner.id);
    } else if(test=="saved_marker_validation") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); auto* a=storage.npcs.at(0);
        unsigned token=a->locals["GMC_TOKEN"];
        a->locals.clear(); a->area=nullptr;
        a->fxqueue.effects.push_back({187,1,token,"UNRELATED"});
        rejected(invoke(1));
        a->fxqueue.effects.push_back({187,0,token,"GMC_TOKEN"});
        rejected(invoke(1));
        a->fxqueue.effects.push_back({187,1,token,"GMC_TOKEN"});
        a->locals["GMC_TOKEN"]=0;
        rejected(invoke(1));
        assert(storage.npcs.size()==1 && a->area==nullptr && a->flags==0);
    } else if(test=="saved_duplicate_owner") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r);
        other.fxqueue.effects.push_back({187,1,owner.locals["GMC_pscrbody"],"GMC_pscrbody"});
        rejected(invoke(1,"pscrbody",2));
        assert(storage.npcs.size()==1);
    } else if(test=="death") {
        PyObject* r=invoke(1,"pscrbody",1); unsigned old=actorId(r); Py_DECREF(r);
        auto* a=storage.npcs.at(0); a->stats[IE_STATE_ID]=STATE_DEAD;
        r=invoke(1,"pscrbody",3); assert(!flag(r,"Alive")); Py_DECREF(r); assert(storage.npcs.size()==1);
        r=invoke(1,"pscrbody",1); assert(flag(r,"Created") && actorId(r)!=old); Py_DECREF(r);
        assert(storage.npcs.size()==1 && (a->flags&IF_CLEANUP) && a->persistence==-1 && a->name.empty());
    } else if(test=="missing_template") {
        dataStorage.missing=true; rejected(invoke(1,"pscrbody",1));
        assert(owner.locals.empty() && storage.locals.empty() && storage.npcs.empty());
    } else if(test=="registration_failure") {
        storage.rejectNPC=true; rejected(invoke(1,"pscrbody",1));
        assert(storage.npcs.empty() && Actor::allocated.empty());
        storage.rejectNPC=false; PyObject* r=invoke(1,"pscrbody",1); assert(flag(r,"Created")); Py_DECREF(r);
    } else if(test=="foreign_collision") {
        Actor foreign; foreign.name="gmcpscrbody00000001"; areaA.AddActor(&foreign,true);
        rejected(invoke(1,"pscrbody",1)); assert(foreign.flags==0 && storage.npcs.empty());
        assert(owner.locals.empty());
    } else if(test=="marker_mismatch") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); auto* a=storage.npcs.at(0);
        a->locals["GMC_TOKEN"]=22; rejected(invoke(1,"pscrbody",2)); assert(storage.npcs.size()==1 && a->flags==0);
    } else if(test=="duplicate_owner") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); other.locals=owner.locals;
        rejected(invoke(2,"pscrbody",1)); rejected(invoke(1,"pscrbody",2)); assert(storage.npcs.size()==1);
    } else if(test=="registry") {
        owner.locals["GMC_pscrbody"]=9; rejected(invoke(1)); owner.locals.clear();
        storage.locals["GMC_NEXT"]=0x7fffffff; rejected(invoke(1,"pscrbody",1)); assert(storage.npcs.empty());
    } else if(test=="invalid_input") {
        for(const char* name:{"","toolongcre","../bad","a-b"}) rejected(invoke(1,name,1));
        rejected(invoke(1,"pscrbody",4)); rejected(invoke(77,"pscrbody",1));
        owner.InParty=0; rejected(invoke(1001,"pscrbody",1)); assert(storage.npcs.empty());
    } else if(test=="owner_unavailable") {
        owner.area=nullptr; rejected(invoke(1,"pscrbody",1)); owner.area=&areaA;
        owner.stats[IE_STATE_ID]=STATE_DEAD; rejected(invoke(1,"pscrbody",1)); assert(storage.npcs.empty());
    } else if(test=="dismiss_unloaded") {
        PyObject* r=invoke(1,"pscrbody",1); Py_DECREF(r); auto* a=storage.npcs.at(0);
        a->area=nullptr; r=invoke(1,"pscrbody",2); assert(r==Py_None); Py_DECREF(r);
        assert(storage.npcs.empty() && Actor::allocated.empty());
        r=invoke(1); assert(r==Py_None); Py_DECREF(r);
    } else { assert(false); }
    while(!Actor::allocated.empty()) delete *Actor::allocated.begin();
    assert(!PyErr_Occurred()); Py_Finalize(); std::cout << test << " passed\n";
}
'''


def generate_harness():
    return BOUNDARIES + (ROOT / "plugins/GUIScript/CompanionBindings.h").read_text() + SCENARIOS


class CompanionTests(unittest.TestCase):
    def scenario(self, name):
        env = os.environ.copy()
        home = env.pop("GEMRB_TEST_PYTHONHOME", None)
        if home:
            env["PYTHONHOME"] = home
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(name + " passed", result.stdout)


for scenario in ("inspect", "create_recall", "two_owners", "reload", "transition", "death", "missing_template",
                 "registration_failure", "foreign_collision", "marker_mismatch", "duplicate_owner", "registry",
                 "invalid_input", "owner_unavailable", "dismiss_unloaded", "reload_unloaded",
                 "saved_marker_validation", "saved_duplicate_owner"):
    setattr(CompanionTests, "test_" + scenario, lambda self, name=scenario: self.scenario(name))


if __name__ == "__main__":
    run_tests(CompanionTests, generate_harness)
