// SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include <cstring>

static void RetireCompanion(Game* game, Actor* companion)
{
	game->SelectActor(companion, false, SELECT_NORMAL);
	game->DelNPC(game->InStore(companion));
	companion->SetPersistent(-1);
	companion->SetScriptName(ieVariable());
	companion->ignoredFields.origScriptName.Reset();
	if (companion->GetCurrentArea()) {
		companion->DestroySelf();
	} else {
		delete companion;
	}
}

PyDoc_STRVAR(GemRB_ManageCompanion__doc,
	     "ManageCompanion(ownerID, creature, mode=0) -> dict or None.\n"
	     "Modes: 0 inspect; 1 summon or recall; 2 dismiss; 3 synchronize existing.\n"
	     "Ownership is saved in namespaced actor locals and a game counter, never a party slot.\n"
	     "Existing living actors retain HP, effects and inventory. Mode 1 replaces dead actors.\n"
	     "Mode 3 rebinds the summoner and moves a living companion only across areas.\n"
	     "Returns ActorID, Alive, Created and InArea. No familiar state is used.\n"
	     "The caller owns class eligibility, resource costs and initial creature statistics.");

static PyObject* GemRB_ManageCompanion(PyObject* /*self*/, PyObject* args)
{
	int globalID, mode = 0;
	const char* creatureName = nullptr;
	PARSE_ARGS(args, "is|i", &globalID, &creatureName, &mode);
	if (mode < 0 || mode > 3) return RuntimeError("Invalid companion mode");
	const size_t length = std::strlen(creatureName);
	if (!length || length > 8) return RuntimeError("Invalid companion resource");
	for (size_t i = 0; i < length; ++i) {
		char c = creatureName[i];
		if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
		      (c >= '0' && c <= '9') || c == '_')) {
			return RuntimeError("Invalid companion resource");
		}
	}
	GET_GAME();
	GET_ACTOR_GLOBAL();
	if (!actor->InParty) return RuntimeError("Companion owner must be a party actor");

	const ResRef resource(creatureName);
	ieVariable key;
	key.Format("GMC_{}", resource);
	ieDword token = actor->GetLocal(key, 0);
	const ieDword last = game->GetGlobal("GMC_NEXT", 0);
	if (last > 0x7fffffff || token > last) return RuntimeError("Invalid companion ownership registry");
	if (token) {
		for (int i = 0; i < game->GetPartySize(false); ++i) {
			const Actor* other = game->GetPC(i, false);
			if (other != actor && other->GetLocal(key, 0) == token) {
				return RuntimeError("Duplicate companion owner identity");
			}
		}
		for (int i = 0; i < game->GetNPCCount(); ++i) {
			if (game->GetNPC(i)->GetLocal(key, 0) == token) {
				return RuntimeError("Duplicate companion owner identity");
			}
		}
	}
	Map* map = actor->GetCurrentArea();
	ieVariable name;
	name.Format("gmc{}{:08x}", resource, token ? token : last + 1);
	Actor* companion = game->FindNPC(name);
	if (game->FindPC(name) || (map && map->GetActor(name, 0) && map->GetActor(name, 0) != companion)) {
		return RuntimeError("Companion script name is already in use");
	}
	if (companion && (!token || companion->InParty || companion->GetLocal("GMC_TOKEN", 0) != token)) {
		return RuntimeError("Companion ownership marker does not match");
	}
	bool created = false;
	auto alive = [](const Actor* target) {
		return target && !(target->GetStat(IE_STATE_ID) & STATE_DEAD) &&
			!(target->GetInternalFlag() & IF_CLEANUP) && target->GetStat(IE_HITPOINTS) > 0;
	};
	if (mode == 2) {
		if (companion) RetireCompanion(game, companion);
		Py_RETURN_NONE;
	}
	if (mode == 1) {
		if (!map || !alive(actor)) return RuntimeError("Companion owner is not alive in an area");
		if (!alive(companion)) {
			std::unique_ptr<Actor> fresh(gamedata->GetCreature(resource));
			if (!fresh) return RuntimeError("Companion creature resource cannot be loaded");
			if (!token) {
				if (last == 0x7fffffff) return RuntimeError("Companion ownership registry is full");
				token = last + 1;
				game->locals["GMC_NEXT"] = token;
				actor->locals[key] = token;
			}
			fresh->CreateStats();
			fresh->SetScriptName(name);
			fresh->ignoredFields.origScriptName = name;
			fresh->locals["GMC_TOKEN"] = token;
			fresh->SetBase(IE_EA, EA_CONTROLLED);
			fresh->SetBase(IE_XPVALUE, 0);
			if (game->AddNPC(fresh.get()) < 0) return RuntimeError("Companion cannot be made persistent");
			if (companion) RetireCompanion(game, companion);
			companion = fresh.release();
			map->AddActor(companion, true);
			companion->SetPosition(actor->Pos, true, Size(10, 10));
			companion->RefreshEffects();
			created = true;
		}
	}
	if (!companion) Py_RETURN_NONE;
	if ((mode == 1 || mode == 3) && map && alive(actor) && alive(companion)) {
		companion->objects.LastSummoner = actor->GetGlobalID();
		if (!created && (mode == 1 || companion->GetCurrentArea() != map)) {
			companion->ClearActions();
			MoveBetweenAreasCore(companion, map->GetScriptRef(), actor->Pos, -1, true);
		}
	}
	return Py_BuildValue("{s:i,s:O,s:O,s:O}",
			     "ActorID", companion->GetGlobalID(),
			     "Alive", alive(companion) ? Py_True : Py_False,
			     "Created", created ? Py_True : Py_False,
			     "InArea", map && companion->GetCurrentArea() == map ? Py_True : Py_False);
}
