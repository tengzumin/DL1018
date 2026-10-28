# Root independent decision: WN12 attitude screen

Date: 2026-10-27

## Decision

The 12-scene WN12 screen is complete and **fails its frozen screen gate**. It does not show that learned attitude replacement is impossible, and it does not justify expanding this WN12 configuration to DEV72 or TEST. The failure is the position-retention gate: macro Q is 12.1668 mm versus C5 at 10.0796 mm, exceeding the frozen 1.05×C5 limit (10.5836 mm) by 1.5832 mm. The candidate passes Q versus B (14.3062 mm), task SO(3) versus B (50.158 mrad) and C5 (46.511 mrad), 12/12 integrity, and all safety counters are zero.

The candidate's inner attitude tracking macro is 11.438 mrad, below B (12.761 mrad) and C5 (12.865 mrad). Thus the evidence does not support “attitude is necessarily poor.” However, HF task SO(3) is 58.566 mrad versus B at 57.619 mrad; the HF inner tracking error is better than B/C5, while the overall position-related task and trajectory metrics remain coupled. This distinction must be kept in future reports.

## Why the change looked small

This study intentionally changed only the shared attitude command filter frequency from WN18 [18,18,12] to WN12 [12,12,12]. The neural model SHA stayed identical. This was a controller-configuration isolation test, not a new network or learned-head implementation. On the same 12 scenes, WN12 versus parent WN18 increased Q by 2.476 mm on average, with Q worse in all 12 scenes. HF task SO(3) improved by 2.633 mrad, but W15 worsened by 0.653 mrad and W00–W08 worsened by 3.744 mrad. The shared filter therefore trades better HF reference tracking for broader position/task cost; this setting should not be retained.

## Integrity and resource record

The independent audit script reports no audit failures. Candidate 12/12 runs completed stable with 20,000 transitions and 20,001 states; all five safety counts are zero. Parent WN18 replay lineage passes 12/12. Known historical limitations are retained: the first raw's v1 wrapper/runtime release bytes were not preserved, its raw remains bound by status/SHA at its original path, and all 12 marker files omit authorization_phase despite exact unique remaining11 run_start IDs matching the authorized snapshot and launcher.

No MATLAB process is currently running. This audit launched no MATLAB/Plant, training, or new flight; it did not read TEST or change any raw, model, or cache. The run ledger remains 16 MATLAB process starts, 12 completed Plant calls, zero training runs, zero TEST reads. Runtime authorization remains revoked (DRAFT/NONE, 0 authorized calls).

## Next decision

Stop this WN12 branch. Retain its records as a failed screen. For the next candidate, restore the WN18 shared filter and make one attitude-specific learned-controller change under a separate frozen taskbook. Do not repeat the composite tracking update unchanged: its earlier six-scene effect versus prediction-only was small (task SO(3) improved 0.30%, inner tracking 2.32%, Q worsened 2.12%), and it failed B/C5 gates. Keep RBF output/update disabled, use only legal causal inputs and fixed J0, and prohibit time-varying inertia reconstruction. Root must audit the source/data/model identity and no-Plant validation before any new release.

A new isolated next-stage taskbook is now frozen at experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/TASKBOOK_ROOT_v1.md (SHA-256 90dcfedadeedf7cbbd328c61e5f57dab72e7f3a97f33993e51c57eccf08d85f). It authorizes one TRAIN-only residual-target training and offline/no-Plant validation; no Plant call is authorized before root audit.

Binding data-source addendum: experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/TASKBOOK_ROOT_v1_ADDENDUM01.md; SHA-256 2821b83e065a7d1bb82467bf964fb94bf5c2b272d4ee4e0284ff8e13e446c581. It specifies C5 TRAIN_C5_24 only for fitting and C5_VAL48 only for one-shot offline scoring; the B-fixed teacher dataset is excluded.
