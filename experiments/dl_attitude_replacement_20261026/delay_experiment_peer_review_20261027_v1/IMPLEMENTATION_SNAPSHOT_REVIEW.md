# 单事件延迟实现快照复核

复核时间：2026-10-27。只读检查 `mlp15_one_event_delay_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m` 指定的初始化、事件分支、命令/日志范围。未启动 MATLAB/Plant，未修改实施文件。检查时该 runner 文件 SHA256 为 `D36696AB6C4D345D70067782AB50990CDB3740CAF61550FCB061706C3BF4F658`；这是快照标识，不代表包装后交付状态。

## 结论

在所审代码中未发现延迟时序阻断或控制超范围：缓存的是 step helper 返回的完整 `estimateTorque_Nm`；事件 k 先应用先前缓存，再把当前生成量缓存到下一事件；初始缓存为零；非事件样本从 held torque 赋值；历史测量仍使用已有的逐样本 `requested` 力矩历史，并会自然反映已实际应用的延迟补偿。控制器仍把该补偿通过原 `attitude_bs_step` 加入力矩命令；未见另乘当前 β、重做 Dmax 或改变 Plant/执行器路径。

## 可核对路径

- **初始化及首事件：** 第 1080–1085 行把 held torque 和 previous generated torque 初始化为零，来源 sample 为 0、time 为 NaN。第 2452 行每个样本先令 `dT=heldMlp15Torque`；事件首次运行时第 2478–2482 行从零初始化的 prior cache 取应用量，并记录 source sample/time。故第一事件补偿为零。
- **事件缓存顺序及完整力矩：** 第 2460–2467 行把当前 β、Dmax 和时刻/样本交给原 step；第 2476–2490 行调用 step 后，先选 prior torque 作为 applied，再从 `mlpOut.estimateTorque_Nm` 取当前 generated torque并缓存。runner 中没有对应用 torque 再乘 β 或再裁剪。第 2491–2494 行按实际生成源时间计算事件间 delay age。
- **非事件保持：** 第 2452 行位于事件条件之前，每个 Plant 样本先恢复 held torque；只有第 2453 行之后的 attitude event 分支会更新 held cache。因此事件间沿用上一次已应用力矩。全步日志第 2877–2885 行保存 applied torque、来源、逐样本年龄和首事件零标志。
- **残差历史及控制路径：** 第 2471–2474 行把 `requested(previousIndex:k-1,2:4)` 作为既有 step 的 torque history，并和 `omega_history` 区间 `[previousIndex:k]` 对齐；第 2754–2757 行仍由原 `attitude_bs_step(...,dT,P)` 生成总 moment 和 command，第 2846 行逐样本写入 `requested(k,:)=command.'`。所以 residual history 的来源/区间构造未被另造；其数值将按实际延迟控制命令变化，这是实验干预应有的结果。日志导出同时保留 requested 与 generated/applied/source fields（第 2948–2964 行）。
- **范围：** 延迟分支只在 `mlpCandidate`（第 2451 行）更新。该 runner 所见数值 step 调用仍为 `mlp15_attitude_step_v1('step',...)`；任务负责人报告其数值 step SHA 与 v3 相同。仅凭本次 runner 快照不据此判断新 raw、独立 auditor 或正式交付已通过。

## 快速验收建议

实现逻辑没有需要在本文件提出的阻断修复。无 Plant 合成/auditor 验收时，仍应按每个 Plant 样本明确断言：非事件 applied 与上一样本完全相等；每个事件的 applied/source 精确对应前一事件 generated；首事件为零；不等事件间隔的 source 时间与年龄相符；10 ms residual 重放使用 `requested` 的已记录实际命令区间，而不是 generated cache。日志中的 `source_event_index` 实际记录 MATLAB 样本索引 `k`（1-based），审计脚本应按样本索引解释，并用 source time 交叉核对。

该静态复核不等于无 Plant 验收、raw audit、闭环安全/性能审核或航次放行。
