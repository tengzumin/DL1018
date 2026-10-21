# DSSM14 26 个输场离线诊断

日期：2026-10-22（北京时间）。范围为 corrected DSSM14 对 FULL B 的 VAL/DEV 已完成原始日志；本轮未访问 TEST，也未启动 Plant、训练或采集。

## 结论与边界

corrected DSSM14 的 72 场结果复算为 B 均值 **17.058080675 mm**、DSSM14 均值 **12.387217899 mm**，**46 胜 / 26 负 / 0 平**。26 场平均退步 **0.854737 mm**；最大退步 **2.406268 mm**，场景为 **DL1018_VAL_T3_C00_W13**。

26 场原始误差复算的 0–5 s / 5–20 s 分组为 **12 两段均更差、4 仅早段更差、10 仅后段更差**。16/26 的 0–5 s Q 更高，22/26 的 5–20 s Q 更高；这两个阶段的 RMSE 不可相加，也不能把当前 DSSM14 26 场归成“全由早段”或“全由后段”。父模型独立逐表检查 `PARENT_LOSS_PHASE_CHECK.json` 与本次 raw 复算一致。

位置分轴有一个稳定关联：26/26 输场的 Z 轴 0–20 s 位置误差 RMSE 高于 B；X 为 17/26，Y 为 9/26。26 场汇总轴差（候选减 B）见下表，单位 mm。父模型独立按 ΔMSE 重算后，只有 **14/26** 场的 Z 是最大的正 ΔMSE 轴；三个预固定胜场的 Z 轴也都略高于 B，但其他轴改善抵消。故 Z 是值得继续核对的共同信号，不能说它解释全部输场，更不能据此归因给 W 更新、先验或任何单一控制环节。

| 阶段 | 轴 | 平均轴 RMSE 差 | 候选高于 B | 最小 … 最大差 |
|---|---:|---:|---:|---:|
| 0–5 s | X | +0.821 | 15/26 | -3.083 … +4.039 |
| 0–5 s | Y | +0.443 | 15/26 | -1.192 … +1.982 |
| 0–5 s | Z | +1.461 | 26/26 | +0.078 … +3.615 |
| 5–20 s | X | +0.129 | 16/26 | -1.530 … +1.487 |
| 5–20 s | Y | -0.428 | 9/26 | -2.385 … +1.892 |
| 5–20 s | Z | +2.751 | 23/26 | -0.601 … +5.953 |
| 0–20 s | X | +0.350 | 17/26 | -1.851 … +2.270 |
| 0–20 s | Y | -0.187 | 9/26 | -1.131 … +1.227 |
| 0–20 s | Z | +2.389 | 26/26 | +0.055 … +5.354 |

| Split | Task | 输场数 | 阶段分组（两段 / 仅早 / 仅后） | 0–20 s Z 平均轴 RMSE 差（mm） | Z 高于 B |
|---|---|---:|---|---:|---:|
| VAL | FIG8_3D | 5 | 两段 1 / 仅早 0 / 仅后 4 | +2.316 | 5/5 |
| VAL | HELIX | 5 | 两段 4 / 仅早 0 / 仅后 1 | +2.311 | 5/5 |
| VAL | SQUARE | 6 | 两段 3 / 仅早 2 / 仅后 1 | +2.599 | 6/6 |
| DEV | FIG8_3D | 3 | 两段 2 / 仅早 0 / 仅后 1 | +4.341 | 3/3 |
| DEV | HELIX | 3 | 两段 1 / 仅早 1 / 仅后 1 | +0.920 | 3/3 |
| DEV | SQUARE | 4 | 两段 1 / 仅早 1 / 仅后 2 | +1.900 | 4/4 |

## 身份、覆盖与复核

先以最新 PAIR14 对 B 配对表、`SCENE_COMPARISON_V2.csv`、V3 计划、FULL B `RAW_INDEX.csv`、两套 corrected PAIR14 session `RAW_INDEX.csv` 和现有 216 行原始文件完整性表核验身份，再固定原始文件白名单，随后才打开 raw。白名单为 **26 个输场 + 每个任务一个事先固定的 VAL 胜场 = 29 场 ×（B、DSSM14）= 58 个文件**，仅 VAL/DEV；session 原始索引通过 candidate 的 manifest index 对应 original 1–123 或 tail21 124–144。没有 TEST 行或 TEST raw path。

58/58 文件的 SHA、大小与 mtime 均和当前索引/完整性记录一致；每场的 B/DSSM14 合同、transition 时间网格和外部物理数组身份通过校验。纯离线 `raw_scan.arr` / `raw_scan.score` 逐文件重算全程与两个阶段 Q，并复核外部数组 hash；29/29 候选的已完成 runtime replay 为 `REPLAY_VALID`。父模型另独立以 h5py 直接抽查了 3 个代表配对（最差、仅早段更差、仅后段更差；共 6 个 raw），Q 误差不超过 1e-12 m，SHA 和外部物理数组逐元素吻合，见 `../PARENT_RAW_SPOTCHECK.json`。旧 `prior_adaptation_audit_v1` 只包含旧 FULL72 NN 审计，未作为 corrected DSSM14 证据复用；本次复用了 corrected 144 行 composed replay 与纯评分 helper。

`FULL288` 名称容易误解：冻结 comparison plan 指向的 `supporting_rescore/outputs/RAW_METRICS.csv` 经核实为 288 行，`split` 仅有 VAL、DEV，TEST 行为 0；其 SHA-256 `e9736f11487385bf1feceb9bee4a68b2b7547f8875fbe071d1ffff009d757384` 与 plan 绑定一致。该文件用于配对前校验 B 外部数组身份，筛选进本诊断的 B 行仍仅为 72 场 VAL/DEV。

关键输入身份（其余输入完整 SHA、尺寸和路径见 `identity_and_scope.json`）：

- `PAIR14_SCENE_RESULTS_VS_B.csv` SHA-256：`b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137`。
- `SCENE_COMPARISON_V2.csv` SHA-256：`a1d8479126ec33891ae336177e6a54fd05ad97c60e27ea253fb4f1ac0f96d4b9`。
- `RAW_METRICS.csv`（上述 FULL288 评分输入）SHA-256：`e9736f11487385bf1feceb9bee4a68b2b7547f8875fbe071d1ffff009d757384`。
- FULL B `RAW_INDEX.csv` SHA-256：`4213d3b9993fe64940e558dbb7da198b18d9fa9cfa44064fcbbea80ea04806f5`。
- corrected PAIR14 两 session 索引、composed replay、FULL B metrics、冻结计划与 raw 文件 SHA 均记录于 `raw_whitelist.csv`、`identity_and_scope.json`。

## 阶段轴与运行时证据

固定的每任务胜场参照按“最早 VAL `source_scene_id` 的 PAIR14 胜场”选择，先于打开 raw：

| Task | 固定参照场景 | 0–20 s Q 差（mm） | 0–5 s Q 差（mm） | 5–20 s Q 差（mm） |
|---|---|---:|---:|---:|
| FIG8_3D | DL1018_VAL_T2_C02_W12 | -0.886 | -0.583 | -1.103 |
| HELIX | DL1018_VAL_T1_C00_W07 | -4.609 | -3.604 | -5.685 |
| SQUARE | DL1018_VAL_T3_C03_W00 | -2.245 | -3.333 | -1.764 |

DSSM14 的 29 个日志均有 1968 个有效推理事件，首个事件和 Head 更新均在 0.32 s；每场 Head 更新数为 1968。26 个输场中 `weight_delta_fro` 的逐事件均值跨场平均为 0.002582，p95 跨场平均为 0.005238。记录的初始 W0 范数在 29/29 场都是 **5.972779706（非零）**，runtime replay 的 W0 error 均为 0；分析没有把 trained output_W 当作零初始化。

26 个输场的每场 1 秒 Q 中，首次出现 DSSM14 Q 高于 B 的箱为 [1,2) s 的有 15 场、[2,3) s 的有 11 场。这只是首个 **1 秒箱级**的候选高于 B 时点，不是精确误差分叉或发散时刻。它发生在首个更新时间之后，但不同闭环轨迹下的时间并置不证明 Head 更新导致误差。现有 per-phase/axis 表同时记录 a_nominal、a_req、a_f、event raw/applied 与误差 RMSE；其 0–20 s 每场-轴 RMSE 均值为：

| 指标（m/s²） | B | DSSM14 |
|---|---:|---:|
| 标称加速度 a_nominal | 0.256 | 0.253 |
| 状态速度数值导数加速度（FD） | 0.313 | 0.346 |
| FD 减标称加速度的 RMSE | 0.186 | 0.227 |
| PCF 请求 a_req（仅候选事件） | 不适用 | 0.453 |
| PCF 滤波 a_f（仅候选事件） | 不适用 | 0.395 |
| 事件 raw acceleration（仅候选事件） | 不适用 | 0.323 |
| 事件 applied acceleration（仅候选事件） | 不适用 | 0.318 |

`a_req`、`a_f` 是相应日志字段，不称为实际加速度。没有用独立 plant `a_actual` 字段；表中的 `a_actual_from_state_derivative` 是从状态速度按实测 1 ms transition 时间戳做中心数值求导，首末样本排除，并非独立物理加速度测量。26 个输场汇总的 raw-to-applied/β 振幅差异 proxy 计数为 0，stage1 projection active 为 0，motor saturation 为 0，generalized clipping 为 0；这些被记录的标志/等价 proxy 在候选日志中均未触发。PCF eta 的 before/after 向量范数 p95 跨 26 场平均分别为 0.059626 与 0.059539 m/s，before/after 很接近。此处没有把观测到的关联写成部件因果，也没有从 C/W 名称推断风或形变含义。

字段覆盖表逐文件记录字段是否存在、有效事件数、有效事件有限值行数、mask 外非有限值和布局。候选的有效事件输出按 `stage1_position_event_inference_valid` mask 筛选，mask 外 NaN 不进入统计；B 日志没有有效在线推理事件（29/29 为 0），所以 Head、PCF 事件字段在 B 上标为不适用，而不是猜补。字段与对应时间段/轴的详细数值在 `phase_axis_metrics.csv`、`control_phase_metrics.csv`、`group_axis_summary.csv`、`group_control_summary.csv`。

### 补充：Z 轴 raw 输出的先验/在线分解

对 `raw_whitelist.csv` 中 29 个 DSSM14 VAL/DEV 候选 raw 逐文件核验后，确认日志包含完整逐事件 `weight_before`、`weight_after`、`phi_33` 和 `weight_initial`，并非只有 `weight_delta_fro`。29/29 场字段均存在且所选数据全有限：原始 HDF5 形状分别为 inference mask `(1,20000)`、step index `(1968,1)`、`phi_33 (33,20000)`、事件前/后权重各 `(1968,3,33)`、`weight_initial (3,33)`、事件 raw acceleration `(3,20000)`。有效事件 mask 后每场均为 1968 个样本（0–5 s 468 个、5–20 s 1500 个、全程 1968 个）。

用 `W_before × phi` 重建事件 raw acceleration，29 场最大绝对误差为 **6.66×10⁻¹⁶ m/s²**（阈值 1×10⁻⁸ m/s²）。下表为每场指标再做等权跨场平均；输出为同一批记录状态上的 `W_initial × phi` 与日志在线 raw Z，加上在线减初始输出的差值。RMS 对差值逐事件计算，单位均为 m/s²。这里的差值只表示固定状态上的 raw 输出变化，不表示误差改善/恶化，也不构成权重更新导致位置退步的因果证据。

| 场组 | 阶段 | 场数 | 初始 Z 均值 | 初始 Z RMS | 在线 Z 均值 | 在线 Z RMS | 在线−初始均值 | 在线−初始差值 RMS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 26 输场 | 0–5 s | 26 | +0.005421 | 0.033933 | -0.007198 | 0.085299 | -0.012619 | 0.064109 |
| 26 输场 | 5–20 s | 26 | +0.019965 | 0.033798 | -0.013746 | 0.104365 | -0.033710 | 0.098879 |
| 26 输场 | 全程 | 26 | +0.016506 | 0.034620 | -0.012189 | 0.100288 | -0.028695 | 0.092008 |
| 固定胜场参照 | 0–5 s | 3 | +0.012882 | 0.024285 | +0.072902 | 0.082516 | +0.060020 | 0.066205 |
| 固定胜场参照 | 5–20 s | 3 | -0.001771 | 0.020578 | +0.084432 | 0.095430 | +0.086203 | 0.089738 |
| 固定胜场参照 | 全程 | 3 | +0.001713 | 0.021533 | +0.081690 | 0.092692 | +0.079977 | 0.084821 |

逐场、逐阶段结果在 `prior_online_z_rebuild.csv`，逐场字段形状与有限值覆盖在 `prior_online_z_field_coverage.csv`，汇总及重建门限在 `prior_online_z_summary.json`。本次没有引入 target、beta 或 clip，也没有读取 B 或 TEST raw。完整事件权重现已足以在不新增数据的情况下继续做 Z 通道先验/在线 raw 输出分解；若要把 raw 输出变化映射到跟踪误差，需先在后续单独核实相应 target/参考字段的语义。

## 26 场完整配对表

Q 值单位 mm；Δ=候选−B。阶段 Δ 由各阶段 RMSE 分别计算，**不可相加**。首个 1 秒箱列只标示候选 Q 首次高于 B 的箱；空值表示 20 个一秒箱内没有高于 B。

| Split | Task | 场景 | B Q 0–20 | DSSM14 Q 0–20 | Δ0–20 | Δ0–5 | Δ5–20 | 首个 1s 箱 Q候选>B |
|---|---|---|---:|---:|---:|---:|---:|---:|
| DEV | FIG8_3D | DL1018_DEV_T2_C09_W10 | 10.613 | 11.627 | +1.014 | -0.042 | +1.886 | [2,3) s |
| DEV | FIG8_3D | DL1018_DEV_T2_C12_W13 | 11.545 | 12.546 | +1.000 | +0.290 | +1.569 | [2,3) s |
| DEV | FIG8_3D | DL1018_DEV_T2_C14_W14 | 10.757 | 11.999 | +1.241 | +0.233 | +1.798 | [1,2) s |
| DEV | HELIX | DL1018_DEV_T1_C10_W09 | 10.985 | 11.465 | +0.480 | +0.455 | +0.492 | [1,2) s |
| DEV | HELIX | DL1018_DEV_T1_C11_W12 | 10.507 | 10.959 | +0.452 | +1.647 | -0.048 | [1,2) s |
| DEV | HELIX | DL1018_DEV_T1_C15_W14 | 12.148 | 12.293 | +0.145 | -0.142 | +0.269 | [2,3) s |
| DEV | SQUARE | DL1018_DEV_T3_C03_W15 | 5.584 | 6.332 | +0.748 | +3.158 | +0.148 | [1,2) s |
| DEV | SQUARE | DL1018_DEV_T3_C10_W11 | 12.916 | 14.610 | +1.694 | -0.519 | +2.607 | [2,3) s |
| DEV | SQUARE | DL1018_DEV_T3_C13_W12 | 10.415 | 11.338 | +0.923 | +3.620 | -0.302 | [1,2) s |
| DEV | SQUARE | DL1018_DEV_T3_C15_W14 | 11.421 | 11.876 | +0.455 | -0.044 | +0.712 | [2,3) s |
| VAL | FIG8_3D | DL1018_VAL_T2_C00_W10 | 8.517 | 8.694 | +0.177 | -0.713 | +1.080 | [2,3) s |
| VAL | FIG8_3D | DL1018_VAL_T2_C01_W11 | 11.775 | 12.558 | +0.783 | -0.579 | +1.516 | [2,3) s |
| VAL | FIG8_3D | DL1018_VAL_T2_C03_W13 | 9.543 | 9.871 | +0.328 | -0.055 | +0.603 | [2,3) s |
| VAL | FIG8_3D | DL1018_VAL_T2_C04_W14 | 9.772 | 10.301 | +0.529 | -0.377 | +1.254 | [2,3) s |
| VAL | FIG8_3D | DL1018_VAL_T2_C15_W09 | 9.543 | 10.326 | +0.783 | +1.944 | +0.185 | [1,2) s |
| VAL | HELIX | DL1018_VAL_T1_C02_W09 | 9.481 | 9.781 | +0.299 | -0.084 | +0.520 | [2,3) s |
| VAL | HELIX | DL1018_VAL_T1_C04_W11 | 10.362 | 11.826 | +1.463 | +2.153 | +1.144 | [1,2) s |
| VAL | HELIX | DL1018_VAL_T1_C06_W13 | 8.794 | 10.439 | +1.644 | +1.972 | +1.593 | [1,2) s |
| VAL | HELIX | DL1018_VAL_T1_C07_W14 | 13.799 | 14.205 | +0.405 | +0.339 | +0.436 | [1,2) s |
| VAL | HELIX | DL1018_VAL_T1_C08_W15 | 9.162 | 10.209 | +1.047 | +1.488 | +1.155 | [1,2) s |
| VAL | SQUARE | **DL1018_VAL_T3_C00_W13** | 7.372 | 9.779 | +2.406 | +2.951 | +2.863 | [1,2) s |
| VAL | SQUARE | DL1018_VAL_T3_C01_W14 | 11.405 | 11.446 | +0.041 | -1.880 | +1.191 | [2,3) s |
| VAL | SQUARE | DL1018_VAL_T3_C02_W15 | 7.044 | 7.888 | +0.843 | +3.158 | +0.416 | [1,2) s |
| VAL | SQUARE | DL1018_VAL_T3_C13_W10 | 11.161 | 12.042 | +0.881 | +3.899 | -0.671 | [1,2) s |
| VAL | SQUARE | DL1018_VAL_T3_C14_W11 | 14.044 | 16.139 | +2.095 | +2.842 | +1.807 | [1,2) s |
| VAL | SQUARE | DL1018_VAL_T3_C15_W12 | 9.802 | 10.146 | +0.344 | +3.703 | -1.599 | [1,2) s |

## 下一步（单项建议）

若继续，唯一建议是基于这 29 场现有日志，先核实可用 target/参考加速度字段的身份，再在相同状态和时间戳上比较 `W_initial × phi` 与在线 Z raw 的目标残差；只有字段语义核实通过才计算残差。当前已能逐项复建 raw 输出，但还没有证据把在线输出变化解释为跟踪误差的因果来源。26/26 输场的 Z 轴 RMSE 高于 B、只有 14/26 场 Z 是最大正 ΔMSE 轴、三个胜场参照的 Z 也略高于 B，这些证据支持聚焦 Z 通道继续核验，不支持直接关闭 Head 或混合 B。

## 可重跑与产物

在 PowerShell 7、当前工作区根目录下运行：

```powershell
python reports/integration_next14_v1/losing26/diagnose_losing26.py --prepare
python reports/integration_next14_v1/losing26/diagnose_losing26.py --analyze
python reports/integration_next14_v1/losing26/rebuild_prior_online_z.py
```

`--prepare` 只验身份并先写白名单，不打开 raw；`--analyze` 只顺序读取白名单中的 58 个文件。两项原分析均退出码 0，汇报 58/58 文件、29/29 配对；72 场和输场阶段数复算通过。新增 raw 输出重建脚本退出码 0，覆盖 29/29 DSSM14 候选及 87 个场景-阶段行，重建误差通过 1e-8 m/s² 门限。主要文件：`loss_26_scene_table.csv`（26场）、`fixed_task_win_refs.csv`（3个预固定参照）、`raw_whitelist.csv`、`identity_and_scope.json`、`raw_file_diagnostics.csv`、`phase_axis_metrics.csv`、`control_phase_metrics.csv`、`field_coverage.csv`、`group_axis_summary.csv`、`group_control_summary.csv`、`scene_pairs.csv`、`prior_online_z_rebuild.csv`、`prior_online_z_field_coverage.csv`、`prior_online_z_summary.json`。
