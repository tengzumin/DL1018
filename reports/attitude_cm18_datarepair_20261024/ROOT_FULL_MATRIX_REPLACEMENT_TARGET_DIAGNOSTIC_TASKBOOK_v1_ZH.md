# 姿态 RBF 替代：完整三轴同状态目标核验任务书

2026-10-25，Root。仅放行离线诊断的实现，源码审核后方可执行。0 Plant、0 optimizer、0 TEST，不改变已冻结数据提取函数与训练集。

## 为什么做

Root 的 yaw 逐事件复算及非作者复核均表明：旧行为残差标签 `d_old` 与直接替代接口的理想补偿量一般不同。四场中即使精确输出旧标签，同状态 yaw 加速度误差 RMS 仍为 0.11968–0.20698 rad/s²。这是当前部署接口下的目标一致性问题，不能仅靠扩网络消除；也不证明重新训练一定改善闭环。

下一步只将此核验扩展到实际三轴与分配器。不能把 yaw 的标量公式直接用于有分配耦合的 roll/pitch。

边界：这不是宣称 residual 学习普遍错误。若在线或递归结构准确追踪依赖当前动作的残差，并满足收敛条件，它可能通过固定点获得合适补偿；现有输入也含过去动作，不能忽略这种可能。当前检查仅判断旧标签与直接同状态理想动作是否一致，后续必须用与实际递归时序对应的实验区分，不能据此自动替换训练目标。

## 固定输入与方程

仅四份已审 matched-position probe raw（T1_B、T1_C5、T3_B、T3_C5，1999 事件各），路径与 SHA 以冻结 `offline_label_decomposition_v2/MATCHED_POSITION_LABEL_DECOMPOSITION_v2.json` 为准，其 SHA `2c98a3e6ce6915bb03e00c4a74db1415ac1f71c2515773b48b3e4fa173f60093`。不得读 VAL/TEST、重新采集或调用 episode。

读取并锁定实际 `allocate_control.m`、`controller_parameters.m`、`simulation_parameters.m`、`allocation_matrix.m` 与质量属性依赖。允许调用纯分配器作同状态代数检查，禁止 Plant 积分。令 C0 为固定 controller allocation、Ct 为真实 Plant allocation，L 为 `[zeros(1,3);J0]`。在 actuator 理想且该请求无裁剪/饱和时：

```text
G = Jtrue \ ((Ct * (C0 \ L))(2:4,:))
wrench0 = Ct * (C0 \ [T; tau_nom])
E0 = Jtrue \ (wrench0(2:4) + windTorque - gyroTrue - JdotTrue*omega) - alphaBS
alpha(c) - alphaBS = E0 - G*c
d_old = E0 + (I-G)*c_old
c_star = G \ E0
```

以上是数学表达式，不是可直接粘贴的 MATLAB 下标语法。`c_old=J0\tau_comp_old`；alphaBS 使用固定 J0/Jdot0 定义。不能把 G 简化为 Jtrue\J0 而漏掉真实与名义 allocation 差异。真实几何与风仅用于离线核验。

## 必须核验

1. 对当前实际请求，通过纯 `allocate_control` 重建 realized wrench，与 raw 逐事件核对；同时核 request=nominal−applied compensation 及完整残差标签闭合。
2. 由零补偿物理式计算 E0，并独立核 `E0=d_old-(I-G)c_old`。条件差、奇异或数值异常必须报告，不静默正则化。
3. 对 c_star 用完整分配器重算同状态真实加速度。分别报告“线性理想式”和“经过实际限幅/电机约束后”的误差，不把不可行理想动作当成可部署动作。
4. 检查现有候选输出 clip（约 `[45,45,4.7124]`，必须从已冻结部署文件读取精确值，不按本行舍入值计算）、固定 beta 及时序约束；报告 c_star 输出超界数与相应误差，不能修改 clip 或阈值。当前补偿是施加后的加速度量，若比较部署输出须明确 beta 换算与 beta=0 的处理。
5. 每场/逐轴报告旧标签与 c_star 的 RMS 差、精确输出旧标签时的同状态误差、c_star 理想/受限误差、G 条件数、可行性及所有失败。yaw 与已审标量结果交叉核对。

预期：当 G 非 I 且旧动作不是理想补偿时，旧标签与 c_star 有系统差异。若实际完整分配器否定线性前提或 c_star 不可行，停止把该式当成直接重标注方案，先解释差异。此任务不选模型、不改标签、不宣称闭环改善或稳定。

## 交付与保护

最少一个 MATLAB 入口，scalar JSON 汇总及可复算的小型数值表，产物不超过 16 MiB，独立版本目录且不覆盖。先核一场再扩四场的执行顺序可放同一离线入口；任何失败保留并停止，不自动修复重跑。Root 执行并最终审核，之后另行决定是否启动单因素重标注/训练。
