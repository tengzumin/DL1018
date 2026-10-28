# Root review: C5_VAL48 metadata repair and preflight

Date: 2026-10-27 (Asia/Shanghai)

## Findings

- The failed original score attempt is correctly recorded as fail-closed before numerical data: 0 scenes and 0 events scored. Its start marker and failure report hashes still match the frozen values. This is an identity-interface failure, not evidence for or against MLP15 attitude performance.
- The REPAIR01 adapter accepts only the three identity layouts present in the frozen 48-scene cohort: 11 V2 rows, 36 V3 rows, and one legacy V1 reused row. It binds fresh rows to the C5 input lock and batch status, and reused rows to the exact parent audit plus the same-scene B sources. `_ACC_FIX_V1` aliases are accepted only with the locked canonical scene ID. `payload_review_sha256` remains separate from external identity.
- Static review of the adapter confirms it opens only status/lock JSON and whitelisted `/runIdentity` and `/runStart` identity fields, plus the three-value coordinate-mask metadata. It does not access `/log`, scene commands, state, features, labels, or score arrays. The scorer wrapper performs identity audit and the frozen scorer's metadata-only preflight; it creates no score-start marker and has no score execution path.
- The 48-row mapping has 48 unique scenes, 16 locked aliases, 12 reused rows, and 36 new rows. All 144 raw/status/run_start SHA-256 values match the source freeze. The repair manifest's six artifact hashes and all 30 bound-input hashes were independently checked and match.
- The preflight receipt reports 48 sources and 144 identity-file checks, with `numeric_VAL_arrays_read=false`, `score_start_marker_created=false`, `TEST_accessed=false`, `Plant_called=false`, and `training_run=false`.

## Decision

Approve the isolated REPAIR01 identity adapter and metadata preflight. Approve one numerical C5_VAL48 offline diagnostic under ADDENDUM05, using the unchanged checkpoint, labels, event timing, score rules, and zero-residual baseline. Keep the preflight lock immutable. A separate execution script/lock must bind this review and the approved inputs; root must inspect its final hashes and confirm it can execute only that one offline score before launch. No model fitting, tuning, TEST access, B/C5 rerun, Plant call, or closed-loop run is approved here.

The result of the approved score will still be a reused-validation generalization diagnostic, not closed-loop evidence. The MLP15 candidate has not yet been shown to improve attitude behavior.

## Bound artifacts

- Addendum05 SHA-256: `c021b25451677458c7e4e750b4bc502ebaa6b62470c6b86e320e541c784b35b5`
- Repair adapter SHA-256: `92c92b08615d28ddbeba9222840ba26609bc3fa390705272b130a1cea03420d4`
- Metadata-only wrapper SHA-256: `0175b2027cdc11f6291fd15b76f7dd12a8c90d5253bb9dd4b026dcb3e394eabc`
- Repair lock SHA-256: `6472c1f0381d1d161dd001c0f89935bbf073540970dbf0e363ee2a2fd9518305`
- Metadata audit JSON SHA-256: `1f0397b2acb7833e30c0cf27539ae73cc27c5d69da756833dd7271f974c1bf05`
- Mapping CSV SHA-256: `02cf9fa543c7bd2428a9046ac3b364c7a2012505e7e7a5f837671b2770938c83`
- Preflight receipt SHA-256: `23a374099aeef8e124e98f963a2f89f11f596289ca843ab319a52710fc34c5f1f`
- Repair hash manifest SHA-256: `67cb41656a3926006b65fb06d0ef6a4e76cbe393fdd498a21c5e92e9cd931a17`
