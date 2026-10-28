# 物理惯量前馈与力矩等效扰动观测器：修订设计审查 v2

日期：2026-10-25。状态：只读源码审查和任务书草案；未改控制代码、未训练、未运行 Plant/航次，未读取 TEST、MAT 或 raw。v2 修正 v1 对 RBF 限幅单位和 observer 输入力矩来源的误述；v1 留存供审计。

## 决策与失败证据

下一条优先路线是“命令重建形态的惯量前馈 + 力矩等效扰动观测器”，替换姿态 RBF 补偿。它只检验显式惯量/惯量变化前馈与合扰动估计是否适合当前任务，不预设成功。已有屏查显示 C5_24 对同栈 C5+在线 RBF 的 Q 与 SO(3) 都仅 2/12 场胜；C5_COVERAGE33 为 Q 3/15、SO(3) 1/15 场胜。固定 CM18 的 TRAIN/DEV NRMSE 是 0.015295/0.267078，DEV/TRAIN=17.46；教师首个形变事件上的标签向量 RMSE 为 0.897 rad/s²。它们支持测试另一机制，不能证明失效由惯量项单独造成。

## 源码模型、符号与单位

Plant 的机体系转动方程是

\[
J(\rho)\dot\omega+\omega\times[J(\rho)\omega]+\dot J(\rho,\dot\rho)\omega
=\tau_{act}+\tau_{wind}.
\]

`J` 单位 kg·m²，`Jdot` kg·m²/s，`omega` rad/s，角加速度 rad/s²，广义力矩和风矩 N·m。现有反步使用固定 `J0`，`attitude_bs_step` 先求 body-frame `alphaBS`，再构成 `Mnom=J0*alphaBS+omega×(J0*omega)`，最后按 `rawMoment=Mnom−estimateTorque` 输出。姿态 RBF 6 维输入为 `[eφ,sφ,eθ,sθ,eψ,sψ]`，分别是 rad 与 rad/s；该候选不复用这些特征或 RBF 权重。

正式 `B2-RBF-Full-SPLIT` 基线的 RBF 通道不是直接 torque 输出：`rbf_mimo_update` 先把 `datt` 按 `cfg.rbf.attitude.dmax=[45,45,4.7124]` 分轴限幅，单位 rad/s²；运行时再乘 `beta=min(k*dt/2.2 s,1)`，最后乘 `P.inertia=J0` 得到 N·m 补偿。因此候选不把该 dmax 写成 torque 限值。若 `J0` 非对角，等效 torque 可行集是 `J0*[-dmax,+dmax]` 的映射集合，轴向裁剪发生在 body-axis acceleration-equivalent 坐标，不能把矩阵乘积误解成逐 torque 轴对角限幅。

离线 C* 标签仍是加速度目标：`G*C*=E0`，其中 `G=J^{-1}{C(rho)C0^{-1}[0;J0]}_torque`，`E0=J^{-1}(wrench0_tau+tauwind−omega×Jomega−Jdot*omega)−alphaBS`；训练目标为 `C*/beta`，应用时乘 `J0` 才是力矩。它依赖 Plant 真形态/风，只用于离线标签，禁止作为部署输入。

## 唯一候选、因果残差与接口

以当前命令维护独立形态估计。场景的 1 ms command 语义是 `rhodot=.05*u`，`u∈{-1,0,1}`，`rho∈[.15,.25] m`。在采样 `j` 当前命令已到达后，估计速率为 `rhodothat_j=.05*u_j`；区间结束更新 `rhohat_{j+1}=clip(rhohat_j+.001*.05*u_j,.15,.25)`。候选从该估计几何计算 `Jhat,Jdothat`，不读场景里的静态 `rho_hat`，更不读 `rho_true`。

姿态物理前馈（N·m）为

\[
\tau_{shape,j}=(\hat J_j-J_0)\alpha_{BS,j}
+\omega_j\times[(\hat J_j-J_0)\omega_j]+\dot{\hat J}_j\omega_j.
\]

observer 不要求实际 torque telemetry。每个 100 Hz 姿态事件 `e` 使用刚完成的区间 `[t_{e-1},t_e]`，区间长度严格取 scheduler 的 `Delta_e=t_e−t_{e-1}`。Plant 每 1 ms 步记录的 controller-clipped 广义力矩命令记为 `tau_cmd_j=a.clipped_generalized(2:4)`；它在 `allocate_control` 中仅由请求与 controller limits 得到，位于 C0 电机分配/电机饱和之前，**是发给分配器的 N·m 命令，不是实际/已施加力矩**。区间命令均值按时间戳累计：`tau_cmd_bar_e=(1/Delta_e)∑_{j∈[e−1,e)} dt*tau_cmd_j`。

用角动量差分吸收时变惯量项。令 `Lhat=d(Jhat*omega)/dt + omega×(Jhat*omega)`，按 1 ms 样本对叉乘项做梯形求积，则刚结束区间的 N·m 残差为

\[
r_{\tau,e}=\frac{\hat J_e\omega_e-\hat J_{e-1}\omega_{e-1}}{\Delta_e}
+\frac{1}{\Delta_e}\int_{t_{e-1}}^{t_e}\omega\times(\hat J\omega)\,dt
-\bar\tau_{cmd,e}.
\]

积分只使用已完成区间的角速度样本、命令重建的 `Jhat` 轨迹和已保存命令。其定义等价于区间合扰动近似：`(tau_act−tau_cmd)+tau_wind+(Lhat−Ltrue)`。风、实际 actuator/C0→C(rho) 分配误差、命令跟踪误差及惯量模型误差一起进入 lumped residual；这些量不被分别识别，也不作为观测器输入。用 nominal-inertia 等效加速度状态更新：

\[
r_{a,e}=J_0^{-1}r_{\tau,e},\qquad
\hat d_{a,e}=\operatorname{Proj}_{[-d_{max},d_{max}]}
\{(1-\gamma_e)\hat d_{a,e-1}+\gamma_e r_{a,e}\},
\quad \gamma_e=1-e^{-\Delta_e/0.10s},\quad \hat d_{\tau,e}=J_0\hat d_{a,e}.
\]

`dhat_a` 单位 rad/s²，`dhat_tau` N·m；`J0\r_tau` 是矩阵求解，输出三通道按 body x/y/z 的加速度等效坐标解释。初值为零，投影界用匹配基线的 `cfg.rbf.attitude.dmax`，不是 torque 界。

每个 1 ms 控制步形成净额外加速度等效补偿并沿用基线软启动/限幅坐标：

\[
a_{extra,j}=\operatorname{clip}_{\pm d_{max}}\{J_0^{-1}(\tau_{shape,j}-\hat d_{\tau,e})\},\quad
\tau_{comp,j}=J_0\,[\beta_j a_{extra,j}],\quad
\beta_j=\min(k\,dt/2.2s,1).
\]

由于现有端口按 `Mnom−estimateTorque` 工作，传入 `estimateTorque_j=−tau_comp,j` 才得到 `Mnom+tau_comp,j`。这里负号只是在复用减法端口；该输入不应被误记成物理扰动估计。候选对 attitude RBF 输出/更新均关闭，姿态 helper 之外 C5 位置栈、反步名义项、C0 分配、执行器和安全限幅不变。

## 因果可用性核验与审查边界

已从冻结代码确认 C5 DEV 仿真输入可因果取得并对齐：`make_scenes_dl1018` 以 `t=(0:.001:20)'` 建场景，按 `rhoDotTrue(k)` 写 `command(k)=rhoDotTrue(k)/.05`，随后积分出下一采样形态；`run_dl1018_closed_loop` 断言场景时间差等于 `cfg.plant.dt=.001`，每轮以同一索引 `k` 访问 `s.arms.command(k,:)`，随后控制/分配并从 `x(k)` 推进到 `x(k+1)`。100 Hz scheduler 返回真实 event time 与 `dtUpdate`。因此在 event `e` 更新时上一 event 区间已完成；当前 `u_k` 只供当前/后续形态估计，不得回填到上一区间。当前场景的 `rho_hat` 字段确实静态，不可用来冒充估计。此确认针对预设仿真命令，不证明实机舵机/滑臂按命令速率精确跟踪。

允许 observer/helper 接口：当前/历史 body-rate、相应时戳、当前与历史已发形态命令、`cfg` 中冻结的 `J0` 与控制参数、`tau_cmd_j` 缓冲、`dhat_a`、`rhohat`。明确禁止接口含 `Ptrue`、`rho_true`、风矩、`realized_generalized`、Plant 导数。`allocate_control` 的 `info.clipped_generalized` 可作为只读的 controller-side command，因为该字段等于 controller 侧通用限幅；其同一返回体中的 `actualGeneralized`/`wrenchNow` 不得传入 observer。实现前要求对这一字段做静态数据血缘复核。

投影只保证 observer 状态数值有界；LPF 不保证估计误差收敛，合扰动可能随饱和、命令或执行器延迟快速变化。物理前馈误差、差分噪声及采样延迟也可能让候选更差。代数恒等、无 Plant 合成检查或有限 DEV 成功都不能推出渐近稳定、ISS、实际硬件稳定或 TEST 泛化；本方案没有 Lyapunov 证明。

## 最小验证提纲

先做纯合成无 Plant 检查：用人工 SPD 矩阵、命令、`omega` 和 `alphaBS` 验证 `(Mnom+tau_shape)` 对应的理想刚体方程符号闭合；构造已知区间合扰动，确认角动量差分残差及 `J0\r_tau` 坐标映射；逐项核对 N·m 与 rad/s²；扰动未来命令后确认过去 `rhohat/Jhat/r_tau` 不变；检查 projection、beta、全有限和事件时间戳。任一失败不进入 Plant DEV。

随后三场 DEV 成对 fresh-run：`DL1018_DEV_T1_C00_W03`（HELIX、无形变、有风）、`DL1018_DEV_T2_C02_W15`（FIG8_3D、单臂形变、W15 零风）、`DL1018_DEV_T3_C10_W11`（SQUARE、C10 对应拓扑 34，即臂 3/4 形变，有风）。严格按统一任务书运行 C5 position + online attitude RBF 与候选，各场各两支；只换姿态 compensation。最终是否放行以独立任务书为准。

## 已读取文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `matlab/core/vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| `matlab/core/allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| `matlab/runtime/run_dl1018_closed_loop.m` | `9f6b436c8247c49783ec04ef326b20fc5d7de2870c9ab972212a0b2e4c432bc2` |
| `matlab/runtime/controller_options_dl1018.m` | `93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1` |
| `matlab/runtime/prepare_effective_config_dl1018.m` | `d7530b4088cd1255093c36c70d033eeef010efd3ab92b5c86defc64f66652d3d` |
| `matlab/core/default_config.m` | `685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51` |
| `matlab/scenes/make_scenes_dl1018.m` | `7d11b4ebf63105b016c67f4b3c427282b35dafa53280ef2daf5578a6a16bb9ec` |
| `matlab/core/tcn0916_morphology_scenario.m` | `711a87e01e616ee141f9068a8c4e31758dc328ade3f692e1a92a5de723d30438` |
| `matlab/core/tcn0916_topologies.m` | `3fd341fa2292c8118f8b363611671677517c44009550bdf82e96cd751e6dce5f` |
| `matlab/core/rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| `matlab/core/simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| `matlab/core/arm_mass_properties.m` | `8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5` |
| `matlab/core/rbf_mimo_update.m` | `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a` |
| `matlab/data/export_attitude_events_dl1018.m` | `baeca25a27ee411e900d38333c888a91aa7ce2c5a17ad58cc6989f7aea684141` |
| `matlab/data/attitude_events_source_v311.m` | `a97bc8585e916e7fc78651200eaf2ae04e4a90ce575865ce5fa7989f52f94792` |
| `matlab/core/allocation_matrix.m` | `5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d` |
| `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_ROOT_CAUSE_DIAGNOSIS_v1_ZH.md` | `d564d77133e2752d327450c9cedb5d7c3d946c1988dc58fc7720fa39b25d4894` |
| `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md` | `41c38fe91ff121be1853826db94e830ad4c3a76ebee8623bcab0de5cd6a2a3c3` |
| `reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md` | `934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017` |
| `reports/attitude_cm18_c524_coverage33_20261025/physics_replacement_design_v1/ATTITUDE_NONRBF_PHYS_COMPENSATOR_DESIGN_v1_ZH.md` | `1608ebc98ee4a2495aefbf5c2018f92968a7492c79a57c83a06b067035abb6c8` |

