# Taskbook: beta=0.25 task-attitude blend, HF28 candidate screen

Date: 2026-10-27 (Asia/Shanghai)
Status: **APPROVED for exactly one 28-scene candidate-only HF screen** under `audits/ROOT_REVIEW_HF28_RELEASE_DECISION_v1.md`. Expansion beyond this screen and all TEST access remain gated by a later root decision.

## Decision question

Does one fixed, deployable SO(3) blend between the C5 position-loop-generated attitude command and the same-step trajectory task attitude improve high-frequency closed-loop attitude enough to beat both frozen B and C5, while keeping position error below B and within 5% of C5?

This is a 28-scene development screen. It is not independent test evidence and cannot support paper claims by itself.

## Frozen intervention

The stack is GRU_STREAM attitude replacement plus frozen DSSM14/C5 M110 position loop, fixed J0, the same Plant, initial conditions, references, GRU weights, online tracking-head rule, update clock, command filter, safety limits, and actuators. There is no training or parameter search.

At the active GRU_STREAM path, the original target is `target_unblended = [eul_position(1:2); r.euler(3)]`, where `eul_position` comes from `positionInfo.commanded_acceleration`. The exogenous task reference is `taskEuler=baseline_force_to_attitude(r.acceleration,r.euler(3),P)`. Only trajectory-reference acceleration and reference yaw are used. `r.euler(1:2)` are zero in `reference_row`; do not use them as task roll/pitch. No measured Plant state, inertia reconstruction, Jhat/Jdot, or hidden label enters the blend.

The one changed active command is shortest-geodesic interpolation on SO(3): `Rmix=Rpos*exp(0.25*log(Rpos'*Rtask))`, using physical aerospace ZYX orientation represented by [roll,pitch,yaw]. The mixture becomes the target sent to the existing `command_filter_step`. Beta is fixed at 0.25. The GRU, its online tracking head, the DSSM position controller, Plant, filter, limits, and weights are unchanged.

The isolated runner changes only the general main-loop target callsite near line 2392, guarded by `if gruStreamCandidate`. Only GRU_STREAM computes and logs the beta=.25 blend; every other method passes its original target through unchanged and leaves blend-only logs NaN. The MLP/TCN callsite near line 1309 and the other method branch near line 1808 are unchanged and inactive for GRU_STREAM. The preview target near line 2047 remains unchanged; the candidate route asserts `~isNetwork && ~adaptiveBasisActive && method=='B2-RBF-Full-SPLIT'`, so that adaptive preview branch is unreachable. Preview therefore keeps the original trajectory target; it is not fed into the active controller or blended path. The candidate raw records original and mixed target, task target, and beta each transition.

## Cohort, input locks, and reuse

Run exactly the 28 scene IDs in `HF28_EXECUTION_MANIFEST_v1.json` (W09-W14, sorted by scene ID), once each. `HF28_INPUT_MANIFEST_v1.json` binds payload paths/hashes, external identity, and frozen baseline score values. The execution manifest adds B/C5 raw paths/hashes strictly for scene-only pair validation. No baseline is rerun, and no B/C5 score is recomputed.

The baseline score source is `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/FULL72_PAIRED_SCORE_v1.csv`, SHA-256 `dfbc732ee97e770ea328d8eeac7efd203f06502cfa56d2ab9a11a74998b66630`; source JSON SHA-256 `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff`. B provenance remains incomplete and 60 C5 raws remain parent-audit-pending, so the comparison is provisional.

### Raw access exception for read-only pairing

For each matching B/C5 raw file, the preflight may hash the file and load only the `runIdentity` and `scene` variables. It may inspect only `runIdentity.scene_id`, `runIdentity.external_identity_sha256`, and `runIdentity.TEST_accessed`. B must include and match all three fields. Some legacy C5 raws lack `external_identity_sha256`; for C5, `scene_id` and `TEST_accessed` are required, and any present external identity hash must match. A missing C5 hash is recorded as an attestation gap, never inferred. Pairing still requires exact equality of the allowed `scene` fields `time`, `initial_state`, `reference`, `arms`, and `environment_wind_I` against the locked payload. It must not load `log` or any other raw variable, inspect other `scene` fields, read controller/state/motor/actuator/diagnostic outputs, derive metrics, or rescore baselines. The first preflight found this legacy-field gap at `DL1018_VAL_T1_C02_W09`; the amended bounded rule is recorded in `HF28_PAIR_PREFLIGHT_ROOT_REVIEW_v1.md`.

The existing `prepare_mlp15_dev72_no_plant` reads the bound B raw SHA and only `runIdentity.external_identity_sha256` and `runIdentity.TEST_accessed`; it also reads the existing status/metadata JSON and locked payload/config/model inputs, including its inherited MLP15 preparation asset. The attempt then replaces those options with the locked GRU_STREAM model/options before the candidate call; it performs no MLP inference or training. It does not read B raw `scene`, `log`, or controller trace. Root should reject the driver if code review finds any raw access outside the allowlist above. TEST remains sealed.

The batch selects candidates only from the frozen 28-scene execution manifest. The existing prepare helper also reads its parent 72-scene metadata manifest to bind the selected payload/B identity, plus the locked C5 snapshot/model and frozen GRU model by absolute path and SHA. No MAT, model, or payload is copied. Candidate raw/status/marker/log outputs go only to this study's new `runs_beta025_hf28` directory. The successful read-only pairing receipt is locked under `audits` before release; the batch validates that receipt without overwriting it. Each attempt rechecks its selected payload, B raw, and C5 raw SHA immediately before its closed-loop invocation.

## Pre-registered screen

Use all 28 paired scenes with equal-scene macro means. Advance to a separate root decision for full DEV72 only if every gate passes:

- HF position Q macro mean is strictly lower than B and at most `1.05 x C5_Q`.
- HF task attitude SO(3) macro RMSE is strictly lower than both B and C5.
- Every candidate flight has exactly 20,000 transitions, `status=STABLE`, empty/`none` `safety_stop_reason`, and finite logged state/reference/control values.
- Motor saturation, generalized clipping, tilt limiting, attitude-head projection, and attitude-head output saturation are each zero in every flight. Any nonzero count fails the screen.
- Report controller-call time p50/p95/max against the 1 ms sample period. Wall time alone is not a failure gate.

Report every scene, paired Q and task SO(3), exact deltas, win/loss/tie counts, all safety/actuator counts, controller timing, and failures. Retain failed attempts and never rerun a scene. The 5% position allowance is only an engineering screen before DEV72; it is not a paper acceptance threshold. Do not remove scenes, tune beta, or open TEST based on these results.

If all gates pass, stop and return to root before DEV72 expansion. If a score or safety gate fails, keep all outputs and stop this beta=.25 direction.

## Candidate-only scoring protocol

The isolated scorer score_beta025_hf28.py calls only the frozen full72 scorer function score_raw(candidate_raw, gravity=9.8, max_tilt=0.5235987755982988). Frozen source: experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py, SHA-256 6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16. Gravity/tilt constants are inherited from experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json, SHA-256 507f9a13af2d20aca64a08ea7846991198112bd97ca8456dccb9402ec9424862; max_tilt=0.5235987755982988 rad is 30 degrees.

The new scorer reads only each new Candidate raw, its same-attempt `run_start.json`/`run_status.json`, and the B/C5 numeric Q/task-SO(3) values in `HF28_EXECUTION_MANIFEST_v1.json`. It requires the Candidate `runIdentity` group, binds the sidecar scene/candidate/split and locked release/manifest/code/model/payload identities, and verifies the raw file's SHA against `run_status.json` before scoring. It verifies and imports the frozen scorer module, then calls `score_raw` only; it does not call that module's `validate_release()` or `main()`. It never opens B/C5 raw files, reads no baseline raw log, and computes no B/C5 metrics. Pair outcomes use the frozen absolute `WIN_TOL=1e-12` on unrounded values. Macro means give each of the 28 scenes equal weight. It writes one 28-row paired CSV and one summary JSON with candidate/B/C5 macro means, exact paired deltas, win/loss/tie counts, per-scene and pooled `controller_call_time_s` p50/p95/max against the 1 ms sample period, and every safety count. Missing, invalid, mismatched, or unreadable candidate raw stays as an unscored row and fails the gate; no scene is dropped.

After the batch is complete, the exact PowerShell 7 scoring command is:
& 'C:\ProgramData\anaconda3\python.exe' 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_blend_beta025_hf28_v1\score_beta025_hf28.py'

This command has not been run. Scorer SHA-256: `ff873573093259d885577a7f2238b52bf9df50eb8f43692059a53222b72242ca`. It is locked in `RELEASE.json`.
## Isolated implementation identity

- Study directory: `experiments/dl_attitude_replacement_20261027/task_attitude_blend_beta025_hf28_v1`
- Initial 59-file MATLAB source-copy receipt: `SOURCE_COPY_MANIFEST_v1.csv`, SHA-256 `7367755aaf37b087399eb54b7d1f68c7633684e51809332b8421818796dc575a`; 738,550 bytes, no MAT copied.
- Final runner/helper changes and five new isolated MATLAB files are listed in `SOURCE_COPY_MANIFEST_AMENDMENT_v1.csv`.
- Final isolated MATLAB tree lock: `HF28_CODE_LOCK_v1.json`, SHA-256 `bf3e970661291e9c9d679d4fdc134329f69a5505f3ba3d748790c681c2021861`; 64 MATLAB files, including the guarded runner and new drivers.
- Active runner copy: `candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m`; hash is locked in `RELEASE.json`.
- SO(3) helper: `candidate_runner_work/matlab/runtime/task_attitude_blend_so3_beta025.m`; hash is locked in `RELEASE.json`.
- Prepare helper copy: `candidate_runner_work/matlab/runtime/prepare_mlp15_dev72_no_plant.m`; its only local change binds `researchRoot` explicitly to `experiments/dl_attitude_replacement_20261026`, because the new study is nested under 20261027. Its hash is locked in `RELEASE.json`.
- Payload input manifest: `HF28_INPUT_MANIFEST_v1.json`; execution manifest: `HF28_EXECUTION_MANIFEST_v1.json`; both hashes are locked in `RELEASE.json`.
- Frozen GRU model, C5 receipt/snapshot/model, source runner and all copied code hashes are recorded by absolute path/SHA in the manifests or release lock. No model or MAT is copied.

## Release and execution protocol

`RELEASE.json` records the approved 28-call budget and exact 28 HF scenes. The attempt and batch entrypoints validate the released hashes before opening payload/raw files or creating run markers. The batch validates the already-completed, locked B/C5 pair-preflight receipt and then executes one candidate attempt per scene sequentially. A single entry into the candidate closed-loop runner counts as one authorized call, including immediate failure; no baseline call is included. Any failure is retained; no automatic retries occur, and the MATLAB batch lock rejects a concurrent launch.

PowerShell 7 launch command, for use only after explicit release (not run during this preparation):

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261027/task_attitude_blend_beta025_hf28_v1'); addpath('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261027/task_attitude_blend_beta025_hf28_v1/candidate_runner_work/matlab/runtime'); run_beta025_hf28_batch"
```

Estimated load: 28 sequential 20,000-transition flights; based on prior same-runner full72 wall times, roughly 15-25 minutes including MATLAB startup and preflight. No training/GPU job. Candidate outputs are capped at 5 GiB; stop before launch if free disk space is below 30 GB. The command above has not been run.
