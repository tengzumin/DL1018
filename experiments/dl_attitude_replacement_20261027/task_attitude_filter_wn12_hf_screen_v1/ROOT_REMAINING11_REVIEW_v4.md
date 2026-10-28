# Root review v4 — approve the remaining 11 filter-wn12 scenes

Date: 2026-10-27 (Asia/Shanghai)
Decision: approve exactly the 11 frozen DEV/VAL scenes in the `REMAINING11` phase, using the active `SOURCE_LOCK_v2.json` and the already frozen model/config. This approval does not open TEST, retrain, rerun B/C5, or authorize retries.

## What was checked

- Root reran `audit_engineering_gate_raw_v1.py`. It returned `PASS_METRICS_AND_IDENTITY_WITH_FIRST_OUTPUT_PATH_MISMATCH`, with zero failed checks. The candidate raw SHA is `01f826a970865eaa2596b01866321d2341749133872d30b16d4f408c22410190`; status/run-start/marker and locked payload/B/C5/model identities match. The run completed STABLE with 20,000 transitions and 20,001 states. Motor saturation, generalized clipping, tilt limiting, attitude-head projection, and head-output saturation were all zero.
- The frozen scorer results for this first engineering scene are Q = 11.659 mm (B 10.985 mm, C5 10.466 mm); task SO(3) = 42.502 mrad (B 42.201 mrad, C5 43.273 mrad); inner SO(3) = 20.140 mrad (B 23.237 mrad, C5 23.274 mrad). This single scene does not meet the aggregate performance gate and is not evidence that the 12-scene candidate passes. It is sufficient only for the predeclared engineering gate: stable execution, complete identity, and zero safety events.
- The first candidate raw was written at the scene root instead of its locked `attempt_01` subdirectory. It was not moved or copied. `run_status.json` binds the actual path and raw SHA. The path exception is documented in `PATH_RECONCILIATION_ADDENDUM_v1.md`.
- The first run refers to `SOURCE_LOCK_v1.json`; its `study_artifacts` entry records the former wrapper SHA `c1c6a67455f2e5661b2bb478ba130980aa1e52454ed5559191e892f9235ba772`, but those wrapper bytes are no longer available. The run-time RELEASE bytes were also not preserved. I therefore do not claim byte-for-byte recovery of the first run's wrapper or RELEASE. The stable raw, status, run-start, marker, run-time SHA references, and unchanged 59-file runtime source lock are retained as historical evidence.
- Root ran `validate_filter_wn12_no_plant_v2.py`; it passed 12 scene identities, all 59 runtime files, the active v2 lock covering those 59 files plus the current wrapper, 3 byte-identical preparation metadata copies, 9 external dependency hashes, the single `wn` config delta, and DRAFT/zero-authorization/TEST-false boundaries. `SOURCE_LOCK_v1.json` and `SOURCE_DIFF_v1.json` remain unchanged for the first raw. The future wrapper routes each raw from the locked `candidate_raw_path` and rejects outputs outside this study's matching scene directory.
- The 94 non-finite diagnostic dataset paths in the candidate raw have the same names, shapes, and non-finite masks as the same-scene historical parent raw. Scorer, state, filter, and attitude output arrays are finite. These legacy diagnostic placeholders are disclosed in the raw audit, not counted as scorer failures.

## Decision and limits

The changed control factor is only the command-filter natural frequency: roll/pitch 18 → 12 rad/s; yaw stays 12 rad/s. The frozen GRU base remains fixed with its online tracking-DeltaW head; RBF attitude output/update and inertia reconstruction remain disabled. No controller, model, position loop, or safety-limit change is approved here.

The first scene shows a small task-attitude loss relative to B and position Q loss relative to both B and C5, alongside better inner-loop attitude error. The fixed 12-scene screen is needed to decide whether this filter change helps in the aggregate. Do not describe the candidate as improved until the full predeclared screen passes. Do not tune parameters or change methods during this batch.

The parent GRU/head runtime has existing MATLAB replay audits; this review did not run a second MATLAB replay for the new raw. The engineering gate is approved on the taskbook's declared stability, identity, and safety criteria plus the independent raw/scorer audit above. This distinction remains in the evidence record.

## Authorized execution

Authorize exactly these 11 scenes, in this order, through `RUN_FILTER_WN12_SCREEN_EXACT_v1.ps1 -Stage Remaining11`:

1. `DL1018_VAL_T1_C07_W14`
2. `DL1018_DEV_T2_C09_W10`
3. `DL1018_VAL_T2_C04_W14`
4. `DL1018_DEV_T3_C09_W09`
5. `DL1018_VAL_T3_C01_W14`
6. `DL1018_DEV_T1_C01_W15`
7. `DL1018_VAL_T2_C05_W15`
8. `DL1018_VAL_T3_C02_W15`
9. `DL1018_VAL_T1_C00_W07`
10. `DL1018_DEV_T2_C00_W04`
11. `DL1018_DEV_T3_C00_W05`

Reuse the locked B and C5 raws. Stop the batch at the first execution, completeness, identity, or safety failure; do not retry that scene. Do not access TEST. After the batch, revoke authorization and independently score all 12 scenes against the frozen screen gates.
