# C3 DEV72 指标独立表级复算

输入仅为冻结的 `PARENT_ALL288_METRICS.csv` 与场景/终态清单；本复算不重读任何 raw。Q 为 0–20 秒三维位置 RMSE，场景等权，成对胜负容差为 1e-12 m。

指标表 SHA-256：`acf0e3137ab171a8801a0a7672515a17ca85e8a16c1e067512c261c49ddbcd11`。共 72 场、288 条 method 行（DEV 24，VAL 48）。

C3 对 B 为 61 胜、11 负、0 平；门槛是至少 62/72 胜，因此该门失败（61/72=84.722%，不能四舍五入成 85% 通过）。
其余三项 Q 均值门通过：ALL72 C3 11.759245 mm vs B 17.058081 mm；HF W09–W14（n=28) C3 10.619983 mm vs B 10.719024 mm；W15（n=6) C3 6.342900 mm vs B 7.647292 mm。
全 comparator 的 C3 输场配对共 28 条（B 11、DSSM14 16、KAN14 1），与冻结 `PARENT_ALL_LOSING_PAIRS.csv` 的场景/comparator 集合及 delta 逐条核对一致。对 B 的 11 个输场按任务数：FIG8_3D 8, HELIX 2, SQUARE 1；均位于 W09–W14 组。

性能门总结果为 3 项通过、胜场数门失败；完整性、安全门由独立 raw/source 审核另行覆盖。该 72 场是开发证据，包含 12 个复用的 VAL 子集结果，不是独立 72 场样本或 TEST 证据。

逐组、逐方法 Q、所有输场与精度字段见同目录 `C3_DEV72_METRICS_PEER_RECALC.json`（SHA-256 `1eb628f6a91effafe70d8aef30fba0296c2b71e66848f86f907b569bb9226f7e`）。

复算脚本 SHA-256：2877ea597c2c4e06e09a2e117d201d9680d0ba45ec7a6646d7bd68490b56af12。
