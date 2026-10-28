# 姿态 TCN 替代：文献近邻与应用贡献边界 v4

检索核对日期：2026-10-26（Asia/Shanghai）。本附录补充 v3，不修改冻结任务书、方法或验收门槛。方法细节只根据可读取的原论文/作者材料陈述；无法读取的闭源论文只登记书目信息与待核事项。

## 新核对的直接近邻

| 工作 | 原文核对结果 | 对本项目定位的影响 |
|---|---|---|
| Tao Yang, Huai-Ning Wu, Jun-Wei Wang, [“cc-DRL: A Convex Combined Deep Reinforcement Learning Flight Control Design for a Morphing Quadrotor”](https://doi.org/10.1109/TCYB.2025.3580074), *IEEE Transactions on Cybernetics* 55(9), 4554–4566 (2025); [原文预印本](https://arxiv.org/abs/2408.13054) | 原文明确研究四个变臂长的变形四旋翼，同时控制位置和姿态；对 16 个代表性形态分别用 PPO 训练控制律，再以凸组合形成覆盖形态空间的控制方案；论文提供仿真结果。方法细节按 arXiv 原文核对，期刊书目按 DOI/PubMed 记录核对。 | 这是与本项目平台/任务最直接的先例。不能声称首次对主动变形四旋翼使用深度学习、首次做变形位置与姿态控制，或首次在形态变化下学习控制。它是整机控制律与形态插值；本项目候选只替换现有 BS 姿态环中的 RBF 补偿接口，位置环和主控制栈保持不变。 |
| Chun-Xiao Li, Huai-Ning Wu, Tao Yang, [“Coordinated Control of Flight and Morphing for Morphing Quadrotor via Reinforcement Learning”](https://doi.org/10.1109/TAES.2025.3574295), *IEEE Transactions on Aerospace and Electronic Systems*, 61(5), 12755–12766 (2025) | 出版商 DOI/书目信息可确认该工作已发表。本文检索时 IEEE 全文页不可读取；不据二手摘要断言其具体控制结构、实验设置或性能。 | 题名已显示其与“飞行控制和形态变化协同”直接相邻。投稿前需取得并核对全文，特别确认其控制对象、可用信息、形态执行器、任务和验证方式；在此之前不得作“首次协同控制”或“此前没人研究学习式变形飞行控制”的主张。 |
| Jonghyun Woo et al., [“A Comprehensive Framework for Modelling and Control of Morphing Quadrotor Drones”](https://doi.org/10.3390/aerospace13010005), *Aerospace* 13(1), 5 (2026) | 出版社页面摘要/正文描述扩展变形飞行器，动力学显式包含质心与惯量变化，采用反馈线性化、LQR、EKF，并讨论构型与故障恢复；证据为数值仿真。 | 变形构型下显式惯量建模与控制已有近邻。本项目不使用形态相关惯量重建，可作为信息预算和实现路线的区别；不能把“惯量变化影响变形飞行”本身当作新发现。 |
| Jonas Eschmann, Dario Albani, Giuseppe Loianno, [“RAPTOR: A Foundation Policy for Quadrotor Control”](https://arxiv.org/abs/2509.11481), *Science Robotics* 11(114), eaec1481 (2026), [期刊记录](https://pubmed.ncbi.nlm.nih.gov/42127208/) | 原文描述 1000 个 RL 教师蒸馏为一个递归学生，并在 10 种真实四旋翼上评估。学生通过历史上下文隐式识别动力学，不显式回归惯量等参数。 | 深度学习、教师蒸馏、序列输入、隐式适应都不是本项目独有；RAPTOR 的目标是多平台整机控制和跨机型适应，本项目不是 foundation policy，也不主张跨平台泛化。其结果进一步说明“不显式重建惯量”是一种可行设计选择，但不替代本项目自身的闭环证明。 |

## 与冻结候选的精确差异

冻结候选是 13 输入、15 事件因果 TCN，用 B 姿态 RBF 的日志动作作离线监督；部署时替换 RBF 补偿输出和权重更新。控制栈保留 DSSM14 位置环、BS 名义姿态控制器、固定名义惯量 (J_0) 以及原有输出限幅和 startup beta。候选不读取 \hat{J}、\dot{\hat J}、Plant 真值或 RBF 隐状态，也不运行 physics feedforward 或 observer。故准确表述是“在主动变形仿真控制栈中，以因果 TCN 替换姿态 RBF 补偿接口，且不向该候选提供时变惯量重建”。不能说成完全无物理模型，也不能声称 TCN 独立发现了优于教师的新控制律。

## 应用层主张如何落到现有证据

1. **闭环替代效果：**按冻结任务书在相同任务、配置和计分下，与 B 比较位置 (Q_{0-20})、SO(3) 姿态误差、逐场胜负、风组、执行器与安全状态；原 C5_RBF 和 C5_10 物理前馈为次级对照。TCN 的离线动作拟合误差不能代替这些闭环结果。
2. **主动变形应用证据：**GHP7 双向窄门 pilot scorer 已包含双向通行、15 mm 配置几何余量、最小 clearance 和 application-feasible 判定，并会同报告位置/姿态跟踪。该任务只能支持“仿真配置几何包络 proxy”。Plant 没有墙体接触/碰撞响应；电池外形被假设包含在机身内，桨盘尺寸基于估计值。因此不能表述为实机安全通行、碰撞测试或安全认证。
3. **证据级别：**六场 GHP7 是配对方向与安全筛查，不是显著性或普遍应用效果证明。论文主性能仍由冻结任务书的 DEV72 和一次性 TEST48 配对门决定；如果只在六场 gate pilot 上见到改善，结论必须限于个案仿真。
4. **适用边界：**当前证据来自单一训练 seed、一个仿真 Plant、理想形态命令跟踪、冻结 BS 控制器和固定 (J_0)。没有实机验证、传感器噪声/形态跟踪误差测试、跨平台或跨 seed 证明。论文应逐项写明，不把仿真 proxy 泛化成真实穿越能力。

## 决策

- 维持深度学习 TCN 为唯一主候选；不把 \hat{J}/\dot{\hat J} 输入或惯量前馈拼进 TCN。C5_10 只作为单独的物理参照，且必须披露其信息条件不同。
- 保留冻结的训练、parity、pilot、DEV72、TEST48 顺序，不因新增文献搜索改变代码、任务、统计规则或测试封存状态。
- 暂不写“新控制方法”贡献。若完整配对结果达标，贡献候选是一个受限、可复现的应用结论：在指定主动变形仿真任务和上述接口条件下，TCN 是否能替代姿态 RBF，并保持/改善跟踪与几何通行 proxy。
- 在投稿前取得 Li et al. (2025) 的全文并逐项核对；若无法获得，则在相关工作中只写可由出版记录支持的事实，并主动缩窄 novelty claim。

## 来源与访问记录

- Yang et al. (2024/2025) 原文 HTML：<https://arxiv.org/html/2408.13054>；具体方法核对了摘要、引言、算法说明及仿真章节。期刊 DOI/书目信息：<https://doi.org/10.1109/TCYB.2025.3580074>。
- Li et al. (2025) 出版商 DOI：<https://doi.org/10.1109/TAES.2025.3574295>；IEEE 全文页无法访问，本附录不采用二手来源中的方法细节。
- Woo et al. (2026) 出版商论文页：<https://www.mdpi.com/2226-4310/13/1/5>；核对摘要和模型/控制章节。
- Eschmann et al. (2026) arXiv v2 原文：<https://arxiv.org/html/2509.11481>；期刊记录：<https://pubmed.ncbi.nlm.nih.gov/42127208/>。
- 本地证据：`DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_FROZEN_ZH.md`、`ATTITUDE_TCN_INERTIA_AND_RBF_ISOLATION_AUDIT_v1.md`、`INERTIA_RECONSTRUCTION_DECISION_v2.md`、`matlab/score_tcn_ghp7_pilot_v2.m`。
