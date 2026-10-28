# CM18 SCREEN4 same-state replay source handoff

状态：源码已冻结，等待 ROOT 审核后执行固定 SCREEN4。此交接只记录静态源码准备；没有调用 `check_cm18_replay_v1`，没有读 SCREEN4 缓存数值，没有读取 H5 数值数组，没有运行 Plant、状态积分、episode、optimizer 或训练，也没有访问 TEST/SCREEN12。

新增入口：`experiments/attitude_cm18_a1_20261024/check_cm18_replay_v1.m`，SHA256 `751B28041DF3111D99389EBE4A61974BC0E3F6062ADB442427C484F4FBFF7739`，大小 43,699 bytes。入口签名固定为 `check_cm18_replay_v1(modelJsonPath, expectedModelSha, outputDir)`。

实现先核验 INPUT_MANIFEST、SCREEN4 manifest、SCREEN4四场 raw/run_start/cache 文件哈希、缓存输入身份与固定cfg；H5仅校验文件身份，不读其数值。它同时核验物理依赖、engine/forward/allocator源码身份，以及实际 ROOT release 的四个源文件身份和部署 JSON 中 `source_files` 字典身份。部署 JSON 路径及期望 SHA 固定为 `experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json` / `ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae`；ALL816 manifest 身份从部署 JSON/release交叉核验，SCREEN4 manifest另按固定 SHA `b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c`核验。

逐事件重构18维输入并与封存 cache 比对；alphaBS 由 `attitude_bs_step` 重建，并以 raw 中的 tauNom 反算交叉检查；`z` 每场景从零开始，只累计当前行之前的命令；`a` 只用此前完成的十条请求力矩。先重建旧请求，经真实 allocator 与电机时间常数公式复算 setpoint、actual motor 和 realized wrench。只要特征或旧动作闭合失败，就不解释新动作。通过后才在原始同一状态、同一推力/几何/风上按 frozen clip-beta-J0 规则构造新请求，并重算分配、执行器响应和瞬时 omegaDot；不推进状态。报告保存完整逐事件记录及按场景/phase/axis 的 label、E、clip、motor saturation 汇总，要求输出目录为 runtime_preparation_v1 下不存在的新直接子目录，输出总大小不超过100 MiB。

该入口是独立公式参考，不证明新 engine 的实际执行。通过后仍需对真实首次运行日志逐事件核验。

## 静态检查

实际使用 MATLAB R2025b 执行：

```powershell
matlab -batch "issues=checkcode('experiments/attitude_cm18_a1_20261024/check_cm18_replay_v1.m','-id'); for k=1:numel(issues), fprintf('%d %s %s\n',issues(k).line,issues(k).id,issues(k).message); end"
```

实际进程 exit code：`0`。MATLAB 返回 27 条 Code Analyzer advisory；没有 MATLAB 解析错误。该命令只静态检查源码，未调用入口。另用 PowerShell `Get-FileHash -Algorithm SHA256` 取得上述源码哈希，并用只读文本搜索确认入口源码没有 `vehicle_derivative(...)`、`rk4(...)` 或 engine 调用表达式。

## ROOT 审核后可执行的命令

以下仅为待执行命令模板；本次没有运行，也没有生成 replay receipt。需在仓库根目录并确认输出目录不存在后，由 ROOT 审核/执行：

```powershell
matlab -batch "addpath('experiments/attitude_cm18_a1_20261024'); summary=check_cm18_replay_v1('experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json','ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae','reports/attitude_cm18_a1_20261024/runtime_preparation_v1/screen4_same_state_replay_v1'); disp(summary.status)"
```
