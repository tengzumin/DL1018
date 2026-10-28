# TRAIN24 teacher attitude gain and DC-penalty frequency audit

## Scope

Uses locked TRAIN_C5_24 trajectories, the existing feasibility-teacher labels, and both scene-group OOF student outputs. No VAL/TEST data, new Plant call, or inertia reconstruction. Teacher is an in-sample per-scene oracle; its result is not generalization evidence. Student posture values are frozen-trajectory SO(3) replays, not closed-loop scores.

## Full-action comparison

| Method | position residual macro (m/s²) | frozen SO(3) macro (rad) | 0–5 s | 5–10 s | 10–15 s | 15–20 s | DC bias norm macro (m/s²) |
|---|---:|---:|---:|---:|---:|---:|---:|
| C5_baseline | 0.200214 | 0.057216 | 0.051232 | 0.059568 | 0.060251 | 0.055190 | 0.000000 |
| feasibility_teacher | 0.199788 | 0.047988 | 0.044211 | 0.049874 | 0.050081 | 0.045775 | 0.091215 |
| student_no_dc | 0.196671 | 0.053238 | 0.047607 | 0.055330 | 0.056452 | 0.051336 | 0.047907 |
| student_dc_penalty | 0.190022 | 0.056681 | 0.050456 | 0.058789 | 0.059952 | 0.055016 | 0.007472 |

## Correction spectra

Band fractions below are averaged per scene after separating the per-scene mean (DC) from nonzero-frequency variance.

| Method | <0.5 Hz | 0.5–2 Hz | 2–5 Hz | 5–20 Hz | 20–50 Hz |
|---|---:|---:|---:|---:|---:|
| C5_baseline | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| feasibility_teacher | 0.432 | 0.354 | 0.211 | 0.002 | 0.000 |
| student_no_dc | 0.522 | 0.249 | 0.223 | 0.007 | 0.000 |
| student_dc_penalty | 0.358 | 0.295 | 0.339 | 0.008 | 0.000 |

## Band-only attitude proxy

Each row injects one zero-phase filtered action-correction band into the logged C5 action, then replays the exact frozen 1-ms attitude command filter. Bands are evaluated separately, so scores are non-additive.

| Method | Correction band | 0–5 s SO(3) | 5–10 s | 10–15 s | 15–20 s | all 20 s |
|---|---|---:|---:|---:|---:|---:|
| feasibility_teacher | 0.05_0.5Hz | 0.049602 | 0.058809 | 0.059811 | 0.054607 | 0.056316 |
| feasibility_teacher | 0.5_2Hz | 0.050700 | 0.058700 | 0.059464 | 0.054499 | 0.056495 |
| feasibility_teacher | 2_5Hz | 0.051179 | 0.059485 | 0.060185 | 0.055140 | 0.057152 |
| feasibility_teacher | 5_20Hz | 0.051232 | 0.059567 | 0.060251 | 0.055190 | 0.057215 |
| feasibility_teacher | 20_50Hz | 0.051232 | 0.059568 | 0.060251 | 0.055190 | 0.057216 |

## Interpretation and next fixed test

The DC-penalty arm is compared against its no-DC parent by per-scene action spectrum and frozen posture replay above. Use only TRAIN24 findings to select one follow-up recipe. The follow-up must keep the model causal and use a teacher-centered low-frequency target if the teacher's useful posture corrections reside at low frequency; teacher remains offline supervision only. It must be evaluated once under the same four scene-group folds, with no held-out tuning.

Band-only replay is not a causal decomposition: filtered components can interact, and a frozen trajectory cannot model changed feedback states. No result here establishes closed-loop Q.

- Analysis plan SHA-256: `1d39311b46dd440261dc21bf4264c704a20512eabafd5e001f2f80308ce77b63`
- Analysis script SHA-256: `491aaf37f1668d522b911482338efe766be94a90e4c4c55cd99c8eb18c965c95`
- Results JSON SHA-256: `01678f464eb763a4e9931a3c701db2e5718b662ed2937c5cfaa19cddf5ad0d64`
