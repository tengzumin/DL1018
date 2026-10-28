# 主动变形窄门 pilot 任务书 v2（草案）

日期：2026-10-25。状态：草案，尚未放行任何新 Plant call。项目历史文件、旧 TEST 与 DEV72 结果均保持原位。
> **2026-10-25 主线更新（优先于本草案后续 holdout 描述）**：先完成当前公平诊断 pilot，分清共享物理前馈、observer 与主动形态任务各自的作用；pilot 后不自动运行 432-call physics/observer holdout。之后另立 DL 姿态替代任务书，固定位置环为 C5，并以 B 与 C5+原在线 RBF 为对照。首选候选为小型因果时序网络（如 TCN）输出受限的姿态残差力矩，推理时冻结权重；输入限定为部署可得的姿态误差、机体系角速度、BS 名义角加速度/力矩及可测或可命令的臂长/臂长速度，不输入 `Jhat`、`Jdot_hat`、Plant 真值或仿真专属状态。先审计并复用 RBF 输出/闭环记录作为离线监督来源，按场景划分训练与验证；若标签由仿真 Plant 量生成，必须与推理输入隔离并披露。显式惯量重建只作为本轮对照或后续消融，是否部署由证据决定。48 场 holdout 继续封存，候选冻结后另立任务书决定用途。当前 v1 在 GHP6 的 B 运行因日志组装缺少 `trim_head_audit_v39` 失败，已消耗 1 次 Plant call 且没有 raw；不重复该场景。v2 使用新场景 ID/seed，补入逐 SHA 锁定的只影响日志的 runtime helper，并重新做完整 no-Plant 审核。

## 1. 研究问题

同时补足三个互不替代的证据：

1. **系统级比较**：冻结 candidate 是否在主动变形的往返检视任务中优于原始 B。
2. **姿态配置比较**：在同一个 C5 DSSM14/M110 位置栈和同一新场景下，分别测量物理前馈对在线 RBF 的增益，以及共享物理前馈后 observer 相对在线 RBF 的增益。主要替代判断比较 C5+物理前馈+observer 与 C5+RBF+同一物理前馈；plain C5+RBF 仍作为 legacy 参考。
3. **形态应用价值**：同一轨迹、初态、风和 candidate 算法下，主动 `.15→.25→.15 m` 形态在窄门净空与开阔区机动表现上，能否优于 pilot 规则选出的**已测固定配置**。`.15 m`、`.207182 m` 是有限固定对照；不声称搜索了连续臂长范围的全局最佳。固定 `.25 m` 只做几何不可行对照，不声称 Plant 仿真过门。

结果将称为**仿真与配置几何包络证据**。当前 Plant 没有墙体接触/碰撞响应，不能报告真实碰撞通过。桨半径 `0.0635 m` 是 5 英寸桨几何估算值；`distributed_v1` 把电池作为原点点质量且没有电池外形尺寸，因此 checker 只覆盖已配置的机身/臂/电机/舵机/桨盘组件包络，假设电池完全包含在机身尺寸中。所有 clearance 均为模型几何 proxy，不是 CAD/实机安全认证。

### 1.1 文献与本研究的主张边界

已有工作已覆盖“变形四旋翼穿窄口”和“变形用于近距离表面检视”：Falanga 等在实际自主飞行平台上展示窄缝穿越、垂直面近距离检视及物体抓取；Cui 等把全机形态纳入时空轨迹优化与姿态控制，显式处理惯量/CoG变化并报告真实环境实验；Qin 等把可变臂长并入 minimum-snap 轨迹规划并用增广 MPC 跟踪。另有 MorphoCopter 的 Acados/ROS 2/Gazebo/PX4 开源实现与窄通道 MPC 工作。

因此本任务**不声称首次主动变形穿门、首次全身形态规划或首次变形近面检视**。当前实验最多提供：已锁定低层控制配置在一个特定、预先规定的“窄门往返+开阔区机动”仿真任务上的系统/配置比较；没有相机、感知或视点质量模型，不据此声称完成了视觉检视创新。若论文要把交叉学科应用作为主要贡献，后续还需加入可复现的实际检查指标/传感器几何，或收窄为有明确基线的应用验证。

参考：
- Falanga et al., “The Foldable Drone: A Morphing Quadrotor That Can Squeeze and Fly,” IEEE RA-L, 2019, [DOI 10.1109/LRA.2018.2885575](https://doi.org/10.1109/LRA.2018.2885575).
- Cui et al., “Motion Planning and Control of A Morphing Quadrotor in Restricted Scenarios,” [arXiv:2312.07075](https://arxiv.org/abs/2312.07075).
- Qin et al., “Minimum Snap Trajectory Planning and Augmented MPC for Morphing Quadrotor Navigation in Confined Spaces,” *Drones*, 2025, [DOI 10.3390/drones9040304](https://doi.org/10.3390/drones9040304).
- Modi et al., “Constrained MPC-Based Motion Planning for Morphing Quadrotors in Ultra-Narrow Passages under Limited Perception,” [arXiv:2605.15999](https://arxiv.org/abs/2605.15999); authors' [morphocopter_mpc repository](https://github.com/harshjmodi1996/morphocopter_mpc).
- “cc-DRL: a Convex Combined Deep Reinforcement Learning Flight Control Design for a Morphing Quadrotor,” [arXiv:2408.13054](https://arxiv.org/abs/2408.13054); model-free PPO is trained for representative arm-length modes and evaluated in simulation.
- Li et al., “Adaptive model predictive control based on neural networks for Hover attitude tracking with input saturation and unknown disturbances,” *Transactions of the Institute of Measurement and Control*, [DOI 10.1177/01423312231180236](https://doi.org/10.1177/01423312231180236); uses a neural estimate/compensation for unmodeled dynamics and disturbances in attitude tracking.

**主张边界：** 神经网络扰动/残差补偿已有先例，主动变形四旋翼的深度强化学习也已有仿真工作；因此不能把“使用 DL”“不显式传入惯量”或“变臂长飞行”单独声称为首创。本项目应以 C5 位置栈固定、严格匹配姿态输入/控制条件、窄门往返应用任务及完整安全/几何对照形成证据；具体方法贡献须由后续任务书和实验结果决定。

`MorphoCopter MPC` 的作者代码仓库公开了 Acados/ROS 2 Humble/Gazebo Garden/PX4 流程，可作为应用规划/仿真工程参考；它不是本项目 MATLAB 闭环的直接替换件。当前检索未找到 cc-DRL 论文的官方代码发布，暂不把非作者 quadrotor RL 仓库当成方法基线。

## 2. 场景定义

### 2.1 门洞与飞行包络

- 隔墙：`x∈[-0.10,+0.10] m`；矩形开口：`y∈[-0.225,+0.225] m`、`z∈[0.90,1.50] m`，中心 `(0,0,1.20) m`。
- 四臂为 X 形，方向角 `45°,135°,225°,315°`。桨盘半径取 cfg 的 `0.0635 m`，明确作为 5 英寸桨估算值。
- yaw=0 且中心对齐时，外缘宽度 proxy 为 `2(ρ/√2+0.0635)`：`ρ=.15` 时 0.3391 m（每侧余量 55.4 mm），`ρ=.25` 时 0.4806 m（每侧越界 15.3 mm）。固定形态名义边界臂长按每侧 15 mm 定为 `ρ*=√2(0.225−0.0635−0.015)=0.207182 m`；这只是名义上限，姿态/位置误差可能使实际几何净空小于 15 mm。
- 最终几何 checker 必须绑定 `vehicle_envelope.rotor_physical_radius=0.0635 m`（不能误用转动惯量参数里的 `.045 m`），用同一 Plant geometry 参数计算旋翼盘、机身、臂、电机及舵机在实际姿态下穿过墙体 slab 的最小有符号净空及时间；以上简式只用于尺寸草案，不能代替完整 checker。`state` 位置按 Plant 的 instantaneous total CoG 解释，checker 必须用当时 CoG 偏置重建组件几何；四臂同步时理论 CoG 居中仍需显式校验。

### 2.2 20 秒往返检视参考

- `dt=0.001 s`，`t=0..20 s`，共 20,001 状态点、20,000 transitions。初态等于参考起点，初速度/姿态角速度为零。
- x 参考：定义 `s(u)=10u³−15u⁴+6u⁵`；0–6 s 用 `u=t/6` 从 `−1.5` 到 `+1.5 m`，6–14 s 保持 `+1.5 m`，14–20 s 用 `u=(t−14)/6` 从 `+1.5` 返航至 `−1.5 m`。速度和加速度用该多项式解析求导。因此参考中心约在 3 s 与 17 s 两次过门。
- 开阔区横向机动仅放在 8–12 s，位置和一、二阶导数均解析生成；门口过门窗口维持 `y=0,z=1.2,yaw=0`。为使位置、速度、加速度在区间两端均连续，定义 `b1(u)=sin⁴(πu)`、`b2(u)=sin⁴(2πu)`，`u=(t−8)/4`；区间外令机动为 0。对 `b=sin⁴(au)`，公式 `b_u=4a sin³(au)cos(au)`、`b_uu=4a² sin²(au)(3cos²(au)−sin²(au))` 是对 u 求导；时间导数必须用 `db/dt=b_u/4`、`d²b/dt²=b_uu/16`。三个任务 profile：G1 单峰横移 `y=.45 b1`；G2 **同侧双峰**横移 `y=.35 b2`；G3 `y=.30 b1, z=1.2+.15 b1`。builder 必须用解析一、二阶导数，不能在边界用有限差分造成指令尖峰。先做无 Plant 速度、加速度、名义倾角和门口净空校核；如超过既有执行器/姿态边界，只能在 holdout 未生成前修改并重新审核此任务书。
- 48 个未使用场景：G1/G2/G3 × W00–W15。ID 为 `DL1018_GH48_G{1|2|3}_W{00..15}`。每组均有 16 个风值，W15 为零风；W09–W14 是高频风组。新种子暂定 `2,100,000,000 + 1000*(G−1) + W`，冻结前对本机所有既有锁/manifest 的**ID/seed 字段**作只读冲突核验（不读取任何旧 TEST raw、status 或成绩），并核验 `<2^31`。
- 独立 pilot 使用 `DL1018_GHP7_G{1|2|3}_W{00|12}`，seed=`2,060,000,000 + 1000*(G−1) + W`；与 holdout 的 ID、seed、payload 完全不重用。pilot 与 holdout ID/seed 清单均须在 pilot 开始前冻结并通过既有 lock/manifest 的 ID/seed 元数据冲突核验；holdout payload 暂不生成；只有新的 DL 候选与独立任务书冻结后才重新决定。
- W00–W14 的频率/幅值档沿用现有场景代码中已公开的离散定义，但相位由新种子产生；方位、仰角和风向公式必须写入独立 builder，并在首次 pilot scene 生成前锁定。此时仅冻结 holdout ID/seed 清单，不物化 holdout payload。W15 使用全零风。不得调用会构建/载入 888 场数据或 TEST 行的 `make_scenes_dl1018('BUILD')`。

### 2.3 臂长干预

- **ACTIVE**：拓扑 `1234`；四臂同步；初始 `.15 m`；6.0 s 开始以 `.05 m/s` 伸至 `.25 m`，保持至少 5 s；13.0 s 回缩，15.0 s 前回到 `.15 m`。在约 3 s 首次过门和约 17 s 返航过门时均为紧凑形态，开阔区检视机动时为扩展形态。
- **FIXED_BOUND15**：四臂全程固定名义边界长度 `ρ*=0.207182 m`，与 ACTIVE 共享参考、初态、风、candidate 算法/模型权重。全时序 `command/rhoDot_true/rhoDot_hat=0`，`rho_true/rho_hat=ρ*`，且 cfg 初始臂长同为 `ρ*`；binder 必须重算并核对 fixed-controller `J0`/SHA、`C0` 与 generalized/control limits。不得以 cfg 初始 `.15 m` 假装 `ρ*`。每场实际 clearance 仍须由完整几何 checker 判定，不能预先叫作安全通过。由于名义惯量和几何派生限值随臂长改变，此项是匹配各自几何参数的闭环**配置包比较**，不是纯形态调度的隔离因果效应。
- **FIXED_MIN**：`C0`、四臂固定 `.15 m`，与 ACTIVE 共用同一 candidate 算法运行完整任务，作为保守短臂性能对照；另计算其几何包络。
- **FIXED_WIDE**：四臂固定 `.25 m`，只由 geometry checker 核验其对 0.45 m 开口的模型净空为负；除非无 Plant 审核确认用来回答额外问题，否则不启动其 Plant 仿真。

## 3. 方法与配对

### 3.1 对照公平性复核

冻结源审计确认：`paired_runner/morph_dev2_dev72_v1/matlab/runtime/run_paired_observer_closed_loop.m` 的 `formalRbfBaseline` 分支让 RBF 使用固定名义 `P=fixedController`（约第 1085 行），RBF 力矩为 `P.inertia ×` 在线 RBF 角加速度输出（约第 2394 行）；`matlab/core/attitude_bs_step.m` 以 `M_nom−estimateTorque` 形成命令（第 41 行）。冻结候选另调用 `phys_attitude_replacement_candidate_v2.m` 中的 `tau_shape=(Jhat−J0)α_BS+ω×((Jhat−J0)ω)+Jdot_hatω`（第 98 行），这项没有进入 plain C5+RBF。

所以 plain RBF 对照没有获得同一条显式形态惯量前馈，原来直接比较会把物理前馈的收益混在“替代 RBF”的收益里。helper 由形态命令积分 `rho_hat`，不读取 `rho_true` 或 Plant 实际力矩；这是模型信息和理想执行器假设的不对称，不是直接读取仿真真值的 oracle。新增 C5+RBF+F 使用同一 `tau_comp,F` 和在线 RBF 更新，把比较改为：RBF 加同一前馈是否仍落后于物理前馈加 observer。即使这样，结论仍是两个姿态配置的比较，不是对 observer 单独因果效应的证明。
每个 ACTIVE 场景运行七种 ACTIVE 控制方法；另有 C5+11 的两个 FIXED 配置臂，总计九种配置。所有同场 arm 从同一个 scene payload 运行；C5 arms 使用相同位置网络/normalizer/W0、BS 增益、Plant、allocator、参考滤波与 `J0`，仅按预登记的姿态分支变化，并分别记录 option hash：

1. 原始 **B**：原位置、原在线姿态 RBF；使用 B 锁定控制代码的隔离 wrapper。
2. **C5+RBF**：C5 DSSM14/M110 位置环 + 原 B 在线姿态 RBF，作为同位置栈 legacy 参考。
3. **C5+RBF+F**：保留完全相同的在线 RBF 输出与更新，并叠加与 C5+10 完全相同的 `tau_shape` 物理前馈；observer 关闭。这是姿态替代的主要匹配对照。
4. **C5+00**：C5 位置环，physics feedforward=off、observer=off、姿态 RBF=off。
5. **C5+10**：仅 physics feedforward。
6. **C5+01**：仅 observer residual compensation。
7. **C5+11**：当前 physics/observer candidate，两项开启、姿态 RBF=off。
8. **C5+11 FIXED_MIN**：同算法/网络/head/filter/gains 的 full candidate 与同一新参考/风/初态，四臂固定 `.15 m`。
9. **C5+11 FIXED_BOUND15**：同算法/网络/head/filter/gains 的 full candidate 与同一新参考/风/初态，臂长改成 FIXED_BOUND15；cfg/`J0`/派生限值按固定几何重新一致化。

原设计中的 48 场 holdout 需要 432 formal Plant calls；这是未放行的后续研究选项，不属于当前任务书的执行授权。当前只申请公平诊断 pilot 的 54 calls。每种方法按 scene 配对，时间样本不得作为独立统计单位。物理 feedforward/observer toggle 只存在于新隔离派生树，旧冻结 helper/source lock 不得修改。

### F×O 消融的精确定义

定义 F 为直接模型形状力矩项 `tau_shape` 开关；定义 O 为基于区间合并残差的 observer 力矩补偿开关。四格为：

| 臂 | F | O | `tau_comp`（正向补偿项） |
|---|---:|---:|---|
| C5+00 | 0 | 0 | `0`；observer 不更新 |
| C5+10 | 1 | 0 | `J0 * [beta * clip(J0 \ tau_shape, ±dmax)]`；observer 不更新 |
| C5+01 | 0 | 1 | `J0 * [beta * clip(J0 \ (-dhat_tau), ±dmax)]`；observer 正常更新 |
| C5+11 | 1 | 1 | `J0 * [beta * clip(J0 \ (tau_shape-dhat_tau), ±dmax)]`；冻结 candidate 原公式 |

实际施加到 `attitude_bs_step` 的力矩为 `dT=−tau_comp`；四格统一公式为 `tau_comp=J0*[beta*clip(J0 \ (F*tau_shape−O*dhat_tau), ±dmax)]`，并在 `F=O=1` 时逐样本与冻结 v2 helper 核对。四格共用完全相同的 `J0/Jhat/Jdot`、残差定义、`dmax`、`beta` 和合并限幅。O=1 时残差仍用命令积分的 `rho_hat` 重建 `Jhat`；C5+01 因此是“仅 observer 力矩输出”，不表示完全不用形态物理模型。`r_tau_Nm` 是区间合并力矩残差；`J0\r_tau` 是名义惯量等效角加速度坐标，`dhat_tau` 是投影低通后的合并残差补偿量，均不称作真实外扰。C5+RBF+F 的实际命令按 `M= M_nom−tau_RBF+tau_comp,F` 实现，即传入 `attitude_bs_step` 的 `estimateTorque=tau_RBF−tau_comp,F`；`tau_comp,F` 与 C5+10 使用相同 beta、J0、裁剪和 `tau_shape`，observer 不更新。每个 scene 先计算配对因子 contrast，对 48 场等权平均。定义 `Y` 为正值越大越差的指标，所有 `Δ` 均为“启用项−关闭项”；因此负值表示改善：`ΔF=(Y10+Y11−Y00−Y01)/2`、`ΔO=(Y01+Y11−Y00−Y10)/2`、`I=Y11−Y10−Y01+Y00`。bootstrap 按 scene 整体重采样，并保留该 scene 的全部 arm 与时间序列。

### 预注册解释

- C5+11 对 B：系统级比较。
- C5+RBF+F 对 C5+RBF：估计相同物理前馈加入在线 RBF 后的效果。
- C5+11 对 C5+RBF+F：主要姿态替代比较；共享同一形态惯量前馈后，比较 observer 与在线 RBF。C5+11 对 plain C5+RBF 只作为整体配置比较，不单独归因 observer。
- `tau_shape` 只由合法形态命令、当前角速度、共同 BS 名义角加速度和锁定的质量几何模型计算；不读取 Plant 真值。理想执行器下命令积分 `rho_hat` 与计划形态轨迹一致，因此结果依赖完美动作跟踪假设，不能当作实际传感器/执行误差下的验证。
- C5+00/10/01/11：同一 C5/BS/J0/Plant 下 feedforward×observer `2×2` 消融，按 scene 配对计算两因素效应与交互项，不预设可加。
- C5+11 ACTIVE 对 FIXED_MIN/FIXED_BOUND15：形态配置包比较，涉及形态命令与各自匹配的初始几何/J0/派生控制限值。两种固定臂长均运行；FIXED_WIDE 只计算包络。应用优越性必须按 pilot 前冻结的固定配置选择规则判断，不得在 holdout 上挑最差固定基线。

## 4. 统计与一次性留出门

- 主位置指标：`0–20 s` 三维位置 RMSE `Q`。主姿态指标：用锁定的 C5 ACTIVE nominal cfg 生成唯一 canonical `P_task`（其 cfg SHA、`g`、`max_tilt` 与 reference yaw 均锁定），对每个 scene 的同一解析加速度和 yaw 调用冻结 `baseline_force_to_attitude`，把公共未滤波 `R_task(t)` 存入 scene payload 并绑定 SHA；所有 controller/scorer 复用该数组，不得按各臂参数重算。另核验 B/候选共用的重力与倾角定义。实际 `filtered_attitude_reference` 与自身跟踪误差另表报告，不作主比较目标。
- 系统门（C5+11 对 B）：Q 与 SO(3) 场景宏平均都严格较低，且分层 paired-scene bootstrap 95% CI 上界均 `<0`；两项各至少 41/48 场胜；W09–W14 与 W15 的 Q/SO(3) 组均值均不高于 B；所有原始值和小幅改善敏感性同时报告。W15 每 profile 仅 1 场，组均值门只作描述性条件检查。
- 姿态替代门（C5+11 对 C5+RBF+F）：SO(3) 宏平均更低、paired 95% CI 上界 `<0`、至少 41/48 场更低，W09–W14 与 W15 不高于 matched control；Q 如实报告，不要求相对 C5 无退化，但不得违反 system gate 对 B 的 Q 要求。C5+RBF+F 对 C5+RBF 的前馈增益单独配对报告。若 C5+11 未胜过匹配对照，即使胜过 plain RBF，也不得声称 observer 姿态环替代 RBF；Q 退化时只能声称姿态指标改善，不能声称整体跟踪不退化。
- 几何任务通过事件：必须记录 CoG 从墙前到墙后、再从墙后返回墙前两次有向穿越；每次过墙期间机身/臂/电机/旋翼完整包络通过开口，且离开墙体 slab 后再判定该次通过完成。仅停在墙前、穿越方向错误或包络未离开 slab 均不算 pass。checker 依据 Plant 的瞬时 CoG 和姿态重建包络。
- 形态任务报告：两次过门的最小包络 clearance、最低余量时刻、CoG 位置误差、过门时臂长；8–12 s 开阔区 Q/逐轴误差、姿态误差、最大倾角/角速度、饱和/限幅/clip。每场 `Q_8–12 = sqrt(mean(||p_k−p_ref,k||²))`，取 `t=8.000..12.000 s` 共 4,001 个 state samples；宏平均为先对每场等权求 mean，再求 `1−mean(Q_ACTIVE)/mean(Q_selected_fixed)`。ACTIVE candidate 几何 pass 要求 48/48 场两次完整 envelope clearance 均 `≥15 mm`；无接触 Plant 限制须出现在摘要和图注。
- 应用结论称为“主动形态窄门往返与开阔区跟踪仿真”，不称视觉检视成功（当前没有相机、目标可见性或成像质量模型）。每个 scene 的任务可行须同时满足：20,000 transitions 完整且状态有限、无 safety stop、无电机饱和/广义量裁剪/tilt-limit 触发；完成两次有向过门且完整 envelope clearance 均 `≥15 mm`；`Q_0–20≤0.05 m`、`Q_8–12≤0.05 m`、终点位置误差 `≤0.10 m`。比较时固定配置使用同一口径。应用优越性只相对 pilot 规则选出的**已测固定配置**评估：若 ACTIVE 48/48 场均任务可行而 fixed 有场景不可行，则报告配对任务可行率差及其原因分解；若两者均 48/48 场任务可行，则定义 `B=1−mean(Q_8–12,ACTIVE)/mean(Q_8–12,fixed)`，scene 等权宏平均须 `B≥0.05`，且按 G1/G2/G3 分层共同重采样配对 scene、每次重算该比值后的双侧 percentile 95% CI 下界也须 `≥0.05`，才称开阔区跟踪有至少 5% 的实际改善。否则仅报告几何/误差比较，不称应用优势。FIXED_BOUND15/FIXED_MIN 同时报告，holdout 结果不得用于换选固定基线。
- 安全门：有限值、完整 transitions、安全 stop、电机饱和、generalized clip、tilt limit、峰值倾角/角速度均逐场报告。运行失败保留并计入；不得按指标剔除场景。
- 主宏平均 paired-scene bootstrap 固定 seed `20261025`、20,000 次，按 G1/G2/G3 分层且 profile 等权；每次抽中的 scene 索引对所有比较 arm 共用。95% CI 使用双侧 percentile `[2.5%,97.5%]`；系统/姿态门用 97.5% 上界 `<0`，5% 应用门用 2.5% 下界 `≥0.05`。风组检查按固定 W 集合计算。上述组合是该留出任务的操作性门；未通过只说明此门未通过，不证明候选在其他条件普遍无效。不宣称跨训练种子可靠性或实机通过。
- holdout 一次性执行；任何 holdout 成绩不得用于调参、切 Head、改门宽/轨迹或决定候选。若任一冻结测试失败，保留失败结论；需要修复时必须用新 scene IDs/seeds 建下一份独立留出，不重跑同一批声称成功。

## 5. 资源与安全执行流程

1. 新建全隔离路径 `experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/`；仅从 DEV72 已冻结候选、C5 模型与 B 的 source-lock 拷/取所需文件。历史代码、MAT、cache、raw 与 ledger 均只读；不删除任何文件。
2. 生成 no-Plant builder、holdout 与 pilot 的 ID/seed 清单、6 个 scene 的 18 个几何绑定 pilot payload、全机几何 checker、candidate/B 隔离 runner、source lock 与 scorer。此时不生成 holdout payload。pilot 使用独立 ID/seed，绝不复用 holdout payload。所有候选配置与源码 hash 在任何 Plant pilot 前冻结；holdout ID/seed 清单也先冻结并检查新颖性。只读既有 lock/manifest 中的 ID/seed 字段；不得读取旧 TEST MAT/raw/run_status/成绩。
3. Root 对所有改变文件做行级源码审核；分别锁定 B 与 C5 的源树、wrapper、cfg/options；B 不绑定 DSSM14。核验 B/候选共同的 Plant、allocator、wind、actuator、gravity 与 R_task 身份；C5 各 ACTIVE F×O arm 必须共用 model/normalizer/W0、position options、Plant 与场景 payload。FIXED_MIN/FIXED_BOUND15 的 geometry cfg、J0、C0 和派生限值分别锁定，不要求其与 ACTIVE 的 cfg/J0 相同。所有同条件 arm 都从同一个 frozen payload 读场景；MATLAB path 净化与进程隔离逐 worker 检查。使用 PowerShell 7 作业编排；每个 MATLAB `-batch` worker 使用独立进程、prefdir、source tree 与唯一输出目录，不在同一 MATLAB 进程切 path/function cache。先以一个 worker 完成 pilot 子批并测得每 worker 峰值 RSS；之后按 `worker数≤min(逻辑核数, floor(可用RAM/单worker实测P95 RSS))` 逐级增加并发，充分使用当时可用内存；worker 按实测 P95 RSS 排队，不终止或打断已运行实验。每次启动新 worker 前按实测 P95 raw/trace 大小计算“待完成任务预计写入量 + 10 GiB 磁盘余量”；可用空间不足则只暂停排队，不删除结果，空间恢复后续跑。无固定项目配额，worker 均为独立 MATLAB 进程、prefdir 与唯一输出目录。
4. no-Plant 检查通过后运行 6 个独立 pilot scene（G1/G2/G3 × W00/W12），九臂 B、C5+RBF、C5+RBF+F、C5+00/10/01/11 ACTIVE、C5+11 FIXED_MIN、C5+11 FIXED_BOUND15，共 54 Plant calls。pilot 用于检查全部分支、runner、安全和任务几何，并按预注册规则选择 fixed comparator；不得据 pilot 调整 candidate 参数。选择规则：仅保留六个 pilot scene 均完整结束、状态有限且为 `STABLE`、无 safety stop，并且两次过门均满足完整 envelope clearance `≥15 mm` 的固定配置；在合格者中选 `Q_8–12` scene-macro 较低者，差值不超过 `1e-9 m` 时取臂长较大者。若无配置合格，不作相对已测可行固定形态的应用优势主张。Root 审核 pilot 后冻结对比结论与几何筛选结果；不自动生成 48 个 holdout payload，也不自动放行 432-call physics/observer formal batch。下一步先为 DL 姿态替代编写单独任务书，明确可部署输入、离线标签隔离、数据划分、训练身份及安全门；48 场 holdout 在 DL 候选冻结前继续封存。若技术性故障要求改代码，保留失败航次；每个变更源码集合都必须重新完成 no-Plant 审核、生成新 pilot IDs/seeds、重锁所有 source/config hashes 并取得新的 pilot release，不能复用失败航次。仅允许修复已定位的实现故障；不得按 pilot 指标调参。新增修复 pilot 航次另记账，不占用 48-scene holdout，也不设用户指定次数上限。若 candidate 性能/安全未过预登记门，停止其扩展；若确认需改算法，则回 DEV 研究并为新候选另立独立任务书和 holdout.
5. 原计划的 432-call physics/observer formal batch 已从当前执行顺序移出。只有 DL 候选完成训练、DEV 门审核和实现冻结后，主审才会据新任务书决定是否使用封存 holdout；后续方法数、航次数、统计门及资源计划均须按 DL 方法重定并预注册。A02 实测 58 calls 约 73 分钟仅作串行基准，不能直接当作新批次耗时.
6. A02 raw 约 440 MB/场、原 84.5 GB 估算针对旧的 432-call physics/observer holdout 设计，不代表当前 pilot 或未来 DL 任务的实际需求。pilot 先按单 worker 实测 P95 raw/trace 大小重算总写入量，并保留至少 10 GiB 磁盘余量；无固定新增产物配额、不自动删除数据.
7. 保留逐场 start marker、raw/status、scene/spec/source hash、实际 Plant 调用与 transitions、MATLAB stdout/stderr 和总 ledger。输出 full paired CSV/JSON、所有输场、figure、geometry proxy 与 paper methods/results 初稿。

## 6. 放行条件与当前停点

本草案本身没有释放 MATLAB/Plant。以下条件全部完成后，主审再将本文件改成冻结版本并给出明确 pilot release：

- no-Plant scene builder、pilot payload 与 48 场 holdout ID/seed 清单已完成并自校验；参考速度/加速度/名义倾角、臂长约束与开口几何通过。holdout payload 尚未生成，继续封存；新的 DL 候选及其任务书冻结后，再决定是否生成测试 payload 并重新审核身份。
- geometry checker 用 CoG参考点、旋转后的 body/arms/motors/rotor disks 做完整 envelope 与两次有向穿越检查，并用 analytic `.15/.207182/.25 m` 边界做单元自校核。
- 新隔离 `run_gate_holdout_closed_loop` 必须接受 `reference_contract_id=DL1018_GATE_INSPECTION_HOLDOUT_V1` scene contract，并支持 C5+RBF、C5+RBF+F、C5+00/10/01/11、ACTIVE/FIXED_MIN/FIXED_BOUND15；不得改冻结旧 runner。C5+RBF+F 保持 RBF update/output 与 plain RBF 相同，只合加共同物理前馈；R_task 和声明 SHA 必须在任何 Plant run 前通过同一字节口径校验。派生 helper 的 F×O=11 分支逐样本与冻结 v2 candidate 同路径/同输出；00/10/01 仅改变预登记 torque term 与 observer update 开关。C5+RBF 与 physics arms 的共同 C5 position options/hash 必须一致。新 B wrapper 必须从 frozen scene payload 直接读场景，不得读取旧 B raw。
- B wrapper 输入新 `scene`，不读历史 B raw；B 与 candidate 的 Plant/allocator/风载/参考入口来源和配置均逐 SHA 核验；path/function cache 由独立 MATLAB 进程隔离。
- holdout IDs/seeds 与本机所有既有 locks/manifests 不重复；为核验唯一性，旧 TEST 只可读取 lock/manifest 中的 ID/seed 字段，绝不读取旧 TEST raw、MAT、status 或成绩。所有新输出写入本任务独立目录，不进入旧 TEST 目录。
- 每批启动前核对当前实验进程、Windows 可用 RAM、逻辑核数及预计余下写入量；worker 数依第 5 节的 P95 RSS/磁盘公式决定。不得终止或打断已运行的实验。

**当前状态：** v1 的 attempt_20261025T150543025Z_f1ba48ad45924587a0dc5d2cb4503b80（GHP6/G1/W00）保留为 FAILED，账本记 1 次 Plant call、无 raw MAT；根因是 frozen B source tree 漏锁 `trim_head_audit_v39.m`，失败发生在闭环调用返回后的日志整理。v2 已在独立目录加入该 helper overlay，原文件与镜像 SHA 均为 `66dd557a672ca3363fe320223107c99975cf404e3657c93bd108b5d331e4eedc`，并由 runner、PowerShell identity verifier 和 source lock 检查。v2 仍在 no-Plant 准备阶段：冻结任务书、v2 candidate/B locks、18 个新 GHP7 payload、receipt、root audit、54-call release 和空评分核验都尚未完成；因此目前新增 Plant calls=0、训练=0、TEST 未读。v1 失败 marker/status/raw 状态均保留；GHP6 不重跑。v2 的 GHP7 seed 为 `2060000000 + 1000*(G−1) + W`，只读核验既有 ID/seed 元数据未发现冲突。48-scene holdout payload 继续封存。
