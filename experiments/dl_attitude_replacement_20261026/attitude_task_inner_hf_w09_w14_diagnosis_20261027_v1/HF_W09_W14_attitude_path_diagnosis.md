# HF_W09_W14 attitude-path diagnosis

Offline read-only diagnosis of the frozen GRU32 Full72 Candidate, B, and C5 raws. No Plant/MATLAB, training, or TEST data were accessed. C5 remains pending parent raw audit per the frozen score report.

## Scope and alignment

Selected exactly 28 unique DEV/VAL scenes with wind IDs W09–W14; read 84 locked raw files (28 scenes × 3 methods). Each raw SHA-256 was checked against the frozen score JSON before reading.

Raw dimensions match the scorer: state/reference acceleration are 20001 samples; time is 0.000–20.000 s at 1 ms; filtered_attitude_reference and command_filter_target_euler are 20000×3; transition_time is exactly time[0:20000]. Within every scene, Candidate/B/C5 time, transition_time, reference acceleration, and reference yaw are exactly equal.

Window metrics use the shared transition instants [0,5), [5,10), [10,15), [15,20), 5000 samples per window. This keeps task, command target, filtered reference, and actual attitude on the same timestamps. The full-duration score reproduction also includes the final state at t=20 s, as the frozen scorer does.

Task Euler attitude reuses the frozen score equation: add gravity to reference acceleration z; derive roll/pitch from reference acceleration and yaw; scale roll/pitch together to the locked max tilt; keep reference yaw. For same-time Euler attitudes A and B, each geodesic sample is θₖ = angle(R_B(tₖ)ᵀ R_A(tₖ)), matching the frozen `Rotation.from_euler('xyz', B).inv() * Rotation.from_euler('xyz', A)` convention; each reported RMSE is sqrt(mean(θₖ²)). `command_filter_target_euler` is the runner's per-transition target from `positionInfo.commanded_acceleration` via `baseline_force_to_attitude`; its timestamps are `transition_time`.
The command-target logging and conversion are visible in the frozen run sources: Candidate `run_mlp15_dev72_closed_loop.m` (target conversion near line 1303, log field near 2960); B `run_paired_observer_closed_loop.m` (near 1221 and 2780); C5 `run_dl1018_closed_loop.m` (near 1169 and 2694).

## Frozen source identities

- Diagnostic script SHA-256: `e04c4bb9f867149c4230a98ad22c2c5b9c77023167a3725caa8d552f98c049b2`
- Frozen score script SHA-256: `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`
- Frozen score JSON SHA-256: `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff`
- Frozen paired score CSV SHA-256: `dfbc732ee97e770ea328d8eeac7efd203f06502cfa56d2ab9a11a74998b66630`
- Gravity / tilt cap: `9.8 m/s²` / `0.523598775598 rad`
- Task-formula release SHA-256: `507f9a13af2d20aca64a08ea7846991198112bd97ca8456dccb9402ec9424862`; formula source SHA-256: `18b4ad900f0d60ef92f9d6a82742ddf7d2bc63e990a59c9ee72679b06297f182`
- Candidate runner source SHA-256: `a1b9e47992da41b49373f409d9333048b6130698d80614817d64bbc1a652ddcc` (C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_full72_v1\candidate_runner_work\matlab\runtime\run_mlp15_dev72_closed_loop.m)
- B runner source SHA-256: `ef8247080f6be023de105f3e86146d6bd70dc73dfa3fed56584105b85279ac91` (C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_dev72_v1\matlab\runtime\run_paired_observer_closed_loop.m)
- C5 runner source SHA-256: `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c` (C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\position_axis_coordinate_c5_20261023\run_dl1018_closed_loop.m)
- Raw identities and SHA-256 values: the 84 scene/method rows in the CSV.

## Frozen HF macro comparison

| Method | Task SO(3) actual (mrad) | Inner SO(3) actual (mrad) |
|---|---:|---:|
| Candidate | 58.854 | 13.817 |
| B | 54.816 | 15.506 |
| C5 | 58.795 | 15.688 |

The recomputed full-duration task and inner SO(3) RMSE match the frozen per-scene values within 1e-10 rad for all 84 raws.

## 0–5 s

Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.

| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |
|---|---:|---:|---:|---:|---:|
| Absolute: Candidate | 68.337 | 50.881 | 0.435 | 53.477 | 53.543 |
| Absolute: B | 51.620 | 12.238 | 0.050 | 50.245 | 50.251 |
| Absolute: C5 | 68.246 | 50.725 | 0.206 | 53.460 | 53.467 |
| Candidate − B | 16.717 | 38.643 | 0.385 | 3.232 | 3.292 |
| Candidate − C5 | 0.091 | 0.156 | 0.229 | 0.017 | 0.076 |

Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):

| Signal | Mean RMS rate | Largest per-scene peak rate | Units |
|---|---:|---:|---|
| Reference acceleration | 0.258453 | 0.959424 | m/s³ |
| Reference yaw | 0 | 0 | rad/s |

## 5–10 s

Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.

| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |
|---|---:|---:|---:|---:|---:|
| Absolute: Candidate | 81.441 | 60.821 | 20.969 | 64.877 | 62.531 |
| Absolute: B | 62.464 | 15.678 | 23.664 | 61.645 | 58.135 |
| Absolute: C5 | 82.166 | 60.734 | 23.906 | 65.770 | 62.512 |
| Candidate − B | 18.976 | 45.143 | -2.695 | 3.232 | 4.396 |
| Candidate − C5 | -0.725 | 0.087 | -2.937 | -0.893 | 0.019 |

Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):

| Signal | Mean RMS rate | Largest per-scene peak rate | Units |
|---|---:|---:|---|
| Reference acceleration | 0.661403 | 1.71661 | m/s³ |
| Reference yaw | 0 | 0 | rad/s |

## 10–15 s

Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.

| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |
|---|---:|---:|---:|---:|---:|
| Absolute: Candidate | 80.160 | 59.136 | 13.916 | 64.390 | 62.076 |
| Absolute: B | 61.882 | 15.359 | 15.053 | 60.735 | 57.691 |
| Absolute: C5 | 80.632 | 58.972 | 15.454 | 64.952 | 61.989 |
| Candidate − B | 18.278 | 43.777 | -1.137 | 3.654 | 4.385 |
| Candidate − C5 | -0.473 | 0.165 | -1.538 | -0.562 | 0.087 |

Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):

| Signal | Mean RMS rate | Largest per-scene peak rate | Units |
|---|---:|---:|---|
| Reference acceleration | 0.661644 | 1.71662 | m/s³ |
| Reference yaw | 0 | 0 | rad/s |

## 15–20 s

Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.

| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |
|---|---:|---:|---:|---:|---:|
| Absolute: Candidate | 71.885 | 53.767 | 10.395 | 57.071 | 56.258 |
| Absolute: B | 54.324 | 12.196 | 12.254 | 53.855 | 52.256 |
| Absolute: C5 | 72.222 | 53.710 | 12.284 | 57.555 | 56.212 |
| Candidate − B | 17.561 | 41.572 | -1.859 | 3.216 | 4.003 |
| Candidate − C5 | -0.337 | 0.058 | -1.889 | -0.484 | 0.046 |

Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):

| Signal | Mean RMS rate | Largest per-scene peak rate | Units |
|---|---:|---:|---|
| Reference acceleration | 0.258444 | 0.959424 | m/s³ |
| Reference yaw | 0 | 0 | rad/s |

## ALL: 0–20 s shared 20,000 samples

Absolute group values are macro means across 28 scenes (one RMSE per scene, then equal scene weight); differences are Candidate minus comparator. Values are SO(3) RMSE in mrad.

| Group result | Task→command target | Command target→filtered | Filtered→actual | Task→filtered | Task→actual |
|---|---:|---:|---:|---:|---:|
| Absolute: Candidate | 75.924 | 56.383 | 13.817 | 60.537 | 58.854 |
| Absolute: B | 58.266 | 14.023 | 15.506 | 57.361 | 54.816 |
| Absolute: C5 | 76.344 | 56.266 | 15.688 | 61.113 | 58.795 |
| Candidate − B | 17.658 | 42.360 | -1.689 | 3.176 | 4.038 |
| Candidate − C5 | -0.420 | 0.118 | -1.872 | -0.576 | 0.058 |

Shared external reference-command movement (mean of per-scene rates; identical across Candidate/B/C5 within each scene):

| Signal | Mean RMS rate | Largest per-scene peak rate | Units |
|---|---:|---:|---|
| Reference acceleration | 0.520348 | 1.71662 | m/s³ |
| Reference yaw | 0 | 0 | rad/s |

## What the data supports

- Over ALL shared samples, Candidate actual is 1.689 mrad closer to its filtered reference than B, while Candidate's filtered reference is 3.176 mrad farther from task and its task→actual error is 4.038 mrad higher. Candidate's command target is 17.658 mrad farther from task, and command target→filtered gap is 42.360 mrad higher than B. This supports a pre-inner-loop/reference-chain mismatch accompanying the score reversal: the actual attitude follows Candidate's filtered reference better overall, but that reference is less aligned with the external task. The five SO(3) RMSE links are non-additive, so this does not quantify a causal share.
- In the four same-time bins Candidate task→actual is worse than B by 3.292–4.396 mrad; Candidate task→command target is higher by 16.717–18.976 mrad and command target→filtered by 38.643–45.143 mrad. Candidate filtered→actual is slightly worse in 0–5 s (+0.385 mrad) and better in the later bins (−2.695, −1.137, −1.859 mrad).
- Candidate→B and Candidate→C5 segment deltas are printed for every requested phase and ALL shared samples; a negative delta means a smaller geodesic RMSE for Candidate. The path RMSEs do not add algebraically, so they locate where discrepancies appear but do not assign an additive share of task error.
- The external reference acceleration/yaw is unchanged across the three methods within every scene. The per-phase rate/span values quantify the shared, time-varying commands; they are not candidate-specific input differences.

## Interpretation limits

The logged command target depends on each run's position-controller commanded acceleration and its yaw at that instant. Therefore task→command target measures outer-loop/setpoint divergence from the externally defined task attitude; command target→filtered reference measures the gap across the command filter/reference chain; filtered reference→actual measures inner tracking. The association of a segment with the score pattern is supported by these observations, but causality would require a controlled rerun or intervention. Candidate Full72 is an in-sample DEV/VAL screen; B run labels remain raw-pending-audit and C5 parent audit remains pending as qualified in the frozen score report.

CSV: `HF_W09_W14_attitude_path_by_scene_phase.csv` (420 per-scene/method/phase rows: four windows plus ALL shared samples).
