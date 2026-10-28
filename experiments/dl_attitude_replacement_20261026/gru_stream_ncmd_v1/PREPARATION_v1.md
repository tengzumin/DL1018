# GRU32 continuous-state NCMD trainer preparation

Candidate: `GRU32_STREAM72_NCMD_S2026102001`.

Only the supervision source changes from the cosine C5 teacher candidate. The model remains `GRU(13,32)+Linear(32,3)` and the 13-D X comes only from `matched_teacher_data_v1.npz`. Y comes only from `nominal_command_target_v1.npz` members `c5_train_y_clipped_float32` and `c5_val_y_clipped_float32`; the trainer does not read the old teacher Y or either unclipped label member. The exact source/target hashes, array hashes, order, normalizer, initialization, schedule, and release0 boundary are in `GRU_STREAM_NCMD_SOURCE_LOCK_v1.json`.

Original scene cohorts are DEV24 (`DL1018_DEV_*`) and VAL48 (`DL1018_VAL_*`). Internal archive split names are aliases; all 72 are development data and VAL48 is not independent validation. No TEST data, realized torque, true/estimated inertia, wind, or mass is a training input. The target is a clipped nominal requested-command port residual, not RBF-output supervision.

The fixed cosine training contract, scene order/shuffle, batch 4, TBPTT 128, final 79-event chunk, 60,000 steps, SmoothL1 beta 1, Adam/weight decay, seed, and byte-identical GRU15 normalizer remain inherited from the cosine candidate. Expected valid samples: 29,985,000. Release0 is pending root review: 0 training jobs / 0 steps / 0 Plant calls. `self_check_gru_stream_ncmd_v1.py` performs identity and toy stream checks only; it does not call `optimizer.step` and must leave the run directory absent.

The output model interface remains the existing nine-field MAT interface at `runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat`, with `stream_parity_vector_v1.mat` beside it. No runtime changes are included here.