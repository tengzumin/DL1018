Figure: position-context transfer in two fixed TRAIN diagnostic scenes (T1/T3, C15, W14). The attitude controller remains the original RBF in all four flights. Blue and orange denote the B and C5 position-controller contexts, respectively. Each scatter contains all 1,999 attitude events. The dashed rectangle is the component-wise min/max rectangle over all 1,535,232 events from the 768 original TRAIN scenes; it is not an estimate of joint support. C5 has 613/1,999 and 628/1,999 events outside this rectangle, versus zero in both B flights. Bottom panels evaluate the same frozen A1 predictor on each flight's own reconstructed physical residual target. These are offline prediction RMSEs, not attitude tracking RMSEs or closed-loop neural-controller results. The two selected diagnostic pairs do not estimate aggregate performance or uncertainty across trajectories or training seeds.

Reproduction (PowerShell 7, from repository root):

```powershell
python reports/attitude_position_context_probe_20261024/figures/gen_fig_position_context_diagnostic_v1.py
```

The script verifies pinned input hashes and recomputes outside counts before drawing. Current inspected outputs are `fig_position_context_diagnostic_v2.pdf` and `.png`; v1 is retained as the first layout. The no-overwrite guard means rerunning requires a fresh output version. No fitting, Plant calls, raw MAT reads, or TEST access occurs.
