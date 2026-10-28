# Applied notch HF6 frozen-score audit

Six fixed scenes rescored with the frozen FULL72 `score_raw`. This is a development screen, not independent validation. The scorer made no Plant calls and did not train, read TEST, or reconstruct inertia.

## Macro mean

| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |
|---|---:|---:|---:|
| Applied_Notch_3p5Hz_Q1 | 10.609 | 60.033 | 14.471 |
| B | 11.266 | 57.619 | 16.193 |
| C5 | 10.584 | 61.204 | 16.425 |
| Parent_Cosine_GRU | 10.141 | 61.199 | 14.410 |

Candidate minus comparator macro mean (negative means lower error):

| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |
|---|---:|---:|---:|
| B | -0.657 | +2.415 | -1.722 |
| C5 | +0.025 | -1.171 | -1.953 |
| Parent_Cosine_GRU | +0.468 | -1.166 | +0.061 |

## Per-scene frozen scores

| Scene | Method | Q (mm) | task (mrad) | inner (mrad) | clip events X/Y/Z | max raw/limit |
|---|---|---:|---:|---:|---:|---:|
| DL1018_VAL_T3_C01_W14 | Applied_Notch_3p5Hz_Q1 | 10.100 | 61.548 | 16.555 | 0/0/0 | 0.4118 |
| DL1018_VAL_T3_C01_W14 | B | 11.405 | 61.792 | 17.915 | 0/0/0 | 0.0000 |
| DL1018_VAL_T3_C01_W14 | C5 | 9.990 | 65.383 | 17.965 | 0/0/0 | 0.0000 |
| DL1018_VAL_T3_C01_W14 | Parent_Cosine_GRU | 9.621 | 65.417 | 15.910 | 0/0/0 | 0.0000 |
| DL1018_DEV_T1_C10_W09 | Applied_Notch_3p5Hz_Q1 | 9.867 | 43.981 | 20.187 | 0/0/0 | 0.2672 |
| DL1018_DEV_T1_C10_W09 | B | 10.985 | 42.201 | 23.237 | 0/0/0 | 0.0000 |
| DL1018_DEV_T1_C10_W09 | C5 | 10.466 | 43.273 | 23.274 | 0/0/0 | 0.0000 |
| DL1018_DEV_T1_C10_W09 | Parent_Cosine_GRU | 9.493 | 43.308 | 20.245 | 0/0/0 | 0.0000 |
| DL1018_DEV_T2_C09_W10 | Applied_Notch_3p5Hz_Q1 | 11.880 | 76.234 | 10.649 | 0/0/0 | 0.5167 |
| DL1018_DEV_T2_C09_W10 | B | 10.612 | 63.600 | 10.314 | 0/0/0 | 0.0000 |
| DL1018_DEV_T2_C09_W10 | C5 | 11.354 | 73.160 | 11.392 | 0/0/0 | 0.0000 |
| DL1018_DEV_T2_C09_W10 | Parent_Cosine_GRU | 11.319 | 73.055 | 10.686 | 0/0/0 | 0.0000 |
| DL1018_DEV_T3_C09_W09 | Applied_Notch_3p5Hz_Q1 | 10.035 | 61.440 | 9.654 | 0/0/0 | 0.3205 |
| DL1018_DEV_T3_C09_W09 | B | 11.022 | 59.061 | 10.703 | 0/0/0 | 0.0000 |
| DL1018_DEV_T3_C09_W09 | C5 | 9.645 | 60.705 | 10.785 | 0/0/0 | 0.0000 |
| DL1018_DEV_T3_C09_W09 | Parent_Cosine_GRU | 9.418 | 60.663 | 9.645 | 0/0/0 | 0.0000 |
| DL1018_VAL_T1_C07_W14 | Applied_Notch_3p5Hz_Q1 | 11.702 | 63.426 | 22.016 | 0/0/0 | 0.4772 |
| DL1018_VAL_T1_C07_W14 | B | 13.799 | 64.501 | 25.873 | 0/0/0 | 0.0000 |
| DL1018_VAL_T1_C07_W14 | C5 | 12.147 | 67.174 | 25.969 | 0/0/0 | 0.0000 |
| DL1018_VAL_T1_C07_W14 | Parent_Cosine_GRU | 11.389 | 67.207 | 22.443 | 0/0/0 | 0.0000 |
| DL1018_VAL_T2_C04_W14 | Applied_Notch_3p5Hz_Q1 | 10.069 | 53.569 | 7.767 | 0/0/0 | 0.3174 |
| DL1018_VAL_T2_C04_W14 | B | 9.772 | 54.556 | 9.115 | 0/0/0 | 0.0000 |
| DL1018_VAL_T2_C04_W14 | C5 | 9.902 | 57.530 | 9.162 | 0/0/0 | 0.0000 |
| DL1018_VAL_T2_C04_W14 | Parent_Cosine_GRU | 9.608 | 57.543 | 7.532 | 0/0/0 | 0.0000 |

## Release and source binding

Pilot snapshot RELEASE SHA-256 `3d7a513464e562eed657d90d7f7ad993c848d901649d84570bc7e9bf08794e3d`; pilot source-lock snapshot SHA-256 `f2159df0f9aea6506a1da8aee86cbde1f1d132eb9030df4b84ce3310a26a610c`.
Current continuation RELEASE SHA-256 `7ae9a1d48619650fcfe353d0bba9d1bf601c39703a3398821d3b690c05d9b341`; source lock SHA-256 `cea7057cc62c0dd6b4f688c90b7017d5918914cd7511929a87e89d4fecab9219`. Candidate runs used release hashes `3d7a513464e562eed657d90d7f7ad993c848d901649d84570bc7e9bf08794e3d, 7ae9a1d48619650fcfe353d0bba9d1bf601c39703a3398821d3b690c05d9b341` and source-lock hashes `cea7057cc62c0dd6b4f688c90b7017d5918914cd7511929a87e89d4fecab9219, f2159df0f9aea6506a1da8aee86cbde1f1d132eb9030df4b84ce3310a26a610c`.
Verified 66 archived pilot source files and 66 current locked source files. The pilot and continuation are intentionally reported as different release generations.

## Safety and interpretation

Per-scene safety counters come from the frozen scorer. Candidate event-level notch clipping and path-reconstruction errors are in the JSON next to each scene. B, C5, and parent GRU comparators are separate runs on the same scene, not paired-state trajectories.
This fixed HF6 set is a development screen. A fresh grouped holdout is required before selecting a winner.

Reproduce after all six candidate statuses are complete: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/score_notch_hf6_v1.py`.
