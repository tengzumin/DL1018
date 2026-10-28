# Conditional attitude error bound: fixed-J0 BS + frozen GRU hold

## Instance and scope

This is a conditional finite-horizon local bound for the implemented attitude channel, not a stability proof for the position-attitude cascade. Parameters come from the prepared CFG snapshot bound by gru_stream_cosine_dev_v1/LOCKED_CFG.json (snapshot SHA-256 842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a), not default_config.m:

\[
J_0=\begin{bmatrix}
0.003257553333&-2.17\times10^{-19}&0\\
-2.17\times10^{-19}&0.003257553333&0\\
0&0&0.006360648333
\end{bmatrix}\ \mathrm{kg\,m^2},\qquad \dot J_{\rm BS}=0.
\]

- K1 = (1.5, 1.5, 1.3); K2 = (22.5, 22.5, 12.7).
- h = 1 ms; attitude event rate = 100 Hz (H = 10 ms); command filter wn = (18,18,12), damping = (1,1,1), acceleration limits = (Inf,Inf,6).
- dmax = (45,45,4.7124) rad/s^2; at each event beta_j = min(k_j h / 2.2, 1), where k_j is the one-based MATLAB sample index.

The locked J0 SHA-256 is 8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75. No Jhat, time-varying-inertia reconstruction, Plant-truth feature, TEST data, training, or new simulation is used. The only raw check is the existing T1_C08_W15 C5 trace below.

## Correct Euler and backstepping signs

For ZYX Euler state eta = (phi,theta,psi) and body rate omega, the implementation uses

\[
\dot\eta=T(\eta)\omega,\qquad
T=\begin{bmatrix}
1&\sin\phi\tan\theta&\cos\phi\tan\theta\\
0&\cos\phi&-\sin\phi\\
0&\sin\phi\sec\theta&\cos\phi\sec\theta
\end{bmatrix},\qquad
\ddot\eta=T\dot\omega+\dot T\omega,
\]

where Tdot = T_phi phi_dot + T_theta theta_dot and (phi_dot,theta_dot) = (T omega)_(1:2). This is the full map; substituting T=I or treating eta_ddot as omega_dot is not valid here.

Let r, rdot, rddot be the current filtered reference, e = wrap(r-eta), nu = rdot-T omega, and s = nu+K1 e. The implemented virtual acceleration is

\[
\alpha=\dot r+K_1e,\quad \dot\alpha=\ddot r+K_1\nu,\quad
u_c=\dot\alpha+e+K_2s.
\]

It converts to body acceleration omega_dot_nom = T^{-1}(u_c-Tdot omega), then

\[
\tau_{nom}=J_0T^{-1}(u_c-\dot T\omega)+\omega\times J_0\omega,\qquad
\tau_{req}=\tau_{nom}-J_0\beta_j\hat d^{clip}_j.
\]

The minus sign is the implementation: attitude_bs_step subtracts estimateTorque. For the fixed-J0 nominal model with command-port residual d = omega_dot - J0^{-1}(tau_req-omega x J0 omega), the continuous chart dynamics are

\[
\dot e=s-K_1e,\qquad
\dot s=-e-K_2s+T(\beta_j\hat d^{clip}_j-d).
\]

Thus perfect compensation requires beta_j d_hat_clip = d; the residual enters with a minus sign and the applied estimate with a plus sign in s_dot.

## Exact sample recurrence and conditional bound

For each actual 1 ms transition k to k+1, define the command-port residual

\[
d_k^h={\omega_{k+1}-\omega_k\over h}
+J_0^{-1}\left(\omega_k\times J_0\omega_k-\tau_{req,k}\right).
\]

This gives the exact discrete identity
\[
\Delta\omega_k/h=J_0^{-1}(\tau_{req,k}-\omega_k\times J_0\omega_k)+d_k^h.
\]
Here tau_req is the controller command sent to the allocator. Request-to-realized allocation difference, actuator effects, external moments, and actual-Plant mismatch are already inside d_k^h. Do not add an allocator torque residual a second time.

Let event j hold q_j = clip_dmax(d_hat_raw,j) over the next ten 1 ms samples, and define epsilon_k = beta_j q_j - d_k^h. On a no-wrap interval define

\[
\rho^e_k={e_{k+1}-e_k\over h}-\nu_k
=h\ddot r_k+T_k\omega_k-{\eta_{k+1}-\eta_k\over h},
\qquad
\rho^T_k=\dot T_k\omega_k-{T_{k+1}-T_k\over h}\omega_{k+1}.
\]

rho_e includes the command filter's semi-implicit reference update; rho_T is the finite-step T(eta)omega product-rule/map error. Substitution of the exact body-rate identity and the filter update rdot_(k+1)-rdot_k = h rddot_k gives

\[
\begin{aligned}
e_{k+1}&=e_k+h(s_k-K_1e_k+\rho^e_k),\\
s_{k+1}&=s_k+h[-e_k-K_2s_k+T_k\epsilon_k+K_1\rho^e_k+\rho^T_k].
\end{aligned}
\]

For the norm, scale s by t_* = 1 s and set x = (e, s_bar), s_bar = t_* s. Then A_* = [[-K1,I/t_*],[-t_* I,-K2]], Phi = I+h A_*, B_* = [0;t_* I], and chi_k = (rho_e, t_*(K1 rho_e+rho_T)). With the locked gains and h=0.001 s, the exact norm is ||Phi||_2 = 0.9987005035245451; use the upward bound q_bar = 0.998701 < 1. The nominal discrete poles are 0.99845227 and 0.97754773 for roll/pitch, and 0.99861160 and 0.98738840 for yaw. Therefore, while the local chart holds,

\[
\|x_n\|_2\le \bar q^N\|x_{n-N}\|_2+
h\sum_{i=n-N}^{n-1}\bar q^{n-1-i}
\left(t_*\|T_i\|_2\|\epsilon_i\|_2+\|\chi_i\|_2\right),
\qquad \bar q=0.998701.
\]

If verified horizon-wide bounds ||T_i|| <= T_max, ||epsilon_i|| <= E, and ||chi_i|| <= R hold, then

\[
\|x_n\|_2\le \bar q^N\|x_{n-N}\|_2+
{h(1-\bar q^N)\over1-\bar q}(t_*T_{max}E+R).
\]

This is a conditional finite-horizon estimate, not an unconditional invariant-set or global-stability result. Require |theta| <= pi/2-delta with sin(delta) > 1e-4; then the code's 1e-4 pitch clamp is inactive and ||T||_2 <= ||T||_F <= sqrt(2 sec^2(pi/2-delta)+1). The code clamp itself does not prove that the trajectory remains in a useful nonsingular chart.

## 100 Hz prediction, ramp, and hold

For a complete forward event window I_j of ten transitions, let dbar_j^h = (1/10) sum_(k in I_j) d_k^h, training label y_j = clip_dmax(dbar_j^h), and deployed clipped prediction q_j. For every held sample,

\[
\epsilon_k=
\underbrace{\beta_j(q_j-y_j)}_{\text{model average-prediction error}}+
\underbrace{\beta_j(y_j-\bar d_j^h)}_{\text{label clipping bias}}+
\underbrace{(\beta_j-1)\bar d_j^h}_{\text{startup/ramp residual}}+
\underbrace{(\bar d_j^h-d_k^h)}_{\text{within-hold oscillation}}.
\]

These terms must be bounded on the candidate's own closed-loop states to provide E. A teacher-trace fit alone does not establish this: d_k^h is command-conditioned, so changing compensation changes the issued command and can change the residual. The decomposition assumes the training target clips the interval mean; if code clips each 1 ms value before averaging, the label-clipping term must be changed. The forward d_k^h values use future gyro samples only as offline labels; inference at event j must not receive them as features.

The source initializes held GRU torque to zero, updates hidden/output only on events, and reuses the held torque on non-event samples; the BS law still runs each 1 ms. The prepared options set 100 Hz and phase -0.1; the first event is at t=0.010 s (MATLAB sample k=11, zero-based state index 10). The implementation uses beta = 11(0.001)/2.2 = 0.005 there. Before it, compensation is zero; between events beta-scaled torque is staircase-held, not continuously ramped. Output clipping guarantees only ||tau_hat|| <= ||J0||_2 ||dmax||_2 ~= 0.4059 N m. It does not bound d_k^h, state, or the closed loop.

## T1_C08_W15 0-Plant check

For the existing C5 raw trace (SHA-256 c118dd1bd5567e0e7c58b7f5334109187b2cfe743977a6a18a3976d7d0ab23c3), I reconstructed d_k^h from state(10:12), requested_generalized(2:4), and locked J0. The exact discrete body-rate identity reconstructs to floating precision. On the 19,999 consecutive pairs where filtered references are logged, the semi-implicit filter checks give max |rate_(k+1)-rate_k-h accel_k| = 1.39e-17 and max wrapped |ref_(k+1)-ref_k-h rate_(k+1)| = 2.08e-17. The full discrete s recurrence, using the logged applied C5 compensation, has max absolute residual [3.02e-17, 5.59e-17, 2.49e-18] rad/s. The command-sign check tau_req = nominal_torque - compensation_torque has max absolute error 0.0 N m. Raw event flags show 1,999 events, first at 0.010 s, then every 0.010 s through 19.990 s. This checks sample/sign/clock alignment on the C5 teacher trace only; it does not validate GRU prediction accuracy or a stability margin.

## What is not proved

The result stops at the local attitude channel and only applies until the pitch/wrap chart or assumed bounds fail. A full position-attitude result additionally needs an outer-position ISS/Lyapunov bound for its learned/delayed channel; bounded and regular force-to-Euler references under force/tilt limits; an interconnection or small-gain/cascade argument covering position-to-attitude and yaw coupling; uniform candidate-trajectory residual/prediction/hold bounds; and a verified safe-set invariance condition. None follows from output clipping, a finite raw trace, training loss, PE, or nominal contraction alone. No Lee-theorem result is imported.

## Reproduction artifacts

The executed 0-Plant check is reproducible with [reproduce_t1_0plant_check.py](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/reproduce_t1_0plant_check.py). Its output is [T1_0PLANT_NUMERICAL_CHECK.json](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/T1_0PLANT_NUMERICAL_CHECK.json); the actual process exit receipt is [T1_0PLANT_CHECK_EXIT.txt](C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/attitude_ncmd_error_bound_20261027_v1/T1_0PLANT_CHECK_EXIT.txt). The script SHA-256 is B285EE237DC9D77FF5F08C6CA9CA2805E53A9A3481C34C0C1D77B390B08EBF24; it returned exit code 0.