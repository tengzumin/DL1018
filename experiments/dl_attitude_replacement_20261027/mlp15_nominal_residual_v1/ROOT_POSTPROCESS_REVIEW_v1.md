# Root review: CPU-only MLP15 training artifact postprocess

Date: 2026-10-27 (Asia/Shanghai)

## Independent checks

- Postprocessor SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\postprocess_train_artifacts_v1.py); audit note SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\POSTPROCESS_AUDIT_v1.md).
- Frozen config/freeze SHA-256: 120600428ced22c416a8744861a1f6b6e1f6ac64430f61223e614af67021664 / 6d5bee445381778e7cc4f181345420826f69d8c724a56995f2115274723ff454.
- TRAIN NPZ/checkpoint/MAT SHA-256: 242c86426f48cfe6d37afc25994d67a6c8ff3f0ea25246d50765a831e4458566 / $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\runs\MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01\model_final.pt) / $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\runs\MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01\mlp15_attitude_weights_v1.mat).
- Training log SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\runs\MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01\training_log.jsonl); stderr SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\training_stderr_v1r1.log).
- Independent check confirms 60 log rows, steps 1,000 through 60,000 in order, all alidation_evaluated=false, finite loss/time, and final step 60,000.
- Checkpoint has step 60,000, seed 2026102001, and frozen config/freeze/data identities. All six layer arrays and three normalizers in the MATLAB file match checkpoint values exactly after flattening (maximum absolute difference 0).
- Postprocessor AST parses. Static review found no optimizer or CUDA calls. It loads only TRAIN x_train/y_train; it derives scene IDs from the frozen config. Its only intended outputs are 	raining_metrics_train.json, parity_vector_v1.mat, and 	raining_postprocess_receipt_v1.json. All three are absent before execution.

## Decision

Approve exactly one run of this SHA-bound CPU-only postprocessor using the checkpoint SHA above. It may recompute in-sample TRAIN diagnostics and generate one TRAIN parity fixture and receipt. It must not fit or change model weights, read VAL/TEST, or call Plant. Preserve the original nonzero training export error in the receipt. No closed-loop run is authorized by this review; root must audit the postprocess outputs before the single offline C5_VAL48 diagnostic.
