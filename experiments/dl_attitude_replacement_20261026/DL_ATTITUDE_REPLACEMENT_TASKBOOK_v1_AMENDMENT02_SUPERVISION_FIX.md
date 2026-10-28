# Taskbook Amendment 02 — teacher-action supervision and nominal-signal alignment

Date: 2026-10-26 (Asia/Shanghai). This amendment corrects the data contract after the VAL48 audit documented in `SUPERVISION_TARGET_ROOT_CAUSE_v1.md`. It changes no DEV/TEST scene IDs, success thresholds, Plant assumptions, or safety gates.

## Superseded v1 items

For the DL attitude head only, supersede taskbook v1's residual target and the `alpha_bs_body` training feature. The current `training_v1_retry01` is preserved as a diagnostic run with mismatched supervision; it is not a valid RBF-replacement candidate and must not enter Plant evaluation or paper performance tables.

## Corrected candidate contract

- **Inputs (13):** wrapped BS attitude error (3), body rate (3), BS nominal body torque before learned compensation (3), and four current morph commands (4). Training uses `attitude_bs_nominal_torque_Nm`; runtime uses the matching `attitude_bs_step` `nominal_moment`. No `cfg.plant.inertia` conversion is used to manufacture an input feature.
- **Target (3):** B's logged `rbf_output_raw` at the 100 Hz attitude event, in `rad/s²`, pre-beta and after the RBF's existing output limit. This is behavior distillation of the action being replaced, not a physical residual label. Do not read the RBF weights or hidden state as network inputs.
- **Runtime:** frozen causal TCN output remains `rad/s²`; use the frozen C5 fixed-controller `J0` only for the existing `J0 * beta * clip(output)` torque interface. `J0` must equal `controller_parameters(cfg, simulation_parameters(cfg, arm_initial, 0), 'fixed').inertia` and be SHA-locked. Do not read `cfg.plant.inertia` as controller `J0`.
- No time-varying inertia reconstruction, `Jdot`, Plant truth, explicit observer, online TCN update, or RBF runtime dependency. Existing fixed BS/RBF output bounds and startup beta remain unchanged.
- Reuse the same 768 TRAIN and 48 VAL B raw files; no new B/C5 collection, no TEST access. Fit normalization on TRAIN only and select the checkpoint on teacher-action VAL48 scene-macro RMSE.
- Keep the 13→3 Causal TCN, 15-event causal window, seed `2026102001`, and 60,000 optimizer steps. Run at most one GPU job at a time. The corrected release, dataset, trainer and model must use new immutable v2 paths; do not overwrite v1 files or artifacts.

## Execution order

1. Let PID 23108 (`training_v1_retry01`) reach a terminal state without interruption. Preserve and label it diagnostic-only.
2. Build a new versioned TRAIN/VAL dataset from existing raw files with the corrected feature/target contract. Verify all source hashes, scene ordering, event alignment, no TEST access, and the teacher torque relation `tau_teacher = J0 * beta * rbf_output_raw` on VAL48.
3. Freeze corrected dataset, trainer, runtime feature adapter, taskbook amendment and source lock. Run Python/MATLAB forward parity plus no-Plant static and causal/safety checks.
4. Only after the existing GPU job ends and those checks pass, start one corrected training job. Do not start a second GPU job concurrently.
5. Use only its best VAL teacher-action checkpoint for six GHP7 pilot calls after the usual lock audit. DEV72 and TEST48 remain behind the unchanged taskbook gates.

This correction does not claim that teacher imitation is a new control theory contribution. The paper claim remains an application result that must be earned by the frozen closed-loop and independent-test evidence.
