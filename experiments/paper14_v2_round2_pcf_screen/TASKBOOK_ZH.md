# DL1018 Round 2：PCF 协调子系统单因素 12 场筛查任务书

## 状态与边界

版本：`PAPER14_V2_R2_PCF_OFF_SCREEN_20261022_REVISION_4`  
冻结时间：2026-10-21 20:46:44 UTC（2026-10-22 04:46:44 Asia/Shanghai）  
主目标：`reports/paper14_v2/STATE.json` 中的 72 小时论文结果攻关目标。  
本任务书授权范围：**只允许在本目录建立隔离 runner、输入锁、静态验证和评分器，并执行不调用 Plant 的离线验证。当前不授权 MATLAB 闭环航次。**

Round 1 的 12 场门槛失败，不进入 72 场。TEST 保持封存。不得训练、调参、改模型、扩展场景、读取 TEST、重跑 B/原 PCF-on DSSM、覆盖旧结果、删除文件或停止现有进程。Round 2 与 Round 1 产物分目录保存；Round 1 及其它历史工程只读。

## 问题、假设与解释边界

Round 1 只关闭在线 W 更新，未能区分 PCF 对在线更新信号的作用。锁定 runtime 的 FEATURE+在线更新分支显示：PCF 开启时，runner 先计算 `surface - eta_before` 再按 `[7,8,10]` 分轴限幅；PCF 关闭时直接对 `surface` 做同一限幅。两条分支都将所得 `s_eff` 传给同一个锁定 helper `position_only_search_head_step` 更新 W。PCF 关闭也会停止 `eta` 的离散递推，初始 `eta=0`。当前调用链中 `a_f`、`r_f` 只进入诊断日志，不进入位置/姿态/执行器命令。项目里的 `position_stage1_update_head*.m` 是 `stage1SearchEnabled=false` 时才进入的另一分支，不是此候选实际使用的 helper。

唯一优先假设 H2：**当 W 在线更新保持开启时，PCF 协调子系统对更新方向的修正可能是 W09–W14 闭环位置误差偏高的因素之一；关闭该子系统后，高频 Q 应优于原 PCF-on 候选，并改善多数高频场景的 Z RMSE。** 这是待证伪机制假设，不是已确认根因，也不预设新候选达到 72 场验收。

本轮因果干预定义为整个 `command_filter_coordination_v3_5` 子系统开/关；不得把闭环轨迹间差异表述成仅 `eta` 的 isolated state-level 因果证明。候选与原 PCF-on/B 在相同场景、初始状态和物理条件下配对，但轨迹会因干预而分叉。

## 唯一实验差异与固定条件

候选构造器必须从相同 `position_only_search_options(cfg, model, 'FEATURE', 12, 1)` 基线生成选项，并且**只**将

```matlab
opts.stage1_position_runtime.command_filter_coordination_v3_5.enabled = false;
```

其余条件全部逐字段相同。特别是 `stage1_position_runtime.enabled=true`、`update_enabled=true`、FEATURE Head、kappa=1、gamma=12、beta=1、W0、模型、normalizer、姿态控制、C0/J0、Plant、执行器、X14、采样率和初值不得变化。optimizer steps=0；不训练。

静态实现必须断言 options 与 PCF-on 基线除上述布尔值外 `isequaln`；run_start/raw/status 必须记录 Head=FEATURE、update=true、PCF=false、固定模型/normalizer/W0 身份、scene ID、输入与源码哈希。还须用冻结的有效配置执行不调用 Plant 的 options/path smoke，确认不会触发 runner 中“AttitudeFusion 下位置 Head active 必须 PCF enabled”的断言，且任何配置层都没有把 PCF=false 覆盖回 true；若冲突或无法验证，停止且不授权 PROBE。首次 PCF-off 航次须确认 `eta` 保持零，且未扣除 eta 的原始 surface 被送入既有 Head 更新 helper，再按现有 `[7,8,10]` m/s² 分轴限幅后参与更新；同时确认 W 在线更新事件实际执行。任何运行时证据不一致即停止并保留产物，不重试。

## 冻结输入身份与场景

只复用 Round 1 的身份合格输入。R2 必须以自身 `frozen_inputs.json` 再锁定这些路径和哈希，不得修改 Round 1 文件：

| 输入 | 路径 | SHA256 |
|---|---|---|
| Round 1 完整输入锁（上游身份契约） | `experiments/paper14_v2_round1_frozen_w0_screen/frozen_inputs.json` | `3aa4aaa36bddec431f5b1b03d8e0dd9e5d5866818e343b81fddf1b9c2ca19eb3` |
| 固定 12 场 VAL 清单 | `reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv` | `176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e` |
| 24 个已配对 ON/B raw 身份清单 | `experiments/paper14_v2_round1_frozen_w0_screen/reused_pair_raw_manifest.csv` | `3bdfe154105f399607584a56ab0e67e498d200395a76adfe46fd1455880cf2b6` |
| 逐场 14 个物理字段 payload 等同性记录 | `experiments/paper14_v2_round1_frozen_w0_screen/scene_payload_identity.csv` | `d6a76d83d6e98ab9f29a1dff3ad479ccdfde6dc581cad70f2da4014367bddd16` |
| Round 1 B/PCF-on/冻结 W0 配对原始重评分表 | `experiments/paper14_v2_round1_frozen_w0_screen/reports/round1_screen_results.csv` | `2090abdc99b386650c6f5debf75974b34943dfa2b45129fe913efeafb1214dc4` |
| Round 1 12 场总结 | `experiments/paper14_v2_round1_frozen_w0_screen/reports/round1_screen_summary.json` | `b1e39d991133a3b0b3ffc649946b825584d94b08e718d54893084d9370152a08` |
| FEATURE 搜索头在线更新 helper（R1 已锁定） | `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\sources\local_runtime\position_only_search_head_step.m` | `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc` |
| PCF eta 离散 step（R1 已锁定） | `matlab/models/position_filter_realization_pcf_step_v3_5.m` | `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0` |

Round 1 输入锁已包含并绑定实际 FEATURE 搜索更新 helper、PCF eta step、runner、options、模型、normalizer、Plant/执行器源身份以及配对 raw 完整路径与 SHA。R2 `frozen_inputs.json` 和 preflight 必须继承并复验这些身份，特别检查 `position_only_search_head_step` 的 `which()` 实际路径和 SHA；不得把未调用的工作区 fallback helper 当成本候选实现。R2 builder/preflight 还必须逐场复核 12 个场景及 24 个 ON/B raw；数据仅原位只读，不复制到 R2、不改 mtime/内容。

场景固定为上述清单完整 12 行及其字典序：FIG8_3D、HELIX、SQUARE 各含 W09–W11、W12–W14、W15、W00–W08 的预选 VAL 场景。每场 20 s，计分 `[0,20)` 的 20,000 个 1-kHz Plant 样本；位置事件 100 Hz；Plant dt=0.001 s。保留终态 t=20 供完整性诊断但不计入 Q。固定 seed=2026102001，模型 optimizer steps=0。

## 筛查流程、预算与停止条件

执行者只能实现本任务书规定的隔离包，不得扩大范围。代码必须先通过主模型对完整任务书、静态实现、输入锁和 launcher 的复核。获批后先以 PROBE 运行字典序首场 `DL1018_VAL_T2_C00_W10`，实际核验 run_start、raw、状态、在线更新/eta 证据、运行时间和输出字节；PROBE 完整后由主模型另行决定是否运行剩余 11 场。PROBE 与 CONTINUE 不串联、不自动续跑。失败航次不可重试或覆盖。

预估本批最多 12 航次，资源上界按每场 30 秒计并留 25% 余量；CONTINUE 时长按 `max(锁定每场 30 秒上界, 首场 attempt_execution_and_raw_persistence 实测秒数) × 11 × 1.25` 估算，不会因快速 PROBE 低估剩余时间。`episode_runtime_seconds` 只计 `run_episode_dl1018` 调用，排除场景/输入加载及 MAT/status/report 写入；`attempt_execution_and_raw_persistence_seconds` 从写 `run_start.mat` 前开始，至写完 `raw_run.mat` 后结束，包含 episode 调用与这两份 MAT 写入，但排除场景/输入加载及后续 status/report 写入。二者都不等同于 `controller_call_time_s`。输出上限暂按 12×55 MB=660 MB。launch 前重新检查剩余空间至少 30 GB、MATLAB=0 个、GPU 作业=0 个，并识别而不终止现有进程；磁盘新增产物仍受本周期 80 GB 上限约束。WDDM GPU 预检保留普通 NVIDIA 进程原始行、`nvidia-smi -q -d PIDS` 原始输出、PID/类型/Win32 映像名映射和 GPU Compute engine 计数器。普通表与 PIDS 表的 PID+type 必须交叉一致；compute-query 中缺少普通表行的 PID，只能在 PIDS 表存在唯一 `C+G`/`G` 行、PID 能映射到 Win32 非疑似映像且该 PID 至少有一条 GPU engine 计数器记录时按 WDDM 图形上下文记录；若有逐 PID `engtype_Compute` 计数器，其值必须为零，普通 3D/Copy/Video 图形引擎计数不要求为零。`C+G` 表示该进程同时关联 Compute 与 Graphics context，并不表示当前有活动 kernel；只以 GPU engine 活动计数判断实际工作，任何活动全局或逐 PID `engtype_Compute` 计数都阻断。未知 PID/type、疑似 compute 映像、查询失败或非有限/越界计数都阻断；图形上下文数量及非 Compute 图形计数本身不阻断。该预检报告只记录资源状态，不授予运行权限。若当前资源条件、硬截止 `2026-10-24T17:01:00Z` 或预算不满足，不启动。仅用 PowerShell 7 (`pwsh`)；不打断正在运行的任何实验。

不安全、不完整、源/输入哈希不符、既有 attempt、时间/磁盘预算失败、PROBE 运行时不变量失败，均立即停止；保留所有实际生成文件，记录一次真实启动。不自动修复并重跑。不允许代码触碰 `runs` 中已有数据，R2 新航次只写本目录的 `runs/<scene>/attempt_01/` 和 `reports/`。

## 预登记指标、筛查门槛与失败解释

主指标仍为 0–20 s 三维位置 RMSE `Q`；辅报 X/Y/Z RMSE、Z 的 `[0,5)` 与 `[5,20)`、每方法峰值/p95、安全、饱和、控制调用耗时和 OFF 整场 wall runtime。逐场明确 OFF 对 PCF-on 和 B 的 Q 胜/平/负；汇总分别列 `W09_W11`、`W12_W14`、`W15`、`W00_W08`，另保留合并 `W09_W14` 指标用于筛查门槛。每场对 B/ON/OFF 报告 status、last_transition、finite、complete、安全停止原因、motor_saturated/generalized_clipped 比例，以及 `controller_call_time_s` 的 mean/p95/max；若锁定 raw 缺少该字段、长度错误或含非有限值，评分失败关闭。OFF 的 `episode_runtime_seconds` 只计 `run_episode_dl1018`；`attempt_execution_and_raw_persistence_seconds` 从 `run_start.mat` 写入前到 `raw_run.mat` 写入后，二者分别报告，不称为整场 wall-clock，也不与控制器调用耗时互换。未舍入原值用于判定；单场胜负容差为 `1e-12 m`。评分器必须核对 R2 候选 raw 的 SHA/size/mtime 读前读后一致，并复核冻结 ON/B raw 与两个重评分 CSV 的 SHA/size/mtime 读前读后未变；同时校验运行状态中的模型 MAT/绑定、normalizer 文件/数组、W0、场景输入、Plant/runtime 源身份以及 raw 数组完整性。ON/B/OFF 日志中的 `reference/position` 输入必须逐元素完全相等；这是参考输入身份检查，不是实际状态轨迹比较，也不使用 `1e-12 m` 容差。由于 PCF-off 是处理干预，候选状态轨迹预期可能与 PCF-on/B 分叉，禁止要求不同方法的实际状态逐点相等。`1e-12 m` 只用于同一 raw 重评分核对，以及任务书定义的 Q 胜负/不劣判断。

建议进入 72 场开发验证的 Round 2 筛查门槛必须同时满足：

1. 12/12 场 `STABLE`、20,000 transitions、完整且安全；模型/场景/源码身份正确，在线更新=true、PCF=false、W0/normalizer 身份一致，运行时 `eta=0`、`s_eff=clip(surface, ±[7,8,10])`，且同一锁定 FEATURE helper 实际执行 W 更新事件。
2. 六个 W09–W14 场的候选平均 Q 严格低于现有 PCF-on 候选，且不高于同六场 B 的平均 Q（均使用原始值和 `1e-12 m` 浮点判定容差）。
3. W09–W14 中至少 4/6 场的候选 Z RMSE 严格优于对应 PCF-on 候选，单场容差 `1e-12 m`。
4. W15 组三场候选平均 Q 不高于同场 B；W00–W08 组三场平均 Q 不高于同场 B，均允许最多 `1e-12 m` 数值容差。
5. 全 12 场宏平均 Q 严格低于同场 B 宏平均 Q；同时报告微小改善敏感性，分别列胜负数与改善幅度，不用胜率代替幅度。

任一项不通过：登记为“筛查未通过，不进入 72 场”，保留全部数据，不做参数调整，不读取 TEST。该 12 场联合门槛失败不能单独宣称证伪整个 H2。全通过也只向主模型申请进入 72 场开发验证；不代表开发门槛通过、不授权 TEST，也不能声称理论门槛完成。若通过后全 72 未达到计划中 62/72、严格更低宏平均 Q、高频和 W15 不劣于 B，则停止该候选方向，保留 TEST。

结果报告必须列全 12 行和四个分组，展示 B、PCF-on、PCF-off 原始配对数值、ΔQ/ΔZ、胜负与安全标记；不能只报告高频输场或仅给均值。禁止将时间窗口当独立样本，禁止宣称跨种子可靠性或实机泛化。

## 输出与后续审批

R2 代码、任务书、输入锁、预检、命令、资源/启动账本、run_start/raw/status、评分 CSV/JSON、静态和 MATLAB 离线 smoke 日志都放在 `experiments/paper14_v2_round2_pcf_screen/`。不得上传 MAT/raw/checkpoint/cache/fixture，不做批量暂存。

执行者交付后，主模型逐项审核任务书哈希、源码差异、输入锁、静态检查、MATLAB options smoke 与环境 preflight。只有审核通过才可发出一场 PROBE 命令；只有 PROBE 审核通过才决定 11 场 CONTINUE；只有 12 场结果过预登记门槛才单独决定是否开展 72 场开发验证。每次都由主模型独立复算分数并作继续/修复/复测/停止决定。

```powershell
# 仅供后续主模型审查后使用；本任务书此刻不授权启动：
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode PROBE -ParentReviewed

# 只有 PROBE 审核通过并另行授权，才可单独运行：
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode CONTINUE -ParentReviewed
```

## 主模型冻结审核记录

2026-10-22 复审修订 1：消除“候选与对照逐点轨迹数据误差≤1e-12 m”的歧义。不同闭环方法允许且预期产生不同轨迹；仅要求配对场景、输入/物理 payload、初值、时间基准、采样与统计身份相同，候选 raw 和复用对照 raw 各自内容哈希读前读后一致。1e-12 m 仅用于同一 raw 的重评分核验与任务书的指标比较，不能用于不同方法轨迹等同性。另加入 effective-options / runner contract 的离线兼容 gate；不兼容则不发 PROBE。

## 主模型冻结审核记录

2026-10-21 20:46 UTC：主模型复核 Round 1 实际锁定 runner 的 FEATURE+在线更新分支。PCF 开启使用 `clip(surface-eta_before)`，关闭使用 `clip(surface)`，两者传入已锁定的 `position_only_search_head_step`；PCF false 时 eta 停止递推。当前工作区中的 `position_stage1_update_head*.m` 不属于该分支。Round 1 lock 已绑定真实更新 helper，先前对 helper 漏锁的疑虑经复核撤回。审查决定：批准在隔离目录实施 runner、锁、静态/离线验证；不批准任何闭环航次。后续执行者不得自行扩大范围或启动。代码与输入锁完成后须由主模型重新审核，再决定是否仅启动首场 PROBE。

2026-10-22 复审修订 2：细化逐场评分字段与资源预检口径。ON/B/OFF 的 `reference/position` 输入逐元素完全相等；只作参考输入身份校验，不比较闭环状态轨迹。controller 调用耗时按 `controller_call_time_s` 报 mean/p95/max；OFF episode 与 attempt 持久化计时按定义分列，不称为整场 wall runtime。报告每种方法的 Q 胜/平/负、四个独立 band 组和合并高频 gate、峰值/p95、饱和/裁剪比例、安全标记与身份核验。controller 耗时缺失或数组不完整则拒绝评分。失败结论收窄为筛查未通过、不进入 72 场、不调参；不能据此声称 12 场联合门槛单独证伪 H2。WDDM GPU 审计只作资源预检，不是运行授权。


2026-10-22 复审修订 3：WDDM 资源审计增加只读 `nvidia-smi -q -d PIDS` 原始表、PID/type 与普通进程表交叉核对，以及 compute-query 缺少普通行时的 PIDS fallback；fallback 只有唯一匹配的允许类型、Win32 非疑似映像及存在且为零的逐 PID GPU engine counters 才可放行。`C+G` 是图形上下文类型，不单独证明活动内核；活动全局 Compute counter 仍失败关闭。离线 options smoke 报告改为版本化新文件，静态测试将其 frozen lock SHA、选项 builder SHA 和 FEATURE helper 路径/SHA 与当前锁绑定；旧报告以 stale 名称保存在本目录。CONTINUE 使用 `max(锁定每场 30 秒上界, PROBE 实测 run_episode 秒数) × 11 × 1.25` 估算剩余时间。报告分开记录 `episode_runtime_seconds` 与 `attempt_execution_and_raw_persistence_seconds` 并说明测量边界；二者均排除上游场景/输入加载，后者排除之后 status/report 写入。以上仅修订审计与资源估算，不改变唯一差异、场景、指标、门槛或运行授权。


2026-10-22 复审修订 4：preflight 拒绝非有限或超出 [0,100] 范围的 GPU engine 利用率读数；C+G 进程的 fallback 必须有完整逐 PID GPU engine 零值证据。评分器在直接读取 HDF5 计分数组后再次核验 OFF/B/ON raws 的 SHA、大小、mtime；每个场景组额外报告 OFF−ON 与 OFF−B 的 Z 均值差及 WIN/TIE/LOSS 数，合并高频筛查门槛不变。仅增强测量完整性和汇总可审计性，不改实验因素或通过标准。



2026-10-22 复审修订 5：按实际计时边界修正 CONTINUE 剩余时长估算，使用 `max(30 秒上界, PROBE 的 attempt_execution_and_raw_persistence_seconds) × 11 × 1.25`，而非只计 run_episode。纠正 WDDM 语义：NVIDIA `C+G` 表示 Compute 与 Graphics 两类 context，不代表当前 kernel 活跃；compute-query 的 PIDS fallback 要求 PID/类型唯一、映像已知且可信、存在逐 PID engine 记录，并确认没有活动 `engtype_Compute`。普通 3D/Copy/Video 图形引擎活动允许；任何全局或逐 PID Compute 活动仍阻断。静态审核要求与输入锁已同步，旧 smoke 将保留为 stale 历史证据并重新生成当前锁绑定版本。
