# GRU target-fit diagnosis

## Conclusion

Keep the C5 RBF teacher target unchanged for now. The evidence points first to GRU teacher-fit / representation / sequence-distribution mismatch, not to a demonstrated error in the target definition. It does not identify which of optimization, representation, or closed-loop state distribution dominates.

On the same C5 recorded event sequence (six scenes, 10,680 mature events pooled), GRU-vs-RBF-teacher RMSE is **0.936 / 0.714 / 0.0524 rad/s²** for roll / pitch / yaw. The teacher target RMS is **10.77 / 10.85 / 0.380 rad/s²**. In the mature 2.2–5 s segment the approximate residual is nearly zero, but GRU-vs-teacher RMSE is **0.579 / 0.288 / 0.0446 rad/s²**; the corresponding RBF teacher is essentially zero-error against that interval target. This is a teacher-fit gap on C5_VAL48, which is included in full72 training, so it is not independent generalization evidence.

For mature C5 intervals, the RBF teacher vs approximate residual RMSE is **0.667 / 0.696 / 0.0983 rad/s²**, while GRU output on the same C5 sequence is **0.974 / 0.998 / 0.108 rad/s²**. On the GRU’s own six closed-loop records, its actual output vs the same interval approximation is **0.707 / 0.719 / 0.0992 rad/s²**. The own-record result is close to the C5 teacher’s residual fit, while the same-state C5 comparison shows a larger GRU gap. Since these are different recorded trajectories, this is evidence that sequence/state distribution matters; it is not a counterfactual comparison.

So the next branch should keep labels fixed and inspect representation / training fit and sequence distribution. Do not relabel the teacher from this analysis alone.

## Scope and method

- A: replay the frozen GRU from hidden state zero over all 1,999 C5 events per scene and compare its post-DMAX/pre-beta output with logged C5 `rbf_output_raw` at the same event.
- B: on those C5 records, compare the GRU and RBF outputs at interval start against the interval residual at the next event.
- C: on each GRU closed-loop raw, compare its logged post-DMAX output at interval start against the next-event interval residual.
- Each scene has 1,999 events and 1,998 adjacent intervals; the mature start-aligned set has 1,779 intervals per scene. The full CSV reports each scene, W15/HF/ALL6 pools, axes, beta maturity, early/late windows, RMSE, bias, target RMS, and valid count.
- Interval target is an offline 10 ms fixed-J0 nominal-model approximation using gyro differences and actual issued generalized torque. It is not an instantaneous physical residual, a closed-loop counterfactual, or a deployment input. No true inertia, Jhat, Jdot, Plant truth, TEST data, training, relabeling, or parameter search was used.

## Reproducibility

Run from the repository root with PowerShell 7:

```powershell
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:MKL_THREADING_LAYER='SEQUENTIAL'
python reports/gru_stream_target_fit_diagnosis_20261027_v1/diagnose_gru_stream_target_fit_v1.py
```

The script completed with `PASS_GRU_STREAM_TARGET_FIT_DIAGNOSIS` for all six scenes. Frozen model SHA-256: `963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021`. Prior validated target-semantics script SHA-256: `0d8e321861c0f149bea81ce5e99e27470e0ea593c9663c27402cf019e0a8ac32`. All source, model, C5 raw, GRU raw, status, audit, release, and prior-report input hashes are recorded in `INPUTS.json`.

Plant calls: 0. Training jobs: 0. TEST read: no.
## Full72 fit and fixed-hidden readout-gradient check

This bounded follow-up streamed the original C5 `TRAIN24` and `VAL48` arrays separately, resetting hidden state for each of 72 scenes. It used only the frozen MAT model and `matched_teacher_data_v1.npz`; no raw run or physical configuration was read.

| Split / period | valid events | RMSE roll / pitch / yaw (rad/s²) | Mean bias roll / pitch / yaw (rad/s²) |
|---|---:|---|---|
| TRAIN24, all | 47,976 | 1.044 / 0.973 / 0.0706 | +0.818 / −0.353 / −0.0390 |
| VAL48, all | 95,952 | 1.196 / 1.254 / 0.0883 | +0.881 / −0.571 / −0.0421 |
| ALL72, all | 143,928 | 1.148 / 1.168 / 0.0828 | +0.860 / −0.498 / −0.0411 |
| ALL72, beta mature | 128,160 | 1.210 / 1.237 / 0.0867 | +0.925 / −0.551 / −0.0416 |
| ALL72, last 5 s | 36,000 | 1.059 / 1.264 / 0.0634 | +0.817 / −0.471 / −0.0295 |

The positive roll bias is **not confined to the six screen scenes**: it is +0.818 in TRAIN24 and +0.881 in VAL48. Both subsets are part of the 72-scene teacher corpus used for this frozen model, so neither is an independent generalization set.

For the final frozen readout, the fixed-hidden SmoothL1 `head.bias` gradient is `[+0.035725, −0.017956, −0.022419]` with event-equal weighting. Under the actual 16-chunk equal weighting (15 × 128 events, then 79), it is `[+0.035626, −0.017932, −0.022279]` (L2 norm `0.045685`). The two estimates agree. This shows a remaining fixed-hidden readout descent direction; it does not reconstruct Adam history, establish why training stopped there, or prove that changing `head.bias` alone would improve closed-loop performance.

Together with the C5 interval check, this supports **keeping the teacher target fixed** and prioritizing training-fit / representation / sequence-distribution investigation. It does not establish that one of those factors alone caused the closed-loop screen failure.

Full72 script: `diagnose_full72_fit_gradient_v1.py`; result: `FULL72_TEACHER_FIT_AND_HEAD_GRADIENT.json`. Result status is `PASS_READ_ONLY_FULL72_FIXED_HIDDEN_DIAGNOSTIC`. Script SHA-256: `52c0c75a70c233f7a87309af8cb76ab0330e1348e404375194df85aadcf1489d`; JSON SHA-256: `b1d85c43d55bdac3b8c1394c8fd9dde5cd409f97f48a50fae1ca4d0a8df56323`.

Full72 input SHA-256: C5 dataset `b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f`; frozen model `963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021`. The JSON records hashes for the manifest, root six-scene metrics/decision, and prior validated script as well.

The full72 command is `python reports/gru_stream_target_fit_diagnosis_20261027_v1/diagnose_full72_fit_gradient_v1.py` from the repository root with `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and `MKL_THREADING_LAYER=SEQUENTIAL`.
Primary diagnosis script SHA-256: `08836ce6f728e0f7d6ca1d054247fe56dc1e9f8e88a919bbbb38996ee5a71beb`. Its six-scene inputs and raw SHA-256 values are enumerated in `INPUTS.json`.