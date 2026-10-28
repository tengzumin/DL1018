# 姿态环深度学习路线：文献定位核验

检索日期：2026-10-26。书目信息以 Crossref DOI 元数据核对；方法范围按原论文摘要/正文核验。

## 直接相关工作

1. Che, H., Chen, J., Bai, G., & Wang, J. (2023). [A Modified Model-Free Adaptive Control Method for Large-Scale Morphing Unmanned Vehicles](https://doi.org/10.3390/drones7080495). *Drones, 7*(8), 495. 该工作研究大型变形无人机姿态控制，使用输入/输出数据构造双环数据模型和模型自由自适应控制，并给出闭环有界性、跟踪误差收敛分析与数值仿真。它说明“形态变化下的姿态数据驱动控制”已有直接先例；本项目不能把“用学习器替换一个补偿器”称作首个形态飞行器数据驱动控制方法。

2. Ren, W., Wei, Y., Wang, C., & Wang, Z. (2025). [Finite-Time Adaptive Reinforcement Learning Control for a Class of Morphing Unmanned Aircraft with Mismatched Disturbances and Coupled Uncertainties](https://doi.org/10.3390/drones9080562). *Drones, 9*(8), 562. 该工作在变形无人机上研究自适应强化学习控制，并针对不匹配扰动与耦合不确定性引入自适应上界估计。它属于更广义的变形飞行器，不等于已经验证了本项目的主动变形四旋翼位置/姿态组合控制栈。

3. Hwangbo, J., Sa, I., Siegwart, R., & Hutter, M. (2017). [Control of a Quadrotor with Reinforcement Learning](https://arxiv.org/abs/1707.05110). arXiv:1707.05110. 该工作学习从飞行器状态到旋翼推力的神经策略，并报告仿真和真实四旋翼验证。它支持神经策略用于四旋翼控制的可行性，但没有覆盖本项目的主动变形结构或“在既有位置环中替换姿态 RBF”这一接口。

## 对本项目的定位约束

当前 TCN 的训练标签是 B 姿态 RBF 的记录动作，定位应是**冻结深度网络替代既有自适应 RBF 补偿头的应用验证**。监督模仿本身不构成新的控制理论；只有当同一位置环、BS 姿态名义控制器、Plant、allocator、场景身份和指标下，DEV72 与封存 TEST48 均达到任务书门槛，才可主张该替换在本仿真范围内改善了主动变形任务表现。

方法描述须写明：运行时不重建形态相关惯量、不估计惯量变化率、不读 Plant 真值或 RBF 隐状态；固定名义 `J0` 仍用于既有加速度补偿到力矩的控制接口，输入含形态命令。因此本系统不应被称为完全 model-free；结果范围限于理想命令驱动变形仿真，不外推到有执行器滞后、臂长传感误差或真实飞行。

C5_10 的命令驱动惯量前馈只作为独立物理参照。其优势可说明模型先验在当前仿真的价值，不能归因于 TCN；若以后把物理项加入网络候选，需新建独立候选并分别报告网络与物理项贡献。

## 参考核验

- Crossref 核验 DOI：`10.3390/drones7080495`、`10.3390/drones9080562`、`10.1016/j.ast.2023.108540`。
- Hwangbo 等原论文页面：arXiv:1707.05110；其正文报告了仿真与实机 quadrotor 实验。
- 该清单是路线定位用的初筛，不代替投稿前逐篇阅读全文、核对实验设置和生成正式 BibTeX。
