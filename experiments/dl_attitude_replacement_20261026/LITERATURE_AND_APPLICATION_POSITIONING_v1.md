# TCN 姿态替代：文献与应用定位（初查）

日期：2026-10-26（Asia/Shanghai）

## 本地任务数据核验

抽查冻结的 GHP7 `DL1018_GHP7_G1_W00` payload（哈希受 `GHP7_PILOT_PAYLOAD_MANIFEST_v1.json` 约束）：20 s、1 kHz、20,001 个状态；目标位置总跨度约 3.034 m；形态命令覆盖 `[-1,1]`。scene metadata 将几何称为 configured-component proxy，电池按点质量处理，5 英寸旋翼半径为估计值。因此这是主动变形仿真任务，不是实测飞行或已标定完整机体几何。

GHP7 的冻结应用定义是主动变形窄门**往返两次**，并在 8–12 s 开阔段评估位置跟踪。Plant 没有墙体接触/碰撞响应；15 mm 通行余量基于机身、臂、电机、舵机和估计桨盘的配置几何包络，电池视为包含在机身外形内。论文中应称“配置几何包络仿真证据”，不能写成实机碰撞通过或安全认证。

候选 TCN 的在线输入只取姿态误差、机体系角速度、BS 名义角加速度和四臂形态命令。payload 虽含 `rho_true/rhoDot_true`，它们不得进入候选特征；闭环物理 Plant 仍会用形态真值推进动力学。形态命令理想跟踪是假设，必须写入适用边界。

## 直接相关先行工作

| 工作 | 与本项目的关系 | 对论文定位的影响 |
|---|---|---|
| Saviolo, Li & Loianno, “Physics-Inspired Temporal Learning of Quadrotor Dynamics for Accurate Model Predictive Trajectory Tracking,” IEEE RA-L, 2022. [论文](https://arxiv.org/abs/2206.03305), [作者代码库](https://github.com/arplaboratory/PI-TCN) | TCN 已用于四旋翼时序动力学学习和闭环 MPC；论文用飞行数据及 physics-inspired loss。作者仓库页面当前列出 README、`process_data.py`、LICENSE，重点是数据处理和数据说明，不是可直接替换本项目姿态 RBF 的控制实现。 | 不能声称 TCN 或时序学习首次用于四旋翼。可借鉴因果历史窗口、与物理基线并行比较和数据划分；本项目监督目标与控制接口不同。 |
| Cui et al., “Motion Planning and Control of a Morphing Quadrotor in Restricted Scenarios,” IEEE RA-L, 2024. [论文](https://arxiv.org/abs/2312.07075) | 研究四外部执行器变形四旋翼的狭窄环境全身轨迹规划和非线性姿态控制；控制过程中动态调整惯量、质心和推力参数，并报告仿真和实飞。 | 不能声称首次在变形四旋翼上通过狭窄环境，亦不能声称首次处理形变惯量。应用贡献需限定到“因果学习残差在不给控制器时变惯量模型的条件下，对联合跟踪和安全通行的影响”。 |
| Derrouaoui et al., “Trajectory tracking control of a morphing UAV using radial basis function artificial neural network based fast terminal sliding mode: Theory and experimental,” Aerospace Science and Technology, 2024. [出版社页面/摘要](https://doi.org/10.1016/j.ast.2024.109719) | 直接把 RBF 神经网络用于 morphing UAV 轨迹/姿态相关控制，考察形态变化、扰动与不确定性。 | RBF 已是变形飞行控制的已知路线；本工作应清楚报告替代目标、相同控制栈和新任务指标，不能把“第一次将神经网络用于变形控制”当贡献。 |
| Köse, “Octorotor flight control system design with stochastic optimal tuning, deep learning and differential morphing,” 2024. [DOI](https://doi.org/10.1007/s40430-024-04972-1) | 公开摘要描述以深度网络估计形态相关惯量，并优化差动变形八旋翼控制参数。 | 进一步说明“学习惯量/深度网络用于变形飞行”已有先例；本轮避免 `Jhat/Jdot_hat` 有利于把主结论限定为观测量驱动的残差补偿，而不是惯量辨识贡献。 |
| Cao et al., “Intelligent Attitude Control for Morphing Flight Vehicle: A Deep Reinforcement Learning Approach,” IEEE TVT, 2025. [DOI](https://doi.org/10.1109/TVT.2025.3541606) | 题名与书目信息指向变形飞行器深度强化学习姿态控制，是直接近邻。当前未取得并逐段核对全文。 | 不得声称“首次用深度学习控制变形飞行器姿态”。正式论文前应取得全文，核对其平台、控制对象、输入信息、比较基线和实验条件。 |

## 目前可以成立的定位（仍待结果验证）

不把 TCN 架构或自适应律包装成全新理论。可检验的应用主张是：在冻结的 BS/C5 控制栈中，用单个因果、冻结权重 TCN 替代姿态 RBF 残差输出；网络使用控制器状态与形态命令，不用时变惯量估计、Plant 真值或在线更新；在主动形态变化任务上同时考察位置误差、SO(3) 姿态误差、执行器/安全状态和通行几何。

该主张只有在完整 DEV72 和一次独立 TEST48 配对证据通过后才可写成结果。六场 GHP7 先导仅用于工程、安全和方向筛查。要把论文贡献写成“弱模型依赖”，还需明确姿态/角速度的仿真可观测性、理想形态命令跟踪、无传感器噪声、标称 BS、DSSM14 位置环、单训练种子等限制；目前不支持实机、跨种子或一般变形平台结论。
