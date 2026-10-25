# Ordinary table and map-cache compatibility checks

Configure GemRB to obtain `config.h`, then run:

```sh
python3 gemrb/tests/security/test_valid_container_caches.py \
  --config-directory build --output valid-container-caches.json
```

The check uses actual `TableMgr`, `TraversabilityCache` and geometry declarations,
the table's real signed-field parser, and selected production table/cache/index
methods. It compiles with `NDEBUG`, AddressSanitizer and UndefinedBehaviorSanitizer.
It covers ordinary APR-table values and cached/clamped lookups, normal map-cache
initialization/reuse/resize, and row/grid boundaries selecting the spare cell.
An isolated source overlay can supply `--header-root` for the complete
checkout's remaining headers.

Resource discovery, the map's property-size provider and GameData's field shell
are bounded adapters. Only the actual early `Update` prefix is included; actor
movement/state updates and complete pathfinding are not executed. These checks
do not run malformed files, overflow-sized inputs, baseline comparisons or a
full engine. Passing them does not establish gameplay or imported-content
acceptance. Receipts record normalized source, fixture, runner and API hashes.
The existing `FitRegion` origin fields are uint16 and can wrap negative actor
origins before indexing; this change does not repair that representation.
