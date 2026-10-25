# Parser bounds regression fixtures

`test_parser_bounds.py` extracts the selected production parser functions and
spawn-specification statements into bounded host adapters. It compiles the
result with AddressSanitizer and UndefinedBehaviorSanitizer. The adapters replace
engine, renderer and resource dependencies; they do not establish full-engine,
package, gameplay or imported-content compatibility.

For an ordinary valid-fixture smoke check on a host with Python and GCC/Clang:

```sh
python3 gemrb/tests/security/test_parser_bounds.py \
  --case plt-valid --case mve-valid --case bam-valid --case wed-valid \
  --case bam-frame-limit --case bam-cycle-limit \
  --case spec-name --case spec-values --output valid-fixtures.json
```

`test_wall_group_contract.py` separately compiles the actual early portion of
`AREImporter::GetMap` with dependency adapters. It checks that an unopened WED
or empty wall-group result is rejected before requesting a tile map, while a
valid group table proceeds. The final loader installs the saved table, rather
than making a second unchecked parse call. This is a loader-prefix contract
check, not complete area loading or rendering.

The supported BAM frame/cycle boundary cases use 65534. AnimationFactory
reserves 65535 as its invalid-index sentinel and requires counts below it.

The compatibility adapter includes the production image-size helper and mirrors
the current checked Seek/bool Blit and point/size-constructor signatures. An
isolated source overlay can use `--fallback-root` to supply unchanged production
sources from a complete checkout. Fixture inputs and expectations are retained.

The runner can also select its existing bounded rejection/edge cases with
`--case`. The optional `--baseline` mode reads a Git ref without changing the
checkout. It is for diagnostic comparison, not a passing acceptance gate.

The JSON receipt records normalized production-source hashes, per-case results,
compiler and the evidence boundary. A later source change requires fresh
validation; historical receipts must not be described as checks of a newer head.
