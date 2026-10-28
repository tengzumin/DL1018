# Conditional bounded-error result for the DL_TCN attitude candidate

Status: derivation draft; not a completed stability certification or a performance result.
Scope: the frozen DL_TCN candidate with fixed nominal controller inertia `J0`; no shape-dependent inertia reconstruction, `Jhat`, `Jdot_hat`, Plant truth, observer, or RBF state enters its runtime.

The training target is B's logged, pre-beta and output-limited RBF action. Therefore this TCN is a behavior-cloning replacement for that action, not a learned physical residual or inertia estimator. Teacher-action RMSE alone does not prove closed-loop attitude improvement.

## Source contract checked

The v4 candidate runner recomputes the nominal BS moment at every 1 ms Plant/control step. It refreshes the TCN compensation at its 100 Hz attitude event and holds that torque between events. It forms the 13-channel feature from wrapped attitude error, body rate, nominal BS torque, and current morph command, and applies the network output as `J0 * beta * clip(output, -dmax, dmax)`. The MATLAB forward pass first multiplies the network output by the TRAIN target RMS, so clipping is applied in physical `rad/s^2` units before conversion to `N*m`. Each allocated wrench is then used for one RK4 Plant step. The Plant separately evolves with its time-varying inertia. The allocator can add a wrench mismatch when its fixed geometry differs from the active Plant geometry. This is a controller/Plant model mismatch, not a runtime inertia reconstruction.

Source hashes at derivation time:

| File | SHA-256 |
|---|---|
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/attitude_bs_step.m` | `CF6B20FFC4DF2625D9316A80340D69542E380D14FEAED66EF8498E793FDACCBC` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/vehicle_derivative.m` | `C3258DD5B70268D1465CA7701855B065244AEBFAF5816C85E959D39015CD2786` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/rk4_vehicle_step.m` | `7E10A8C77B2740F2F9F222F3B06C6C021CB3A9342070AD7F3EBABA3C47395EF5` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/controller_parameters.m` | `4FAD5E78C0BD4177461647AF167E7C86A7DEFA628B43D523B0B7DA2EF5556398` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/core/allocate_control.m` | `5AC26D8C5BA6243F755BCF6AD3A07E98E503C213E4C95EDBEE7DD2C2627F3D53` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/runtime/tcn_attitude_step_v1.m` | `9EC27DC1A9226C7F64ACD26F1D0E8173FB0E1AABFB3D67D51318ABA66122F130` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/runtime/tcn_attitude_forward_v1.m` | `193C288D33AD213AA57F40DB4795A3D1F0898CCF5F678E7854CCF925CB6FF3CC` |
| `pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/runtime/run_gate_holdout_closed_loop.m` | `EC6F41038D1643D1A6795BC3117C093A02FDC20F34C8B86E6E5D83B9580F7A9A` |

Any source change invalidates this source binding and requires a fresh audit.

The no-Plant readback of the C5 snapshot used by the pilot preparer was checked against its receipt SHA-256 `842EF395569E675DB6E139C2684D72B976946915E5E0A58B9B7F24EC10C1D24A`. It reports `dt = 0.001 s`, `attitude_update_hz = 100`, `K1 = diag(1.5, 1.5, 1.3)`, `K2 = diag(22.5, 22.5, 12.7)`, `dmax = (45, 45, 4.7124) rad/s^2`, and `beta_rise_time = 2.2 s`. Rebuilding the fixed controller from the snapshot's `arm_initial = (0.15,0.15,0.15,0.15) m` gives `J0` eigenvalues `(0.00325755333333, 0.00325755333333, 0.00636064833333) kg m^2` and `||Jdot_BS||_F = 0`. With the implemented unit `K0`, the Lyapunov decay coefficient in the ideal bound is `c = 2.6 s^-1`. The conservative TCN torque bound is `||tau_N||_2 <= 0.40590 N m`; the total disturbance bound `D` is not yet evaluated.

## Closed-loop error model

Let `eta` be ZYX Euler attitude, `omega` body angular rate, and `T(eta)` the implemented Euler-rate map, so `eta_dot = T omega`. On a nonsingular Euler chart, define

\[
e=\operatorname{wrap}(\eta_d-\eta),\quad
\alpha=\dot\eta_d+K_1e,\quad
z=\alpha-T\omega.
\]

The implemented nominal virtual acceleration is

\[
\alpha_n=\dot\alpha+K_0e+K_2z,
\]

where `K0` is the unit coefficient written as `+e` in the MATLAB code (with simulation time in seconds, it carries units of `s^-2`). The corresponding nominal body angular acceleration is

\[
a_n=T^{-1}(\alpha_n-\dot T\,\omega).
\]

The fixed-model controller asks for

\[
M_c=J_0a_n+\omega\times(J_0\omega)-\tau_N,
\quad
\tau_N=J_0\,\beta\,\operatorname{clip}(f_\theta(x_{k-14:k}),-d_{\max},d_{\max}).
\]

The neural head is frozen and causal. Its torque is piecewise constant between 100 Hz TCN events. Since `0 <= beta <= 1`, its commanded torque is bounded by

\[
\|\tau_N\|_2\le \|J_0\|_2\,\|d_{\max}\|_2.
\]

The Plant code implements

\[
J(t)\dot\omega=M_{\rm actual}+\tau_w
-\omega\times(J(t)\omega)-\dot J(t)\omega.
\]

At each 1 ms controller sample the BS moment is recomputed using the current state and the most recently held TCN torque; that sampled moment is passed to the allocator and used during the next RK4 interval. Let `epsilon_h` denote the difference between this one-step held moment and the instantaneous continuous-time fixed-J0 BS expression that uses the same piecewise-constant TCN torque. Let `epsilon_alloc` denote the realized-versus-requested moment difference caused by allocation/model mismatch or limits. Subtracting `a_n` gives

\[
\ddot\eta=\alpha_n+d_\eta,
\]

where

\[
d_\eta=T J^{-1}\!\left[
(J_0-J)a_n
+\omega\times((J_0-J)\omega)
-\dot J\omega
-\tau_N
+\epsilon_h+\epsilon_{\rm alloc}+\tau_w
\right].
\]

Here `epsilon_alloc` includes generalized-command clipping, actuator saturation or motor lag, and the fixed-controller/active-Plant allocation mismatch. The TCN's 100 Hz hold is represented directly by the bounded, piecewise-constant `tau_N`; `epsilon_h` is only the inner 1 ms controller/Plant sample-and-hold discrepancy. The physical `J(t)` and `Jdot(t)` appear only in this offline Plant equation; they are not candidate inputs.

On a chart with no angle-wrap discontinuity, the tracking dynamics are

\[
\dot e=z-K_1e,\qquad
\dot z=-K_0e-K_2z-d_\eta.
\]

## Conditional proposition

Assume on a forward-invariant operating set `Omega` that:

1. `K0`, `K1`, and `K2` are positive diagonal matrices (`K0` is the unit error coefficient in the code); `a_e = lambda_min(K0 K1) > 0` and `k2 = lambda_min(K2) > 0`.
2. The Euler chart stays nonsingular and the wrapped tracking error has no branch discontinuity.
3. The Plant inertia is uniformly positive definite, `lambda_min(J(t)) >= j_min > 0`.
4. References, body rate, nominal acceleration, `Jdot`, wind torque, allocator mismatch, and the sample-and-hold discrepancy are uniformly bounded on `Omega`.

Then `d_eta` has a finite bound `D` on `Omega`. For

\[
V=\tfrac12(e^\top K_0e+z^\top z),\quad
a_e=\lambda_{\min}(K_0K_1),\quad
c=\min\!\left(\frac{2a_e}{\lambda_{\max}(K_0)},k_2\right),
\]

where `K0` is positive diagonal (the code's unit coefficient) and `k2 = lambda_min(K2)`. Young's inequality gives

\[
\dot V\le -cV+\frac{D^2}{2k_2}.
\]

Consequently, define the weighted tracking-error vector `xi = [K0^(1/2)e; z]`, so `||xi||_2^2 = 2V`. Then

\[
V(t)\le e^{-ct}V(0)+\frac{D^2}{2k_2c}(1-e^{-ct}),
\qquad
\|\xi(t)\|_2^2\le e^{-ct}\|\xi(0)\|_2^2+\frac{D^2}{k_2c}(1-e^{-ct}).
\]

Thus the conditional ultimate radius in this weighted norm is `D / sqrt(k2*c)`. If `D=0`, the ideal continuous-time error model is exponentially stable.

One conservative bound is

\[
D\le \sup_{\Omega}\|TJ^{-1}\|_2\left[
\|J_0-J\|_2\,\|a_n\|_2
+\|\omega\|_2^2\|J_0-J\|_2
+\|\dot J\|_2\|\omega\|_2
+\|J_0\|_2\|d_{\max}\|_2
+\|\epsilon_h\|_2+\|\epsilon_{\rm alloc}\|_2+\|\tau_w\|_2
\right]_{\sup,\Omega}.
\]

This bound is deliberately conservative: it treats the learned compensation as a bounded input and does not assume that the TCN cancels the inertia mismatch. It therefore does not establish that the TCN improves tracking, that its output is a correct physical residual, or that any observed finite simulation is stable for all initial conditions.

## What is still required before using this in a paper

- Verify the exact frozen configuration and numerical values of `K1`, `K2`, `J0`, `dmax`, attitude-event period, and the allowed Euler-angle domain against the released candidate artifacts.
- Establish bounds or measured conservative envelopes for `J`, `Jdot`, `omega`, `a_n`, wind torque, allocation mismatch, and the held-command discrepancy on the claimed operating set. Simulation maxima alone support only that tested set and horizon.
- Derive a bound for the 1 ms sample-and-hold discrepancy and the RK4 numerical integration error. The current proposition assumes a bounded `epsilon_h` and does not certify the discrete RK4 map.
- If the claimed result is about the implemented sampled system, extend the proof to the 1 ms sampled/RK4 dynamics or explicitly retain the continuous-time result as a conditional analysis of the nominal error model.
- Keep the closed-loop DEV/TEST comparison as the empirical performance evidence. This proposition is a bounded-error argument only; it is not a substitute for the paired experiments or their safety checks.

## 2026-10-26 source and algebra review

The eight source hashes listed above were recomputed against the frozen candidate tree and all match. Read-only inspection confirms: the TCN torque is subtracted from the fixed-J0 backstepping moment; TCN output is held between 100 Hz events; the nominal backstepping moment is recalculated at the 1 ms control sample; the resulting wrench is applied through the allocator and one RK4 Plant interval. The Plant uses its time-varying `J(t)` and `Jdot(t)` only in its own dynamics. No algebraic inconsistency was found in the continuous-time decomposition or the weighted Lyapunov inequality, provided the proposition assumptions hold.

Using the frozen numeric values, `c = 2.6 s^-1`, `||J0||_2 = 0.00636064833333 kg m^2`, and `||dmax||_2 = 63.8138 rad/s^2`, giving the conservative candidate torque bound `||tau_N||_2 <= 0.40590 N m`. This bounds only the TCN compensation torque, not the total closed-loop disturbance `D`.

This review does not close the theorem gate. The current artifacts do not prove a compact forward-invariant operating set or establish rigorous bounds for every term in `D`; `epsilon_h` and `epsilon_alloc` remain assumed bounded, and the continuous-time argument does not certify the implemented 1 ms sampled / RK4 map. Therefore this is a conditional continuous-time UUB result only, not a stability certification, and it must not be used as evidence of closed-loop performance. This was a source/algebra review by the primary agent, not the independent peer review required for final theory acceptance.

