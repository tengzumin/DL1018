# DL1018 实验归档索引

更新时间：2026-10-28。

本索引用于快速定位 DL1018 的已结束实验、主要结果与当前工作。已结束包括通过和未通过的实验；未通过的结果保留为负结果，不作为方法成功结论。

## 仓库归档范围

GitHub 提交包含实验代码、配置与来源锁、紧凑的指标和状态文件、复核报告。`.mat` 模型/运行文件、模型权重、逐步仿真轨迹、事件 H5、数据集 NPZ、MATLAB 本地偏好目录和证书均不上传。当前本地未跟踪文件约 78.9 GB，绝大部分是生成数据。

## 主要实验脉络

| 方向 | 实验目录或报告 | 结果与状态 |
|---|---|---|
| DL1018 正式门控 | 根目录 `README.md`、`reports/G06_P_DEV.json` | G00–G05 已通过；G06 停在 `STOP_POSITION_NOT_QUALIFIED`；G07–G13 未启动。 |
| 位置控制方法迭代 | `experiments/position_prior_calibration_c1_20261022`、`position_beta_clock_c2_20261023`、`position_delayed_prediction_c3_20261023`、`position_coordinate_c4_20261023`、`position_axis_coordinate_c5_20261023` | C1–C5 的代码、参数和复核资料按实验目录归档；各阶段结论以对应 Gate 与审计报告为准。 |
| C5 匹配消融与冻结评估 | `experiments/position_c5_matched_ablations*`、`experiments/c5_test48_v*`、`experiments/c5_test48_recovery_v1` | 包含消融版本、TEST48 冻结证据及恢复审计；原始运行轨迹不随本次 Git 提交上传。 |
| C7 split-target 隔离 | `experiments/position_split_target_c7_20261024`、`reports/paper_continuation_20261023/STATE.json` | 仍处于准备/复核阶段，当前状态记录为 0 次 Plant 调用；不列为已完成实验。 |
| 姿态替代模型 | `reports/attitude_experiment_reconciliation_20261027/HISTORY_INVENTORY_v1.md` | 历史候选的完成数和负结果见下表，不把失败筛选结果表述为成功。 |
| 新双环小数据试跑 | `experiments/dl_attitude_replacement_20261028/large_gru_dual_loop_dev24_v1` | 24 场包在首场后以 `STOPPED_FATAL` 结束，0 个完成计分场景；保留代码与失败状态，作为一次已结束的失败试跑。 |
| 新双环大数据 | `experiments/dl_attitude_replacement_20261028/large_attitude_data_root_v1`、`large_gru_dual_loop_dev_v1` | 仍在进行：TRAIN 数据生成进度为 512/1536；24 场双环包处于 `PREPARED_NO_PLANT_PENDING_ROOT_AUDIT`。本次提交不包含这两个活动目录。 |

## 姿态候选历史摘要

以下状态来自 [HISTORY_INVENTORY_v1.md](attitude_experiment_reconciliation_20261027/HISTORY_INVENTORY_v1.md)：

- MLP15 causal：6/6 VAL 完成，未通过 C5/位置门控，Q 比 C5 差 13.38%。
- MLP15 composite v3：6/6 VAL 完成，未通过 task SO(3) 与 Q 门控，Q 比 C5 差 15.79%。
- GRU cosine tracking head：6/6 VAL pilot 完成；内环误差改善，但高频 task SO(3) 仍差于 B/C5。
- GRU full72：72 行评分完成，其中 66 个新 raw 审计和 6 个父结果复用；72 场同时用于训练，属于 in-sample 结果。
- NCMD：DEV24+VAL48 训练完成，6/6 VAL 飞行完成；task SO(3) 门控未通过。
- WN12：12 场筛选指标已记录，未通过 Q 门控；当前工作区缺少其候选 raw，旧 raw 重评分不能复现。
- Beta025：仅 28 场离线命令/滤波 shadow 通过，Plant 调用数为 0；已准备的运行包未执行。
- force09：12 场中有 3 场候选 raw 的环境风为全零；风扰语义需要按审计报告解释。

## 当前推进记录

训练中的 TRAIN 数据和新双环运行产物只在本地保留。待数据生成、来源锁复核和 24 场评估完成后，再将新实验摘要、模型权重与审计报告单独归档；原始仿真轨迹仍按项目既有约定留在本地。
