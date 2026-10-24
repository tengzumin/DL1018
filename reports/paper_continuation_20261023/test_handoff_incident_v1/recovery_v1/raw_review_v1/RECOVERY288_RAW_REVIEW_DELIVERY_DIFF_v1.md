# Recovery288 reader delivery and protected-source diff

- Reader: `audit_test48_raw_recovery288_v1.py`
- Reader SHA-256: `a709201623d9e9f0e4b312946a1db35021bd5aa379c9f7ca04af3147e4be79d0`
- Base reader: `test_raw_review_v5/audit_test48_raw_v5.py`
- Base SHA-256: `1c7380abd2b1f29e0f7045017abaeef87f54d751ad74a710bfbdbdac504730ff`
- Recovery scope SHA-256: `2480b9ac36eaa608a090c312ce2f3d63f37b3830c5054912e559fae720dc1a95`
- Recovery release SHA-256: `97721e4ded2f7f8224aa6720e89302fa64e805244282ab1d3a87c35f283ed397`

## Changes isolated to this reader

The reader composes the 288 scene/method records from B48v3, the first 31 committed DSSM records, the separately disclosed scene 32 record, the recovery DSSM tail for canonical scenes 33–48, and four v9 scientific method batches with Recovery208 process receipts. It preflights the release and process receipts before opening TEST raw files. Tail records must match both canonical batch indices 33–48 and local indices 1–16; the final set must contain each of the 288 scene/method pairs exactly once.

Scene 32 is checked against the pinned no-score parent review for raw path, run-start path, and both SHA-256 values. Its missing `runIdentity` and unknown original DSSM OS exit remain explicit. The old six-process OS0 gate remains unmet and is not reclassified as passing.

## Protected algorithm comparison

The region beginning at `item_sha = str(record["raw_sha256"]).lower()` and ending immediately before `require(len(method_native) == 48` is byte-for-byte identical to the v5 base after newline normalization: 39 lines, SHA-256 `5ec49de8562e5d1aad03baa2d74bc86f152d12a943da71b5006a9f563dc3f24d`. This preserves the inherited scoring, event, and actuator audit logic in that region.

## CODEONLY checks

- Python AST parse: PASS.
- `synthetic_self_check()` called in memory on this reader: PASS; no output file was written.
- Synthetic scene 32 binding rejected wrong raw path, run-start path, raw SHA, and run-start SHA.
- Synthetic tail check rejected incorrect canonical and local indices.
- Synthetic 288 coverage rejected both a missing pair and a duplicate pair.
- Frozen v1 synthetic timing/struct checks: PASS; `TEST_accessed` was false.

No TEST raw, score, MATLAB, Plant, or training was accessed or run for this delivery. The real audit CLI remains for the root reviewer to run only after the required completion and receipt gates.
