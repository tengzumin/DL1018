# 首航准备源码审核

ROOT 已完整读取 prepare_a1_first_flight_v1.m 与 run_a1_first_flight_v1.m。

准备结果：MATLAB R2025b OS0；固定 DEV T1_C01_W15；32项C5活动源与6项共享输入、31项which核对；cfg不变，opts反向恢复后与C5快照isequaln。新模型固定step30000，三项姿态RBF开关关闭。无Plant/engine/episode/训练/TEST调用。

运行器核验：仅一个引擎调用；独立ROOT放行及SHA必须存在；启动前复核源码、模型、原场景与准备快照身份；新目录不得覆盖；只允许固定一场。完整性与安全检查后保留原始日志。

决定：准备源码可保留；尚不放行首航。须先完成同状态旧动作闭合与新动作诊断审核。准备PASS不代表闭环效果通过。

重放attempt4已终止OS1，原因是输出目录守卫将fileparts第三输出（扩展名）误当目录名，未进入动作重放。ROOT已通知执行者单点修复并在实际MATLAB覆盖此守卫；此错误与模型/物理机制无关。此前pre-data检查未覆盖该守卫，不能称全部入口门槛通过。保留全部失败记录。
