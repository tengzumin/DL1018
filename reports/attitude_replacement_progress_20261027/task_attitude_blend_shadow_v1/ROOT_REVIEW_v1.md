# Root review: fixed task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)

## Decision

**Offline gate passes. Proceed to prepare one isolated high-frequency closed-loop screen using the same fixed beta=0.25 intervention.** This is only permission to prepare the implementation/taskbook and review them; the 28 Plant runs remain gated by a separate root approval. Do not touch TEST, do not rerun B/C5, and do not change training/model weights.

## Independent result check

The reviewed script completed `PASS_GATE` on the 28 locked W09-W14 scenes and 56 Candidate/C5 raw files. It reported exact raw identity matches, no raw copies, and no Plant/MATLAB/training/B-raw/TEST access. The first attempt is preserved in `ABORT_RECORD_attempt01.json`; it stopped at a filter-source hash typo before opening raw. The typo is corrected and the approved rerun completed.

I independently recomputed equal-scene means from all 56 rows in `PER_SCENE_v1.csv`:

| Method | Original task→filtered | Beta=.25 task→filtered | Change | Mixed task→command | Command shift |
|---|---:|---:|---:|---:|---:|
| Candidate | 60.537174 mrad | 45.522496 mrad | -15.014678 mrad | 56.942825 mrad | 18.980942 mrad |
| C5 | 61.112905 mrad | 45.954468 mrad | -15.158438 mrad | 57.257939 mrad | 19.085980 mrad |

Candidate's pre-registered gate was 58.949 mrad, so the 45.522496 mrad replay clears it by 13.426504 mrad. All 28/28 Candidate scenes and 28/28 C5 scenes reduce the task-to-filtered-reference RMSE in this same-state shadow. Original filter replay residuals were at floating-point scale (maximum angle 6.4e-16 rad and rate 4.94e-15 rad/s). No blended command exceeded 30° tilt; the largest was 16.3432° for Candidate and 16.3921° for C5. Total files in the isolated directory remain about 54.5 kB, far below 100 MiB.

## Interpretation and boundary

This is a deterministic same-state command/filter replay. It does **not** show actual vehicle attitude or position improvement: the Plant was not propagated, and recorded state/controller trajectories were not fed back from the modified target. The roughly 19 mrad command shift could materially disturb the position ring, so position-Q is a mandatory closed-loop check.

The result is strong enough to justify one 28-scene W09-W14 Candidate-only closed-loop screen against already-frozen B and C5 scores. The screen must preserve the existing GRU attitude module, C5 position module, Plant, references, seeds, filter limits, and all other parameters; change only the task-attitude target by beta=0.25 shortest-geodesic interpolation. Log both original and mixed targets. Require complete safety/actuator checks and report paired position Q plus SO(3) task attitude against B/C5. No TEST access or baseline reruns. A full DEV72 run can be considered only after root reviews the 28-scene candidate results.

## Evidence and provenance

- Taskbook: `ROOT_TASKBOOK_TASK_ATTITUDE_BLEND_SHADOW_v1.md`
- Taskbook amendment and approvals: `AMENDMENT_source_hash_v1.md`, `ROOT_APPROVAL_v2.md`, `ROOT_SCRIPT_REVIEW_v2.md`
- Script: `diagnose_task_attitude_blend_shadow_v1.py`
- Script hash: `ed523cfed9bfd088ccb75faf43f3490a477802332090380de3ef63dc0f76da9f`
- Outputs: `STATUS_v1.json`, `RESULT_v1.json`, `PER_SCENE_v1.csv`
- Frozen beta: `0.25`; frozen gate: Candidate task→filtered RMSE `<=58.949 mrad`
