# Post-training artifact audit and CPU postprocessor proposal

This is a read-only audit after the only authorized complete training. The postprocessor below has been written but has **not** been run. No VAL/TEST arrays or Plant were accessed.

## Training outcome and failure

- Run: `MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01`
- Authorized fit completed all 60,000 updates with seed `2026102001` on `cuda:0`; the final training log row is step 60,000, normalized SmoothL1 `0.004275967366993427`, elapsed `132.92263010001625` s, and `validation_evaluated=false`.
- The trainer exited with nonzero status (Python exit code 1) during post-training parity-vector export. It had already written the final checkpoint and MATLAB weights. The exact error was `RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cpu and cuda:0!`. Serialization called `model.cpu()` and the subsequent parity sample window remained on `cuda:0`.
- A separate earlier engineering attempt made one `optimizer.step()` then exited on the missing `log_every_steps` config key; it has no checkpoint and is retained separately. ADDENDUM03 authorized one full retry, which completed 60,000 steps. Neither failure used VAL, TEST, or Plant.

## Read-only identity checks

| Artifact | SHA256 | Read-only result |
|---|---|---|
| `TRAINING_CONFIG_v1r1.json` | `e120600428ced22c416a8744861a1f6b6e1f6ac64430f61223e614af67021664` | Config identity matches checkpoint and freeze manifest |
| `TRAINING_FREEZE_MANIFEST_v1r1.json` | `6d5bee445381778e7cc4f181345420826f69d8c724a56995f2115274723ff454` | Freeze identity matches checkpoint |
| TRAIN NPZ | `242c86426f48cfe6d37afc25994d67a6c8ff3f0ea25246d50765a831e4458566` | Dataset SHA matches config and freeze manifest |
| `model_final.pt` | `9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74` | `step=60000`, `seed=2026102001`, `train_split=TRAIN_C5_24` |
| `mlp15_attitude_weights_v1.mat` | `dfbad11dbc7ed19b42d3b536bb4b019cbf29209d69c904b0b5000a168af58819` | All six layer arrays and three normalizers exactly match checkpoint values after flattening; maximum absolute difference is 0 |
| `training_log.jsonl` | `fc51a741be1628504f4dd868834f1b9f0c591a62ab656885a2dec7215ddc06b6` | Ends at step 60,000; every logged row says validation was not evaluated |
| `training_stderr_v1r1.log` | `52fe0050c616c27a22b913cf5c215763a7daea280844a4c381ee75035d1d8dfc` | Contains the observed CPU/CUDA parity-export RuntimeError |
| `postprocess_train_artifacts_v1.py` | `a23a368259d9450139867cfb49604862499f8e9af9e1ecb9fb7a706768f09568` | CPU-only postprocessor; AST parse passed; script was not executed |

The 60-line training log has contiguous steps 1,000 through 60,000, finite loss and elapsed fields, strictly increasing elapsed time, and `validation_evaluated=false` on every row. The final raw log-line SHA256 is `de4b167e0ea115ee85c53624345d3a6d88e468ff4bd6fe33f65a53965305d615`; its summary is step `60000`, normalized SmoothL1 `0.004275967366993427`, elapsed `132.92263010001625` s, validation `false`.

For bias fields, MATLAB stores row vectors while the checkpoint stores one-dimensional tensors; flattening both gives exact value equality. Weight matrices have identical shape and values.

## Proposed postprocessor contract

The script requires the explicitly reviewed checkpoint SHA. It verifies frozen config/freeze/addendum hashes, the dataset SHA, checkpoint step/seed/split, state-dict layer shapes, and TRAIN-only normalizers. It validates all 60 training-log rows at the frozen 1,000-step cadence and checks that every row is finite and validation-free. It hashes `training_stderr_v1r1.log` and requires the recorded CPU/CUDA error marker before reporting the trainer's nonzero exit status (`1`). It reads only the TRAIN NPZ arrays `x_train` and `y_train`; scene IDs come from the frozen config. It loads the checkpoint with `map_location="cpu"` and loads the existing MATLAB weights solely to compare every layer weight/bias and all three normalizers element-for-element. It then runs inference with CPU tensors and `torch.nn.functional.linear`; it has no optimizer, CUDA call, or checkpoint/weight write path. The receipt records log line count, last step, final-row SHA/content summary, stderr SHA/error marker, and checkpoint/MAT comparisons.

It will create only these currently absent files in the `_REPAIR01` run directory:

1. `training_metrics_train.json`: clipped model residual RMSE per axis and wind group over the 47,976 TRAIN events; this is an in-sample diagnostic and does not refit.
2. `parity_vector_v1.mat`: normalized TRAIN scene 0/event 100 input window plus the checkpoint's unclipped physical MLP output, for MATLAB no-Plant parity.
3. `training_postprocess_receipt_v1.json`: input/output hashes; records the post-training trainer error, completed 60,000 updates, CPU-only reconstruction, and `VAL/TEST/Plant=false`.

No output has been created by this script. The next required action is root review of the script and this audit note. Only after that review should the postprocessor be run; VAL48 remains untouched until the checkpoint and receipt are fixed.
