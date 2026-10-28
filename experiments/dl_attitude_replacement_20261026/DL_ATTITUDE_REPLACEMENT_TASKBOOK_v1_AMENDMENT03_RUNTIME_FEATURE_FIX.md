# Amendment 03 — runtime feature alignment

Date: 2026-10-26 (Asia/Shanghai).

## Finding

The v2 candidate runner did not implement Amendment 02's feature contract: its TCN feature builder used `ai0.nominal_body_angular_acceleration` for channels 7–9, while the frozen teacher dataset and Amendment 02 specify the BS nominal body torque in N·m. The input dimension remained 13, so the mismatch would not fail shape checks; it would silently send the trained network values in the wrong units and semantics.

## Isolated correction

The v2 runner and its artifacts remain unchanged. The isolated `pilot_runner_v3_teacher_distill` copy changes only those three feature channels to `ai0.nominal_moment`, matching the dataset's logged `attitude_bs_nominal_torque_Nm`. All other features remain wrapped attitude error, body rate, and current morph commands in the same order.

The TCN still predicts the logged pre-beta, limited RBF acceleration action. Runtime still applies the existing beta and dmax, then maps it through the fixed controller `J0`. No time-varying inertia reconstruction, `Jdot`, Plant truth, observer, or online update is used.

## Release gate

Before any TCN pilot, the v3 runner must pass source/hash review, MATLAB static/no-Plant checks, and a feature-order check against the frozen dataset. No Plant run is authorized by this amendment.
