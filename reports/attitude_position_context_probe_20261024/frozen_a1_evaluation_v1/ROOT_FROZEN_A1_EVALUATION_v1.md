# Frozen A1 matched-position evaluation

Status: **PASS_GATES**. A1 checkpoint step 30000, canonical float64 deployment, all 1,999 events per flight.

| Flight | Position mode | Yaw RMSE (rad/s²) | Roll / pitch / yaw RMSE (rad/s²) | SO(3) RMSE (deg, left 20,000) | Position Q (m, full 20,001 states) | Motor sat. | Generalized clip |
|---|---|---:|---|---:|---:|---:|---:|
| T1_B | B_POSITION_RBF | 0.180425 | 0.153953, 0.158218, 0.180425 | 0.888777 | 0.010263 | 0 | 0 |
| T1_C5 | C5_POSITION_M110 | 0.332624 | 0.904193, 1.47277, 0.332624 | 0.906507 | 0.00912606 | 0 | 0 |
| T3_B | B_POSITION_RBF | 0.247918 | 0.2235, 0.160723, 0.247918 | 1.2002 | 0.013285 | 0 | 0 |
| T3_C5 | C5_POSITION_M110 | 0.508014 | 1.36726, 1.55496, 0.508014 | 1.20639 | 0.0114822 | 0 | 0 |

| Pair | B yaw RMSE | C5 yaw RMSE | Δ C5−B | Δ ≥ 0.02 | C5 ≥ 1.25×B | Pass |
|---|---:|---:|---:|---|---|---|
| T1 | 0.180425 | 0.332624 | 0.152199 | True | True | True |
| T3 | 0.247918 | 0.508014 | 0.260096 | True | True | True |

SO(3)/position tracking values are per-flight descriptive metrics against each flight's own filtered/reference trajectory. The paired offline prediction gate is the preregistered context-transfer test; neither metric establishes component causality or shared-reference control performance.

Deferred from the frozen taskbook: all-TRAIN alphaXY support range and wind/old-action decomposition. See the JSON `deferred_taskbook_items` for scope.
