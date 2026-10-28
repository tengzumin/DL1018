# Root taskbook: force-to-attitude yaw convention audit

Date: 2026-10-27 (Asia/Shanghai)

## Decision

Approved for one read-only offline diagnostic on the 28 existing W09–W14 scenes, Candidate and C5 trajectories only. The check addresses a source-level convention mismatch: `baseline_force_to_attitude` documents a reference yaw, while the closed-loop callers pass actual state yaw and then replace the returned yaw with the desired reference yaw.

## Frozen inputs and scope

- Use only the 56 Candidate/C5 raw files already listed in `reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2.csv`.
- Verify each path is inside this repository and each raw file SHA-256 matches the locked identity row before reading it.
- Read only state yaw, logged `command_filter_target_euler`, logged `raw_outer_attitude`, reference acceleration/yaw, and time grids.
- Reuse the previously verified task attitude definition: gravity `9.8 m/s²`, tilt cap `30°`, desired reference yaw. Confirm command target tilt remained below the cap before using the inverse direction mapping.

## Single question

For the same logged commanded-force direction, how much does composing roll/pitch from actual yaw and then attaching desired yaw rotate the implied thrust axis away from the direction requested by the position controller? Re-express the inferred body-z direction using the desired yaw, then compare the logged target and this algebraic corrected target against the external task attitude. Report equal-scene macro RMSE, per-scene values, yaw mismatch, and target displacement.

The corrected target is a same-state algebraic diagnostic only. It does not propagate the plant, and it cannot establish closed-loop performance or a causal share of the 20-second score. No commanded acceleration is reverse-engineered from Plant truth; the force direction is reconstructed solely from the logged target Euler angles and logged actual yaw. No inertia, wind, or Plant truth is read.

## Limits

- Zero MATLAB, Plant, optimizer/training, and TEST access.
- No production source/model/config/raw changes, no raw copies, no baseline reruns.
- All new files stay in this isolated directory; output cap 1 GiB.
- Do not call the yaw convention an implementation bug until the convention and quantified same-state effect are reviewed. If the diagnostic is material and points toward the external task, prepare a separate one-factor candidate patch taskbook and a small closed-loop screen; do not patch or fly in this stage.

## ROOT approval

The primary reviewer approves the above offline scope. Next action is to run the isolated Python diagnostic, independently inspect its raw identities and calculations, then decide whether to prepare the closed-loop patch taskbook.
