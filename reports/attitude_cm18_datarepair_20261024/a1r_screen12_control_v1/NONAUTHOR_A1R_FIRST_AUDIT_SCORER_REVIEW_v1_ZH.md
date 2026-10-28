# A1R 首场独立审计与冻结评分复核

复核对象是 `DL1018_DEV_T1_C01_W15`。A1R raw SHA256 为 `062a5bea4a429453ec38fb19f70b75ce4753e2d790993580ffe68f5fb728c9cf`；独立事件审计报告 SHA256 为 `da7b0126f5242e362effb30e08dfbcbe624929dc398e9a254b8a294405ac3d49`，状态 `PASS`。冻结评分 JSON SHA256 为 `eb3dcd7df2583e7e47458d5b12b39e2a3db13d0a6aeb7860d4529bfb615f7661`，评分实现 `reports/attitude_cm18_a1_20261024/root_screen12_metrics_v1.py` SHA256 为 `3b345050b31cabdfcb08dab405d9e34b736e1f65c02bc9fd22d3a0f08c9aeb52`。

我对同一 raw 只读调用冻结 `score`，并与其 JSON 和 A1R 事件审计结果逐项比较。ALL、PRE、POST 三段的样本数、位置 Q、各位置轴 RMSE、位置峰值、SO(3) RMSE/峰值和 transported body-rate 向量 RMSE 均完全一致；所有数值差均为 0。

| 时段 | 样本 | 位置 Q RMSE (m) | SO(3) RMSE (deg) | 位置峰值 (m) | body-rate 向量 RMSE (rad/s) |
|---|---:|---:|---:|---:|---:|
| ALL 0–20 s | 20,000 | 0.0038190875510 | 0.330240911821 | 0.009916836708 | 0.008163840624 |
| PRE 0–5 s | 5,000 | 0.0009250959172 | 0.000180612960 | 0.001264316744 | 0.000004466935 |
| POST 5–20 s | 15,000 | 0.004377438994 | 0.381329344417 | 0.009916836708 | 0.009426790811 |

事件重建最大绝对差为 `7.105427357601002e-15`（forward、clip、held acceleration）；BS nominal torque 差为 `1.3010426069826053e-18`，beta 差为 0。1999 个 CM18 事件、499/1500 PRE/POST 分组均符合预期。三条旧 RBF 路径均关闭，日志输出与更新均为零；本场按各轴的 CM18 clip、motor saturation、generalized clip 及 tilt limit 计数全为零。安全峰值为位置误差 `0.00991684 m`、倾角 `5.44515 deg`、机体角速度 `0.157737 rad/s`，三个尾随安全持续时间均为 0。

冻结评分 JSON 的 `status` 仍为 `SCORED_PENDING_COMPLETE_EVENT_AUDIT`，与其数值已由 PASS 事件审计完成的状态不同步。数值和 raw SHA 已独立核对；若该 JSON 用作终态汇总，需由其所有者更新状态并另存新证据。此复核只覆盖这一场，不据此推断其余 SCREEN12 场景或总体效果。
