# Stage1 compensation low-pass replay on HF6

Same-trace DEV/VAL replay only; this is not a changed-state closed-loop result. No TEST, Plant, training, or inertia reconstruction.

The raw compensation is exactly zero at t=0 in all six scenes. The first valid Stage1 inference event is at 0.320 s and is nonzero. Thus initialization at the first sample is zero; the first active event is not zero.

| Replay | Mean compensation RMS (m/s²) | Mean ideal-inner task→filtered (mrad) | Δ vs B (mrad) | Scenes better than B | Mean command-accel perturbation RMS (m/s²) |
|---|---:|---:|---:|---:|---:|
| raw | 0.702389 | 62.197 | +1.647 | 2/6 | 0.000000 |
| fc=18/(2π) Hz, 1-ms | 0.633112 | 60.752 | +0.202 | 3/6 | 0.289381 |
| τ=0.1 s, 1-ms curve | 0.603949 | 59.621 | -0.928 | 5/6 | 0.344353 |
| τ=0.1 s, 100-Hz update + hold | 0.604188 | 59.655 | -0.895 | 5/6 | 0.328929 |

B mean task→logged-filtered-reference: 60.550 mrad.
First-event coefficients: old 1-ms=0.01784; τ=0.1 1-ms=0.00995; τ=0.1 100-Hz=0.09516.
The 100-Hz recurrence applies a larger update at the event and holds it between events. It is not pointwise equivalent to the 1-ms curve; the first-event responses differ, and the event-based output leads the gradual 1-ms rise by nearly one event interval.
The conditional task estimate freezes the recorded position/state trajectory, recalculates the outer-loop target from the filtered compensation, and replays the original attitude command filter. It assumes perfect inner tracking of that replayed filter output.
Position Q was not recomputed. The command-acceleration perturbation shows the position-loop path can change, so none of these conditional task numbers predicts closed-loop position or attitude performance.
