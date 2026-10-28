# 首场 wn12 trace replay 审计说明（待 root 审核执行）

脚本：`audit_filter_wn12_engineering_gate_raw.m`。它沿用父 study `audit_gru_stream_tracking_head_raw.m` 的 GRU/DeltaW trace replay 核心，但替换了父脚本不适用于本场的 72 场、RELEASED/current-release SHA、reuse 和 candidate path 假设。当前文件是审阅草案；本 agent 未运行 MATLAB，尚无 trace replay 结果。

## 复核内容

- `run_start`、`run_status`、attempt marker、raw `runIdentity` 和 log 中的场景/候选/历史 RELEASE SHA 链；raw SHA、manifest/input hashes、锁定模型和 v1 source lock。
- 固定模型 ID 与 model SHA；GRU 每事件重放、输出先于 DeltaW 更新、DeltaW 更新等式及 held torque；nominal BS feature 和 BS command torque closure。
- 重建当前锁定 cfg 的 wn-only `[12,12,12]` 覆盖，复核 fixed J0/Jdot0；确认无 variable-inertia reconstruction、无 Plant-truth 输入、`TEST_read=false`。
- 20,001 状态、20,000 个 1 ms transition、1,999 个 100 Hz attitude events，以及 motor saturation/generalized clipping。

## 历史 SHA 边界

首场 run-time RELEASE SHA 为 `06c8aba11fbaec0fc35d7e23397a362b38d0583decd99182793b912d4b43118e`，由 run_start/status/marker/raw identity/log 相互核对。原 RELEASE 字节未归档；当前 RELEASE 是 post-run DRAFT，因此脚本不会把当前 DRAFT SHA 当作 run-time SHA，也不会声称已经重新验证原 RELEASE 内容。

首场 `run_start` 记录的 source lock 是 `SOURCE_LOCK_v1`。v1 wrapper 元数据记录 SHA `c1c6a67455f2e5661b2bb478ba130980aa1e52454ed5559191e892f9235ba772`，但对应原始 wrapper 字节不可用。脚本核对 v1 中的 59 个 runtime source 文件并记录 v1 wrapper SHA；当前 wrapper SHA 单独按 v2 lineage 验证。它不会把当前 wrapper 说成首场实际执行字节。

首场 `candidate_raw_path` 规划为 `runs/<scene>/attempt_01/raw_run.mat`，实际 raw 按 status 留在 `runs/DL1018_DEV_T1_C10_W09/raw_run.mat`。脚本以 status 中的 raw path/SHA 为实际产物身份，并把这项差异写进报告，不移动或复制 raw。B/C5 的 `attempt_01` path 只作为配对输入。

## Root 单独执行命令

审核脚本和 v2 source lock 后，root 可在 MATLAB 中执行：

```matlab
studyRoot = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261027\task_attitude_filter_wn12_hf_screen_v1';
cd(studyRoot);
addpath(fullfile(studyRoot,'audits'));
audit_filter_wn12_engineering_gate_raw('DL1018_DEV_T1_C10_W09');
```

该命令只读取首场 raw、同场 locked DEV/VAL payload/B/C5、当前锁定模型和 source/config；审计本身不调用 closed-loop runner、Plant 或训练入口。成功时只在本目录写 `audits/DL1018_DEV_T1_C10_W09_WN12_ENGINEERING_GATE_TRACE_REPLAY.json`；已存在时脚本会拒绝覆盖。

当前 RELEASE 保持 DRAFT/授权 0，剩余 11 场未授权。此草案未运行；不构成通过结论或任何运行授权。
