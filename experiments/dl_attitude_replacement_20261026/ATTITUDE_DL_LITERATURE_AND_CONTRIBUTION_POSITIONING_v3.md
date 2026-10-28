# 姿态 TCN 路线：文献与贡献边界 v3

检索核对日期：2026-10-26（Asia/Shanghai）。本文件补充 v2，不覆盖 v2 的初筛记录。DOI 元数据用 Crossref 核对；具体方法描述对照原论文摘要/正文、作者论文页或代码仓库。范围是定位近邻，不是穷尽综述。

## 新增的直接近邻

| 论文 | 可支持的结论 | 与 DL1018 的区别 |
|---|---|---|
| Yan Zong, Ningyun Lu, Bin Jiang, [*Synthesising Controllers for Quadrotors via Imitation Learning*](https://doi.org/10.1109/CAC59555.2023.10451191), CAC 2023, pp. 8637–8641. [作者论文 PDF](https://yzong.com/pub/Zong2023a.pdf) | 四旋翼控制器的专家 I/O 模仿、特征设计、直接输出推力/力矩及 DAgger 已有先例。原文报告仿真跟踪。 | 学习整体策略输出，不是主动变形四旋翼固定 BS 栈内的姿态 RBF 补偿口替换。 |
| Shuo Li, Ekin Ozturk, Christophe De Wagter, Guido C. H. E. de Croon, Dario Izzo, [*Aggressive Online Control of a Quadrotor via Deep Network Representations of Optimality Principles*](https://doi.org/10.1109/ICRA40945.2020.9197443), ICRA 2020, pp. 6282–6287. [arXiv 原文](https://arxiv.org/abs/1912.07067) | 离线神经网络模仿最优控制器并输出控制动作已有先例；论文报告仿真和真实飞行。 | 学习最优状态到控制映射，不涉及 morphing 或 RBF 子模块蒸馏替代。 |
| Jonas Eschmann, Dario Albani, Giuseppe Loianno, [*RAPTOR: A Foundation Policy for Quadrotor Control*](https://doi.org/10.1126/scirobotics.aec1481), *Science Robotics* 11(114), eaec1481, 2026-05-13. [arXiv 原文](https://arxiv.org/abs/2509.11481), [作者代码仓库](https://github.com/rl-tools/raptor). | 多个 RL 教师策略蒸馏成递归学生、再跨多种真实四旋翼评估，已是近期先例；“四旋翼教师蒸馏”本身不能作为 DL1018 的新颖性主张。 | RAPTOR 面向跨机型的整机基础策略和上下文适应；DL1018 只检验主动变形仿真栈里一个固定接口的姿态补偿替换。 |

原 v2 中关于 morphing UAV 数据驱动控制、morphing UAV 的 RBFANN、以及四旋翼 TCN 动力学建模/MPC 的近邻仍然相关：Che et al. (2023)、Derrouaoui et al. (2024)、Saviolo et al. (2022)、Looper & Waslander (2021)。这些工作进一步限制“TCN”“动作学习”“变形飞行器控制”各自可单独主张的新颖性。

## 对当前方法的准确表述

当前正式候选是 **B 姿态 RBF 动作的离线教师蒸馏**：用 B 原始日志里每个姿态事件的 `rbf_output_raw` 监督 13 输入、3 输出、15 事件历史的因果 TCN。源码确认 `rbf_output_raw` 是 RBF 权重更新前得到、经 `dmax` 限幅、startup beta 前的动作；部署时以 TCN 替换 RBF 的姿态输出和在线更新，并施加相同的输出限幅、beta 和固定名义 J0 力矩映射，不估计时变惯量。准确说法是“在仿真主动变形四旋翼姿态环中，以 RBF 教师监督的因果 TCN 替换 RBF 补偿接口”，不能称为独立于 RBF 教师的学习、无惯量模型控制或新自适应控制理论。

目前可验证的应用层贡献只能是：**在固定名义控制器、无时变惯量重建的条件下，严格配对评估该 TCN 是否能在主动变形场景中替代姿态 RBF，并同时满足任务书的位置、姿态和安全门槛。**这一表述只有在完成任务书规定的 parity、6 场 pilot、DEV72 与一次性 TEST48 后才可作为结果。6 场 pilot 只能作安全和方向筛查；VAL48 用于 checkpoint 选择，不能包装成独立测试。

## 关键性能风险与待证机制

1. **教师动作不是只由当前状态决定。** B 的 RBF 有在线权重状态并按控制误差更新；学生没有读取这些权重，只保留 15 个事件的输入历史。相近的短窗特征可能对应不同的教师隐藏权重和输出。该状态混叠目前是合理的机制风险，尚未由单独的碰撞/可辨识性分析证明。
2. **离线动作拟合不等于闭环性能。** 当前训练最小化的是 B 状态分布上的教师动作误差；学生闭环一旦偏离教师轨迹，会遇到分布偏移。17k 的 VAL 归一化动作 RMSE 复算一致，只证明 checkpoint 计分可复现，不证明候选优于 B。
3. **训练协议偏差需披露。** 正式 v2 与无效 v1 诊断任务曾在同一 GPU 并发，已由 Amendment06 记录。v1 目标错误，必须排除；单次训练和单个 seed 不支持跨种子可靠性结论。
4. **适用域有限。** 现有证据是仿真、理想形态命令跟踪、固定名义 (J_0) 接口；不支持实机、真实形态传感器误差、滞后、跨平台或跨训练种子泛化主张。

## 当前决策

- 不把惯量重建并入 DL_TCN 主候选。C5_10 等基于几何先验的惯量前馈只作为单独的 physics-informed 诊断参照，明确不同信息预算与理想命令跟踪假设。
- 不宣称 TCN、行为克隆、教师蒸馏或 morphing-UAV RBF 是本项目首创。
- 先完成冻结训练与 parity，再按 pilot → DEV72 → 封存 TEST48 的原任务书顺序决策。闭环失败后，才根据 trace 检验短历史状态混叠、分布偏移等假设；本文件不启动新训练、不改验收门槛，也不解封 TEST。
