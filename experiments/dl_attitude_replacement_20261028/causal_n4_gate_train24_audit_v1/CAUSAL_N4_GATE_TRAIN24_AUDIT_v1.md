# 固定因果 N4 blend 门 TRAIN24 信号审计 v1

## 范围

只读 24 条 TRAIN_C5_24 physical parent cosine-GRU raw 中的 100 Hz applied action、reference position/acceleration 和 state position；未训练、未运行 Plant、未读取 VAL/TEST 评分、未解码风真值、未做惯量重建。W 组别只在门轨迹计算完成后离线汇总。

## 固定协议

- 输入：`stage1_position_event_applied_acceleration_mps2`，只取 `stage1_position_event=1` 的时刻。每场 1,999 个位置事件；31 个未 ready NaN 事件按当时实际输出零动作，随后 1,968 个 ready 事件。非事件 1 ms 样本不参与估计；部署中门和滤波动作按 100 Hz 更新并 ZOH 保持。
- 零初态因果 Butterworth：2 阶 2–5 Hz 带通和 2 阶 2 Hz 低通，三轴独立滤波。能量为三轴平方和，零初态 EMA `tau=1 s`。
- `ratio=Ebp/(Ebp+Elp+1e-8)`；`g_target=clip((ratio-.35)/.30,0,1)`；blend 门 `tau=.3 s`。首个 `t>=2 s` 事件从 `g=0` 开始平滑；`t<2 s` 强制 `g=0`。N4 状态建议从启动持续更新，输出 `clip(u_C5+g*(u_N4-u_C5),-3,3)`。

## 组级结果

下表每场先汇总 `t>=2 s` 的时间门信号，再跨场报告中位数和四分位数；组别不参与门估计。

| 离线场组 | 场数 | ratio中位数 Q2–20s | ratio P90 | g均值中位数 | g P90中位数 | g>0.1时间占比中位数 | g≥0.5时间占比中位数 | 参考自身g>0.1占比中位数 | 状态位置误差2–5Hz RMS中位数(m) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| W09-W14_high | 10 | 0.3460 | 0.4297 | 0.0867 | 0.2493 | 0.2875 | 0.0064 | 0.0000 | 0.0011 |
| W00-W08_lower | 11 | 0.0030 | 0.0049 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0005 |
| W15_no_tone | 3 | 0.0051 | 0.0159 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0001 |

## 固定门的区分与风险

- 逐场连续门信号对 W09–14 相对 W00–08/W15 的 pairwise exceedance probability（仅离线排序，不选阈值）：gate_mean_t2_20=0.800, gate_p90_t2_20=0.800, gate_fraction_gt_0p1_t2_20=0.800, gate_fraction_ge_0p5_t2_20=0.750.
- `g>0.1`、`g>=0.5` 都按预先固定输出门直接统计，不以 W 组调节阈值；逐场轨迹和启动时间见 JSON。
- Reference acceleration 用相同公式作误触发上下文诊断，不进入部署门。若 W15/低频组的 action gate 仍常打开，单靠该能量比不能把风频振荡和任务/控制器自身高频动作分开；即使 reference 自身 gate 低，task-induced control transients 仍可能造成误开。
- 位置跟踪误差 2–5 Hz RMS 仅作同时段的状态佐证，不是新的门输入，也不是对滤波器闭环效果的估计。24 场小样本、不同 task/构型混杂且 parent 已见这些场景，不能据此宣称统计功效或跨风组因果识别。
- 固定的低维策略是让 N4 常态更新，再用该 `g` 平滑混合；`g=0` 退回 C5，避免启用时滤波器状态重置。该门只依赖历史 C5 action；有限阶因果频带估计会有启动/过渡泄漏，固定 2 s inhibit 和 EMA 只能限制瞬态，不能证明风因果来源。

## 输入锁与哈希

- BATCH_BINDINGS SHA-256：`c6e8cb26ba023e88f4120d702c83708938de2fed22762bb10220d2f8eb586c91`。
- 审计脚本 SHA-256：`793771872a3efc970c088bb7f86618c100cc3de24a82de0ec269cc9abf598ad3`。
- parent raw SHA-256 已验证：24/24。逐场 raw 路径/哈希见 JSON。
- 不读取 `score_path`、wind truth、VAL/TEST、或任何候选 N4 raw；没有执行 N4 action replay。
