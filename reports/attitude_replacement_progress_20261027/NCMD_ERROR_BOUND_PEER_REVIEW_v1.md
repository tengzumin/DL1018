# Independent peer review: conditional NCMD attitude bound

## Finding

**P2, non-blocking — state the terminal-reference boundary explicitly.** `T1_C08_W15` has 20,001 state samples through 20.000 s, but only 20,000 filtered-reference samples through 19.999 s. The reproduction script sets `n = min(ref_count−1, state_count−1) = 19,999`, so its filter/surface recurrence checks stop at the transition ending at 19.999 s; it does not verify the final transition 19.999→20.000 s. A separate read-only timestamp check confirmed 1 ms spacing to floating-point error (`2.33e−15` s). This does not invalidate the final NCMD target interval `[19.990,20.000)`: its gyro endpoints and requested commands exist, and the target construction is independent of the missing terminal reference. Keep the current claim bounded to the 19,999 checked reference pairs; if a future report claims the recurrence through the terminal 20.000 s state, derive/check that final reference update or exclude the endpoint explicitly.

## Mathematical and code-map review

No blocking sign, scale, or recurrence error was found.

- **Fixed BS map and torque sign:** `attitude_bs_step.m` uses `eta_dot=T(eta)omega`, the analytic `Tdot`, `T^{-1}(u_c−Tdot omega)`, and `tau_nom=J0*omega_dot_nom+omega×J0omega+Jdot_BS*omega`. It forms `tau_req=tau_nom−estimateTorque`; the bound correctly uses `Jdot_BS=0` for the locked fixed controller and maps the applied clipped residual back as `J0 beta q`. The resulting surface disturbance is `T(beta q−d)`, with the signs in the derivation consistent with source.
- **Filter and sampled residuals:** `command_filter_step.m` returns the pre-update reference/acceleration, then updates rate first and angle with the new rate. Thus `rho_e` contains the semi-implicit filter step as written. The product increment identity for `T omega` gives the stated `rho_T`; substituting the command-port body-rate identity yields the reported `e` and `s` recurrences with the stated signs.
- **Norm bound:** With `x=(e,t_*s)`, `t_*=1 s`, the block matrix `A_*` is correct. The reported `||I+hA_*||_2=0.9987005035245451` is below the upward-rounded `q_bar=0.998701`; the geometric finite-horizon bound follows while the local chart and disturbance bounds hold. The Frobenius envelope `sqrt(2 sec²(pi/2−delta)+1)` is valid for the stated pitch chart.
- **10 ms label and hold decomposition:** averaging the ten 1 ms `d_k^h` values is algebraically identical to the interval endpoint rate difference plus the average gyro/request term. The four-term decomposition accounts for model prediction error, interval-mean clipping, beta ramp, and within-hold variation exactly when the target clips the 10 ms mean. The first event at 10 ms uses one-based `k=11`, so beta is `11*1 ms/2.2 s=0.005`; zero held torque before that event matches the runtime. Request-to-realized/allocation effects are already in `d_k^h` and must not be added again.
- **Scope and limits:** The documents correctly call this a local, finite-horizon conditional bound. They do not claim a uniform NCMD prediction-error bound, invariant safe set, global attitude stability, or a full position-attitude cascade result. The T1 recurrence check uses one existing C5 teacher trace and logged applied compensation; it is a sign/clock/kinematics consistency check, not NCMD model validation or a stability-margin measurement. `d_h` is defined from the measured delta-omega identity, so its reconstruction check is an algebraic consistency check, not independent evidence that the physical residual is small.

## Inputs reviewed

- `DERIVATION.md`, SHA-256 `10C73D5EB28FF44ECA9D85DEAA785FB0F6AF683582CE22E5C8754621AB58557A` (matches the requested digest).
- `ASSUMPTIONS_AND_CODE_MAP.md`, SHA-256 `2C2FF2C3A7F6AB1098833FFBE5C7CCC3E768AA4D48435AA388AD6CCC523C83C5`.
- `reproduce_t1_0plant_check.py`, SHA-256 `B285EE237DC9D77FF5F08C6CA9CA2805E53A9A3481C34C0C1D77B390B08EBF24`.
- `T1_0PLANT_NUMERICAL_CHECK.json`, SHA-256 `7DBA315602F9C31F58FB57CB186CC541EC0C73B7D5BDA7D6CFAAD635AD9BB0A9`, status PASS, recorded exit code 0.

Review scope was read-only. The only additional numeric check read the same existing T1 C5 raw timestamps; it did not start MATLAB or Plant, train, or read TEST. No author files or runtime files were changed. The boundary clarification is non-blocking for the NCMD first-scene deployment.