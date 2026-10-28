# Cosine GRU tracking-error residual head：隔离实施任务书

状态：实现准备中；Plant 授权 0，训练 0，TEST 未读。此任务只在独立 study `gru_stream_cosine_tracking_head_dev_v1` 工作，不改 cosine/NCMD 旧 study、模型、训练器、raw 或评分缓存。控制代码在 root 实际审核前不得启动任何航次。

## 单因素与基线

候选是在已冻结 `GRU32_STREAM72_COSINE_S2026102001` 基础上增加一个纯 tracking-error residual head。GRU(13,32) recurrent weights、`head_weight/head_bias/target_rms`、normalizer、hidden reset/carry、当前 13 维合法特征、固定 cosine 模型字节均不变。候选部署 ID：`GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001`；模型来源仍锁到 cosine MAT SHA `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`。

保留位置 C5 DSSM14/M110、nominal BS、fixed J0/Jdot0、`[Inf Inf 6]` command filter、beta、dmax、30° tilt projection、Plant/actuator 和主动形变场景。RBF 姿态输出与更新关闭。无 Jhat/Jdot、变量惯量重建、真实 Plant truth、RLS、observer、新标签、新训练或额外输入。

## 逐事件公式与顺序

仅在真实 attitude event 调用新增 `gru_stream_tracking_head_step_v1`，从首场 `h=0, DeltaW=0_(33x3)` 开始。对当前合法特征按冻结 normalizer 执行冻结 GRU 得到 `q_base`（已乘 `target_rms`，物理量 rad/s²）与 `h_after`。取不归一化 `phi=[h_after;1]`（33×1），在更新前预测：

`q_raw = q_base + DeltaW_before' * phi`

应用顺序固定为 `q_clip=clip(q_raw, ±dmax)`，`q_beta=beta*q_clip`，`tau=J0*q_beta`。该输出用于当前事件；随后才更新状态矩阵。令 `surface=ai0.surface`、`T=ai0.euler_rate_map`、`drive=T' * clip(surface, ±s_limit)`，使用该事件实际间隔 `eventDt=attitudeEventDt` 和真实已准备 cfg 中锁定的逐轴参数：`gamma=[2.1,2.25,1.1]`、`sigma_w=[0.11,0.12,0.2]`、`s_limit=[2.3,2.3,1.4]`、`wmax=60`：

`DeltaW_unprojected = DeltaW_before + eventDt * (-beta*phi*(gamma.*drive)' - DeltaW_before.*sigma_w')`

`DeltaW_after = elementwise_clip(DeltaW_unprojected, -wmax, +wmax)`

仅 `DeltaW` 在线更新；GRU/原 readout 权重永远固定。beta 只进 residual torque 和 tracking 更新各一次；每个 Plant 1 ms 步的 held torque、下一次事件输出顺序及其他 BS/安全逻辑不变。第一事件的 `eventDt` 采用原事件调度器值；不得用固定名义 `dt` 替换它。

## 最小实现文件与审计数据

- 直接父：`gru_stream_cosine_dev_v1`。新 `candidate_runner_work` 从直接父精确复制；只在 isolated DEV engine 的 GRU event 分支改 init/step/trace/log 协议，并新增 `runtime/gru_stream_tracking_head_step_v1.m`。不得改 GRU forward 或 frozen GRU step。
- 新 driver 与 raw auditor 从 cosine study 复制后，仅绑定新 study/candidate/helper/协议字段和新 release/raw identity；manifest 仅复用路径与 SHA，不复制任何 runs/raw。
- trace 至少记录 event sample/time/eventDt、feature、q_base/q_raw/q_clip/beta/J0 torque、hidden before/after、phi、DeltaW before/derivative/unprojected/after、surface/T/drive、gamma/sigma/s_limit/wmax，以及输出-before-update与 no-RBF/no-inertia flags。每 1 ms 已有 applied torque / requested command trace继续审核。
- release 初始 `authorized_Plant_calls=0`、`Plant_calls=0`、authorized scenes 为空。SOURCE_LOCK 对新完整 source tree逐文件 SHA 锁定；SOURCE_DIFF 以 cosine 直接父为准，标出实际 DEV 与新增 helper 及 driver/audit 的变化。

## 允许的无 Plant 核验（root 代码审阅后）

纯合成事件核验：冻结 GRU 输出应精确等于直接父 `gru_stream_attitude_step_v1` 的 raw/hidden；DeltaW=0 时在相同 q clip/beta/J0 下 torque 逐点相同；事件输出必须使用更新前 DeltaW；非事件 1 ms 样点 held torque不变；记录的事件 dt、一次 beta、更新公式与逐元素 ±60 投影逐值复现；W0/RBF关闭/固定参数检查通过。随后才做必要 Python/MATLAB 双精度数值 parity、真实 cfg/`which` 与实际 DEV 和外层入口双重零预算拒绝。此任务书本身不授权 Plant。

若无 Plant 检查与静态审核均通过，root 独立审查实际实现后决定是否给首场授权；通过首场工程核验后才可能另批其余五场。这里不预设性能通过门槛，也不声称 tracking head 能解决姿态退化。
