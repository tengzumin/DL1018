# 数据分布迁移：原论文与官方代码核查

2026-10-25。只读研究；未引入外部代码、算法或新增运行。核查范围限下列原文具体章节及代码文件，不声称完整复现。

|已有工作|实读依据|本项目差异与可执行验证|
|---|---|---|
|Ross/Gordon/Bagnell，DAgger，AISTATS2011|原论文§2–3、Algorithm3.1：策略会影响其后输入分布；以当前策略采集状态并查询专家后聚合数据。|本文是残差回归而非直接动作模仿，不能套其误差界。只切换上游位置策略的C5教师，尚不等于新姿态NN自身闭环分布。先修参考源、认证既有C5 VAL、匹配TRAIN；若仍失败再审新NN轨迹上的目标/动作关系。|
|Neural-Fly，Science Robotics2022，arXiv v2|原文§4的Data Collection、Domain Shift Problems，Discussion及S4；作者明确讨论环境变化引起输入分布变化，讨论部分还指出级联姿态环交互需进一步理解。|它主要以位置环气动力补偿为对象，不能用来宣称本项目主动变形姿态环已被验证。借鉴验证原则：报告输入覆盖、分组泛化、数据来源和真实闭环效果，不把离线拟合好当作替代RBF成功。|

原论文：
- [DAgger原文PDF](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)
- [Neural-Fly原文HTML](https://arxiv.org/html/2205.06908)；PDF接口因15.5MB大小取回失败，改用可读HTML具体正文与附录，未把摘要当全文。

官方代码实读：Neural-Fly [mlmodel.py](https://github.com/aerorobotics/neural-fly/blob/0ed50246b1f1db194e8f0726749351636d3501bf/mlmodel.py) 的Phi_Net与validation，以及 [utils.py](https://github.com/aerorobotics/neural-fly/blob/0ed50246b1f1db194e8f0726749351636d3501bf/utils.py) 的format_data。validation先用adaptation子集最小二乘求线性系数，再在validation输入上预测；format_data按子数据集保留condition元信息。这里没有复制网络、在线律或声称该仓库提供了本项目可直接使用的姿态控制器。

通过官方GitHub API实际核定main提交为 `0ed50246b1f1db194e8f0726749351636d3501bf`，提交时间2022-05-21T17:08:06Z。未运行该仓库训练或飞控。

Root推断（本项目结论，不归给论文）：当前数据版本/参考修复未同步与上游B→C5变化已有本地实证，应先做这两项工程修复。文献支持这一检验顺序，不证明本项目的误差来自某个NN组件，也不构成新方法贡献。应用创新仍须由主动变形工况收益、对照/消融、计算成本、适用边界和独立测试共同支持。
