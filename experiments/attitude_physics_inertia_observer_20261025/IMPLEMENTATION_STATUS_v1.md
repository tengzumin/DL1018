# Isolated implementation status

Date: 2026-10-25. This is an implementation-only checkpoint after synthetic testing.

The experiment directory now contains one pure state-in/state-out candidate helper with init / prepare / commit phases and one synthetic audit entry point. The helper derives rho_hat, rhoDot_hat, J_hat, and Jdot_hat from the currently available morphology command and frozen geometry config; the observer consumes only completed-interval body rates, timestamps, and the previously committed controller-clipped torque command. That command is explicitly a pre-allocation command, not actual/applied torque.

This checkpoint does not include a baseline runner, a candidate closed-loop runner, or any hook into run_dl1018_closed_loop.m. It is not runnable as a flight candidate and has no DEV results. No production matlab/core or matlab/runtime file was modified.

The PowerShell 7 launcher ran MATLAB R2025b synthetic checks only. The final receipt reports PASS, interface torque error 0 N*m, synthetic angular-acceleration error 7.11e-15 rad/s^2, candidate `tau_shape` per-axis error `[0,0,0]` N*m, candidate torque-delta per-axis error `[0,0,1.39e-17]` N*m, interval residual error below 8.89e-16 N*m, acceleration-coordinate mapping error below 8.89e-16 N*m, two completed observer updates, and a passed current-command causality fork. The helper's actual `estimateTorque_Nm` was passed through `attitude_bs_step`; its output torque delta matched `tau_comp_Nm` per axis. The profiler trace contains no Plant, scene, simulation-parameter, or data-loader call. No TEST, MAT, raw, scene log, or flight data was read.

source_lock_candidate_v1.json is a review candidate only, not frozen and not sufficient to authorize closed-loop runs. The next approval gate is review of the isolated helper and synthetic receipt. A later implementation phase must add and review the full baseline/candidate runner integration, regenerate a complete source lock after all code/config/scene/options are final, and obtain separate approval before any DEV flight.

