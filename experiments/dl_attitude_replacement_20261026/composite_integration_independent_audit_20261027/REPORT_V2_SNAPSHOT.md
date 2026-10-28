# mlp15_composite_dev_v2 独立只读审核（快照）

审核日期：2026-10-27。审核期间 v2 文件仍在变化；以下反映本次最后复读到的源码快照，不视为最终交付审查。仅用 PowerShell 读取源码、JSON 和文件 SHA；未启动 MATLAB、Plant、训练或 TEST，也未重建惯量。

## 当前结论

| 项目 | 快照结论 |
|---|---|
| DEV72 tracking 接线 | **已接入源码。** 事件块传 `ai0.surface`、`ai0.euler_rate_map` 和实际相邻 head 事件间隔，并写入 trace。 |
| 真实 C5 cfg / 固定 J0 | **driver 路径正确，数值捕获待完成。** `LOCKED_CFG.json` 已存在，但 `capture_status=PENDING_REAL_PREPARED_CFG`，目前只有来源字段，没有实际 cfg 数值；driver 会用 `prepared.cfg` 检查 `[Inf,Inf,6]`、J0、零 `inertia_dot_for_bs` 和 fixed mode。 |
| 模型绑定 | **初次快照问题已修复。** 最新 driver 从 release 指定的 full72 权重重新构造 candidate options 并重建 identity；hash 对得上 release 记录中的 full72 模型。 |
| 预算顺序 | 新唯一 driver 与 DEV72 loop 都检查 composite release；driver 在创建 marker 前检查。当前 v2 根级 `RELEASE.json` 已存在，但状态为 `PREPARED_ROOT_REVIEW_REQUIRED`、授权调用数为 0、场景列表为空，因此没有授权航次。 |
| raw audit | **v2 审计脚本已落地。** `audits/audit_composite_dev_raw.m` 从 DEV raw measurements 重建 surface/map，并核对 top-level trace 与 step 输入；目前没有真实 raw，未运行这项审核。 |
| 交付状态 | v2 顶层 `RELEASE.json`、manifest、source lock/diff 及两份 audit 脚本已存在。尚缺真实 cfg 数值捕获和生成后的 `audits/NO_PLANT_CHECK_v2.json`；release 仍是 `PREPARED_ROOT_REVIEW_REQUIRED`、授权/已用航次 0、场景空。 |

## 已确认的正向修复

### 1. DEV72 tracking 字段已接通

`candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:2445-2461` 将当前 BS 的 `ai0.surface`、`ai0.euler_rate_map`、样本索引和时间传入 composite step。首个 head 事件的 `actual_event_dt` 初始化为 0；后续以 `t(k)-mlp15Memory.previous_time_s` 更新。trace 在 `:2464-2479` 保存 `causal_head`、tracking surface/map/dt 和更新前后权重。

`mlp15_attitude_step_v1.m:65-80` 会检查这些输入，并核对事件间隔；`LUNA` fixture/无 Plant 记录不能代替 DEV72 闭环验证，但源码接口现在是连上的。

### 2. 最新 outer driver 使用真实 `prepared.cfg`，并重绑 full72 模型

`candidate_runner_work/matlab/runtime/prepare_mlp15_dev72_no_plant.m:76-83` 从 receipt 指定的 C5 snapshot 读 `cfg/W0`，`prepared` 在 `:106-116` 返回 `cfg/model/identity`。新 `run_composite_dev_attempt.m:38` 使用该 preparer 的真实 payload；`:57-66` 将 `prepared.cfg` 与锁定限幅 `[Inf;Inf;6]`、K1、dmax、beta 对照，`:67-73` 构造 fixed `Pfixed` 并检查 `inertia==J0`、`inertia_dot_for_bs==zeros(3)`、fixed mode。

审核期间曾看到 driver 直接断言 preparer 的旧模型 SHA 与 release 一致。最后复读时已改为 `:39-50` 从 `release.model_path` 加载 full72 MLP、重建 options/identity，再检查共同 C5 position identity。静态 SHA 核对为：`mlp15_formal_v1/run_v1` 权重 `07A115318B946852B844A9BFE7A805C2B9AC0432E4BD3489A586D3C378B1161A`；full72 权重 `67A6564148BA8C1988D7457C04A5D3271516FF4010DA18E61E29FD7DA13BE46B`。最新 driver 使用后者；旧 preparer 仍先载前者，但这份旧 options 随后被 outer driver 覆盖。

### 3. 新预算检查在 marker 前，DEV loop 也有独立 guard

`run_composite_dev_attempt.m:4-16` 先要求 v2 release 存在、状态为 `RELEASED`、预算大于零且场景在授权列表中，再校验输入。它在 `:23-36` 检查重复场景和预算，在 `:38-73` 完成真实 cfg、fixed J0、which-path 和场景绑定后才创建 attempt 目录与 marker。

实际 `run_mlp15_dev72_closed_loop.m:15-32` 另行读取 v2 `RELEASE.json`、检查状态/预算/场景，并要求已绑定当前 scene 的 marker，随后才继续 loop 初始化。因此新 driver 的 release/授权预算检查位于 marker/Plant 之前，loop 的 release/授权预算检查位于 Plant 之前。当前根级 `RELEASE.json` 已存在，但其状态不是 `RELEASED` 且 `authorized_Plant_calls=0`，所以新 driver 会在执行 Plant 前 fail-closed；旧快照中“release 文件不存在”的说法已过时。

最新 driver 的 `verify_release_inputs` 在 `run_composite_dev_attempt.m:141-163` 不只检查 `SOURCE_LOCK_v2.json` 本身的 SHA，还校验 lock root 并逐个核对 `lock.files` 中源码 SHA；这一点在本次审核中已确认修复。

## 尚需修复或补齐

### 1. 顶层准备文件已生成；cfg capture 与 no-Plant 检查仍 pending

本次 `Get-Item` 复核确认 v2 根级 `RELEASE.json`、`LOCKED_CFG.json`、`MANIFEST.json`、`PREDICTION_ONLY_BASELINE_REPORT.json`、`SOURCE_LOCK_v2.json`、`SOURCE_DIFF_v2.json`，以及 `audits/audit_composite_dev_raw.m`、`audits/audit_composite_dev_no_plant.m` 均已存在。此前报告将它们列为缺失，属于过时快照结论，现予更正。

真正未完成的是 `LOCKED_CFG.json:3` 的 `capture_status=PENDING_REAL_PREPARED_CFG`（目前文件只有 schema、状态和 source），以及 `RELEASE.json:13,20` 中 `locked_cfg_sha256` 与 `no_plant_check_sha256` 仍为 `PENDING_REAL_PREPARED_CFG`。`audits/NO_PLANT_CHECK_v2.json` 尚未生成。release 当前保持 `PREPARED_ROOT_REVIEW_REQUIRED`、`authorized_Plant_calls=0`、`Plant_calls=0`、`authorized_scenes=[]`，因此新 driver 仍应拒绝调用。

**最小修复：** 只需从真实 `prepared.cfg` 完成 LOCKED_CFG 数值捕获、执行允许的无 Plant 检查并生成 `NO_PLANT_CHECK_v2.json`，再刷新对应 SHA；root review 前保持零航次与空授权场景。
### 2. 新 raw audit 已对齐 v2 trace；等待真实 raw

`candidate_runner_work/matlab/core/attitude_bs_step.m:14-24,46,49` 给出 `surface=z2=etaRateDesired+K1.*e-T*omega` 和 Euler map `T`。新 `audits/audit_composite_dev_raw.m:54-68` 从实际 state 与记录的 `filtered_attitude_reference/rate` 重建相同 surface/map，并核对 trace 顶层 tracking 字段与 `causal_head` 输入；`:91-92` 检查事件 dt 与相邻实际 head 事件时间差。它现在读取 v2 `RELEASE.json`/manifest/source lock，并核对 `runIdentity.mlp15_model_sha256`（`:6-29`）。脚本与 DEV trace 的数据契约已对齐，但当前没有 composite raw，故尚无实测重放结论。

`audits/audit_composite_dev_no_plant.m` 也已落地；当前阻断是 `LOCKED_CFG` 仍 pending，且对应 `NO_PLANT_CHECK_v2.json` 尚未生成。

## 审核边界

该报告记录的是 v2 写入过程中的源码快照。代码在复读期间更新过；根级 release、cfg/source-lock、manifest 与 v2 raw audit 均已出现，先前的缺失结论已更正。当前仅 cfg capture 与 NO_PLANT_CHECK 输出待完成；release 仍零航次。未调用任何 driver、MATLAB 或 Plant，不能宣称实际 DEV72 航次已经执行或通过。




