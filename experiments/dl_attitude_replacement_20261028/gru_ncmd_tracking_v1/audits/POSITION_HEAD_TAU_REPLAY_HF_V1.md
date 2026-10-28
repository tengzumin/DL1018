# Position head τ=0.1 HF replay

## Decision evidence

The prior 60-scene C3 screen records only `C3_DELAYED_PREDICTION_TAU1_RHO001` (τ=1 s, ρ=.01). I found no τ=.1/ρ=.1 run in that screen. The completed original cosine-GRU HF raws save event φ, effective surface, delayed target, initial W, and per-event weights, so the proposed update can be replayed without estimating missing variables.

I replayed the saved six matched DEV/VAL HF scenes twice on their fixed logged trajectories: baseline ρ=.01 and one candidate ρ=.1 (h=.01 s, γ=12, λ=.002, same labels, φ, s_eff, clips, PCF, and GRU). The baseline replay matches logged weights to <4.5e−16 and applied acceleration to <6.7e−16. Original cosine-GRU results:

| Metric (equal mean over six scenes) | ρ=.01 | ρ=.1 |
|---|---:|---:|
| Future 10 ms XY label vector RMSE (m/s²) | 0.3290 | 0.2636 |
| XY learned-force RMS (N) | 0.5010 | 0.4616 |
| 1–3 Hz label-vs-prediction phase, X (deg) | −4.8 | +14.2 |
| 1–3 Hz label-vs-prediction phase, Y (deg) | +12.7 | +9.9 |

Every scene reduced future-label RMSE by 16–28%; XY learned-force RMS changed from +1.3% to −11.8%. The NCMD six-scene replay was consistent (RMSE −20.7%, force RMS −6.6%). The phase changes show that the larger step changes timing as well as fit.

## Recommendation and limits

This is enough evidence for one single-scene τ=.1 pilot on the original cosine-GRU parent. ρ=.1 is a moderate gradient step for unit-norm φ (the fixed-target prediction-gradient direction has unit maximum curvature), but this says nothing about the coupled closed-loop system. The replay holds plant states and features fixed; it is not a closed-loop prediction and cannot establish task or position improvement. Keep the pilot to this one parameter and inspect force/position/task metrics before any expansion.

No Plant was run. The audit reads only completed DEV/VAL HF logs; it does not read TEST, wind, J, or Jdot. Reproduction and per-scene details are in [POSITION_HEAD_TAU_REPLAY_HF_V1.json](POSITION_HEAD_TAU_REPLAY_HF_V1.json); the executable audit is [position_head_tau_replay_hf_v1.py](position_head_tau_replay_hf_v1.py).
