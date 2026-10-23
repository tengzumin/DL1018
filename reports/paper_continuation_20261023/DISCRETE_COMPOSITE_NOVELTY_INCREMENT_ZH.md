# 离散复合自适应的补充文献核对

本次针对新储能推导补查原始论文/作者预印本，不执行外部仓库代码、不改变当前候选。未完成全面查新，不能据搜索无命中认定首次提出。

| 原始来源 | 实际读取范围 | 对本项目的限制 |
|---|---|---|
| [Composite adaptive NN learning and control for discrete-time nonlinear uncertain systems in normal form](https://www.sciencedirect.com/science/article/pii/S092523122030103X)，Neurocomputing 390 (2020), DOI 10.1016/j.neucom.2020.01.052 | 出版商索引摘要；正文访问403 | 离散复合NN学习/跟踪本身已存在。未读其完整更新/证明，不声称本项目储能与其相同或不同。 |
| [Composite learning control of robotic systems: A least squares modulated approach](https://www.sciencedirect.com/science/article/pii/S000510981930473X) | 出版商索引摘要；正文访问403 | 该摘要已区分无IE时的闭环渐近稳定与IE下的指数参数收敛；“不用PE证明某种稳定性”不能单独作为本项目创新。 |
| [Simultaneous Online System Identification and Control using Composite Adaptive Lyapunov-Based Deep Neural Networks](https://arxiv.org/pdf/2311.13056v2)，arXiv:2311.13056v2，2026-05-21 | 原始16页PDF的摘要、引言和网络定义；后续定位读取超时，未逐行核验完整证明 | 作者使用状态导数观测、全层Jacobian与复合更新，区分UUB与PE下更强收敛。本项目冻结编码器/线性头、一个已完成区间积分、单次离散投影不等于其方法，也不能直接借其定理。注意当前版本标题和日期已不同于早期2023摘要标题。 |
| [Gradient-Based Adaptive Prediction and Control for Nonlinear Dynamical Systems](https://arxiv.org/html/2602.11899v1)，arXiv:2602.11899v1，2026-02-12 | 原始HTML §§1–3，含假设、预测算法背景与控制定理2及其证明框架 | 作者无PE预测/控制结果仍有特定弱凸性、噪声、步长、最小相位与增长条件。本项目未验证这些条件，不能直接移植其收敛结论；无PE本身也不是充分贡献。 |

## 当前主审判断

现阶段能提出的贡献候选是**与实际采样部署相符的残差坐标与已完成区间目标配对，以及针对当前/旧特征错位、保持、泄漏和投影的离散误差分析**。这仍须与最直接的完整原文继续对照，并由消融/独立测试支撑。不能把“用了DSSM”“增加预测误差”“使用积分避免瞬时导数”“采用投影”或“不假设PE”分别包装成首创。

新的负旧方向平方储能已在理想子情形取得精确数值证书，实际扰动后验推导也已核对；这只证明本项目一个具体候选分析成立，不能据此断言该储能构造在整个离散自适应文献中首次出现。当前方法/理论/论文贡献验收仍分别保留待审核状态。
