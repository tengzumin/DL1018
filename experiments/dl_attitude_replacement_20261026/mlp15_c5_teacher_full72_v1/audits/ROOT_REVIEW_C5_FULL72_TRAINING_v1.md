# Root review: C5-RBF MLP15 full72 training release

Date: 2026-10-26 (Asia/Shanghai)
Decision: **APPROVED_FOR_TRAINING**, exactly one training job. Plant, closed-loop runs, and TEST access remain unreleased.

## Findings

- The same-task offline architecture screen ranked MLP15 first, followed by TCN15, GRU15, DSSM15. It used B-RBF teacher actions, so it only preselects an architecture; it does not establish performance on C5 states or in closed loop.
- The prepared C5 training data contains all 72 available C5-RBF teacher scenes, 1,999 events per scene, 143,928 unique events. Independent root recomputation matched the four selected C5 feature/label array hashes, combined full72 hashes, manifest scene order, and dataset SHA. Training reads only the six C5 NPZ members; B24 members are not loaded.
- The only model inputs are the frozen 13 features: wrapped attitude error (3), body rates (3), nominal BS torque (3), and normalized morphology command (4). The trainer checks this exact feature contract and rejects Jhat, Jdot_hat, inertia/mass-property, Plant-truth, RBF-hidden-state, observer, and physical-feedforward inputs. The source manifest and source lock both require inertia_config_read=false and plant_truth_read=false.
- The target is the logged C5 attitude rbf_output_raw at the same causal event, post-DMAX and pre-beta, in rad/s². Fixed J0 appears only in prior trace auditing of torque mapping; it is not an input feature and no changing-inertia estimate is reconstructed.
- The 48 prior C5 VAL scenes were already used for C5-24 checkpoint selection/action diagnostics. This run reclassifies them as development training data. Therefore this 72-scene fit has no independent action-validation split; its fixed final-step checkpoint must be judged by closed-loop development screening later and, if eligible, a separately frozen independent test.
- The trainer is isolated, hash-checks its sources and dataset, refuses reruns into an existing output directory, publishes only step 60,000, and passed CPU synthetic self-check. Root independently verified all locked source hashes before approval.

## Frozen training release

- Architecture: MLP15 (13 inputs × 15 causal events → 64 → 32 → 3; SiLU).
- Data: all 72 C5-RBF development scenes only; 143,928 unique event windows.
- Seed 2026102001; Adam lr=1e-3, weight_decay=1e-5; batch 512; SmoothL1 beta 1; exactly 60,000 optimizer steps; publish final_step_60000 only.
- Input/label source, feature order, scene IDs, selected arrays, dataset, manifest, trainer, screen code, and audit inputs are SHA-locked in MLP15_C5_TEACHER_FULL72_SOURCE_LOCK_v1.json.
- No Plant, C5/B baseline rerun, closed-loop candidate flight, or TEST read is part of this release.

Root source-lock SHA-256 after approval: 2c733dd093ab2ea1ff74f6cf2828a130345f022b3439456bf22abff8961edc8a.

## Training result and export review

- Run receipt status `PASS`, exactly one job, 60,000/60,000 optimizer steps on `cuda:0`, elapsed 150.887 s. The 72-scene training loss mean declined from 0.10665 at step 1,000 to 0.02140 at step 60,000; this is training loss, not held-out validation.
- All seven output hashes in the receipt match their files. The checkpoint is step 60,000, contains 14,723 finite parameters, and has the expected `195→64→32→3` shapes. MATLAB export normalizers have shapes `1×13`, `1×13`, `1×3`.
- Independent MATLAB R2025b parity passed for raw and clipped output: maximum absolute error `1.7869e-7 rad/s²` against tolerance `1e-5`. The parity audit used the correctly named `expected_model_output_raw_rad_s2` and `expected_runtime_output_clipped_rad_s2` fields; the older parity helper expected a different field and was not reused.
- The run receipt records `plant_called=false`, `TEST48_read=false`, and `B24_arrays_read=false`. The output remains a development candidate; closed-loop screening is still required.
