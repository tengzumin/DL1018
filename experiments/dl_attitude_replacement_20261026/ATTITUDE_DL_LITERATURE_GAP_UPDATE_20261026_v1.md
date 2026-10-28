# 姿态 TCN 文献缺口补充审计（2026-10-26）

状态：补充文献审计；不修改冻结任务书、训练输入或运行中实验。  
范围：核对主动变形四旋翼的深度学习姿态/飞行控制先例，修正论文贡献措辞。仅将原论文、作者预印本和出版方页面用于技术判断。

## 新确认的直接先例

### 1. cc-DRL 已研究四臂变长四旋翼的位置与姿态控制

Yang, Wu & Wang, “cc-DRL: A Convex Combined Deep Reinforcement Learning Flight Control Design for a Morphing Quadrotor,” *IEEE Transactions on Cybernetics*, 55(9), 4554–4566 (2025), DOI [10.1109/TCYB.2025.3580074](https://doi.org/10.1109/TCYB.2025.3580074). 作者预印本：[arXiv:2408.13054](https://arxiv.org/abs/2408.13054), [全文 HTML](https://arxiv.org/html/2408.13054v1).

作者在四个变长机臂的变形四旋翼上训练 16 个代表机臂长度模式的 PPO 控制器，并按臂长对策略作凸组合；控制器直接输出四个旋翼速度，覆盖位置和姿态。仿真包含 20 秒 figure-8 轨迹及非对称机臂变化。论文的动力学方程明确含时变转动惯量；运行策略以状态和机臂长度组合权重，不等于部署时显式重建 \(\hat J(t)\) 或 \(\dot{\hat J}(t)\)。其“model-free”是指 PPO 控制策略，不代表仿真 Plant 不含惯量模型。

**影响：**本项目不能声称“首次用深度学习控制主动变形四旋翼”“首次不用动力学模型”或“首次解决变形下姿态控制”。此先例也说明深度学习主线并不要求把惯量重建放进网络；可以由数据策略吸收部分形态相关动态影响，同时不显式计算惯量。

### 2. 变形 UAV 姿态自学习控制已有先例

Huang et al., “Online self-learning attitude tracking control of morphing unmanned aerial vehicle based on dual heuristic dynamic programming,” *Aerospace Science and Technology*, 143, 108727 (2023), DOI [10.1016/j.ast.2023.108727](https://doi.org/10.1016/j.ast.2023.108727). 出版方摘要介绍了部分 model-free 的 DHP 姿态跟踪方法，并通过 RLS 识别增广系统、结合不确定性补偿。它属于形态 UAV 姿态学习控制的直接先例，但不是本项目的冻结 TCN 模块替换实验。

Cao et al., “Intelligent Attitude Control for Morphing Flight Vehicle: A Deep Reinforcement Learning Approach,” *IEEE Transactions on Vehicular Technology*, 74(6), 8851–8865 (2025), DOI [10.1109/TVT.2025.3541606](https://doi.org/10.1109/TVT.2025.3541606)，是变形飞行器姿态 DRL 的进一步先例。当前能核验的出版记录与摘要只足以确认主题与 TD3 训练方向；未据此推断它的飞行器结构、传感器接口或与本项目的定量可比性。

### 3. TCN 与四旋翼学习控制也已有基础

Saviolo, Li & Loianno 的 PI-TCN 工作学习四旋翼时序动力学并用于 MPC，且有真实飞行验证（RA-L 2022，DOI [10.1109/LRA.2022.3192609](https://doi.org/10.1109/LRA.2022.3192609)）。这支持 TCN 用于四旋翼时序建模的可行性，不是姿态 RBF 输出蒸馏或变形四旋翼模块替换的证据。

## 与 DL1018 冻结候选的边界

DL1018 的候选是**一个因果 TCN 模块**：在原 C5 DSSM14 位置环和 BS 姿态名义控制器上，替换姿态 RBF 补偿输出；教师目标为离线记录的 RBF 动作，推理仅用冻结任务书规定的可测因果特征和变形指令，输出再按固定名义 \(J_0\) 及原有边界映射。它不计算或读取时变 \(\hat J\)、\(\dot{\hat J}\)、Plant 惯量真值、RBF 隐状态或 observer 状态。它既不是端到端 PPO，也不是纯“model-free”整机控制器。

与 cc-DRL 的可检验差异是控制接口和部署方式：cc-DRL 训练多个代表形态策略并直接控制旋翼；DL1018 只替换现有控制栈中的姿态补偿头，保留位置环、BS 主控制、分配器和执行器链路。论文若能成立，贡献应限定在这个**受约束的姿态补偿模块替换及其严格配对仿真证据**，而不是新的通用控制理论。

## 论文表述与证据要求

- 相关工作必须正面讨论 cc-DRL、DHP 姿态自学习及 morphing-UAV DRL；不得只以“尚无相同 TCN/RBF 代码”推导创新性。
- 不宣称首次深度学习、首次 model-free 或完全无模型；现有 BS 与固定 \(J_0\) 仍是控制栈的一部分。
- 可检验的窄贡献是：单个冻结因果 TCN 是否能在不显式惯量重建的情况下替代姿态 RBF 补偿，并在相同主动变形场景中对 B 改善位置与姿态，同时保持安全约束。
- 教师动作拟合只证明模仿程度。主证据仍必须来自配对闭环结果、风况分组、安全指标和封存 TEST。
- 不把公开论文结果与 DL1018 仿真数值直接作头对头优劣比较。未找到可核验的 cc-DRL 作者代码仓库；有限仓库搜索不能证明代码不存在。

## 来源与复核范围

- [cc-DRL 作者预印本全文](https://arxiv.org/html/2408.13054v1)：检查了 12 维状态、四旋翼速度动作、16 个代表臂长模式、在线凸组合、含时变惯量的动力学表达及 figure-8 仿真章节。
- [cc-DRL 期刊 DOI](https://doi.org/10.1109/TCYB.2025.3580074)：用于发表版本书目信息。
- [DHP 论文 DOI](https://doi.org/10.1016/j.ast.2023.108727)：依据出版方摘要定位其姿态自学习与 RLS 识别范围。
- [形态飞行器 DRL 姿态论文 DOI](https://doi.org/10.1109/TVT.2025.3541606)：仅用于书目和题目/摘要层面定位。
- [PI-TCN 论文 DOI](https://doi.org/10.1109/LRA.2022.3192609)：用于四旋翼时序网络相关工作定位。
