# W15 同状态重放可行性审查

日期：2026-10-22。结论：**现有证据支持位置层和单次 Head/PCF 事件的局部复算；不足以重建 B 与 PCF-on 的完整同状态控制链反事实，也不足以把控制差异归因到最终 0–20 s X 轴 RMSE。** 本审查只复核既有 W15 审计、任务书和列明源码，没有重新读取 MAT、运行仿真、Plant、训练或预检，也没有访问 TEST。

## 已有记录能支持的结论

既有九个 W15 raw 审计显示，三场平均 X RMSE 为 B 5.738941 mm、PCF-on 6.837031 mm、R3 6.836015 mm。B 与 R3 在 20 ms 的位置命令力差等于 B 的 RBF 补偿力负值，逐分量残差小于约 \(10^{-19}\) N；状态首次差异在 21 ms，位置名义加速度差异到 22–28 ms 才出现。该早期分叉符合 B formal-RBF 与候选 P_A/DSSM 的预定配置差异，只定位首个请求差异。它既不能证明该微小差异造成后续误差，也不能排除经闭环递推累积的影响。

R3 相对 PCF-on 的首个 Head 更新坐标差异在 0.320 s，Head 输出差异在 0.330 s，完整状态差异在 0.331 s。既有 raw audit 已用记录的事件输入复算权重更新和更新后输出。三场 R3 相对 B 的平均 X RMSE 差为 +1.097074 mm；R3 的 X RMSE 比 PCF-on 低 0.001016 mm，但该差值来自各自闭环轨迹，不能据此估计 Z-mask 的因果效应，更不能解释其与 B 的差距。

## 方程与重放边界

`position_bs_step` 在固定状态、参考、参数和残差力下按

\[
e=r_p-p,\quad \dot e=r_v-v,\quad z_2=r_v+k_1\odot e-v,
\]
\[
a_{nom}=r_a+k_1\odot\dot e+e+k_2\odot z_2,\quad
F_{cmd}=m a_{nom}-F_{residual}
\]

计算名义与命令力。日志中的完整状态、参考及位置中间量可以核验已发生的局部计算；要在同一状态替换控制器重算，仍须有与该运行匹配的质量、重力、反步增益、倾角限值和候选/B 各自的残差估计内态。源码方程见 [position_bs_step.m](../../../matlab/core/position_bs_step.m#L17)。

单次 Head 事件需要 \(\phi,W_{before},s,\eta,\Delta t,\beta,d_{max}\)、mask 与协调开关；源码按更新前权重先算并限幅输出。PCF-on 更新面为 \(s-\eta\)；R3 runner 先计算 \(\eta_{eff}=[1,1,0]^\top\odot\eta\)，再用 \(s-\eta_{eff}\) 作为更新面，随后泄漏、Euler 更新并投影。既有审计已对一组实际事件完成局部复算，见 [position_stage1_update_head.m](../../../matlab/models/position_stage1_update_head.m#L8)、[position_stage1_update_head_pcf_v3_5.m](../../../matlab/models/position_stage1_update_head_pcf_v3_5.m#L9) 与 [R3 runner](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m#L1960)。这不构成整条闭环重放。

完整“位置 → 姿态目标 → 命令滤波 → 姿态力矩 → 分配/电机”重建还缺少可逐运行绑定的完整参数及身份：部分 MAT 没有完整数值 `cfg`，R3 `runIdentity` 不含全部运行参数，PCF-on 没有本次白名单内的 `run_start` 侧车。具体还需确认滤波初值与参数；姿态反步增益、惯量及惯量导数、姿态 RBF 残差估计内态；分配矩阵、限幅、上一时刻电机状态与电机时间常数；以及补齐模型/normalizer、runner/source SHA 与逐运行的绑定。对应源码为 [command_filter_step.m](../../../matlab/core/command_filter_step.m#L14)、[attitude_bs_step.m](../../../matlab/core/attitude_bs_step.m#L41)、[固定控制器/分配配置](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m#L67)、[分配与电机状态](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m#L2428) 和 [电机时间常数](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m#L147)。

要把 20 秒 X RMSE 解释为闭环因果结果，还须从相同初态分别推进各控制器及其内态，并固定或记录逐步外力、外力矩、形态输入、Plant 参数与求解步长。已记录的分离轨迹不提供另一控制器的反事实状态。Plant 使用广义输入、外力和外力矩推进，见 [vehicle_derivative.m](../../../matlab/core/vehicle_derivative.m#L31) 和 [rk4_vehicle_step.m](../../../matlab/core/rk4_vehicle_step.m#L13)。

## 决定与下一步边界

因此，当前能严谨报告的是：局部位置力和 Head/PCF 事件与已记录日志相符；W15 X 回归仍未定位；本次审查没有发现可确认的实现错误。不得据此宣称 RBF 差异无害，也不得将其解释为性能根因。若未来另行批准研究周期，先取得完整运行配置/源码/模型身份及以上内态，做不推进 Plant 的固定共同状态重放，并逐级复现已记录输出；重放不能在记录精度内复现时，停止因果推断。完成并审核该诊断前不新建闭环任务书。当前 3/3 轮次已耗尽，72 场扩展与 TEST48 保持封存。

本次 Luna 子代理的任务范围为源码和既有审计文件，没有重新读 MAT；请求的 GPT-6-Luna xhigh 和正常速度档无法由当前工具独立核验。
