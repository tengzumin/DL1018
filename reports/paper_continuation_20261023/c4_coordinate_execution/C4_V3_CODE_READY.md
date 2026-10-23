# C4 v3 code ready (static review only)

Status: `CODE_READY_NO_MATLAB`; awaiting parent review before the one authorized `prepare_c4_coordinate_v3` batch. This work did not start MATLAB or Plant.

The only preparation logic change from reviewed v2 is the scene identity template: clone `c3Pack.sceneIdentity(1)` then retain the existing per-scene row assignment and assertions. Other prepare/runner changes are v3 function, schema/state, and artifact-path rebinding. Contract content is unchanged apart from schema/state. Lock v3 was built from lock v2; active sources, shared inputs, model identity, twelve scene identities, numeric limits, and prohibitions compare equal. Static audit passed the restricted lock diff and SHA verification for all source references.

The existing MAT decoder read C3 snapshot `C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat` (SHA-256 `3ddf24ad98e0900a2bb105b34369e73be03d015c66ec599347dfb43d0e730ae6`); decoder SHA-256 is `372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af`. It reports 72 scene rows and W0 shape 33x3. The decoded field inventory is recorded in [C4_C3_SNAPSHOT_FIELD_AUDIT_v1.json](C4_C3_SNAPSHOT_FIELD_AUDIT_v1.json), SHA-256 `9d97e74b7df79afefce5c826880d1086ba994827b44ab464b7305b97d96a8b00`.

| Snapshot section | Fields |
|---|---|
| `opts` | `attitude_rbf_frequency_hz`, `formal_rbf_baseline`, `position_delayed_prediction_enabled`, `position_rbf_frequency_hz`, `rbf_attitude_enabled`, `rbf_attitude_gamma_scale`, `rbf_attitude_output_enabled`, `rbf_attitude_update_enabled`, `rbf_full_phase_start`, `rbf_phase_start`, `rbf_position_gamma_scale`, `rbf_position_output_enabled`, `rbf_position_update_enabled`, `stage1_position_runtime`, `v1_adaptive` |
| `modelIdentity` | `W0_sha256`, `input_dim`, `model_id`, `normalizer_arrays_sha256`, `selected_step`, `window` |
| `sourceIdentity` | `prepare_entry`, `prepare_entry_sha256`, `runner`, `runner_sha256`, `source_paths`, `source_sha256`, `which_checks` |
| `sceneIdentity` | `B_raw_path`, `B_raw_sha256`, `alias_normalized_in_memory`, `canonical_scene_id`, `payload_review_sha256`, `raw_scene_id`, `scene_id` |

C4 dereferences `modelIdentity.W0_sha256` and `.normalizer_arrays_sha256`; `sceneIdentity.scene_id`, `.B_raw_path`, and `.B_raw_sha256`; it compares `cfg` as a whole and `opts` as a whole after removing only `position_coordinate_m`. `sourceIdentity` is loaded but not dereferenced; C4 builds its own identity. Structure cloning preserves every C3 scene field.

| v3 file | SHA-256 |
|---|---|
| `prepare_c4_coordinate_v3.m` | `3044ab45a27e9c941011e840047b5a515b4fef2a11b855346d6737836d02019e` |
| `run_c4_coordinate_v3.m` | `382ace97950672c1a543b76004d32f3d79e0d378a57b16765bf4d2dc9d5e2e3f` |
| `C4_COORDINATE_LOCK_BUILD_v3.py` | `4d04152f16c364974065dfb259f0e0106ce3e2fe3175eb85ba514493e4cce559` |
| `C4_RUN_CONTRACT_v3.json` | `bf9f97ca00be222370042436a1c01eb42033b5b6b5ce4fee038bd0b9676a55bd` |
| `C4_INPUT_LOCK_v3.json` | `59d1c81f73f8362c15183492d921f5f1d5d1afe12f41949b618497a9e75892d2` |

The v3 lock references 32 active sources (31 `.m`, one `.mat`) and 12 scenes. The already passing synthetic cross-language result remains bound to its reviewed v2 checker and was not rerun.
