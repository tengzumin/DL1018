# 姿态参考可行性离线诊断

日期：2026-10-27。复用 `experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/MANIFEST.json` 绑定的六个 B/C5 原始 MAT，不重跑仿真、不读取 TEST 数组、不调用 Plant、不改 runtime。输入与源码 SHA 见 `INPUT_SHA256.csv`；逐场细表见 `scene_window_metrics.csv`。

## 指标与时间对齐

固定任务姿态使用 raw `scene/reference/acceleration` 和 `scene/reference/yaw`，`g=9.8 m/s²`：

```text
A = cos(yaw)*ax + sin(yaw)*ay
B = sin(yaw)*ax - cos(yaw)*ay
roll  = atan2(B, hypot(az+g, A))
pitch = atan2(A, az+g)
```

当 `hypot(roll,pitch)>30°` 时，将 roll/pitch 向量整体缩放到 30°。六场无样本触发该投影。所有 Euler 均为 `[roll,pitch,yaw]`；使用 ZYX 旋转 `Rz(yaw) Ry(pitch) Rx(roll)`。SO(3) 距离为旋转测地角，稳定 `atan2(sinθ,cosθ)` 等价于 `acos((trace(R1'R2)-1)/2)`。

原始 transition 时间为 0 至 19.999 s，间隔 1 ms。每点将 actual 取作该 transition 的起始状态 `log/state`，与 `log/filtered_attitude_reference` 及同刻任务参考对齐。诊断窗口为 `[0,5)`、`[15,20)`、`[0,20)`，每场分别 5,000、5,000、20,000 个 transition 样本。主任务姿态计分使用 20,001 个状态样本；这里因滤波参考只有 20,000 个 transition 记录，使用 interval-aligned 20,000 点复算诊断，不修改主计分定义或结果。

风组按 raw `scene/environment_wind_I` 分组：W15 三场环境风速向量全程为零；W12 两场、W13 一场非零。风场分类使用该速度向量，不把 m/s 误作力。

## SO(3) RMS 结果

下表是跨场景拼接所有样本计算的 pooled RMS，括号内 B/C5，单位度；它不是对场景 RMS 作简单平均。

| 窗口 | 风组 | 场景数 | actual–fixedtask | actual–filtered reference | filtered reference–fixedtask |
|---|---|---:|---:|---:|---:|
| 0–5 s | zero_wind_W15 | 3 | 0.08745 / 0.08897 | 0.000602 / 0.000617 | 0.08728 / 0.08886 |
| 0–5 s | nonzero_wind_W12 | 2 | 2.68028 / 2.66552 | 0.001496 / 0.005333 | 2.68006 / 2.66534 |
| 0–5 s | nonzero_wind_W13 | 1 | 2.59804 / 2.68851 | 0.002322 / 0.011453 | 2.59775 / 2.68820 |
| 15–20 s | zero_wind_W15 | 3 | 0.41470 / 0.16077 | 1.02486 / 1.02497 | 1.15053 / 1.09448 |
| 15–20 s | nonzero_wind_W12 | 2 | 2.73910 / 2.77302 | 0.80522 / 0.80560 | 3.10361 / 3.12250 |
| 15–20 s | nonzero_wind_W13 | 1 | 2.91108 / 3.09979 | 0.002264 / 0.012515 | 2.91109 / 3.09980 |

另给 `[0,20)` 的全区间结果。`wind_group_summary.csv` 同时列出 pooled RMS 和场景等权 `scenario_macro` RMS；场景宏平均定义为先对每场求 RMS，再对场景 RMS 作算术平均。`combined_nonzero_wind_W12_W13` 汇总 W12+W13。例：C5 的 `[0,20)` pooled（actual–fixedtask / actual–filtered / filtered–fixedtask）为 W15 `0.1850/1.2460/1.2897°`、W12 `2.8382/1.2032/2.9796°`、W13 `2.8583/0.0124/2.8582°`、合并非零风 `2.8449/0.9825/2.9397°`；对应 scenario-macro 在同一 CSV。

逐点检查了 `|d(actual,fixed)-d(actual,filtered)| <= d(filtered,fixed)` 和 `d(actual,fixed) <= d(actual,filtered)+d(filtered,fixed)`。36 个 scene×arm×window 单元均无超过 `1e-8 rad` 的三角界违例，最大正违例 `1.65e-17 rad`；逐单元数值在 `pointwise_triangle_checks.csv`。这些是几何关系，不是因果分摊，不能把三个 RMS 相减作因果解释。

结果显示，0–5 s 有风组 actual 通常贴近滤波参考而滤波参考离固定任务约 2.6–2.7°；15–20 s W12 的后两者差约 3.1°，W13 actual 仍贴近滤波参考而偏离固定任务约 2.9–3.1°。无环境风 W15 的晚段滤波参考/固定任务仍相差约 1.09–1.15°，所以参考差异并非只在非零环境风组出现，也不能仅凭该结果把姿态或总体分数差异归因于外环补偿或评分定义。

## 力方向可行性与数据边界

本地 `candidate_runner_work/matlab/core/vehicle_derivative.m:31-32` 的平动方程为

```text
p̈ = R(roll,pitch,yaw) * [0,0,T]ᵀ / m - [0,0,g]ᵀ + F_I/m.
```

指定期望位置加速度 `a` 后，推力方向正比于 `m*(a+g*e3)-F_I`；无外力时方向由 `a+g*e3` 给出。给定偏航后，该 thrust direction 通常确定 roll/pitch。四旋翼只有沿机体 z 轴的单一推力向量；侧向外力下，保持位置/速度要求的推力方向通常偏离纯名义轨迹加速度构造的固定姿态。额外固定 roll/pitch 一般无法同时满足不同的侧向力平衡，除非容许位置误差或还有恰好抵消的力。

`position_bs_step.m:24-49` 把参考加速度与位置/速度反馈组合为 `aNominal`，扣除 `residualForce/m` 后将 `commanded_acceleration+g*e3` 映射为 roll/pitch；`baseline_force_to_attitude.m:15-23` 是名义加速度加重力的对应映射。`run_mlp15_dev72_closed_loop.m:2389-2392` 将外环映射结果设置 yaw 后送入 `command_filter_step`，并在 `:2934` 将滤波输出 `ir.euler` 记录为 `filtered_attitude_reference`。因此滤波参考已包含闭环外环命令与命令滤波；actual–filtered 还包含其后的姿态动力学响应，不能单独等同于内环误差的全部原因。

`environment_wind_I` 是环境风速（m/s）。离线核对的 raw `log/wind_force_I` 是仿真风载（N）；`morphology_aware_wind_load.m` 根据环境风与机体速度差生成阻力并写入该量。W15 环境风为零，但因相对运动仍有很小气动阻力：各场/arm 全区间水平风力 RMS 为 0.00156–0.00311 N；W12 为 0.33146–0.35922 N，W13 为 0.37700–0.37762 N。对应最大水平风力范围分别是 W15 0.00300–0.01003 N、W12 0.54891–0.68407 N、W13 0.86880–0.86962 N。环境风速和历史风载只用于离线分组/物理边界核验，不是部署输入；这里未读取质量数值，`m` 只作为动力学符号使用，未访问或重建 `J/Jdot`。

## 复现

PowerShell 7 从项目根目录执行：

```powershell
python reports/attitude_reference_feasibility_20261027_v1/recompute_attitude_reference_feasibility.py
```

`REPRODUCTION_RECEIPT.txt` 记录此次命令与 exit code 0：6 场、36 个指标单元、36 个三角界单元通过。脚本记录 manifest SHA，对每个 B/C5 raw 校验 manifest 绑定 SHA，并检查 `TEST_accessed=0`、字段长度/时间对齐、窗口样本数和三角界。当前 manifest SHA-256：`d33cf1715437e1c120f1e84fb7bc581a9d030771d61efbc5c1a063af0fa8e35d`。
