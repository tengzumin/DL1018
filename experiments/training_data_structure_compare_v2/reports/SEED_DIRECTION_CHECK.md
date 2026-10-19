# Seed 方向复核

## 可比的双 seed 离线结果

| 方案 | seed 2026101911：共同 VAL 最优 RMSE / step | seed 2026101912：共同 VAL 最优 RMSE / step | 方向 |
|---|---:|---:|---|
| MIXED_KAN | 0.289469 / 57k | 0.289491 / 45k | 两次几乎相同 |
| TEACHER_KAN | 0.315402 / 0 | 0.313991 / 12k | 两次都未优于混合组；最优点接近初始化 |
| DEEP_KAN | 0.276317 / 57k | 0.275326 / 54k | 两次均优于 MIXED_KAN 的共同 VAL 分数 |

共同 VAL 使用同一 144 条开发记录、同一来源权重与同一物理 RMSE 口径。MIXED 两 seed 的分数差约 0.000022 m/s²；DEEP 两 seed 的分数差约 0.000991 m/s²。说明这三组的离线方向在两个预设 seed 上一致；不等于闭环收益在 seed 间稳定。

## 不可当作双 seed 结论的运行

- HISTORY_KAN seed 2026101911 按用户要求在 18k/60k 停止训练，选用 step 15k 最佳 checkpoint；未运行第二 seed。其 DEV 结论只适用于冻结的 step 15k 快照，不能外推到一个未训练完成的模型。
- WIDE_MLP 是用户额外要求的一次探索性运行，单 seed 2026101911，60k 完成，最佳共同 VAL RMSE 0.279519（step 54k）；未运行第二 seed，且随机初始化，不属于函数保持结构对照。
- BRIDGE6 只按预定首 seed 运行；DEV 只检验冻结 HISTORY step 15k，不构成候选的 seed 间闭环复现。

## 判读限制

共同 VAL 是开发数据，不是盲测。跨 seed 的 VAL 一致性不能替代闭环重复；本轮没有把任何模型按 DEV 成绩回流训练、换 seed 或重选 checkpoint。
