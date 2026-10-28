# A1T 同状态动作误差分解任务书 v2

2026-10-25，Root。仅批准准备离线诊断方案；不授权执行 Plant、闭环积分、训练、optimizer、模型选择或控制修改。当前有场景仍在运行，未终态且未独立审计 PASS 的 raw 一律不读。最终报告须覆盖固定 SCREEN12 全 12 场，包含改善场与退化场；数据未齐时只报 `INCOMPLETE`，不得形成全场结论。

## 目标与边界

在每个已完成并通过独立 A1T raw audit 的同一条记录轨迹上，区分：（1）固定 A1T 网络输出对直接补偿目标的逼近误差；（2）beta/输出限幅造成的可达性损失；（3）原 100 Hz 更新和 1 ms 零阶保持造成的同状态动作差异。通过相同记录状态重放纯模型和物理代数，不积分新轨迹、不改变实际日志动作，也不把不同闭环轨迹间的差异解释成组件因果效应。

目标是定位误差主要出现在网络近似、beta/clip 可达性，还是采样保持阶段。`C*` 使用真实形态与风的物理信息，只作离线 oracle；这些信息不进入网络输入或部署。结果不证明 A1T 全局泛化、闭环改进或稳定性，也不自动授权重训/改结构。

## 固定输入与复用源

1. 使用 `reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json` 的固定 12 行顺序；每一行仅在同场 A1T run status 终态、raw 完整、`A1T_SCREEN12_INDEPENDENT_LOG_AUDIT_V1` 为 PASS 且 raw SHA 一致后才可读取。身份来源优先采用逐场 ROOT release、`run_start.mat`、`run_status.json` 与 PASS 审计，禁止仅依赖 status 文本。
2. 复用已审 A1T audit `reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/audit_a1t_screen12_log_v1.py`（SHA-256 `14de8af50058ebfb39b1d7ca484561b50adf5086bdfacd0dc3a541fd6871f6be`）中的 HDF5 布局、20,000 左对齐 transitions、事件索引 `11:10:19991`、X18/BS/forward/clip/beta/held 复核、A1T deployment 与来源绑定；不得复制或变更冻结 audit。
3. 物理关系复用已审核 `experiments/attitude_cm18_datarepair_20261024/audit_full_matrix_replacement_target_v1.m`（SHA-256 `fe48f2d9d812cfa92364bd859490858a0e3eec01b3e6e80c773c829f9975042c`）及 `reports/attitude_cm18_datarepair_20261024/full_matrix_replacement_target_v1/FULL_MATRIX_REPLACEMENT_TARGET_DIAGNOSTIC_v1.json`（SHA-256 `bdb0ba18cd9d81aa176157c58f665c6ca2a0eb8946e75c3f652ea18ccffabee3`）所用完整三轴 `G/E0/C*` 推导、纯 `allocate_control` 对照和约束检查。该诊断的旧四场输入不可冒充本任务 A1T raw；只复用公式和逐状态物理构造方式。
4. 网络参数只读固定 A1T deployment：`experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1/deployment_parameters_v1.json`，SHA-256 `dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42`；selected step `40000`。纯 forward 使用冻结 helper 与已绑定身份；不重新载入训练器、拟合 normalizer 或更换权重。
5. 必须使用 raw 中真实记录的 state、command、reference/filter、requested/realized wrench、nominal BS torque、`wind_torque_B`、arm command/true morphology/rates、事件与 held 动作，以及 run-start cfg。缺少恢复 `Jtrue/Ct/Jdot/wind` 或完整 X18 所需数据时，该场标为失败并停止解释；不得从预测或同名场景猜补。

## 逐状态定义

每个 1 ms transition 状态均使用其原始状态和当前真形态/风。按冻结 controller 及原始 `attitude_bs_nominal_torque_Nm` 重建 `alphaBS`；用与原审计一致的纯函数从 cfg、`rho_true/rhoDot_true` 取得 `Jtrue`、`Jdottrue`、`Ct`，从固定 controller 取得 `J0/C0/Jdot0`。令 `L=[zeros(1,3);J0]`、`wrench0=Ct*(C0\[T; tauBS])`，完整映射与零补偿漂移为：

```text
M  = Ct * (C0 \ L);
G  = Jtrue \ M(2:4,:)
E0 = Jtrue \ (wrench0(2:4) + windTorque
                - cross(omega,Jtrue*omega) - Jdottrue*omega) - alphaBS
C* = G \ E0
```

代码需按实际 MATLAB 矩阵布局实现，不得把 `G` 简化成惯量比；检查 `G` finite/full-rank/condition、名义 allocator 线性前提、请求/realized wrench 闭合和 `E0-G*C*` 闭合。不得对异常矩阵正则化或静默跳过。理想式误差须另与实际完整 allocator 复算区分，并报告 allocator generalized clipping 与 motor saturation。

对每个实际 100 Hz A1T 事件，冻结网络的 raw 输出记作 `y`，日志中的 beta 和 clip 限值分别为 `beta`、`dmax`。实际更新动作应复核为 `cactual=beta*clip(y,-dmax,dmax)`，并与 engine held log 相符。`C*` 是 beta 之后的理想施加量，beta 为正时理想 raw 输出为 `ystar=C*/beta`。定义可审核的直接分解：

```text
fit_applied       = C* - beta*y
clip_increment    = beta*(y - clip(y,-dmax,dmax))
actual_residual   = E0 - G*cactual
```

在没有 allocator generalized clipping 与 motor saturation、且上述局部线性式成立时，`cproj=beta*clip(C*/beta,-dmax,dmax)`（`beta>0`）是 `C*` 在动作分量盒约束 `[-beta*dmax,beta*dmax]` 上的逐分量欧氏投影；`beta=0` 时可行集合为 `{0}`，故 `cproj=0`。这个投影是一个可行参照，不是 G 加权物理误差下的最优补偿。若 `G` 满秩，则对三轴二范数有：

```text
sigma_min(G) * norm(C* - cproj, 2)
    <= min_{c in feasible_box} norm(G*(C* - c), 2)
    <= norm(G*(C* - cproj), 2)
```

以上上下界只针对明确定义的**线性 surrogate**：在动作盒 `feasible_box=[-beta*dmax,beta*dmax]`（`beta=0` 时 `{0}`）上，对 surrogate 误差 `G*(C*-c)` 求最小向量二范数。它不证明真实完整 allocator 在整个输入盒上保持线性；即便 nominal 和 `cproj` 两个已检查动作未触发 clipping/saturation，也不足以作该推断。该任务不检查盒角点、不做 QP，也不把 surrogate 界称为真实 allocator 全局 floor。真实 allocator 只对明确重算的 held、fresh、`cproj` 等动作报告观测误差和 flags；任一动作有 generalized clipping/motor saturation 时尤其不得将 surrogate 界套到真实误差上。该界不拆成逐轴下界，不称 `cproj` 为物理最优。G 的最小奇异值、秩与条件必须随场记录。

在线性、无执行器限幅条件下，令 `rfit=G*fit_applied`、`rclip=G*clip_increment`，则 `actual_residual=rfit+rclip`。必须保留交叉项：逐轴 `MSE_actual[a]=MSE_fit[a]+MSE_clip[a]+2*mean(rfit[a]*rclip[a])`；向量二范数 MSE 对应交叉项 `2*mean(dot(rfit,rclip))`。分量 RMS 不能相加，也不能只按各项 RMS 大小断言哪项“主导”；实际输出受 allocator 限幅时以完整 allocator 重算为准。

每个事件至少输出 `y` 对 `ystar` 的 raw 输出差、fit_applied、clip_increment、`cproj` 可行参照及上述二范数界（仅适用事件）、线性物理分量、MSE 交叉项和完整 allocator 物理误差；逐轴报告 signed mean/RMS，另报三轴向量 RMS、事件数、每轴 clip、allocator clip、motor saturation、G 条件摘要。beta schedule 不可单独称为误差：对 `beta>0` 且无 clip，`beta*(C*/beta)=C*`；beta 影响可达性主要通过固定 raw clip 与 beta=0 不可达项体现。

## 100 Hz 保持同状态对照

为隔离 sample/hold，在相同原始 1 ms 状态上重建每个 transition 的完整 X18（复用 A1T audit 对状态、BS、command 累积量、10 个已完成 requested-torque 历史窗及事件时序的定义），用相同冻结网络逐状态作只读 forward。此 forward 不写回日志、不更改状态、不调用 controller/episode/Plant。事件更新之间，构造 `cfresh=beta_held*clip(yfresh(X18_i),-dmax,dmax)`，与同一行实际 `cm18_applied_acceleration_held_rad_s2` 比较；保持同一个已记录 `beta_held` 和同一个 clip，故差异仅表示“在该记录状态上刷新网络输入”与上一 100 Hz 输出保持之间的动作差。排除首个 100 Hz 事件前的初始零输出区间，并单独报告事件行（fresh 与更新输出应闭合）。

对实际 held 与 fresh action 在每个相同 transition state 分别用完整 allocator 复算 true angular acceleration，报告 fresh-minus-held 的逐轴 signed mean/RMS、向量 RMS、phase、clip/saturation；也保留 `G_i*(cfresh-chold)` 的局部线性对照并报告与完整分配器的差。此项是固定记录状态的静态一步反事实，不是“将 1000 Hz 网络放进闭环”的性能预测；不能推断后续姿态、位置、风或形态状态会保持。

## 固定分组和输出

- 全 12 场逐场报告；同时报告 `ALL`、`T1`、`T2`、`T3`、manifest 明确标注的 `HF` 子组、scene_id 后缀为 `W15` 的子组，并附 task/category 交叉分组。所有聚合采用等场景权重：先在每场内计算相应时段/事件指标，再对组内 scene 指标做算术平均，并报告 scene_count；不能把事件拼接后按样本数加权。HF 严格按冻结 manifest 字段筛选，W15 严格按固定 scene_id，不从结果或指标推断分组。输场和赢场都保留，不按 A1T 与 RBF 表现筛选。
- 所有逐事件统计按原 scorer 时间窗：ALL `[0,20)`、PRE `[0,5)`、POST `[5,20)`。event-only 指标使用各窗内实际事件；hold 指标只用首个更新后到 20 s 的非事件 transition，并报告真实样本数。
- 分别汇总 network-fit、beta/clip 可行参照与二范数界、hold freshness 三类的各轴 signed mean/RMS、三轴向量 RMS、物理重算误差及 clipping/saturation 计数。保留每场 raw/audit/release、deployment、runner、scorer、物理 helper 的 SHA。全 12 未完成并审计 PASS 前，结果整体状态只能为 `INCOMPLETE`。
- 不以单场 C5/RBF 或旧训练标签 RMSE 作为该诊断的分母/真实标签；本报告不重评分闭环 winner gate，也不修改既有 paired-score 文件。没有预登记数值胜负阈值，不根据结果增减分组、调限幅或追加结构实验。

## 禁止事项

零 Plant、零 episode/engine 调用、零闭环积分、零训练/optimizer、零 TEST 读取；不改 A1T/A1R runner、engine、模型、数据、raw、manifest、auditor 或既有报告。Oracle `C*` 使用真实物理状态，仅作逐状态机制对照，不能拿去部署或作为本任务已训练模型成绩。任务书本身不授权实现或执行；Root 先审方案和后续最小源码，再另行决定是否运行。


