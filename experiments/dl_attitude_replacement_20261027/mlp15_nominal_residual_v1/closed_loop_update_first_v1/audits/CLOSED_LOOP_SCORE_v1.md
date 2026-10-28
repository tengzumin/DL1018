# Closed-loop candidate paired score

Candidate, B, and C5 were scored on the same 12 authorized scenes.

## Paired metrics

| Cohort | N | Method | Q (m) | Task SO(3) (rad) | Inner SO(3) (rad) |
|---|---:|---|---:|---:|---:|
| ALL12 | 12 | Candidate | 0.010629122 | 0.047384987 | 0.014617253 |
| ALL12 | 12 | B | 0.014306172 | 0.050158211 | 0.012760750 |
| ALL12 | 12 | C5 | 0.010079641 | 0.046510930 | 0.012864783 |
| HF_W09_W14 | 6 | Candidate | 0.010915751 | 0.061364099 | 0.018986797 |
| HF_W09_W14 | 6 | B | 0.011265770 | 0.057618624 | 0.016192997 |
| HF_W09_W14 | 6 | C5 | 0.010583788 | 0.061204097 | 0.016424750 |
| W15 | 3 | Candidate | 0.008098129 | 0.006179617 | 0.019631905 |
| W15 | 3 | B | 0.008053074 | 0.005979245 | 0.018492348 |
| W15 | 3 | C5 | 0.006550361 | 0.002981792 | 0.018491434 |
| W00_W08 | 3 | Candidate | 0.012586858 | 0.060632133 | 0.000863515 |
| W00_W08 | 3 | B | 0.026640074 | 0.079416352 | 0.000164656 |
| W00_W08 | 3 | C5 | 0.012600625 | 0.060653732 | 0.000118197 |
| NO_WIND_W00 | 0 | Candidate | not sampled | not sampled | not sampled |
| NO_WIND_W00 | 0 | B | not sampled | not sampled | not sampled |
| NO_WIND_W00 | 0 | C5 | not sampled | not sampled | not sampled |
| LOW_WIND_W01_W08 | 3 | Candidate | 0.012586858 | 0.060632133 | 0.000863515 |
| LOW_WIND_W01_W08 | 3 | B | 0.026640074 | 0.079416352 | 0.000164656 |
| LOW_WIND_W01_W08 | 3 | C5 | 0.012600625 | 0.060653732 | 0.000118197 |

Macro percent change of Candidate versus baseline (positive means higher error):

| Cohort | Baseline | Q | Task SO(3) | Inner SO(3) |
|---|---|---:|---:|---:|
| ALL12 | B | -25.70% | -5.53% | +14.55% |
| ALL12 | C5 | +5.45% | +1.88% | +13.62% |
| HF_W09_W14 | B | -3.11% | +6.50% | +17.25% |
| HF_W09_W14 | C5 | +3.14% | +0.26% | +15.60% |
| W15 | B | +0.56% | +3.35% | +6.16% |
| W15 | C5 | +23.63% | +107.25% | +6.17% |
| W00_W08 | B | -52.75% | -23.65% | +424.44% |
| W00_W08 | C5 | -0.11% | -0.04% | +630.57% |
| NO_WIND_W00 | B | not sampled | not sampled | not sampled |
| NO_WIND_W00 | C5 | not sampled | not sampled | not sampled |
| LOW_WIND_W01_W08 | B | -52.75% | -23.65% | +424.44% |
| LOW_WIND_W01_W08 | C5 | -0.11% | -0.04% | +630.57% |

Evidence conclusion: HF task attitude is +6.50% versus B (0/6 scene wins); ALL12 position error is +5.45% versus C5. This development screen misses the high-frequency task-attitude target; overall gains versus B do not establish a pass.


## Candidate scene wins

| Baseline | Metric | Win | Tie | Loss |
|---|---|---:|---:|---:|
| B | Q_m | 9 | 0 | 3 |
| B | task_SO3_rad | 4 | 0 | 8 |
| B | inner_SO3_rad | 4 | 0 | 8 |
| C5 | Q_m | 5 | 0 | 7 |
| C5 | task_SO3_rad | 3 | 0 | 9 |
| C5 | inner_SO3_rad | 4 | 0 | 8 |

## Per-scene paired outcomes

| Scene | B: Q | B: task | B: inner | C5: Q | C5: task | C5: inner |
|---|---|---|---|---|---|---|
| DL1018_DEV_T1_C10_W09 | WIN (-0.001394) | LOSS (+0.001265) | WIN (-0.002262) | WIN (-0.000875) | LOSS (+0.000193) | WIN (-0.002299) |
| DL1018_VAL_T1_C07_W14 | WIN (-0.000272) | LOSS (+0.002926) | LOSS (+0.001052) | LOSS (+0.001381) | LOSS (+0.000254) | LOSS (+0.000956) |
| DL1018_DEV_T2_C09_W10 | LOSS (+0.000645) | LOSS (+0.009552) | LOSS (+0.005615) | WIN (-0.000096) | WIN (-0.000008) | LOSS (+0.004538) |
| DL1018_VAL_T2_C04_W14 | LOSS (+0.000324) | LOSS (+0.003092) | LOSS (+0.007988) | LOSS (+0.000193) | LOSS (+0.000118) | LOSS (+0.007940) |
| DL1018_DEV_T3_C09_W09 | WIN (-0.001239) | LOSS (+0.001702) | WIN (-0.000566) | LOSS (+0.000138) | LOSS (+0.000059) | WIN (-0.000648) |
| DL1018_VAL_T3_C01_W14 | WIN (-0.000164) | LOSS (+0.003934) | LOSS (+0.004936) | LOSS (+0.001251) | LOSS (+0.000344) | LOSS (+0.004886) |
| DL1018_DEV_T1_C01_W15 | WIN (-0.002196) | WIN (-0.001005) | WIN (-0.001412) | WIN (-0.000449) | LOSS (+0.000775) | WIN (-0.001413) |
| DL1018_VAL_T2_C05_W15 | LOSS (+0.002628) | LOSS (+0.001542) | LOSS (+0.006802) | LOSS (+0.004411) | LOSS (+0.005693) | LOSS (+0.006803) |
| DL1018_VAL_T3_C02_W15 | WIN (-0.000297) | LOSS (+0.000064) | WIN (-0.001971) | LOSS (+0.000682) | LOSS (+0.003126) | WIN (-0.001969) |
| DL1018_VAL_T1_C00_W07 | WIN (-0.004629) | WIN (-0.000503) | LOSS (+0.001297) | LOSS (+0.000031) | WIN (-0.000063) | LOSS (+0.001268) |
| DL1018_DEV_T2_C00_W04 | WIN (-0.015123) | WIN (-0.021940) | LOSS (+0.000326) | WIN (-0.000009) | WIN (-0.000007) | LOSS (+0.000398) |
| DL1018_DEV_T3_C00_W05 | WIN (-0.022407) | WIN (-0.033909) | LOSS (+0.000474) | WIN (-0.000064) | LOSS (+0.000004) | LOSS (+0.000571) |

Safety sample totals: `{"Candidate": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "B": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}, "C5": {"motor_saturation_samples": 0, "generalized_clip_samples": 0, "tilt_limited_samples": 0, "attitude_head_projection_samples": 0, "attitude_head_output_saturated_samples": 0}}`.

Metric functions: frozen `score_full72_candidate_v1.py`; Q is position-error RMS, task/inner attitude use SO(3) geodesic RMSE.
B/C5 raw paths and hashes are inherited from WN12's bound manifest and parent score. B historical runtime-identity limitation remains.
Only DEV/VAL scenes in the 12-scene authorization are used; TEST is not read.
No W00 no-wind scene is in this cohort; the W00-W08 low-wind cohort contains only the listed wind indices.

## Safety counter scope

The frozen scorer fields `attitude_head_projection_samples` and `attitude_head_output_saturated_samples` are legacy v39 counters. Their zero values do not indicate that the MLP15 physical-residual trace had no projection or residual clipping. The read-only MLP trace audit reports **952 final-state projections / 38 residual dmax clip events** for the original candidate and **786 final-state projections / 785 output projections / 33 residual dmax clip events** for update-first. The original runtime did not log a separate output-projection counter. See `experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/closed_loop_candidate_v1/audits/MLP15_TRACE_SAFETY_COUNTS_v1.json`.

Both variants retain the existing tracking-drive update, so this screen does not isolate a pure target-only factor.

## Disposition

**FAIL / CLOSE.** The 12-scene screen misses the HF task-attitude target (+6.50% versus B, 0/6 scene wins); ALL12 position error is +5.45% versus C5 and W15 position error is +23.63% versus C5. Do not expand this candidate to the full 72-scene cohort.
