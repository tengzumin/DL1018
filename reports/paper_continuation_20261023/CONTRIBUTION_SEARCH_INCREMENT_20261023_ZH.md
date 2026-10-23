# 新增原始文献核对与贡献边界

检索于2026-10-23进行，仅将作者原文、期刊/会议出版页用于判断；没有把搜索摘要冒充全文。此页不授权改变冻结C4，也不构成新方向已成立。

| 原始来源及实际阅读范围 | 与本项目的关系及决策 |
|---|---|
| [Quadrotor Composite Learning Neural Control with Disturbance Observer against Aerodynamic Disturbances](https://www.sciencedirect.com/science/article/pii/S2405896323002616)，出版摘要可读，全文请求403 | 摘要已经包含神经网络、扰动观测器以及由状态估计误差参与的复合更新。因此“预测误差加跟踪误差”不能单独作为新贡献；未逐式核对其算法。 |
| [Composite adaptive finite-time control for quadrotors via prescribed performance](https://www.sciencedirect.com/science/article/pii/S0016003220302027)，出版摘要/引言检索结果可读，直接全文403 | 已有复合自适应与命令滤波四旋翼控制的结合。不能宣称首次结合，也不能因其有限时间结论直接推导本项目离散更新稳定。 |
| [Adaptive Neural Network Quadrotor Trajectory Tracking Controller Tolerant to Propeller Damage](https://www.imavs.org/papers/2024/10.pdf)，实际可读13页会议全文 | 在已有Neural-Fly基础上研究离线表征与在线复合适应，并有机载实现。低计算量、离线表征加在线线性系数并非充分的新意。本文没有给本项目X14/PCF实现提供现成的正确性保证。 |
| [Adapting Neural Robot Dynamics on the Fly for Predictive Control](https://arxiv.org/html/2604.04039v1)，实际阅读III/IV及实验段落 | 使用状态和控制输入的增量动力学模型及低秩二阶在线适应，属于不同控制框架。不能仅换低秩层就声称创新；它也不能在保留X14及当前BS架构的前提下直接替换部署模型。 |
| [Command-Filter-Based Trajectory-Tracking Control of Quadrotor subject to Internal and External Disturbances](https://arxiv.org/html/2510.26368v1)，实际可读作者原文 | 命令滤波、扰动观测和状态观测的结合已有直接相关工作。需要把本项目的实际残差参考、采样标签与误差坐标关系逐项说明，不能用泛称“加观测器”代替贡献。 |

当前主审决定：C4依然只是一个冻结的机制干预。无论性能是否通过，都不把它的入口修复算成方法贡献，也不把同步换坐标本身宣称为首创。可能成立的论文论证需要额外支持：实际离散目标与误差动力学的一致设计、对命令滤波残差通道的可复算解释、与原方法/冻结更新/移除新增机制的配对消融，以及与部署实现对应而假设明确的误差界。性能门与论文证据门分别审核。

已核验的原始代码仍为前一增补页记录的DATT固定提交及本地实现。此次未发现上述新论文的已核验作者源码入口，不把缺少链接写成“没有开源”。
