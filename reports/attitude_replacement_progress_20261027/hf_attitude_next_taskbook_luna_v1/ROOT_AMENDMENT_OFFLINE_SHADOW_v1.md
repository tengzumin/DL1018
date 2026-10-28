# ROOT amendment: bounded C5 weight snapshots

Date: 2026-10-27 (Asia/Shanghai)

## Decision

I approve a narrow amendment to the C5 native replay gate in `HF_SAME_STATE_SHADOW_DIAGNOSTIC_TASKBOOK_v2_ZH.md`. The approved diagnostic remains read-only and offline: the same 28 DEV/VAL scenes, no TEST, no MATLAB, no Plant, no training, no raw copying, and no production edits.

## Evidence and revised parity gate

The C5 `rbf_event_audit` is capped at eight stored event snapshots per raw file, while the per-step raw logs retain the full attitude event schedule. A metadata inspection of both the locked reuse scene `DL1018_VAL_T1_C02_W09` and new scene `DL1018_DEV_T1_C10_W09` confirmed 8 audit snapshots (`time/dt: 8`, `input: 6x8`, and weight tensors `81x3x8`). The field `rbf_event_count` remains a separate total event count and must equal 1,999.

For each of the 1,999 events, the replay must still verify event/update flags, time and update intervals, six-dimensional RBF input, clipped and unclipped output, applied/held torque, and weight norm against the raw per-step records using the taskbook tolerances. Reconstruct the full C5 weight recursion from zero initialization. For every snapshot actually stored (the first eight in these files), compare audit time, dt, input, output, `W_before`, `W_dot`, `W_unprojected`, and `W_after` against that replay. Record the stored snapshot count and explicitly disclose that full weight matrices were not logged for the remaining events; do not describe those missing snapshots as directly observed.

Any full-step or available-snapshot mismatch remains a scene-level `FEASIBILITY_ONLY` failure. This amendment does not promote C5 `run_status`, change a controller, or authorize any closed-loop run.

## Prepared snapshot identity clarification

There are two distinct prepared snapshots in the frozen lineage. `LOCKED_CFG.json` binds the candidate's C5-derived cfg snapshot `C5_DEV72_PREPARED_CFG_OPTS_v3.mat` (SHA-256 `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a`). `C5_DEV72_INPUT_LOCK_v3.json` binds the C5 run snapshot `C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat` (SHA-256 `e417b56e68a73f7af6f40a5e7928631db1b4f3c05de1c3abd24828053760749d`). The offline replay must use the C5 input-lock snapshot for C5 cfg/opts, hash-check both files, and compare the controller-relevant fields across them before use. A read-only decode confirmed equality for Plant `dt`, command-filter parameters, attitude BS gains, RBF centers/scales, the default width behavior, adaptation limits, fixed morphology, formal RBF flags, and RBF gamma scale. Any relevant mismatch stops the run.

## Additional implementation requirements

- Verify the actual SHA-256 of `RELEASE.json`, `LOCKED_CFG.json`, the candidate model, C5 position model, C5 effective config, and every approved input listed in the taskbook before replay.
- Check candidate raw `gru_stream_attitude_model_sha256` against the frozen model identity.
- Include GRU event time/sample and beta checks, and report beta-scaled residual differences as well as torque differences.
- Preserve scene-local pass/fail details in the output when a gate fails.

