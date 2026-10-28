# 局部角速度反馈敏感度诊断

## 原点 parity

六场各取 200 个成熟事件，以成熟事件序列上的 rounded linspace 固定抽样，共 1200 点。BS 名义力矩重建使用 `attitude_bs_step` 的 ZYX `T/Tdot`、固定 K1/K2、J0/Jdot0 与陀螺项；当拍滤波参考加速度来自 `command_filter_acceleration_applied_rads2`。原点计算与日志的最大绝对差：BS nominal torque `1.04e-17 N·m`，composite net torque 对 `requested_generalized` `7.63e-17 N·m`；SiLU base `2.89e-14`、phi `9.93e-16`。composite estimate torque 与原始 compensation log 最大差 `7.63e-17 N·m`。完整 parity 见 [local_feedback_parity_all_v1.json](local_feedback_parity_all_v1.json)。

固定 snapshot K1=`[1.5,1.5,1.3]`、K2=`[22.5,22.5,12.7]`；J0/Jdot0 使用 `LOCKED_CFG` 捕获的 fixed controller 值，Jdot0 为零。未访问可变形态/Plant inertia 字段。

## 中心差分结果

计算对象是 `tau_net(omega) = tau_BS(omega) - J0 * beta * clip(f_MLP(omega,tau_BS(omega)) + target_rms .* (W_before' * phi))`。姿态、参考及导数、arms、前14次网络输入历史、模型、beta 和日志中的 `weight_before` 全部固定；仅改变当前 omega，并据此重算当拍 `tau_BS` 特征。每次扰动都用同一个输出前 W，不运行 RLS/tracking 更新。MLP/补偿是事件触发的零阶保持信号；本导数只对应 100 Hz 事件输出更新瞬间，不建模事件间保持、状态演化或下一事件历史推进。EPS=`1e-5` 与 `5e-6` 的最大 Jacobian 差：BS `3.47e-12`、frozen MLP `6.05e-8`、composite `1.51e-7`；BS 解析式与中心差分最大差 `1.47e-12`。1200 个原点均无输出 clipping。

`Sym(-d tau/d omega)` 的最小特征值：

| 组 | BS only 中位数 / 最小值 | frozen MLP 负值比例 | composite 中位数 / 最小值 | composite 负值比例 | `||Jcomp−JBS||F/||JBS||F` 中位数 / P95 |
|---|---:|---:|---:|---:|---:|
| W15 | `0.0780 / 0.0749` | 70.8% | `−0.0479 / −0.9735` | 69.7% | `3.13 / 7.16` |
| HF | `0.0778 / 0.0739` | 49.2% | `+0.0263 / −0.5055` | 40.2% | `1.29 / 5.08` |

Composite 对角项的中位数均高于 BS 对角项：W15 roll/pitch/yaw `0.148/0.158/0.102` 对 `0.0782/0.0782/0.0891`；HF `0.0995/0.0904/0.0918` 对 `0.0782/0.0781/0.0892`。因此负的最小特征值对应耦合方向，不能概括成每个轴的对角阻尼都被削弱。

按时间窗的 composite 最小特征值中位数 / 负值比例：W15 first5 `−0.185 / 100%`、middle `−0.0157 / 56.5%`、last5 `−0.0607 / 78.6%`；HF first5 `+0.0225 / 40.6%`、middle `+0.0341 / 36.0%`、last5 `+0.00678 / 48.2%`。代表极值包括 W15 T1 sample 16151（16.15 s，`−0.974`）、W15 T2 sample 17311（17.31 s，`−0.772`）和 HF T1 sample 12661（12.66 s，`−0.505`）。全部 1200 点、每轴矩阵与描述性极端事件见 [local_feedback_event_jacobians_v1.csv](local_feedback_event_jacobians_v1.csv)、[local_feedback_summary_v1.csv](local_feedback_summary_v1.csv) 与 [local_feedback_outliers_v1.csv](local_feedback_outliers_v1.csv)。

## 解释边界

结果显示冻结历史下的 MLP 输入反馈导数相对 BS 导数不可忽略，并在不少抽样事件中令 `Sym(-J)` 出现负特征值；这与局部交叉轴抗阻尼方向相容，值得审阅。实际 composite 比 frozen MLP 的负值比例略低，且多数轴对角项增加，所以这些结果不证明 tracking 造成闭环劣化，也不能证明完整系统不稳定或确定主因。它只是固定状态/参考/历史/权重下的瞬时局部诊断；真实闭环中姿态、历史、估计与其他动力学会共同变化。成功的 C5/RBF 也可能依赖相似局部补偿，当前 MLP 结果不能说明这是 MLP 特有问题。下一项最小区分证据是只用现有成功 RBF/C5 raw 日志，在相同状态/事件采样下计算其局部 Jacobian（前提是日志完整保留该路径所需输入、输出和权重）；对比负特征值方向是否为通用补偿结构。日志不充分时明确记为不可判定，不重建惯量、不启动 Plant。

仅使用 Python 读取六个现有 raw、锁定审计、full72 模型与 fixed cfg snapshot。未启动 MATLAB、Plant、训练或 TEST，未修改 v3 源码/配置。
