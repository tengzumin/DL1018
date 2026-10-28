# 任务书草案：形态惯量前馈 + 力矩等效扰动观测器三场 DEV 配对筛查

日期：2026-10-25。状态：待主审逐式/单位审核并另行放行；本文件只定义执行方案，不授权运行。未改代码、未启动航次、未读取 TEST、MAT 或 raw。设计依据见 [修订设计审查 v2](../../reports/attitude_cm18_c524_coverage33_20261025/physics_replacement_design_v1/ATTITUDE_PHYS_INERTIA_OBSERVER_DESIGN_v2_ZH.md)。

执行放行顺序与合成接口门槛由 [v1.1 补充条款](PHYS_ATT_OBSERVER_DEV3_TASKBOOK_ADDENDUM_v1.1_ZH.md) 补充并优先适用。

## 目标与单因素对照

检验一个机制：命令侧 `rhohat/rhoDothat` 计算惯量变化前馈，100 Hz 一阶有界扰动估计器补偿其余等效力矩。候选不训练，不用 CM18、RBF 特征或在线 RBF 更新。对照为同场、同输入、同冻结 runner 的两条闭环支路：

1. C5 position 栈 + 原 online attitude RBF（RBF 输出/更新均开）。
2. 同一 C5 position 栈 + 候选姿态补偿（RBF attitude 输出/更新均关）。

除 attitude compensation block/开关外，场景对象、位置控制、姿态 BS `J0`/增益、command filter、C0 allocation、执行器、限幅、随机种子、仿真步长和保存配置必须逐字节一致。baseline provenance 尚未锁定，因此不得重用旧航次；每场 fresh baseline 与 candidate 各跑一次，按场配对。不得训练或选参。

## 锁定方程和部署可用输入

Plant 转动方程为 `J*omegaDot + omega×(J*omega) + Jdot*omega = tauAct + tauWind`。候选当前采样 `j` 用 `alphaBS`（body-frame，`attitude_bs_step` 输出的 `nominal_body_angular_acceleration`）、当前 `omega` 和命令侧 `Jhat/Jdothat` 计算：

```text
tau_shape_j = (Jhat_j-J0)*alphaBS_j
            + omega_j × ((Jhat_j-J0)*omega_j) + Jdothat_j*omega_j        [N*m]
rhohat_(j+1) = clip(rhohat_j + 0.001*0.05*u_j, 0.15, 0.25)             [m]
rhodothat_j = 0.05*u_j                                                 [m/s]
```

scene command 源码核验已通过：场景生成器在 `t=(0:.001:20)'` 生成 `command(j)=rhoDot(j)/0.05`，并在每样本末积分到下一个形态状态；runtime 断言 `diff(s.time)==cfg.plant.dt==0.001`，按当前索引 `k` 取 `s.arms.command(k,:)`，当步分配后才推进 `x(k+1)`。因此命令与 Plant interval `[t_k,t_{k+1}]` 对齐，候选只用当前已发 `u_k` 和过去命令积分。当前 scene 的 `rho_hat` 字段固定为初始形态，候选必须维护自己的 `rhohat`。

姿态事件频率沿 C5 `controller_options_dl1018` 固定为 100 Hz；事件边界和 `Delta_e` 采用 `rbf_event_scheduler_step` 的实际 timestamp。每个 1 ms 子步存一个分配器输入侧命令 `tau_cmd_j=a.clipped_generalized(2:4)`（N·m）。该字段由 request 与 controller generalized limits 计算，发生在 C0 电机反解/电机饱和之前。它是 known clipped command，**不是 actual/applied torque**。仅该字段可以进入 observer；不得传 `Ptrue`、`rho_true`、`realized_generalized`、`wrenchNow`、风矩或 Plant 导数。Plant 自己继续推进场景真值不等于候选可读真值。实施时须通过静态数据流审查确认 observer 只读 command 字段。

对刚结束的事件区间 `[t_(e-1),t_e]`，`Delta_e=t_e−t_(e−1)`，按实际时间戳累计上一区间 1 ms 命令；对 `omega×(Jhat*omega)` 用 1 ms 样本梯形积分：

```text
tau_cmd_bar_e = sum(dt*tau_cmd_j)/Delta_e
r_tau_e = (Jhat_e*omega_e - Jhat_(e-1)*omega_(e-1))/Delta_e
          + trapz_[t_(e-1),t_e](omega × (Jhat*omega))/Delta_e
          - tau_cmd_bar_e                                                [N*m]
r_a_e = J0 \ r_tau_e                                                    [rad/s^2]
gamma_e = 1-exp(-Delta_e/0.10 s)
dhat_a_e = clip((1-gamma_e)*dhat_a_(e-1)+gamma_e*r_a_e, +/- dmax_a)
dhat_tau_e = J0*dhat_a_e                                                [N*m]
```

`dmax_a=cfg.rbf.attitude.dmax=[45,45,4.7124] rad/s²`。该设置来自匹配正式 RBF 支路：RBF 先在 acceleration-equivalent body x/y/z 通道限幅，再乘同一 `beta`、同一固定 `J0` 转成 torque。它不是 N·m 限值。`J0` 非对角时必须用矩阵左除 `J0\r_tau`，在 body-axis acceleration-equivalent coordinates 分轴 clip，再乘回 `J0`；有效 torque set 是 `J0*[-dmax_a,+dmax_a]`。

每个 1 ms 子步按当前候选状态算输出：

```text
a_extra_j = clip(J0 \ (tau_shape_j - dhat_tau_e), +/- dmax_a)          [rad/s^2]
beta_j = min(k*dt/cfg.rbf.attitude.beta_rise_time, 1)                  [dimensionless; match baseline]
tau_comp_j = J0*(beta_j*a_extra_j)                                      [N*m]
estimateTorque_j = -tau_comp_j                                         [N*m]
moment_j = attitude_bs_step(..., estimateTorque_j, P0)                 [N*m]
```

`attitude_bs_step` 内部做 `Mnom−estimateTorque`，因此负号才产生 `Mnom+tau_comp`。该接口值只是 signed compensation reuse，不得作为 disturbance estimate 日志。Observer `dhat_a` 初值 0；`rhohat_0=cfg.plant.arm_initial`；无完整前一事件区间时保持 0，不做虚构差分。

## 执行前检查：纯合成，无 Plant

单独生成 synthetic audit，不调用 `run_dl1018_closed_loop`、`simulation_parameters`、Plant、场景日志或真实飞行数据。要求：

- 任取 SPD `J0/Jhat`、合成 `Jdothat`、`omega/alphaBS`，核对 `Mnom+tau_shape = Jhat*alphaBS + omega×(Jhat*omega)+Jdothat*omega`，double 数值误差 `≤1e-10 N*m`。
- 构造满足已知 `r_tau` 的合成角动量端点和跨步 command，核对角动量差分残差、时间加权 `tau_cmd_bar`、`J0\r_tau`、低通递推和 dmax projection；核对三个通道轴序及 Nm→rad/s²→Nm 映射。
- 因果测试修改 `t_e` 之后的命令，断言 `rhohat/Jhat/r_tau/dhat_e` 不变；检查区间端点、`Delta_e`、当前 command 只进入未来 interval、clip 和 beta 都无未来采样。
- 任一符号、单位、时戳、未来数据、有限性或投影检查失败即停，不进入 DEV。

## 三场 DEV 固定配对与逐场门槛

场景均为开发留出集；其中 T2 明确纳入 3D 八字主轨迹。每个场景 20 s、20,000 个 1 ms transition。按下列顺序对每场跑 baseline 后跑 candidate，一次、不重试：

| 顺序 | scene ID | task / topology / wind | 机制覆盖 |
|---|---|---|---|
| 1 | `DL1018_DEV_T1_C00_W03` | HELIX；C00 无活动臂；W03 有风 | 检查无形变时扰动估计/前馈是否带来副作用 |
| 2 | `DL1018_DEV_T2_C02_W15` | FIG8_3D；C02 仅臂 2 活动；W15 零风 | 3D 八字 + 单臂形变，隔离惯量前馈效应 |
| 3 | `DL1018_DEV_T3_C10_W11` | SQUARE；C10 对应 topology 34（臂 3、4）；W11 有风 | 多臂形变、风和交互误差 |

每支须 `STABLE/RUN_COMPLETE`、20,000 transition、20,001 state sample、无安全停止且所有 observer/状态日志有限；候选 motor saturation 与 generalized clipping 均为 0，tilt-limit 计数不高于该场 paired baseline。逐场 candidate 的 Q RMSE (m) 与 SO(3) RMSE (rad) 均不得高于 baseline 超过 `1e-12`；三场至少一个指标相对 baseline 严格改善超过 `1e-12`。任一场、任一门槛失败就停止，不扩大 DEV、不改参重跑、不读 TEST。全部通过只请求主审另行批准扩充 DEV；不是稳定性或泛化证明。

## 精确产物、资源与停止条件

产物只允许写入本任务目录：

```text
experiments/attitude_physics_inertia_observer_20261025/
  PHYS_ATT_OBSERVER_DEV3_TASKBOOK_v1_ZH.md
  source_lock_v1.json
  synthetic/PHYS_ATT_OBSERVER_SYNTH_AUDIT_v1.json
  runs/<scene_id>/baseline/{run_start.json,run_status.json,run_raw.mat,scene_audit.json}
  runs/<scene_id>/candidate/{run_start.json,run_status.json,run_raw.mat,scene_audit.json}
  pairs/<scene_id>_PAIR_AUDIT_v1.json
  PHYS_ATT_OBSERVER_DEV3_SUMMARY_v1.csv
  PHYS_ATT_OBSERVER_DEV3_REPORT_v1_ZH.md
```

每条 run 日志必须能审计 `scene/time`, state/reference, morphology command、`rhohat/rhoDothat`、observer event timestamps/`Delta_e`、`omega` endpoints、`Jhat` endpoints、区间 `tau_cmd` sample/average、`r_tau`, `dhat_a`, `tau_shape`, acceleration clip/beta、`tau_comp`, `estimateTorque`, RBF 开关、requested/controller-clipped/nominal allocated command、motor saturation/clip、safety 和 metrics。`Ptrue`、真值 wind torque 和 `realized_generalized` 可由 Plant 日志存在，但不得被候选读取；逐 run audit 须核对 candidate observer 的字段血缘。

估时预算（未测墙钟）：6 次 fresh 20 s 闭环，共 120 s 仿真、120,000 次 Plant transition；合成审计、身份核验及汇总合计预留最多 3 小时串行 wall-time。闭环和审计新增产物硬上限 1 GiB，启动前要求至少 30 GiB 可用空间；不满足即不启动。任何输入/source hash 不一致、命令时间戳错位、候选读到禁止真值、非有限数、任务场景错误、安全停止或产物越界立即停止，保留失败输出，不重试。只要任一 DEV 指标门槛失败即停止本轮路线筛查。

## 源码与证据锁

执行前重新比对下列 SHA；任一变化须重新审查，不得继续用本任务书：

| 文件 | SHA-256 |
|---|---|
| `matlab/runtime/run_dl1018_closed_loop.m` | `9f6b436c8247c49783ec04ef326b20fc5d7de2870c9ab972212a0b2e4c432bc2` |
| `matlab/runtime/controller_options_dl1018.m` | `93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1` |
| `matlab/runtime/prepare_effective_config_dl1018.m` | `d7530b4088cd1255093c36c70d033eeef010efd3ab92b5c86defc64f66652d3d` |
| `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| `matlab/core/vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| `matlab/core/allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| `matlab/core/default_config.m` | `685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51` |
| `matlab/scenes/make_scenes_dl1018.m` | `7d11b4ebf63105b016c67f4b3c427282b35dafa53280ef2daf5578a6a16bb9ec` |
| `matlab/core/tcn0916_morphology_scenario.m` | `711a87e01e616ee141f9068a8c4e31758dc328ade3f692e1a92a5de723d30438` |
| `matlab/core/tcn0916_topologies.m` | `3fd341fa2292c8118f8b363611671677517c44009550bdf82e96cd751e6dce5f` |
| `matlab/core/rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| `matlab/core/rbf_mimo_update.m` | `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a` |
| `matlab/core/simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| `matlab/core/arm_mass_properties.m` | `8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5` |

只读场景时序依据：`make_scenes_dl1018.m` 生成当前索引 command；`tcn0916_morphology_scenario.m` 定义命令与状态递推；`run_dl1018_closed_loop.m` 以同一 `k` 消费命令、调用 allocator 后推进下一状态；`rbf_event_scheduler_step.m` 提供姿态事件边界；`allocate_control.m` 证明 clipped generalized field 与 `actualGeneralized` 分离。旧 C5 根因报告、15 场结果及覆盖任务书的身份 SHA 已记在设计审查 v2；它们只支撑已报告的 DEV 失败证据，本任务没有重新读取 MAT/raw。

## 理论和证据边界

这里的 lumped disturbance 是按动力学残差定义的总量，包含 actuator/C0/C(rho) mismatch、风与估计几何误差，不能由该残差单独区分来源。命令积分只在场景规定的理想 rate 模型下重建 `rhohat`，不证明真实形态精确跟踪。Observer LPF 与 projection 不构成稳定性证明；无 Plant 合成测试只查代数、因果与单位；三场 DEV 是开发筛查，不能推出渐近稳定、ISS、硬件性能、全覆盖有效或 TEST 泛化。
