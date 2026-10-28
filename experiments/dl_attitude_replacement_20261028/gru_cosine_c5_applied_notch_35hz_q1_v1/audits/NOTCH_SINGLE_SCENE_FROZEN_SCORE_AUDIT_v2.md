# Notch single-scene frozen-score and signal-path audit

One completed VAL scene; frozen FULL72 `score_raw` rescored the raw logs. Auditor made no Plant calls and did not read TEST or reconstruct inertia. This is a development diagnostic, not independent validation.

## Paired same-scenario scores

| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |
|---|---:|---:|---:|
| B | 11.405 | 61.792 | 17.915 |
| C5 | 9.990 | 65.383 | 17.965 |
| Parent_Cosine_GRU | 9.621 | 65.417 | 15.910 |
| Position_Applied_Lowpass_tau0p1 | 11.163 | 62.134 | 16.422 |
| Applied_Notch_3p5Hz_Q1 | 10.100 | 61.548 | 16.555 |

Notch minus comparator (negative means lower error):

| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |
|---|---:|---:|---:|
| B | -1.305 | -0.244 | -1.360 |
| C5 | +0.110 | -3.834 | -1.410 |
| Parent_Cosine_GRU | +0.479 | -3.869 | +0.645 |
| Position_Applied_Lowpass_tau0p1 | -1.063 | -0.586 | +0.133 |

## Run identity and signal path

Raw SHA-256 `e6e158c2f9a89fa824b0c618dbbf96d486f05a79957b5184e2c1856da844d4b9`; run status `STABLE`, transitions=20000, Plant calls in original run=1; safety stop `none`.
Run-bound archived RELEASE SHA-256 `3d7a513464e562eed657d90d7f7ad993c848d901649d84570bc7e9bf08794e3d`; source lock snapshot SHA-256 `f2159df0f9aea6506a1da8aee86cbde1f1d132eb9030df4b84ce3310a26a610c`. These match run_start, run_status, raw runIdentity, and archived pilot snapshot. Current RELEASE at audit time is `7ae9a1d48619650fcfe353d0bba9d1bf601c39703a3398821d3b690c05d9b341` (same as run snapshot: False); the older no-Plant preparation receipt had a pre-release hash and does not bind this Plant run.
All 66 archived source files verify against the run-bound lock. Current source lock matches the run snapshot: False; current runner bytes match archived runner bytes: False. The archived runner/helper hashes, not later-edited working copies, bind the executed source.
Actual filter: causal 100-Hz 3.5-Hz/Q=1, event indices 10…19990 every 10 samples; position predictor τ=1.0 s, ρ=0.01.
Output clipping events: 0; maximum raw-output/allowed-limit ratio 0.411764.

| Recurrence/link check | Max abs error |
|---|---:|
| notch_recurrence_raw_mps2 | 0.000e+00 |
| notch_output_clip_mps2 | 0.000e+00 |
| clip_flag_mismatch_count | 0.000e+00 |
| event_output_to_held_zoh_mps2 | 0.000e+00 |
| held_to_total_compensation_mps2 | 1.110e-16 |
| compensation_to_force_N | 0.000e+00 |
| held_force_N | 0.000e+00 |
| injected_force_N | 0.000e+00 |
| position_command_from_nominal_minus_comp_mps2 | 4.441e-16 |
| PCF_a_req_equals_position_command_mps2 | 0.000e+00 |

The check follows logged Stage1 event input → exact notch recurrence → logged elementwise clip → held output → total position compensation/force → position command; `stage1_position_pcf_a_req_mps2` equals the actual position commanded acceleration at every logged transition. This verifies that PCF received the command formed with the filtered compensation.

No safety counters were nonzero in the frozen scorer for this scene. Cross-scene conclusions require more scenes; these paired records are separate Plant trajectories.

## Reproduction

From repository root: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/audit_notch_single_scene_v1.py`.
