# Root taskbook addendum 05: repair the C5_VAL48 identity gate

This addendum follows TASKBOOK_ROOT_v1 and ADDENDA01–04, the frozen MLP15 checkpoint, and the prior C5_VAL48 score attempt. It records a narrow continuation because that attempt stopped on scene identity metadata before reading any VAL log or command arrays: 0 scenes and 0 events were scored. Preserve its marker, empty progress file, failure report, and all original source data.

## Frozen candidate and score contract

- Candidate checkpoint SHA-256: `9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74`.
- MATLAB weights SHA-256: `dfbad11dbc7ed19b42d3b536bb4b019cbf29209d69c904b0b5000a168af58819`.
- Keep the existing C5_VAL48 scene list, source-file hashes, evaluation rules, TRAIN-only normalizers, zero-residual baseline, and event/causality contract. Do not change model, weights, thresholds, labels, or score definitions.
- The old C5_VAL48 diagnostic directory is immutable. All repair artifacts go under a new `C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR01` directory.

## Required metadata-only identity audit

Before opening any numerical VAL arrays, inspect all 48 source rows and verify file SHA-256 values and exact identities using the frozen C5 source lock and the existing compatible V1 builder contract. The cohort may contain V1, V2, and V3 identity layouts, plus canonical/raw `_ACC_FIX_V1` aliases.

- For fresh rows, require the raw and run_start external identity fields to match the source-lock `external_identity_sha256`; require scene ID, candidate, and coordinate mask to match the lock.
- For reused C5 rows, bind the source-lock external identity through the exact locked same-scene B source and C5 reuse record. Validate status candidate/mask, canonical and raw scene IDs, B raw path/hash, payload-review SHA format, and the precise parent audit evidence required by the existing compatible builder. Do not interpret `payload_review_sha256` as an external identity or use it as a substitute.
- Accept a source/raw scene alias only when the canonical ID matches the frozen scene ID and the locked status and audit permit that exact alias. Do not normalize or infer IDs from filenames.
- Verify run_start identity metadata agrees with the permitted raw/status identity branch. The audit must read only HDF5 identity groups and status/lock JSON; it must not read `log`, command, state, label, feature, or score arrays.
- Any missing, conflicting, or unbound field fails closed. Produce a per-scene 48-row audit table and bind the audit script/output and all source locks by SHA-256.

## Isolated repair and conditional score

Create a new scorer or a narrowly isolated identity adapter under `C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR01`; do not edit the frozen TRAIN builder, original scorer, input MAT files, or any prior output. The adapter may change only source identity validation. Reuse the frozen label builder and scoring logic unchanged. Run a metadata-only preflight first; it must report all 48 identities PASS, no numerical VAL read, no TEST access, no Plant, and no training.

After root reviews the 48-row audit, code, lock, and preflight hashes, exactly one numeric C5_VAL48 offline diagnostic may run under the frozen evaluation rules. It may read the locked VAL numeric arrays only for this one score. It may not fit, tune, select, or normalize the candidate; rerun B/C5; access TEST; or call Plant. Stop after the score receipt for independent root review. C5_VAL48 remains reused validation evidence, not independent test evidence.

No closed-loop run is authorized by this addendum. Root must decide separately after reviewing the offline score.
