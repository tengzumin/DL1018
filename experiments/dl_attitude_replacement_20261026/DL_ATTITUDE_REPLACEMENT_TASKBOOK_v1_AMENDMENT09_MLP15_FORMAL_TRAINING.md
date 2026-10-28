# Amendment 09 — promote MLP15 for one formal teacher-action fit

Date: 2026-10-26 (Asia/Shanghai). The primary-model review of Amendment 08 and its independent audit is complete.

## Decision

Promote MLP15 from the equal-budget offline screen to one formal training run. It had the lowest independent VAL48 teacher-action RMSE at 2,000 steps (0.5235933016), ahead of TCN15 (0.5599352790), GRU15 (0.5683463714), and DSSM15 (0.6536864665). It also took 4.15 s to train and 0.096 s for full VAL, compared with 980.29 s and 71.56 s for TCN15. The 28k-step partial TCN score is retained as an unequal-budget diagnostic and is not the architecture selection basis.

This is a candidate-promotion decision only, not final model selection. Teacher-action fit is not closed-loop performance. Compare the MLP in same-scene closed-loop trials against the frozen B reference and reuse eligible C5/C5_10 comparators before selecting it. If the pilot does not meet the frozen safety/performance gate, do not promote it; review the next architecture candidate under the same closed-loop rules. Do not claim replacement success until a candidate passes source/data identity, independent checkpoint audit, Python/MATLAB parity, the no-Plant release gate, paired pilot safety, DEV72, and the sealed one-time TEST48 criteria already frozen in v1.

## Frozen formal fit

- Model: flatten the causal 15-event by 13-feature window (195 values), then Linear(195,64) + SiLU, Linear(64,32) + SiLU, Linear(32,3). No dropout or future features.
- Data: existing frozen B-RBF teacher-action dataset, TRAIN 768 / VAL 48, event target rbf_output_raw in rad/s². Fit input normalizer and per-axis target RMS from TRAIN only.
- Seed 2026102001; 60,000 optimizer steps; batch 512; Adam, learning rate 1e-3, weight decay 1e-5; SmoothL1 beta 1.0.
- Select earliest strict minimum of full VAL48 scene-macro normalized teacher-action RMSE. Batched validation is run at each 1,000-step checkpoint.
- Save only under experiments/dl_attitude_replacement_20261026/mlp15_formal_v1/. Save an atomic optimizer/RNG checkpoint with every progress update so the run can be resumed only after verifying its process is absent and the frozen hashes still match.

The runtime continues to exclude shape-dependent inertia reconstruction, Jhat/Jdot, Plant truth, RBF hidden state, observer, and physics feedforward. Fixed nominal J0 remains part of the existing torque interface. No Plant or TEST access is permitted during training.
