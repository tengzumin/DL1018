# GRU32 cosine C5 preparation

Candidate: `GRU32_STREAM72_COSINE_S2026102001`.

This is a copy of the root-reviewed `gru_stream_c5_teacher_v1` trainer/self-check into a new exclusive directory; no old `runs/` or `logs/` were copied. The sole optimizer algorithm change is a fixed per-update cosine learning-rate schedule: for update `s=1..60000`, `1e-5 + (1e-3-1e-5)*(1+cos(pi*(s-1)/59999))/2`, set before `optimizer.step()`. Every JSONL optimizer-step row records the applied rate as `learning_rate_step` and `learning_rate`.

The model remains single-layer GRU(13,32)+Linear(32,3), seed `2026102001`, batch 4, TBPTT 128, 1,999 events/scene, the same deterministic settings, C5 dataset and byte-identical GRU15 full72 normalizer, exact same seeded initial state_dict SHA `82d952ce8f150388015bc2776b8acceb9c9da59814470eb036ec9ca99420e06e`, Adam weight decay `1e-5`, SmoothL1 beta 1, and final-step-only checkpoint policy. No warmup, restart, plateau rule, early stop, resume, gradient clipping, additional input, validation selection, online head, Plant call, TEST read, or J/Jdot reconstruction is introduced.

The 72-scene schedule and valid-event ledger remain inherited unchanged: 60,000 optimizer steps, 29,985,000 valid samples, final chunk 79 valid events with no padding. `self_check` passed schedule endpoints/monotonicity, initial identity, normalization identity, streaming/reset/future isolation/valid-prefix/detach checks with `optimizer.step=0`. Release0 remains pending root review with zero authorized jobs and zero Plant calls. No training output directory exists yet.

After root approval, the one prepared launch command is in `ACTUAL_REPRODUCIBLE_COMMAND_v1.md`. It uses the previously successful preloaded-dependency/child-only KMP unset pattern. The runner writes the same MAT interface as the constant-LR candidate under `runs/GRU32_STREAM72_COSINE_S2026102001/gru_stream_c5_teacher_weights_v1.mat`.

The C5_VAL48_AS_DEV_TRAIN split is part of training and is not independent validation.
