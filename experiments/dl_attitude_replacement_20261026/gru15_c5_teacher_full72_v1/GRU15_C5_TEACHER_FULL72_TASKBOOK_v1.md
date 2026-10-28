# GRU15 C5 教师全量训练任务书 v1

状态：训练准备；尚未训练、尚未运行 Plant。此任务仅授权一份 C5 教师离线训练，闭环需单独审核 release。

## 目标

用已筛选的 GRU15 替换 MLP15，检验带门控状态的时序模型能否更好近似 C5 在线 RBF 补偿。GRU 输出姿态残差角加速度；其余闭环与 MLP15 对照保持一致。

## 合法输入

每一姿态事件输入 13 维，严格顺序为：

1. wrapped 姿态误差 3 维；
2. 机体系角速度 3 维；
3. 名义 BS 力矩 3 维；
4. 无量纲形态命令 4 维。

模型仅读取当前与之前 14 个事件；窗口外补零。禁止惯量或质量属性、`Jhat/Jdot_hat`、Plant 真值、RBF 权重或隐状态、observer、物理前馈进入输入或模型状态。固定名义 `J0` 仅在网络输出后把残差角加速度映射为力矩；不按形态重建惯量。RBF 输出和在线更新关闭，GRU 权重全程冻结。

## 数据与训练

- 复用 `mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz` 中的 72 场 C5_RBF 数据，143,928 个唯一事件；不读取 B24 数组，不读取 TEST48，不新增 Teacher/Plant 采集。
- 监督目标：事件 k 的 `rbf_output_raw`，已按 `dmax` 裁切、尚未乘 beta，单位 rad/s²。
- 结构：13 输入、单层 GRU、32 hidden units、15 事件因果窗口、3 输出；PyTorch GRU gate 次序 `reset, update, new`。
- 固定 seed `2026102001`、Adam、学习率 `1e-3`、weight decay `1e-5`、batch 512、60,000 steps；normalizer 只由 72 场开发教师数据拟合；只保留 `final_step_60000`，不依据验证集或闭环结果挑 checkpoint。
- 最大新增模型产物 2 GiB；无 Plant 航次、无 TEST 访问。

## 审核及后续门

训练前运行 CPU synthetic self-check，核对锁定数据身份和白名单；训练后检查 receipt、输入清单、模型权重和训练步数，并以 MATLAB no-Plant 独立实现做 GRU parity，容差 `1e-5 rad/s²`。任何输入字段、目标单位或时序差异均停止发布。

通过 parity 后才提交独立 GRU runner、no-Plant 特征审计和闭环任务书。闭环最多先跑 G1/W00 一场，人工审核后再释放同一六场 GHP7 ACTIVE 配对筛查；复用已有 B/C5_RBF raw，不重跑基线，不碰 TEST。固定 C5 `max_tilt=pi/6` 与残差 `dmax=[45,45,4.7124]` 是本批基线绑定条件；若采用其他倾角配置，须另行建立共同配置配对数据，不能只改候选。

性能门沿用用户目标：姿态宏平均严格优于 B 与 C5_RBF；位置宏平均优于 B，且相对 C5_RBF 退化不超过 10%；逐场报告 SO(3)、位置 Q、倾角投影、电机饱和、广义裁切与可行性。六场仅为开发筛查，不是 DEV72 或 TEST48 结论。
