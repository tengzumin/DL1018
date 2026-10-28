# Filter wn12: 12-scene screen audit

Status: **SCREEN_GATE_FAIL**. Runtime release snapshot SHA: `65607eb089c214bfce0a7d2359d1d873f4b39af04ca310f6db3a2533bf2ab67f`.
Scenes: 12 total; 1 engineering gate + 11 remaining11. Snapshot/launcher exact-ID checks: True; unique run starts: True.
Metric scorer: `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_full72_v1\audits\score_full72_candidate_v1.py` (SHA `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`); gravity 9.8 m/s², max tilt 0.523598775598 rad.

## Macro means and group means

| Cohort | n | Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |
|---|---:|---|---:|---:|---:|
| ALL12 | 12 | candidate | 0.0121667732778 | 0.0463080868025 | 0.0114383732429 |
| ALL12 | 12 | B | 0.0143061720022 | 0.0501582114376 | 0.0127607496167 |
| ALL12 | 12 | C5 | 0.0100796405369 | 0.046510929731 | 0.012864782935 |
| ALL12 | 12 | WN18 | 0.0096907731341 | 0.0465254410475 | 0.0114750373251 |
| HF_W09_W14 | 6 | candidate | 0.0125161796282 | 0.0585660301392 | 0.014287696984 |
| HF_W09_W14 | 6 | B | 0.0112657696599 | 0.0576186242038 | 0.0161929970971 |
| HF_W09_W14 | 6 | C5 | 0.0105837878111 | 0.0612040973594 | 0.0164247500807 |
| HF_W09_W14 | 6 | WN18 | 0.0101411272689 | 0.0611989933664 | 0.014410201999 |
| W15 | 3 | candidate | 0.00775452291116 | 0.00370763363991 | 0.0165346483985 |
| W15 | 3 | B | 0.00805307444097 | 0.0059792452499 | 0.0184923481314 |
| W15 | 3 | C5 | 0.00655036147696 | 0.00298179182594 | 0.0184914343771 |
| W15 | 3 | WN18 | 0.00588118932792 | 0.00305472950038 | 0.0165349928148 |
| W00_W08 | 3 | candidate | 0.0158802109436 | 0.0643926532917 | 0.000643450605153 |
| W00_W08 | 3 | B | 0.0266400742482 | 0.0794163520928 | 0.000164656141233 |
| W00_W08 | 3 | C5 | 0.0126006250485 | 0.0606537323793 | 0.00011819720137 |
| W00_W08 | 3 | WN18 | 0.0125996486708 | 0.060649047957 | 0.000544752487641 |

WN12 minus parent WN18 (same frozen scorer; negative means lower error):

- ALL12 (n=12): ΔQ=0.00247600014366 m; Δtask SO(3)=-0.00021735424507 rad; Δinner SO(3)=-3.66640822438e-05 rad.
- HF_W09_W14 (n=6): ΔQ=0.00237505235931 m; Δtask SO(3)=-0.00263296322723 rad; Δinner SO(3)=-0.000122505015087 rad.
- W15 (n=3): ΔQ=0.00187333358324 m; Δtask SO(3)=0.000652904139526 rad; Δinner SO(3)=-3.44416314888e-07 rad.
- W00_W08 (n=3): ΔQ=0.00328056227278 m; Δtask SO(3)=0.00374360533466 rad; Δinner SO(3)=9.86981175126e-05 rad.

## TASKBOOK screen gates

- PASS — `Q_candidate_lte_B`
- FAIL — `Q_candidate_lte_1_05_C5`
- PASS — `task_SO3_candidate_strictly_lt_B`
- PASS — `task_SO3_candidate_strictly_lt_C5`
- PASS — `safety_zero_all_12_candidate_raws`
- PASS — `all_12_integrity_checks`
- PASS — `all_12_scores_available`
- FAIL — `overall_pass`

## Candidate safety counts

| Scene | Motor sat | Generalized clip | Tilt limit | Head projection | Head saturated |
|---|---:|---:|---:|---:|---:|
| DL1018_DEV_T1_C10_W09 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T1_C07_W14 | 0 | 0 | 0 | 0 | 0 |
| DL1018_DEV_T2_C09_W10 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T2_C04_W14 | 0 | 0 | 0 | 0 | 0 |
| DL1018_DEV_T3_C09_W09 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T3_C01_W14 | 0 | 0 | 0 | 0 | 0 |
| DL1018_DEV_T1_C01_W15 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T2_C05_W15 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T3_C02_W15 | 0 | 0 | 0 | 0 | 0 |
| DL1018_VAL_T1_C00_W07 | 0 | 0 | 0 | 0 | 0 |
| DL1018_DEV_T2_C00_W04 | 0 | 0 | 0 | 0 | 0 |
| DL1018_DEV_T3_C00_W05 | 0 | 0 | 0 | 0 | 0 |

## Strict per-scene wins (ties within 1e-12)

- Candidate vs B, Q_m: 7 wins, 0 ties, 5 losses.
- Candidate vs B, task_SO3_rad: 7 wins, 0 ties, 5 losses.
- Candidate vs B, inner_SO3_rad: 9 wins, 0 ties, 3 losses.
- Candidate vs C5, Q_m: 1 wins, 0 ties, 11 losses.
- Candidate vs C5, task_SO3_rad: 6 wins, 0 ties, 6 losses.
- Candidate vs C5, inner_SO3_rad: 9 wins, 0 ties, 3 losses.

## Audit findings

- Candidate raw path differs from the locked planned output path in 1 scene(s); the first engineering-gate raw remains status/SHA-bound at its original location.
- Parent WN18 comparator raw replay lineage: 12/12 pass; two W15 rows reuse the existing dev_v1 raw lineage.
- Attempt markers missing `authorization_phase`: 12/12. See JSON for the phase-counter impact and run_start/launcher duplicate guard evidence.
- Source tree: v1 runtime files 59/59; v2 files 60/60. v1 wrapper bytes remain unavailable.
- No MATLAB/Plant/training was launched by this audit; no TEST inputs were read; raw files were not changed.

Full provenance, per-scene metrics, all checks and findings: `SCREEN12_RESULTS_v1.json`. Per-scene table: `SCREEN12_RESULTS_v1.csv`.
