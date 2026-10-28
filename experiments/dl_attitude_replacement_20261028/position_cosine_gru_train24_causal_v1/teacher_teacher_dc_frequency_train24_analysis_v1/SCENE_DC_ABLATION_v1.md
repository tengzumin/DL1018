# Scene-mean action ablation (TRAIN24 frozen task)

Scene mean is measured from ready event actions. `DC-only` injects that vector on ready rows; `mean-removed` subtracts it from the full correction. Both are offline ablations on frozen C5 trajectories.

| Method | DC norm macro | Full SO(3) | DC-only SO(3) | Mean-removed SO(3) |
|---|---:|---:|---:|---:|
| teacher | 0.092651 | 0.047988 | 0.049963 | 0.055449 |
| student_no_dc | 0.048662 | 0.053238 | 0.053921 | 0.056565 |
| student_dc | 0.007590 | 0.056681 | 0.056976 | 0.056924 |

Per-method 5-second window scores are in the JSON. The DC-only/mean-removed contrasts are non-additive frozen-task diagnostics and do not predict closed-loop Q.
