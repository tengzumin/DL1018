# Teacher-centered DC OOF experiment

## Prespecified recipe

Same GRU, scene folds, seed schedule, 300 steps and Adam 1e-3 as the prior teacher+position/DC experiment. Loss = 0.5 normalized teacher-delta MSE + 0.5 normalized position-action MSE + 0.5 teacher-centered scene-mean action loss. The last term matches each training scene's student mean correction to its teacher mean correction, scaled by 0.1×training-fold teacher RMS. Means, scales and X14 normalization are training-fold-only; teacher is not an inference input.

This follow-up tests only the hypothesis that keeping the teacher's TRAIN-only scene mean recovers some frozen posture benefit suppressed by the zero-mean penalty. It does not turn the teacher's frozen-task benefit into a closed-loop Q guarantee. The parent-reported pilot showed position improvement without beating B on attitude; no heldout/pilot values were used to choose this objective or its constants.

## Aggregate OOF

| Method | Position macro (m/s²) | Frozen SO(3) macro (rad) | Teacher DC tracking error (m/s²) | DC bias norm (m/s²) | Mean 1-s bias (m/s²) |
|---|---:|---:|---:|---:|---:|
| C5 | 0.200214 | 0.057216 | 0.092651 | 0.000000 | 0.000000 |
| No-DC teacher+position | 0.196671 | 0.053238 | 0.060895 | 0.000000 | 0.000000 |
| Zero-DC penalty | 0.190022 | 0.056681 | 0.089991 | 0.007590 | 0.020837 |
| Teacher-centered DC | 0.214596 | 0.050522 | 0.039323 | 0.090539 | 0.112403 |

Position and frozen task win/tie/loss vs zero-DC arm: `[0, 0, 24]` and `[21, 0, 3]`.
Teacher-mean tracking closer/equal/farther vs zero-DC and no-DC students: `[18, 0, 6]` and `[16, 0, 8]`.

The narrow, prespecified frozen-task mechanism hypothesis is supported: teacher-mean error falls from 0.089991 to 0.039323 m/s², while SO(3) falls from 0.056681 to 0.050522 rad. The tradeoff is poor: position residual rises by 0.024574 m/s² versus zero-DC and 0.014382 m/s² versus C5; it is worse than zero-DC in all 24 scenes. This does not support deployment as a balanced position-and-attitude model.

## Per-scene OOF

| Scene | Fold | Position (m/s²) | SO(3) (rad) | Teacher-mean error (m/s²) | DC bias norm (m/s²) | max 1-s bias (m/s²) |
|---|---|---:|---:|---:|---:|---:|
| DL1018_DEV_T1_C00_W03 | holdout_W00_05 | 0.11286 | 0.03755 | 0.05628 | 0.10097 | 0.30899 |
| DL1018_DEV_T1_C01_W15 | holdout_W14_15 | 0.05444 | 0.01798 | 0.02832 | 0.02310 | 0.15944 |
| DL1018_DEV_T1_C04_W00 | holdout_W00_05 | 0.12069 | 0.05054 | 0.09641 | 0.13219 | 0.31489 |
| DL1018_DEV_T1_C05_W06 | holdout_W06_10 | 0.11796 | 0.04565 | 0.01381 | 0.08425 | 0.23224 |
| DL1018_DEV_T1_C07_W08 | holdout_W06_10 | 0.27830 | 0.06924 | 0.02234 | 0.12195 | 0.29481 |
| DL1018_DEV_T1_C10_W09 | holdout_W06_10 | 0.13520 | 0.03846 | 0.03906 | 0.04975 | 0.16262 |
| DL1018_DEV_T1_C11_W12 | holdout_W11_13 | 0.13801 | 0.04275 | 0.01982 | 0.07397 | 0.19343 |
| DL1018_DEV_T1_C15_W14 | holdout_W14_15 | 0.37288 | 0.05641 | 0.05686 | 0.10306 | 0.32631 |
| DL1018_DEV_T2_C00_W04 | holdout_W00_05 | 0.16341 | 0.04648 | 0.01045 | 0.08604 | 0.28002 |
| DL1018_DEV_T2_C02_W15 | holdout_W14_15 | 0.06487 | 0.01457 | 0.01912 | 0.02009 | 0.18344 |
| DL1018_DEV_T2_C03_W01 | holdout_W00_05 | 0.13796 | 0.04566 | 0.06438 | 0.11508 | 0.27158 |
| DL1018_DEV_T2_C06_W07 | holdout_W06_10 | 0.26456 | 0.06768 | 0.01107 | 0.11648 | 0.25449 |
| DL1018_DEV_T2_C08_W08 | holdout_W06_10 | 0.28397 | 0.06756 | 0.02167 | 0.13535 | 0.31189 |
| DL1018_DEV_T2_C09_W10 | holdout_W06_10 | 0.35087 | 0.06719 | 0.07130 | 0.12075 | 0.28556 |
| DL1018_DEV_T2_C12_W13 | holdout_W11_13 | 0.37551 | 0.06652 | 0.08762 | 0.08639 | 0.21677 |
| DL1018_DEV_T2_C14_W14 | holdout_W14_15 | 0.37149 | 0.05314 | 0.04421 | 0.09985 | 0.25840 |
| DL1018_DEV_T3_C00_W05 | holdout_W00_05 | 0.19916 | 0.05592 | 0.02947 | 0.08124 | 0.18001 |
| DL1018_DEV_T3_C03_W15 | holdout_W14_15 | 0.04088 | 0.01096 | 0.01834 | 0.02318 | 0.09459 |
| DL1018_DEV_T3_C05_W02 | holdout_W00_05 | 0.16071 | 0.06102 | 0.01508 | 0.07630 | 0.21521 |
| DL1018_DEV_T3_C06_W08 | holdout_W06_10 | 0.37670 | 0.09706 | 0.06795 | 0.10237 | 0.19011 |
| DL1018_DEV_T3_C09_W09 | holdout_W06_10 | 0.17509 | 0.05167 | 0.04440 | 0.09588 | 0.27605 |
| DL1018_DEV_T3_C10_W11 | holdout_W11_13 | 0.36372 | 0.05492 | 0.03017 | 0.14888 | 0.23196 |
| DL1018_DEV_T3_C13_W12 | holdout_W11_13 | 0.13134 | 0.04066 | 0.01802 | 0.07189 | 0.16290 |
| DL1018_DEV_T3_C15_W14 | holdout_W14_15 | 0.35970 | 0.05293 | 0.05761 | 0.10393 | 0.23801 |

## Limits

All task scores are frozen-state command-filter replays, not closed-loop attitude results. Position residual is the supervised 10-ms label metric, not Q. The teacher-centered loss uses held-out teacher means only in post-hoc OOF comparison; only training-fold teacher labels enter optimization. No VAL/TEST, Plant, or inertia reconstruction was used.

- Config SHA-256: `73cb05382bb10e2f8be96d31aa9a1ff674ca80b249486079881e8475fb1fdc9a`
- Training script SHA-256: `cab2d40b70196b780329c34654193bc0a7efdeebf198ce4863b61e4f5c7a7357`
- OOF SHA-256: `25d9c8e396b0d0fa08bc474d3e4041b2d8a5be98a0ef334b2a9a75ff32012674`
- Results SHA-256: `355183d8ca18c0f306a2cf7561a68c1723342a654e5d285c393919dc66d6aac1`
- Result finalizer SHA-256: `2c43c60dac248fede6ba22ee5bcd540b5ba110fc3a65c3ce48dd31b23961b0e1`
