# 姿态参考可行性：原始文献边界

主审 2026-10-27 在线核验原文。该备注不改变任何任务姿态评分或验收目标，也不授权新方法/训练。

- Lee, Leok, McClamroch, *Control of Complex Maneuvers for a Quadrotor UAV using Geometric Methods on SE(3)*, [原始论文](https://arxiv.org/pdf/1003.2005)：位置模式的式(22)–(23)由位置反馈与所需合力构造机体第三轴，再构造完整姿态；这不是任意独立指定三个位置和三个姿态分量。
- 同作者 *Nonlinear Robust Tracking Control of a Quadrotor UAV on SE(3)*, [原始论文](https://arxiv.org/pdf/1109.4457)：式(23)–(24)的推力方向含位置反馈和鲁棒平移补偿项，正文 Section III.C 解释给定第三轴后还剩一维方向选择。其稳定性命题有明确控制结构、增益及初值条件，不可移植为本项目离散 BS/GRU/执行器系统的证明。

本项目需要另核真实 Plant 的推力方向、变形动力学、坐标符号及参考生成代码，再判断该一般可行性约束如何适用。环境风速度不能当成外力。即便固定无风名义姿态与有风位置任务存在偏差，也不能单凭该通则解释本轮全部失败，尤其不能解释无风下 GRU 相对 C5 的退化。逐点实际姿态、固定任务姿态、filtered 内环参考的距离必须分开计算；不得直接相减 RMS 作因果分解。

首要性能继续保留固定任务 SO(3) 与位置 Q；inner tracking 为补充指标，不能替代失败的主指标。下一步只读诊断目录为 reports/attitude_reference_feasibility_20261027_v1。
