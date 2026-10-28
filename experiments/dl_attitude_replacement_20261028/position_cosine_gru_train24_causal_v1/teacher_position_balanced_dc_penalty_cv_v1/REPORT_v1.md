# Scene-group OOF with per-scene DC action-bias penalty

## Fixed objective and protocol

- Same causal X14 GRU, four whole-scene folds, 300 steps/fold, Adam 1e-3 and seeds 20261028 + fold index.
- Base loss: 0.5 teacher-delta normalized MSE + 0.5 position-action normalized MSE; each scale uses ready rows from that fold's training scenes only.
- Added one fixed term: 0.5 times the mean squared per-scene action-change mean, normalized by `(0.1 × training-fold teacher RMS)`. The penalized signal is `mean_ready(student_action − C5_action)` by scene and axis.
- The four actual train/holdout counts are 18/6, 16/8, 20/4 and 18/6. X14 normalization uses training-fold rows only. No VAL/TEST data, Plant call, or inertia reconstruction.
- Teacher labels are auxiliary training supervision only; they are not part of inference.

## OOF results

| Method | Position residual macro (m/s²) | Position residual pooled (m/s²) | Frozen SO(3) macro (rad) | Frozen SO(3) pooled (rad) | DC action bias macro (m/s²) | 1-s bias norm macro (m/s²) |
|---|---:|---:|---:|---:|---:|---:|
| C5 baseline | 0.200214 | 0.239729 | 0.057216 | 0.060908 | 0.000000 | 0.000000 |
| Prior teacher + position OOF | 0.196671 | 0.228069 | 0.053238 | 0.056992 | 0.048662 | 0.062803 |
| New DC-penalty OOF | 0.190022 | 0.223685 | 0.056681 | 0.060555 | 0.007590 | 0.020837 |

Position win/tie/loss vs C5: `[17, 0, 7]`; frozen posture: `[18, 0, 6]`.
Position win/tie/loss vs prior student: `[21, 0, 3]`; frozen posture: `[2, 0, 22]`.

## Fold scales

| Fold | train/holdout | teacher RMS | position RMS | DC scale |
|---|---:|---:|---:|---:|
| holdout_W00_05 | 18/6 | 0.075413 | 0.268694 | 0.007541 |
| holdout_W06_10 | 16/8 | 0.067555 | 0.224015 | 0.006756 |
| holdout_W11_13 | 20/4 | 0.069638 | 0.231493 | 0.006964 |
| holdout_W14_15 | 18/6 | 0.072217 | 0.231370 | 0.007222 |

## Per-scene held-out diagnostics

| Scene | Fold | Prior position | New position | Prior SO(3) | New SO(3) | Prior DC | New DC | New max 1-s bias |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DL1018_DEV_T1_C00_W03 | holdout_W00_05 | 0.08287 | 0.06815 | 0.03976 | 0.04591 | 0.06613 | 0.00091 | 0.02455 |
| DL1018_DEV_T1_C01_W15 | holdout_W14_15 | 0.04280 | 0.03290 | 0.01351 | 0.01476 | 0.01064 | 0.00144 | 0.04806 |
| DL1018_DEV_T1_C04_W00 | holdout_W00_05 | 0.07382 | 0.06215 | 0.05669 | 0.06249 | 0.06973 | 0.01026 | 0.05865 |
| DL1018_DEV_T1_C05_W06 | holdout_W06_10 | 0.10617 | 0.09892 | 0.04974 | 0.05318 | 0.03649 | 0.00295 | 0.05813 |
| DL1018_DEV_T1_C07_W08 | holdout_W06_10 | 0.27422 | 0.27106 | 0.07182 | 0.07513 | 0.04446 | 0.00802 | 0.04508 |
| DL1018_DEV_T1_C10_W09 | holdout_W06_10 | 0.12367 | 0.12101 | 0.03878 | 0.04260 | 0.05058 | 0.00174 | 0.06185 |
| DL1018_DEV_T1_C11_W12 | holdout_W11_13 | 0.11851 | 0.11107 | 0.04827 | 0.04868 | 0.01202 | 0.00981 | 0.05301 |
| DL1018_DEV_T1_C15_W14 | holdout_W14_15 | 0.35478 | 0.35300 | 0.06070 | 0.06401 | 0.05487 | 0.00594 | 0.06102 |
| DL1018_DEV_T2_C00_W04 | holdout_W00_05 | 0.15335 | 0.13920 | 0.04798 | 0.05250 | 0.08250 | 0.00864 | 0.05751 |
| DL1018_DEV_T2_C02_W15 | holdout_W14_15 | 0.04076 | 0.03265 | 0.01033 | 0.01108 | 0.01384 | 0.00272 | 0.04617 |
| DL1018_DEV_T2_C03_W01 | holdout_W00_05 | 0.10622 | 0.08847 | 0.04859 | 0.05620 | 0.08576 | 0.00481 | 0.06363 |
| DL1018_DEV_T2_C06_W07 | holdout_W06_10 | 0.26501 | 0.25020 | 0.07026 | 0.07583 | 0.07130 | 0.01493 | 0.04578 |
| DL1018_DEV_T2_C08_W08 | holdout_W06_10 | 0.27700 | 0.27442 | 0.06997 | 0.07370 | 0.04713 | 0.00519 | 0.06212 |
| DL1018_DEV_T2_C09_W10 | holdout_W06_10 | 0.33094 | 0.32881 | 0.07482 | 0.07627 | 0.07131 | 0.00799 | 0.05637 |
| DL1018_DEV_T2_C12_W13 | holdout_W11_13 | 0.34594 | 0.35050 | 0.07340 | 0.07166 | 0.01839 | 0.02818 | 0.10076 |
| DL1018_DEV_T2_C14_W14 | holdout_W14_15 | 0.33427 | 0.33441 | 0.05737 | 0.06145 | 0.04860 | 0.00172 | 0.07440 |
| DL1018_DEV_T3_C00_W05 | holdout_W00_05 | 0.18196 | 0.17870 | 0.06066 | 0.06363 | 0.04245 | 0.01204 | 0.03436 |
| DL1018_DEV_T3_C03_W15 | holdout_W14_15 | 0.03381 | 0.03161 | 0.00927 | 0.00868 | 0.02416 | 0.00222 | 0.02752 |
| DL1018_DEV_T3_C05_W02 | holdout_W00_05 | 0.14616 | 0.13358 | 0.06561 | 0.06751 | 0.03049 | 0.02522 | 0.11610 |
| DL1018_DEV_T3_C06_W08 | holdout_W06_10 | 0.38711 | 0.37231 | 0.09711 | 0.10457 | 0.04816 | 0.01153 | 0.05118 |
| DL1018_DEV_T3_C09_W09 | holdout_W06_10 | 0.15853 | 0.14990 | 0.05541 | 0.06014 | 0.05201 | 0.00237 | 0.03833 |
| DL1018_DEV_T3_C10_W11 | holdout_W11_13 | 0.34819 | 0.34415 | 0.05360 | 0.06182 | 0.12614 | 0.00647 | 0.06665 |
| DL1018_DEV_T3_C13_W12 | holdout_W11_13 | 0.11170 | 0.10890 | 0.04541 | 0.04629 | 0.01348 | 0.00578 | 0.05372 |
| DL1018_DEV_T3_C15_W14 | holdout_W14_15 | 0.32231 | 0.32444 | 0.05865 | 0.06223 | 0.04724 | 0.00128 | 0.06831 |

## Interpretation limits

This fixed penalty directly targets scene-level DC action change and tracks one-second block means. These are training/OOF diagnostics; they do not simulate candidate state feedback and cannot establish closed-loop Q. No weights were selected or changed after seeing held-out scores. The low-frequency hypothesis is supported only if the new OOF DC and one-second bias decrease without unacceptable degradation in position residual or frozen SO(3); closed-loop benefit still requires a separately authorized paired evaluation.

- Plan SHA-256: `9b021e6cc699c50c383019d780d7d913995735121d3e141f062353ebbdaa4949`
- Script SHA-256: `2c16f5a973562824c29fdfdd07cdaea9cbef8e2cda387bc2717a002bc5eb1ce8`
- OOF SHA-256: `0b7b37e777a88af864482f60c2d9f531da7b86d243a725c3a10354c9e4734288`
- Results SHA-256: `915171401e80cfc05bab27ad11cb615364b162fcce1bd1160aa0c164f65f2672`
