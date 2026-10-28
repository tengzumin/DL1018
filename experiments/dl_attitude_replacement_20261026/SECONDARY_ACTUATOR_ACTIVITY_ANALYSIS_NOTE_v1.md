# TCN 姿态替换：次要执行器活动指标预登记

状态：预登记分析；不修改候选、训练、主验收门或 Plant 航次预算。  
适用数据：DEV 与一次性 TEST 中身份合格、完整的候选/B 配对 raw；可复用时不重跑基线。  
解封要求：在任何 TEST 数据读取前，将本文件 SHA-256 随最终统计规则锁定。

## 指标

对 0–20 s 记录的四个电机转速命令 \(\omega_i[k]\)（rad/s），定义归一化总变差：

\[
TV_{\omega} =
\frac{\sum_{k=2}^{N}\sum_{i=1}^{4}|\omega_i[k]-\omega_i[k-1]|}
{4\cdot1900\cdot20}.
\]

这个指标描述电机速度命令的总变化量，按四个电机、1900 rad/s 上限和 20 s 时长归一化。计算口径复用项目现有 matlab/metrics/measure_pcf_dl1018.m 的 motor_TV_normalized_per_s 定义。候选 raw 由 runner 保存 motor_command。

## 报告规则

- 主要按身份合格的逐场候选/B 配对计算差值；对已存在且身份匹配的 corrected C5_RBF raw 作次要比较。报告 DEV/TEST 的场景等权均值、配对差均值和场景级配对 bootstrap 区间，并给出 W09–W14、W15 分组。C5_10 仅可作为单独物理对照列出，不用于归因。
- 只在 raw 完整、转速有限且时间轴符合冻结场景时计算；缺失场保留并说明，不能静默剔除。
- 与已冻结的 motor saturation、generalized clipping、tilt limit 和控制耗时并列报告。该指标不增设通过门槛、不参与 checkpoint/模型/阈值选择。
- 只能称为“归一化电机指令总变差”或“命令平滑度代理”。仿真没有经校准的电机电流、电压、效率或功率模型，因此不得据此声称实际能耗/电池收益。
- 不新增任何闭环航次；按冻结 TEST48 一次性流程读取，失败后不重跑或调参。

## 代码依据

- matlab/metrics/measure_pcf_dl1018.m：现成归一化公式。
- experiments/dl_attitude_replacement_20261026/pilot_runner_v4_teacher_distill/candidate_runner_work/matlab/runtime/run_gate_holdout_closed_loop.m：候选 trace 保存 motor_command。
- 原始电机命令由 allocator 按转速（rad/s）记录；不把平方转速或分配请求混作实测转速。

本指标是应用层次要结果，不替代论文主要位置/姿态性能与安全证据。

