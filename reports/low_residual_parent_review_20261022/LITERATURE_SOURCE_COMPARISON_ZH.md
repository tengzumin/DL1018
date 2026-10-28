# 高频／无风补偿：原始论文与作者代码核对

本页用于解释后续方向，不能代替DL1018的配对证据。未运行外部代码、未引入新依赖、未启动新训练或闭环。C1仍按已冻结任务书评分，不依据文献修改本批参数。

## 控制导向训练与回归目标

[Richards等RSS2021论文](https://arxiv.org/abs/2103.04490)、[扩展论文](https://arxiv.org/abs/2204.06716)及[作者仓库](https://github.com/spenrich/Control-Oriented-Meta-Learning)直接讨论为自适应控制学习表示。本次实际读取作者`pvtol/train_ours.py`和`pvtol/train_mrr.py`：前者通过闭环仿真积分状态跟踪及控制输入跟踪成本，并加meta参数L2正则；后者从状态、控制和下一状态构造一步Euler动力学残差，在子集拟合ridge读出后对全数据残差计分。支持的区别是优化目标本身不同，而非简单替换网络名称。

源码：[控制目标入口](https://raw.githubusercontent.com/spenrich/Control-Oriented-Meta-Learning/main/pvtol/train_ours.py)、[回归入口](https://raw.githubusercontent.com/spenrich/Control-Oriented-Meta-Learning/main/pvtol/train_mrr.py)。本项目实际观察到原加权监督损失、按运行归一的相对风险与闭环Q偏好不同；文献使“应面向部署控制过程核验目标”成为合理方向，不能证明本项目标签有bug或保证某个新目标胜B。

可复现性边界：当前仓库顶层[train脚本](https://raw.githubusercontent.com/spenrich/Control-Oriented-Meta-Learning/main/train)向入口传seed和M两个参数，而所读PVTOL入口还要求num_steps参数。没有实际验证该顶层命令可直接运行。它的多种子循环也不适用本项目禁止种子搜索的现有约束。

## Neural-Fly：表示与在线律必须一起比较

[Neural-Fly原论文全文](https://arxiv.org/html/2205.06908)的复合自适应律同时包含跟踪误差项、测量预测创新项、泄漏及随时间更新的增益矩阵。本项目当前FEATURE Head是跟踪误差梯度、零中心泄漏和逐元素投影，没有同一套预测创新及增益更新。因此不能直接套用其效果或稳定性结论。

作者[公开代码库](https://github.com/aerorobotics/neural-fly)中实际读取的[mlmodel.py](https://github.com/aerorobotics/neural-fly/blob/main/mlmodel.py)包含带常数项的表示网络，以及适应子集拟合读出、验证子集计分的辅助流程。`error_statistics`还会用整份数据拟合系数；这是离线拟合诊断，不能作为本项目在线因果预测能力的证据。本次没有核实该仓库提供与论文完全对应的可直接部署在线控制器。

论文误差界保留表示误差、测量误差、系数变化和泄漏项，且有轨迹等假设；不能从权重被裁剪推出闭环稳定。其离散实现专门处理增益矩阵正定性，不能直接用朴素Euler复制连续矩阵更新。其更新／应用时序也需与本项目“先输出、后更新”逐项核对。

## 对本项目下一步的约束

1. 先完成C1这一单因素检验。仅缩放W0是在验证幅度假设，不是复现上述方法，也不是充分论文创新。
2. 若C1失败，不能继续扫c。应先在冻结的TRAIN数据上，用部署一致的因果时序区分“静态拟合目标不合适”和“表示／在线律不能有效利用目标”。离线真实物理量可用于核验，但不能送入部署输入。
3. 任何预测创新方向必须先列清X14历史、已发命令、可测状态能否因果构造目标及噪声／时延；若依赖真实风或真实加速度oracle则不符合现有范围。未通过此项，不批准实现新在线律或新Plant。
4. 若选择控制导向目标，必须明确真实闭环、代理模型及离散在线更新是否一致；代理模型上收益不能直接冒充原Plant收益。下一轮仍须单因素、对照、预算和失败解释，当前文献核对不授权新增作业。

当前结论：存在有依据的研究方向，但尚无文献能够保证在本项目高频与无风上胜B。必须由原始记录、固定场景配对和实现对应理论共同判定。
