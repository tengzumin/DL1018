# Root taskbook addendum 04: one-shot C5_VAL48 offline diagnostic

This binds to TASKBOOK_ROOT_v1 and ADDENDA01–03, ROOT_TRAINING_RESULT_REVIEW_v1.md, and the frozen MLP15 checkpoint below. It authorizes only offline validation and no-Plant MATLAB parity. It authorizes no training, closed-loop run, TEST access, or Plant call.

## Frozen candidate

- Checkpoint: uns/MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01/model_final.pt, SHA-256 9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74.
- MATLAB weights: same run directory, mlp15_attitude_weights_v1.mat, SHA-256 dfbad11dbc7ed19b42d3b536bb4b019cbf29209d69c904b0b5000a168af58819.
- This candidate completed the fixed 60,000-step TRAIN_C5_24 fit. Do not change weights, normalizers, model, threshold, or runtime clip.

## Authorized work

1. Freeze the C5_VAL48 scene IDs and all raw/status/run_start file paths and SHA-256 values from the existing approved source lock before reading their numeric arrays. Reuse existing C5 raw runs; do not rerun B or C5. Rebuild physical-residual labels from those logged records with the same past-only timing, units, sign, and feature definition as the approved TRAIN builder. VAL is diagnostics only; it must never enter fitting, normalization, checkpoint selection, or parameter choices.
2. Score the frozen checkpoint once over all 48 C5_VAL48 scenes. Report per-scene errors, axis-pooled and scene-macro RMSE by axis and wind group, target/output distributions, clipping counts, and all source identities. Label this as reused validation data, not independent TEST evidence. If identity or causality checks fail, stop before scoring and report the exact gap.
3. Run one no-Plant MATLAB parity check from parity_vector_v1.mat and the frozen MATLAB weights. Check the actual MLP forward path used by the candidate integration, flatten order, normalization, SiLU layers, and residual output; use absolute tolerance 1e-6 rad/s^2. Do not initialize or call the Plant, runner, dynamics, or actuator. Run MATLAB Code Analyzer on the isolated parity function; report command, result, and source hashes.
4. Write all new code, validation arrays/manifests, tables, and logs beneath C5_VAL48_OFFLINE_DIAGNOSTIC_v1/; refuse overwrite. Bind code/data/model/output hashes and state TEST=false, Plant=false, 	raining=false in a receipt. Do not modify prior experiment outputs.

After these deliverables, stop and return control to root for independent review. A passing offline score does not establish closed-loop benefit. Root will decide whether to issue a separate frozen 12-scene closed-loop screen; no screen starts automatically.
