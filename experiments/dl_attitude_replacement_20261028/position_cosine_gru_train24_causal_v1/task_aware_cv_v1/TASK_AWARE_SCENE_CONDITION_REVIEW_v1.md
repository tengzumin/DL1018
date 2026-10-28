# Task-aware residual head: TRAIN24 OOF review

This is a frozen-state command replay over the physical TRAIN24 parent cosine-GRU trajectories. It is not a new closed-loop result. The parent model has already seen these DEV24 scenes and VAL48.

## OOF result

| Metric | C5 baseline | No-task GRU, λsmooth=0.01 | Task-aware GRU, λtask=0.1 |
|---|---:|---:|---:|
| Task SO(3) scene-macro RMSE | 57.216 mrad | 64.556 mrad | 64.407 mrad |
| Task SO(3) pooled RMSE | 60.908 mrad | 69.193 mrad | 69.052 mrad |
| Position target scene-macro RMSE | 0.200214 m/s² | 0.099114 m/s² | 0.098978 m/s² |
| Position target pooled RMSE | 0.239729 m/s² | 0.124864 m/s² | 0.125131 m/s² |

Task-aware improves task SO(3) over no-task in 18/24 scenes, by only 0.149 mrad macro (0.141 mrad pooled). It remains worse than C5 in 23/24 scenes and is 7.191 mrad worse macro than C5. Position macro improves by 0.000136 m/s² versus no-task, while pooled position RMSE worsens by 0.000267 m/s². The position/task trade is small and mixed.

By task ID, task SO(3) macro is 51.677/60.353/59.617 mrad for C5 versus 56.169/68.835/68.217 mrad for task-aware on T1/T2/T3. Task-aware beats no-task on task SO(3) in 8/8, 5/8, and 5/8 scenes respectively. Task IDs are posthoc groups, not model inputs.

Most task-angle error lies below 5 Hz. SO(3) error-vector band RMS (scene macro, mrad) for C5 / no-task / task-aware is: 0–1 Hz 12.751 / 15.125 / 15.076; 1–2 Hz 7.848 / 10.851 / 10.875; 2–5 Hz 6.416 / 9.844 / 9.831. Above 5 Hz each band is below 0.8 mrad, and task-aware differs negligibly from no-task. Thus the task loss barely changes the dominant low-frequency gap to C5.

Wind codes are sparse design labels: most have one scene, and none has more than three. Signs vary; for example W14 (3 scenes) gains 0.300 mrad task SO(3) over no-task, while W10 (1 scene) loses 0.235 mrad and 0.00362 m/s² in position RMSE. These counts do not support a wind-conditioned deployment rule.

## Causal-condition screen

X14 contains current preview error, position surface, current Euler angles, preview thrust per mass, and four arm commands. These are the existing controller's event-time features. No task ID or wind code is present in X14. A single predeclared screen used the current preview-error norm, with a median threshold fitted only from each fold's training X14. Task-aware improves next-boundary SO(3) over no-task in both high and low groups in all four folds, but by only 0.043–0.262 mrad. Position effect changes sign across folds: in the high group it ranges from −0.000943 to +0.002679 m/s². This does not identify a stable useful gate.

The exploratory whole-scene correlation between preview-thrust RMS and task-aware-minus-no-task SO(3) is −0.392 across 24 scenes. It uses a full-scene summary, so it is not a causal deployment signal; the sample is too small to set a threshold. Wind/task labels and full-scene future summaries must remain evaluation-only.

## Minimal next falsification

If another offline objective is warranted, keep the same model, folds, 300 steps, action mapping, and causal X14-only inference. Replace the absolute task penalty with one fixed C5-relative guard:

`L = L_position + 0.01 L_smooth + 0.1 mean(max(0, θ_task(candidate,t) − θ_task(C5,t))²)`

Compute both SO(3) terms with the same 1 ms command-filter replay on training-scene references; keep those future reference/trajectory values as training supervision only. At inference, use only current/history X14, process the warmup sequence, and retain the existing `β(t)`, ±0.5 delta clip, ±3 m/s² total clip, and 100 Hz zero-order hold. Do not gate on scene ID, task ID, wind code, or heldout labels.

Use the locked 6/8/4/6 whole-scene folds with train-fold-only normalization and compare against both C5 and the existing no-task OOF control. Reject the objective if task SO(3) macro or pooled RMSE exceeds C5, or if position macro and pooled RMSE fail to match or improve on the no-task control. A pass would justify considering a controlled pilot; it would not establish closed-loop benefit.

## Provenance

Dataset SHA256: `15d689f08fd6d8a53a64c59dbdf62b33f9b8e8a12ce083fb12834cd106df2eeb`.

Task-aware OOF SHA256: `a92c61662fa2fee8faf11d97b1f0234db13f6875c1cc6036098d71f3dccf5dcd`.

Detailed per-scene/fold/wind summaries, the causal screen, and the reconstructed spectra are in `TASK_AWARE_SCENE_CONDITION_DIAGNOSTIC_v1.json`. Its reconstruction matches the training SO(3) RMSE to `1.4e-17 rad`. No VAL/TEST raw, Plant, or inertia reconstruction was used.
