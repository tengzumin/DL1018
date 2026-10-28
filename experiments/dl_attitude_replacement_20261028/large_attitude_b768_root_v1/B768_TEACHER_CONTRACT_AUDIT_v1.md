# B768 attitude teacher contract audit v1

**Status: PASS for the B-only training data contract.** This approves the extracted TRAIN/VAL arrays as causal 13-D inputs and 3-D post-limit/pre-beta RBF targets; it does not certify a not-yet-frozen GRU deployment implementation.

## Checks

- NPZ: TRAIN 768 and VAL 48; 1999 events per episode; shapes `(768,1999,13)/(768,1999,3)` and `(48,1999,13)/(48,1999,3)`. Task counts are 256/16 per task; physical TRAIN and VAL scenes are disjoint.
- Source binding: action-specific raw/run_start paths match all 816 B records. `RUN_PLANT` uses G3 paths; PILOT/REUSE actions use source paths.
- Run-start cfg: all 816 are `fixed`, dmax `[45,45,4.7124] rad/s²`, beta rise `2.2 s`.
- Three task spot checks match NPZ features/labels to current event samples. Inputs are wrapped attitude error (rad), body rate (rad/s), nominal BS torque (N·m), and four arm commands. Target is `rbf_output_raw`, clipped by dmax before the beta ramp.
- For each sample, `rbf_output_raw == clip(rbf_output_unclipped, ±dmax)` and the logged applied acceleration matches `min(k·dt/beta_rise,1) * rbf_output_raw` to numerical precision. The beta log itself is nonfinite in these raws, so it was not used.
- The target is acceleration disturbance in rad/s². The existing C5 builder's fixed J0 reference is `[0.003257553333333334, 0.0032575533333333334, 0.006360648333333333]` kg·m²; this is recorded as provenance only and was not re-derived or applied to the B768 raws. No inertia fields or torque reconstruction were read.
- The 13-D ordering matches the C5 teacher builder and C5 online feature trace contract. A new GRU runtime still needs to implement this same current-event feature order and beta application before deployment is considered audited.

## Scope limits

Raw full-file SHA-256 is not verified. Raw-to-NPZ features and labels were checked on one TRAIN B episode per task; run-start cfg was checked across all 816 B episodes. The existing fixed J0 reference was not revalidated against this expanded cohort. No TEST rows/files were accessed and no training was started.

Machine-readable details are in `B768_TEACHER_CONTRACT_AUDIT_v1.json`.
