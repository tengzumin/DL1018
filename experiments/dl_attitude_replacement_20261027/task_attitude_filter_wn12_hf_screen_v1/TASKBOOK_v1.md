# filter-wn12 HF screen — taskbook (DRAFT)

状态：**首场工程门已完成：5 个 MATLAB 进程累计启动（2 次 pre-marker 失败、2 次 prepare-only、1 次闭环），1 个 Plant 航次完成，raw 为 STABLE / 20,000 transitions。当前 RELEASE 为 DRAFT、授权 0；剩余 11 场未放行，TEST 未读。**

**候选 raw 路径对账：**锁定 cohort 的 `candidate_raw_path` 为 `runs/<scene>/attempt_01/raw_run.mat`；B/C5 的 `attempt_01` 输入路径属于各自来源，不能用作候选输出路径。已完成的首场 raw 按现状保留在 `runs/DL1018_DEV_T1_C10_W09/raw_run.mat`，不移动或复制；其 `run_status.json`、run identity 与 SHA 绑定该产物。wrapper 现会把尚未运行场景的 raw 写到各自锁定 `candidate_raw_path` 所在目录，并在创建目录前校验规范化路径仍位于本 study 的 `runs/<同一 scene>/` 内。当前 RELEASE 仍为 DRAFT、授权 0、已完成 Plant 1；不得据此启动剩余场景。

**source lineage：**首场 `run_start` 记录使用 `SOURCE_LOCK_v1` / `SOURCE_DIFF_v1`；v1 中记录的 wrapper SHA 为 `c1c6a67455f2e5661b2bb478ba130980aa1e52454ed5559191e892f9235ba772`，但该 wrapper 原始字节和当时的 RELEASE 文件字节未归档。首场审计只能核 run_start、run_status、marker、raw identity/log 中历史 RELEASE SHA 一致，核 v1 runtime 59 文件锁及 v1 记录的 wrapper SHA；不得把当前 wrapper 声称为首场实际执行字节，也不得用 current DRAFT RELEASE SHA 替代历史 SHA。当前 wrapper 的路径对账及 v2 lock 检查属于后续 lineage：`SOURCE_LOCK_v2` 逐字节锁定 59 个 runtime 文件和当前 guarded wrapper。仅在 root 独立审核后另行授权的后续场次才使用 v2 lineage；此说明不改变原 12 场名单、配对来源和筛查规则。

首场 trace replay 审计草案见 `audits/audit_filter_wn12_engineering_gate_raw.m` 和同目录 `README_ENGINEERING_GATE_TRACE_AUDIT_v1.md`。脚本仅准备供 root 审核/单独执行；当前没有 MATLAB trace replay 结果，也没有授予剩余 11 场权限。

## 唯一候选改动

以 `gru_stream_cosine_tracking_head_full72_v1` 的冻结 no-blend cosine-GRU tracking-head 候选为基线。只把实际 prepared cfg 的 `control.command_filter.wn` 从 `[18,18,12]` 改为 `[12,12,12] rad/s`：roll/pitch 18→12，yaw 保持 12。运行入口在准备实际 cfg 后、组装 candidate options 前覆盖该数组，并检查把 wn 还原后整个 cfg 与原 cfg `isequaln`。滤波器实现、阻尼 `[1,1,1]`、加速度限幅 `[Inf,Inf,6] rad/s²`、`dt=0.001 s`、滤波器仍以起始 Euler 角、零角速度初始化；每个 1 kHz Plant transition 调用一次二阶递推，日志先记录当前输出再推进状态；初始化、采样和更新时机均锁定。

GRU 模型及 online tracking-DeltaW、输入特征和时序、DSSM14 位置模型、C5 输入/options、固定 J0/Jdot0、控制器增益、事件时钟、位置 Q 定义和全部安全限制均按父 study 绑定。没有 beta=.25/blend 逻辑。隔离 runner 共 59 个 `.m` 文件：58 个与直接父 source lock 逐字节一致；仅 `prepare_mlp15_dev72_no_plant.m` 的训练证据根路径绑定到既有 20261026 树，candidate runner 之外新增本 study guarded attempt wrapper。此路径适配不改模型、控制律、滤波参数或训练。

## 筛查假设与局限

锁定 raw 的 fixed-target 离线滤波重放显示：在记录的 Candidate task target streams 上，只把 roll/pitch `wn` 由 18 降到 12 rad/s，macro task→filtered-reference SO(3) RMSE 从 **60.537 mrad** 降到 **57.595 mrad**。这是筛查假设，不是结果：重放固定了旧 target 序列，不能代表闭环反事实或证明因果；滤波改变后，位置轨迹及后续 target 会变化。因此不能据此声称 task SO(3)、Q 或安全会改善。

本 study 的准备入口还校验父 study 的 72 行 DEV/VAL payload metadata（3 个非 MAT 文件逐字节复制并锁 SHA）；`prepare_mlp15_dev72_no_plant.m` 仅把 MLP15 准备证据目录指向既有 20261026 训练树，相关 JSON 与权重只按 SHA/绝对路径引用，未复制。本 study RELEASE 的 schema 对齐父闭环白名单 `DL1018_GRU_STREAM_DEV_RELEASE_V1`；仅修改本 study wrapper 的对应 guard，59 个 runtime 源文件未改接口。

当前 GRU 已在全 72 个 DEV/VAL 场景训练；本次 12 场与训练场景重叠，是 in-sample development screen，不是独立验证、泛化或 TEST 证据。B 的 72 场 parent raw-equivalence review 通过，但 historical runtime identity gap 仍在；保留该限定。所引用 C5 72 场 parent audit v2 为 PASS。

## 12 场固定 cohort 和来源

筛选规则冻结为：HF 从 W09–W14 中按每个 topology 取最低风 DEV 与最高风 VAL（并列按 C 索引小者）；W15 每个 topology 固定取一场：T1 取 DEV、T2/T3 取 VAL，各自在指定 split 内选最小 C 索引；W00–W08 每个 topology 固定取一场：T1 取 VAL、T2/T3 取 DEV，各自在指定 split 内选最小 C 索引。Exact ID 不可替换，组成 DEV6/VAL6、每个 topology 4 场。B/C5 原始文件均仅按绝对路径和 SHA 引用，见 `INPUT_LOCK_v1.json`。

| 序号 | 层 | 场景 | B 来源 | C5 来源 |
|---|---|---|---|---|
| 1 | HF | `DL1018_DEV_T1_C10_W09` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T1_C10_W09/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C10_W09/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 2 | HF | `DL1018_VAL_T1_C07_W14` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T1_C07_W14/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_VAL_T1_C07_W14/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 3 | HF | `DL1018_DEV_T2_C09_W10` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T2_C09_W10/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T2_C09_W10/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 4 | HF | `DL1018_VAL_T2_C04_W14` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T2_C04_W14/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_VAL_T2_C04_W14/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 5 | HF | `DL1018_DEV_T3_C09_W09` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T3_C09_W09/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C09_W09/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 6 | HF | `DL1018_VAL_T3_C01_W14` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T3_C01_W14/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_VAL_T3_C01_W14/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 7 | W15 | `DL1018_DEV_T1_C01_W15` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T1_C01_W15/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C01_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 8 | W15 | `DL1018_VAL_T2_C05_W15` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T2_C05_W15/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T2_C05_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 9 | W15 | `DL1018_VAL_T3_C02_W15` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T3_C02_W15/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T3_C02_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 10 | W00–W08 | `DL1018_VAL_T1_C00_W07` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_VAL_T1_C00_W07/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T1_C00_W07/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 11 | W00–W08 | `DL1018_DEV_T2_C00_W04` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T2_C00_W04/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T2_C00_W04/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |
| 12 | W00–W08 | `DL1018_DEV_T3_C00_W05` | `experiments/b_traceable_c3core_dev72_20261023/runs_b/DL1018_DEV_T3_C00_W05/B_TRACEABLE_C3CORE_V1/attempt_01/raw_run.mat` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C00_W05/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` |

## 两阶段门与停止规则

1. **No-Plant preflight：** 验证 12 个 DEV/VAL payload、B/C5 raw/status、候选模型、source tree、配置单差异及 exact scene order。任何缺失、SHA 不符、来源不等价或配置额外变化，停止；此阶段 Plant=0。 静态 Python 校验后，root 还须单独调用一次 MATLAB `prepare_mlp15_dev72_no_plant` 做真实 prepare-only 预检；该预检不得调用 `run_mlp15_dev72_closed_loop`，也不得创建 attempt marker，用于捕获静态校验无法发现的 MATLAB path/interface 缺项。root 审核该结果后，方可另行考虑工程门授权。
2. **工程门：** 仅场景 1 `DL1018_DEV_T1_C10_W09`，并须由 root 单独把 DRAFT release 改为 `RELEASED / ENGINEERING_GATE / 1 call`。检查稳定完成、独立 raw audit、输入/J0/位置模型/安全限制身份通过，且无 safety stop、motor saturation、generalized clipping 或 tilt limit。任何失败即停止，不运行剩余 11 场。
3. **审核门：** 场景 1 通过后暂停；剩余 11 场须由 root 检查工程门结果并另行签发 `REMAINING11 / 11 calls` release。launcher 要求 root review 状态与结果 SHA，未满足时拒绝启动。
4. **最终筛查门：** 12 场等场景 macro：`Q_m(candidate) <= Q_m(B)` 且 `Q_m(candidate) <= 1.05 * Q_m(C5)`；`task_SO3(candidate) < task_SO3(B)` 且 `< task_SO3(C5)`；12/12 均安全通过。`Q_m` 是每场 20001 个状态上的 RMS Euclidean position error，再对 12 场等权平均；`task_SO3` 是 task-reference 对实际姿态的 geodesic SO(3) RMSE，再对场景等权平均。Q 的等号允许，SO(3) 必须严格更优。不满足则筛查失败并停止，不做参数回调；任何单场安全/完整性失败均立即停止。

## 准确的 PowerShell 7 命令（仅供 root 审查后使用）

工程门：

```powershell
pwsh -NoProfile -File 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_filter_wn12_hf_screen_v1\RUN_FILTER_WN12_SCREEN_EXACT_v1.ps1' -Stage EngineeringGate
```

仅在工程门通过并经 root review、另行授权后运行剩余 11 场：

```powershell
pwsh -NoProfile -File 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_filter_wn12_hf_screen_v1\RUN_FILTER_WN12_SCREEN_EXACT_v1.ps1' -Stage Remaining11
```

当前 `RELEASE.json` 为 DRAFT，两个命令都会在启动 MATLAB 前拒绝执行。此处没有授权任何闭环/Plant 航次。
