# Root independent review: TRAIN_C5_24 physical residual data

Date: 2026-10-27
Decision: **PASS_DATA_PREPARATION; AUTHORIZE ONE TRAIN-ONLY MODEL RUN; NO PLANT**

## Scope and identities

The review covered only the new isolated study directory, the locked C5 TRAIN source records, the TRAIN-only residual NPZ, and the generated manifest. No TEST content was read. No MATLAB, Plant, or closed-loop run was started.

- Builder: prepare_train_data_v1.py, SHA-256 34d1af3f2fc5ba54629790e8ea363a58143957639ba28fa894b5a62dc3f2e679
- Dataset: TRAIN_C5_24_PHYSICAL_RESIDUAL_v1.npz, SHA-256 242c86426f48cfe6d37afc25994d67a6c8ff3f0ea25246d50765a831e4458566
- Manifest: TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json, SHA-256 18761c159e003388e7a728132913eaf0b290c0d109d797618986ef87d8fd3bbb
- Binding taskbook: TASKBOOK_ROOT_v1.md, SHA-256 90dcfedadeedf7cbbd328c61e5f57dab72e7f3a97f33993e51c57eccf08d85f
- Binding addendum: TASKBOOK_ROOT_v1_ADDENDUM01.md, SHA-256 2821b83e065a7d1bb82467bf964fb94bf5c2b272d4ee4e0284ff8e13e446c581

## Independent findings

The source lock, old training config, and matched C5 manifest bind the same 24 TRAIN_C5_24 scene IDs and ordering. Luna reports rehashing all 24 raw/status/run_start triples with zero mismatch (72 files total); the resulting data contains exactly 24×1,999=47,976 event rows.

The NPZ contains only TRAIN features, physical-residual targets, scene IDs, event/time indices, and fixed J0. It contains no VAL or TEST array. The builder's feature reconstruction matches the locked C5 train feature member elementwise (max float32 difference 0). Root independently recomputed the NPZ SHA, shapes, and TRAIN-only target RMS: [8.0208567, 7.1227997, 0.4822274] rad/s². Root also independently reconstructed features and the fixed-J0 residual at events 10, 100, and 19990 from three raw scenes; maximum feature difference was 0 and maximum target difference was 1.051e-12 rad/s².

All 24 records report zero generalized clipping, zero motor saturation, and zero difference between controller-clipped and requested generalized commands. The requested command is strictly 4 columns under the C5 runtime contract; the builder now fails closed on other shapes. The label uses transitions e-10 through e-1 and state samples through e, never the command at e. The independent synthetic sign check recovers a known disturbance acceleration [0.7,-0.4,0.2] rad/s² with near-machine-precision error and gives near-zero residual for zero disturbance.

The 8 T2 source_scene_id values with suffix _ACC_FIX_V1 are preserved as aliases. Their raw scene_id matches the locked scene ID, and the run_start/status source alias is recorded in the manifest with the same external identity SHA; the alias is disclosed rather than silently rewritten.

The target uses fixed nominal J0 and an interval residual derived from logged body rate, timestamps, and already-requested controller torque. It is an offline training label and an approximate nominal-model residual, not true time-varying inertia or instantaneous disturbance. The runtime must continue to use only the existing 13 legal feature inputs and the past-event window. Jhat/Jdot, true plant torque/disturbance, wind, actual arm lengths, RBF outputs/hidden states, and future samples remain prohibited.

## Training authorization and limits

Authorize exactly one fixed-seed MLP15 model training on TRAIN_C5_24 only, per the taskbook, with input/target normalization fit from TRAIN only. C5_VAL48 may be scored once for offline diagnostics and must not alter checkpoint selection, normalization, hyperparameters, or source. The legacy full72 MLP checkpoint is not an independent validation comparator because its training config used C5_VAL48 as fitting data.

Luna may now finish the isolated training implementation, freeze/hash the exact training config, and run this one training plus offline evaluation and MATLAB/Python no-Plant parity. No Plant call, closed-loop flight, TEST read, additional seed, or parameter search is authorized by this review. Root must inspect the resulting model/config/source hashes and no-Plant reports before issuing any separate closed-loop release.
