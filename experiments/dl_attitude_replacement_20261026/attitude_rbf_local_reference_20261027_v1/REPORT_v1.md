# C5 RBF local feedback reference diagnosis

## Result

Exact Python forward replay passed for all six C5 teacher raws (1,999 update events each), including output-before-update order, all clipped and unclipped RBF outputs, basis norms, weight and derivative norms, and the first eight stored weight snapshots per scene. The maximum replay discrepancy across all checks was **1.78e-14**; the maximum first-eight snapshot discrepancy was **2.22e-16**.

For each scene, 200 uniformly spaced mature events were selected. Each event compares BS-only, replayed C5 RBF with frozen `W_before`, and full72 frozen MLP evaluated hypothetically on the same C5 state/history. Finite differences used ε = 1e-5 and 5e-6 rad/s.

## Replay parity

| C5 scene | Updates | Mature | Max absolute parity error |
|---|---:|---:|---:|
| DL1018_VAL_T1_C05_W12 | 1999 | 1780 | 1.78e-14 |
| DL1018_VAL_T1_C08_W15 | 1999 | 1780 | 1.78e-14 |
| DL1018_VAL_T2_C02_W12 | 1999 | 1780 | 1.07e-14 |
| DL1018_VAL_T2_C05_W15 | 1999 | 1780 | 1.78e-14 |
| DL1018_VAL_T3_C00_W13 | 1999 | 1780 | 2.22e-16 |
| DL1018_VAL_T3_C02_W15 | 1999 | 1780 | 1.07e-14 |

Across 48 stored early weight snapshots, maximum error was 2.22e-16. RBF input was `[e_roll,surface_roll,e_pitch,surface_pitch,e_yaw,surface_yaw]`; each event output used `W_before`, then update produced `W_after`.

## Local damping and sensitivity

`λmin` is the minimum eigenvalue of `Sym(-dτ_net/dω)`. The increment ratio is `||J_mode − J_BS||F / ||J_BS||F`. The local derivative freezes state, reference and derivatives, arm command, prior 14 MLP features, and current weights; it recomputes nominal BS torque and current RBF surface/input when ω is perturbed.

| Family | Window | n | λmin median BS | λmin median RBF | λmin median frozen MLP* | Negative λmin MLP* | Increment ratio median RBF | Increment ratio median MLP* |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| W15 | first5 | 96 | 0.078142 | 0.078142 | -0.168556 | 100.0% | 9.63592e-14 | 6.18 |
| W15 | middle | 336 | 0.077722 | 0.077753 | -0.050900 | 65.5% | 0.000358973 | 4.42 |
| W15 | last5 | 168 | 0.078145 | 0.078179 | -0.170419 | 80.4% | 0.000753319 | 6.27 |
| HF | first5 | 96 | 0.077938 | 0.077938 | 0.009945 | 41.7% | 2.61466e-09 | 1.7 |
| HF | middle | 336 | 0.077599 | 0.077608 | 0.009923 | 45.5% | 0.000350568 | 1.93 |
| HF | last5 | 168 | 0.077969 | 0.078027 | 0.022913 | 39.9% | 0.000569291 | 1.77 |

| Family | Axis | `Sym(-J)` diagonal median BS | RBF | frozen MLP* | Increment ratio median RBF | frozen MLP* |
|---|---|---:|---:|---:|---:|---:|
| W15 | roll | 0.078181 | 0.078198 | 0.289995 | 0.000313616 | 2.86 |
| W15 | pitch | 0.078171 | 0.078181 | 0.189807 | 0.00045519 | 1.53 |
| W15 | yaw | 0.089073 | 0.089073 | 0.188302 | 1.66583e-05 | 7.74 |
| HF | roll | 0.078181 | 0.078181 | 0.134195 | 0.000245057 | 0.877 |
| HF | pitch | 0.078151 | 0.078159 | 0.134059 | 0.000235674 | 0.819 |
| HF | yaw | 0.089154 | 0.089158 | 0.109930 | 1.07767e-05 | 2.32 |

Across all 1,200 points, BS and replayed RBF had **zero** negative `λmin` values; their medians were 0.077906 and 0.077940. RBF increment ratio median/p95 was 0.0003811 / 0.001391 (maximum 0.002754), and none of the selected RBF outputs saturated. The hypothetical MLP had 711/1,200 negative `λmin` values (59.25%); its increment ratio median/p95 was 3.39 / 7.21. No selected MLP output saturated.

Worst hypothetical MLP sample was `DL1018_VAL_T1_C05_W12`, sample 16411 at 16.41 s, with `λmin = -0.7238` and increment ratio 14.39. This is only a frozen MLP evaluated on a C5 log point.

## Interpretation and limits

The C5 teacher RBF contributes very little instantaneous torque feedback sensitivity compared with nominal BS on these sampled states. The hypothetical frozen MLP is substantially more sensitive and often has a negative symmetric-part minimum eigenvalue, which makes current-rate feedback sensitivity a plausible difference to investigate. It does **not** show that this is the cause of the v3 flight result: the MLP values are evaluated on C5 state/history, not from a C5 MLP flight, and these are local frozen-memory derivatives rather than a full stability analysis or Plant counterfactual.

Fixed values were `K1=[1.5,1.5,1.3]`, `K2=[22.5,22.5,12.7]`, `J0=diag([0.0032575533,0.0032575533,0.0063606483]) kg·m²`, and `Jdot0=0`. No variable inertia was read or reconstructed.

## Reproducibility

Full numerical command (PowerShell 7):
```powershell
$env:MKL_THREADING_LAYER='SEQUENTIAL'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
& python -u 'experiments/dl_attitude_replacement_20261026/attitude_rbf_local_reference_20261027_v1/rbf_replay.py' --phase full --scene all
```

After the numerical run, the script’s source precheck was changed to read expected SHA values directly from the audited C5 input lock and v3 `SOURCE_LOCK_v3.json`. The lock-derived revalidation passed; it confirmed the same SHA values used by the completed run. No numerical replay/Jacobian was rerun because this change only replaced embedded expected-hash literals with lock lookups. See `SOURCE_LOCK_VALIDATION_v1.json` and `PROVENANCE_v1.json`.

*Plant calls: 0 · MATLAB started: false · training: 0 · TEST read: false*
