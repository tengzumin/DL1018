# GRU14 / DSSM14 Student 采集与续训对照

任务状态：**COMPLETE**。
Student 配对轨迹：240/240；训练 fit：8/8；总 Plant 启动：433/432（含已记录工程重试）。
只比较位置 Q；B 为同场 DL1018 B 原始轨迹。姿态 RMSE 作为记录量，不参与选择。原始 B、原 Final 编码器、G06/合同文件均未覆盖。TEST 未访问。

## 四组 DEV24 配对结果

| 模型与训练组 | 稳定配对场数 | Student 宏Q (m) | 同场B宏Q (m) | 胜B场数 | 姿态宏RMSE (rad) |
|---|---:|---:|---:|---:|---:|
| DSSM14 / STUDENT_MIX20 | 24/24 | 0.014676588 | 0.016958918 | 15 | 0.014151841 |
| DSSM14 / TEACHER_CONTINUE | 24/24 | 0.014682934 | 0.016958918 | 13 | 0.014105712 |
| GRU14 / STUDENT_MIX20 | 24/24 | 0.015442366 | 0.016958918 | 15 | 0.01426854 |
| GRU14 / TEACHER_CONTINUE | 24/24 | 0.014893423 | 0.016958918 | 16 | 0.014169159 |

按 24 场宏位置 Q 与同场 B 比较：
- DSSM14 / STUDENT_MIX20：稳定配对 24/24，差值 -0.0022823303 m，宏Q低于B：True。
- DSSM14 / TEACHER_CONTINUE：稳定配对 24/24，差值 -0.0022759843 m，宏Q低于B：True。
- GRU14 / STUDENT_MIX20：稳定配对 24/24，差值 -0.0015165526 m，宏Q低于B：True。
- GRU14 / TEACHER_CONTINUE：稳定配对 24/24，差值 -0.0020654952 m，宏Q低于B：True。

## 训练步数扩展

共完成 100,000 个优化步。按用户要求，将终点最优的 fit 按 10,000 步扩展，直到最佳点不再位于区间终点：
- STUDENT_MIX20_DSSM14_SEED2026102011：10,000→20,000 步，最佳点 18,000 步；共同验证 RMSE 0.19942705。
- TEACHER_CONTINUE_DSSM14_SEED2026102012：10,000→20,000 步，最佳点 19,000 步；共同验证 RMSE 0.20355104。

## Student 逐条同场配对

逐条数据见 `reports/STUDENT_PAIRED_240.csv`；包含模型、split、scene、位置Q、同场B、差值、位置轴RMSE、姿态Q/轴RMSE和原始路径。

## BRIDGE6 候选筛选

候选逐场评分见 `reports/bridge6_package_scores.csv` 和 `reports/BRIDGE6_ALL_PACKAGES.csv`，锁定记录及锁定时序见 `state/LOCKED_CANDIDATES.json`。

DEV 全部逐场配对见 `reports/DEV_PAIRED_24.csv`（四组共96行）。

## 训练与复现

训练曲线见各 fit 目录的 `training_history.csv`；加载审计为 `reports/student_loader_check.json`。断点续跑步骤见 `RESUME.md` 和 `RUN_COMMANDS.md`。
