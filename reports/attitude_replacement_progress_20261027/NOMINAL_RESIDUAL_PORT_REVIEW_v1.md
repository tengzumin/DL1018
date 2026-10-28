# Nominal-residual command-port review (snapshot 2026-10-27)

## Finding

The command-port formula and sign are consistent with the deployed fixed-`J0` nominal model. `requested_generalized` is the controller's generalized-wrench request passed to the allocator; it is **not** the realized actuator body moment. `realized_generalized` is the allocator/Plant-side generalized wrench, and the Plant adds external torque separately. With the same recorded state and constant `J0`, replacing requested torque by realized torque gives the exact identity

\[
R_{cmd}-R_{real}=J_0^{-1}(\tau_{real}-\tau_{req}).
\]

Thus `R_cmd` is the appropriate *command-port* residual candidate for a nominal model whose input is the controller request. It lumps allocation/actuator mismatch together with downstream dynamics relative to fixed `J0`; it is not a pure inertia residual or ground-truth label. `R_real` is a useful offline port diagnostic, but it conditions on the post-allocation actuator wrench and is not interchangeable with the command-port target.

## Source trace

- In [`run_mlp15_dev72_closed_loop.m`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:2761), the controller computes `moments`; line 2764 forms `command=[thrust;moments]`. Line 2774 passes that exact `command` to `allocate_control(command,P,Ptrue,previousMotor)`. Line 2853 logs `requested=command`; line 2854 logs `realized=wrenchNow`. Lines 2805–2806 pass `wrenchNow` to the integrator along with a separate `torquePlant`.
- [`allocate_control.m`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/allocate_control.m:16) takes `command(:)` as `requested`, clips it at lines 17–20, solves motor squared-speed using `Pcontroller.allocation.C` at line 18, and computes `actualGeneralized=Pplant.allocation.C*motor.^2` at line 24. It also records the allocation-model mismatch at lines 39–44.
- [`vehicle_derivative.m`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/vehicle_derivative.m:34) forms net body moment as `generalizedInput(2:4)+torque(:)`; line 35 applies `J^{-1}(moment−ω×Jω−Jdot·ω)`. Therefore `realized_generalized(2:4)` is the actuator wrench contribution, not the complete net body moment when wind/injected external torque is present.
- The frozen config [`LOCKED_CFG.json`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/LOCKED_CFG.json) binds the fixed `J0` matrix (SHA-256 `8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75`) and zero `Pfixed_inertia_dot_for_bs`. No true inertia, `Jhat`, or `Jdot` was read or reconstructed here.

## Independent raw checks

I read the two existing C5 `raw_run.mat` files with Python/h5py only. Each has 20,001 state samples and 20,000 1 ms transitions. For transition `k`, I used `ω_k=state(10:12,k)`, `Δω/Δt=(ω_{k+1}−ω_k)/Δt`, and the logged moment channels 2:4 of `requested_generalized` / `realized_generalized`. The gyroscopic term is evaluated at the left endpoint; this is a discrete fixed-`J0` approximation, not an exact integration of the nonlinear Plant equation. The identity was checked per transition across the full 20 s trace.

| C5 scene | max `|τreal−τreq|`, roll/pitch/yaw (Nm) | max identity error per axis (rad/s²) | clipping / motor saturation |
|---|---:|---:|---:|
| T1_C08_W15 | `[0.0216314, 0.1054112, 8.98e−17]` | `[1.78e−15, 1.42e−14, 2.71e−17]` | 0 / 0 |
| T3_C00_W13 | `[3.75e−16, 3.43e−16, 9.62e−17]` | `[3.55e−15, 1.45e−15, 1.03e−16]` | 0 / 0 |

Both traces report `motor_time_constant_s=0`; `allocated_generalized` matches `requested_generalized` to floating-point precision. In T1, however, `realized_generalized−allocated_generalized` reaches 0.1054112 Nm in pitch despite no clipping or motor saturation. This directly demonstrates the nominal/Plant allocation-port difference; it is not evidence that the requested command was physically applied. T3 happens to have coincident ports to numerical precision and does not establish that generally.

Inputs: [`T1_C08_W15 raw_run.mat`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T1_C08_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat), SHA-256 `c118dd1bd5567e0e7c58b7f5334109187b2cfe743977a6a18a3976d7d0ab23c3`; [`T3_C00_W13 raw_run.mat`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T3_C00_W13/C5_AXIS_MASK_M110/attempt_01/raw_run.mat), SHA-256 `fe56d41b82deed388bd90f3e1933d40ba4abb1a33c9a770f85729de9932071f6`.

## Target and causality limits

Use `R_cmd` when the target is defined as observed gyro acceleration minus the fixed-`J0` prediction driven by the controller request. For an event at sample `k`, compute it only from completed intervals: pair `ω_i→ω_{i+1}` with the request actually issued for that interval, `τreq_i`; if the event cadence is 10 ms, aggregate the preceding ten intervals. Use the deployment-available gyro stream with the same filtering and timing, not future state. The C5 offline check used logged Plant-state angular rates, so sensor filtering/noise alignment remains to be validated.

The existing same-state comparison [`ROOT_C5_SAME_STATE_TARGET_REVIEW_v1.json`](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/ROOT_C5_SAME_STATE_TARGET_REVIEW_v1.json) is motivation to compare targets, not proof that a new target will improve closed-loop tracking. Before any retraining, verify that its nominal-residual calculation uses this same requested-command port and interval alignment. No training, new target, Plant run, TEST read, or release authorization is implied by this port review.