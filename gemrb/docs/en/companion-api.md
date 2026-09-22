# Persistent companions for class mods

`GemRB.ManageCompanion(ownerID, creatureResref, mode=0)` manages one companion
per party owner and creature resource. The creature resource is an ASCII
alphanumeric/underscore name of at most eight characters.

| Mode | Operation |
| --- | --- |
| 0 | Inspect without creating state or a creature. |
| 1 | Create a missing/dead body, or recall the existing living body. |
| 2 | Dismiss the owned body without erasing the owner's identity. |
| 3 | Synchronize an existing body: rebind its summoner and move a living body across areas. Never create or resurrect. |

The result is `None` when no body exists, otherwise a dictionary containing
`ActorID`, `Alive`, `Created` and `InArea`. The returned actor ID is valid for the
current engine session only. Re-query after loading a save.

Owner identity is a namespaced local `GMC_<resource>`, allocated from the saved
game counter `GMC_NEXT`. The body carries `GMC_TOKEN`, receives a unique script
name, and is registered in the native persistent-NPC roster. Both the current
script name and `ignoredFields.origScriptName` are set: the CRE writer preserves
the latter. Actor locals are serialized by the existing CRE variable effects.
`LastSummoner` is re-established by modes 1 and 3, not used as saved ownership.
The familiar slot, familiar bonuses and protagonist-specific familiar state
are not modified.

Recall and synchronization retain the same living actor, its HP, effects and
inventory. Dismissal removes the body from the persistent roster and defers
active-map destruction. Dead-body replacement loads the new resource before
retiring the old body. Missing resources, invalid owner state, duplicate owner
identities and foreign name/marker collisions raise an error instead of deleting
unrelated actors. Owners imported into another save with an inconsistent token
registry require explicit migration; the binding does not guess a new identity.

The caller remains responsible for class eligibility, action confirmation,
per-rest limits, initial statistics, progression, and scheduling synchronization.
This API is not an automatic follower tick or a resource-accounting system.
Multiple operations are not an engine-wide transaction. A roster-registration
failure may retain a reserved identity, which a later retry reuses safely.

`gemrb/tests/GUIScripts/test_companion.py` compiles the production binding with
controlled actor/map storage. Its fifteen scenarios cover ownership, recall,
injuries, simulated reload/ID changes, area transfer, replacement and failure
boundaries. These tests do not substitute for actual campaign save/reload tests.
