# Root entry review: MORPH_DEV2 T3 continuation

Date: 2026-10-25 (Asia/Shanghai)
Decision: APPROVE exactly one T3 baseline-to-candidate pair, two runner calls total.

## Root review findings

- The A02 C02 attempt remains STOPPED_ON_FAILURE with its original candidate status FAILED_ENGINEERING. Root verified the two original MAT files by SHA-256 and byte length and independently reproduced the C02 score and full trace checks. No old status or raw was edited.
- The failures were in the isolated runner: it required vector histories to have N elements rather than N by 3, treated runtime scalar RBF toggles as per-sample vectors, and omitted the CSV index argument. The T3-only entry repairs these points without changing the plant, controller, model, normalizer, options, scene, seed, or scoring definition.
- The new wrapper, launcher and checker are confined to the new continuation directory. Source diff against the prior diagnostic wrapper shows only the T3-only execution scope, exact dimensions, trace assertions, budget/reporting and failure handling changed. Shared deployment and model files are unchanged.
- The PS7 static checker exited 0. Launcher and checker PowerShell parsers each reported 0 errors. It locked 39 deployment sources, 17 inputs, 9 prior A02 evidence files and 2 A02 raw manifests. Root independently rechecked the locked hashes and A02 raw bytes.
- MATLAB R2025b checkcode completed with exit 0 and 20 advisory messages (NBRAK2, STCI, AGROW, ALIGN, NOCOMMA, ISCL, MSNU, NASGU). These are Code Analyzer style/performance suggestions; no syntax failure was reported. MATLAB executable SHA-256 is 6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9.
- At decision time no MATLAB process was active and C: had 193.5 GiB free.

## Evidence motivating this continuation

In the existing C02 zero-wind 3D figure-eight, the physics/observer candidate improved position Q from 0.005412968909 m to 0.004270442964 m (delta -0.001142525945 m) and SO(3) RMSE from 0.013187128979 rad to 0.008521352291 rad (delta -0.004665776688 rad), with zero motor saturation and generalized clipping. The early segment regressed slightly and Z-axis Q worsened by about 0.00003175 m. This is a single scene and does not establish transfer.

T3, DL1018_DEV_T3_C10_W11, SQUARE with arms 3/4 active morphing, seed 2026123971, is the second preregistered application-domain scene. It tests whether the observed effect transfers. The result is descriptive and will not select a new model by itself.

## Authorized scope

- One shared T3 scene, baseline then candidate, exactly two runner calls; cumulative count including A02 is at most four.
- New attempt output cap 1,650,000,000 bytes; C: free space must remain at least 30 GiB.
- No C02 rerun, B, training, TEST, DEV72, tuning, retry, or method change in this release.
- Preserve all outputs and failure statuses. Any artifact, safety, integrity, or resource failure stops the batch; no retry from this release.
- Root will independently rescore the raw pair before choosing the next research stage. T3 alone is not a paper result.

## Frozen review identities

Candidate lock SHA-256: 87d607fbcff1681410b5709182c8cdf6ca4f54875edd30d3e8a890dbc0f50167
Static audit SHA-256: 0465048cca4f02bcffecfd647627440ef30fd0f2d77331085847697c58ac81d3
Wrapper SHA-256: 04c6a45f6886ad31becfcff6d12132b90bc594987c6f2c93421754fac0706d43
Launcher SHA-256: f15e9c7ac6eaf6ed2d1c8cf17db50082af54bf37f02d1bfd9aa9b5c53b1c2851
Checker SHA-256: 9b8b57b6c58fad6c69f8e218c2bab75656a4eac6180bf7d4ed5b757c34cc6795
Taskbook SHA-256: 5e2913d4f40ad0006fc86866313302bedfad23b310076efd5b743f8b7010b8e3
State snapshot SHA-256: 32d2f10bb800c828d7c45df4bb5d4eba55f1366cad529e8d7ab8f7200e70337a

This root approval applies only to the release written alongside this review record and does not alter A02 or authorize further runs.
