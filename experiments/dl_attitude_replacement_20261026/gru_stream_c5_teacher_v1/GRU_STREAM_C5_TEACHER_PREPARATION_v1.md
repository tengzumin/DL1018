# GRU32 continuous-state C5 preparation

Candidate: `GRU32_STREAM72_S2026102001`.

This preparation reuses the approved 13→GRU32→3 model definition, C5 teacher data identity, and byte-identical full72 GRU15 normalizer. It changes the sequence protocol to carry scene-local hidden state across 128-event truncated-BPTT chunks. The fixed training schedule is one seed, four scene streams per optimizer step, Adam `1e-3` with weight decay `1e-5`, SmoothL1 `beta=1`, and exactly 60,000 steps if later released. The final 79 events are processed without padding. No gradient clipping, validation selection, resume, extension, extra features, online weight updates, or Plant calls are part of this candidate.

The source lock and training release0 both start with `authorized_jobs=0` and `plant_calls_authorized=0`. The formal command is gated on both files and is recorded in [TRAINING_COMMANDS_v1.md](TRAINING_COMMANDS_v1.md). The toy self-check verifies full-sequence versus per-event carry, scene reset, future-input isolation, valid-prefix padding, and chunk detach without an optimizer step.

The 48 scenes originally labeled C5_VAL48 were previously used for checkpoint selection/action comparison and are training data here. This 72-scene fit is not independent validation and cannot establish generalization or paper readiness.

Training output budget is 2 GiB. The approved training implementation writes only the final checkpoint, weights MAT, copied normalizer, full-scene parity fixture, step history, progress/config, and receipt. The current preparation creates none of those run outputs.
