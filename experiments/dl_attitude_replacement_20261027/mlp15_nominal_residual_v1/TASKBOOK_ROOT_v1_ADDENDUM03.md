# Root binding addendum 03: one repaired training attempt

This addendum binds to TASKBOOK_ROOT_v1 and ADDENDA01/02. It authorizes one complete retry only after root audits the new trainer, config, and pretraining freeze manifest.

## Failure record

The first launch used `train_mlp15_physical_residual_v1.py`, config SHA256 `cffeef6bb03e488defe9ef897072b99189b52ded59d131d53df58a03d5becd8e`, and the original output directory `runs/MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001`. It exited after the first `optimizer.step()` while evaluating its logging condition because the frozen config omitted `log_every_steps`. The original traceback ended with `KeyError: 'log_every_steps'` at trainer line 223. Exactly one optimizer update occurred; there was no completed training, checkpoint, normalization export, validation access, TEST access, or Plant call. The original directory and console/stderr logs are retained unchanged; its only run artifact is an empty `training_log.jsonl`.

## Authorized repair

The repaired trainer is a new immutable file, `train_mlp15_physical_residual_v1r1.py`. Its only code change reads `log_every_steps` with a fixed 1000-step default and rejects non-positive intervals. The new frozen config explicitly sets `log_every_steps=1000`. The model, data, input features, seed, CUDA device, deterministic settings, batch size, 60,000-step schedule, optimizer, loss, normalization rules, and fitting members remain identical to ADDENDUM02. The retry uses a new output directory ending in `_REPAIR01`; the failed directory must be preserved.

After root review of the new preflight freeze artifacts, exactly one complete 60,000-update training retry is authorized under the new config. If preflight fails, stop and report. No further retry, validation/TEST use before final checkpoint freeze, Plant call, or closed-loop launch is authorized here.
