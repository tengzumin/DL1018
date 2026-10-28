# GHP7 G1/W12 pilot score audit v1

Source: `pilot_score_after_G1_W12_v1/pilot_score.json` (release revision 7). Eighteen of 54 slots were scored (G1/W00 and G1/W12); 36 remain. No duplicates or invalid attempt records. All 18 structural completions were true. Raw SHA-256 values matched their run status records.

| Arm | Geometry | Q0–20 (m) | Q8–12 (m) | SO(3) RMSE (rad) | Minimum clearance (m) | 15 mm gate | Feasible |
|---|---|---:|---:|---:|---:|---|---|
| B | ACTIVE | 0.0105160251 | 0.0110401059 | 0.0618696022 | 0.055400 | pass | yes |
| C5_RBF | ACTIVE | 0.0096309829 | 0.0066853375 | 0.0621743100 | 0.052807 | pass | yes |
| C5_RBF_F | ACTIVE | 0.0095120812 | 0.0058488832 | 0.0625277934 | 0.052844 | pass | yes |
| C5_00 | ACTIVE | 0.0097868528 | 0.0076284657 | 0.0622087655 | 0.052792 | pass | yes |
| C5_10 | ACTIVE | 0.0094738101 | 0.0055397140 | 0.0625487675 | 0.052898 | pass | yes |
| C5_01 | ACTIVE | 0.0104010155 | 0.0108032840 | 0.0622354441 | 0.052782 | pass | yes |
| C5_11 | ACTIVE | 0.0095690567 | 0.0062657717 | 0.0623656467 | 0.052841 | pass | yes |
| C5_11 | FIXED_MIN | 0.0092360805 | 0.0058936240 | 0.0571980869 | 0.053718 | pass | yes |
| C5_11 | FIXED_BOUND15 | 0.0105016186 | 0.0055302291 | 0.0650550182 | 0.013314 | fail | no |

All six ACTIVE C5 arms improved position Q0–20 over B in this scene. All six had a slightly larger SO(3) RMSE than B, so the attitude comparison is not consistently favorable. `C5_RBF_F` improved Q0–20 over `C5_RBF` by about 0.119 mm and Q8–12 by about 0.836 mm, while its SO(3) RMSE was 0.000353 rad worse. This is an early scene-specific result, not a cross-scene conclusion.

`C5_11/FIXED_BOUND15` remained stable but had only 13.314 mm minimum clearance, below the 15 mm proxy gate; it remains a failed/infeasible ablation and is not removed from the result set.
