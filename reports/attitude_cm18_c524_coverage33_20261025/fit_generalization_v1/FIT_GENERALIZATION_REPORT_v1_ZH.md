# C5_COVERAGE33 冻结模型拟合与跨场离线诊断

本报告只比较同一个冻结 CM18 checkpoint 对 TRAIN/DEV cache 中直接 `Cstar/beta` 标签的纯前向逐点残差。它不是闭环结果，也不是独立测试或 TEST 泛化结论。

## 主比较（每场 ordinal 0,5,…,1995 共 400 行）

| 项目 | 值 | scene-block bootstrap 95% CI |
|---|---:|---:|
| TRAIN_NRMSE T | 0.015295 | 0.010225 – 0.020636 |
| DEV_NRMSE D | 0.267078 | 0.210948 – 0.329972 |
| D − T | 0.251783 | 0.196141 – 0.315404 |
| D / T | 17.461698 | 11.916585 – 27.683459 |

预注册标签：**GENERALIZATION_GAP**。T=0,D>0 的 ratio replicate 数：0 / 10000。区间按 scene block 独立重抽 TRAIN 33 场与 DEV 15 场，不重抽事件行。

## 固定分割与校验

TRAIN 33 场：T1/T2/T3 = 12/10/11；DEV 15 场：4/6/5。
重建 row-map SHA：`bc202f6653fb04169990dac9dd209805bbf661b1797c3e64788206e6d6c75521`；sample-stream SHA：`c3bbbf2f82a8bb50e4851b08614816024c7b912e36f9f6c6a0bc1a215d3ec9a9`。
所有 cache：48 / 48 个通过身份、时钟、行图与 Cstar/beta 闭合；最大标签闭合误差 0.000000000000 rad/s²。

## 附加 DEV 分层

附加分层不改变主判定；少于 5 场的区间标为不稳定，仅作描述。每场先计算指标，再按场景等权汇总。

| 分层 | 场数 | 事件数 | 候选宏平均 normalized vector NRMSE | 95% CI |
|---|---:|---:|---:|---:|
| DEV_all_1999 | 15 | 29985 | 0.266899 | 0.210287 – 0.328629 |
| DEV_first_morph_event | 15 | 15 | 0.110367 | 0.086199 – 0.133415 |
| DEV_active_phase | 15 | 4558 | 0.305238 | 0.242444 – 0.370631 |
| DEV_phase_code_0 | 0 | 0 | — | — |
| DEV_phase_code_1 | 15 | 7985 | 0.000000 | 0.000000 – 0.000000 |
| DEV_phase_code_2 | 15 | 2290 | 0.338191 | 0.258208 – 0.427018 |
| DEV_phase_code_3 | 15 | 9656 | 0.419622 | 0.325773 – 0.523982 |
| DEV_phase_code_4 | 15 | 2268 | 0.225103 | 0.151437 – 0.308020 |
| DEV_phase_code_5 | 15 | 7786 | 0.000000 | 0.000000 – 0.000000 |
| DEV_W00 | 1 | 1999 | 0.250380 | 0.250380 – 0.250380 |
| DEV_W01 | 1 | 1999 | 0.212352 | 0.212352 – 0.212352 |
| DEV_W02 | 0 | 0 | — | — |
| DEV_W03 | 0 | 0 | — | — |
| DEV_W04 | 0 | 0 | — | — |
| DEV_W05 | 0 | 0 | — | — |
| DEV_W06 | 0 | 0 | — | — |
| DEV_W07 | 0 | 0 | — | — |
| DEV_W08 | 3 | 5997 | 0.252922 | 0.185388 – 0.366657 |
| DEV_W09 | 2 | 3998 | 0.235085 | 0.154635 – 0.315535 |
| DEV_W10 | 1 | 1999 | 0.223897 | 0.223897 – 0.223897 |
| DEV_W11 | 1 | 1999 | 0.464421 | 0.464421 – 0.464421 |
| DEV_W12 | 2 | 3998 | 0.201404 | 0.147125 – 0.255683 |
| DEV_W13 | 1 | 1999 | 0.462109 | 0.462109 – 0.462109 |
| DEV_W14 | 1 | 1999 | 0.476553 | 0.476553 – 0.476553 |
| DEV_W15 | 2 | 3998 | 0.141014 | 0.125269 – 0.156759 |
| DEV_W09-W14 | 8 | 15992 | 0.312495 | 0.225110 – 0.403873 |

TRAIN 与 DEV 各自的逐场物理/归一化 RMSE、signed bias、向量 bias、零输出基线以及中心化差值见 `primary_scene_metrics.csv`；DEV 全事件与分层逐场结果见 `secondary_scene_metrics.csv`，场景等权摘要和 bootstrap 区间见 `secondary_strata_summary.csv`。

## 范围与资源回执

本评估只读取 allowlist 中的 33 TRAIN 与 15 DEV EVENTS cache；固定 checkpoint 共执行 1 次 NumPy 前向、处理 95952 行；不读取 raw MAT、不读取 C5_VAL48/TEST、不训练、不调用 Plant/engine、不启动闭环。训练步数、optimizer steps、Plant calls、engine calls 与 episode calls 均为 0。

Taskbook SHA：`e0e274a2c12a038001a5b2bfe77ada944ed32c9a48c105933c97cdf5456c41ca`；checkpoint SHA：`960ef67b7dd2ac1d2d1bca5d13e818674b2f14357d85ae6035590914c250cb07`；model SHA：`66f8053782e7afb823afa24368cea8002b55b536a587a8e8b13dbb9e13cf3142`；normalizer SHA：`23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781`。

该结果仅诊断此 checkpoint 在固定 33 TRAIN / 15 DEV cache 标签上的逐点拟合差异；它不代表轨迹级闭环效能、其它场景总体表现或独立测试。
