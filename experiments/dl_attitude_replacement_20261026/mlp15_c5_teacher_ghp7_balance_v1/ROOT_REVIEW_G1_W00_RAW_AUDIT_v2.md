# 主审：G1/W00 首场闭环审核 v2

日期：2026-10-26（Asia/Shanghai）

## 结论与决定

G1/W00 工程门通过，批准按冻结任务书继续剩余五个 GHP7 开发场景。总候选上限仍为六次闭环；已消耗 1 次，还剩 5 次。TEST48、DEV72 均未放行。

## 独立复算

审计脚本：audit_mlp15_c5_ghp7_balance_g1w00_v1.m。报告：G1_W00_RAW_AUDIT_v2.json。raw SHA-256：456234f6477e7619f851e21b604486cf4f4ae4217b95e3a5b2afaea100e065e0。

候选完成 20000/20000 transitions，STABLE，无 safety stop，application_feasible=true。对 1999 个姿态推理事件逐条重建 13-D 特征，最大重建误差为 0；所有特征有限。RBF 输出、RBF 在线更新和时变惯量重建均未启用。最小双向几何净空 53.50 mm，15 mm 几何门通过。

| 方法 | 0–20 s 位置 Q (m) | SO(3) RMSE (rad) | 应用可行 |
|---|---:|---:|---|
| B | 0.012510156857027187 | 0.0633611272050734 | 是 |
| C5_RBF | 0.009975204632515243 | 0.062645829537664136 | 是，保留历史 logger completion-flag mismatch |
| GHP7-balanced MLP15 | 0.010049321186687894 | 0.06265796276368113 | 是 |

候选相对 B 的 Q 改善 2.461 mm（19.67%），姿态 RMSE 改善 0.0007032 rad。相对 C5，Q 退化 0.07412 mm（0.743%），姿态 RMSE 退化 0.00001213 rad（0.0194%）。因此首场支持“同时优于 B、位置接近 C5”，但不能单独证明姿态优于 C5；最终按六场宏平均预登记门判断。

## 限幅与饱和

本场沿用 C5 快照中的 max_tilt=30° 和姿态残差 dmax=[45,45,4.7124] rad/s²。它们是配置值；本场 tilt projection、dmax clipping、motor saturation、generalized clipping 的计数全部为 0，故这些限幅没有实际介入本场控制。不能据此说限幅已从代码移除。

## 账本与例外

首场实际运行约 26 秒，输出 raw 约 61.6 MB。此前两次 MATLAB 启动均在 marker/Plant 之前失败，分别是 Code Analyzer 报告路径错误、release 报告哈希过期；两次都没有 Plant call、marker 或 raw。记录分别保存在 PREPLANT_LAUNCH_FAILURE_v1.json 与 PREPLANT_LAUNCH_FAILURE_02_v1.json。

初次独立计分报告 v1 将 B/C5 的 application_feasible 默认写成 false；不用于决策，已保留原件并由报告 v2 更正为 baseline reuse manifest 中的历史值。C5 的 completion-flag mismatch 仍单独披露，没有改写历史 raw 或状态。

## 续跑范围

继续顺序执行 G1/W12、G2/W00、G2/W12、G3/W00、G3/W12，各一次；复用同一 B/C5 raw 与 payload，不训练、不扫参数、不跑新 B/C5、不访问 TEST。逐场保留失败，六场结束后独立汇总 Q、SO(3)、可行性、限幅与耗时。GHP7 仍是开发筛查，不是独立 TEST。
