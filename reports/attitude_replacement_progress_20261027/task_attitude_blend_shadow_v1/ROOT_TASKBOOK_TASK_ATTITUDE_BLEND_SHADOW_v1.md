# ROOT taskbook: fixed SO(3) task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)
Status: approved for one offline shadow under `ROOT_APPROVAL_v2.md`; corrected script execution is separately gated by `ROOT_SCRIPT_REVIEW_v2.md`.

## 1. Decision question

Determine whether one pre-registered, deployable reference-attitude blend materially closes the high-frequency Candidate's task-to-filtered-attitude gap to B on the already recorded W09–W14 trajectories. The result is an offline same-state shadow only. It decides whether a small, isolated closed-loop screen is worth authorizing; it cannot demonstrate closed-loop improvement.

The sole tested coefficient is **beta = 0.25**, chosen from the already reported path gap before any blend replay: Candidate task→filtered is 60.537 mrad versus B 57.361 mrad (+3.176 mrad), while Candidate inner filtered-reference→actual is already 1.689 mrad better than B. Candidate task→position-generated command is 75.924 mrad versus B 58.266 mrad (+17.658 mrad). The separate yaw-convention audit measured only −0.000241 mrad change in Candidate task-target error, so yaw correction is not the target of this diagnostic.

## 2. Frozen scope and inputs

Use exactly the 28 W09–W14 scene IDs and the 56 Candidate/C5 raw files (one of each method per scene) selected from:

- `reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2.csv` — SHA-256 `71f3d159954198a066ef8cc00151e07a90ef4de92f216db6990a07da045c2c1a`.
- `reports/attitude_replacement_progress_20261027/yaw_target_semantics_diagnosis_20261027_v1/RESULT_v1.json` — SHA-256 `4a5d9230e8bf407da93d1a3912f13a1021e5ba3c9cef2a468c1a155692c3dff4`.
- `reports/attitude_replacement_progress_20261027/yaw_target_semantics_diagnosis_20261027_v1/INPUT_RECHECK_v1.json` — SHA-256 `7873fa9fda44349d6a142c27d14294498e099b1d403a1341b19ecab9e742d793`.

Before opening any raw, require the identity CSV, prior diagnostic result, and recheck file hashes above to match; then require exact equality of the 56 `(scene_id, method, raw_path, raw_sha256)` rows against the prior `RESULT_v1.json`, with each raw path contained under this project and each raw hash matching. Abort on any mismatch. Do not read B raw files. The frozen B values in §1 are context from the completed, SHA-locked path report only.

Read only these fields:

- `log/command_filter_target_euler` — position-generated Euler command before the shared filter;
- `log/filtered_attitude_reference` and `log/filtered_attitude_rate` — internal command-filter state at recorded transitions;
- `log/transition_time` and `log/time` — transition timestamps plus alignment-only full time grid;
- `scene/reference/acceleration` and `scene/reference/yaw` — external trajectory reference used to reconstruct the task attitude.

Do not load `log/state`, arms, motor/actuator data, wind, Plant parameters, inertia, disturbance labels, or any other raw variables. Use the existing task convention: (g=9.8\,\mathrm{m/s^2}), max tilt (30^\circ), desired reference yaw, and the exact `Rotation.from_euler('xyz', ...)` score convention.

The reference acceleration and yaw are exogenous trajectory commands already available to the controller interface (`r`); the position-generated target is an existing outer-loop command. Both are deployable signals. Require `transition_time` to equal the first 20,000 entries of `log/time` and use the reference acceleration/yaw at those exact timestamps. `log/time` is only for alignment, never an intervention input. Do not use measured state/Plant truth, reconstructed inertia/Jhat/Jdot, hidden labels, or future-Plant values as inputs.

## 3. Single intervention

For each recorded transition, let (R_p) be the logged position-generated command and (R_t) the task attitude reconstructed only from reference acceleration and yaw using the frozen scorer equation. Form exactly one counterfactual target:

\[
R_{mix}=R_p\,\exp\!\left(0.25\,\log(R_p^T R_t)\right),
\]

using the shortest SO(3) geodesic; convert back with the same XYZ Euler convention. No coefficient sweep, no scene-specific coefficient, no filtering/smoothing of beta, and no other target or controller changes. Do not silently project or clamp the mixed target; record any max-tilt violation as a failed validity check.

Replay the existing shared second-order command filter using the exact audited recurrence in `command_filter_step.m`, seeded from the first recorded internal filter Euler/rate state for each raw. Frozen settings are `dt=0.001 s`, `wn=[18,18,12] rad/s`, `damping=[1,1,1]`, and acceleration limits `[Inf,Inf,6] rad/s^2`. First replay the original logged target and require it to reproduce the logged filtered reference/rate before computing the blended replay; otherwise abort without interpreting the counterfactual. Do not propagate the Plant or feed the counterfactual filter output back into any recorded state/controller.

## 4. Pre-registered metrics and decision gate

For each method and each scene, compute the 20,000-transition RMSE geodesic metrics, then equal-weight the 28 scene RMSE values:

1. task attitude → original position-generated command;
2. task attitude → beta=0.25 mixed command;
3. original command → mixed command displacement;
4. task attitude → original filtered reference (replay identity check and recorded baseline);
5. task attitude → beta=0.25 counterfactual filtered reference.

Also report per-scene values, transition count, time-grid match, filter replay max angle/rate residual, maximum tilt of mixed command, count/fraction of samples over the 30° task cap, and any numerical/identity failures. Do not use time samples as independent statistical units; this is deterministic replay, not an inferential test.

Primary gate for the Candidate: the macro mean task→counterfactual-filtered SO(3) RMSE must be **≤58.949 mrad**, closing at least half of the previously observed +3.176 mrad gap to B's frozen 57.361 mrad. The coefficient remains fixed even if it fails. If Candidate exceeds this threshold, or the original filter replay fails identity, or any mixed-command tilt exceeds the cap, recommend **stop; do not spend closed-loop flights on this blend**. If it passes all checks, recommend only a small isolated closed-loop screen against reused B/C5 identities; root must approve a separate execution taskbook before any Plant run. C5 results are secondary descriptive checks, not a tuning source.

## 5. Code and provenance identities reviewed

- Candidate closed-loop caller: `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m`, SHA-256 `a1b9e47992da41b49373f409d9333048b6130698d80614817d64bbc1a652ddcc`; outer target conversion/filter call near lines 1303–1306.
- Shared filter: `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/core/command_filter_step.m`, SHA-256 `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b`.
- Force-direction adapter: `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/core/baseline_force_to_attitude.m`, SHA-256 `ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039`.
- Frozen candidate config: `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/LOCKED_CFG.json`, SHA-256 `613aff59c4036ae488cb373afacb3ef1383faa970c8dcd99ffac68462cb6d95f`.
- Prior path evidence: `experiments/dl_attitude_replacement_20261026/attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/HF_W09_W14_attitude_path_diagnosis.md`; by-scene CSV SHA-256 `87e5780879b5c5ae9ff8be8eb8cae3f99700b939938239dc15c4827ee412daaa`.

The source shows the position-generated target comes from `positionInfo.commanded_acceleration` via the shared force-to-attitude adapter, then passes through the shared command filter. The blend is therefore a reference-shaping intervention, not a learned-model gain. It can improve attitude alignment while making requested attitude inconsistent with the position ring's acceleration direction, potentially worsening position tracking; this tradeoff is the reason to reject a failed offline gate before any closed-loop expense.

## 6. Prohibited actions, storage, and deliverables

- No MATLAB/Octave, Plant/closed-loop calls, optimizer/training, TEST access, B raw access, baseline reruns, code/model/config edits, or raw copies.
- Do not edit/overwrite existing results, status, ledger, protected caches, taskbooks, or raw files.
- Create any diagnostic script, status, and outputs only under `reports/attitude_replacement_progress_20261027/task_attitude_blend_shadow_v1/`.
- Maximum total new output: **100 MiB**; expected outputs are one script, one status JSON, one summary JSON, and one 56-row per-scene CSV.
- Preserve all failures and abort records. Require root to review and approve the script hash and this taskbook before execution.

## 7. Interpretation boundary

Passing this gate means only that fixed beta=0.25 moves the logged command/filter reference toward the external task on the recorded states, enough to justify a small closed-loop screen. It does not establish position performance, stability, task completion, or causal improvement in SO(3) closed-loop score. Failing the gate rejects this one blend coefficient for this cohort; it does not establish that every reference-shaping method is ineffective.
