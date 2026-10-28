# Closed-loop candidate paired score

Candidate, B, and C5 were scored on the same 12 authorized scenes.

## Paired metrics

| Cohort | N | Method | Q (m) | Task SO(3) (rad) | Inner SO(3) (rad) |
|---|---:|---|---:|---:|---:|
| ALL12 | 12 | Candidate | 0.010360107 | 0.047260161 | 0.013741772 |
| ALL12 | 12 | B | 0.014306172 | 0.050158211 | 0.012760750 |
| ALL12 | 12 | C5 | 0.010079641 | 0.046510930 | 0.012864783 |
| HF_W09_W14 | 6 | Candidate | 0.010824909 | 0.061355392 | 0.018477224 |
| HF_W09_W14 | 6 | B | 0.011265770 | 0.057618624 | 0.016192997 |
| HF_W09_W14 | 6 | C5 | 0.010583788 | 0.061204097 | 0.016424750 |
| W15 | 3 | Candidate | 0.007183427 | 0.005681395 | 0.016975577 |
| W15 | 3 | B | 0.008053074 | 0.005979245 | 0.018492348 |
| W15 | 3 | C5 | 0.006550361 | 0.002981792 | 0.018491434 |
| W00_W08 | 3 | Candidate | 0.012607182 | 0.060648465 | 0.001037063 |
| W00_W08 | 3 | B | 0.026640074 | 0.079416352 | 0.000164656 |
| W00_W08 | 3 | C5 | 0.012600625 | 0.060653732 | 0.000118197 |
| NO_WIND_W00 | 0 | Candidate | not sampled | not sampled | not sampled |
| NO_WIND_W00 | 0 | B | not sampled | not sampled | not sampled |
| NO_WIND_W00 | 0 | C5 | not sampled | not sampled | not sampled |
| LOW_WIND_W01_W08 | 3 | Candidate | 0.012607182 | 0.060648465 | 0.001037063 |
| LOW_WIND_W01_W08 | 3 | B | 0.026640074 | 0.079416352 | 0.000164656 |
| LOW_WIND_W01_W08 | 3 | C5 | 0.012600625 | 0.060653732 | 0.000118197 |

Macro percent change of Candidate versus baseline (positive means higher error):

| Cohort | Baseline | Q | Task SO(3) | Inner SO(3) |
|---|---|---:|---:|---:|
| ALL12 | B | -27.58% | -5.78% | +7.69% |
| ALL12 | C5 | +2.78% | +1.61% | +6.82% |
| HF_W09_W14 | B | -3.91% | +6.49% | +14.11% |
| HF_W09_W14 | C5 | +2.28% | +0.25% | +12.50% |
| W15 | B | -10.80% | -4.98% | -8.20% |
| W15 | C5 | +9.66% | +90.54% | -8.20% |
| W00_W08 | B | -52.68% | -23.63% | +529.84% |
| W00_W08 | C5 | +0.05% | -0.01% | +777.40% |
| NO_WIND_W00 | B | not sampled | not sampled | not sampled |
| NO_WIND_W00 | C5 | not sampled | not sampled | not sampled |
| LOW_WIND_W01_W08 | B | -52.68% | -23.63% | +529.84% |
| LOW_WIND_W01_W08 | C5 | +0.05% | -0.01% | +777.40% |

Evidence conclusion: HF task attitude is +6.49% versus B (0/6 scene wins); ALL12 position error is +2.78% versus C5. This development screen misses the high-frequency task-attitude target; overall gains versus B do not establish a pass.


## Candidate scene wins

| Baseline | Metric | Win | Tie | Loss |
|---|---|---:|---:|---:|
| B | Q_m | 9 | 0 | 3 |
| B | task_SO3_rad | 5 | 0 | 7 |
| B | inner_SO3_rad | 4 | 0 | 8 |
| C5 | Q_m | 6 | 0 | 6 |
| C5 | task_SO3_rad | 3 | 0 | 9 |
| C5 | inner_SO3_rad | 4 | 0 | 8 |

## Per-scene paired outcomes

| Scene | B: Q | B: task | B: inner | C5: Q | C5: task | C5: inner |
|---|---|---|---|---|---|---|
| DL1018_DEV_T1_C10_W09 | WIN (-0.001577) | LOSS (+0.001594) | WIN (-0.003307) | WIN (-0.001058) | LOSS (+0.000523) | WIN (-0.003344) |
| DL1018_VAL_T1_C07_W14 | WIN (-0.000147) | LOSS (+0.002841) | LOSS (+0.001138) | LOSS (+0.001505) | LOSS (+0.000168) | LOSS (+0.001042) |
| DL1018_DEV_T2_C09_W10 | LOSS (+0.001235) | LOSS (+0.009378) | LOSS (+0.007297) | LOSS (+0.000494) | WIN (-0.000182) | LOSS (+0.006219) |
| DL1018_VAL_T2_C04_W14 | LOSS (+0.000606) | LOSS (+0.003017) | LOSS (+0.009013) | LOSS (+0.000476) | LOSS (+0.000043) | LOSS (+0.008965) |
| DL1018_DEV_T3_C09_W09 | WIN (-0.001444) | LOSS (+0.001657) | WIN (-0.001196) | WIN (-0.000066) | LOSS (+0.000014) | WIN (-0.001278) |
| DL1018_VAL_T3_C01_W14 | WIN (-0.001319) | LOSS (+0.003933) | LOSS (+0.000760) | LOSS (+0.000096) | LOSS (+0.000343) | LOSS (+0.000711) |
| DL1018_DEV_T1_C01_W15 | WIN (-0.003892) | WIN (-0.001052) | WIN (-0.008052) | WIN (-0.002145) | LOSS (+0.000728) | WIN (-0.008053) |
| DL1018_VAL_T2_C05_W15 | LOSS (+0.002808) | LOSS (+0.002771) | LOSS (+0.006343) | LOSS (+0.004592) | LOSS (+0.006922) | LOSS (+0.006344) |
| DL1018_VAL_T3_C02_W15 | WIN (-0.001526) | WIN (-0.002613) | WIN (-0.002842) | WIN (-0.000547) | LOSS (+0.000448) | WIN (-0.002839) |
| DL1018_VAL_T1_C00_W07 | WIN (-0.004616) | WIN (-0.000481) | LOSS (+0.001587) | LOSS (+0.000044) | WIN (-0.000040) | LOSS (+0.001558) |
| DL1018_DEV_T2_C00_W04 | WIN (-0.015125) | WIN (-0.021940) | LOSS (+0.000369) | WIN (-0.000010) | WIN (-0.000007) | LOSS (+0.000441) |
| DL1018_DEV_T3_C00_W05 | WIN (-0.022358) | WIN (-0.033882) | LOSS (+0.000661) | WIN (-0.000014) | LOSS (+0.000031) | LOSS (+0.000758) |

Safety sample totals: `{"Candidate": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "B": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "C5": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}}`.

Metric functions: frozen `score_full72_candidate_v1.py`; Q is position-error RMS, task/inner attitude use SO(3) geodesic RMSE.
B/C5 raw paths and hashes are inherited from WN12's bound manifest and parent score. B historical runtime-identity limitation remains.
Only DEV/VAL scenes in the 12-scene authorization are used; TEST is not read.
No W00 no-wind scene is in this cohort; the W00-W08 low-wind cohort contains only the listed wind indices.

## Safety counter scope

The frozen scorer fields `attitude_head_projection_samples` and `attitude_head_output_saturated_samples` are legacy v39 counters. Their zero values do not indicate that the MLP15 physical-residual trace had no projection or residual clipping. The read-only MLP trace audit reports **952 final-state weight projections** and **38 residual dmax clip events** for this original 12-scene candidate; the original runtime did not log a separate output-projection counter. See `experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/closed_loop_candidate_v1/audits/MLP15_TRACE_SAFETY_COUNTS_v1.json`.

Both the original and update-first runs include the existing tracking-drive update, so these results do not isolate a pure target-only factor. See `CONTINUATION_STATE_v2.json` for the study continuation note.
