#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise native fist replacement, unarmed selection and Monk table lookup.

Compile the production function bodies with controlled inventory/resource
boundaries. The defense oracle is the shipped table, including reordered rows;
the weapon oracle observes the cache after the old inventory item is replaced.
Full actor effects, rendering and real saves remain live acceptance checks.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest

from native_harness import run_tests


ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


BOUNDARIES = r'''
#include <algorithm>
#include <cassert>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
using ieWord = unsigned short;
using ieWordSigned = short;
using ResRef = std::string;
constexpr int IW_NO_EQUIPPED=1000, SLOT_FIST=10, SLOT_MELEE=35, SLOT_MAGIC=34;
constexpr int SLOT_EFFECT_FIST=2, SLOT_EFFECT_MELEE=4, SLOT_EFFECT_MISSILE=5;
constexpr int IE_INV_ITEM_EQUIPPED=1, IE_KIT=152, MAX_LEVEL=40;
struct { int fistStat=232; } CFGCache;
template<class T> T Clamp(T value, T low, T high) { return std::clamp(value,low,high); }
struct Core {
    int QuerySlot(int slot) const { assert(slot==0); return SLOT_FIST; }
    int QuerySlotEffects(int slot) const {
        return slot==SLOT_FIST ? SLOT_EFFECT_FIST : SLOT_EFFECT_MELEE;
    }
} coreStorage;
Core* core=&coreStorage;
struct CREItem {
    ResRef ItemResRef;
    int Flags=0;
};
struct Inventory {
    std::vector<std::unique_ptr<CREItem>> Slots=std::vector<std::unique_ptr<CREItem>>(40);
    int Equipped=IW_NO_EQUIPPED, EquippedHeader=0;
    int cacheRefreshes=0, animationRefreshes=0;
    ResRef cachedWeapon;
    const CREItem* GetSlotItem(int slot) const { return Slots.at(slot).get(); }
    CREItem* GetSlotItem(int slot) { return Slots.at(slot).get(); }
    static int GetWeaponSlot(int slotcode) { return SLOT_MELEE+slotcode; }
    int GetEquippedSlot() const { return Equipped==IW_NO_EQUIPPED ? SLOT_FIST : GetWeaponSlot(Equipped); }
    bool MagicSlotEquipped() const { return bool(Slots[SLOT_MAGIC]); }
    bool IsSlotEmpty(int slot) const { return !Slots.at(slot); }
    bool FistsEquipped() const;
    bool SetEquippedSlot(ieWordSigned,ieWord,bool=false);
    void SetSlotItemRes(const ResRef& resref,int slot) {
        Slots.at(slot)=std::make_unique<CREItem>(CREItem{resref});
    }
    void CacheAllWeaponInfo() {
        ++cacheRefreshes;
        const auto* item=GetSlotItem(GetEquippedSlot());
        cachedWeapon=item ? item->ItemResRef : "";
    }
    void UpdateWeaponAnimation() { ++animationRefreshes; }
    void RemoveSlotEffects(unsigned) {}
    void AddSlotEffects(unsigned) {}
    unsigned FindSlotRangedWeapon(unsigned) const { return SLOT_FIST; }
    unsigned FindRangedWeapon() const { return SLOT_FIST; }
};
struct Actor {
    Inventory inventory;
    int monkLevel=1, sorcererLevel=1;
    const std::string className="SORCERER_MONK", kitName="";
    int GetMonkLevel() const { return monkLevel; }
    int GetXPLevel(bool) const { return (monkLevel+sorcererLevel+1)/2; }
    int GetBase(int) const { return 22; }
    int GetActiveClass() const { return 22; }
    const std::string& GetClassName(int) const { return className; }
    const std::string& GetKitName(int) const { return kitName; }
    void SetupFist();
};
struct TableMgr {
    using index_t=unsigned;
    std::vector<std::string> names;
    std::vector<std::vector<int>> rows;
    unsigned GetColumnCount() const { return rows.front().size(); }
    unsigned GetRowIndex(const std::string& name) const {
        auto found=std::find(names.begin(),names.end(),name);
        return found==names.end() ? unsigned(-1) : found-names.begin();
    }
    template<class T> T QueryFieldSigned(unsigned row,unsigned column) const {
        return row<rows.size() && column<rows[row].size() ? rows[row][column] : 0;
    }
    template<class T> T QueryFieldSigned(const std::string& row,const char*) const {
        return row=="SORCERER_MONK" ? 3 : 0;
    }
};
using AutoTable=std::shared_ptr<TableMgr>;
struct GameData {
    AutoTable monkBon=std::make_shared<TableMgr>(), weaponMisc=std::make_shared<TableMgr>();
    AutoTable LoadTable(const char* name,bool=true) const {
        return std::string(name)=="monkbon" ? monkBon : weaponMisc;
    }
    ResRef GetFist(int,int level) const { return "FIST"+std::to_string(level); }
    int GetMonkBonus(int,int,const Actor* = nullptr);
} gameDataStorage;
GameData* gamedata=&gameDataStorage;
static void readTable(const char* path) {
    std::ifstream input(path);
    assert(input);
    std::string line, word;
    std::getline(input,line); std::getline(input,line); std::getline(input,line);
    while (std::getline(input,line)) {
        std::istringstream row(line);
        if (!(row>>word)) continue;
        gamedata->monkBon->names.push_back(word);
        std::vector<int> values;
        int value;
        while (row>>value) values.push_back(value);
        gamedata->monkBon->rows.push_back(values);
    }
}
'''


MAIN = r'''
int main(int argc,char** argv) {
    assert(argc>=2);
    const std::string scenario=argv[1];
    Actor actor;
    if (scenario=="initial-fist") {
        actor.SetupFist();
        assert(actor.inventory.cachedWeapon=="FIST1");
    } else if (scenario=="replacement") {
        actor.inventory.SetSlotItemRes("FIST1",SLOT_FIST);
        actor.inventory.CacheAllWeaponInfo();
        actor.monkLevel=6;
        actor.sorcererLevel=1;
        actor.SetupFist();
        assert(actor.inventory.GetSlotItem(SLOT_FIST)->ItemResRef=="FIST6");
        assert(actor.inventory.cachedWeapon=="FIST6");
        const int refreshes=actor.inventory.cacheRefreshes;
        actor.SetupFist();
        assert(actor.inventory.cacheRefreshes==refreshes);
    } else if (scenario=="armed-replacement") {
        actor.inventory.SetSlotItemRes("DAGGER",SLOT_MELEE);
        actor.inventory.SetEquippedSlot(0,0);
        actor.SetupFist();
        actor.monkLevel=8;
        actor.SetupFist();
        assert(actor.inventory.cachedWeapon=="DAGGER");
        assert(actor.inventory.Equipped==0);
        assert(actor.inventory.GetSlotItem(SLOT_FIST)->ItemResRef=="FIST8");
    } else if (scenario=="quick-fist") {
        actor.inventory.SetSlotItemRes("FIST6",SLOT_FIST);
        assert(actor.inventory.SetEquippedSlot(SLOT_FIST-SLOT_MELEE,0));
        assert(actor.inventory.FistsEquipped());
        assert(actor.inventory.GetEquippedSlot()==SLOT_FIST);
        assert(actor.inventory.cachedWeapon=="FIST6");
        actor.inventory.SetSlotItemRes("DAGGER",SLOT_MELEE);
        assert(actor.inventory.SetEquippedSlot(0,0));
        assert(!actor.inventory.FistsEquipped());
        assert(actor.inventory.SetEquippedSlot(IW_NO_EQUIPPED,0));
        assert(actor.inventory.FistsEquipped());
    } else if (scenario=="magic-weapon") {
        actor.inventory.SetSlotItemRes("MAGIC",SLOT_MAGIC);
        actor.inventory.SetSlotItemRes("FIST6",SLOT_FIST);
        assert(!actor.inventory.SetEquippedSlot(SLOT_FIST-SLOT_MELEE,0));
        assert(!actor.inventory.FistsEquipped());
        assert(actor.inventory.GetEquippedSlot()==SLOT_MAGIC);
    } else if (scenario=="bonuses") {
        assert(argc==4);
        readTable(argv[2]);
        int level=std::stoi(argv[3]);
        std::cout<<gamedata->GetMonkBonus(0,level,&actor)<<" "
                 <<gamedata->GetMonkBonus(1,level)<<" "
                 <<gamedata->GetMonkBonus(2,level)<<"\n";
    } else return 3;
}
'''


def generate_harness():
    actor = (ROOT / 'core/Scriptable/Actor.cpp').read_text()
    inventory = (ROOT / 'core/Inventory.cpp').read_text()
    data = (ROOT / 'core/GameData.cpp').read_text()
    return BOUNDARIES + '\n'.join((
        function(inventory, 'bool Inventory::FistsEquipped() const'),
        function(inventory, 'bool Inventory::SetEquippedSlot('),
        function(actor, 'void Actor::SetupFist()'),
        function(data, 'int GameData::GetMonkBonus('),
    )) + MAIN


class MonkProgressionTests(unittest.TestCase):
    def run_case(self, *arguments):
        result = subprocess.run([str(self.binary), *map(str, arguments)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_initial_fist_populates_weapon_cache(self):
        self.run_case('initial-fist')

    def test_replaced_fist_updates_cache_using_monk_component_level(self):
        self.run_case('replacement')

    def test_progression_keeps_equipped_weapon(self):
        self.run_case('armed-replacement')

    def test_quickweapon_fist_uses_unarmed_sentinel(self):
        self.run_case('quick-fist')

    def test_fist_selection_cannot_override_magic_weapon(self):
        self.run_case('magic-weapon')

    def assert_bonuses(self, path):
        rows = {words[0]: list(map(int, words[1:])) for line in path.read_text().splitlines()[3:]
                if (words := line.split())}
        for level in (0, 1, 2, 6, 8, 19, 40, 60):
            expected = [0, 0, 0] if not level else [
                min(6, level // 3), rows['AC_BONUS'][min(level, 40) - 1],
                rows['ACM_BONUS'][min(level, 40) - 1]]
            with self.subTest(table=path.name, level=level):
                self.assertEqual(list(map(int, self.run_case('bonuses', path, level).split())), expected)

    def test_defense_rows_match_shipped_bg2_and_ee_tables(self):
        for family in ('bg2', 'bgee', 'bg2ee'):
            self.assert_bonuses(ROOT / 'unhardcoded' / family / 'monkbon.2da')

    def test_named_defense_rows_allow_reordered_table(self):
        lines = (ROOT / 'unhardcoded/bgee/monkbon.2da').read_text().splitlines()
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / 'monkbon.2da'
            table.write_text('\n'.join(lines[:3] + list(reversed(lines[3:]))) + '\n')
            self.assert_bonuses(table)


if __name__ == '__main__':
    run_tests(MonkProgressionTests, generate_harness)
