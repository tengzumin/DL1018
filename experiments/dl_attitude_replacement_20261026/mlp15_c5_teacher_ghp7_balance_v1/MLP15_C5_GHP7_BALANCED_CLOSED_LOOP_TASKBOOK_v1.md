# GHP7-balanced MLP15：六场闭环开发筛查任务书 v1

日期：2026-10-26（Asia/Shanghai）  
状态：冻结；仅 G1/W00 工程门初始放行。其余五场须在首场 raw 审核后写入 continuation release。

## 候选与系统边界

- 候选：`DL_MLP15_C5_GHP7_BALANCED`，runtime arm `DL_MLP15`，权重 `mlp15_c5_teacher_ghp7_balance_v1/runs/C5_MLP15_GHP7_BALANCE_SEED2026102001/mlp15_attitude_weights_v1.mat`，SHA-256 `8e048e212ae17f4e588ba35d7af18ed5183799074fbc2c66dfe7c6e5a77d8138`。
- 已完成 60,000 步 MLP15 训练；仅 final step。MATLAB R2025b/PyTorch parity 最大误差 `2.591743831e-7 rad/s²`，容差 `1e-5`。本任务不再训练或调参。
- 位置环使用已锁定的 C5 DSSM14/M110 和同一 ACTIVE 形态；BS 名义控制、Plant、allocator、执行器及其余控制配置共用 C5 配对构造器。姿态 RBF 输出和在线更新关闭，MLP 权重冻结，固定 J0 仅用于角加速度残差到力矩映射。
- 13-D 因果输入仅含 wrapped attitude error×3、body rates×3、nominal BS torque×3、morph command×4。禁止 `Jhat/Jdot_hat`、惯量/质量属性、Plant truth、RBF 权重/隐状态、observer、physical feedforward 或未来输入。
- 沿用用户确认的共同限值：`max_tilt=30°`；姿态残差 `dmax=[45,45,4.7124] rad/s²`。两项均按原 C5 快照配置，不作候选专属调整。

## 固定六场及对照

| 场景 | 风组 | B/C5 数据 |
|---|---|---|
| G1/W00 | W00 | 复用 `GHP7_BASELINE_REUSE_MANIFEST_v1.json` |
| G1/W12 | W12 | 同上 |
| G2/W00 | W00 | 同上；B 和 C5 历史 `application_feasible=false` |
| G2/W12 | W12 | 同上；B 历史 `application_feasible=false` |
| G3/W00 | W00 | 同上 |
| G3/W12 | W12 | 同上 |

场景身份由既有 `GHP7_PILOT_PAYLOAD_MANIFEST_v1.json` 锁定。B 与 C5 raw 不复制、不覆盖、不重跑；candidate 每场 20,000 transitions。候选输出写入本任务独立目录 `pilot_runs_mlp15_c5_ghp7_balance_v1`。TEST48、DEV72 和其他场景不在本筛查中。

## 执行顺序

1. 对六场先做无 Plant 身份准备，核验 candidate 模型、parity、payload、R_task、C5 快照、位置模型和共同选项 SHA；确认新输出目录为空，TEST 保持封存。
2. 只放行 G1/W00 一次工程门航次。保存 `attempt_started.marker`、`run_start.json`、raw、status；即使失败也计入一次并保留。
3. 主审独立检查首场 raw、因果 trace、稳定/安全标志、输出残差和限幅计数。通过后才把其余五个 scene ID 写入续跑 release，顺序执行。
4. 六场完成后逐场与对应 B/C5 历史 raw 复算，并报告 W00、W12 和六场等权宏平均；所有历史不可行例外照实保留。

## 预登记闭环门

- 位置：六场宏平均 Q 严格优于 B；相对 C5 的退化不得超过 10%（`Q_candidate ≤ 1.10 × Q_C5`）。
- 姿态：六场 SO(3) RMSE 宏平均严格优于 B 和 C5。
- 工程：候选六场全部完整、STABLE、无 safety stop，且 `application_feasible=true`；报告 motor saturation、generalized clipping、tilt projection、residual `dmax` clipping 和实际耗时。任一场不完整或不可行即不晋级。
- 给出每场未舍入指标、W00/W12 组均值、对 B 与 C5 的配对差、raw SHA 和源身份。GHP7 是已用于先前候选筛查的开发场景；此结果不是独立测试或论文泛化证明。

## 资源和下一步

候选最多 6 个闭环航次；复用 B/C5 12 份历史 raw。一次只运行一个 MATLAB/Plant 作业，不并行重负载任务，不读取 TEST。只有六场完整且门通过，才准备新的 DEV72 任务书；本任务书不授权 DEV72 或 TEST。
