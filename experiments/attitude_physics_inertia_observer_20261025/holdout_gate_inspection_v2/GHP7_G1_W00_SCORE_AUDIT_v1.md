# GHP7 G1/W00 pilot score audit v1

Source: `pilot_score_after_G1_W00_v1/pilot_score.json` (release revision 7). Nine of nine registered slots were scored; 45 slots for later scenes remain missing. All nine are structurally complete and STABLE, with no duplicate or invalid attempt records. Raw SHA-256 values were checked against the run status files before scoring.

| Arm | Geometry | Q0–20 (m) | Q8–12 (m) | SO(3) RMSE (rad) | Minimum clearance (m) | 15 mm gate | Feasible |
|---|---|---:|---:|---:|---:|---|---|
| B | ACTIVE | 0.0125101569 | 0.0176535722 | 0.0633611272 | 0.055401 | pass | yes |
| C5_RBF | ACTIVE | 0.0099752046 | 0.0116848255 | 0.0626458295 | 0.053666 | pass | yes |
| C5_RBF_F | ACTIVE | 0.0098824454 | 0.0112542747 | 0.0626200958 | 0.053758 | pass | yes |
| C5_00 | ACTIVE | 0.0101507733 | 0.0124169512 | 0.0626733488 | 0.053635 | pass | yes |
| C5_10 | ACTIVE | 0.0098118244 | 0.0109578917 | 0.0626083428 | 0.053761 | pass | yes |
| C5_01 | ACTIVE | 0.0108818564 | 0.0150834997 | 0.0628054497 | 0.053560 | pass | yes |
| C5_11 | ACTIVE | 0.0099397241 | 0.0115094775 | 0.0626310501 | 0.053729 | pass | yes |
| C5_11 | FIXED_MIN | 0.0094495664 | 0.0094894453 | 0.0574191657 | 0.054540 | pass | yes |
| C5_11 | FIXED_BOUND15 | 0.0106954416 | 0.0100413986 | 0.0652697975 | 0.013988 | fail | no |

This one scene is diagnostic only. `C5_RBF_F` improves over `C5_RBF` by about 0.093 mm in Q0–20 and 0.431 mm in Q8–12, while `C5_10` is the best active arm in this scene. These differences do not establish a cross-scene ranking. The fixed-bound15 case is retained as an infeasible geometry ablation; it was stable and did not trigger the flight safety stop.
