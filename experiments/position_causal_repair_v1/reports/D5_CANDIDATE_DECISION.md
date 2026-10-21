# D5 修复候选同场 canary 判定

## 范围与结论

- 固定使用 BRIDGE6 六场 TRAIN；B、POS_OFF、Initial、C0 Final 均按 scene_id 复用同场数据。C0 身份与 D3 Selected Final 包一致，不新增 Plant。
- C2 X14 与 C1 X20 各完成 6/6 条完整、finite、STABLE 的 P_A 轨迹。C1 实际输入维度和日志重建一致，最大绝对误差 `2.22e-16`。
- 两候选均通过每任务姿态护栏；均未通过“六场宏 Q 优于同场 C0 Final”门槛，故 D5 无候选晋级，不运行 D6。
- D5 实际新增 Plant=14：C2 完整 6、C1 完整 6、两次 C1 维度错误的部分尝试各 1。另有两个零 Plant 工程尝试，均留在资源台账。D5 上限 18，未用满。

## 六场逐条配对

Q 为单条 0–20 s 三维位置 RMSE（m），A 为单条姿态 RMSE（rad）。

| Scene | Task | B Q | Initial Q | C0 Final Q | C1 X20 Q / A | C2 X14 Q / A |
|---|---|---:|---:|---:|---:|---:|
| DL1018_TRAIN_T1_C02_W08 | HELIX | 0.030277 | 0.046466 | 0.038633 | 0.040418 / 0.009434 | 0.047949 / 0.009313 |
| DL1018_TRAIN_T1_C02_W15 | HELIX | 0.007318 | 0.028784 | 0.019753 | 0.016621 / 0.020601 | 0.019331 / 0.020216 |
| DL1018_TRAIN_T2_C01_W08 | FIG8_3D | 0.036314 | 0.056211 | 0.047976 | 0.056935 / 0.025316 | 0.068096 / 0.023993 |
| DL1018_TRAIN_T2_C01_W15 | FIG8_3D | 0.016031 | 0.032308 | 0.024871 | 0.033937 / 0.016681 | 0.029405 / 0.016388 |
| DL1018_TRAIN_T3_C03_W08 | SQUARE | 0.024410 | 0.038627 | 0.028410 | 0.029921 / 0.010033 | 0.032553 / 0.010041 |
| DL1018_TRAIN_T3_C03_W15 | SQUARE | 0.007791 | 0.027401 | 0.017816 | 0.017491 / 0.020639 | 0.017887 / 0.020199 |

## 六场等权宏 Q 与胜负

| Series | Macro Q (m) | Beats B | Beats POS_OFF | Beats Initial | Beats C0 Final |
|---|---:|---:|---:|---:|---:|
| B | 0.020357 | — | — | — | — |
| POS_OFF | 0.083440 | 6/6 | — | — | — |
| Initial | 0.038299 | 0/6 | 6/6 | — | — |
| C0 Final (reused D3) | 0.029577 | 0/6 | 6/6 | 6/6 | — |
| C1 X20 fixed | 0.032554 | 0/6 | 6/6 | 4/6 | 2/6 |
| C2 X14 adaptation-aware | 0.035870 | 0/6 | 6/6 | 4/6 | 1/6 |

C1 improves on Initial by `0.005746 m` macro Q, and C2 by `0.002429 m`; however, C1 is `0.002977 m` worse than C0 Final and C2 is `0.006294 m` worse. Neither replaces B: both lose to B in all six scenes. Both are much better than POS_OFF.

## 姿态护栏与执行情况

原 G06 姿态护栏为每任务宏 A `<= 1.10 × same-scene B macro A + 0.002 rad`。

| Candidate | Task | Candidate macro A | B macro A | Limit | Result |
|---|---|---:|---:|---:|---|
| C1 | HELIX | 0.015018 | 0.014763 | 0.018240 | PASS |
| C1 | FIG8_3D | 0.020998 | 0.019764 | 0.023740 | PASS |
| C1 | SQUARE | 0.015336 | 0.015060 | 0.018566 | PASS |
| C2 | HELIX | 0.014764 | 0.014763 | 0.018240 | PASS |
| C2 | FIG8_3D | 0.020191 | 0.019764 | 0.023740 | PASS |
| C2 | SQUARE | 0.015120 | 0.015060 | 0.018566 | PASS |

两候选每场均为 1,999 个位置事件、1,968 个有效推理事件，最大事件间隔误差 `1.99e-15 s`；电机饱和率和广义量裁剪率均为 0。C1 推理时间 p99 为 0.428–0.477 ms，单次最大 18.127 ms、2 次超过 10 ms；C2 p99 为 0.319–0.421 ms，单次最大 17.824 ms、5 次超过 10 ms。D3 同机 Final 的 p99 最大 0.832 ms、单次最大 31.151 ms、合计 5 次超过 10 ms。因此 canary 没有超出本机 D3 既有观测范围的时序尾部；100 Hz 事件 cadence 未漂移。最大单次延迟仍保留为运行时监控项。

## 工程记录与证据边界

第一次 C1 尝试发现 `init_dl1018()` 的 `restoredefaultpath` 清除了候选路径，X20 因而被 14 维历史送入前向并在推理处中止；第二次部分尝试同样保留。随后运行器在初始化后重加隔离路径、用显式函数句柄验证路径，并归档每次错误尝试。两个部分尝试各计 1 次 Plant；路径检查失败的一次计 0。原始 MATLAB 源码没有改动。修复后 C1 实际运行使用 X20，6/6 完整，输入日志与重建误差不超过 `2.22e-16`。

C2 六场是在发现路径重置问题前完成的，实际使用原生产 X14 路径。候选和模型都是 X14；该生产路径与隔离副本的 X14 分支使用相同特征顺序、14×32 历史和前向计算，因此 C2 仍是有效的 X14 在线候选桥接，不构成 X20 路径验证。每场 X14 输入由原始日志的 `stage1_position_feature_14` 确定，MATLAB 零 Plant parity 报告另行验证了候选模型前向。C2 六场均完整且稳定。

逐场原始数据与指标：`D5_POSITION_CANDIDATE_C1.csv`、`D5_POSITION_CANDIDATE_C2.csv`；工程/Plant 消耗见 `RESOURCE_LEDGER.csv`。G06 原状态仍为 `STOP_POSITION_NOT_QUALIFIED`，D5 结果不回写旧门槛。
