# Scene payload launcher 空进程列表修复与一次重试

日期：2026-10-25。root 审批。本补充条款仅补充 `SCENE_PAYLOAD_TASKBOOK_v1_ZH.md`，不改变其无 Plant 范围，不授权 runner、闭环航次、训练或 TEST。

第一次 PowerShell 7 launcher 调用退出码为 1，发生在创建 runs 目录和启动 MATLAB 之前。`ActiveMatlabProcesses` 的空数组经 PowerShell pipeline 展开后成为 `$null`，StrictMode 在 `$preexisting.Count` 处报错。root 用独立最小复现得到同样错误，并确认 `@(EmptyProcessList)` 的 Count 为 0；现场 MATLAB/Octave 进程数为 0，runs 目录不存在。已消耗：launcher 调用 1 次、MATLAB 调用 0 次、Plant 航次 0 次、训练 0 次。

允许的唯一代码修正：将 launcher 初始和循环刷新两处 `$preexisting = ActiveMatlabProcesses` 改为 `$preexisting = @(ActiveMatlabProcesses)`。不得改 MATLAB probe、39 个隔离源、场景输入、配置或模型，不得扩展修复。

修复后先用 PowerShell 7 Parser 及 StrictMode 下的空列表/实际只读进程检查验证；记录新 launcher SHA 与本补充条款 SHA。由 root 审查后允许一次 cause-specific launcher 重试，仍最多产生原任务书允许的一次 MATLAB payload 生成。发现既有进程、command/receipt 或 runs 产物时先跟踪既有状态，不重复启动。再次失败保留证据并停，禁止执行者自主重试。

此次修复不改变原任务书的 `NOT_FROZEN`、`closed_loop_runs_authorized=false`、`executed=false`，也不构成六航次放行。
