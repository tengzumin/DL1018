# 首轮冻结 W0 筛查：主模型代码与任务书审查

审查日期：2026-10-22 03:41（Asia/Shanghai）。审查人：当前主模型。

**决定：批准仅运行首个 VAL 场景 PROBE，用于量测耗时、输出大小和运行完整性。** 该批准不覆盖其余 11 场、72 场扩展、训练或 TEST；probe 后必须由主模型检查真实 raw、run_start、状态、安全和资源记录，再单独决定 CONTINUE。

审查对象是 [冻结任务书](TASKBOOK_ZH.md)、[隔离运行入口](run_frozen_w0_screen.m)、唯一差异构造器、PS7 launcher/preflight、只读场景身份核验器及未来评分器。完整执行契约与文件 SHA 见任务书和 frozen_inputs.json。

审查发现并在启动前补齐了两项身份检查：MATLAB runner 现于 init_dl1018 前绑定 preflight 所引用的 frozen_inputs SHA，并重新计算模型、normalizer、场景/配对 raw 清单、评分器、代码和任务书的全部锁定 SHA；B scene raw 在 load 前后再次检查 size、mtime 和 SHA。run_start 和 probe summary 均记录 frozen_inputs SHA。独立测试没有发现其余会改变场景、计分或单因素配置的代码错误。

解释边界已写入冻结任务书：实际开关 update_enabled=false 不仅冻结 W，也会从 PCF 协调输出路径切至直接冻结 Head 输出。因此本轮只检验整个“自适应 Head + PCF 输出协调耦合分支”，任何 12 场结果都不能单独证明在线 W 更新有害或有益；若通过，下一轮先设计能分别识别 PCF 输出协调与 W 更新的单因素对照。

验证结果：PowerShell 7 静态测试、PowerShell AST、Python AST、24 个 raw 的只读 scene payload verifier 均通过；12/12 VAL 配对的14个物理字段在20,001个样本上精确相等。无标记 preflight 有77项 SHA 核验、verifier exit 0、MATLAB进程0、其他 Python 进程0、10个已分类 SolidWorks MCP CAD 进程、C盘可用约168.5 GB；其唯一 BLOCKED 原因为审批前缺少 ParentReviewed 标记。MATLAB离线配置 smoke 构造了预期 OFF options，确认 FEATURE Head、PCF仍启用和W0/normalizer身份；未调用 run_episode、Plant、launcher或创建航次。Code Analyzer报告4条建议级信息，无语法错误。

本审查绑定：

- runner SHA256：eae60a18445f807179f15063691905303edf6d8bbd87512ae2b092e7f03f4694
- taskbook SHA256：547dce3db84c6a85c6c8bf8688425922262071e0071d670ad65d2d5633ed13ad
- frozen_inputs SHA256：eb4e503e1d33bff1b983cead3fd535e4af02c7d15f0d9d77a4c3cae13c3b99ce
- 审批前 preflight：BLOCKED；marker=False；errors=A fresh parent-review marker is required for every preflight mode.

获批命令（由本审查决定执行，限单场 PROBE）：

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\launch_round1.ps1" -Mode PROBE -ParentReviewed
```

不得把 CONTINUE 与 PROBE 合并或自动调用。独立 TEST48 继续封存。

## 修复后复审（2026-10-22）

首次 PROBE 在创建 attempt/调用 Plant 前因 runner 读取不存在的 `split` 列退出；故障及零 Plant/航次记录已写入冻结任务书。修复将 MATLAB 入口改为校验真实 CSV 的 `task,band,scene_id` 表头、冻结12个 ID 顺序与 VAL 前缀，并增加静态回归断言。

主模型独立核验：PS7 静态测试和 parser、Python AST、24个已锁定 raw 的只读 payload verifier、MATLAB `readtable` 字段/顺序 smoke 全部通过；12/12 场14个字段和20,001点完全一致；无 `runs` 输出、无 MATLAB 进程、Plant calls=0。无标记 preflight 为预期 BLOCKED，唯一错误是缺少父模型审查标记；身份锁、raw/scene核验均通过。10个 Python 进程均分类为 SolidWorks MCP CAD；C盘可用约168.23 GB。

**决定：批准只重启首场 `DL1018_VAL_T2_C00_W10` 一次 PROBE。** 不授权其余11场、CONTINUE、训练或 TEST；完成后重新检查真实产物，CONTINUE 必须另行决策。此启动失败不产生任何科学结果。

修复版身份：
- runner SHA256：91c79be3cb96a83601e6c9af27a09115b706b573abfad31d54f9ccc6acc6226e
- static_test SHA256：9f3fa40c6394fdf61e56fb4faf018296988ef90ffffd8bdba87253409fc33c69
- taskbook SHA256：18b25e55a18fca540d9bf760748f80993eb4f1ae3eaba5ee309bf5d160907832
- frozen_inputs SHA256：baae8fe1e5cb3afc47a92ee12cf525fd93cd597441a4649449c762cf95c80a38

## 第二次启动故障与暂停决定（2026-10-22 03:52 +08:00）

修复场景表字段后的单场 PROBE 已通过带审查标记的 launcher preflight（MATLAB进程0、C盘可用168,223,555,584 bytes），但 MATLAB 随后在 `run_frozen_w0_screen.m` 的 `init_dl1018()` 调用处退出：`matlab/runtime/init_dl1018.m` 未加入 path。主模型核对源码确认 runner 先 `restoredefaultpath`、随后调用 init，实际 runtimeDir 的 `addpath` 晚于该调用。此为第二个入口启动故障，与 scene CSV 字段问题不同。

启动在创建 `runs/<scene>/attempt_01` 前退出；`runs`/attempt 不存在，Plant calls=0、transitions=0、TEST reads=0，无科学航次结果。单次 PROBE 启动授权已消耗；目前不再有启动授权。已把最小 path 顺序修复交给 Luna xhigh 实施者，范围限当前隔离包；主模型待其完成后独立审核，届时再决定是否批准新的单场启动。

## 第二次入口修复复审与单场再次授权（2026-10-22）

主模型独立复核 runner 现在从锁定 `runtimeFiles` 查找 `init_dl1018.m`，检查后前置加入 runtimeDir，再执行初始化；静态测试锁定此顺序。PS7 static/parser、Python AST、无标记 preflight 77项 SHA（0失败）、12/12 payload verifier 均通过；MATLAB 离线 path/init smoke 输出 `MATLAB_INIT_PATH_PASS`，未调用闭环或 Plant。Code Analyzer 仅报4条建议级信息，无语法错误。无 MATLAB 进程、无 `runs` 输出，Plant/transition/TEST均为0，磁盘空间高于下限。

**决定：批准同一首场 `DL1018_VAL_T2_C00_W10` 再启动一次 PROBE。** 不含其余11场、CONTINUE、训练、调参或 TEST。若失败前已创建任何 attempt，保留并停止；若成功完成，主模型审查原始产物和资源估算后另行决定是否 CONTINUE。

修复版身份：
- runner SHA256：7bddee18ced23d75852134d58ec01aeff5f86ca9b16188930e45410554879e25
- static_test SHA256：9fd79f41c4392d4bb41fc4ae8308496ceea7a7f01c0d6ade68ed0c8ce51c0017
- taskbook SHA256：d613d14faec40989a3dedf96c9475cd21f0058b4698c806db80725c5077c6241
- frozen_inputs SHA256：edb41b9f75810bec0b512611bc0fa55901954ef8ba7c2fc678c8d86c358a6c8c

## 第三次启动故障及当前无授权状态（2026-10-22 04:02 +08:00）

修复 init 搜索路径后，单场 PROBE 再次通过 preflight 并完成初始化，但在 `verify_runtime_chain` 的 `run_dl1018_closed_loop` active-path assertion 处退出。主模型核对冻结锁发现：前五个核心 runner/helper 来自外部 reference 的 `sources/local_runtime`，而 `init_dl1018.m` 来自 DL1018 本地 `matlab/runtime`。修复把 `runtimeDir` 变量指向 init 目录，并移除了 init 后对锁定主 runtime 目录的加入，导致 active path 与冻结 source path 不一致。

本次在创建 `runs/<scene>/attempt_01` 前退出，没有 `runs`、attempt、run_start/raw/status 或航次输出；Plant calls=0、transitions=0、TEST files read=0。单场启动授权已消耗；当前没有后续启动授权。Luna xhigh 正在隔离修改 runner/static/taskbook/lock，区分 `initRuntimeDir` 和锁定主源码目录，恢复锁定目录优先级并新增静态回归断言。修复完成后仍须主模型复审。

## 锁定源码路径修复复审（2026-10-22）

核实第三次失败源于 init 目录与 locked runtime 目录实际不同。修复版入口现在分开 `initRuntimeDir`/`lockedRuntimeDir`，init后将锁定主源码目录重新置于 path 前部，并 clear/rehash 后执行源 SHA 与 `which` 路径断言。主模型独立验证：PS7 static/parser、Python AST、no-marker preflight 77/77 SHA、scene verifier 12/12通过；MATLAB离线 init 和锁定 runner/helper 路径 smoke 通过；Code Analyzer仅4条建议级信息，无语法错误。没有 runs/Plant/transitions/TEST产物。

**决定：批准同一首场 `DL1018_VAL_T2_C00_W10` 再执行一次 PROBE。** 这是新的一次性审查授权，只包括该 scene。若入口再次失败或 attempt 不完整/不安全，保留记录并停止、不重跑；只有完整安全完成后才由主模型审核 raw/run_start/status 和资源估算，决定是否 CONTINUE。

修复版身份：
- runner SHA256：63bfce8ab739a4171874890907405ae00ef3ab756f3781a84fb15f03900af6e8
- static_test SHA256：39c953988b10735c7bd38850671f57697ecba368fe213016a49c274cb860a4b9
- taskbook SHA256：7dd57f46b8c73039a1d22771aaf8ea5005fd87f78c3e595461b0751b3670767d
- frozen_inputs SHA256：e128c527cddcb81a42db9380775534b34d771e933e4bdaef7688ec78904cf1b6
