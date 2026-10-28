# 隔离 runner 三场配对筛查任务书草案 v1

日期：2026-10-25。状态：待审核。本草案仅规划接入；当前不授权实现、MATLAB/Plant 调用或闭环航次，也不涉及训练。沿用 [DEV3 任务书 v1](PHYS_ATT_OBSERVER_DEV3_TASKBOOK_v1_ZH.md) 与 [v1.1 补充条款](PHYS_ATT_OBSERVER_DEV3_TASKBOOK_ADDENDUM_v1.1_ZH.md) 的方程、门槛和分级放行；本轮只覆盖下列三个 DEV 场景，不读或使用 TEST。

## 最小接线与因果边界

1. 在本目录新建隔离 runner 树，镜像 `matlab/runtime`、`matlab/core`、`matlab/scenes` 中实际依赖的 `.m` 源码及三场所需场景规格；将运行入口复制并改为唯一函数名，例如 `paired_runner/matlab/runtime/run_paired_observer_closed_loop.m`。将 `phys_attitude_replacement_candidate.m` 纳入同一源码树/锁。只改隔离副本，不改生产 runtime。先盘点完整依赖闭包，禁止从未锁定的生产路径、工作区或旧日志取代码/配置。
2. 两臂走同一个冻结 runner、同一 C5 position stack、`B2-RBF-Full-SPLIT`、1 kHz Plant / 100 Hz 姿态事件、固定 `J0`/BS 参数、command filter、C0 allocation 与 Plant。Baseline 保持 online attitude RBF 输出和更新开启；candidate 关闭两者、跳过 RBF 推理/更新分支，并只启用候选 helper。除这项预注册处理差异及臂标记外，两臂有效选项须规范化后相同；锁定 C5 方法 ID、position model/weights、head mode、RBF 初始权重和全部配置。
3. 接线限于两个时点：在共用姿态事件调度和当前 `ir` 生成后，candidate 用 `attitude_bs_step(...,zeros(3,1),P)` 的 `nominal_body_angular_acceleration`、当前 `omega`、当前 `s.arms.command(k,:)`、采样索引及事件标志调用 helper `prepare`；把其 signed `estimateTorque_Nm` 传给同一 BS 接口。每步 allocation 返回后、访问 Plant 实际 wrench/推进前，才用 `a.clipped_generalized(2:4)` 和 `t(k)` 调用 `commit`。保留当前实际事件时间戳与 `Delta_e`；首个无完整前区间的事件不造差分。候选 helper 只接收上述部署量和冻结 `cfg`，不得接收 `s.arms.rho_true/rhoDot_true`、`Ptrue`、`actualGeneralized`、`wrenchNow`、风矩或 Plant 导数。静态数据流检查须确认这一边界及 `estimateTorque=-tau_comp` 符号；candidate 也不得误记为 RBF 输出。

## 三场及输入身份

每场按表中 ID 调用当前场景生成器一次，并保留 `out.spec` 完整规格行、`out.scene` 全字段、`out.metadata` 摘要；三者分别规范化并计算 SHA-256，连同生成器/source SHA 写入 scene audit。scene ID、task/class/topology、C/W 与 seed 从 `out.spec/out.metadata` 原样核对；seed 必须取实际规格行，不得按 ID 或代码公式推测/重造。两臂使用同一不可变 `out.scene` payload，运行前后核对 scene hash 和字段级完全相同；另核对初态、`time=(0:.001:20)'`、参考轨迹、morphology command、风输入、有效 cfg、C5 控制器/RBF 工件和随机种子。ID/规格不符或任一输入 hash 不同即停；candidate 不能把用于 Plant 的真值字段传入 helper。

| 顺序 | scene ID | 预期场景核对 |
|---|---|---|
| 1 | `DL1018_DEV_T1_C00_W03` | HELIX；C00 无活动臂；W03 有风 |
| 2 | `DL1018_DEV_T2_C02_W15` | FIG8_3D；C02 仅臂 2 活动；W15 零风 |
| 3 | `DL1018_DEV_T3_C10_W11` | SQUARE；C10 / topology 34（臂 3、4）；W11 有风 |

## 锁、航次顺序与停止

隔离接入后必须运行无 Plant 合成/接口审计，并让审计实际调用候选 helper 的 `init/prepare/commit`：将其返回的 `estimateTorque_Nm` 送入真实 `attitude_bs_step` 接口，验证 signed torque 关系；核对 helper 返回的状态/事件输出与合成输入，并覆盖已知区间命令的 observer 更新。仅在测试中重写公式、不调用 helper 输出不算通过。随后生成完整 `source_lock_paired_runner_v1.json`，锁定隔离 runner 与依赖树 SHA、MATLAB/依赖版本、有效 cfg、C5/RBF 工件、三份 scene payload SHA、seed、两臂规范化选项。候选代码、合成审计和 source lock 由 root 审核后，由 root 放行六航次；root 放行前不得启动。放行后逐场执行 baseline 再 candidate，各一次，不重试。现存 baseline 没有与新隔离 runner 同一 `runner_sha`、`source_lock_sha` 和完整输入身份绑定，不能复用；三场 baseline 均须随 candidate 用同一冻结 runner fresh rerun。

每航次开始写 `run_start.json`，结束写 `run_status.json`、`scene_audit.json` 与原始运行日志；至少记录 `runner_sha/source_lock_sha/scene_sha/effective_config_sha/common_options_sha/effective_options_sha`、scene ID/seed/arm、C5/RBF 工件 SHA、步数与状态。candidate 另逐 1 ms 记录 morphology command 与自维护 `rhohat/rhoDothat`、`Jhat/Jdothat`、BS `alpha`、事件时间/`Delta_e`、区间 clipped command 样本/均值、角速度和惯量端点、`r_tau/dhat_a/tau_shape/a_extra/beta/tau_comp/estimateTorque`、RBF 开关、限幅/饱和、安全标志及 Q/SO(3) 指标；配对审计确认 helper 字段血缘。

任一身份/hash/选项不符、因果越界、candidate 触发 RBF、dt 不为 1 ms、20,000 transitions / 20,001 states 不符、日志非有限、非 `STABLE/RUN_COMPLETE`、安全停止或产物越界：保留失败记录并立即停，不重试。Baseline 失败则不跑该场 candidate。每个 candidate 必须 motor saturation=0 且 generalized clipping=0；tilt-limit 计数不得高于本场 baseline；本场 Q RMSE 与 SO(3) RMSE 均不得高于 baseline 超过 `1e-12`。任一单场门槛失败即停后续场景；三场均过单场门槛后，还须至少一个指标相对 baseline 严格改善超过 `1e-12`，否则本路线筛查失败。通过仍只构成三场 DEV 筛查，不推出稳定性或泛化；不得扩场或读 TEST。

本草案不启动或授权任何航次；合成审计、source lock 冻结及 root 放行是不同门槛。



