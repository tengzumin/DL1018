# 姿态 TCN 路线：论文与代码库定位 v2

检索日期：2026-10-26。此为投稿前初筛；不据此宣称“首次”或“无人做过”。本轮只纳入出版方、原论文页面或论文作者/实验室的代码仓库。

## 相关论文

1. Che et al., 2023, [A Modified Model-Free Adaptive Control Method for Large-Scale Morphing Unmanned Vehicles](https://doi.org/10.3390/drones7080495), Drones 7(8), 495。研究大型变形无人机姿态数据驱动控制，使用双环数据模型和 MFAC，并提供收敛分析及仿真。它是变形飞行器姿态数据驱动控制的先例，但不是主动变形四旋翼上的冻结 TCN 替代 RBF 评估。

2. Derrouaoui et al., 2024, [Trajectory tracking control of a morphing UAV using RBFANN based fast terminal sliding mode: Theory and experimental](https://doi.org/10.1016/j.ast.2024.109719), Aerospace Science and Technology 155, 109719。该文把 RBFANN 用于形态切换、扰动和参数不确定性下的 morphing UAV 轨迹控制，并报告实验。它说明“RBF 用于 morphing UAV”已有先例；本项目可以验证的具体缺口是主动变形四旋翼姿态环内、以因果 TCN 替代既有 RBF 补偿接口。

3. Saviolo, Li & Loianno, 2022, [Physics-Inspired Temporal Learning of Quadrotor Dynamics for Accurate Model Predictive Trajectory Tracking](https://doi.org/10.1109/LRA.2022.3192609), IEEE RA-L 7(4), 10256–10263。论文用历史状态/控制输入训练 PI-TCN 学习四旋翼动力学，并进入 MPC 和真实飞行评估。它支持 TCN 对四旋翼时序动力学建模的可行性，但其网络预测动力学供 MPC 使用，与本项目直接输出姿态补偿动作、替代 RBF 的接口不同。

4. Looper & Waslander, 2021, [Temporal Convolutions for Multi-Step Quadrotor Motion Prediction](https://arxiv.org/abs/2110.04182)。该文研究 End2End-TCN 多步运动预测，包含架构和消融分析；属于 TCN 时序建模先例，不是变形四旋翼姿态控制验证。

5. Jäger et al., 2024, [Adaptive morphing of wing and tail for stable, resilient, and energy-efficient flight of avian-inspired drones](https://doi.org/10.1038/s44182-024-00015-y), npj Robotics。该研究把形态机构用于飞行控制与能耗优化，并考察扰动和执行器失效，提供了形态飞行的应用价值范例。平台是仿生固定翼，不等价于本项目四旋翼；可借鉴其应用层指标设计，不能直接作为本项目性能证据。

## 可复查代码库

- 作者仓库 [samuel-looper/quadrotor-tcn](https://github.com/samuel-looper/quadrotor-tcn)：面向四旋翼多步运动预测，提供 TCN/混合模型、训练评估与仿真代码。适合核对序列建模和评估方式；不提供本项目的 RBF 替代控制器。
- 实验室仓库 [arplaboratory/PI-TCN](https://github.com/arplaboratory/pi-tcn)：与 PI-TCN 论文配套，提供数据处理脚本和实验数据说明；README 标注 GPL-3.0。适合复核 TCN 物理建模和训练流程；不直接复用其网络或代码。
- [paul-krug/pytorch-tcn](https://github.com/paul-krug/pytorch-tcn)：通用流式因果 TCN 实现，带有在线 buffer 接口。可作流式推理实现参考；当前模型需部署到 MATLAB，保持已审核的 MATLAB 前向实现比引入新运行时依赖更直接。

本轮搜索没有找到可直接复用的“主动变形四旋翼 attitude RBF replacement”公开代码仓库；这只是有限范围搜索结果，不足以证明不存在。

## 对 DL1018 的论文表述约束

- TCN 网络结构本身已有大量先例；RBF 或数据驱动控制用于变形飞行器也已有先例。
- 当前可检验的贡献应限定为：在已定义的主动变形四旋翼仿真栈中，用冻结、因果的 TCN 替代姿态 RBF 补偿输出，在固定名义控制器接口下完成严格配对的性能和安全验证。
- 主要证据仍来自六场 pilot 门、开发队列和封存 TEST；六场只作安全/方向筛查。C5 的 72 场含 48 个用于 checkpoint 选择的 VAL 场景，必须标成开发证据。
- 由于训练目标是 B 的 RBF 动作，必须同时报告离线动作拟合与闭环控制结果；动作拟合好不能代替闭环优势。
- 若只能证明仿真中改进，就明确限定仿真范围、理想 morph command 跟踪和固定 J0 接口；不声称实机、随机训练种子或跨域泛化。
- 现行任务书的主门槛是位置/姿态误差和安全。能耗、形态增益或执行器负担可作为后续应用层补充，但须从已锁定 trace 明确计算，不能在看过 TEST 后增加选择性指标。
