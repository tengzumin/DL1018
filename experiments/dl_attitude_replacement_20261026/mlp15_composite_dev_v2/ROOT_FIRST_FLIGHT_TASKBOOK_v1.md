# 主审首场执行任务书

2026-10-27。状态：仅在root最终更新RELEASE.json后生效。执行者Luna极高；主模型审核。

首场固定 DL1018_VAL_T1_C08_W15，20000步/20秒，沿用既有冻结模型67a656...及真实C5位置栈。唯一相对prediction-only改动为已审复合tracking更新；不训练、不扫参数、不改Plant/参考/执行器/滤波，不读TEST，不重跑B/C5。

主审已实际读取NO_PLANT_CHECK_v2和LOCKED_CFG，确认真实snapshot、[Inf Inf 6]、fixed J0、inertia_dot_for_bs=0、两层零预算拒绝和路径身份。300事件检查复用同一数值step；真实DEV集成单独核验。release收尾错误必须记录，但不需重复配置核验。

执行前：检查全局无其他重负载MATLAB/GPU作业；仅PowerShell7及显式MATLAB R2025b；source lock/实际driver与raw auditor SHA由root锁定。Root只授权本场一航次，其他五场保持未授权，不自动扩展。

运行唯一driver run_composite_dev_attempt；任何真实启动计入账本。保留raw和失败状态，禁止覆盖/删除。运行后执行audit_composite_dev_raw，从实际测量状态独立重建神经输入、T/s、过去残差及全部更新。真实无投影不构成失败；需核对flags与计算一致。

首场工程门：20001状态/20000转换、完整有限稳定，安全原因空，无motor/general clipping，记录tilt、神经dmax及投影事件。核对场景与B/C5/prediction-only身份、更新前warmup一致、输出先于更新和合法输入；微小数值差按审计容差记录，不改阈值挑结果。

独立报告Q、任务SO3、内环跟踪、峰值与耗时，配对B/C5/frozen/prediction-only。首场不要求单场最终论文标准，但不能冒充全部通过。root工程审核通过后才讨论另两场W15；三场方向门仍为宏平均Q/SO3/内环均优于prediction-only，最终要求双环优于B、姿态优于C5及保留C5位置收益不变。
