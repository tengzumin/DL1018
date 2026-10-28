# Assumptions and code map

## Snapshot and verified inputs

The reviewed source is the 58-file cosine GRU snapshot. The prepared CFG file SHA-256 matches the hash recorded in LOCKED_CFG.json: 842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a. LOCKED_CFG.json SHA-256 is 55a794e875ca95e5846a29997e01065ab9700e26ac17eb9cb57ce02d7e05df99.

Selected values were read from the hash-bound prepared CFG snapshot, not defaults: K1/K2, J0, command-filter parameters, dt, dmax, beta rise time, attitude event rate, and scheduler phase. J0 SHA-256 is 8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75; the lock records BS inertia derivative zero. No true time-varying inertia or Jhat was reconstructed or used as an input.

## Source mapping

| Behavior | Exact source |
|---|---|
| Fixed controller object | [run_mlp15_dev72_closed_loop.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:183) builds the fixed controller from nominal arm lengths and zero arm rates; lines 1166-1175 select P=fixedController for the controller path. Ptrue is a separate Plant input. |
| Fixed nominal inertia and Jdot handling | [controller_parameters.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/controller_parameters.m:34) uses nominal arms in fixed mode; lines 70-77 assign P.inertia and BS inertia derivative. The locked cfg records the actual fixed J0 and zero BS derivative. |
| BS equations and sign | [attitude_bs_step.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/attitude_bs_step.m:14) computes eta rate, wrapped e, nu, alpha and s; lines 25-41 compute desired acceleration, T inverse conversion, nominal moment, and subtract estimateTorque. |
| ZYX T/Tdot | [attitude_bs_step.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/attitude_bs_step.m:58) defines T and Tdot; lines 64-81 show the pitch clamp and derivatives. |
| Reference filter | [command_filter_step.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/command_filter_step.m:11) wraps target error and clips requested acceleration; lines 18-24 return the pre-update reference and semi-implicitly update rate then angle. |
| Event schedule and hold | [run_mlp15_dev72_closed_loop.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:730) selects the attitude rate; lines 755-765 set phase; lines 1250-1260 schedule events. The GRU branch at lines 2498-2525 reuses held torque on non-events and updates beta/output only at an event. |
| GRU clip and beta | [gru_stream_attitude_step_v1.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/runtime/gru_stream_attitude_step_v1.m:33) normalizes the current feature and advances hidden state; lines 37-40 clip the residual, apply beta, map with J0, and carry hidden state. |
| Actual command and Plant integration | [run_mlp15_dev72_closed_loop.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:2761) runs BS each 1 ms and forms command at 2764; lines 2805-2806 pass realized wrench and external torque to RK4. |
| Actual plant equation and RK4 | [vehicle_derivative.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/vehicle_derivative.m:34) adds actuator and external torque; lines 35-36 apply inertia, gyro, and Jdot. [rk4_vehicle_step.m](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/candidate_runner_work/matlab/core/rk4_vehicle_step.m:12) performs the four derivative evaluations. The command-port d_k^h absorbs these downstream differences; they are not deployed model inputs. |

## T1_C08_W15 offline record

Input: [raw_run.mat](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T1_C08_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat), SHA-256 c118dd1bd5567e0e7c58b7f5334109187b2cfe743977a6a18a3976d7d0ab23c3.

Using h5py/NumPy on the raw record and locked J0 only:
- 19,999 adjacent logged filter-reference pairs: max rate-update error 1.39e-17; max wrapped semi-implicit angle-update error 2.08e-17.
- The exact d_k^h body-rate identity reconstructs the measured delta-omega equation; the applied command sign check has max error 0.0 Nm.
- The full sampled s recurrence, including measured rho_e and rho_T defects and logged C5 compensation, has max absolute residual by axis [3.02e-17, 5.59e-17, 2.49e-18] rad/s.
- 1,999 C5 events occur at 0.010, 0.020, ..., 19.990 s.

This verifies the discrete definitions/signs on one C5 teacher trace. It is not a GRU prediction check, not a new Plant run, and not a trajectory-wide stability result.

## Conditions still assumed, not established

1. The trajectory stays in a useful Euler chart: |theta| <= pi/2-delta with sin(delta)>1e-4 so the code's clamp is inactive, and wrapped error/reference do not jump branches.
2. Reference rates/accelerations, omega, rho_e, rho_T, and command-port residual remain bounded. Roll/pitch reference acceleration limits are Inf, so this is an operating-domain/outer-loop condition.
3. The GRU average-prediction error, interval-label clipping bias, beta ramp error, and within-hold residual oscillation have uniform bounds on the candidate's own closed-loop states. Teacher-trace loss does not establish these; d_k^h is command-conditioned.
4. Forward 10 ms training windows match event boundaries, are complete, and clip the interval mean in the stated order. Tail partial windows or a different clip/average order need separate treatment.
5. Allocation/actuator/external-torque differences are already in d_k^h because its input is requested command. Adding realized-minus-requested again double counts the port mismatch.
6. The conditional bound applies only up to chart/assumption exit. Clipping bounds compensation torque, not the residual, hidden-state prediction error, or plant state.

A full position-attitude result additionally needs an outer-position ISS/Lyapunov bound for its learned/delayed path, bounded force-to-Euler reference under limits, a cascade/small-gain argument for position-attitude and yaw coupling, and a verified safe-set invariance condition. None follows from this check or a finite run.
## Reproduction receipt

The executed numeric check is [reproduce_t1_0plant_check.py](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/reproduce_t1_0plant_check.py), with JSON output [T1_0PLANT_NUMERICAL_CHECK.json](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/T1_0PLANT_NUMERICAL_CHECK.json) and exit receipt [T1_0PLANT_CHECK_EXIT.txt](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/T1_0PLANT_CHECK_EXIT.txt). Script SHA-256 B285EE237DC9D77FF5F08C6CA9CA2805E53A9A3481C34C0C1D77B390B08EBF24; exit code 0.