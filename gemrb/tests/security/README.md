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
  --case spec-name --case spec-values --output valid-fixtures.json
```

The runner can also select its existing bounded rejection/edge cases with
`--case`. The optional `--baseline` mode reads a Git ref without changing the
checkout. It is for diagnostic comparison, not a passing acceptance gate.

The JSON receipt records normalized production-source hashes, per-case results,
compiler and the evidence boundary. A later source change requires fresh
validation; historical receipts must not be described as checks of a newer head.
