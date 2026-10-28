# C5 位置环与姿态有限时域理论证据矩阵

日期：2026-10-27。只读冻结计划、理论材料与源码；未读取 TEST 数组/raw，未运行 MATLAB、Plant、训练或实验，也未修改控制代码。

## 结论

原 72 小时计划要求“稳定性或误差界”，不要求全局渐近稳定。2026-10-22 的执行记录当时判理论门未过；后续主审在 2026-10-23 接受了**实际 C5 延迟预测/tracking/leak/投影对应的有限路径条件误差界**，并核过 72 条已完成 DEV 路径。这个窄范围满足数学命题门；它不等于 C5 的先验部署稳定性/域不变性证明，也不改变全局论文 `NOT_QUALIFIED`、TEST 未放行的状态。

| 原要求 / 现有证据 | 实际方程与可成立范围 | 仍缺什么；最小补证 |
|---|---|---|
| **原计划：**理论与贡献审核必须通过；当时定义为稳定性或误差界，无需全局稳定。`reports/paper14_v2/README_EXECUTION_ZH.md:3–5,19`；`reports/paper14_v2/QUALIFICATION_AUDIT_MATRIX_20261022.md:39`。**后续裁决：**有限路径条件误差界在该数学标准下通过，但整体论文仍未合格。`reports/paper_continuation_20261023/THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md:3–5,16–24` | 这是后续对原数学要求的收窄验收：证明给定路径上的界，不承诺从初态预测未来误差或误差衰减。全局/部署稳定、优于 B、参数收敛都不是已证结论。 | 不需要再补全局稳定证明来满足“有误差界”这一窄命题。若论文要声称候选在运行前有保证，最小缺口是从冻结初值与参数导出其路径项的先验界/适用域，而不是把已完成 raw 的最大值称为先验界。 |
| **C5 位置 BS 与 PCF。**实际位置律为 `a_nom = r̈ + K1·(ṙ−v) + K1²e + K2s`，`F_cmd=P.mass·a_nom−residualForce`；源码 `matlab/core/position_bs_step.m:17–27,52–62`。PCF 用命令重构加速度 `a_F` 得 `r_F=a_req−a_F`，并以精确指数保持递推 `eta⁺=exp(−k2dt)eta + ((1−exp(−k2dt))/k2)r_F`；`matlab/models/position_filter_realization_pcf_step_v3_5.m:13–22`。 | C5 位置物理引理将物理加速度误差写成 `epsilon_M + M r_F`，保留位置/速度采样余项及指数 PCF 相对 Euler 的余项。`reports/paper_continuation_20261023/physical_residual_tracking_lemma/PHYSICAL_RESIDUAL_TRACKING_LEMMA_ZH.md:12–21,25–56,58–92`。PCF 状态界仍以 `r_F` 有界为条件；helper 只做有限值检查，不给幅值界。 | 位置误差结论可以使用命令重构与实际相邻速度差形成的物理残差；若要把姿态界代入，需额外把姿态跟踪/力轴方向误差映射为这个位置残差的显式界。单有 `eta` 有界或姿态面界不够。 |
| **C5 在线 Head + 1 s 延迟预测项。**当前运行入口要求 X14、32事件上下文、1 kHz Plant / 100 Hz Head、gamma=12、PCF 与 `[1,1,0]` mask；`experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m:705–727`。目标是在 10 ms 完整区间结束时，用速度增量减去积分的预测参考加速度，再除以 0.01；`.../run_dl1018_closed_loop.m:2022–2044,2256–2270`。 | 实际 helper 对当前事件用 `raw=Wᵀphi`、`applied=beta·clip(raw,±3)`；然后按旧特征/旧标签 `phi_prev·(Wᵀphi_prev−y_prev)ᵀ` 加入 tracking/leak 更新，`rho=0.01=h_event/tau`、`tau=1 s`，最后作一次逐元素 `[-60,60]` 盒投影。首个 ready 事件没有旧标签梯度。`experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m:3–5,26–46`。 | `BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md:7–27,31–59,65–100` 已保留实际延迟索引、标签损失、tracking/leak、projection、beta/output clipping 与 PCF forcing，并桥接到位置 Q 的有限路径界。它依赖逐路径预测损失、目标/裁剪/ramp/forcing 等数值；不推出这些量在任意未来闭环中统一有界。最小论文补充是把所用路径项与 72 raw 实例化作为**后验路径证据**报告，并明确双精度容差不是严格区间认证。 |
| **姿态条件有限时域界。**固定 `J0`、`Jdot_BS=0`，完整 ZYX `T,Tdot` 与 BS 符号、1 ms 离散递推、100 Hz 的 beta/hold 已在 `reports/attitude_ncmd_error_bound_20261027_v1/DERIVATION.md:5–19,21–58,60–109,111–129` 给出；源码映射在 `ASSUMPTIONS_AND_CODE_MAP.md:7–19`。 | 在 Euler chart 不奇异（pitch clamp 不激活、wrapped branch 不跳）、`||T||`、模型残差 `epsilon_k` 与离散余项 `chi_k` 于有限时域有界时，`||x_n|| ≤ q̄^N||x_{n−N}|| + hΣq̄^{n−1−i}(t_*||T_i||||epsilon_i||+||chi_i||)`，`q̄=0.998701<1`。T1 数值检查验证的是 C5 teacher raw 上的离散符号/采样/时钟，不是 GRU 预测精度或稳定裕量。 | 该姿态界不能直接推出位置误差界：它的 `epsilon_k` 是 body-rate command-port 残差；位置定理需要 `epsilon_M+M r_F`、参考/Plant 采样余项。二者之间还隔着姿态到推力方向/加速度的非线性映射、推力/倾角和分配限幅、滤波及外环状态依赖。现有材料明确列出缺少外环 ISS/Lyapunov、force-to-Euler 有界正规映射、cascade/small-gain 与安全域不变性。`DERIVATION.md:131–133`。 |

## 若要写“位置–姿态级联”结论，最小额外命题

在一个明确共同的紧运行域内，给出并验证一个有限时域离散级联不等式：把姿态误差与命令端口残差通过实际 `thrust/force → filtered Euler → allocation/Plant` 映射，界定为位置物理引理所需的 `epsilon_M`、`r_F`、`rho_p/rho_s`；同时把位置误差引起的姿态参考变化作为反向耦合项纳入。对同一组常数证明离散有限时域增益/小增益闭合，或明确检查两层的适用域直到退出时刻。推力、倾角、执行器饱和及 pitch/wrap chart 边界需在该域内处理。

若无法从冻结方程给出共同域与上述映射界，最小诚实表述是并列陈述“位置有限路径误差界”和“姿态条件有限时域界”，不把它们相加成整机闭环保证。不能用投影权重有界、有限航次未发散、训练损失或 PE 替代上述桥接条件；也不需要移植其他控制器的定理。

## 可复核来源

- 原计划/状态：`reports/paper14_v2/README_EXECUTION_ZH.md:3–5,19`；`reports/paper14_v2/QUALIFICATION_AUDIT_MATRIX_20261022.md:39`。
- 位置命题验收与实证范围：`reports/paper_continuation_20261023/THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md:3–24,26–28`；`reports/paper_continuation_20261023/BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md:7–27,31–59,65–100`。
- 位置物理/PCF 采样关系：`reports/paper_continuation_20261023/physical_residual_tracking_lemma/PHYSICAL_RESIDUAL_TRACKING_LEMMA_ZH.md:12–21,25–56,58–92`。
- 实际 C5 方程：`matlab/core/position_bs_step.m:17–27,52–62`；`matlab/models/position_filter_realization_pcf_step_v3_5.m:13–22`；`experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m:2022–2044,2256–2270`；`experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m:3–5,26–46`。
- 姿态条件界：`reports/attitude_ncmd_error_bound_20261027_v1/DERIVATION.md:5–19,21–58,60–109,111–133`；`reports/attitude_ncmd_error_bound_20261027_v1/ASSUMPTIONS_AND_CODE_MAP.md:7–19,37–44`。
