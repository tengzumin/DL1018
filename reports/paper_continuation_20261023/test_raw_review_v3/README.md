# TEST48 mixed v3-B48 / v5-five-method raw reviewer

`audit_test48_raw_v3.py` is the post-run reviewer for six method blocks that share the frozen v3 48-scene package. It reuses the v3 B48 block without rerunning it and reviews only the five new method blocks under `experiments/c5_test48_v5/`. Their source and output basenames and JSON schemas intentionally remain V4; v5 identifies the isolated verifier path-order repair.

The reviewer requires the root-approved v5 run release and five natural OS0 method receipts, while checking the reused v3 B48 OS0 receipt and exact v3 frozen input package. Before opening any raw MAT or invoking the frozen scorer, it also verifies the chronological process history: the original v3 DSSM startup failure (OS1, zero Plant calls), the v4 preparation failure (OS1, zero Plant calls), the isolated v4 path diagnosis (OS0, zero Plant calls, six path mismatches among 168 rows), the v5 no-Plant preparation, the two fixed DEV2 engineering replays, and the five formal v5 method receipts. The v3 and v4 failures and v4 diagnostic remain history only; they are not successful method blocks or scored rows.

The v5 entry/launcher/contract/manifest and v3 taskbook/code-only release are pinned by SHA-256 in the reader. The v5 manifest must retain the six-method order, B48 reuse, shared v3 scenes/cfgopts/index, exact model/source/global-platform identities, and the two approved PCF helper additions for DSSM/KAN. The engineering release bindings use the actual `engineering_DSSM_result_sha256`, `engineering_DSSM_os_exit_sha256`, and matching KAN fields. The historical v3 corrected raw files still do not prove their original MATLAB `which` identities; the v5 dependency lock and DEV2 full-raw replays support the fixed helper behavior but do not retroactively fill that source-history gap.

After all process receipts and stages pass, the reader reuses the frozen v1 raw scorer, actuator checks, 20,000-transition timer checks, readiness summaries, corrected initial-W0 checks, and C5/ablation event auditors. The output keeps the frozen statistics interface: `PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS`, `TEST_accessed=true`, 288 unique scene/method rows in six exact method blocks, and the existing metric/timer fields. The raw audit does not decide the performance gate or paper status.

The code-only release leaves MATLAB, Plant, TEST generation, and training unauthorized. This delivery did not run the raw-review CLI, open TEST raw files, or read TEST scores. `--self-check` is limited to in-memory synthetic checks and frozen helper checks; the final `--output-json` invocation is for the root reviewer only after all five v5 method blocks naturally exit OS0 and the run release is present. Output files must be new; overwrite is refused.

```powershell
python reports/paper_continuation_20261023/test_raw_review_v3/audit_test48_raw_v3.py --self-check
python reports/paper_continuation_20261023/test_raw_review_v3/audit_test48_raw_v3.py --output-json reports/paper_continuation_20261023/test_raw_review_v3/TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS_v3.json
```
