# Root 审核：GHP7-balanced MLP15 的 G3 离线拟合

日期：2026-10-26（Asia/Shanghai）  
决定：**通过离线拟合诊断门；允许准备并执行隔离的 GHP7 六场闭环开发筛查**。此决定不解封 TEST，也不授权 DEV72。

## 复核结果

- 训练回执为 PASS，唯一 job，60,000 步，76 场、151,924 个唯一事件，50%/50% 固定批次采样；耗时 160.742 秒。回执中的 7 个产物 SHA 均与文件逐一相符。
- 训练器回执明确 `ghp7_holdout_opened=false`、`TEST48_read=false`、`plant_called=false`。训练代码只打开 G1/G2 训练包；G3 包在训练结束后才由离线审计器读取。
- MATLAB R2025b parity PASS：Python 与 MATLAB 的 raw/clipped 输出最大误差均为 `2.591743831e-7 rad/s²`，容差 `1e-5 rad/s²`。
- 在同一组 G3 C5 状态和同一 `rbf_output_raw` 标签上，full72 MLP15 的合并归一化 RMSE 为 `23.8338`，新模型为 `9.86759`，相对下降 **58.60%**。G3/W00 向量 RMSE `1.60393 → 0.361188 rad/s²`（新/旧 `0.2252`）；G3/W12 `3.32148 → 1.15534 rad/s²`（新/旧 `0.3478`）。两场均达到预登记门，两个模型在这两场的运行时输出都没有触发 `dmax`。
- 当前 13-D 输入仍为 wrapped attitude error、body rate、BS nominal torque、morph command；未加入惯量重建或其他禁用信号。MLP15 架构、loss、训练步数和种子未改变；唯一研究变量是训练分布及其已冻结采样比例。

## 结论边界

该结果支持“GHP7 状态覆盖能明显改善对 C5-RBF 动作的离线模仿”这一机制假设，但不能推断闭环性能。G3 是开发诊断留出：它未参与本次训练，但此前已出现在 GHP7 候选筛查中。因此新模型仍须在闭环逐场对比 B 与 C5；本次不称独立验证。

闭环筛查继续复用原六场 B/C5 raw 和相同 ACTIVE payload，不重跑基线；沿用 `max_tilt=30°` 与姿态残差 `dmax=[45,45,4.7124] rad/s²`。先单独运行 G1/W00 工程门并审 raw，再继续其余五场。G2/W00 的历史不可行标志和 G1/W00 logger 标志不一致须保留。
