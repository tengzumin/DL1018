# GRU_STREAM 首场与六场闭环任务书

主审 /root，Luna xhigh 实施。当前仅冻结任务，Plant 授权仍为 0；实际模型数值、源码与真实入口审核通过后另签首场 release。

## 候选及输入

候选 GRU32_STREAM72_S2026102001，一次训练已完成 60000 步。模型固定为 gru_stream_c5_teacher_v1/runs/GRU32_STREAM72_S2026102001/gru_stream_c5_teacher_weights_v1.mat，SHA256 963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021。normalizer SHA256 612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693。禁止继续训练、切 checkpoint、改变阈值或首场后调参再归入同一候选。

实际 DEV 入口必须来自 gru_stream_dev_v1 的 run_mlp15_dev72_closed_loop。位置保持 C5 DSSM14/M110。姿态使用当前13维合法输入、场内持续 GRU hidden，权重冻结；RBF 输出及更新关闭；无惯量重建、物理前馈、observer、RLS、composite 或人为一事件延迟。BS、固定 J0/Jdot0、物理场景、执行器、滤波 [Inf Inf 6]、30°倾角投影及原 dmax 保持原值。记录投影次数，不恢复已放宽的“投影次数必须为零”筛查条件。

## 顺序与资源

先仅运行 DL1018_VAL_T1_C08_W15 的 20 s 首场；主审读取原始记录并核对工程、安全、模型和场景身份后，才决定是否补充其余五场：DL1018_VAL_T2_C05_W15、DL1018_VAL_T3_C02_W15、DL1018_VAL_T1_C05_W12、DL1018_VAL_T2_C02_W12、DL1018_VAL_T3_C00_W13。同一已完成航次不得因汇总或 auditor 报错重跑。所有启动、失败、marker、raw 和实际 exit code 留账。

复用已有同场 B/C5 和旧候选记录，不重跑对照。不读取 TEST，不自动扩至 DEV72。GPU 训练已结束；最多一个重载闭环作业。PowerShell7、显式 MATLAB R2025b，所有新增文件位于当前项目隔离目录；不改删历史，不提交 MAT 或 checkpoint。

## 放行与判读

首场前须完成：实际权重全1999事件 Python-double/MATLAB-double 输出与 hidden 逐点误差各不超过1e-8；float32 输出误差不超过1e-4 rad/s²、hidden不超过1e-5；reset、因果、实际 cfg/which/source/model 身份、release0拒绝及raw核验脚本审查。toy PASS不能替代实际模型 PASS。

原始记录须覆盖20001个状态点、20000个控制区间；逐事件检查 hidden carry/场首零状态、当前特征来源、dmax后beta且各一次、当拍补偿与实际issued torque闭合，非事件保持。不以权重冻结或hidden有界代替闭环稳定证明。

主指标沿用0–20 s位置三维RMSE Q、原任务SO(3)和独立inner tracking，未舍入数值、1e-12 m位置胜负容差，不更换参考。报告各场和W15/高频分组，以及峰值、安全、执行器、投影、耗时。

六场只用于是否扩大开发验证：候选宏平均Q须严格低于B且不超过1.10倍C5，任务SO(3)宏平均须严格低于B与C5；W15和高频组Q均不得高于对应B。inner tracking完整报告，不偷换为任务SO(3)。未通过则不扩DEV72，保留全部负结果并据新增证据决定下一机制。六场通过也不等于72场/独立测试或论文达标。

该候选检验持续状态序列训练/推理协议整体，不把与MLP的差异归因于纯memory单因素，不宣称独立训练外泛化。最终性能和论文证据门槛保持原目标。
