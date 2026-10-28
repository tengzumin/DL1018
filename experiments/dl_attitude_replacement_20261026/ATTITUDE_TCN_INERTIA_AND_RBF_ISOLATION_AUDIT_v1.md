# DL_TCN inertia and RBF isolation audit

Date: 2026-10-26 (Asia/Shanghai).

## Decision

The current DL_TCN candidate does **not** use time-varying inertia reconstruction in its planned runtime path. It does retain the fixed nominal controller inertia `J0` used by the shared backstepping controller and by the TCN acceleration-to-torque conversion. The logged B attitude-RBF action is used as the **offline supervised training target**; the candidate does not call the attitude RBF for output or online updates.

This conclusion is a source-path audit, not a closed-loop execution result. The TCN checkpoint is still training, so runtime behavior and performance remain unverified.

## Evidence

- `gate_attitude_arm_spec.m` maps `DL_TCN` to the candidate paired arm and sets RBF, physics helper, feedforward, and observer flags to false.
- `make_paired_c5_options.m` clones the shared C5 position stack, then disables all three attitude-RBF flags for the candidate. `make_gate_holdout_options.m` adds the frozen TCN model without changing that paired controller.
- `run_gate_holdout_closed_loop.m` constructs `fixedController` from the configured initial arm lengths and checks it against the frozen `J0_controller_fixed_kgm2` identity. On the formal baseline path it assigns `P=fixedController`; the TCN event feature uses `ai0.nominal_moment` computed from that `P`, measured body rates, attitude error, and commanded arm positions. The separate `Ptrue` object is built from the simulated Plant state and is passed to plant/allocation dynamics, not to the TCN feature or estimator.
- The frozen dataset manifest's feature order (`attitude error ×3`, body rate ×3, nominal BS body torque ×3, commanded morphology ×4) matches the runtime feature assembly in that order.
- At an attitude event the `tcnCandidate` branch calls `tcn_attitude_step_v1` and then skips the following RBF-update branch. Its trace records both RBF output and update as disabled, and time-varying inertia reconstruction as false.
- `tcn_attitude_step_v1.m` normalizes the 13 observable features and converts the clipped TCN residual with fixed `J0` and the scheduled `beta`; it has no `Jhat` or `Jdot_hat` input.
- The existing v4 no-Plant audit report is PASS for all 49 MATLAB runner files, with `plant_invoked=false` and `test_data_read=false`.

## Method interpretation

This is teacher-distilled deep learning: B's logged `rbf_output_raw` (the RBF output after `dmax` clipping and before startup `beta`) provides training labels, while the deployed candidate replaces the RBF output/update path with the causal TCN and applies the same output clipping and `beta`. It is not independent of RBF during training, and it should not be described as a controller learned without an RBF teacher. The frozen comparison against B must establish whether the TCN generalizes well enough in closed loop to meet the position and attitude gates.

## Reviewed source identities

| Source file | SHA-256 |
|---|---|
| `runtime/gate_attitude_arm_spec.m` | `C1808F06278DAA26E7DB53C09F690CFABD9C2CE7524547F6EE793754A7373478` |
| `runtime/make_gate_holdout_options.m` | `D7AC906653D9432416EFFE51280849C339CB5B3EF607F250081BDB7851D35A63` |
| `runtime/make_paired_c5_options.m` | `543E2AE9163BDDDFACE3F1032EA2BFA1DEB71E2D1BC1A48811142A696AC3029F` |
| `runtime/run_gate_holdout_closed_loop.m` | `EC6F41038D1643D1A6795BC3117C093A02FDC20F34C8B86E6E5D83B9580F7A9A` |
| `runtime/tcn_attitude_step_v1.m` | `9EC27DC1A9226C7F64ACD26F1D0E8173FB0E1AABFB3D67D51318ABA66122F130` |
| `core/controller_parameters.m` | `4FAD5E78C0BD4177461647AF167E7C86A7DEFA628B43D523B0B7DA2EF5556398` |
| `core/attitude_bs_step.m` | `CF6B20FFC4DF2625D9316A80340D69542E380D14FEAED66EF8498E793FDACCBC` |

These hashes are this audit's source snapshot; the later release source lock remains mandatory and must match the files actually used for the pilot.
