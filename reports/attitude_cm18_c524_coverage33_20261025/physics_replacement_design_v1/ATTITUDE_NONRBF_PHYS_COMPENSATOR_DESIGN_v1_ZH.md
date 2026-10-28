# 姿态环非 RBF 物理补偿候选：设计审查 v1

日期：2026-10-25。范围：只读冻结源码和已有报告；未改代码、未训练、未启动 Plant/航次，未读取 TEST、MAT 或 raw。

## 结论与已知失败边界

只建议一个候选：在原反步姿态环外，用命令侧形态估计计算惯量/惯量变化前馈，再用三轴一阶有界扰动状态估计器补偿剩余力矩。它测试“显式补偿已知形态惯量项、把风和模型误差作为慢变合扰动估计”是否比静态标签回归更适合当前任务；它不预设成功。

选择它的理由是已冻结静态 CM18 证据偏弱：C5_24 对同栈 C5+RBF 的 Q 和 SO(3) 都是 2/12 场胜；C5_COVERAGE33 是 Q 3/15、SO(3) 1/15 场胜，未达到扩大 DEV 的门槛。Coverage33 固定模型 TRAIN/DEV NRMSE 为 0.015295/0.267078，DEV/TRAIN=17.46；首个形变事件教师状态上的标签误差向量 RMSE 已为 0.897 rad/s²。它们支持继续检验另一种机制，不证明失败由形态惯量漏项单独造成。

## 冻结方程、标签和单位

Plant 的机体系刚体方程为

\[
J(\rho)\dot\omega=\tau_{\rm applied}+\tau_{\rm wind}-\omega\times[J(\rho)\omega]-\dot J(\rho,\dot\rho)\omega.
\]

`vehicle_derivative` 使用 `J`（kg·m²）、`Jdot`（kg·m²/s）、角速度（rad/s）和力矩（N·m）；`distributed_v1` 忽略额外内部变形动量项。固定名义姿态环中 `Jdot0=0`，`attitude_bs_step` 构成 `Mnom=J0·alphaBS+omega×(J0·omega)`，再严格按 `rawMoment=Mnom−estimateTorque` 生成请求力矩。`alphaBS` 是反步虚拟的机体系角加速度（rad/s²）；`estimateTorque` 是力矩（N·m）。

C* 不是力矩坐标。冻结 relabeler 定义 `L=[0;J0]`、
\[
G=J^{-1}\{C(\rho)C_0^{-1}L\}_{\rm torque},\quad
E_0=J^{-1}(wrench_{0,\tau}+\tau_{wind}-\omega\times J\omega-\dot J\omega)-\alpha_{BS},
\]
`G·C*=E0`、`beta=min(k·dt/2.2 s,1)`、训练目标 `C*/beta`。`C*` 与目标均为加速度量（rad/s²）；`G` 无量纲。应用时加速度补偿 `beta·clip(C*/beta)` 乘 `J0` 才成为施加力矩（N·m）。该标签使用真实形态和风只用于离线构造，不能用于部署输入。

RBF 的 6 维输入严格为 `[eφ,sφ,eθ,sθ,eψ,sψ]`：误差 `e` 为 rad，反步面 `s` 为 rad/s。其 81 个高斯基函数使用缩放 `[0.6,4,0.6,4,0.6,3]`、`sigma=1.2`；100 Hz 事件上先用当前权重输出并限幅，再以限幅反步面更新权重，权重投影至 ±60。RBF 补偿直接进入 `estimateTorque` 接口，单位 N·m。候选会关掉 RBF 的输出和更新，不复用其基函数或在线权重。

冻结 C5 场景由 `make_scenes_dl1018` 调用预设形态生成器，指令速度为 0.05 m/s，范围 0.15–0.25 m，命令 `u∈{−1,0,+1}`，`rhodot=v·u` 并按 1 ms 前向积分限幅。场景文件当前把 `rho_hat` 固定在初值、`rhoDot_hat=0`；因此候选必须维护自己的命令侧状态，不能直接把这两个字段当成已跟踪真实形态。其因果更新是 `rhohat[k+1]=clip(rhohat[k]+0.001·0.05·u[k],0.15,0.25)`；当前时刻的 `rhohat[k]` 只积分到上一间隔，当前速率预测为 `rhodothat[k]=0.05·u[k]`。用冻结 `distributed_v1` 几何函数从这两个估计量计算 `Jhat,Jdothat`，单位分别为 kg·m²、kg·m²/s。

## 唯一优先候选和接口

期望的净补偿为
\[
\tau_{shape}[k]=(\hat J-J_0)\alpha_{BS}
+\omega\times[(\hat J-J_0)\omega]+\dot{\hat J}\omega,
\qquad q[k]=\operatorname{clip}_{\pm d_{max}}(\tau_{shape}[k]-\hat d[k]).
\]
这里 `tau_shape` 与 `dhat` 都是 N·m；`dhat` 表示风及被合并的执行器/模型差异。按现有函数的减号契约，将 `estimateTorque=dhat−tau_shape` 传给 `attitude_bs_step`，输出就是 `Mnom+q`。为保持试验范围单一，仍用原固定 `J0` 反步名义项、原 C5 位置栈、原 C0 分配器、执行器和限幅；不把控制器整体切成形态模式。

在 100 Hz 姿态事件 `k` 更新扰动估计，严格只用前一事件区间 `[k−1,k]` 的数据：
\[
r_{k-1}=\hat J_{k-1}\frac{\omega_k-\omega_{k-1}}{\Delta t}
+\omega_{k-1}\times(\hat J_{k-1}\omega_{k-1})
+\dot{\hat J}_{k-1}\omega_{k-1}-\bar\tau^{est}_{applied,k-1},
\]
\[
\hat d_k=\operatorname{Proj}_{\pm d_{max}}\{(1-\gamma)\hat d_{k-1}+\gamma r_{k-1}\},
\quad \gamma=1-e^{-\Delta t/0.10\,s},\quad \Delta t\simeq0.01\,s.
\]
`omega[k]` 来自当前角速度测量；有限差分表示刚结束的区间，不用当前命令的未来响应。`rhohat[k−1]`、`rhodothat[k−1]` 和上一间隔的力矩用于残差；更新后的 `dhat[k]` 与当前 `tau_shape[k]` 才用于当前请求。0.10 s 和现有 `dmax=[45,45,4.7124] N·m` 是单次筛查的预注册起始滤波/投影值，不是由数据选出的最优参数。

施加力矩来源是首要前置条件。合法候选是实际电机转速/转子速度 `Ωactual`（传感器或已确认的因果执行器状态）平方，与命令侧 `Ĉ(rhohat)` 组合：`tau_applied_hat = Ĉ_tau(rhohat)·(Ωactual.^2)`；跨一个事件周期按 1 ms 采样累计成 `bar_tau_est_applied`。不得读 `realized_generalized`：当前仿真代码以 Plant 的真值分配矩阵 `C(rho_true)` 计算它；也不得读 `rho_true`、风力矩或 Plant 导数。源码中的 `motorNow` 是由 setpoint 和可选电机时间常数计算的模拟量，`allocated_generalized` 用固定 C0 重构，二者都不是硬件测得力矩的证据。**在进入 DEV 前必须只读确认目标运行接口能提供有时间戳的实际电机状态，或已冻结且匹配的因果电机模型；若只有 requested torque/setpoint，则停止本候选的 observer DEV，不把请求值称为实际力矩。**只读确认方式：检查目标采集/执行接口源码和字段来源，确认信号在事件 `k` 前已产生，并以信号血缘检查排除 `Ptrue`、`rho_true` 和 `realized_generalized`；无需打开 raw/MAT。

最小实现 seam（本报告只建议、不改动）：在 `matlab/runtime/run_dl1018_closed_loop.m` 的 attitude event 与 `attitude_bs_step` 调用之间，增加一个纯因果状态 helper，例如 `matlab/core/attitude_morph_compensation_step.m`。输入只含当前/上一事件 body-rate、已发 morphology command、固定 cfg/`J0`、名义 `alphaBS`、上一事件电机状态/累计力矩、`dhat` 和上一时刻 `rhohat`；输出 `rhohat/rhodothat`、`tau_shape`、更新后 `dhat` 与合成 `estimateTorque`。初始化 `rhohat=cfg.plant.arm_initial`、`dhat=0`，首次形态事件前 observer 只采集因果历史，输出为零扰动估计。惯量只由 `arm_mass_properties(rhohat, cfg.plant, rhodothat)` 得到；分配重建只用 `allocation_matrix(rhohat, P_hat)`，不从 Plant 对象读形态。`attitude_bs_step.m`、C5 输出/参数、位置控制和 C* 离线定义均保持冻结。

最大机制风险：当前 C5 分配器仍以 C0 反解电机；真实形态下实际 wrench 通过 `C(rho)` 变化。命令侧 `Ĉ` 重构的力矩误差会进入 `dhat`，前几拍无法被前馈精确抵消。风矩也不可直接测得，只能通过测量角速度变化与实际电机力矩的差估计。采样差分噪声、0.10 s 延迟、命令积分与实际形态跟踪误差、饱和和分配失配都可能让候选变差。投影只保证 `dhat` 有界，不保证姿态闭环稳定；代数抵消检查、有限 DEV 成功或单一 observer 时间常数都不能推出渐近稳定、ISS 或硬件稳定性。当前没有对带采样、分配饱和和形态误差系统的 Lyapunov 证明。

## 最小可证伪验证草案

**无 Plant 前置检查（建议先做，不代表已执行）：**用合成命令序列核对 1 ms 状态积分及限位，不载入任何航次日志；对合成正定 `Jhat`、`J0`、`Jdothat`、`omega` 和 `alphaBS` 代入无风、精确执行器代数式，检查 `Mnom+tau_shape` 对应的理想角加速度等于 `alphaBS`，绝对误差 `≤1e−10 rad/s²`；用人为构造的已知电机速度信号核对 `Ĉ_tau·Ω²` 单位/轴序；检查每个 `dhat[k]` 只读到 `k−1` 区间且始终在 `±dmax` 内，输出和状态全有限。任一时间索引、单位/轴序不符，或形态估计不由已发命令因果恢复则停止。这个检查不调用 Plant、不证明观测器对真实 Plant 的估计正确，也不提供稳定性证据。

**最小 DEV 筛查（待独立任务书和输入接口确认后）：**固定三场配对，均逐场对比同场 `C5 position + online attitude RBF`：`DL1018_DEV_T1_C00_W03`（无移动臂、有风，检查扰动观测器）、`DL1018_DEV_T2_C02_W15`（单臂形变、无风，检查形态前馈）、`DL1018_DEV_T3_C10_W11`（多臂形变与 W09–W14 风场，检查叠加情形）。这些都是 DEV 开发场景；首场曾进入旧屏查，所有结果仅作为开发证据，不称独立验证。固定同一 C5 scene、位置 `cfg/opts`、reference、初值、风、调度、100 Hz 更新、名义反步/分配和执行器；只将 attitude compensation 模块替换为本方案，RBF 输出/更新均关闭。两支运行都记录 Q、SO(3)、饱和/clip、observer 输出限幅、信号时间戳和完整性；配对基线不重跑时须复用身份已核验的同场既有 baseline。

预先通过门槛：3/3 完整且零安全停止，候选零电机饱和/广义裁剪，三场逐场 Q 与 SO(3) RMSE 均不劣于对应 RBF 基线（容差 `1e−12`），且至少一场至少一个指标严格改善；任一项失败即停止、不扩展 DEV、不访问 TEST。全通过只批准另行审查是否扩大 DEV，不能宣称解决泛化或稳定性。

## 只读身份 SHA-256

以下为本审查读取的冻结源码/报告 SHA-256。设计方案本身尚未实现。

| 文件 | SHA-256 |
|---|---|
| `matlab/core/vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| `matlab/core/simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| `matlab/core/arm_mass_properties.m` | `8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5` |
| `matlab/core/distributed_mass_properties.m` | `db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a` |
| `matlab/core/controller_parameters.m` | `4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398` |
| `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| `matlab/core/allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| `matlab/core/allocation_matrix.m` | `5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d` |
| `matlab/core/tcn0916_morphology_scenario.m` | `711a87e01e616ee141f9068a8c4e31758dc328ade3f692e1a92a5de723d30438` |
| `matlab/core/tcn0916_topologies.m` | `3fd341fa2292c8118f8b363611671677517c44009550bdf82e96cd751e6dce5f` |
| `matlab/core/default_config.m` | `685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51` |
| `matlab/data/export_attitude_events_dl1018.m` | `baeca25a27ee411e900d38333c888a91aa7ce2c5a17ad58cc6989f7aea684141` |
| `matlab/core/rbf_mimo_basis.m` | `4139c7d08daa5bea6e04702b966ce76cdb6a54ea33d9820cfd9c3a70529248f4` |
| `matlab/core/rbf_mimo_update.m` | `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a` |
| `matlab/core/rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| `matlab/runtime/run_dl1018_closed_loop.m` | `9f6b436c8247c49783ec04ef326b20fc5d7de2870c9ab972212a0b2e4c432bc2` |
| `matlab/scenes/make_scenes_dl1018.m` | `7d11b4ebf63105b016c67f4b3c427282b35dafa53280ef2daf5578a6a16bb9ec` |
| `experiments/attitude_cm18_c524_coverage33_20261025/relabel_c524_coverage33_v1.m` | `7857b8d6c92ed1e5341b76b718f9e410f6d4bab22326ed3bcf079c197228ba43` |
| `experiments/attitude_cm18_datarepair_20261024/extract_cm18_events_v1.m` | `15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1` |
| `reports/attitude_cm18_c524_screen12_20261025/C524_ROOT_CAUSE_DECISION_v1_ZH.md` | `f040721064031668b7b8ae9bc14c444fc605645a462d22c9754e168a5de9c2d6` |
| `reports/attitude_cm18_c524_screen12_20261025/C524_SCREEN12_RESULT_v1.md` | `b2bb74826dd11ab82f6af714df15345b1a9db419dc93412204e075a694857988` |
| `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_ROOT_CAUSE_DIAGNOSIS_v1_ZH.md` | `d564d77133e2752d327450c9cedb5d7c3d946c1988dc58fc7720fa39b25d4894` |
| `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md` | `41c38fe91ff121be1853826db94e830ad4c3a76ebee8623bcab0de5cd6a2a3c3` |
| `reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1/FIT_GENERALIZATION_REPORT_v1_ZH.md` | `d2305c87118e638345b9da13784d3c58d00d01a9cbf3394d5866befdbafba34c` |
| `reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md` | `934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017` |
