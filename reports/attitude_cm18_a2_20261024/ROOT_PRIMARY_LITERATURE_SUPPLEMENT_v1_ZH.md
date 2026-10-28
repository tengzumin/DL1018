# 本阶段补充原始论文核对

用途：界定已有工作与本地诊断，不据摘要决定新结构，不把文献结论当本项目的因果证据。

1. Cui 等，Motion Planning and Control of A Morphing Quadrotor in Restricted Scenarios，2023，已读取作者arXiv摘要页：[原文入口](https://arxiv.org/abs/2312.07075)。其框架结合考虑形态的轨迹规划与姿态控制，摘要明确提及随形态调整惯量、质心以及在线推力系数。因此“变形时考虑动力学参数变化”不是本项目可单独宣称的新意。当前项目只有给定变形命令跟踪，不能借该文实机或受限空间结果扩张本项目应用主张。本阶段尚未逐式阅读该文全文/核验其代码。

2. Bauersfeld 等，NeuroBEM: Hybrid Aerodynamic Quadrotor Model，RSS 2021，已读取作者arXiv摘要页：[原文入口](https://arxiv.org/abs/2106.08015)。该文将物理气动模型与学习结合，评估的是模型预测和泛化；这支持需要认真比较物理与学习建模的研究背景，但不证明本项目残差标签适合直接作为补偿动作，也不能把其预测收益解释成本项目闭环收益。本阶段尚未逐式阅读全文或运行其代码。

3. 检索到 Actuators 15(6):286 的原始文章入口：[Active Disturbance Rejection Control of Quadrotor UAVs Under Uncertainties and Disturbances](https://www.mdpi.com/2076-0825/15/6/286)。全文打开返回429；搜索摘录提到输入增益失配与控制输入相关的总扰动项。由于未成功核验全文方程，本阶段不以此摘录支持关键推导，不复制其结论。

本项目真正可审查的当前证据仍是本地同状态关系 E(c)=E0−Mc 与行为标签 d_old=E0+(I−M)c_old，以及A2全部48场失败结果。后续若改变监督目标，必须先用同一记录状态的实际分配器与物理方程检验，不能只凭文献标题、摘要或“物理先验”命名放行训练。
