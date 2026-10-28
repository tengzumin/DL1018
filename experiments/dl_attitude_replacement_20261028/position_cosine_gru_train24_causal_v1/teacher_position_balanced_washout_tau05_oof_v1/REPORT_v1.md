# Fixed tau=0.5 s causal washout TRAIN24 OOF replay

- Source: exact 24-scene TRAIN_C5_24 OOF student; fixed four scene-group folds; no retraining.
- Filter: `alpha=exp(-0.01/0.5)=0.9801986814`; scene reset; readiness starts at zero-based event 31; original beta rise 1.8 s; residual and total action clips retained.
- No VAL/TEST raw, Plant call, or inertia reconstruction.

| Method | Position residual macro (m/s²) | Position pooled (m/s²) | Frozen SO(3) macro (rad) | Scene DC bias macro (m/s²) | 1-s bias macro (m/s²) |
|---|---:|---:|---:|---:|---:|
| C5_baseline | 0.200214 | 0.239729 | 0.057216 | 0.000000 | 0.000000 |
| no_DC_student | 0.196671 | 0.228069 | 0.053238 | 0.048662 | 0.062803 |
| DC_penalty_student | 0.190022 | 0.223685 | 0.056681 | 0.007590 | 0.020837 |
| tau05_washout_student | 0.192414 | 0.226284 | 0.056828 | 0.001125 | 0.018861 |

## Predeclared thresholds

All four pass: **False**

| Metric | Limit | Observed | Pass |
|---|---:|---:|---|
| Scene DC bias macro (m/s²) | ≤0.010 | 0.001125 | True |
| 1-s bias macro (m/s²) | ≤0.025 | 0.018861 | True |
| Frozen SO(3) macro (rad) | ≤0.054 | 0.056828 | False |
| Position residual macro (m/s²) | ≤0.197 | 0.192414 | True |

## Fold-level washout metrics

| Fold | Scenes | Position macro (m/s²) | Frozen SO(3) macro (rad) | DC bias macro (m/s²) | 1-s bias macro (m/s²) |
|---|---:|---:|---:|---:|---:|
| holdout_W00_05 | 6 | 0.114924 | 0.058931 | 0.001372 | 0.022998 |
| holdout_W06_10 | 8 | 0.239778 | 0.069218 | 0.001120 | 0.018279 |
| holdout_W11_13 | 4 | 0.228481 | 0.057969 | 0.001176 | 0.016851 |
| holdout_W14_15 | 6 | 0.182709 | 0.037443 | 0.000852 | 0.016842 |

## Limits

Position residual is acceleration-target residual, not geometric position error. Frozen SO(3) is scored by replaying the candidate action against fixed C5 states/yaw/reference and does not estimate closed-loop state feedback. This is a development replay on previously used TRAIN24 OOF scenes, not an independent validation.
