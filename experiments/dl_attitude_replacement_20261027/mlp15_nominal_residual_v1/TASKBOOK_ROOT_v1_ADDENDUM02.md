# Root binding addendum 02: exact one-run training contract

This addendum freezes the training recipe before the authorized training run. It is binding with TASKBOOK_ROOT_v1.md and ADDENDUM01.

## Model and optimization

Use the existing MLP15 definition bound by the parent source lock: 15-event causal window, 13 inputs per event, flatten in event-major order, Linear(195,64) -> SiLU -> Linear(64,32) -> SiLU -> Linear(32,3). Use seed 2026102001; batch size 512; 60,000 optimizer updates; Adam with learning rate 0.001 and weight decay 1e-5; SmoothL1(beta=1.0); final-step-only checkpoint. Use cuda:0 and deterministic PyTorch/CUDA settings from the parent trainer. If cuda:0 is unavailable or deterministic execution fails, stop and report rather than silently changing device or recipe. No early stopping, second seed, parameter search, or checkpoint selection.

## Fit-only statistics and data sampling

Fit input mean/std and per-axis target RMS from the 24 TRAIN_C5_24 scenes only. Use population mean/std over scene and event axes, floor each input std at 1e-6, and target RMS = sqrt(mean(y_train**2)) per axis. Use the exact 47,976 TRAIN event rows. Sample each optimizer batch by independent uniform scene and event indices from these 24 scenes with the fixed seed. C5_VAL48 must never enter any fitting, normalizer, batch sampling, or checkpoint decision.

The training manifest must bind all 24 scene IDs and source raw/status/run_start hashes, dataset NPZ SHA, source builder SHA, model/trainer SHA, hyperparameters, normalizer arrays SHA, final checkpoint SHA, device, PyTorch/CUDA versions, and completed step count.

## One-shot validation

After the final checkpoint is frozen, score it once over all 48 C5_VAL48 records using the same feature and fixed-J0 residual definitions. Build validation labels from the locked VAL raws without saving a combined TRAIN+VAL fit dataset. The score is diagnostic only; do not choose a checkpoint, alter source, normalization, hyperparameters, or target based on the result in this phase. Report per-axis scene-macro and pooled RMSE, wind-group summaries, dmax exceedance rates, and every source identity used.

## Stop and report

If any input source, data hash, alias mapping, device, finite-value, or deterministic-seed check fails, stop without silently changing the contract. No Plant, closed-loop launch, or TEST access is authorized.
