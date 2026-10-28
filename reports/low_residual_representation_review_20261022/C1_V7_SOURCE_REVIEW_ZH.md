# C1 v7 源码与资源门独立审核

审核范围：只读检查 v7 release、source lock、runner、options builder、offline smoke、preflight、资源澄清及已生成的 dryrun/smoke 记录。没有读取 MAT/raw，没有运行 preflight、probe、Plant、训练或 TEST。结论针对“是否可进入单独的三航次 PROBE 审批门”，不构成 Plant 执行授权。

## 冻结身份

| 项目 | SHA-256 |
|---|---|
| `C1_RELEASE_v7.json` | `94847c24de6cb6bd92a7017da55d0fd5f1180da67413911650f3cec9efb3b843` |
| `C1_SOURCE_LOCK_v2.json` | `02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5` |
| runner | `a66634426a327c1478900188ab89913230aa59896c17c74fd2c15876abad54a2` |
| options builder | `f7e62646141513e3144439054134aec45b7385a79ec117d9d4e407e2a652a575` |
| offline smoke | `7c7a9b4c11a513bd8a048dc8e2b833d43c09db5371913964047324b4778d7eb0` |
| preflight | `1d200947d47c678589836c267ce64253bcb52563953a2abe3e04cd23698ebcd7` |
| 资源与计时澄清 | `aa7fd3b7256a9c85f70705e6b6e3e149f692e6d26a5e30b40f45cc994122b78c` |
| v7 dryrun 记录 | `6a485474e00ee9ec798d43b2397a596f6bb9b775f367b283640a7114eae8b6a7` |
| v7 offline smoke 记录 | `5d26718ce9d5964487febf6a6c210828f9bd08df878a114f266468391079800c` |

release 中的路径与上述哈希均匹配。source lock v2 引用 v1 的哈希并新增资源/计时澄清；既有科学输入字段未改变。runner 与 smoke 使用 v2 lock、v7 release，并校验澄清文件哈希。options builder 未变，`c*=0.2802979648061464`、模型、场景表、12 场景、3+33/36 航次门、6 GiB 输出上限及 30 GB 余量门保持不变。

## v6 阻塞记录与 v7 处理

v6 release（SHA `975b5d13e8d7a25db4c96811ad96fafc6259f9e1facc51be1dfbcc4eac42f2c6`）及旧 source lock（SHA `f5dcef2143445ff80e9c3c3186a76098870d60f593ca7966ffe6f34cfd248b6b`）保持原样。v6 的旧 BLOCKED 记录仍在；它记录 ChatGPT.exe PID 43980（约 0.996 CPU 秒/墙钟秒）和 VALORANT-Win64-Shipping.exe PID 69504（约 3.985）触发资源门，且 `processes_stopped=false`。这条记录保留为当时的有效阻塞证据，没有被 v7 改写。

此前 v4 代码中的 `$Pid` 与 PowerShell 只读自动变量 `$PID` 大小写等价，可能导致进程枚举赋值失败。v7 使用 `$TaskProcessId`，并通过冻结哈希确认该修正已进入本版本；这与 v6 上述实际负载阻塞是两件事。

资源澄清允许仅已识别的 ChatGPT.exe 与 VALORANT-Win64-Shipping.exe 桌面负载参与固定步长 Q 筛查；MATLAB、活动研究 Python/GPU Compute 和其他未知重负载仍阻塞，不停止或抢占进程。它明确把这类筛查标为非隔离，不作为正式效率或实时性验收。

## v7 dryrun 证据

`C1_PREFLIGHT_DRYRUN_V7_PASS.json` 的状态是 `PASS_DRY_RUN`，绑定 v7 release 与 source lock。该次采样记录：

- MATLAB 进程数 0、其他重负载数 0；唯一被标记的允许桌面 CPU 负载是 VALORANT，约 4.987 CPU 秒/墙钟秒。
- GPU 总利用率采样为 19% 与 23%，只记录为系统利用率。NVIDIA 查询列出 25 个上下文记录；WDDM 枚举 337 个 GPU engine 计数，其中匹配 Compute 类型 0、活动 Compute 计数 0。若进程/显存详情是 N/A，结果依赖 WDDM Compute 计数；这些瞬时观测不等于对所有时间“GPU 空闲”或“没有 GPU 作业”的证明。
- 运行输出当前为 0；36 航次按 55 MB/航次并加 25% 余量预留 2.475 GB，低于 6 GiB 上限。可用空间约 167.46 GB，高于 30 GB 下限；试运行阶段时间预算按 1,350 秒估算。
- `timing_isolated=false` 且 `formal_timing_qualified=false`；桌面负载被记录，时间量不能用于正式效率或实时性结论。

runner 会把 preflight 文件 SHA、两项计时标志、计时标记和桌面负载记录写入 run_start、runIdentity、run_status 与阶段汇总，并在 probe 校验中核对身份。v7 release 仍标记 `plant_authorized=false`；dryrun 和 offline smoke 均未调用 Plant，也未访问 TEST。启动 runner 仍需要单独 PROBE approval 和新鲜的正式 preflight PASS，dryrun 记录不能代替这两项门。

## 结论

v7 的源码与资源门通过独立只读审核，可提交主审进入单独的三航次 PROBE 审批流程。这里的 PASS 仅表示固定步长筛查路径和相应资源记录门通过；不表示已经获准或执行 probe，也不构成正式计时、GPU 空闲或闭环性能结论。

## v7 启动门更正（后续形状诊断）

我此前的 v7 源码审核漏掉了 valid_scene 对 MATLAB 数组方向的错误假设。v7 门把参考向量与四臂数组按“分量 × 样本”形状检查，实际锁定 runtime 按样本行访问：s.reference.position(k,:)、velocity/acceleration 同理，yaw 使用 (k)；s.arms.command(k,:)、rho_true/rho_hat/rhoDot_true/rhoDot_hat(k,:)；环境风也按 s.environment_wind_I(k,:) 读取。固定步长脚本的 k 是统一时间行号，因此 canonical scene shape 为 20001×3 的环境风/位置/速度/加速度、20001×4 的五个 arm 字段、20001×1 的时间与三个 yaw 字段；initial_state 为 12×1。旧 v7 shape gate 与运行时访问契约不相容，故其启动失败应归为实现门错误，不能视为航次失败或闭环证据。

首次 v7 probe 在该 shape gate 处停止，未进入 Plant；主审记录为 0 markers、0 raw、0 实际航次。这个事实不改写前文“v7 dryrun 与资源门通过”的范围，也不授权旧 v7 重试。v7 release 的 plant_authorized=false 与单独 probe 授权门仍按原记录保留。

我另核只读诊断 experiments/position_prior_calibration_c1_20261022/reports/C1_PROBE_SCENE_GATE_DIAG_v7.json（SHA-256 EBE5B4E147B8856A6983FF97B59ACA69C62F5A617657C38C9C3479C701EAC568）：12 个唯一场景均有 14 个字段检查；字段签名只有一套，均为上述 canonical 方向与长度；所有字段 finite、场景身份及预期形状通过。每行的 raw SHA 与预期值一致，前后 raw SHA、字节数和 datenum 均不变。诊断绑定 source lock v2 SHA 02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5 与 v7 release SHA 94847c24de6cb6bd92a7017da55d0fd5f1180da67413911650f3cec9efb3b843，并标记 plant_called=false。该诊断校正了字段方向证据，但本身不替代尚待冻结的 v8 runner/preflight 审核。

## v8 形状修复复核（只读，未启动 probe）

v8 release SHA-256 为 82dcf11c4e5d8155b8f92e83671ae99eb6a2e876c690688af3fd118b5ded69b7；锁定 runner 为 ec70afd7aecb8f025c5cdf26ba40a7c9f3c9fb2caf5b9cf33a34fce4e8b69f07，preflight 为 fb1550e2b0c11543f902e0762f8e9ce2c132e6e89d8bd1834b22b29ab1670068。Release、runner、preflight、builder、smoke 与 source lock v2 全部与各自 SHA pin 匹配。

v7→v8 runner diff 的研究路径变化限于 valid_scene 维度判定改为诊断所见的 20001×3、20001×4、20001×1；静态查看未见对 scene 数组的转置或重排。其余差异为 release/preflight/approval/summary/runs 输出改用 v8 独立名字与 runs_v8，避免复用 v7 失败产物。builder、options smoke、C1 参数、场景条件、Plant 运行循环和 source lock v2 均未变。锁定 runtime 的 k 行访问与 12 场 shape/finite/identity/SHA 诊断一致。v8 checkcode 退出码为 0，记录 11 条 MATLAB 非致命 analyzer warning。

v8 当前没有新的 approval、preflight、probe summary 或 runs_v8 目录；release 明确 plant_authorized=false。故本次只读复核结论是：修复 shape gate 与输出隔离通过，可由主审继续单独审查/签发 probe 授权；本报告没有启动或授权 probe，也没有新增 Plant 运行。
