# Closed-loop candidate paired score

Legacy generic attitude_head_projection_samples and attitude_head_output_saturated_samples count the v39 head, not the MLP15 causal head. Actual MLP15 projection, clipping, causality and torque checks are in MLP15_TRACE_SAFETY_COUNTS_v1.json. HF vs B: task SO(3) +5.00%, Q +8.74%; gate FAIL. No metric or CSV values were changed by this scope annotation.

Candidate, B, and C5 were scored on the same 12 authorized scenes.

## Paired metrics

| Cohort | N | Method | Q (m) | Task SO(3) (rad) | Inner SO(3) (rad) |
|---|---:|---|---:|---:|---:|
| ALL12 | 12 | Candidate | 0.011618899 | 0.046905369 | 0.013796096 |
| ALL12 | 12 | B | 0.014306172 | 0.050158211 | 0.012760750 |
| ALL12 | 12 | C5 | 0.010079641 | 0.046510930 | 0.012864783 |
| HF_W09_W14 | 6 | Candidate | 0.012249979 | 0.060502374 | 0.018218483 |
| HF_W09_W14 | 6 | B | 0.011265770 | 0.057618624 | 0.016192997 |
| HF_W09_W14 | 6 | C5 | 0.010583788 | 0.061204097 | 0.016424750 |
| W15 | 3 | Candidate | 0.008086347 | 0.006285431 | 0.017803777 |
| W15 | 3 | B | 0.008053074 | 0.005979245 | 0.018492348 |
| W15 | 3 | C5 | 0.006550361 | 0.002981792 | 0.018491434 |
| W00_W08 | 3 | Candidate | 0.013889289 | 0.060331298 | 0.000943642 |
| W00_W08 | 3 | B | 0.026640074 | 0.079416352 | 0.000164656 |
| W00_W08 | 3 | C5 | 0.012600625 | 0.060653732 | 0.000118197 |
| ACTUAL_NO_WIND_RAW | 3 | Candidate | 0.008086347 | 0.006285431 | 0.017803777 |
| ACTUAL_NO_WIND_RAW | 3 | B | 0.008053074 | 0.005979245 | 0.018492348 |
| ACTUAL_NO_WIND_RAW | 3 | C5 | 0.006550361 | 0.002981792 | 0.018491434 |
| ACTUAL_NONZERO_WIND_RAW | 9 | Candidate | 0.012796416 | 0.060445349 | 0.012460203 |
| ACTUAL_NONZERO_WIND_RAW | 9 | B | 0.016390538 | 0.064884534 | 0.010850217 |
| ACTUAL_NONZERO_WIND_RAW | 9 | C5 | 0.011256067 | 0.061020642 | 0.010989232 |

Macro percent change of Candidate versus baseline (positive means higher error):

| Cohort | Baseline | Q | Task SO(3) | Inner SO(3) |
|---|---|---:|---:|---:|
| ALL12 | B | -18.78% | -6.49% | +8.11% |
| ALL12 | C5 | +15.27% | +0.85% | +7.24% |
| HF_W09_W14 | B | +8.74% | +5.00% | +12.51% |
| HF_W09_W14 | C5 | +15.74% | -1.15% | +10.92% |
| W15 | B | +0.41% | +5.12% | -3.72% |
| W15 | C5 | +23.45% | +110.79% | -3.72% |
| W00_W08 | B | -47.86% | -24.03% | +473.10% |
| W00_W08 | C5 | +10.23% | -0.53% | +698.36% |
| ACTUAL_NO_WIND_RAW | B | +0.41% | +5.12% | -3.72% |
| ACTUAL_NO_WIND_RAW | C5 | +23.45% | +110.79% | -3.72% |
| ACTUAL_NONZERO_WIND_RAW | B | -21.93% | -6.84% | +14.84% |
| ACTUAL_NONZERO_WIND_RAW | C5 | +13.68% | -0.94% | +13.39% |

Evidence conclusion: HF task attitude is +5.00% versus B (0/6 scene wins); ALL12 position error is +15.27% versus C5. This development screen misses the high-frequency task-attitude target; overall gains versus B do not establish a pass.


## Candidate scene wins

| Baseline | Metric | Win | Tie | Loss |
|---|---|---:|---:|---:|
| B | Q_m | 6 | 0 | 6 |
| B | task_SO3_rad | 4 | 0 | 8 |
| B | inner_SO3_rad | 4 | 0 | 8 |
| C5 | Q_m | 1 | 0 | 11 |
| C5 | task_SO3_rad | 8 | 0 | 4 |
| C5 | inner_SO3_rad | 4 | 0 | 8 |

## Per-scene paired outcomes

| Scene | B: Q | B: task | B: inner | C5: Q | C5: task | C5: inner |
|---|---|---|---|---|---|---|
| DL1018_DEV_T1_C10_W09 | WIN (-0.000239) | LOSS (+0.000998) | WIN (-0.004237) | LOSS (+0.000280) | WIN (-0.000074) | WIN (-0.004274) |
| DL1018_VAL_T1_C07_W14 | LOSS (+0.001565) | LOSS (+0.001939) | LOSS (+0.000182) | LOSS (+0.003218) | WIN (-0.000733) | LOSS (+0.000086) |
| DL1018_DEV_T2_C09_W10 | LOSS (+0.002217) | LOSS (+0.007524) | LOSS (+0.005882) | LOSS (+0.001476) | WIN (-0.002036) | LOSS (+0.004804) |
| DL1018_VAL_T2_C04_W14 | LOSS (+0.001685) | LOSS (+0.002271) | LOSS (+0.007325) | LOSS (+0.001554) | WIN (-0.000704) | LOSS (+0.007277) |
| DL1018_DEV_T3_C09_W09 | LOSS (+0.000709) | LOSS (+0.001316) | LOSS (+0.003852) | LOSS (+0.002086) | WIN (-0.000327) | LOSS (+0.003770) |
| DL1018_VAL_T3_C01_W14 | WIN (-0.000033) | LOSS (+0.003255) | WIN (-0.000851) | LOSS (+0.001383) | WIN (-0.000336) | WIN (-0.000901) |
| DL1018_DEV_T1_C01_W15 | WIN (-0.003310) | WIN (-0.001170) | WIN (-0.007400) | WIN (-0.001563) | LOSS (+0.000609) | WIN (-0.007401) |
| DL1018_VAL_T2_C05_W15 | LOSS (+0.003393) | LOSS (+0.001685) | LOSS (+0.005584) | LOSS (+0.005176) | LOSS (+0.005836) | LOSS (+0.005585) |
| DL1018_VAL_T3_C02_W15 | LOSS (+0.000017) | LOSS (+0.000404) | WIN (-0.000250) | LOSS (+0.000995) | LOSS (+0.003465) | WIN (-0.000247) |
| DL1018_VAL_T1_C00_W07 | WIN (-0.003292) | WIN (-0.001369) | LOSS (+0.001327) | LOSS (+0.001368) | WIN (-0.000928) | LOSS (+0.001297) |
| DL1018_DEV_T2_C00_W04 | WIN (-0.014065) | WIN (-0.022011) | LOSS (+0.000376) | LOSS (+0.001050) | WIN (-0.000078) | LOSS (+0.000447) |
| DL1018_DEV_T3_C00_W05 | WIN (-0.020896) | WIN (-0.033875) | LOSS (+0.000635) | LOSS (+0.001448) | LOSS (+0.000039) | LOSS (+0.000732) |

Safety sample totals: `{"Candidate": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "B": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "C5": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}}`.

Metric functions: frozen `score_full72_candidate_v1.py`; Q is position-error RMS, task/inner attitude use SO(3) geodesic RMSE.
B/C5 raw paths and hashes are inherited from WN12's bound manifest and parent score. B historical runtime-identity limitation remains.
Only DEV/VAL scenes in the 12-scene authorization are used; TEST is not read.
Actual wind cohorts use the scored candidate raw's `scene/environment_wind_I`: `ACTUAL_NO_WIND_RAW` means every component is exactly zero; `ACTUAL_NONZERO_WIND_RAW` means at least one component is nonzero. Scene-ID W00/W01-W08 suffixes are labels, not measured wind classes; no separate low-wind claim is inferred.
