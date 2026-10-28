# Root review and release: single C5_VAL48 offline score

Date: 2026-10-27 (Asia/Shanghai)

## Frozen inputs

- Scorer SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\score_c5_val48_once_v1.py)
- Score lock SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_SCORE_LOCK_v1.json)
- Evaluation rules SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_EVAL_RULES_v1.json)
- C5_VAL48 source freeze SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_SOURCE_FREEZE_v1.json)
- 144-file identity check SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\C5_VAL48_IDENTITY_CHECK_v1.json)
- MATLAB parity hashes SHA-256: $(& param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() experiments\dl_attitude_replacement_20261027\mlp15_nominal_residual_v1\C5_VAL48_OFFLINE_DIAGNOSTIC_v1\matlab_parity\MATLAB_PARITY_HASHES_v1.txt)
- Checkpoint SHA-256: 9c924f1566447644287595253026e035b2fcb716a57be0e60d6f04bafdd8ed74

## Root audit

The scorer uses the frozen TRAIN-only checkpoint/normalizers, one forward pass over the 48 existing C5_VAL scenes, past-only features and residual labels at events 10..19990. The logged torque labels use transitions e-10 through e-1 and state endpoints e-10 through e. The score is the frozen base MLP15 before beta ramp or online-head adaptation, clipped only by frozen runtime dmax. It reports the same-label zero-residual baseline, per-scene and wind-group metrics, distributions, and clipping.

My independent --preflight returned PREFLIGHT_PASS: 48 scenes; 144 raw/status/run_start hashes matched; checkpoint, MATLAB weights, builder interface and event contract matched; numeric VAL arrays were not read; no start marker was created; TEST, Plant and training were not accessed. The scorer writes a final receipt and binds the no-Plant MATLAB parity manifest. MATLAB R2025b parity and Code Analyzer already passed (max error 6.1712762407933885e-7 rad/s^2, absolute tolerance 1e-6, 0 analyzer issues).

## Release

Approve exactly one numeric C5_VAL48 reconstruction and offline score under this lock. No model selection, fitting, normalization change, code/threshold change, TEST read, B/C5 rerun, or Plant call. C5_VAL48 is reused validation, not independent test evidence. After the score and receipt exist, stop for root review; no closed-loop screen starts automatically.
