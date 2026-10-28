# N4 T3 C09 W09 单场闭环独立复核

日期：2026-10-28。只读审计 `DL1018_DEV_T3_C09_W09`（`TRAIN_C5_24`，fold `holdout_W06_10`）的 N4 已有 raw。未启动新 Plant，未读取 TEST/VAL 数据；raw 的 `Plant_calls=1` 是已有单场闭环调用。

## 身份与唯一干预

- N4 raw SHA-256：`9ba6b7e2797f36f6714f2c13791d142f3fbb1c47b5a4c8f8d3436178f4f77f2e`；status SHA-256：`e777d7d542ef4d206dc68e6ebd72d1edaa4c27a535326f307092d5b108978873`。raw 文件为 `n4T3C09_v1/runs/DL1018_DEV_T3_C09_W09/attempt_01/raw_run.mat`；raw、status、binding、score 与 source lock 的哈希交叉匹配；source lock 中 isolated runner 哈希也匹配。双notch noGRU 对照 raw SHA 为 `6028d94915dcb47bd23b6babf81f93a31cd0ca8fb041cb45ec5d20f5bbabcd91`。
- 场景、C5 DSSM position model SHA `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`、parent cosine-GRU attitude model SHA `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`、parent raw SHA `14176658aac8e8b69817f71aff748add1b591cee744cd05954184e52e34c2cb2`、C5 raw SHA `fa11a41b18ce9d4c3b7558d3bbb0d230aaef3e7071fc15419df0c6d1fca2f3a4`，均与同场 no-position-GRU 双notch对照绑定相同。冻结 C5 options 在移除滤波 runtime payload 后通过 exact-options 断言。
- 位置 residual-GRU 未启用、未加载；raw 记录 0 个事件，raw/clipped/applied residual 非零计数全为 0。既有 `3.5 Hz/Q1` notch 关闭。
- N4 是 100 Hz、限幅 `3 m/s²` 的四节二阶 notch：`[2.2, 3.2, 3.7, 4.8] Hz`、各 `Q=4`，最终 C5 action 后、force injection 前更新，其他时刻零阶保持；无风/W 分支。与同场双notch noGRU相比，前两节系数逐值相同，新增的只有 3.7、4.8 Hz 两节。实际闭环输入会因反馈而分化，这不改变模型、场景和滤波位置一致的事实。

## 4 节动作链重放

T3 raw 含 20,000 个 1 kHz transition、1,999 个 stage-1 更新（索引 10 到 19,990，间隔 10 ms）；首个非零滤波输入在索引 320。按 release 的 4 组系数和 helper 初始化规则独立重放：首次非零样本直通并初始化全部 section histories，之后逐节递推，输出限幅到 ±3，事件间保持。

- raw 与限幅后事件输出相对日志的最大绝对误差均为 `0`；全程 held action 重建误差为 `0`。
- held force 与 injected force 最大差为 `0`；runner 代码在滤波事件处设置 `stage1PositionHeldForce=P.mass*notchApplied`，之后将此 held force 作为 `dF` 输入位置动力学。
- raw validation 和独立重放均确认无 clip event。没有发现未落入实际力路径的旁路滤波结果。

## 冻结分数

用绑定的冻结 `score_full72_candidate_v1.py` 重算 N4、B、C5、parent 与双notch noGRU 同场 raw；N4/B/C5/parent 的 `Q_m`、task/inner SO(3) 与 N4 score JSON 逐值相同。下表中 `Q_m` 为 mm，task/inner 为 mrad。

| 对照 | Q_m | task SO(3) | inner SO(3) |
|---|---:|---:|---:|
| N4 | 9.908 | 58.495 | 9.289 |
| 双notch noGRU | 9.701 | 58.438 | 9.287 |
| B | 11.022 | 59.061 | 10.703 |
| C5 | 9.645 | 60.705 | 10.785 |
| parent cosine-GRU + C5 | 9.418 | 60.663 | 9.645 |

N4 相对双notch noGRU 的 Q 高 `0.207 mm`（`+2.13%`），task 高 `0.0568 mrad`；相对 B 的 Q 低 `10.11%`、task 低 `0.567 mrad`；相对 C5 的 Q 高 `2.73%`、task 低 `2.210 mrad`；相对 parent 的 Q 高 `5.20%`、task 低 `2.168 mrad`。N4 局部诊断预设的 `Q ≤ 1.05×C5`、task 不劣于 B、20k 稳定、零安全计数四项均通过；这只是 T3 单场诊断。

## 谱对照

我按 N4 scorer 相同的窗函数、频带和定义重算 N4 与双notch noGRU 的 band RMS。task-error 为 wrapped task Euler−actual Euler 向量 RMS；action 为 held applied acceleration 向量 RMS。频带边界为 `[中心−0.5, 中心+0.5) Hz`；3.2 Hz 与 3.7 Hz 两个频带有 0.5 Hz 重叠，数值是闭环 raw 频谱，不能当作单独滤波器的传递函数。

| 中心/频带 | task-error N4 / 双notch (mrad) | applied action N4 / 双notch (m/s²) |
|---|---:|---:|
| 2.2 Hz `[1.7,2.7)` | 4.792 / 4.343 | 0.02800 / 0.02076 |
| 3.2 Hz `[2.7,3.7)` | 1.248 / 1.252 | 0.003824 / 0.004821 |
| 3.7 Hz `[3.2,4.2)` | 1.058 / 1.054 | 0.001218 / 0.002694 |
| 4.8 Hz `[4.3,5.3)` | 0.137 / 0.202 | 0.002215 / 0.005671 |

结果显示额外两节降低了 3.7/4.8 Hz 频带动作量，但 2.2 Hz 频带动作量和 task-error 高于双notch；N4 的 0.05–0.5 Hz action RMS 为 `0.09128 m/s²`，parent 为 `0.09293 m/s²`（比值 `0.9822`），与双notch noGRU 的 `0.09109 m/s²` 接近。单场数据不足以推广滤波效果。

## 原门状态与边界

本次 score 保留 `prior_two_notch_status_preserved=FAIL_FIXED_FROZEN_REPLAY`；N4 的 `PASS_FIXED_T3_C09_N4_DIAGNOSTIC` 只表示其四项单场诊断标准通过，不替代或改写原冻结 replay/相位 FAIL，也不构成候选整体接收。未运行新 Plant，未用 TEST/VAL 或未见风真值。

