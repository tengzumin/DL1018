# 直接补偿目标：固定四场离线重标注准备

2026-10-25，Root。仅放行实现，源码及三轴非作者复核通过后再执行四场；不放行全量重标注、训练或 Plant。该阶段与 A1R 参考修复控制分开，不能把多个因素合并后冒称单因素收益。

## 固定输入

B_REF_REPAIRED 完整数据 manifest SHA `3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0`；source manifest SHA `0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5`。仅四场：

1. DL1018_TRAIN_T1_C15_W14
2. DL1018_TRAIN_T2_C15_W14
3. DL1018_TRAIN_T3_C15_W14
4. DL1018_VAL_T2_C00_W10

每场严格使用 source manifest 对应的物理 B raw/start：T1/T3 原 A1 来源，T2 corrected B 来源。核真实 SHA、cfg、原缓存事件时序和标签；不得以 C5 结果 raw 替换 B。不能把 probe 新航次的同名场景当成本任务 raw。

## 唯一改变

保留原 X18、事件、场景顺序和 TRAIN/VAL 分割，仅离线构造与直接补偿接口一致的目标。沿已审三轴完整 allocation 公式重建 G、E0、c_star=G\E0，并从真实 cfg 取得精确 dmax/beta。c_star 是施加后的加速度补偿；原网络输出接口在 beta 前，因此另存 `target_raw_output=c_star/beta`（beta>0），beta=0 需显式处理不可达项，不静默除零。保留施加量与原始输出量两个字段，不能混称。

依次验证当前请求和纯 allocator 与 raw 一致、原缓存 behavior residual 的物理闭合、独立 E0 恒等式、G 条件数与求解闭合、直接补偿经过现有 clip/beta/完整 allocator 后的同状态误差与可行性。不正则化 G，不改限幅，不丢弃失败或不可行事件。逐场/逐轴保存完整计数；遇物理或身份闭合失败即保存失败并停止。

新小型 v7 标签缓存只保存新目标、G（若存9列，明确为 MATLAB column-major G(:)'）、时序/index/phase及身份，不复制旧 X18、不改原缓存。新旧监督量来源分开；真几何、真风仅用于离线标签，部署仍只有原 X18。输出独立 `cstar_screen4_v1` 目录，合计不超过 16 MiB，拒绝覆盖。

## 审核与失败解释

预期：当前动作与 raw/旧标签闭合，G 可逆，c_star 对应的同状态理想误差接近数值零；受限输出的误差与不可行项需完整报告，不能只展示理想式。还需核 nominal zero-basis 事件是否产生不可表达的目标，以判断现有模型结构是否适用。

这四场不能证明全训练数据可行、模型可学、闭环改善或稳定；也不否认依赖过去动作的 residual 学习可能通过递归固定点收敛。Root 审核实际四场后，才决定是否安排全数据标签与单因素 A1T 训练。当前不扩模型、不采集新 teacher、不用 TEST。
