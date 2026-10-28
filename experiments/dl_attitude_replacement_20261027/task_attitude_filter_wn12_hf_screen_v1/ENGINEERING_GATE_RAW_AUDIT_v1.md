# Engineering-gate raw audit — filter wn12

Scene: `DL1018_DEV_T1_C10_W09`. Result: **PASS_METRICS_AND_IDENTITY_WITH_FIRST_OUTPUT_PATH_MISMATCH**.

Candidate raw SHA-256: `01f826a970865eaa2596b01866321d2341749133872d30b16d4f408c22410190` (91,594,483 bytes).
Status: STABLE; 20,000 transitions / 20,001 states; time step max error 2.33e-15 s.
Scorer, filter and output arrays finite: True; 94 log diagnostic fields contain non-finite values (full field paths are listed in the JSON).

## Safety counts

- motor_saturation_samples: 0
- generalized_clip_samples: 0
- tilt_limited_samples: 0
- attitude_head_projection_samples: 0
- attitude_head_output_saturated_samples: 0

## Frozen paired scorer results

Constants: gravity 9.8 m/s²; max tilt 0.523598775598 rad. Scorer SHA-256: `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`.

| Metric | Candidate | B | C5 | Candidate − B | Candidate − C5 |
|---|---:|---:|---:|---:|---:|
| Q_m | 0.0116592077401 | 0.0109845617733 | 0.0104658821287 | 0.00067464596688 | 0.0011933256114 |
| task_SO3_rad | 0.0425016928081 | 0.0422008011291 | 0.0432726490353 | 0.000300891679018 | -0.000770956227254 |
| inner_SO3_rad | 0.0201403895027 | 0.0232369539916 | 0.0232740469303 | -0.00309656448892 | -0.00313365742756 |

## Binding and caveats

- Run start and raw identity release SHA agree: True; current release SHA `e369ba5adfead47bff0333cb9ac5a4e832d06d963ae09afcff48958f17c6d335` differs from the recorded run-time SHA `06c8aba11fbaec0fc35d7e23397a362b38d0583decd99182793b912d4b43118e` because the current release is DRAFT/0 after the call.
- Source lock files: 59/59 SHA matches; external dependency files: 12/12 SHA matches.
- Resource ledger: MATLAB process/run count 5/5; pre-marker failures 2; prepare-only 2; closed-loop 1; Plant completed 1; authorized now 0 (RELEASE DRAFT).
- Candidate / B / C5 scene ID and reference arrays match exactly: True.
- **First output path mismatch:** planned candidate path is `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_filter_wn12_hf_screen_v1\runs\DL1018_DEV_T1_C10_W09\attempt_01\raw_run.mat`; produced raw remains at `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_filter_wn12_hf_screen_v1\runs\DL1018_DEV_T1_C10_W09\raw_run.mat`. No file was moved or copied. `run_status.json` SHA and raw identity bind the produced file; see `PATH_RECONCILIATION_ADDENDUM_v1.md`.
- Model identities are distinct by role: run candidate `GRU32_STREAM72_COSINE_TRACKING_HEAD_FILTER_WN12_S20261027`, parent tracking-head arm `GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001`, frozen weights id `GRU32_STREAM72_COSINE_S2026102001`; the frozen weights id is checked against the locked parent model path and SHA.
- This audit did not run MATLAB, Plant, B/C5 simulations, remaining scenes, or access TEST data. MATLAB replay closure remains for root's separate review.

## Checks

- PASS — raw_scene_identity
- PASS — raw_sha_matches_run_status
- PASS — status_raw_path_matches_produced_raw
- PASS — run_status_completed_stable
- PASS — run_status_counts
- PASS — complete_transition_flag
- PASS — status_safety_stop_empty
- PASS — timebase_1ms
- PASS — state_shape_20001x12
- PASS — state_finite
- PASS — scorer_filter_and_output_arrays_finite
- PASS — scorer_metrics_finite
- PASS — filter_target_output_shapes
- PASS — filter_target_output_finite
- PASS — status_and_identity_run_release_sha_agree
- PASS — run_start_manifest_sha_matches_current
- PASS — run_start_source_lock_sha_matches_current
- PASS — run_start_source_diff_sha_matches_current
- PASS — run_start_locked_cfg_sha_matches_current
- PASS — run_start_model_sha_matches_current
- PASS — run_start_candidate_matches_release_candidate
- PASS — release_base_candidate_matches_locked_parent_arm
- PASS — locked_parent_model_sha_matches_candidate_model
- PASS — run_start_frozen_model_candidate_matches_locked_parent_model_id
- PASS — B_C5_sha_matches_manifest
- PASS — payload_sha_matches_manifest
- PASS — scene_references_match_across_candidate_B_C5
- PASS — source_files_match_lock
- PASS — external_dependencies_match_lock
- PASS — locked_cfg_filter_is_12_12_12
- PASS — J0_binding_sane
- PASS — current_release_is_postrun_DRAFT
- PASS — release_resource_ledger_matches_record
- PASS — path_addendum_matches_release_lock
- PASS — run_identity_scene_id
- PASS — run_identity_candidate
- PASS — run_identity_authorization_phase
- PASS — run_identity_frozen_model_candidate
- PASS — run_identity_release_sha256
- PASS — run_identity_manifest_sha256
- PASS — run_identity_source_lock_sha256
- PASS — run_identity_source_diff_sha256
- PASS — run_identity_locked_cfg_sha256
- PASS — run_identity_b_raw_sha256
- PASS — run_identity_c5_raw_sha256
- PASS — run_identity_payload_sha256
- PASS — run_identity_gru_model_sha256
- PASS — run_identity_c5_input_lock_sha256
- PASS — run_identity_c5_snapshot_sha256
- PASS — run_identity_position_model_sha256
- PASS — run_identity_common_position_options_sha256
- PASS — run_identity_TEST_read
- PASS — run_identity_Plant_truth_deployment_input
- PASS — run_identity_base_model_weights_fixed
- PASS — run_identity_tracking_delta_weights_online
- PASS — run_identity_hidden_state_reset_per_scene
