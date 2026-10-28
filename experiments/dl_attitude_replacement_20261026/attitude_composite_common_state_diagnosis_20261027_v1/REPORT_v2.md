# 同状态 shadow 诊断 v2

## 结果

六场 logged composite trace 均精确复现。逐事件最大误差（含 feature、T/surface、base、权重、协方差、composite output 和 fixed-J0 residual）分别为：W15 T1 `1.94e-12`、T2 `1.08e-12`、T3 `2.75e-12`；HF T1 `7.67e-13`、T2 `3.98e-13`、T3 `1.81e-13`。

按上一事件实际输出对齐下一段观测后，归一化一步误差 RMSE（RLS-only → composite）为：

| 组 | roll | pitch | yaw |
|---|---:|---:|---:|
| W15 | 0.215235 → 0.215131 (-0.05%) | 0.180290 → 0.180448 (+0.09%) | 0.128842 → 0.128771 (-0.06%) |
| HF | 0.226273 → 0.225028 (-0.55%) | 0.138827 → 0.138097 (-0.53%) | 0.275764 → 0.275705 (-0.02%) |

Tracking/RLS 累计权重增量轴范数比：W15 roll/pitch/yaw `3.16%/3.88%/0.03%`；HF `2.37%/3.07%/0.03%`。P trace 范围 W15 `11.79–431.36`、HF `22.90–330.00`；协方差最小特征值保持正值，未见发散迹象。更细的 maturity、first5/middle/last5、轴向创新与 P 极值见 [shadow_summary_v2.csv](shadow_summary_v2.csv)。

现有证据不支持“tracking 明显牺牲 HF 预测”的归因：误差差异很小且轴间混合，RLS 增量占主导。六场实际闭环 paired flight metric 的 macro 均值（candidate → prediction-only）为 Q `0.009676 → 0.009475`（差 2.12%，candidate 较差）、SO(3) `0.028082 → 0.028167`（改善 0.30%）、inner tracking `0.019583 → 0.020047`（改善 2.32%）。这是现有六场策略总效应；不能据此把结果单独归因于 tracking。paired CSV 与 32 条 candidate loss 记录均保留。

## 限制与下一项最小区分实验

这是固定 composite 航次状态、输入与观测序列上的条件 shadow replay，不是 prediction-only 闭环反事实。现有六场 paired 闭环对比已覆盖整体策略效果；本次弱且混合的 shadow 差异不足以支持再跑同一 tracking-on/off A/B。当前没有建议新增实验。若未来需把总效应进一步拆到具体更新项，应先由实际决策提出新的区分问题，再设计最小干预。

首版错误实现已在 [ATTEMPT01_INVALIDATION.json](ATTEMPT01_INVALIDATION.json) 标记并保留，不作为结论。v3 原始数据、源码和配置未改；未启动 MATLAB、Plant、训练或 TEST。
