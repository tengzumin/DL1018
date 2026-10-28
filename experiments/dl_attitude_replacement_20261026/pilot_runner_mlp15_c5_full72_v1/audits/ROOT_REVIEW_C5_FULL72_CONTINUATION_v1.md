# ROOT 审核：MLP15 C5 full72 扩展到剩余五场

## 首场审核结果

G1/W00 ACTIVE 候选完整运行 20,000 个 transitions / 20,001 个 states，状态 `STABLE`，无安全停止；电机饱和、generalized clip、tilt limit 均为 0。几何代理检查双向通过，最小间隙 51.18 mm，超过 15 mm 门槛。原始数据和独立复算记录在 `G1_W00_RAW_AUDIT_v1.json`。

13D 输入 trace 覆盖 1,999 次推理。逐事件从 wrapped 姿态误差、机体系角速度、BS 名义力矩和形态命令重构，最大绝对误差为 0。RBF 输出/更新及时变惯量重建标记均为 false；没有 Plant 真值或惯量重建输入。

| 指标 | MLP15 full72 | B | C5_RBF | 判读 |
|---|---:|---:|---:|---|
| 0–20 s 位置 Q | 10.318 mm | 12.510 mm | 9.975 mm | 胜 B；比 C5 高 3.44%，低于 10% 位置容差 |
| SO(3) RMSE | 0.062872 rad | 0.063361 rad | 0.062646 rad | 胜 B；本场略逊于 C5 |

C5_RBF G1/W00 的历史 completion-flag mismatch 已在复用清单和独立审计中披露，raw 未改写。单场只作工程门；它不替代六场等权宏平均性能判断。

## 决定

工程有效性、输入合法性和安全门全部通过。按冻结任务书，授权 G1/W12、G2/W00、G2/W12、G3/W00、G3/W12 五场各一次，连同已完成首场不超过 6 个候选 Plant 调用。仍复用已有 B/C5 raw，不读 TEST、不训练、不改参数。五场结束后停止并审核六场完整配对表；本次授权不自动晋升到 DEV72。

原 G1/W00 release 保留在 `MLP15_C5_FULL72_PILOT_RELEASE_G1_W00_v1.json`。扩展 release 通过 parent SHA 引用它，两个 release 的边界可由每个 `run_start.json` 复核。
