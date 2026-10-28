# Root review: yaw reference semantics diagnostic

Date: 2026-10-27 (Asia/Shanghai)

## Review decision

**Diagnostic accepted as complete; do not promote a yaw-only patch to closed-loop evaluation.** The caller/helper yaw convention is inconsistent and should be corrected if this mapping is changed in a future isolated candidate, but the measured effect is too small to explain the high-frequency task-attitude deficit. This is a real interface-semantic defect with negligible measured impact in the audited trajectories, not the current performance root cause.

## Evidence checked

- The approved taskbook limited the work to 56 existing Candidate/C5 raw trajectories from 28 W09–W14 scenes, with locked SHA-256 identities.
- The diagnostic reports `PASS_COMPLETE`; all 56 identities were rechecked, with no Plant, MATLAB, training, TEST, inertia, or raw-copy access.
- The Python script reconstructs the commanded thrust direction from logged outer target Euler angles and actual yaw, then re-expresses roll/pitch at desired yaw. Its self-check verifies that the reconstructed body-z matches the logged force direction. The external task attitude and score convention are unchanged.
- An independent Luna xhigh review reloaded the same 56 files, checked identities and recomputed all scene summaries; it agreed with the report. The corrected-axis residual of about 8e-9 rad is numerical `arccos` precision, effectively zero.

## Reproduced macro results

| Method | Current target-to-task SO(3) RMSE | Corrected target-to-task SO(3) RMSE | Change | Current target vs requested force-axis RMSE | Yaw mismatch RMSE |
|---|---:|---:|---:|---:|---:|
| Candidate | 75.923767 mrad | 75.923526 mrad | -0.000241 mrad | 0.156660 mrad | 1.454818 mrad |
| C5 | 76.343918 mrad | 76.344182 mrad | +0.000264 mrad | 0.179272 mrad | 1.639477 mrad |

The Candidate's task-target change is only 0.241 microrad in scene-macro RMSE and is not consistently beneficial (18/28 scenes improve). The logged target-to-force-axis residual is at most 0.157 mrad RMS on Candidate and 0.179 mrad on C5; re-expression removes that residual to numerical precision. This cannot explain the roughly 4.038 mrad Candidate-vs-B task-attitude gap or establish a closed-loop gain.

## Limits and next decision

This is an algebraic, same-state target diagnostic. It does not propagate the plant or establish a causal change in the 20-second closed-loop score. Do not spend a closed-loop batch on this correction alone. Keep the old raw files and prior STOP records untouched. If the mapping is changed as part of a future candidate, use desired yaw consistently and record the convention, but test that change only as part of a separately approved, isolated one-factor candidate.

The next useful investigation is the larger pre-inner-loop gap: Candidate and C5 share force-to-attitude mapping and filter source/settings, and their inner tracking is better than B, while Candidate's task attitude loses mainly from task-to-command / command-to-filter stages. Review whether the position-generated attitude command persistently diverges from the external task attitude under high-frequency motion, then prepare a minimal fixed command-shaping/blending screen only if existing raw replay predicts meaningful benefit without using Plant truth. Any such replay remains diagnostic, not closed-loop evidence.

## Artifact identity

- Taskbook: `ROOT_TASKBOOK_YAW_REFERENCE_AUDIT_v1.md`
- Script: `diagnose_yaw_argument_v1.py`
- Summary: `RESULT_v1.json`
- Per-scene output: `PER_SCENE_v1.csv`
- Input identity recheck: `INPUT_RECHECK_v1.json`
- Status: `PASS_COMPLETE`
- Output size: 106,356 bytes
