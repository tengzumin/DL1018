# ROOT 决策：放行高频姿态同状态 shadow v1

日期：2026-10-27（Asia/Shanghai）

## 决策

批准按 `HF_SAME_STATE_SHADOW_DIAGNOSTIC_TASKBOOK_v2_ZH.md` 实施只读离线诊断。只处理列出的 28 个 DEV/VAL 高频场景；不访问 TEST，不启动 MATLAB、Plant、闭环航次或训练，不改 production runner、模型、配置或历史 raw。所有新文件写入单独的 shadow 输出目录，原始 MAT 按路径读取且不复制，新增文件总量不超过 5 GiB。

放行前的输入身份已复核：任务书 SHA-256 `b48c9998ac7675b22ebe8e3e01b278d14f57ad2256520a4bcf068be58ba8a67d`；身份 CSV SHA-256 `71f3d159954198a066ef8cc00151e07a90ef4de92f216db6990a07da045c2c1a`；summary SHA-256 `32d27dc83b4e9ac79c9f2f847b6eb2825ea403ead8172330e418015223c73eb5`。56 对应 raw/status 的哈希、路径和所需 HDF5 字段通过；候选 raw audit 28/28 对上。C5 高频组为 6 条 lock reuse 与 22 条新 raw，逐场 status 仍按原值保留。

## 已关闭的 1968 计数疑点

C5 reuse lock 中的 `parent_screen_event_count=1968` 与 raw 姿态事件数并不矛盾。其来源是旧父审计报告的通用 `event_count` 字段，实为**位置** `stage1_position_event_inference_valid` 样本数：父审计脚本筛选索引 `np.arange(320, 19991, 10)`，并用 `len(ids)` 写入该字段（`check_c5_raw_parent.py` 第 100–101、190 行；脚本 SHA-256 `59cb79f91d49e3d5ca3c268007038a66a3692f75a2cd354535f13cb8ad39fdcb`）。因此不能把它解释为姿态 RBF 更新计数。

ROOT 对 6 个 reuse raw 逐一读取了 per-step 字段：`attitude_event_flag=1999`、`rbf_update_flag=1999`、`rbf_event_count=1999`、`rbf_update_dt>0` 的样本数为 1999；姿态事件与 RBF 更新标记不一致数为 0。旧父审计计数的语义已经解释，该 STOP 门关闭。原 `run_status` 仍保持 `RUN_COMPLETE_RAW_PENDING_AUDIT`；本次诊断不会改变 audit 等级。

## 执行时必须 fail closed

1. 先对一个 C5 reuse 场和一个 C5 新 raw 场做端到端离线 parity preflight；成功后再处理其余场景，不重复已完成场景。
2. 每场逐样本检查时间、状态、事件、滤波重建和有限值；filter 误差限为 attitude `1e-10 rad`、rate `1e-8 rad/s`。
3. 先通过 candidate 原 GRU native replay 和 C5 原 RBF native replay；RBF 输出误差限 `<1e-9 rad/s²`、扭矩 `<1e-10 N·m`。事件数、time-index、memory 链、输出先于更新或 torque closure 任一项不符，该场只报告 FEASIBILITY_ONLY，不作模型间比较；不猜缺失值、不自动重试。
4. 运行前重验 GRU 模型、固定 `J0`、DSSM14、C5 有效配置和 RBF initial-weight override。C5 source 默认 `W=0`，但若 locked opts 中存在或无法确认 `rbf_attitude_initial_weight`，停止该场。
5. 不把 shadow 动作差换算为闭环 SO(3) 收益，不对 C5 raw pending-audit 场景晋级，不触碰 TEST。

完成诊断后，Luna 应交回入口源码、精确命令、输入/源文件 SHA、parity 结果、全场动作表和资源清单。ROOT 将独立复算并据结果编写下一项单因素姿态修复任务书；在此之前不改姿态控制律、不扩跑闭环。
