# 非作者源码复核：matched position context probe v1

结论：以本次只读核对的源码、准备快照和 Root 的 `PREPARED_NO_PLANT` 回执为准，T1_B 没有发现具体启动阻断。未运行 MATLAB、engine 或 Plant。

复核身份：prepare SHA-256 `37f866d0fc84d5a2dfbf07e19ee415589c4d841d7fe9839a6e1473a8b1a225d4`；runner SHA-256 `f35bf83462eb652f87e455afae67f3dab003f5e74753838a6ccb60cb8f8e754d`；任务书 SHA-256 `69c329de945bced5ba67adc23baa243b50074e0b8625ff86b9f8a78bcaf3b945`。

T1_B 输入与快照绑定正确：准备 JSON 的 T1 raw 和 run_start 路径均对应 `DL1018_TRAIN_T1_C15_W14/B/attempt_01`，相对路径是 `data/raw/train/DL1018_TRAIN_T1_C15_W14/B/attempt_01/raw_run.mat`；四份快照的 scene/mode 映射正确。prepare 在加载前后校验 raw、run_start、manifest、ALL816 和 C5 文件的 SHA，并验证 B run_start 的 raw 路径、初态、cfg、共同选项。B 与 C5 的 options 叶级差异完整落在 position RBF 开关、C5 runtime/PCF/delayed prediction/mask 位置处理包内；姿态及其他共同选项受等值检查和差异 allowlist 约束。C5 engine、wrapper、source binding、模型、normalizer 与 32 个活动源码身份均已 pin。

复核到的实际初始化路径与任务书一致：engine 每次调用从 `scene.initial_state` 初始化状态和姿态命令滤波器，并在函数局部创建姿态/位置 RBF 权重；C5 runtime 也在本次调用内创建 context history、trained weight、held force、PCF、延迟积分与历史字段。因此四航次不会通过 engine 的持久状态继承上一航次。runner 在调用前重新核对源 scene、scene id、时间网格与初态，写入独立 run_start，并以固定 flight allowlist、单次 attempt、Root release pins 和 first-Plant-step marker 约束执行。

审计边界：runner 的 run_start 记录 `mutable_initial_state` 预期值，但调用前只把 scene 初态与快照初态逐项比较，没有用运行后 raw log 对每个 RBF/PCF/延迟内部初值逐字段断言。固定 engine 的局部初始化源码支持这些值从规定默认态开始；这不是 T1_B 启动阻断，但实际运行审计仍应以 raw 日志和 pinned engine 的初始化行为确认姿态分支、C5 历史与初值未发生意外偏离。

准备回执 `PREPARED_MATCHED_POSITION_PROBE_v1.json` 状态为 `PREPARED_NO_PLANT`，声明 0 Plant、0 training steps、0 optimizer steps、未访问 TEST、未调用 engine；Root 的实际 MATLAB checkcode/prepare 结果由 Root 回执记录。本报告不构成 Plant 放行。
