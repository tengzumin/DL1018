# TRAIN-only design decision for one follow-up fold run

## Evidence used

Only the locked TRAIN_C5_24 traces and existing teacher / student OOF actions were used for this design decision. Frequency/time report SHA-256: `692f9c98ae14763a48d9aa626850c46d93a5b00afebbc989a7f6b25639818a7f`. Scene-mean ablation SHA-256: `c6b6af20f2247cd3e7a5766b8290f6e2cca130c552f96b29acb99e7c8fbfcc94`.

The frozen-task teacher action reduces SO(3) scene-macro from 57.216 to 47.988 mrad, with gains in each 5-second window. Teacher scene-mean action change has macro norm 0.09265 m/s². On the same frozen trajectories, injecting that teacher mean alone scores 49.963 mrad; removing the mean from the full teacher action scores 55.449 mrad. These are non-additive frozen-trajectory diagnostics. Teacher AC correction energy is concentrated below 5 Hz; frequencies above 5 Hz contribute negligibly.

The zero-DC student penalty reduced scene-mean action norm from 0.04866 to 0.00759 m/s². It reduced absolute 0.05–0.5 Hz and 0.5–2 Hz correction energy by about 75% and 52%, while changing the OOF frozen posture proxy from 53.238 to 56.681 mrad. Its position residual improved from 0.196671 to 0.190022 m/s².

The parent also reported a closed-loop pilot where position improved but attitude did not beat B. That result conflicts with the frozen-task teacher benefit and demonstrates that a teacher-centered correction is **not a closed-loop position guarantee**. The pilot information is recorded as context only; it does not set any training scale, weight, window, or selection criterion in this experiment.

## One fixed experiment

Run exactly one four-fold scene-group OOF experiment with the existing causal X14 GRU, original fold membership, 300 steps, Adam at 1e-3, and seeds 20261028 + fold index. Preserve the original 0.5 teacher-delta loss and 0.5 position-residual loss. Replace the zero-mean target with a teacher-centered scene-mean target:

`0.5 * mean_scene,axis(((mean_ready(a_student - a_C5) - mean_ready(a_teacher - a_C5)) / (0.1 * teacher_RMS_train_fold))^2)`.

The teacher mean is computed on training-fold scenes only. Teacher stays offline supervision; inference uses only causal X14 and the existing C5 action. All scales are training-fold-only. No VAL/TEST, Plant, or inertia reconstruction; no post-OOF tuning.

## Falsifiable outcome

The test passes its narrow hypothesis only if held-out OOF scene-mean student action moves closer to held-out teacher mean than the zero-DC arm, and the frozen SO(3) proxy improves relative to the zero-DC arm. Position residual and low-frequency action metrics will be reported regardless of direction. Even a pass does not establish better closed-loop Q; only a separately authorized paired closed-loop evaluation can do that.
