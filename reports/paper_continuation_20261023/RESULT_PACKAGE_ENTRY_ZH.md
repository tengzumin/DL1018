# DL1018 仿真论文证据包入口（持续审核版）

当前性能验收已通过，论文证据包整体仍待最终贡献、稿件和复现发布审核。本页不替代原始记录，也不将历史失败改为通过。

## 已核验的结果

主指标为每场 0–20 s 三维位置 RMSE，场景等权平均；使用未舍入值与 `1e-12 m` 胜负容差。

| 数据 | C5 胜 B | B 平均 Q | C5 平均 Q | 高频组 | 无风组 |
|---|---:|---:|---:|---:|---:|
| DEV72 | 64/72 | 17.058081 mm | 11.558928 mm | 10.719024 → 10.179304 mm | 7.647292 → 6.334075 mm |
| TEST48 | 46/48 | 18.619575 mm | 12.155996 mm | 11.693191 → 11.005986 mm | 6.755625 → 5.527405 mm |

两套数据分别通过预定的胜场、总体 Q、高频 Q 和无风 Q 四项性能检查。TEST48 高频为 16/18 胜，无风为 3/3 胜；三维八字 T2 为 15/16 胜。TEST48 两个对 B 输场是 T1_C14_W09（差 0.106685 mm）与 T2_C14_W12（差 1.162507 mm），没有隐藏或剔除。该测试结果不得用来调整 C6 或重新选择 C5。

完整六方法 288 行指标、全部 comparator 输场、分组、逐轴、早后阶段、峰值、安全/饱和、计时、配对场景区间和微小收益敏感性均在 [最终结果目录](test_results_final_v1/RESULTS_REPORT_ZH.md)。父级逐项核对 11,232 个表格数字与冻结统计一致，见 `test_results_final_v1/PARENT_TABLE_REVIEW_v1.json`。

## 问题定位与方法作用

已有审核支持三个层次，不能合并成一个“网络不好”的解释：

1. 旧三维八字“全胜”包含不同评分窗口与实验条件。旧 32N_KAN 的 5–20 s 为 32/32，0–20 s 为 31/32，0–5 s 为 0/32；轨迹、启动插值、控制更新配置、模型与 normalizer 也发生变化。旧参考加速度曾有实现错误，修正它不等于恢复所有旧收益。
2. 物理预训练标签与在线 PCF 坐标目标不同。物理残差是 `a_actual − a_req`；在线完成区间标签相对 `a_M` 构造，含已知 PCF 坐标项。单看输出幅值、拟合损失，或比较不同闭环状态，不能证明某组件导致退步。现有匹配对照没有证实可直接归咎于共同 BS/姿态/Plant/执行器的控制器差异。
3. C5 的完成区间预测项具有有限、异质的实测作用。DEV72 相对仅移除此项的 NoPred 平均改善 0.551242 mm，54/72 胜；TEST48 改善 0.505912 mm，36/48 胜。T2 的配对区间仍跨零，不能写成每个任务普遍有效。固定 M110 相比 M111 的开发集收益约 0.200317 mm，只是累计收益的一部分。

上述根因与边界依据包括 `DEV72_FINAL_SCIENCE_SCOPE_DECISION_v2_ZH.md`、`final_contribution_peer_max/PEER_REVIEW_v1_ZH.md` 及其 T2 方向勘误，以及 `c5_eight_loss_recovery/` 内的旧结果追溯。冻结 trained W0 的消融保留网络与预训练权重，不能解释成“删除网络”实验。

## C6 三维八字修复分支

C6 只把预测梯度乘原有启动系数 beta，其余科学配置冻结。固定 12 场已真实完成：首场 1 + 尾批 11，均有自然 OS0 记录。根的独立配对复算显示：全程均值 9.055650 → 8.964622 mm，早段均值 11.620109 → 11.461167 mm，8/12 胜 C5。

但预登记要求两个旧筛查输场均改善，其中 T3_C00_W13 退步 0.275450 mm；三场 W15 相对 C5 也均退步。因此已决定**不扩展这个固定 C6 到 DEV72，不扫 beta/增益**。见 `c5_eight_loss_recovery/c6_startup_ramp/PARENT_C6_NO_EXPANSION_DECISION_v1.json`。逐事件完整性审计 v5 已真实自然 OS0：全部 23,616 次更新及物理配对检查通过，科学门失败得到确认；见 `PARENT_C6_SCREEN12_FINAL_REVIEW_v1.json`。读取器 v1–v4 的失败原位保留，没有重新运行仿真。

## 理论与文献

理论是对应实际延迟预测、tracking、泄漏与盒投影的条件有限路径误差界，并已在 DEV72 实例化；界与实际 Q 的比值约为 3.74–31.33。它依赖完整路径与明确的浮点残差假设，不证明先验 Plant 稳定性、未来误差小、参数收敛或优于 B。证明、非作者复核与数值映射见 `THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md`。

Jiang TNNLS 2022 等已有指令滤波、神经近似、跟踪/预测复合更新与投影；不能把这些原则称为首创。可论证范围是具体 PCF 坐标目标、完成区间更新时序、实际实现对应的分析和匹配证据。最直接相关原文对照见 `literature_peer_challenge_v1/PEER_CHALLENGE_JIANG_TNNLS_v1_ZH.md`；新原始文献补查见 `LITERATURE_PRIMARY_UPDATE_20261024_ZH.md`。部分离散四旋翼论文全文仍不可达，不能据摘要排除算法重合。

## 来源限制与复现

原 DSSM 首批 32 场的自然退出码 UNKNOWN，scene32 缺 `runIdentity`，旧六进程 OS0 门仍未通过；恢复的 208 场有各自自然 OS0 凭据。另有两条历史 TEST 摘要意外展示，C5 选择在其前冻结，与当前 TEST 的物理重叠 UNKNOWN。报告保留这两类披露，不声称历史完全盲测。单种子、单 Plant、理想全状态、无实飞与未隔离计时限制外推。

- [英文稿与证据映射](final_contribution_peer_max/manuscript_test_v1/EVIDENCE_MAP_ZH.md)：含 LaTeX 构建命令、输入身份及图表。
- `test_results_final_v1/build_test_results_final_v1.py`：校验冻结 JSON/CSV，整理表格和图；不运行 Plant、不重新采样。
- `test_handoff_incident_v1/recovery_v1/raw_review_v5/audit_test48_raw_recovery288_v5.py`：完整原始记录审核；需要本地保留的 MAT/模型与冻结来源文件。
- `test_handoff_incident_v1/recovery_v1/statistics_v5/test48_statistics_recovery288_v5.py`：冻结统计实现。
- `PAPER_EVIDENCE_REQUIREMENTS_AUDIT_CHECKPOINT_v3.json`：逐项完成证据与剩余工作。
- `STATE.json` 和 `README_RESUME_ZH.md`：现场状态与续跑入口；不得执行旧历史启动命令。

后续提交只包含审核过的源码、任务书、报告、小表与论文图稿。MAT、checkpoint、缓存、夹具和私有论文全文保留本地，不上传 GitHub。
