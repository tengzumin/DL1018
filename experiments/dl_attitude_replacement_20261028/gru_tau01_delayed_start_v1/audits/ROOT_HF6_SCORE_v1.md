# Delayed-start GRU HF6 paired screen

Status: **COMPLETE_HF6_SCREEN**. Completed scenes: 6/6.
Fixed DEV/VAL HF6 screen; this is development screening, not independent validation. TEST was not read.

| Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |
|---|---:|---:|---:|
| Delayed_Start_Candidate | 0.0109986132 | 0.0602141073 | 0.0143223597 |
| Tau01 | 0.0121748847 | 0.0596097091 | 0.01433596 |
| Parent_Cosine_GRU | 0.0101411273 | 0.0611989934 | 0.014410202 |
| B | 0.0112657697 | 0.0576186242 | 0.0161929971 |
| C5 | 0.0105837878 | 0.0612040974 | 0.0164247501 |

Candidate relative change versus baseline (%; negative is lower error):

| Baseline | Q | task SO(3) | inner SO(3) |
|---|---:|---:|---:|
| Tau01 | -9.661% | +1.014% | -0.095% |
| Parent_Cosine_GRU | +8.456% | -1.609% | -0.610% |
| B | -2.371% | +4.505% | -11.552% |
| C5 | +3.919% | -1.618% | -12.800% |

Safety totals by method:

- Delayed_Start_Candidate: 0 nonzero safety event counters across 6 scenes.
- Tau01: 0 nonzero safety event counters across 6 scenes.
- Parent_Cosine_GRU: 0 nonzero safety event counters across 6 scenes.
- B: 0 nonzero safety event counters across 6 scenes.
- C5: 0 nonzero safety event counters across 6 scenes.

Per-scene candidate metrics:

| Scene | Split | Release gen | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |
|---|---|---:|---:|---:|---:|
| DL1018_DEV_T1_C10_W09 | DEV | 2 | 0.00959119326 | 0.0429955996 | 0.020264921 |
| DL1018_DEV_T2_C09_W10 | DEV | 2 | 0.0132817798 | 0.070979215 | 0.0102768897 |
| DL1018_DEV_T3_C09_W09 | DEV | 2 | 0.00951658873 | 0.0603045154 | 0.00965834628 |
| DL1018_VAL_T1_C07_W14 | VAL | 2 | 0.0117926331 | 0.0661320163 | 0.0222542234 |
| DL1018_VAL_T2_C04_W14 | VAL | 2 | 0.0118522907 | 0.0566383433 | 0.00763797001 |
| DL1018_VAL_T3_C01_W14 | VAL | 1 | 0.00995719376 | 0.0642349541 | 0.015841808 |

Release file hashes are recorded per scene; the pilot scene uses archived generation 1 and the other five use generation 2.
Cohort results are limited to this fixed six-scene development screen and do not establish independent validation.
