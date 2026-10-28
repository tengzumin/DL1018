# 三场 DEV 输入身份补齐任务书 v1

日期：2026-10-25。此任务书只授权补齐隔离 runner 的三场 DEV 规格来源与静态检查；不授权 MATLAB、Plant、训练、航次或完整冻结锁。不读取 TEST 规格/结果、MAT 或 raw。

## 固定输入与来源

只允许从 `configs/scene_specs.csv` 取以下三行，不得根据 scene ID 推算或改写 seed：

| scene_id | split | source_split_code | seed |
|---|---|---:|---:|
| `DL1018_DEV_T1_C00_W03` | DEV | 1 | 2026121803 |
| `DL1018_DEV_T2_C02_W15` | DEV | 1 | 2026122847 |
| `DL1018_DEV_T3_C10_W11` | DEV | 1 | 2026123971 |

从源文件只提取 CSV header 与上述精确匹配行；必须恰好各一行，并校验 `split=DEV`、`split_code=2`、`source_split_code=1`、`sealed=0`、行内 task/class/C/W/seed 与表一致。将三行原文保存在隔离目录的 DEV-only CSV，并逐行记录原文 SHA-256、源文件路径及源文件 SHA-256。生成器只消费这份三行文件，且拒绝缺失/不符的来源字段。

## 代码语义和验证边界

“candidate 不触发 RBF”特指**姿态 RBF**：candidate 不得调用姿态 RBF 推理、更新或输出；保留 C5 DEV72 位置分支原有行为，两臂都可以执行 `updateDt=0` 的位置 RBF 兼容调用，但其输出必须被 C5 position Head 覆盖。禁止因此改写任何其他 C5 位置逻辑。

只用 PowerShell 7 提取/核对 DEV 行，随后做代码静态核验并更新 provenance 清单。任何行数、字段、hash 或分支差异失败即停止；不生成场景、不运行 MATLAB、不启动 Plant/闭环航次。

## 后续门槛

完成后由 root 独立复核三行原始身份、隔离生成器与 C5 位置源一致性，并完成有效 cfg、模型/权重及 scene payload 的身份锁定。只有完整 runner/source/input lock 审核通过后，root 才能另行放行三场六个 fresh DEV 配对航次。TEST 保持封存。
