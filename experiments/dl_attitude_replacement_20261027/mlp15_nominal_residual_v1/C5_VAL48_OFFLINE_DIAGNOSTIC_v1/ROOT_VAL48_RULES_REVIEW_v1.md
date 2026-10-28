# Root review: C5_VAL48 one-shot evaluation rules

Date: 2026-10-27 (Asia/Shanghai)

- Source freeze SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_SOURCE_FREEZE_v1.json); source-lock SHA-256: 2c733dd093ab2ea1ff74f6cf2828a130345f022b3439456bf22abff8961edc8a.
- Identity check SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_IDENTITY_CHECK_v1.json). The manifest reports 144/144 raw/status/run_start hashes match, 48 unique C5_VAL48 scenes, and no numeric arrays read, TEST access, or Plant calls.
- Frozen evaluation rules SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_EVAL_RULES_v1.json). These bind the candidate checkpoint/MAT identities and predeclare a zero-residual baseline on exactly the same physical residual labels. Metrics are per-axis pooled, per-scene macro, per wind group and per scene, plus distribution/clip summaries. Candidate scoring is the frozen base MLP15 before beta ramp or causal-head adaptation; this is an offline label diagnostic only.

## Decision

Approve one C5_VAL48 numeric read/reconstruction/score under these identities and rules. No training, selection, code/threshold/normalizer changes, TEST, or Plant. This is reused validation data, not independent testing. The separate MATLAB subtask may proceed with only the frozen training parity fixture and MAT weights. Both workstreams stop for root review; no closed-loop screen is authorized here.
