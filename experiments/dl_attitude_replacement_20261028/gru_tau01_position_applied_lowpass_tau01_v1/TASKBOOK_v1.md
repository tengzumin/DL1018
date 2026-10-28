# Position applied-acceleration low-pass candidate

Status: one pilot is authorized; the first wrapper invocation failed at the runtime release-schema gate before any Plant dynamics. The original marker and logs are preserved, and a clean, separately named retry is prepared for root review. No retry has been started.

Parent: `gru_tau01_delayed_start_v1`. The fork changes only the Stage-1 applied-acceleration output interface in `run_mlp15_dev72_closed_loop.m` and adds one exact ZOH low-pass helper. Existing NN inference, beta ramp, head clipping, PCF update law, attitude controller, fixed J0, and delayed-position schedule are inherited unchanged.

Filter: vector first-order low-pass, `y[k] = y[k-1] + (1-exp(-dt_event/tau))*(u[k]-y[k-1])`, `tau=0.1 s`; `u` is the existing post-beta, post-head-clipping NN applied acceleration. It updates only at each actual 100-Hz position event using `rbfFullDt`, starts at zero, and is held between events. The same `y` sets `stage1PositionHeldForce=P.mass*y`; the unchanged PCF consumes the resulting `positionInfo.commanded_acceleration`.

The no-Plant check validates units, zero initialization, event timing, the 100-Hz coefficient (0.09516258), distinction from 1-kHz stepping (0.00995017), preservation of the beta-scaled head bound, candidate-release schema acceptance up to a deliberate missing-marker guard, and candidate-runner path resolution. It does not establish closed-loop benefit, phase-margin adequacy, force parity, or safety. No retry dynamics, TEST read, inertia reconstruction, or push is part of preparation.

The prior gate rejection is documented in `audits/FAILED_ATTEMPT_GATE_CORRECTION_v1.json`. Its wrapper `Plant_calls=1` field counted entering the runner; the candidate runner rejected at line 22 before the main loop and first `rk4_vehicle_step`, so physical dynamics calls were zero. A fresh retry uses `runs/DL1018_VAL_T3_C01_W14_retry_002` and binds the corrected report hash. The runtime records a first-transition marker immediately before the first RK4 Plant step so future invocation counts and dynamics starts remain distinct.

Any later evaluation requires root review and an independently locked DEV/HF scene set. Compare against the exact parent replay using the same event schedule and candidate output; report task-pose error, position closure, PCF eta and force differences, saturation, and attitude/position tracking limits. The present no-Plant receipt is preparation evidence only.
