# 冻结基线后的优化决策

当前基线：DSSM14 位置、cosine GRU32 姿态、100 Hz 因果门控 N4；冻结副本见 `gated_n4_baseline_frozen_v1`。原72场只作为开发数据，不作为独立泛化证据。

## 已核查的接口与当前决策

`position_bs_step` 接收的是惯性系残差力 N；内部 `F_cmd = m*a_nominal - residualForce`，随后转换为推力和姿态目标。补偿整形不是额外向真实动力学直接注入力。姿态目标还经过共享二阶命令滤波，故外环补偿的相位与内环可实现带宽需要同时考虑。

下一项固定消融只在 gated N4 支路后加入 `C(s)=(1+0.08s)/(1+0.03s)`，不改变门控、启动2秒、模型、反馈增益和评分定义。Tustin 100 Hz 系数 `b=[17/7,-15/7], a=[1,-5/7]`；极点5/7在单位圆内、直流增益1，但高频幅值趋向8/3，因此稳定滤波器不等于闭环无风险。先固定 TRAIN 场景 DEV_T3_C09_W09 验证，检查任务姿态、位置、内环、安全、动作回放及大于5 Hz能量；不根据VAL失败场景逐场调参。

启动区间的矩形窗DFT可能受到端点泄漏影响，原先“启动高频是主要根因”的说法暂作为待验证假设。独立审计将用去趋势、Hann/Welch交叉检查，不能用离线频带删除推断控制可实现收益。

## 检索到的相关原始研究与适用边界

1. [Tomic, Evaluation of Acceleration-Based Disturbance Observation for Multicopter Control, ECC 2014](https://elib.dlr.de/90226/1/ECC14_0155_FI.pdf)：研究串级位置/姿态控制与加速度扰动观测，位置环生成姿态及角速度参考，并讨论滤波与扰动抑制之间的权衡。它支持检查外内环接口；不能据此宣称本实验的lead会提高指标。
2. [Mustafa, Command-filter-based trajectory-tracking control of quadrotor subject to internal and external disturbances](https://arxiv.org/abs/2510.26368)：将命令滤波与扰动观测结合，避免虚拟控制的重复微分。当前系统已有命令滤波，暂不整体换控制器；若lead失败，优先检查已有滤波器实现与外环补偿的协调。
3. [Bisheban and Lee, Geometric Adaptive Control for a Quadrotor UAV with Wind Disturbance Rejection](https://arxiv.org/abs/1803.06363)：使用在线调整神经网络处理非结构化扰动，并在几何控制框架下分析误差界。可作为后续几何误差/残差学习方向参考；不是现有Euler接口直接替换的证据。

上述适用性判断是本项目的推断，文献没有验证本项目候选。任何后续方法均禁止惯量重建，不访问TEST，不改变冻结基线。

## 第一场实际闭环结果与后续分支

固定 TRAIN 场景 `DL1018_DEV_T3_C09_W09`：lead 候选 Q=0.0093724411 m、task SO(3)=0.0585767419 rad、inner SO(3)=0.0092892543 rad。相对冻结 gate-N4，分别降低0.50386%、0.01060%、0.07921%；安全计数为0，lead-aware事件/保持/注入链回放误差为0。姿态收益很小，不能据此扩大宣称。另两场固定检查是高频 T1_C11_W12 与低频 T1_C00_W03；此时不改变lead参数。

独立频谱审计用 Hann/Welch 与零相位滤波确认 TRAIN HF10 的2–5 Hz残余能量仍高于B。启动0–2s候选与parent逐点相同，不能把启动差归因于尚未开启的N4门控。5–20s的Welch带内RMS比约1.106，有限窗无窗DFT约1.024，稳态“近持平”不应作为已证实结论。

可另行检验的最小消融是门控开启时间2s改1s，恢复无lead支路，其余参数不变。这不是已采用的方案。TRAIN记录表明低频T2_C08_W08在1–2s约1%事件短暂越过门限，应优先列入负面回归，不仅测试容易的低频场景；闭环结果缺失时不得断言提前启用有效。

独立验证草案72v1的HIGH频率仅1.35/2.05Hz，不足以覆盖当前2.2/3.2和3.7/4.8Hz难点。运行前另锁96v2，增加原两组高频及+10%频移；保留72v1原封存产物，不用它作为充分高频验证。所有控制器使用同一场景输入，按预声明名义/频移高频子集分别汇总。
