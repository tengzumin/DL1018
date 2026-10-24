# Recovery288 statistics utility — CODEONLY taskbook (draft for root review)

## Scope and pinned inputs

Create exactly one independent statistics source after this taskbook is approved:

`reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1/statistics_v1/test48_statistics_recovery288_v1.py`

Frozen source to copy: `reports/paper_continuation_20261023/test_statistics_v1/test48_statistics.py` (SHA-256 `5a5e102f57d48ff60e83404606baf306a9a7d7160304919e98dc4f57eb7cbd08`). The new source consumes only a completed JSON emitted by the isolated Recovery288 reader, whose current SHA-256 is `a709201623d9e9f0e4b312946a1db35021bd5aa379c9f7ca04af3147e4be79d0`. Recovery release SHA-256 is `97721e4ded2f7f8224aa6720e89302fa64e805244282ab1d3a87c35f283ed397`; scope SHA-256 is `2480b9ac36eaa608a090c312ce2f3d63f37b3830c5054912e559fae720dc1a95`.

The new script must use ROOT `Path(__file__).resolve().parents[5]`, bind the existing score contract/freeze/scorer to their frozen hashes, and verify the Recovery288 reader SHA. It must not change the old statistics source, contract, reader, or any test data.

## Exact numerical preservation

Copy these frozen constants and numerical/summary routines from the old statistics source verbatim, with no parameter or arithmetic edits: `METHODS`, `CANDIDATE`, `PRIMARY_Q`, `TIE_TOL_M`, `SENSITIVITY_M`, `BOOTSTRAP_REPLICATES`, `BOOTSTRAP_SEED`, `CI_GROUP_ORDER`, `BANDS`, `BASE_SCORE_FIELDS`; `parse_scene_id`, `numeric_scalars`, `quality_scalars`, `group_members`, `wlt`, `mean_metric`, `group_summary`, `bootstrap_indices`, `bootstrap_cis`, `_quality_failure`, `integrity_report`; and all numeric calculations in `analyze_payload`.

Allowed numerical-source changes are limited to the input validator and the returned output envelope/provenance disclosure. No statistic, group, W/L/T tolerance, sensitivity threshold, bootstrap seed/order/count, or inclusion rule may change. Keep the existing synthetic self-check values and calculations.

## Required Recovery288 input guard

The statistics CLI must reject any input unless all of these checks pass before computing summaries:

- Top-level `schema == "RECOVERY288_RAW_IDENTITIES_PHYSICS_ALL_METHODS_V1"`, `status == "PASS_RECOVERY288_RAW_IDENTITIES_PHYSICS_WITH_DSSM_HISTORY_DISCLOSED"`, `TEST_accessed is True`, `plant_calls == 288`, `training_steps == optimizer_steps == 0`, `scene_count == 48`, and `method_count == 6`.
- `methods_order` equals the frozen six-method tuple and `rows` contain exactly one row for every one of the 48 distinct `scene_ids` × six methods (288 unique pairs); each row has the frozen score fields, identities, `STABLE`, no safety stop, `complete is True`, and `actuator_finite_complete is True`. Preserve the existing task/wind coverage and paired external-identity checks.
- `provenance.original_DSSM_natural_os_exit == "UNKNOWN"`; both `provenance.original_DSSM_full_48_OS0_gate` and `provenance.recovery208_run_release.legacy_six_process_OS0_gate` equal `"UNMET_DO_NOT_RECLASSIFY"`. Require the timing-qualification disclosure to match those values. Any claim that the old DSSM OS0 gate passed must be rejected.
- `provenance.recovery208_process_receipts` contains exactly one natural exit-0 receipt for each block `DSSM_TAIL16`, `KAN`, `C5M110`, `C5FREEZE`, and `C5NOPRED`, with no duplicate or missing block. Bind those receipts to the pinned Recovery208 release SHA. This five-receipt check does not replace or reclassify the original DSSM process.
- Require the Recovery288 event ledger to declare the expected C5 scope and exactly 144 unique scene/method audit rows, each `STABLE` with 1,968 events and total `144 * 1,968`. Require the actuator ledger’s 288-row finite/complete declaration and all per-row safety/completeness fields to pass. Require the top-level learned_initial_weight_integrity ledger’s 96 expected rows to pass; each row uses method for its method ID. Refuse inconsistent ledgers.

The new output must have its own Recovery288 statistics schema/status, carry the input SHA and source bindings, and repeat the original-DSSM `UNKNOWN` / legacy-gate `UNMET_DO_NOT_RECLASSIFY` disclosure. It must state that statistics computation is not an old six-process OS0 pass, and keep `paper_gate_or_goal_decision` non-automated.

## Paths and execution boundary

Accept input only from the sibling `raw_review_v1` directory. Require the requested output to resolve directly inside this new `statistics_v1` directory and refuse an existing output (exclusive create). The source and its self-check must never open MAT/HDF5, TEST raw, model weights, or score source data; the production CLI only reads the supplied JSON plus pinned source/contract files. Do not run the production statistics CLI for this CODEONLY task.

## Synthetic-only checks

Implement an in-memory self-check (no file output) that confirms: the copied numeric self-check still passes; legacy old PASS schema is refused; wrong Recovery288 schema/status is refused; old-gate PASS or original exit other than UNKNOWN is refused; each missing/duplicate/nonzero-exit receipt case is refused; missing/duplicate scene-method pairs are refused; bad event counts/scope, failed safety/actuator flags, and wrong corrected-W0 ledger counts are refused. The valid synthetic envelope must have 48 synthetic TEST-shaped scene IDs and deterministic synthetic metrics only; never use real row IDs or measurements.

## Delivery boundary

Deliver only the new Python source and this approved taskbook in the new directory. Report the final source SHA, hashes of the protected numeric regions, AST result, and synthetic check summary to the root. No production statistics run and no raw/score reads are authorized here.
