# 姿态环 RBF 替换失败后的下一步证据审查

日期：2026-10-25。目的：为下一步非 RBF 姿态环选择一个可证伪的小实验。只综合已有审查报告、模型/训练源码与公开一手论文/作者仓库；没有读取 TEST、raw、MAT 或数据缓存，也没有运行代码、训练或闭环。本建议不判断已证实根因。

## 现有证据与边界

| 已有候选 | 与同 C5 位置栈 + 在线姿态 RBF 比较 | 可支持的结论 |
|---|---|---|
| C5_24，12 场 DEV | 位置 Q 2 胜/10 负；SO(3) 2 胜/10 负 | 首轮姿态 RBF 替代筛查失败；原始 B 的位置栈不同，不用于姿态单因素归因。 |
| C5_COVERAGE33，15 场 DEV | 位置 Q 3/15 胜；SO(3) 1/15 胜。宏平均 Q 0.0146855 对 0.0103309 m，SO(3) 0.0436700 对 0.0152443 rad | 扩展静态监督覆盖后仍未通过预设闭环门槛。15 场均为开发证据。 |
| 冻结 C5_COVERAGE33 的标签拟合 | TRAIN/DEV NRMSE 0.015295/0.267078，DEV/TRAIN = 17.46；scene-block 95% CI 为 11.92–27.68 | 同一固定模型的跨场离线差距很大；它不是闭环收益估计，也不证明差距的成因。 |
| 首个形变事件 | C* 映射向量 RMSE 0.897 rad/s²；同一事件置于教师状态仍为同量级。active-phase 候选/教师残差为 3.232/3.217 rad/s² | 误差早于候选长时漂移。此证据不能区分函数逼近不足、遗漏状态、噪声或 teacher 标签与部署动作坐标不适配。 |

来源见本报告末尾的项目输入清单。闭环统计与离线拟合分别按场景汇总，不能把 2/12 与 3/15 当作独立重复实验合并，也不能把 DEV 结果写成 TEST 结论。

代码说明当前 CM18 是逐事件静态前向网络，结构为 18→32→32→24，再乘形态基向量。输入为 omega_B(3)、alpha_BS(3)、thrust/mass(1)、u(4)、过去命令积分 z(4)、上一完整区间平均力矩 a(3)。其中已有部分历史摘要；现有证据并未证明哪组可删。现有根因报告指出，在理想形态模型下 rho、rhoDot、phase 可由 command 与 z 重建，因此把它们额外拼接不能作为“新增信息”的证据。

## 原始论文和官方代码

1. Ross、Gordon、Bagnell，DAgger，AISTATS/PMLR 2011：[原论文](https://proceedings.mlr.press/v15/ross11a.html)。它针对策略动作改变后续观测分布、从学习者诱导状态收集专家标签的序列预测问题。它说明静态监督可能遇到策略分布偏移；不保证能修复教师状态上已经出现的映射误差，也不直接适用于本项目的 C* 残差回归。
2. Zhou 等，Hybrid offline–online neural identification-based robust adaptive tracking control for quadrotors，Control Engineering Practice 2024：[DOI 原文](https://doi.org/10.1016/j.conengprac.2024.106032)。论文把历史状态的时间相关性交给 LSTM，并用在线更新估计残差力/力矩，在四旋翼仿真和实机上验证。它支持“动态上下文 + 在线残差适应”是已有研究方向；不同平台、模型与控制律的结果不能推出本项目姿态环会改善。未发现该论文的作者代码库。
3. O’Connell 等，Neural-Fly，Science Robotics 2022：[作者论文/arXiv](https://arxiv.org/abs/2205.06908)。其方法学习跨风况共享表示，并在线适应低维线性系数；论文报告风洞及户外飞行结果。它展示了受结构约束的非 RBF 在线适应先例，不是变形姿态环或本项目教师标签的验证。

有用的作者实现只有一个：[Neural-Fly 官方仓库，固定提交](https://github.com/aerorobotics/neural-fly/tree/0ed50246b1f1db194e8f0726749351636d3501bf)。仓库 README 说明提供 DAIML 训练/验证脚本、数据和实验记录，可参考表示学习与验证组织；它不提供可直接替换本项目姿态环的完整控制器。引用代码库不代表复制或运行其中代码。

## 建议的最小、可证伪路线

建议暂停继续扩大同一静态 X18→C*/beta 监督集，先走一条**输入充分性诊断 → 小型非 RBF 适应器 → 固定 DEV 闭环探针**的路线。第一步不预选 GRU、不删通道，也不把 rho/rhoDot 当新信息；用场景阻断的离线诊断比较完整 X18 与可部署、物理可解释的候选输入组，重点报告首次形变及 active-phase 的逐场残差和 scene-block bootstrap。已有项目的离线可辨识性任务书提供了 X18 对形态估计替换的诊断思路，但其状态横幅为“未审批 / 已取代 / 未执行 / 不得运行”；本审查没有运行或授权复用旧任务书。需先有新、有效的协议，且输入只来自允许的 TRAIN/DEV 标签与已审材料。

若诊断找到稳定、非冗余的最小信号组，后续候选再采用低维、带投影/泄漏约束的线性参数自适应补偿，更新信号来自实际姿态/角速度跟踪误差，保持原 C5 名义栈和输出接口；这不使用 RBF，也不依赖继续拟合更多静态 teacher 行为。最小对照是：冻结静态 CM18、该自适应候选、同栈 C5+在线 RBF 三臂，在预先锁定的少量 DEV 场景逐场配对；先完成无 Plant 的特征/输出/时序审计，再做 4 场工程筛查，至少覆盖三种任务和高风/低风形变。预先登记全程 Q、SO(3)、首变形/active-phase、峰值、饱和/限幅、安全停止、推理延迟与复位一致性。任何安全失败、持续超时、或候选未在预登记主要姿态指标上优于静态 CM18，立即否定本轮方向；小批筛查通过仍只能说明可继续 DEV 验证，不能宣称独立泛化。

它比再给同一静态输入映射增加标签更有鉴别力：33 场静态候选仍未达到闭环门槛且有 17.46 倍 DEV/TRAIN 残差差距，静态标签覆盖已经扩过；当前不确定性转向“哪些部署可见信号含有稳定的增量预测信息”。建议先测这个差异，再决定适应器。该顺序是推断，不是已证实更有效。

主要失效风险是可部署候选输入仍与 X18 等价、场景数少导致区间宽、teacher C* 与闭环动作的关系不适用、在线估计追踪噪声并放大闭环误差、投影/泄漏参数不足以保证稳定，以及 100 Hz 更新到 1 kHz Plant 的时序与实现偏差。上述风险要求固定小批配对与动作/输出审计，不能由离线 NRMSE 消除。

## 本地输入文件及 SHA-256

以下为本审查实际依赖的项目报告与代码文件 SHA-256；未读取其引用的 raw/MAT 内容。

| 输入 | SHA-256 |
|---|---|
| reports/attitude_cm18_c524_screen12_20261025/C524_SCREEN12_RESULT_v1.md | b2bb74826dd11ab82f6af714df15345b1a9db419dc93412204e075a694857988 |
| reports/attitude_cm18_c524_screen12_20261025/C524_ROOT_CAUSE_DECISION_v1_ZH.md | f040721064031668b7b8ae9bc14c444fc605645a462d22c9754e168a5de9c2d6 |
| reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md | 41c38fe91ff121be1853826db94e830ad4c3a76ebee8623bcab0de5cd6a2a3c3 |
| reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1/FIT_GENERALIZATION_REPORT_v1_ZH.md | d2305c87118e638345b9da13784d3c58d00d01a9cbf3394d5866befdbafba34c |
| reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_ROOT_CAUSE_DIAGNOSIS_v1_ZH.md | d564d77133e2752d327450c9cedb5d7c3d946c1988dc58fc7720fa39b25d4894 |
| reports/attitude_cm18_c524_coverage33_20261025/C5_CM18_OFFLINE_IDENTIFIABILITY_TASKBOOK_v1_ZH.md | 47a1e78a9eba62abb32b825008522031d2dcfef64f5e97e9fe11d9da0a515a04 |
| reports/attitude_cm18_c524_screen12_20261025/C524_COVERAGE33_TASKBOOK_v2_ZH.md | 934fc1b8a614c5a32993add65a0aee89d48e7c31ea368646063e5576b78c7017 |
| experiments/attitude_cm18_a1_20261024/model_cm18_v1.py | ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6 |
| experiments/attitude_cm18_c524_coverage33_20261025/train_c5_coverage33_v1.py | 53e23f688633e95e4e8386e186dcba4cbb166cc3a4a1acaa542e84eaea337fc3 |
