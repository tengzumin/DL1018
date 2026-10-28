# A1R：参考修复单因素控制训练任务书

2026-10-25，Root。现在仅批准实现与零步自检；完整数据与源码实际通过 Root 审核后另写执行放行，之前不得启动 optimizer 或 Plant。

## 目的与边界

检验“只修正 T2 参考教师数据”能改变多少姿态预测表现，作为后续 C5 上下文匹配及补偿目标检验的控制。A1R 不是已批准部署的最终候选，不预设它能修好 T1/T3，也不把修 bug 当作充分贡献。继续使用原 behavior residual 标签，刻意保持这一因素，不能悄悄换成 c_star。

## 固定实验

- 输入：已锁 source manifest `0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5` 对应的 B_REF_REPAIRED 全部 816 场。最终数据 manifest 必须由真实 SCREEN4/REST268 PASS 收据与缓存值核验后生成。768 TRAIN、48 B VAL，场景 ID/顺序与 A1 完全相同。
- 训练规则：seed `2026102001`，一次正式训练、60,000 optimizer steps，batch 512、均匀有放回采样、Adam lr=0.001/weight_decay=1e-5、SmoothL1 beta=1。每 TRAIN 场仅 event zero-based 0,5,...,1995，共 307200 行；不搜索种子、不延长步数。
- 模型：原 A1 的 18→32 tanh→32 tanh→24 系数模型及 `[z/2;u]` basis，保持初始化规则/排列/浮点训练与双精度导出规则。固定模型源不修改，不借用旧 KAN/RBF 权重或特征。可调用已经审过的 A1 纯数值训练/评估辅助函数并锁源码，不能复用会写历史目录的正式入口。
- normalizer：只从本次 TRAIN 307200 行重算，float64 canonical、std ddof=0、floor=1e-6；输出轴 scale 及其他规则与原 A1 相同。严格保留 float64 数组；不得从 checkpoint 的 float32 buffers 反推部署 normalizer。
- 验证与选择：每 1000 步完整 B VAL48，各 1999 事件，沿原 A1 的场景等权归一化评分，严格较小更新 best，平分保留最早。C5 VAL48 仅在已选 best 后作固定诊断评估，不用于切 checkpoint、改 seed 或调参。
- 数值：单 CUDA 作业、关闭 TF32/AMP，既有 deterministic 环境设置；首次步前与实际初始参数保存。若数值或工程失败，保留真实步数和异常，不能把重启隐去。

## 验证与交付

先零步核新读取器覆盖及 TRAIN/VAL 隔离、采样行数、normalizer、实际初始参数与原 A1 初始化规则一致；不得在零步自检里优化。训练源码/数据/任务书 SHA 与硬件背景记录后才由 Root 放行。

正式产物使用新目录 `experiments/attitude_cm18_datarepair_20261024/training_a1r_v1`，拒绝覆盖。保存准确命令、配置、normalizer、初始/best/final checkpoint、每 1000 步指标与逐场结果、终端状态与实际步数。新增训练产物预算 1 GiB，盘余不足 30 GiB不启动；MAT/checkpoint/normalizer模型产物不上传 GitHub。不要让收据系统膨胀成新的配置框架。

Root 比较同一组正确参考 B VAL 和同一 C5 VAL 上的冻结 A1/A1R 原始单位逐轴与向量 RMSE、各任务/风组，模型各自使用其固定 normalizer。禁止把两模型各自尺度下的 normalized score 直接当作横向性能提升。预期 T2 可能改变、T1/T3 迁移未必消失；若无改善则明确否定参考修复足以解决部署问题，继续依据三轴目标/上下文证据决定，不反复训练同一控制。

此任务书不批准新 Plant、TEST、闭环性能结论或新标签。最终目标仍是关闭姿态 RBF 输出与更新后，用真实闭环比较验证替代效果。
