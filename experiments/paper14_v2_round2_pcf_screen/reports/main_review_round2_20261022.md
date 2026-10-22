# DL1018 Round 2 主模型审核与 PROBE 决定

- 审核时间：2026-10-21 22:07:33 UTC
- 审查目录：`experiments/paper14_v2_round2_pcf_screen/`
- 计划截止：`2026-10-24T17:01:00Z`；TEST 保持封存。
- 决定：**批准仅运行首场 PROBE `DL1018_VAL_T2_C00_W10`；不批准 CONTINUE、72 场或 TEST。**

## 审核结论

Round 1 冻结 W 的 12 场筛查未通过：W09–W14 平均 Q 从 9.713 mm 增至 34.317 mm，Z 轴胜场 0/6；W00–W08 与 W15 也退化。Round 2 的 H2 让 FEATURE head 和 W 在线更新保持开启，仅关闭整个 PCF 协调子系统，检验其是否造成部分高频退化。它是机制筛查，不是只针对 eta 的状态级因果证明，也不预设 72 场达标。

源码/builder 和有效配置 smoke 确认唯一区别为 `command_filter_coordination_v3_5.enabled=false`；W 在线更新、FEATURE head、模型/W0、normalizer、姿态控制、C0/J0、X14、Plant、执行器、采样与场景条件都锁定。运行脚本只读已冻结 VAL 输入，不训练、不读 TEST、不重跑 ON/B；PROBE 只取预选字典序首场，失败会保留 marker/部分输出并停止。

## 审核证据

- PowerShell 静态测试：`ROUND2_STATIC PASS`；检查 PCF 单差异、源身份、12 个 VAL 场景与 24 个 ON/B raw、评分和资源门。PowerShell AST、Python AST 通过。
- MATLAB R2025b 离线 options smoke：`OFFLINE_OPTIONS_SMOKE_PASS`；闭环、episode、Plant 均未调用，optimizer steps=0；报告绑定当前输入锁 SHA `92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58`。
- 最新 no-marker preflight 报告整体为预期的 `BLOCKED`，唯一原因是没有 `-ParentReviewed`。资源子审计 `PASS`；全局活动 Compute 计数 0；哈希失败 0/81；VAL payload verifier exit=0；MATLAB=0；C: 可用约 156.1 GiB。两个 PIDS fallback（`dwm.exe`、`OmApSvcBroker.exe`）有可信 Win32 映射、逐 PID GPU engine 行且没有活动 Compute；非 Compute 图形行保持原始审计，不当作计算作业。
- `runs/` 不存在。预检没有停止进程、写航次或访问 TEST。launcher 将在启动前重新运行 reviewed preflight，要求报告在 5 分钟内、MATLAB=0、资源/磁盘/硬截止门均通过。
- CONTINUE 时长估算修正为 `max(30s, attempt_execution_and_raw_persistence_seconds) × 11 × 1.25`，包含 run_start/raw 持久化；旧 smoke 版本保留为 stale。

## 冻结身份

| 文件/证据 | SHA256 |
|---|---|
| TASKBOOK_ZH.md | `0de23a43f1e9c512e79a6cf3ac53d3aa95a7b24ce3aa18c60b60a718add3ff5e` |
| frozen_inputs.json | `92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58` |
| run_round2_pcf_screen.m | `e0a88377f1b397efbb939e34559a7b819afe2c5c5cea99fe1d5e909605c5393d` |
| preflight_round2.ps1 | `7e81fa54747da1a5221e01118d403f05b94faa393d8c166ff7db61515edfae7c` |
| launch_round2.ps1 | `fe8e2c0ac7f09d2d19bd599d68a3fc374e4f98e45aaed8c75742b9bdda00f91f` |
| static_test_round2.ps1 | `96933adb52f6c59892ba24438594848fecadc24d9e381673dffe9ccc34c269d2` |
| rescore_round2.py | `d2f0d3168bd41b2b91c471652ae7e4b044530ae2069a93755c21c53de6a724c5` |
| smoke v8 report | `a6fcb2fe3619014dacc3a42fe925799ae1b5432fd5dd725c827fcece81892780` |
| no-marker preflight v12 | `4536b8883a9c1c4f9220424be38e2c6def84355be6f81050510e65b356ed46f3` |

## 获批命令与后续门

仅授权以下一次首场 PROBE。运行后必须独立核验 marker、run_start/raw/status、模型/normalizer/W0/Plant/runtime 身份、eta=0、s_eff=clip(surface, ±[7,8,10])、在线更新事件、STABLE/完整性/安全、计时与输出字节。任一项不一致即停止并保留产物。

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode PROBE -ParentReviewed
```

PROBE 不会自动续跑。只有主模型审核 PROBE 通过后才决定是否启动其余 11 场；12 场门槛全过才可申请进入 72 场开发验证。

GPU 类型解释依据：[NVIDIA nvidia-smi process type definitions](https://docs.nvidia.com/deploy/nvidia-smi/index.html#processes)：WDDM `C+G` 表示 Compute 与 Graphics contexts，不单独表示当前 kernel 活动；因此资源门以 Compute engine 活动计数为准。
