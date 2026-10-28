# TRAIN-only scene validation equivalence

This preflight replaces the legacy `gate_holdout_validate_dev72_scene` wrapper only because that wrapper requires the unrelated 72-scene MLP15 payload manifest. The physical scene checks and closed-loop option/identity checks remain enforced.

| Legacy check | TRAIN-only replacement |
|---|---|
| Scene appears once in the 72-scene manifest; no TEST; DEV or VAL prefix | First scene in the 24-row `DATASET_MANIFEST_v1.json` and `SOURCE_LOCK_v1.json`, `TRAIN_C5_24`, exact `holdout_W00_05` membership, DEV prefix only, and explicit VAL/TEST rejection. Payload SHA is bound in the TRAIN source lock. |
| Fixed scene reference-contract tag | Exact `DL1018_SCENE_REF_FIG8_A2_V2` tag. |
| Plant configuration is 1 kHz | Exact `cfg.plant.dt == 0.001`, loaded from the locked C5 snapshot and fixed-J0 geometry path. |
| 20,001 samples over 0–20 s; 12 finite initial-state values | Same count, exact 1 ms grid, and finite initial state of length 12. |
| Position, velocity, acceleration, yaw, yaw-rate, and yaw-acceleration references are finite and shaped correctly | Same finite-value and shape checks on the selected TRAIN payload. |
| Environment wind is finite N×3; five morphology arrays are finite N×4 | Same checks on the selected TRAIN payload only. Optional `R_task` keeps its 3×3×N finite check and hash. |
| Audit records payload, external identity, and B raw hashes | TRAIN binding pins the payload and external-identity hashes; parent `run_start` pins B/C5 inputs; selected C5 input-lock row pins B raw/status and C5 raw/status/start. Each selected file is rehashed. |
| Candidate model/config and paired options are exact | C5 receipt, snapshot W0, DSSM14 weights, parent cosine-GRU model, heldout-fold checkpoint/MAT, beta and clips are hash/shape checked. `make_gate_holdout_options` and `gate_holdout_identity_hashes` recompute exact GRU_STREAM+C5 options and common-position identity. |
| Only authorized scenes/calls may enter runner | Release whitelist has one TRAIN scene and zero Plant budget. Runner requires this exact study ID, fixed scene, residual-weight hash, no-Plant flag, valid marker, and stops before the Plant loop. |

The checks read no VAL or TEST raw and use no 72-scene manifest. The historic same-scene parent/C5 raw files are only hash/status/start-checked as TRAIN comparators. This is a preflight, not a closed-loop result.
