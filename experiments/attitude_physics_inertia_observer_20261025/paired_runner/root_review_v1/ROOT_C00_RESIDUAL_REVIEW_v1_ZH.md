# Root 独立审核：DEV3 A01 C00 残差诊断 v1

## 审核范围

直接读取 `dev3_v1/attempts/DEV3_20261025_A01/01_DL1018_DEV_T1_C00_W03_candidate/run_raw.mat` 中的候选 `log.phys_attitude_trace`、`wind_torque_B`、`realized_generalized` 与 `controller_clipped_generalized`。未启动 MATLAB/Plant，未读 baseline、TEST 或其他旧 MAT；物理真值只在闭环结束后离线计算。Raw SHA-256：`6f2716992181d1b06c9e28259b1bf16f7adec11c24a4ab90d27a0212acf3b202`。

最终诊断摘要为 `offline_c00_v1/final/summary.json`（SHA-256 `277065130e18f67d85641ad98088e5ca609bb52fdc8e261f9c40691cc2115ee3`）。该目录是权威版本；`offline_c00_v1/` 根目录的首稿存在维度错误，不作为证据。

## 独立复算

- HDF5 记录包含 20,000 个 helper trace 样本，时间从 0 到 19.999 s，步长 1 ms；attitude event 与 observer updated 标志一致，共 1,999 次更新。
- 逐事件按记录的惯量、角速度、实际裁剪力矩和时间间隔重建角动量残差；重建值与记录 `r_tau` 的最大绝对差为 0 Nm。独立分段 RMS 与最终摘要一致：0–2.2 s 的 XYZ 为 `[5.849929e-12, 8.773199e-12, 2.449727e-17] Nm`；2.2–20 s 为 `[1.893109e-12, 2.219047e-12, 2.498013e-17] Nm`。
- 全 trace 的 `Jhat` 恒为 `J0`；形态命令为零，`Jdothat` 和 `tau_shape` 为零。离线物理真值 `wind_torque_B + realized_generalized(moment) - controller_clipped_generalized(moment)` 的逐样本 XYZ 最大绝对值为 `[2.736526e-16, 3.000258e-16, 9.033098e-17] Nm`。
- 用 Simpson 替换陀螺项的梯形积分后，X/Y 残差反而更大；当前证据不支持把梯形求积单独认定为根因，也不支持任意修改滤波器或补偿限幅。

## 决策与边界

helper 的记录可以由部署公式与事件状态重放；本次没有发现能解释评分差异的实现算错。C00 下候选 observer 面对的主要是数值级残差，无法提供有意义的物理扰动补偿；旧 RBF 仍会执行其误差面跟踪修正。该观察与“候选移除了名义跟踪修正能力”相容，但由于两臂闭环状态不同，不能宣称已证明唯一因果。

C00 的既定严格结果保持 FAIL：candidate 相对 baseline 的位置 Q 增加 `2.5209584565e-7 m`，SO(3) RMSE 增加 `1.34242585e-6 rad`。不重跑、不改判据、不据此重标旧实验。

下一步按 `MORPH_DEV2_DIAGNOSTIC_TASKBOOK_v1_ZH.md` 审核并冻结隔离入口，然后只在预登记的两场主动形变 DEV 中测试应用价值；本审核本身不授权 Plant 航次。