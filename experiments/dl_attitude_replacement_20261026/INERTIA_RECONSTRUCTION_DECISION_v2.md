# 姿态 RBF 替代：深度学习与惯量重建的取舍

日期：2026-10-26（Asia/Shanghai）

## 决定

深度学习作为主候选；运行时不做时变惯量重建，也不估计 `Jdot`，不加显式 observer。TCN 用 B 的姿态 RBF 动作作离线教师，部署时只用冻结模型。保留 C5/B 控制器原有固定名义惯量 `J0`，只将 TCN 预测的角加速度等效动作映射成力矩；`J0` 不随形态变化。这属于原 RBF 执行接口的一部分，不是 `Jhat/Jdot_hat` 形态估计。

本轮 TCN 输入固定为 13 维：wrapped 姿态误差 3、机体系角速度 3、BS 名义机体系力矩 3、四个当前形态命令。监督标签为 B 原始日志中的 `rbf_output_raw`，在姿态事件时刻记录、单位 rad/s²、位于 beta 之前且已受原输出上限约束。输入、目标均不读取 Plant 真值、惯量重建量或 RBF 隐状态。相对先前 TCN 草案，正式实现以 Amendment 02 的力矩输入约定为准；v2 runner 的角加速度/力矩错位已在隔离 v3 runner 中修正并通过 MATLAB 无 Plant 静态审核。

## 对现有物理前馈证据的审计

GHP7 全量 pilot 评分表包含 54 次调用、6 个场景，不是 DEV72。该 pilot 已经把同一惯量前馈加到 RBF 上：`C5_RBF_F` 对 `C5_RBF` 的 Q0–20、Q8–12、SO(3) 宏平均都更低，配对胜数分别是 5/6、5/6、3/6。说明“把惯量前馈用于 RBF”确实试过，而且小样本下改善了均值。

该 pilot 中最佳 C5_10 为“只开命令驱动惯量前馈、关 RBF 和 observer”。它在 6 场均可行，Q0–20 宏平均 11.978 mm、SO(3) 宏平均 62.913 mrad；B 分别为 20.219 mm、83.849 mrad。C5_10 对 B 的场景胜数为 Q 5/6、SO(3) 4/6；相对 `C5_RBF`，其 Q0–20 与 Q8–12 六场全胜，SO(3) 胜 4/6。W00/W12 各 3 场，没有 W15，也没有独立测试。

因此该结果说明精确质量几何模型加理想形态命令跟踪在当前仿真里是有力的物理前馈参照；它不证明 TCN 有同样收益，也不证明全 DEV72 或 TEST 表现。C5_11（额外加入有界 observer）没有胜过同样带前馈的 RBF 对照，当前没有证据支持扩展该 observer 方案。此前把物理方法描述成“72 场整体优于 B”不准确，应以这份 6 场审计为准。

## 后续比较口径

1. 先让修正监督的 TCN 完成训练和 MATLAB/Python parity、运行接口与安全检查；旧残差标签训练只保留作诊断。
2. 在同一 6 个 GHP7 scene payload 上比较 TCN、原 B、C5_RBF 与已完成的 C5_10 物理前馈结果。复用 B/C5 和物理候选 raw，不再启动这些对照；报告每场位置 Q、SO(3)、可行性、饱和/限幅与配对差。
3. TCN 主候选不拼接惯量前馈。若它在小样本安全和因果门通过，再按冻结任务书扩展 DEV；沿用已有 B/C5 基线，TEST 继续封存。不能把六场 pilot 当作完整性能结论。
4. 若 TCN 单独不能达到目标，再依据证据决定是否另立“TCN + 命令驱动物理前馈”的新候选；它必须作为独立物理信息方法与 TCN-only、C5_RBF 和 B 对照，不能把前馈收益归功于网络。

## 公平性与适用边界

命令积分和已知质量几何模型不是直接读取 Plant 真值，但它们利用了精确形态动力学先验，并假设命令被理想跟踪。在实际臂长反馈不可用或存在滞后时，`Jhat/Jdot_hat` 可能偏离真实值。因此保留其现有 pilot 结果作模型前馈诊断，不把它作为 TCN 主路线的运行时依赖。

当前 TCN 也使用四个已知形态命令，因此实验结论仍只覆盖理想命令跟踪的仿真条件；这不等于证明了真实硬件的形态估计或鲁棒性。若将来硬件只提供臂长传感器，则必须以可部署测量重新定义输入并另做验证，不能用 Plant 的 `rho_true` 替代。

## 2026-10-26 无 Plant 接口核验

MATLAB R2025b 的 `smoke_tcn_teacher_runtime_no_plant_v1` 通过：登记映射显示 DL_TCN 不开 RBF 输出/更新、惯量重建、observer 或物理前馈；合成权重验证了 13 维输入经固定 `J0` 映射为限幅力矩。完整输出及运行时源码哈希见 `MATLAB_NO_PLANT_TCN_STEP_SMOKE_v1.json`。该 smoke 只验证接口和单位换算，不代表训练模型性能或闭环结果。

`score_tcn_ghp7_pilot_v2.m` 已增加 C5_10 对照绑定：冻结的物理参照清单须匹配同一组六个场景、payload、`R_task` 与原始文件哈希；评分输出逐场报告 TCN 对 B、C5_RBF、C5_10 的位置与 SO(3) 比较。B、C5_RBF、C5_10 原始结果复用，不重跑。该配对评分仍须等 TCN 训练、parity 及六场候选航次完成后生成。

对既有 B/C5_RBF/C5_10 的六场比较已直接重读 raw、校验文件 SHA，并独立重算 Q0–20、Q8–12 和 SO(3)；重算值与清单在 `1e-10` 容差内一致。汇总如下：

| 方法 | Q0–20 (mm) | Q8–12 (mm) | SO(3) RMSE (mrad) | 可行场景 |
|---|---:|---:|---:|---:|
| B | 20.2193 | 33.2685 | 83.8494 | 4/6 |
| C5_RBF | 12.9352 | 17.6064 | 65.6020 | 5/6 |
| C5_10 物理前馈 | 11.9785 | 14.7797 | 62.9132 | 6/6 |

C5_10 对 B 的位置/姿态配对胜数为 5/6、4/6；对 C5_RBF 为 6/6、4/6。范围仍只有 G1/G2/G3 × W00/W12 六场，没有 W15、DEV72 或 TEST48。逐场表和 raw 重算脚本为 `C5_10_PHYSICS_PAIRED_COMPARISON_v1.csv/json`、`matlab/audit_c5_10_physics_comparison_v1.m`。

原 C5_RBF 的 `DL1018_GHP7_G1_W00` 完成标志误报已确认为实现错误。该 raw 和 run-status 绑定 source-lock v4；其完整性条件写成 `n=N-1; last==n-1`，把完整的 `last=n=20,000` 错判为不完整。raw 实有 20,001 个状态样本、20,000 个转移，状态和转移全部有限，status 为 `COMPLETED/STABLE`，无安全停止。其余 5 场 C5_RBF 和 6 场 C5_10 使用 v5 的 `last==n` 条件。历史标记保留 false；逐 raw 指标仍可用，但这个日志缺陷在任何表格中都要披露。证据见 `C5_RBF_COMPLETION_FLAG_ROOT_CAUSE_v1.json` 和 `matlab/audit_c5_rbf_completion_marker_v1.m`。

## 2026-10-26 v4 候选运行链：惯量输入边界复核

本节是对隔离 `pilot_runner_v4_teacher_distill` 源码的只读静态追踪；没有启动 Plant、闭环航次或读取 TEST。

- 在 `matlab/runtime/run_gate_holdout_closed_loop.m:1114-1120`，`Ptrue` 单独由 Plant 真值构造；正式 RBF-BS 配置走 `P=fixedController`，随后断言控制器形态为 `fixed` 且臂长等于初始名义臂长。`controller_parameters.m:34-78` 的固定分支把 arm rates 设为零，并由此生成固定惯量及其零形态变化率；`attitude_bs_step.m:34-41` 因而用固定 \(J_0\)，不加入时变 \(\dot J\) 项。
- `run_gate_holdout_closed_loop.m:2377-2394` 的 TCN 输入只有：姿态误差 3 维、机体系角速度 3 维、固定模型下 BS 名义力矩 3 维、形态命令 4 维。代码没有把 `Ptrue`、真实臂长、重建的 \(\hat J\) 或 \(\dot{\hat J}\) 接入特征。
- `tcn_attitude_step_v1.m:10-26` 仅接收该 13 维特征、冻结的 \(J_0\)、beta 与输出限幅；输出力矩按 `J0 * (beta * clipped)` 映射。这里仍然使用固定名义惯量模型，准确表述应是“去掉时变惯量重建”，不能写成“完全不使用惯量模型”。
- Plant 侧 `vehicle_derivative.m:35-36` 仍按 Plant 参数中的时变惯量和惯量变化率计算动力学。这是被控对象的仿真方程；源码链路未将其回灌给 TCN 输入。该结论限定于当前隔离候选源码和理想仿真接口。

核验源码 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `run_gate_holdout_closed_loop.m` | `EC6F41038D1643D1A6795BC3117C093A02FDC20F34C8B86E6E5D83B9580F7A9A` |
| `controller_parameters.m` | `4FAD5E78C0BD4177461647AF167E7C86A7DEFA628B43D523B0B7DA2EF5556398` |
| `arm_mass_properties.m` | `8EC66E107156B5219F7E41ACA2464EEF1EC8043EB7F67DF313C0F23EF4B551F5` |
| `distributed_mass_properties.m` | `DB380B506E4BACC37BC398D5726C5EBD25BE8EBC08B6C9E76FF59BC78FD45D3A` |
| `attitude_bs_step.m` | `CF6B20FFC4DF2625D9316A80340D69542E380D14FEAED66EF8498E793FDACCBC` |
| `tcn_attitude_step_v1.m` | `9EC27DC1A9226C7F64ACD26F1D0E8173FB0E1AABFB3D67D51318ABA66122F130` |
| `tcn_attitude_forward_v1.m` | `193C288D33AD213AA57F40DB4795A3D1F0898CCF5F678E7854CCF925CB6FF3CC` |
| `vehicle_derivative.m` | `C3258DD5B70268D1465CA7701855B065244AEBFAF5816C85E959D39015CD2786` |
| `bind_paired_fixed_j0.m` | `99F0304EB44CF5AB419560FC1A7D63E732B3A71FB843CA03E3AAC9AB84EFECCE` |

- 替代接口也经源码确认：`gate_attitude_arm_spec('DL_TCN')` 将 `rbf_enabled`、物理前馈和 observer 设为 false；`make_paired_c5_options.m` 对候选关闭 `rbf_attitude_enabled`、`rbf_attitude_output_enabled`、`rbf_attitude_update_enabled`；闭环 runner 在 TCN 分支直接使用 TCN 力矩，不进入姿态 RBF 更新分支。源文件哈希：`gate_attitude_arm_spec.m` = `C1808F06278DAA26E7DB53C09F690CFABD9C2CE7524547F6EE793754A7373478`；`make_paired_c5_options.m` = `543E2AE9163BDDDFACE3F1032EA2BFA1DEB71E2D1BC1A48811142A696AC3029F`。

