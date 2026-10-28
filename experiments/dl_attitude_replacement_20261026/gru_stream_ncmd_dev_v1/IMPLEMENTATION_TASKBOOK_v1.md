# NCMD GRU 部署准备任务书

- study: gru_stream_ncmd_dev_v1
- candidate: GRU32_STREAM72_NCMD_S2026102001
- direct runtime parent: gru_stream_cosine_dev_v1
- created_utc: 2026-10-26T22:31:28Z
- state: candidate-specific deployment bindings prepared; root review pending.

## Scope

This isolated deployment study inherits the reviewed GRU_STREAM runtime from the cosine study. Its 58 locked MATLAB runtime files are copied byte-for-byte. Only driver, audit, manifest, and release identity are adapted. No controller math is changed.

The fixed trainer outputs are:

- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/stream_parity_vector_v1.mat

Training source identity is reference-only. The feature NPZ SHA-256 is b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f. The nominal-command target NPZ SHA-256 is 88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7 and its manifest SHA-256 is fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab. Only c5_train_y_clipped_float32 and c5_val_y_clipped_float32 are the candidate Y arrays. No dataset, raw, or run files are copied into this deployment study.

## Current evidence and safety

The fixed trainer run has completed. Model SHA-256 is cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6; parity vector SHA-256 is c040257fb3b86a1d0dfd43cbc002259499eb3ed5028d29cef2afc23d8f409880. Root accounting review confirms 60,000 steps and 29,985,000 valid samples. Python full-sequence parity is PASS: output max absolute error 5.3329831511961245e-6 and final hidden max absolute error 1.7942364471945638e-7.

MATLAB full-sequence double parity passed: output max error 4.63518112781003e-15 and full hidden max error 7.7715611723761e-16. The noPlant audit passed on R2025b session 25790 with exit 0: real prepared CFG, fixed J0/Jdot0, [Inf Inf 6], isolated which paths, and both zero-budget rejections. Plant authorization is zero, TEST is unread, and this deployment study has not run training or created a runs directory. Root review is required before any later authorization.

The candidate remains GRU_STREAM: current 13 features only, hidden reset per scene, fixed weights, and the existing DMAX then beta then fixed-J0 mapping. Position, BS, filters, Plant, and actuator paths remain inherited. RBF output/update, RLS, composite head, delay, Jhat/Jdot, and true-Plant inertia inputs are not introduced.

