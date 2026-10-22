# Phase 1 机制汇总独立审核

状态：离线审核；未运行实验，未读取 TEST 或原始航次数据。检查时未发现 `mechanism_audit_luna` 报告或脚本；本审阅仅使用同目录的 `mechanism_by_scene.csv` 与 `mechanism_summary.json`。CSV SHA-256：`455289BE8B1201B170960D9C6FD022001A86E5F73DE7140468D649078E76A3DF`；JSON SHA-256：`FE522376A58DD72239E54FC0E4585F5FF4E84F5A756A646D50CE526E11C88AAD`。

## 数值与聚合口径

CSV 有 72 行、72 个不同 scene_id：DEV 24 场、VAL 48 场。每行 `event_count=1968`。逐行按未舍入 Q 重算胜负，使用 `candidate_q_m - B_q_m` 与 ±`1e-12 m` 容差，72 行标签全部匹配，且 `delta_mm` 与 Q 差换算完全一致。JSON 的 scene-equal 宏平均及胜数复算一致：全体 46/72 胜，候选/B 宏 Q 为 12.387218/17.058081 mm；DEV 14/24，VAL 32/48。W09–W14 为 5/28 胜、11.244524/10.719024 mm（候选差 +0.525500 mm）；W15 为 3/6 胜、7.697746/7.647292 mm（候选差 +0.050455 mm）。这证明分组性能弱点存在，不识别造成弱点的组件。

JSON 的 `*_event_weighted` 数值不是逐场 RMSE 的算术加权均值。它们精确对应 pooled RMSE：`sqrt(sum(event_count_i * rmse_i^2) / sum(event_count_i))`。因 72 场 `event_count` 均为 1968，算术加权均值等于 scene-equal 均值；但 pooled RMSE 仍不同于 scene-equal RMSE 平均。例如全体 `prior_target_rmse` 的 scene-equal 均值是 0.278017，而 pooled 值是 JSON 中的 0.295449。报告应将聚合定义写清，避免把两个统计量都称作“平均 RMSE”。候选/B 的 Q 宏值采用逐场等权平均，与性能表口径一致。

`prior_target_rmse`、`online_before_target_rmse`、`online_after_same_state_target_rmse` 分别与对应 x/y/z RMSE 按 `sqrt((rx^2+ry^2+rz^2)/3)` 组合，72 行最大公式差低于 `1.2e-16`。但独立列 `target_rmse` 不等于三者中的任何一个；全体最大与 before/after 列差分别约 0.429/0.430。结合 `target_mean_abs_x/y/z`，它看起来是目标信号自身的尺度统计，而非预测误差；CSV 不含该列公式或字段定义，正文应将其与“预测对目标的 RMSE”分开并补充公式/单位，不能拿它解释在线更新效果。

## 同态、同状态及因果边界

可复核的重放字段支持数值一致：72 行 `W0_first_event_max_abs_diff=0`；`raw_before_replay_max_abs` 和 `applied_replay_max_abs` 最大约 `6.7e-16`，`head_update_replay_max_abs` 最大约 `2.3e-16`，`pcf_eta_replay_1khz_max_abs=0`。这说明列出的重放量与记录相合，也支持每场首事件初始化权重等于 W0。它不证明 `prior_target_rmse`、`online_before_target_rmse`、`online_after_same_state_target_rmse` 的每一个误差样本用了完全相同的 phi、目标标签、时间索引及闭环状态；`same_state` 仅出现在 after 列名，CSV 没有逐事件状态/特征配对键或公式来源。因此，“同态、同状态”的比较强度目前只能以生成脚本和逐事件配对证据确认，不能单由汇总表保证。

按 CSV 明确标记的同状态 after 数值，online-before 到 after 的 pooled 目标误差全体从 0.231864 降至 0.231236；71/72 场 after 较低。W09–W14 从 0.296650 降至 0.295782（28/28 场较低），W15 从 0.037705 降至 0.037045（6/6 场较低）。W0 prior pooled 值又高于 online-before（全体 0.295449 对 0.231864，72/72 场 online-before 数值更低）。这些数值不支持“在线这一步普遍增大同一状态的目标误差”这一窄命题；但状态序列是否真正配对仍需上段所述证据。它们也不构成候选相对 B 的闭环因果证明：高频和 W15 的闭环 Q 与 B 相比退步，同时所列候选目标误差在 after 方向略降；两类指标的对象不同，B 与候选闭环状态也不同。可报告为共现事实，不可据此认定更新律、PCF、网络或某个轴造成分组输场。

## 审核结论

这份表适合作为 72 场描述性机制证据，但不够支持组件因果归因。进入机制决策前，应在表头/说明中固定 pooled RMSE 与 scene-equal mean 的定义，给 `target_rmse` 补公式和单位，并保留同状态逐事件配对的可复核出处。当前证据支持的最强判断是：性能弱点在 W09–W14 和 W15 的分组 Q 中存在；after 目标误差列未显示同状态误差上升。它不确定这些组为何输，也不证明目标误差变化导致或解释闭环 Q 差异。