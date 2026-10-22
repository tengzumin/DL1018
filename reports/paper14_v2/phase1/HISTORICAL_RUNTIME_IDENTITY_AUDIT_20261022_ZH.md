# DSSM 与 B 的历史运行身份审计

日期：2026-10-22。范围为运行清单、`run_status.json`、身份账本、run_start 文件 SHA 与归档源码快照。没有读取原始 `raw_run.mat` 内容，没有访问 TEST、启动 Plant/训练/闭环，也没有修改历史归档。

## 结论

- **DSSM14 的 72 场身份闭合到运行记录。** 61 场在主归档 `corrected_pair_eval_v1`，另 11 场 DEV 在 tail21 续跑归档。72 条 candidate raw SHA 全部唯一地匹配一条 `RUN_COMPLETE_STABLE` 状态记录，且 `runtime_status=STABLE`、`complete=true`、`finite=true`。
- 每条记录的模型 ID/hash、source/runtime scene ID 与当前项目中的 `mechanism_run_start_lineage.csv` 一致；72 个 run_start 文件只做字节级 SHA-256 核验，全部匹配 lineage 的 before/after SHA。尾部 11 场含 `_ACC_FIX_V1` 的 runtime scene ID，与 lineage 记录一致。
- 两个 DSSM 运行批次报告的绝对路径绑定 runtime-tree SHA 不同：主归档 `5a4a104314c63a2a7928e2be359b6ce269da92f23895f1346768728879745db0`，tail21 `ef022e03be0c1caee5753fbf1a233aff4adf4331dfb520c6fcc9db2945de76c6`。独立逐文件比较确认两个 `sources/local_runtime` 快照的 8 个 `.m` 文件名称和内容 SHA 全部相同；归档合并报告也记录 normalized runtime-tree SHA `2b47d306b50f5b654d76da5850b62d765f1fd63fc63cf9a6cbade1173862fa38`。归档合并审查把模型、checkpoint、有效配置、manifest、场景快照等列为一致的科学身份字段。绝对树哈希差异来自路径绑定。主／tail runner、supervisor 和预检报告各自有冻结身份；tail runner 将执行限制在 124–144 索引，不能把其包装层哈希差异误说成 Plant/runtime `.m` 代码差异。
- **普通历史 B 的 72 场源码身份仍未闭合。** `RAW_INDEX.csv` 与 `MATRIX_FINAL_288.csv` 将 B 作为 `REUSE`；`REUSE_IDENTITY.csv` 为其中 51 场补有 raw、模板 run_start、cfg/opts 哈希和稳定状态，但都没有原始 B attempt 的 `runtime_tree_sha256` 或足以绑定完整源码树的同期清单。数值配置和 `collector_id=B` 只能描述配置，不能恢复当时实际加载的 runner、helper、Plant/执行器源码及路径优先级。
- **后续 ACC_FIX 重跑补上了有限的可复现证据，但不能回填普通 B 的身份。** 在同级 `REFERENCE_FIX_FULL72_20261021_022342_313/runs/**/B/attempt_01/run_status.json` 中找到 21 条稳定的 `_ACC_FIX_V1` B 运行。每条 raw SHA 都与其 B 清单源 raw 相同，场景 ID 与模板 `run_start` SHA 也匹配；21 条都报告 `runtime_tree_sha256=a0cc9c286e635013038c378667c5c865579626c6b646b0df3a85c2ea0f238191`。归档 `reports/FROZEN_IDENTITIES.json` 将该树绑定到 runner `8d2786c49b080d93454e2acbaa937bb6b465b4295bcdcef1bb759879d7c2b3e9`、supervisor `ab940f0bc1d35cf5cb425227ea8086184ba6edd1d34de6aa4566c5147301703b` 和 support helper `dd51671c5b78b5748a1ac3d78385217687bcaee24c3ee64e57055f1d44e30a4c`。这些记录证明相同 raw 内容能在该后续运行身份下稳定重现；其 `runtime_scene_id` 明确带 `_ACC_FIX_V1`，而状态文件只存模板 start SHA、没有本次 attempt 的实际 `run_start.mat` SHA，所以它们不能证明普通 B 原始运行使用了同一环境。另有 FIG8_ACC_FIX 的 3 条稳定输出和 1 条 runner error 状态，但没有逐次 runtime-tree 身份，不能补闭此缺口。

因此，DSSM 当前分数对应的 72 条原始运行可以追溯到两个被封存的 runtime 快照；它们的核心本地 `.m` runtime 内容一致。B 的旧分数和日志仍可作为历史对照，但无法声称已复现其完整历史可执行环境，也不能据此完成“同一源码环境”的因果归因。新找到的 ACC_FIX 重跑只证明 raw 内容在新身份下可复现。普通 B 的原始 runtime/source/runner 身份在本次限定归档搜索后仍不可证明；不能用后来版本的运行清单事后补写旧实验身份。

## 可复核的归档位置

外部只读证据源位于 DL1018 同级的归档，不是当前 Git 工作树：

`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\`

- 主归档：`corrected_pair_eval_v1/manifests/PAIR_EVAL_BASELINE_REUSE_288.csv`、`corrected_pair_eval_v1/reports/PAIR_EVAL_FROZEN_IDENTITIES.json`、`corrected_pair_eval_v1/runs/**/run_status.json`。
- tail21：`corrected_pair_eval_tail21_v1/reports/PAIR_EVAL_FROZEN_IDENTITIES.json`、`corrected_pair_eval_tail21_v1/reports/STAGE_MAIN_TAIL_21_IDENTITY.json`、`corrected_pair_eval_tail21_v1/runs/r124,r126,r128,r130,r132,r134,r136,r138,r140,r142,r144/attempt_01/run_status.json`。
- 独立归档合并审查：`corrected_pair_eval_tail21_v1/reports/composed_postrun/PARENT_POSTRUN_MERGE_REVIEW.json`；其中 144 场合并状态为 `PASS_COMPOSED_144_ALL_STABLE_TWO_SESSIONS`，并载有两批科学身份字段、路径敏感身份差异与 normalized runtime-tree 复核结果。此处只将其用于身份核验，不把 KAN/DSSM 合并评分当作 B 比较结果。
- B 补充检索：归档根目录的 `reports/RAW_INDEX.csv`、`manifests/MATRIX_FINAL_288.csv`、`reports/REUSE_IDENTITY.csv`、`reports/FROZEN_IDENTITIES.json`、`runs/**/B/attempt_01/run_status.json`；21 条 ACC_FIX 原始结果身份另与 `corrected_reference_training_v1/corrected_pair_eval_tail21_v1/manifests/PAIR_EVAL_BASELINE_REUSE_288.csv` 逐项核对。限格式搜索覆盖 DL1018、DL1009/RBF-BS0、全流程审计、FIG8_ACC_FIX、FIG8_COMMON_STATE_PRIOR、REFERENCE_FIX_FULL72 六个指定根，解析了 1,021 个 `run_status.json`；找到 21 条 ACC_FIX 稳定记录及 4 条 FIG8_ACC_FIX 状态记录。所有检查均仅读取文本清单和 JSON，没有读取 raw MAT 内容。

本地复核命令（PowerShell 7，仅读取 JSON/CSV、run_status、源码快照及 run_start 字节哈希，不打开 raw_run.mat）：

```powershell
python -B reports/paper14_v2/phase1/verify_historical_runtime_identity.py
```

## 决策

三轮研究上限已经用尽；此身份补证不授权新增航次或解封 TEST48。DSSM 72 场身份不再列为未解决项。完成相邻归档搜索后，普通 B 原始运行身份仍是不可恢复风险：下一周期应明确选择“沿用历史 B、声明执行环境身份限制”或另行批准一组新冻结环境的 B 基线；不得将后者称为历史 B 的复现，也不得把后续 ACC_FIX 的身份当作旧 B 身份。当前开发性能仍低于预设门槛，论文证据包仍为 `NOT_QUALIFIED`。
