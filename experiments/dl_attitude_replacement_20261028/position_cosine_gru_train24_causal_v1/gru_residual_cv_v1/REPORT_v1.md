# Cosine-GRU/C5 TRAIN24 position residual GRU: four-fold OOF

## Result

The fixed `lambda=0.01` residual head reduced offline target RMSE in all 24 held-out scenes. OOF scene-macro RMSE was **0.200214 → 0.099114 m/s²**; pooled RMSE was **0.239729 → 0.124864 m/s²**. This is a development-only residual-head result, not independent full-system validation or evidence of closed-loop benefit.

| Holdout fold | Train / holdout scenes | Macro baseline → model (m/s²) | Pooled baseline → model (m/s²) | Wins |
|---|---:|---:|---:|---:|
| W00–05 | 18 / 6 | 0.105672 → 0.053368 | 0.115278 → 0.060767 | 6/6 |
| W06–10 | 16 / 8 | 0.248759 → 0.114204 | 0.268409 → 0.134702 | 8/8 |
| W11–13 | 20 / 4 | 0.246604 → 0.133194 | 0.277262 → 0.150826 | 4/4 |
| W14–15 | 18 / 6 | 0.199104 → 0.102022 | 0.263216 → 0.138971 | 6/6 |

The folds use the actual `fold_id` values in the source NPZ and manifest. They hold whole wind-code ranges out; scene counts are nonuniform because the physical TRAIN24 cohort is not a Cartesian wind grid.

## Fixed protocol

- Data: 24 physical `TRAIN_C5_24` scene IDs matched to parent cosine-GRU raw trajectories; 1,999 100 Hz events per scene, 1,968 ready events. The frozen parent has seen these exact IDs as DEV24 and was trained/evaluated across DEV24+VAL48.
- Features and target: logged 14-D X at event time `t`; target is the clipped 10 ms empirical interval value ending at `t+10 ms`. Current action is the parent C5 applied acceleration from that event. Residual labels are `clip(target_raw, ±3) - applied_action`.
- Model/objective: `GRU(14,32) -> Linear(32,3)` with zero-initialized output; hidden state processes all events from the first event and resets per scene. Only ready events contribute to `SmoothL1(clip(a_current + beta(t)*clip(delta, ±0.5), ±3), target_clip)`, with `beta=clip(t/1.8,0,1)`. The `lambda=0.01` term penalizes second differences only across three consecutive ready events in a scene.
- Training: Adam, learning rate `1e-3`, 300 optimizer updates per fold, seed `20261028 + fold_index`. Each fold's feature mean/std is fit only on its listed training scenes. No lambda sweep or VAL-based selection was run.
- Output checks: all OOF predictions are finite; the pre-ready output equals the logged baseline because delta is masked to zero. No holdout final action hit the ±3 m/s² clip; raw head saturation at ±0.5 was 0.60%, 5.50%, 7.20%, and 11.30% across the four holdouts.

## Scope and limitation

Training reads only this locked physical TRAIN24 NPZ and its metadata. It does not read VAL/TEST raw data, run Plant, or reconstruct inertia. However, because the parent cosine-GRU has seen these exact DEV24 scenes and VAL48, fold holdout applies only to this newly trained residual head over already-seen parent trajectories. It cannot establish independent generalization of the complete controller, closed-loop stability, or task-level benefit. Per-scene results, fold normalizers, spectra, and training diagnostics are in `RESULTS_v1.json`.

## Reproduction and SHA256

Entry point: `train_cosine_gru_residual_cv_v1.py`. The run used CUDA and took 13.17 seconds.

| Artifact | SHA256 |
|---|---|
| Source NPZ | `15d689f08fd6d8a53a64c59dbdf62b33f9b8e8a12ce083fb12834cd106df2eeb` |
| Source dataset manifest | `16856362913e5144add83035b9b767affa02c0719c66971635731d237bb0d91e` |
| Source dataset lock | `10be2c860c042491acfc0cfaad1067c65d848dd5889c177e6ccb8d65c9602fb7` |
| Dataset builder | `e8872933e9919f0f2737675fcdb07b555f3d862fa9e7f8b4b3bf960bce2f1970` |
| Training script | `6fa02af6317c74f56b25e54bb5b65f02fe89a9885871ca60227475be8a838fd4` |
| OOF predictions | `9dc29cc2d94b990bafc2bdf77cc8c704fb14e2c0582987e3057cd6464e177d0f` |
| Results JSON | `cbd90530f124aa5db42588c5a61984e3137ca163a13be3ff9b8f25e1cf16aaca` |
| Source lock | `197c77af5c293247f7a0ad0dc2eea341ff6bade4845c2f4d960810c13ce495fb` |

| Fold checkpoint | SHA256 |
|---|---|
| `holdout_W00_05_lambda_0.01.pt` | `da04ff8e9dcade4671f8776ffcb2d18d8120bf267f95ad29f0fee9e13d56dd1e` |
| `holdout_W06_10_lambda_0.01.pt` | `c18513678b9a907079c0f7e62e4efe2457dbfcf6da92525704b50c9980ff20cf` |
| `holdout_W11_13_lambda_0.01.pt` | `b9dd7c268e7234d946f0d72dd565616e6816fe887547a90dfc1cc4864c7b52e5` |
| `holdout_W14_15_lambda_0.01.pt` | `1158c935ccfac27b6286a4f53ac4b31bceb08f24196a010c64e345f6c119009e` |
