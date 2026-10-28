# 姿态 TCN 替代：2025 年变形飞行器 DRL 姿态先例补充 v5

核对日期：2026-10-26（Asia/Shanghai）。本文件补充 v4；只更新文献定位，不改冻结方法、任务书、验收门槛、代码或 TEST 封存。

## 新完成的全文核对

Cao, Li, Ding, Huang, Yang, and Gui, [“Intelligent Attitude Control for Morphing Flight Vehicle: A Deep Reinforcement Learning Approach,” *IEEE Transactions on Vehicular Technology*, 74(6), 8851–8865 (2025)](https://doi.org/10.1109/TVT.2025.3541606). 本轮读取了作者上传的全文 PDF（ResearchGate 作者内容页：[全文](https://www.researchgate.net/publication/389082922_Intelligent_Attitude_Control_for_Morphing_Flight_Vehicle_A_Deep_Reinforcement_Learning_Approach)）。

原文核对要点：

- 平台是有折叠翼构型的固定翼 morphing flight vehicle，不是四旋翼；姿态控制目标包括滚转、俯仰、偏航跟踪。
- 控制器用 TD3 离线训练一个 PID-like 深度网络，把姿态误差相关状态映射到舵面等效控制；部署时用冻结参数，不在线更新。它学习的是姿态控制策略，不是模仿 RBF 补偿。
- 翼面形态轨迹按任务预先给定，是开环 morphing command；姿态策略需在这些形态变化和不确定性下跟踪。
- 证据是仿真：包括 2,000 次 Monte Carlo 扰动试验、将训练不确定性范围扩大 50% 的仿真，以及变化任务的仿真。没有实机飞行验证。

因此，此前 v1 中“全文未取得”的记录已过时。该全文提供直接近邻，明确排除“首次将深度学习/DRL用于变形飞行器姿态控制”这一主张。它仍与 DL1018 有重要区别：机型、控制通道、学习目标和实验任务都不同；本项目是主动变形四旋翼，在冻结 BS 姿态控制接口中，以 13 输入、15 事件历史的冻结 TCN 蒸馏 B 的 RBF 补偿动作，不使用形态相关惯量重建，且包含双向窄门的配置几何 clearance proxy。

## 对论文贡献与实验的影响

1. **新颖性边界收窄：**不得声称首个变形飞行器深度学习姿态控制、首个冻结神经姿态控制、首个 morphing quadrotor DRL 或首个窄通道变形飞行。已有近邻包括 Cao et al. (2025) 的变形固定翼 DRL 姿态控制、Yang et al. (2025) 的变臂长四旋翼 cc-DRL，以及 Cui et al. (2024) 的受限空间变形四旋翼规划控制与实飞。
2. **本项目可检验的差异：**在不向候选提供 \hat{J}/\dot{\hat J}、不运行 observer/feedforward、只保留固定 (J_0) 的信息条件下，TCN 是否能作为 drop-in compensation module 替代既有姿态 RBF，并使同一主动变形四旋翼任务在姿态、位置、执行器约束和双向窄门几何 proxy 上不劣于/优于 B。
3. **应用证据门：**六个 GHP7 场景只支持工程安全/方向筛查，不支持普遍应用或统计显著性；其余 DEV72 与封存 TEST48 仍决定广义闭环性能结论。若最终没有在实际 application feasibility、clearance 或跟踪上显示有意义的优势，就不应只凭动作 RMSE 或模型替换本身写成应用创新。
4. **完成全文获取前的纪律：**本全文来自作者上传页面而非 IEEE 正式页面；书目由 DOI 核验。正式稿引用以 IEEE DOI 为准；若引用具体架构、实验和结果，应先用 IEEE 最终版复核版本一致性。

## 决策

保持当前唯一 TCN 候选和原任务书运行顺序。不加惯量重建，不增加训练、调参或航次。闭环比较完成后，依据 pilot/DEV/TEST 的 paired evidence 决定是否存在可写的应用贡献；若候选通过不了原门槛，不把“用了深度学习”当成论文结果。
