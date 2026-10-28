# T1/T3 无位置残差 GRU 双 notch 独立复核

日期：2026-10-28。只读复核物理 DEV 场景 `DL1018_DEV_T1_C10_W09` 与 `DL1018_DEV_T3_C09_W09`（`TRAIN_C5_24`，fold `holdout_W06_10`）。未启动新 Plant、未读取 TEST/VAL 数据或旧错配 `DL1018_TRAIN` cohort；raw 中记录的 `Plant_calls=1` 是已有单场运行。

## 身份与控制条件

| 场景 | noGRU+notch raw SHA-256 | 对应 C5 raw SHA-256 | parent cosine-GRU raw SHA-256 |
|---|---|---|---|
| T1 C10 W09 | `5756b17a695f91567af048ee7be065bcb2ab3876cf10ec2967e925368da1a208` | `1e684df2174bc6b754e7798c67acb5c0b4ead218bcc1bd7b1d5cfc1a2fcf4991` | `c40239f9c9a6cea0f233eabdea3294b20ff4d3384e22a59055dc4e5358f5b541` |
| T3 C09 W09 | `6028d94915dcb47bd23b6babf81f93a31cd0ca8fb041cb45ec5d20f5bbabcd91` | `fa11a41b18ce9d4c3b7558d3bbb0d230aaef3e7071fc15419df0c6d1fca2f3a4` | `14176658aac8e8b69817f71aff748add1b591cee744cd05954184e52e34c2cb2` |

两条 noGRU release/status、raw SHA、binding 和 score 绑定一致；各 source lock 声明的 134 项数量及锁定 runner SHA 均匹配。两场固定同一个 C5 position model SHA `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e` 和 parent cosine-attitude model SHA `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`。C5/parent raw 均为相同场景的已绑定对照。

静态调用链的 exact-options 断言会在移除 dual-notch runtime payload 后，要求其余有效选项与冻结 C5 M110 options 完全相等。raw 记录 dual notch 开启、中心 `[2.2, 3.2] Hz`、`Q=[4,4]`、限幅 `3 m/s²`；既有 `3.5 Hz/Q1` notch 关闭。滤波点位于最终 C5 action 之后、force injection 之前；更新频率 100 Hz，非事件步保持上次输出。

当前 raw 的位置 residual-GRU `enabled=0`、事件数为 0，event/raw/clipped/applied correction 四类残差字段最大绝对值全为 0；模型权重未反序列化。与同场 `with-position-GRU + dual-notch` raw 相比，C5/parent 模型与 raw、notch 参数均相同，变化项是 residual-GRU 的开关。

## 实际动作链重放

两场各 20,000 个 1 kHz transition；stage-1 在样本索引 10、20、…、19,990 共 1,999 次更新（100 Hz）。我用 release 锁定的双notch 系数和 helper 递推，从 raw 的事件输入独立重放：

- notch raw 输出和限幅后输出与日志的最大绝对误差均为 `0`；无 notch clip event。
- 按事件输出重建全 1 kHz held action，与 `stage1_position_held_applied_acceleration_mps2` 的最大误差为 `0`。
- `stage1_position_held_force_I_N` 与 `stage1_position_injected_force_I_N` 最大差为 `0`；runner 对应代码在每次滤波后赋值 `heldForce=P.mass*notchApplied`，并将 held force 作为 `dF` 输入位置动力学。

## 冻结 scorer 结果

用冻结 `score_full72_candidate_v1.py` 对各场绑定的 B、C5、parent、预 notch candidate、with-GRU+notch、noGRU+notch 六份同场 TRAIN raw 重算，`Q_m`、`task_SO3_rad`、`inner_SO3_rad` 与 score JSON 逐值相同（数值差为 0）。下表为关键指标；`Q_m` 用 mm、task SO(3) 用 mrad。

| 控制器 | T1 Q / task | T3 Q / task | 两场算术均值 Q / task |
|---|---:|---:|---:|
| B | 10.985 / 42.201 | 11.022 / 59.061 | 11.003 / 50.631 |
| C5 | 10.466 / 43.273 | 9.645 / 60.705 | 10.055 / 51.989 |
| parent cosine-GRU + C5 | 9.493 / 43.308 | 9.418 / 60.663 | 9.456 / 51.986 |
| 双 notch + position residual GRU | 10.809 / 41.527 | 10.134 / 58.429 | 10.471 / 49.978 |
| 双 notch、无 position residual GRU | 9.703 / 41.539 | 9.701 / 58.438 | 9.702 / 49.989 |

两场均值下，无位置残差 GRU 的 Q 比 B 低 `11.83%`、比 C5 低 `3.51%`；比 parent 高 `2.61%`（约 `0.246 mm`），所以不能称为超过 parent 的位置收益。task SO(3) 均值则较 B/C5/parent 分别低约 `0.642/2.000/1.997 mrad`。同样双notch下，禁用位置 residual-GRU 后 Q 较 with-GRU 低 `7.35%`；task 只略高 `0.0103 mrad`。2.2/3.2 Hz task-error 两场均值为 noGRU `4.365/1.124 mrad`、with-GRU `4.318/1.141 mrad`，呈很小的频带交换，而非一致改善。

## 结论与边界

审计支持当前路径保留 C5 M110/DSSM position 与 parent cosine-GRU attitude，并且在这两个 W09 场景中不额外启用 position residual-GRU；fixed dual notch 的动作确实进入实际 force path。需要特别区分：预 notch attempt014/015 raw 仍记录 position residual-GRU enabled、各有 1,999 个事件，因此 **noGRU+notch 对该 pre-notch raw 不是“只加 notch”的单因素比较**。干净的 residual-GRU 消融是同场、同双notch的 with-GRU vs noGRU。两场 W09 的配对结果不能证明全 72 平均位置改善约 32%；历史冻结 replay 门仍为 `FAIL_FIXED_FROZEN_REPLAY`，本复核未改变该结论，也未作跨风推广。

复核输入集中于两个 `no_position_gru_notch_T{1,3}_single_v1` 的 release、binding、source lock、run status、raw、raw validator 和 score JSON，以及同场 C5、parent、with-GRU 对照 raw/status、冻结 scorer 和 runner/helper。没有查看其他 split 的评分记录。
