# Attitude label qualification: two existing C01 scenes

## Scope and result

Read-only review of exactly two existing records: TRAIN/DL1018_TRAIN_T1_C01_W00/B and VAL/DL1018_VAL_T1_C01_W08/B. A MATLAB R2025b batch script replayed the angular-acceleration label at the 1,999 recorded attitude events using repository dynamics functions and the recorded run_start.mat configuration plus raw state, actual arm lengths/rates, realized generalized wrench, wind force, and wind torque. The script did not invoke a runner, integrate a state, or generate a Plant trajectory. No TEST data or training was used. The actual rho_true/rhoDot_true values enter only this offline label audit; both raw records show the controller-side rho_hat=0.15 m, rhoDot_hat=0 throughout.

The repository equations reproduce every stored target_raw entry exactly (max absolute replay error = 0 in both scenes). The algebraic decomposition closes to at most 7.11e-15 rad/s². This is strong sample-level support that the stored labels are internally consistent with the recorded raw simulation quantities and the current repository’s stated dynamics. “True” here means the simulated Plant’s recorded rho, inertia, wind torque, and realized wrench; it is not a hardware measurement. The replay does **not** recover the exact historical source revision that generated the raw runs: run_start.mat has the B identity/config/options and raw path but no source commit/hash, the raw MAT root has no runIdentity, and H5 has no raw-file hash. Therefore, treat these as B behavior trajectories with labels reproducible under the current pinned model equations; do not claim the old runtime source has been recovered or use them as a source-pinned C5/B causal comparison. The identity gap does not by itself disqualify the records as relabelable supervision if a future dataset export pins the current labeler, hashes raw inputs/outputs, and verifies all event rows.

## Dynamic shape and label scale

At event samples, only arm 1 moves. Its true length spans 0.15–0.22 m in TRAIN and 0.15–0.25 m in VAL; the other three arms remain at 0.15 m. The maximum absolute arm rate is 0.05 m/s. The fixed nominal inertia computed from the same distributed_v1 configuration is approximately diag(0.00325755333, 0.00325755333, 0.00636064833) kg·m² in both cases.

| Scene | max Frobenius ΔJ vs fixed nominal (kg·m²) | max Frobenius Jdot true (kg·m²/s) | target raw max abs by axis (rad/s²) | target raw vector RMS (rad/s²) | max replay error |
|---|---:|---:|---:|---:|---:|
| TRAIN T1_C01_W00 | 1.9955e-3 | 1.6606e-3 | 12.904, 12.904, 1.952 | 11.1687 | 0 |
| VAL T1_C01_W08 | 3.0550e-3 | 1.8680e-3 | 20.406, 20.406, 6.175 | 13.7570 | 0 |

For the matched per-event decomposition

~~~text
y = (alpha_true with tau_virtual) - (alpha_nominal with tau_virtual)
  + J_true^{-1}(tau_realized - tau_requested)
  + J_true^{-1} tau_wind
  + J_true^{-1}(tau_requested - tau_virtual),
~~~

the final request/virtual-torque closure term is exactly zero in both records. Per-sample components sum to the replayed label; their vector RMS magnitudes are:

| Scene | true-vs-nominal J/Jdot model component | realized-vs-requested output component | wind-torque component |
|---|---:|---:|---:|
| TRAIN T1_C01_W00 | 3.2775 rad/s² | 7.9050 rad/s² | 0.6269 rad/s² |
| VAL T1_C01_W08 | 5.3646 rad/s² | 8.4538 rad/s² | 1.0847 rad/s² |

These are same-path algebraic component magnitudes, not independent counterfactual effects or causal percentages: their vector cross terms mean squared component energies do not add to total label energy. The wind term uses the logged body torque, not an oracle wind input to any learner.

## Thrust, allocation, and clipping

At event samples, requested wrench equals controller-clipped wrench; allocated wrench differs from the clipped request by at most 1.78e-15 in the thrust channel and 3.4e-16 in any moment channel. Realized thrust differs from requested thrust by at most 1.78e-15 N, with no motor-saturated motor sample (0/7996). Yet realized roll/pitch moments differ from requested moments by up to 0.04197 N·m in TRAIN and 0.06468 N·m in VAL; yaw difference is below 8.5e-17 N·m. The realized-minus-allocated wrench has the same roll/pitch mismatch. This is consistent with the implementation: allocate_control solves motor-squared commands using the controller allocation matrix and evaluates the actual wrench with the Plant matrix ([allocate_control.m lines 18, 24](../../matlab/core/allocate_control.m:18)); the runner separately logs the nominal allocation reconstruction ([run_dl1018_closed_loop.m lines 2337–2346](../../matlab/runtime/run_dl1018_closed_loop.m:2337)). Thus the label includes meaningful action-conditioned geometry/allocation mismatch even with no command clipping or motor saturation.

target_clip equals target_raw for TRAIN. In VAL, the raw yaw-axis maximum is 6.1749 rad/s² while the clipped maximum is 4.7124 rad/s²; this review records the existing clipping behavior only and does not use VAL to choose a new limit.

## Equation, source, and run records

The replay uses the exporter definition tau_virtual = nominal_moment - applied_compensation, evaluates true acceleration with the event’s actual rho_true/rhoDot_true, and subtracts the fixed-controller virtual acceleration ([exporter lines 31–46](../../matlab/data/export_attitude_events_dl1018.m:31)). The equations are implemented in [simulation_parameters.m](../../matlab/core/simulation_parameters.m:1), [distributed_mass_properties.m](../../matlab/core/distributed_mass_properties.m:1), [controller_parameters.m](../../matlab/core/controller_parameters.m:1), and [vehicle_derivative.m](../../matlab/core/vehicle_derivative.m:1). The MATLAB result JSON records the which() paths for the physical functions actually called. Source SHA256 values and all eight event/raw/run-start/marker SHA256 values are listed in the validation receipt.

Both run_start.mat files identify B, the expected contract, scene-specific run ID/raw path, and recorded cfg/opts; the raw method field is B, and plant_started.marker records first_plant_transition=1. These establish the record/config association, not the missing historical source hash. For a new training-label dataset, the minimum practical path is to bind a source-hashed exporter and raw/H5 hashes to each scene, retain the per-event equation-closure check, and qualify the remaining eligible TRAIN/VAL records. The two-scene success alone is not a whole-split qualification.

## Execution and hashes

The only MATLAB command was:

~~~text
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "run('reports/attitude_redesign_20261024/nonzero_pair_reconstruction_v1.m')"
~~~

MATLAB OS exit code: 0. A separate MATLAB console log was not configured; the result JSON is hash-pinned in the validation receipt. The post-hoc Python JSON threshold check also exited 0; it did not rerun MATLAB. The threshold was 1e-8 rad/s² for replay error and decomposition closure, both passed.

- Replay script SHA256: F455BB80ACE5E2149AB84F56B1330C115C3217212CBB5CF545C4B0873E75C952
- Replay JSON SHA256: E328C4786231A9EB498CAD05590B145BC80C86A86B449E31FDF36AF4C5F71C77
- Validation receipt SHA256: 26B49799AB0F5110EE9D285E08AD1B25807407115015A89E37AE0820DAB44755
- Allocation interpretation source, allocate_control.m SHA256: 5AC26D8C5BA6243F755BCF6AD3A07E98E503C213E4C95EDBEE7DD2C2627F3D53
- Post-hoc validator: [validate_nonzero_pair_reconstruction_v1.py](validate_nonzero_pair_reconstruction_v1.py)
- Hash/exit/result receipt: [nonzero_pair_validation_receipt_v1.json](nonzero_pair_validation_receipt_v1.json)
- Offline replay program and numerical results: [nonzero_pair_reconstruction_v1.m](nonzero_pair_reconstruction_v1.m), [nonzero_pair_reconstruction_v1.json](nonzero_pair_reconstruction_v1.json)

