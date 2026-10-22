# W15 原始记录逐变量离线因果审计

日期：2026-10-22。用途：在已完成的 W15 三任务记录上定位早期控制链分叉，并区分实现错误、候选配置变化与尚未解释的性能差异。本次对数据与运行环境只读，仅修订本审计文档和状态账本；不启动 MATLAB、Plant、训练、预检或新航次，不访问 TEST。

## 审核结论

**未发现实现错误；B 与候选在 20 ms 的首个控制差异已由配置和记录字段闭环解释。** 三场 B 的 run_start 均标记 formal_rbf_baseline=1，且位置 RBF 输出/更新开启；候选则从 P_A 基线明确关闭两者，改用因果 DSSM Head，并在 32 个历史事件准备期内保持零输出。三场 20 ms 的位置名义力逐分量完全相同，B 与 R3 的命令力差等于 B 的位置 RBF 补偿负值，数值残差不超过约 \(10^{-19}\) N。该分叉是预先设定的控制器比较条件差异，不是实现错误。其量级仅标识最早分叉，不能据此解释或排除后续毫米级闭环差距。R3 的后续 z 轴差异符合预定 eta mask 改动；W15 相对 B 的主要性能根因仍未定位。

## 身份、字段与时序

审计读取已登记身份表中三场各自的 B、PCF-on、R3 XY 共九个 raw_run.mat，并读取对应 B/R3 共六个 run_start.mat sidecar。九个 raw_run 的 SHA256 均匹配 w15_offline_diagnosis_20261022.md 中的对应身份；未读取 PCF-off 文件。MAT 为 v7.3/HDF5；MATLAB 语义下每场有 20,001 个状态时点和 20,000 个控制转换。time 是状态时钟，transition_time 是转换左端点；因此 0.020 s 的控制请求基于 20 ms 状态，在推进到 21 ms 前记录。

MAT 日志字段覆盖完整状态、参考位置/速度/加速度/yaw、位置名义力与补偿力、Head/PCF 状态、姿态目标、滤波请求和输出、姿态力矩、广义请求/实现量及电机量。单位按字段名并与允许审计的源码交叉核对：位置 m、速度 m/s、加速度 m/s²、位置力 N、力矩 N·m、欧拉角 rad。MAT 本身未提供独立单位元数据。

## B 与候选的首个分叉

三对记录的初态、完整参考和 20 ms 状态完全相同。按字段绝对差大于 \(10^{-12}\) 检查，20 ms 首个位置请求差异是 position_commanded_force_N；随后 requested_generalized、raw_outer_attitude 与 command_filter_target_euler 也已不同。首个完整状态差异在 21 ms，均为极小机体角速度差；位置名义加速度到 22–28 ms 才出现差异，晚于控制请求和状态分叉。

| W15 场景 | B run_start SHA256 | B 位置 RBF 补偿力（N，t=0.020 s） | 最大 \(|B-R3|\) 命令力差 |
|---|---|---|---:|
| HELIX / T1_C08 | ec4bf37dc6d333434e1016902ce1c4a551e5dec3adc7cfffbed4efd5c74dc8ef | \([6.115e{-17},-5.190e{-9},-8.988e{-11}]\) | \(5.19\times10^{-9}\) N |
| FIG8 / T2_C05 | df4165f70ffffd44562f91c9972a6e2205c222b2f34fe5ccc7a1ff6d29252285 | \([-4.325e{-9},-5.766e{-9},-1.775e{-11}]\) | \(5.77\times10^{-9}\) N |
| SQUARE / T3_C02 | fb764089dbb6fd35bd3820cde4ec50d6c6aead1d8ff9d53009980664c9885be0 | \([-5.856e{-8},2.148e{-24},1.672e{-11}]\) | \(5.86\times10^{-8}\) N |

三份 B run_start 的 formal_rbf_baseline、rbf_position_output_enabled、rbf_position_update_enabled 均为 1；位置 RBF 频率为 100 Hz。20 ms 日志中的 position_compensation_applied_force_N 与 position_rbf_compensation_force_N 逐分量相同。对应三份 R3 记录的两种补偿字段和 stage1_position_held_force_I_N 均为零。三场 position_bs_nominal_force_N 的 B−R3 差逐分量为零，且
\[
\text{commandedForce}_B-\text{commandedForce}_{R3}
=-\text{position RBF compensation}_B
\]
的逐分量剩余小于约 \(10^{-19}\) N。因此记录可直接把最早位置请求差归到 B 的基线 RBF 补偿，而非状态、参考或名义位置控制不同。

源码也吻合此配置：[matlab/runtime/controller_options_dl1018.m](../../../matlab/runtime/controller_options_dl1018.m)，SHA256 `93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1`，其中 B case 保留默认开启的位置 RBF，P_A case 明确关闭 `rbf_position_output_enabled` 与 `rbf_position_update_enabled`；[position_only_search_options.m](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_options.m)，SHA256 `4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf`，从 P_A 构造候选，再附加 position-only DSSM Head。B 的实际运行侧车因此比此前源代码条件审计中的“B2-BS 且无额外补偿”更具体；该条件结论不适用于这里的三条 formal RBF baseline 记录。候选位置 Head 在 0.320 s 才首次更新，0.330 s 才有新 Head 输出。由此确定的是**预期方法对照导致的首个差异**；它只定位最早分叉，不能证明该差异解释 W15 的总体误差，也不能仅凭初始幅值排除长时闭环累积影响。

## PCF-on 与 R3 的首个分叉

三场在 0.320 s 的同一 Head 事件上，位置特征、更新前权重及输出一致；R3 将 eta mask 从 PCF-on 的三轴改为 [1,1,0] 后，首个更新坐标/权重差异只在 Z。Z 轴 Head 输出在 0.330 s 首次分叉，完整状态在 0.331 s 首次分叉。依照 position_stage1_update_head_pcf_v3_5 的输出先于更新顺序，对记录输入离线重算权重更新，与 MAT 中更新后权重一致；用更新权重重算 0.330 s 输出，误差约 \(10^{-17}\)。这验证 mask 按设定进入控制链，**不构成其对闭环误差有利的因果证明**。

在这三场、固定 12 场筛查中的 W15 子组，R3 的场景宏平均 Q 为 8.977088 mm，B 为 8.628703 mm（R3 高 0.348385 mm）；PCF-on 为 8.984548 mm，R3 相对 PCF-on 仅低 0.007459 mm。R3 与 PCF-on 的 X RMSE 分别为 6.836015 与 6.837031 mm，都比 B 的 5.738941 mm 高约 1.097 mm。故 R3 的 z-mask 几乎未动 X 差距，筛查门 G4 仍失败。此处仅为三场固定筛查，不代表全六场 W15 或独立测试结论。

## 代码审查结论与残余风险

- position_bs_step.m:17-27 的误差、名义加速度和力级补偿方向与日志单位/符号一致；20 ms B−R3 固定状态回算已复核名义力相同且命令差等于 B 补偿力的负值。
- position_stage1_update_head.m:8-15 与 position_stage1_update_head_pcf_v3_5.m:8-15 显示事件输出使用更新前权重，随后才进行 eta 协调更新、泄漏与盒投影；与 0.320→0.330 s 日志一致。
- position_filter_realization_pcf_step_v3_5.m:13-21 中 PCF 重构量是按推力和滤波姿态得到的加速度与请求加速度之差，不是实际 Plant 加速度误差。command_filter_step.m:14-24、vehicle_derivative.m:31-38 与 rk4_vehicle_step.m:13-17 显示滤波/姿态/电机限幅之后的真实闭环还包含多级动力学与积分。
- B 三份 run_start 已确认位置 RBF 输出/更新均开启；R3 的 P_A 源码确认位置 RBF 关闭、Head 接管。不是所有 raw MAT 都嵌入完整数值 cfg，R3 runIdentity 也不含全部运行参数，故仍不能声称完整控制/Plant 参数、来源哈希与电机分配链逐项一致。
- 审查范围内未发现可确认的计算方向错误或其他可行动代码缺陷。已确认的 B RBF 与候选 P_A/DSSM 路径差异是任务定义的控制器替换；尚未解释的是该方法替换及 PCF-on 控制链如何累计成 X 轴和 W15 Q 差距。现有轨迹对比不是整个闭环上的组件反事实。

## 主审决定

研发轮次已达 3/3，R3 固定筛查的 W15 子门失败，72 场扩展未授权；完整部署理论门未通过。**停止新增闭环运行，TEST48 继续封存，不宣称论文证据包达标。** 若未来另行批准新的预算周期，第一项应是先审计完整配置/源码身份，再对同一 W15 状态做离线逐级重放（位置名义力与补偿 → 姿态/推力目标 → 命令滤波 → 姿态力矩 → 广义量与电机请求）；只有离线链路能无歧义复建，才编制新的单因素任务书。真实 Plant 量只用于离线诊断，不进入部署输入。

范围与代理边界：离线变量审计按任务书指定的九个 W15 raw_run、六个配对 run_start sidecar、列明源码与既有身份/评分表执行；未扩大目录范围。该代理报告字段重算结果，主会话交叉核对源码方程、已有身份表与指标；分析模型/速度档位无法由工具独立证明。本审计未读取 PCF-off、TEST、新场景或模型文件，不运行实验，不修改原始产物。
