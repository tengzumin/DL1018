# 主动变形姿态控制：原始文献补核

2026-10-25，Root实际浏览。本文只界定研究位置，不以文献代替当前实验结果，不采用“必须全新控制方法”门槛。

## 已核原始来源

1. Patnaik与Zhang，Adaptive Attitude Control for Foldable Quadrotors，arXiv v3 2022-12-30，后关联IEEE LCSS DOI 10.1109/LCSYS.2023.3234045。实际读取作者全文HTML II–IV节：以有限个形态子系统及分段常值切换信号研究姿态，结合模型不确定性自适应、驻留时间与轨迹规划；稳定结论有子水平集与切换条件。不能把该切换系统证明直接用于本项目连续变臂、Euler BS、100Hz保持及RK4实现。
来源：https://arxiv.org/html/2209.08676 ；元数据：https://arxiv.org/abs/2209.08676 。

2. Colombo、Giribet与Martín de Diego，Optimal control of foldable drones and its geometric integration，2026-06-16。实际读取出版社全文3.1节：控制相关惯量模型含惯量变化率项，区分内部形态控制与外部力矩；讨论几何最优控制与数值积分。文中不考虑显式输入饱和。本项目保留Jdot并核实际allocator/饱和是模型一致性工作，不能单凭保留Jdot宣称方法创新。
来源：https://link.springer.com/article/10.1007/s00498-026-00452-0 。

3. Falanga等，The Foldable Drone: A Morphing Quadrotor That Can Squeeze and Fly，IEEE RA-L 2019，DOI 10.1109/LRA.2018.2885575。已核出版页摘要和作者PDF索引片段：形态影响CoG、惯量与控制映射。作者PDF两次全文抓取超时，因此本次不声称已完整复核其控制推导。
来源：https://ieeexplore.ieee.org/document/8567932/ ；作者文件：https://rpg.ifi.uzh.ch/docs/RAL18_Falanga.pdf 。

## 本项目可验证的应用论证（Root推断，尚非成果）

真正值得验证的是：在明确理想状态/预设变形假设下，固定名义模型的级联系统，能否通过只用部署可得信号的学习补偿，跨多轨迹、变形阶段和风组稳定降低位置与姿态误差，并给出可解释的补偿目标与失败边界。已核的参考修复仅给有限收益；需要继续直接目标的单因素训练、固定场景闭环、RBF配对与消融，而不是换网络后自动宣称创新。

当前变臂运动是给定的，不是联合最优规划；没有障碍几何/碰撞检查就不能声称完成自主穿隙任务。若后续以狭窄通道或近距检查说明应用价值，必须有对应尺寸/余量/碰撞与跟踪误差证据，不能只画漂亮三维八字。当前任务不启动新轨迹搜索或替换已冻结验收场景。

此检索不是系统综述，也未证明不存在同类学习方法；后续正文应以明确的任务约束、验证覆盖和局限表达贡献，保留旧RBF与校正对照，避免“首次”或任意形态稳定的说法。
