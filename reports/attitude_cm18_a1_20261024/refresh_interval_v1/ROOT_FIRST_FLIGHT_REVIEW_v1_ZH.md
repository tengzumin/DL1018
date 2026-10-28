# ROOT：1kHz刷新首场审核

隔离引擎与原A1完整diff已由ROOT及非作者Luna极高复核。仅CM18刷新与必要日志/断言变化；原C5位置事件、BS/filter/allocator/Plant代码不变。复制forward及延迟位置helper与原副本SHA相同。实际MATLAB合成调度、入口解析、缺release拒绝通过；四场无Plant准备OS0。ROOT修正/要求修正的入口错误包括期望事件数差一、prep schema/场景顺序、每场独立release文件，以及数值审计单event向量的row-index定位。

首场 T3/C15/W14 实际session3904 OS0，raw SHA 6e09c5e7c22100afc22550e57ca56d5d722cc031b2e73e1303097c2a2c35cce7，19990次CM18刷新，原position/attitude100Hz事件各1999，完整20000转移。独立NumPy数值审计PASS；无安全停止、无motor/generalized saturation，补偿输出clip212事件。模型/窗口/β/增益/场景未变。

|指标|原C5+RBF|A1 100Hz|A1 1kHz|
|---|---:|---:|---:|
|SO3 RMSE deg|.881963779|1.732370655|1.287480300|
|位置Q mm|10.012389|10.582331|10.175265|

首场支持刷新间隔有实际闭环影响，仍未胜原RBF。补偿自身clip增加也如实保留，不与motor saturation混淆。不能将此一场称最终修复。

决定：放行任务书内固定余3场，每场独立release、顺序运行并立即做数值raw审计，任一运行/审计失败即停。Root持有session28285。不同刷新率当前仅用于单因素诊断；若将来选1kHz部署，论文公平对照需另考虑RBF相同刷新率/计算预算，不能省略差异。
