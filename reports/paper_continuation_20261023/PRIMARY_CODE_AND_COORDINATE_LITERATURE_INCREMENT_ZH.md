# 公开代码与坐标补偿：2026-10-23增量核对

本次只读原作者代码和论文出版社页面，没有运行外部源码、下载其飞行数据、训练或访问本项目TEST。下面的检索不能证明新颖性，也不改变C3/C4已失败的门槛记录。

## Neural-Fly公开入口的实际范围

经`git ls-remote`解析，作者仓库main当前提交为`0ed50246b1f1db194e8f0726749351636d3501bf`。GitHub递归tree返回未截断；非data文件为README、mlmodel.py、training-and-validation.ipynb和utils.py。其[官方README](https://github.com/aerorobotics/neural-fly/blob/0ed50246b1f1db194e8f0726749351636d3501bf/README.md)将notebook描述为DAIML离线训练与拟合验证入口，不应把这一公开入口当成完整部署控制器。

实际读取[固定提交mlmodel.py](https://github.com/aerorobotics/neural-fly/blob/0ed50246b1f1db194e8f0726749351636d3501bf/mlmodel.py)：17–36行为多层ReLU表征并附加常数项；101–133行的validation先利用adaptinput/adaptlabel求线性系数，再预测valinput。174–185行另有在整批输入上适配并计算拟合误差的统计入口。这些离线拟合数字不能被称为因果在线控制效果。仓库身份、文件清单和读取源码SHA保存在`NEURAL_FLY_PUBLIC_CODE_INSPECTION_20261023.json`。

对本项目的约束：已知预训练表征、线性在线头和复合更新均有先例；不能把网络替换或拼装本身当作充分贡献。若后续引入该类方法作正式对照，需另写与本项目时序、观测和控制链一致的部署协议；本次没有额外启动该对照，也没有把离线LS作为在线结果。

## 指令滤波与辅助补偿并非空白方向

[系统仿真学报2025原文页面](https://www.china-simulation.com/EN/abstract/abstract3798.shtml)的摘要明确包含神经扰动观测、指令滤波和过滤误差补偿；这里只核到了出版社摘要及文献表，没有声称复现其完整证明或实验。它研究姿态容错，不能直接等同本项目的位置环残差坐标问题。

该页面还列出2024年IEEE TFS论文《Discrete-Time Adaptive Fuzzy Command Filtered Backstepping Control for Quadrotor Unmanned Aerial Vehicle Systems: Theory and Experiments》，DOI [10.1109/TFUZZ.2024.3379510](https://doi.org/10.1109/TFUZZ.2024.3379510)。本次直接DOI访问失败，尚未取得原文，因此仅列为后续需读的直接相关先例，不据二手摘要声称已核实其定理、假设或代码。OpenReview短文的本次直接访问同样被验证页面阻断，未作为新增理论依据。

## 当前研究决定

C4真实闭环已显示统一改坐标会产生分轴取舍；这支撑固定C5的分轴最小机制实验，不证明“分轴”首创，更不允许拼接不同闭环轨迹。C5若过开发门，贡献论证仍需说明：实际输出先于更新、过去区间监督与当前控制的关系、坐标匹配的作用、关键消融及有限时域误差界。只有这些证据补齐，才重新审核论文充分性；理论和贡献当前仍为NOT_MET。

## 补充实际读取的离散理论先例

已读取青岛大学作者单位托管的[Lei、Yu、Wang 2021全文](https://zdh.qdu.edu.cn/__local/E/0F/F9/18E674BA436E70D852BE92A40AF_2B492E69_4604F7.pdf)，DOI为10.1016/j.jfranklin.2021.01.036。它研究感应电机而非四旋翼；第3–5页采用Euler离散模型，滤波引理要求输入一阶/二阶差分有界，第7页式(21)的适应更新含下一采样误差。当前项目是1ms RK4 Plant、10ms事件前权重输出及实际联合投影更新，不能直接移用该定理。该阅读用于核对离散时序和假设差异，不作新增性能或新颖性依据；上述2024四旋翼论文原文缺口仍未解决。

[Parikh等的积分并行学习原作者稿](https://ncr.mae.ufl.edu/papers/IJACSP192.pdf)（DOI10.1002/acs.2945）的摘要及定理段说明，积分形式可避开状态导数估计，参数收敛另依赖历史数据的有限激励条件。本项目只用上一个区间样本，没有核实同类历史栈秩条件；不能把积分监督本身当新颖点，也不能借用其参数收敛结论。本次已读该原始来源的相关提取段，后续定位页的再次抓取超时，未据此声称逐行复核完整证明。

另实际读取[Fisher–Annaswamy的v3原文](https://arxiv.org/pdf/2204.12634v3)第2–4页：其因果代数误差模型、归一化梯度及高阶调谐器基于明确的匹配条件和已知基函数假设。算法先应用控制、测下一状态再形成预测误差；这为时序核对提供直接先例。它没有本项目同样的tracking/leak/旧样本联合盒投影，不能直接替代本项目证明。本次不引入该控制器或套用其增益条件。
