# DSSM 与 B 的历史运行身份审计

日期：2026-10-22。范围为运行清单、`run_status.json`、身份账本、run_start 文件 SHA 与归档源码快照。没有读取原始 `raw_run.mat` 内容，没有访问 TEST、启动 Plant/训练/闭环，也没有修改历史归档。

## 结论

- **DSSM14 的 72 场身份闭合到运行记录。** 61 场在主归档 `corrected_pair_eval_v1`，另 11 场 DEV 在 tail21 续跑归档。72 条 candidate raw SHA 全部唯一地匹配一条 `RUN_COMPLETE_STABLE` 状态记录，且 `runtime_status=STABLE`、`complete=true`、`finite=true`。
- 每条记录的模型 ID/hash、source/runtime scene ID 与当前项目中的 `mechanism_run_start_lineage.csv` 一致；72 个 run_start 文件只做字节级 SHA-256 核验，全部匹配 lineage 的 before/after SHA。尾部 11 场含 `_ACC_FIX_V1` 的 runtime scene ID，与 lineage 记录一致。
- 两个 DSSM 运行批次报告的绝对路径绑定 runtime-tree SHA 不同：主归档 `5a4a104314c63a2a7928e2be359b6ce269da92f23895f1346768728879745db0`，tail21 `ef022e03be0c1caee5753fbf1a233aff4adf4331dfb520c6fcc9db2945de76c6`。独立逐文件比较确认两个 `sources/local_runtime` 快照的 8 个 `.m` 文件名称和内容 SHA 全部相同；归档合并报告也记录 normalized runtime-tree SHA `2b47d306b50f5b654d76da5850b62d765f1fd63fc63cf9a6cbade1173862fa38`。归档合并审查把模型、checkpoint、有效配置、manifest、场景快照等列为一致的科学身份字段。绝对树哈希差异来自路径绑定。主／tail runner、supervisor 和预检报告各自有冻结身份；tail runner 将执行限制在 124–144 索引，不能把其包装层哈希差异误说成 Plant/runtime `.m` 代码差异。
- **B 的 72 场历史源码身份仍未闭合。** 归档 `PAIR_EVAL_BASELINE_REUSE_288.csv` 中有 72 条 B 记录及 raw SHA、run_start SHA、模型 ID 和评分/回放记录，但没有逐次运行 `runtime_tree_sha256` 或足以绑定完整源码树的同期清单。数值配置和 `collector_id=B` 只能描述配置，不能恢复当时实际加载的 runner、helper、Plant/执行器源码及路径优先级。

因此，DSSM 当前分数对应的 72 条原始运行可以追溯到两个被封存的 runtime 快照；它们的核心本地 `.m` runtime 内容一致。B 的旧分数和日志仍可作为历史对照，但无法声称已复现其完整历史可执行环境，也不能据此完成“同一源码环境”的因果归因。若归档里不存在 B 同期 source/runtime manifest，这个历史身份缺口无法靠当前源码事后补回。

## 可复核的归档位置

外部只读证据源位于 DL1018 同级的归档，不是当前 Git 工作树：

`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\`

- 主归档：`corrected_pair_eval_v1/manifests/PAIR_EVAL_BASELINE_REUSE_288.csv`、`corrected_pair_eval_v1/reports/PAIR_EVAL_FROZEN_IDENTITIES.json`、`corrected_pair_eval_v1/runs/**/run_status.json`。
- tail21：`corrected_pair_eval_tail21_v1/reports/PAIR_EVAL_FROZEN_IDENTITIES.json`、`corrected_pair_eval_tail21_v1/reports/STAGE_MAIN_TAIL_21_IDENTITY.json`、`corrected_pair_eval_tail21_v1/runs/r124,r126,r128,r130,r132,r134,r136,r138,r140,r142,r144/attempt_01/run_status.json`。
- 独立归档合并审查：`corrected_pair_eval_tail21_v1/reports/composed_postrun/PARENT_POSTRUN_MERGE_REVIEW.json`；其中 144 场合并状态为 `PASS_COMPOSED_144_ALL_STABLE_TWO_SESSIONS`，并载有两批科学身份字段、路径敏感身份差异与 normalized runtime-tree 复核结果。此处只将其用于身份核验，不把 KAN/DSSM 合并评分当作 B 比较结果。

本地复核命令（PowerShell 7，仅读取 JSON/CSV、run_status、源码快照及 run_start 字节哈希，不打开 raw_run.mat）：

```powershell
python -B reports/paper14_v2/phase1/verify_historical_runtime_identity.py
```

## 决策

三轮研究上限已经用尽；此身份补证不授权新增航次或解封 TEST48。DSSM 72 场身份不再列为未解决项。B 历史身份仍列为不可恢复风险：下一周期若找不到同期清单，应明确选择“沿用历史 B、声明执行环境身份限制”或另行批准一组新冻结环境的 B 基线；不得将后者称为历史 B 的复现。当前开发性能仍低于预设门槛，论文证据包仍为 `NOT_QUALIFIED`。
