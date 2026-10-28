# ROOT 独立复核：高频姿态同状态 shadow

日期：2026-10-27

## 审核结论

离线诊断完成，28/28 场通过。独立复算确认结果表与原始压缩 CSV 的 12 组动作汇总逐项相同，样本数、宿主轨迹和事件时序完整。该诊断只说明同一条已执行状态轨迹上 GRU 姿态头与 C5 RBF 的条件动作差异；不构成闭环反事实，也不能据此判定哪一个动作更优。

## 核验结果

- 28 个 W09–W14 DEV/VAL 场景；候选与 C5 两种宿主轨迹各 28 条。每条轨迹重放 1,999 个 100 Hz 姿态事件，共 111,944 行动作记录。
- 392 项逐场核验全部通过（14 项/场）。GRU native replay 的最大输出差为 `1.41e-13 rad/s²`、`4.03e-16 N·m`；C5 RBF native replay 最大差为 `4.14e-13 rad/s²`、`1.35e-15 N·m`。时间、事件间隔、输入、更新、保持输出与固定 J0 力矩映射闭合。
- GRU 与 RBF 的三轴力矩差向量 RMS：候选轨迹上 `5.591 mN·m`，C5 轨迹上 `5.232 mN·m`。差异主要在 roll/pitch；它证明输出不同，不证明差异有益或有害。
- 每个 C5 raw 只直接记录了前 8/1,999 个完整权重矩阵。剩余权重由锁定的零初值递推重建；全部事件的输出、范数、应用力矩和更新时序均与逐步 raw 记录核验。未把重建权重描述成直接观测。
- 结果文件显示 28 条候选 audit 均 PASS；C5 有 6 条已有 raw audit PASS，另 22 条原 `run_status` 仍为 `RUN_COMPLETE_RAW_PENDING_AUDIT`。本次不提升原状态。
- 输出约 25.4 MB；未复制 raw，没有启动 Plant、MATLAB 或训练，也未读 TEST。

## 与既有闭环结果的合并判断

既有 72 场开发筛查中，高频 W09–W14 的 GRU task SO(3) 宏平均为 `58.854 mrad`，C5 为 `58.795 mrad`，候选略差 `0.058 mrad`；GRU inner SO(3) 为 `13.817 mrad`，优于 C5 的 `15.688 mrad`。对 B，GRU task SO(3) 高 `4.038 mrad`，而 inner SO(3) 低 `1.689 mrad`。这是开发筛查，不是独立测试。

结合此前路径分解，当前证据更支持优先检查 task attitude → command target → filtered reference 的上游链路及其时间/坐标语义。它仍是待验证的定位，不是已经证明的单一根因。shadow 没有发现 native replay、事件时序或力矩映射错误；高频性能差距不能用本次的动作差异归因。

## ROOT 下一步

先对现存 raw 和实际代码审计 command target 与滤波参考的生成：坐标系、角度 wrap、目标时间戳、因果延迟、限幅顺序及 candidate/B/C5 的同条件差异。只依据审计证据写一个单因素修复任务书，再审核小规模闭环筛查。不得把 Plant 真值或惯量重建引入部署输入；TEST 继续封存；不重跑 B/C5 基线。

## 可复算入口

- 诊断脚本：`hf_same_state_shadow_diagnostic_v1.py`
- 完整动作表：`SAME_STATE_ACTIONS_v1.csv.gz`
- 机器结果：`RESULT_v1.json`
- 独立复算：读取上述压缩 CSV，对 12 项 `n/signed_mean/rmse/p95_abs/max_abs` 逐项重新计算，最大绝对差为 0。
