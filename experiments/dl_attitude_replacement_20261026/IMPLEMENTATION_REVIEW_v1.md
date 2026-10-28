# DL attitude TCN implementation review v1

Date: 2026-10-26 (Asia/Shanghai). Reviewer: primary agent. Decision: **approve the single frozen training run after source-lock validation**. No Plant or holdout run is authorized by this review note; closed-loop execution remains behind post-training Python/MATLAB parity.

## Findings resolved before training

1. **T2 source selection was wrong in dataset v1.** The first exporter used `original_a1_source` for all 816 rows, although 272 T2 rows require corrected raw/run-start files. This would have trained on superseded references. Dataset v1 is marked invalid and preserved; no training or Plant run used it. The exporter now joins the repaired dataset manifest to `B_REF_REPAIRED_SOURCE_MANIFEST_v1.json`, checks source action/path/hash/size, and uses corrected T2 raw for all 272 affected scenes.
2. **Corrected T2 VAL start files use a second MATLAB 7.3 wrapper layout.** The first full corrected-source attempt stopped before publishing NPZ/manifest because 16 VAL files store `cfg` at the file root instead of `runStart/cfg`. Reader support for both formats was added. The failed empty output directory and logs are preserved; no training started.

## Current data and code evidence

- Dataset v3: `dataset_v3_corrected/DATASET_MANIFEST_v1.json` reports PASS; 768 TRAIN, 48 VAL, 544 original certified raw, 272 corrected T2 raw, 1,999 events per scene, no TEST access. Every raw and run-start SHA was checked during extraction. Fixed nominal `J0` is identical across the 816 scenes. The compressed dataset SHA matches its manifest.
- Inputs are rebuilt from raw log fields in a 13-channel vector: wrapped attitude error, body rates, nominal BS body angular acceleration reconstructed from logged nominal torque and fixed `J0`, and four morph commands. The extractor does not read `rho_true`, `rhoDot_true`, Plant inertia, Plant torque, historical C*, or old X18/X29 feature caches.
- Targets are the next 10 ms body-rate difference minus current nominal BS angular acceleration. This is an offline label; future state is not an input. Train/VAL residual RMS and morph-command coverage were checked; 720/768 TRAIN and 45/48 VAL scenes contain nonzero morph commands, and split-level residual scales are comparable.
- Python compile and network shape smoke passed (`(2,13,15) → (2,3)`, finite). MATLAB `checkcode` reports zero diagnostics for the forward, step and parity helpers. Numerical parity still must be run with the trained weights before any Plant call.
- Frozen release: `TRAINING_RELEASE_v1.json`, SHA-256 `4d854f81d98e6dc9f72e560cd1bd028a6d72f20d6e01601183d9e86e046263ce`. An independent PowerShell check found no source/data hash mismatch.

## Residual limitations

- Morphology input is the command signal; the current simulator assumes ideal command following. This is not measured arm-position feedback.
- The 10 ms angular-acceleration label is a finite difference without sensor noise. Report it as simulator supervision and assess sensitivity to filtering/measurement noise before making hardware claims.
- No closed-loop DL result exists yet. The initial dataset v1 cannot be used for training, and no score from it may be cited.
