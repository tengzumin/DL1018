# Amendment 04 — bind the pilot runner to the corrected teacher model

Date: 2026-10-26 (Asia/Shanghai).

## Finding

The inherited pilot wrapper and no-Plant preparer still pointed at `training_v1_retry01`, `TRAINING_RELEASE_v2.json`, the residual-label dataset, and v1 model filenames. Those checks could not authorize or load the corrected RBF teacher-action model. The old source remains unchanged and is not released for a Plant call.

## Corrected pilot path

An isolated `pilot_runner_v4_teacher_distill` now binds the 13-feature contract and pre-beta `rbf_output_raw` target to `TRAINING_RELEASE_v3.json`, `training_v2_teacher_distill`, `normalizer_v2.json`, and `tcn_attitude_weights_v2.mat`. Its no-Plant preparer requires the independent VAL48 raw audit and the MATLAB/Python forward parity report before it can build candidate options. Its release and run identities also bind Amendments 02–04, the dataset manifest/audit, parity report, training config, model, C5 inputs, and the six GHP7 payloads.

The six-scene pilot remains the only authorized next Plant scope: one TCN candidate call per frozen GHP7 payload. Reuse the existing B, C5_RBF, and C5_10 results; do not rerun those methods. DEV72 and TEST48 remain gated by the existing taskbook criteria. This amendment grants no Plant call by itself; a separate, hash-complete `PILOT_RELEASE_v2.json` is required after the trained model passes all audits.
