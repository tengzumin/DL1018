# Why one-step residual gains may not transfer to closed-loop position Q

## Scope and method

Only the locked 24-scene TRAIN_C5_24 dataset, its already-existing hash-bound parent TRAIN raw runs, and the already-produced scene-group OOF student actions were used. This analysis made no new Plant call, read no VAL/TEST data, and used no inertia reconstruction. No hyperparameter or model was selected from this analysis.

The logged C5 Q is RMS Euclidean position error over 20,001 states. Student-vs-C5 action residual uses the existing 10-ms clipped acceleration target on the held-out scene fold. Action drift uses a unit double-integrator with no feedback solely as a sensitivity proxy; it is not actual position Q.

## Aggregate findings

- Logged C5 Q scene-macro: 0.0103 m (median 0.0105 m).
- One-step acceleration residual: C5 0.200214 vs OOF student 0.196671 m/s² scene-macro; gain 0.003544 m/s².
- OOF action change from C5: pooled mean [0.027814539741930745, 0.018974987187145114, -0.004879894354720366] m/s², componentwise RMS 0.054898 m/s².
- No-feedback double-integrator peak displacement proxy: median 8.960 m, max 22.810 m.
- Baseline Q vs one-step gain across scenes: Spearman rho 0.139 (descriptive p=0.517, n=24).

A large proxy would show that small, persistent action bias can accumulate, but would not establish that the candidate causes a Q increase. The exact closed-loop effect remains unobserved.

## Per-scene TRAIN diagnostics

| Scene | OOF fold | C5 Q (m) | C5 residual | student OOF residual | one-step gain | action RMS Δ | peak no-feedback Δp proxy (m) |
|---|---|---:|---:|---:|---:|---:|---:|
| DL1018_DEV_T1_C00_W03 | holdout_W00_05 | 0.0082 | 0.06401 | 0.08287 | -0.01885 | 0.04670 | 14.317 |
| DL1018_DEV_T1_C01_W15 | holdout_W14_15 | 0.0051 | 0.02696 | 0.04280 | -0.01583 | 0.03350 | 1.161 |
| DL1018_DEV_T1_C04_W00 | holdout_W00_05 | 0.0103 | 0.05242 | 0.07382 | -0.02141 | 0.04985 | 13.486 |
| DL1018_DEV_T1_C05_W06 | holdout_W06_10 | 0.0088 | 0.10067 | 0.10617 | -0.00550 | 0.04344 | 6.745 |
| DL1018_DEV_T1_C07_W08 | holdout_W06_10 | 0.0107 | 0.28572 | 0.27422 | 0.01150 | 0.06669 | 7.157 |
| DL1018_DEV_T1_C10_W09 | holdout_W06_10 | 0.0095 | 0.12671 | 0.12367 | 0.00304 | 0.04201 | 10.900 |
| DL1018_DEV_T1_C11_W12 | holdout_W11_13 | 0.0090 | 0.12078 | 0.11851 | 0.00227 | 0.03363 | 3.698 |
| DL1018_DEV_T1_C15_W14 | holdout_W14_15 | 0.0101 | 0.37093 | 0.35478 | 0.01615 | 0.06002 | 13.716 |
| DL1018_DEV_T2_C00_W04 | holdout_W00_05 | 0.0127 | 0.14097 | 0.15335 | -0.01238 | 0.05979 | 15.397 |
| DL1018_DEV_T2_C02_W15 | holdout_W14_15 | 0.0050 | 0.02695 | 0.04076 | -0.01381 | 0.03330 | 3.343 |
| DL1018_DEV_T2_C03_W01 | holdout_W00_05 | 0.0118 | 0.07451 | 0.10622 | -0.03171 | 0.06195 | 15.517 |
| DL1018_DEV_T2_C06_W07 | holdout_W06_10 | 0.0120 | 0.27054 | 0.26501 | 0.00553 | 0.06420 | 13.837 |
| DL1018_DEV_T2_C08_W08 | holdout_W06_10 | 0.0115 | 0.29257 | 0.27700 | 0.01558 | 0.06484 | 8.153 |
| DL1018_DEV_T2_C09_W10 | holdout_W06_10 | 0.0113 | 0.35294 | 0.33094 | 0.02200 | 0.06351 | 11.891 |
| DL1018_DEV_T2_C12_W13 | holdout_W11_13 | 0.0112 | 0.37077 | 0.34594 | 0.02483 | 0.04473 | 3.800 |
| DL1018_DEV_T2_C14_W14 | holdout_W14_15 | 0.0107 | 0.37656 | 0.33427 | 0.04229 | 0.06567 | 8.340 |
| DL1018_DEV_T3_C00_W05 | holdout_W00_05 | 0.0155 | 0.18126 | 0.18196 | -0.00070 | 0.04606 | 8.886 |
| DL1018_DEV_T3_C03_W15 | holdout_W14_15 | 0.0041 | 0.02699 | 0.03381 | -0.00682 | 0.02515 | 4.462 |
| DL1018_DEV_T3_C05_W02 | holdout_W00_05 | 0.0170 | 0.12086 | 0.14616 | -0.02531 | 0.06571 | 7.676 |
| DL1018_DEV_T3_C06_W08 | holdout_W06_10 | 0.0141 | 0.39847 | 0.38711 | 0.01135 | 0.06212 | 9.773 |
| DL1018_DEV_T3_C09_W09 | holdout_W06_10 | 0.0094 | 0.16245 | 0.15853 | 0.00393 | 0.04104 | 11.351 |
| DL1018_DEV_T3_C10_W11 | holdout_W11_13 | 0.0117 | 0.37587 | 0.34819 | 0.02768 | 0.09297 | 22.810 |
| DL1018_DEV_T3_C13_W12 | holdout_W11_13 | 0.0088 | 0.11899 | 0.11170 | 0.00729 | 0.03053 | 3.388 |
| DL1018_DEV_T3_C15_W14 | holdout_W14_15 | 0.0097 | 0.36623 | 0.32231 | 0.04392 | 0.06575 | 9.035 |

## Why the current loss leaves Q unconstrained

1. The position term predicts a local 10-ms acceleration residual measured while C5 generated the logged states. It rewards matching that label, not minimizing the integral of future position error under an intervention.
2. Teacher distillation carries a frozen-trajectory attitude/task preference into the student. The teacher's per-scene position cap is also checked on those same logged C5 states; neither is a counterfactual rollout of the updated policy.
3. Once a candidate changes position compensation, the vehicle state, the next X14, and all later feedback actions change. Frozen-history OOF cannot propagate that feedback loop. A small coherent bias may alter phase or accumulate over many events even when one-step RMSE improves.
4. Frozen SO(3) command-filter replay is likewise a fixed-state task metric, not coupled position tracking or closed-loop Q.

## Falsifiable next steps without using VAL for tuning

- First use this report's predeclared OOF diagnostics to decide whether the actual student action has appreciable low-frequency/scene-level bias. Do not treat the no-feedback proxy as a Q score.
- A low-cost training-only candidate is a fold-local penalty on the one-second mean or cumulative impulse of `a_student-a_C5`, evaluated under the same whole-scene OOF protocol. Predeclare its scale from training folds only. This tests the specific bias hypothesis; it still does not prove better Q.
- A principled Q objective requires counterfactual closed-loop trajectories or a validated response model. Given the current no-Plant/no-inertia constraint and absence of candidate interventions in TRAIN logs, no training-only loss can identify the candidate's true Q effect. Any eventual claim needs a separately authorized, paired closed-loop evaluation after design freeze.

## Reproducibility

- Analysis plan SHA-256: `c5feadcfe04625a3618e7fe2d55b693a6b9a846f0394a9752070cb752930df2a`
- Analysis script SHA-256: `1254c97202693dd422d9a20d3d22947235754ba725600ea6d70f8f7f111e1d36`
- Results JSON SHA-256: `023881777f2bb6e3ee8f1cc33f5a6839f1e619716fe57b5fe09d70665e5db5cd`
