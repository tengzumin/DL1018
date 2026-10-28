# Deployment adapter and shared tau_score contract

## Model callback contract

The deployment checkpoint is a **position compensation acceleration residual head**. It is not the GRU attitude/torque model already used by the tau01 runner, and its 14-feature input cannot be passed to `gru_stream_attitude_step_v1` unchanged.

At each 100-Hz position event, the runner should pass:

- `x14`: current causal 14-vector from `stage1_position_feature_input` / `stage1_position_feature_14`, shape `(14,)`, in the source order.
- `hidden`: scene-local 32-vector, initialized to zero and carried event to event. Advance it on warm-up events too.
- `base_action_mps2`: current C5 position-compensation event action, shape `(3,)`.
- `event_time_s`: time of the current feature event relative to run start.
- `ready`: C5 position-event readiness flag.

The checkpoint normalizes `x14` with its saved full-TRAIN24 `normalizer_mean/std`; the one-step GRU computes a raw delta, clips it componentwise to `[-0.5, 0.5] m/s²`, and the adapter emits

`clip(base_action_mps2 + clip(event_time_s / 1.8, 0, 1) * delta, -3, 3)`.

When `ready` is false, set `delta=0` while still updating the GRU hidden state. Reset hidden state at each new simulation scene. The teacher is not an inference input.

`DEPLOYMENT_MODEL_v1.pt` is the authoritative PyTorch checkpoint. `DEPLOYMENT_MODEL_WEIGHTS_v1.npz` exports the same GRU/head tensors and normalizer arrays. PyTorch GRU gate order is reset, update, new; the linear head directly predicts m/s² and has no extra target-RMS multiplier.

## Shared scoring route

The frozen `tau_score` scorer consumes a completed standard raw-run HDF5/MAT artifact, not a checkpoint or model callback. The shared entry point is `score_raw(path: Path, gravity: float, max_tilt: float)` in `experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py`. The official tau01 score record binds this scorer and its constants in `experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json`.

For later scoring, a candidate runner must first call the model callback at position events, write the resulting closed-loop run to the standard raw format, and provide its scene/status/release hash bindings. The shared scorer then computes `Q_m`, `task_SO3_rad`, `inner_SO3_rad`, and safety/phase fields from that raw run. No raw run was produced here, and no tau_score was run: this task only trained and exported the model without calling Plant or reading VAL/TEST.
