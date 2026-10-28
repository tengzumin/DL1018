# MLP15 姿态替代：匹配 B/C5 教师训练与闭环验证任务书（草稿）

日期：2026-10-26  
状态：**APPROVED_FOR_MATCHED_DATASET_BUILD**；允许在隔离目录构建 B24/C5-24/VAL48 数据与 source lock；训练需 source lock 通过主模型复核，Plant 需训练后另行放行。  
实验目录：`experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/`

## 1. 目的与唯一变化

前一版 MLP15 用 B 姿态 RBF 日志动作作教师，完整 DEV72 闭环未通过验收。原训练集有 768 条完整序列，而冻结的 C5 cohort 只有 DEV24 训练场景；直接把旧模型与 C5 重训模型比较会同时改变训练数据来源和样本量，无法区分两者影响。因此本阶段先构造**匹配的 B24 与 C5-24 两个训练臂**：按同一 DEV24 场景清单各取 24 条完整序列，分别使用 B RBF 与 C5 RBF 原始动作标签；架构、窗口、特征、优化器、seed、训练步数及 checkpoint 选择规则一致。两个模型都在同一 C5 VAL48 状态/标签上做 teacher-action 误差对照，并将已冻结的 B-768 MLP 作为附加历史基线。此为受控诊断与修复候选：它区分状态/动作分布来源的影响，并检查固定 MLP15 在匹配样本量下是否能拟合 C5 教师；仍不保证闭环姿态优于 C5。

两种训练教师明确区分：B24 控制臂只用于等量样本对照，使用 B72 同场景 raw 中的 B 姿态 RBF 状态与 `rbf_output_raw` 标签；C5-24 候选臂使用锁定 DSSM14、`C5_AXIS_MASK_M110`（M110=XY mask、PCF auxiliary enabled）位置栈轨迹与 C5 闭环姿态 RBF 标签。只有 C5-24 是后续部署候选；若获准进入 Plant，它与原 C5 一样保留在线 position head，但姿态 RBF 输出/更新关闭并改用冻结 MLP15。两训练臂以外的控制器配置不变，TEST48 不参与训练或模型选择。

两训练臂唯一计划变量是匹配场景上的闭环状态/动作标签来源（B-RBF/B 状态 vs C5-RBF/C5 状态）；每臂均为 24 条序列，架构、13 维因果特征、15 事件窗口、输出、训练超参数及部署控制栈冻结。MLP15 在线姿态推理时权重冻结；部署时姿态 RBF 输出与在线更新关闭，MLP15 输出仍经过既有 `dmax`、startup `beta` 和固定 `J0` 映射。

监督蒸馏损失直接优化的是已记录状态上的 teacher-action RMSE；它不直接优化闭环 SO(3) 误差，也不保证学生在自身 rollout 状态上优于 C5-RBF。C5-RBF 可能有在线更新状态或学生输入未包含的内部信息；学生冻结权重、有限因果窗口会出现闭环状态分布漂移。因此，本轮不得预称其必然解决姿态目标。禁止引入时变惯量重建、`Jhat/Jdot_hat`、Plant 真值、disturbance observer、physics feedforward、B 输出拼接或姿态 RBF 隐状态。

## 2. 输入身份与分割

以 C5 DSSM14/M110 DEV72 冻结输入合同为唯一场景清单来源：

- `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json`
- `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json`
- `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_BATCH_STATUS_v3.json`
- 对应的 `C5_DEV72_RELEASE_v3.json`、source binding、run markers、run_start、run_status 与 raw。
- `experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json`、`B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json`、`B_TRACEABLE_DEV72_RELEASE_v3.json` 及其逐场 status/raw。

输入合同定义同一 cohort 的 **DEV24 + VAL48**。其中 C5 batch status 记录了 60 场新闭环运行，原始记录状态为 `RUN_COMPLETE_RAW_PENDING_AUDIT`；合同列出另外 12 场 VAL 作为已存在结果复用。实际映射必须从冻结合同逐场解析，禁止根据目录顺序重新划分：

- 训练：24 个 `DEV` 场景。
- 教师验证与 checkpoint 选择：48 个 `VAL` 场景。
- `TEST48`：不得读取、解封、用于训练、归一化、模型选择或评分。

B 对照复用锁定 B72 raw/status；C5_RBF 对照复用同一场景 ID、输入物理数组与身份合同下的 C5 raw/status。训练与评估均不得重跑 B 或 C5。场景身份、Payload、reference、initial state、morph schedule、wind、seed 或 source hash 有任一不匹配时，该场不得静默配对或补跑，须停下并报告。

## 3. 训练前强制门：B24/C5 教师 raw/trace 独立审核

本门必须先于标签提取、normalizer 拟合及任何训练运行。审计范围是 72 场完整教师 cohort：

1. 对 60 条 `RUN_COMPLETE_RAW_PENDING_AUDIT` 记录逐条独立核验 raw、run_start、run_status、attempt marker、first Plant marker、SHA、scene ID、source/release/input-lock 身份与时序。所有启动和 raw 记录保留原位。
2. 对合同中复用的 12 条 VAL raw 核验其既有 parent audit、同 cohort C5 模型/控制栈身份、scene/payload 身份和必要日志字段。缺少适用审计或 hash 不一致时，不能把该场标签当作通过项。
3. 对 B24 匹配控制臂，逐场核验 C5 lock 所指向的 B72 raw/status SHA、场景身份、20,000 transitions/20,001 states、STABLE、1,999 姿态事件、有限 13 维输入/3 维标签、时间索引因果性及无未来泄漏。原 B run status 若仍标 `RUN_COMPLETE_RAW_PENDING_AUDIT`，保留原状态并在本阶段单独披露，不回写历史账本。
4. 每个 C5 场确认完整 20,000 transitions/20,001 state samples、STABLE、有限状态/特征/动作；姿态事件数与时间索引符合冻结采样协议，标签与事件一一对齐，无未来样本泄漏。
5. 对 C5 臂确认标签是 C5 闭环姿态 `rbf_output_raw`；对 B24 臂确认标签是同场景 B72 姿态 RBF 的 `rbf_output_raw`。字段名虽含 `raw`，数值已过 `dmax` 限幅、尚未乘 startup beta，单位 rad/s²；`rbf_output_unclipped` 才是未限幅字段。训练目标固定使用“限幅后、beta 前”动作，避免重复应用 beta。核验 beta、`J0` 映射与各自 raw 的实际补偿一致；禁止用 C5 位置输出、Plant 真值或 offline 诊断量作标签。
6. 确认 C5 教师 raw 的控制身份为 DSSM14/M110 位置栈 + 姿态 RBF，C5 姿态 RBF 输出/更新开启；同时确认 B24 对照 raw 的场景/输入身份匹配且 B 姿态 RBF 输出/更新开启。两臂均不得从惯量重建、observer 或物理前馈读取标签。
7. 逐场保存审计通过/失败、路径、原始 SHA、报告 SHA 和失败原因。任一 DEV train 场失败则停止训练；任一 VAL teacher 场失败则停止 checkpoint 选择及下游扩展。不得靠删除失败场、换 split 或静默替换日志凑齐 72 场。

此阶段审核只读，不调用 Plant、不修改旧 raw/status/markers；任何 C5 raw/trace 问题先交主模型裁定，不自行修历史结果。

## 4. 固定模型与训练配置

进行两次匹配训练（B24、C5-24 各一次），均使用原 MLP15 配置；除每臂 DEV24 数据与对应 TRAIN-only normalizer 外不改任何项。两臂逐场训练序列数和事件数必须一致：

- architecture：`MLP15`；输入维数 13、15 个事件，按 event-major/feature-minor 展平；隐藏层 `[64, 32]`，SiLU，输出维数 3。
- optimizer：Adam，learning rate `0.001`，weight decay `1e-5`，batch size `512`。
- loss：`SmoothL1(beta=1.0)`；两臂均用 seed `2026102001`，每臂 60,000 optimizer steps，每 1,000 steps 在同一 C5 VAL48 上评估部署目标动作 RMSE。
- B24 训练标签为匹配 DEV24 场景的 B72 姿态 RBF `rbf_output_raw`；C5-24 标签为同场景 C5 姿态 RBF `rbf_output_raw`。二者事件均为 `k`、post-`dmax`、pre-beta、rad/s²。
- 每个模型的 `input_mean`、`input_std`、三轴 `target_rms` 仅由该臂 DEV24 训练数据拟合；不得由 VAL48 或 TEST 更新。
- 两臂 checkpoint 均按同一个 C5 VAL48 **物理单位 scene-macro teacher-action RMSE** 规则选最早严格最小 step；评估预测先乘各自 `target_rms`，再按部署 `dmax` 限幅后与 post-dmax 标签比较。这样两臂使用同一物理误差尺度，也匹配 runtime。报告两条训练曲线、所选 step、数据/脚本/模型/normalizer SHA 和可复现命令。

若任一臂的标签结构无法按上述既定 13×15 接口直接构造、B/C5 DEV24场景与事件数不匹配，或需要改变模型结构、特征、目标单位、loss、seed、步数、优化器、normalizer 规则或 checkpoint 规则，则停止并另写变更任务书，不在本阶段自行扩范围。

## 5. 训练后无 Plant 检查

在任何闭环航次前完成并交主模型审核：

- 新数据 manifest 精确列出 B24/C5-24/VAL48、每场 raw/status SHA、event 范围、标签定义和分割来源；确认两个训练臂都恰为 24×1,999 事件，TEST 未读取。
- 两个 normalizer 来源分别可复算，且各自只 fit 对应 DEV24。
- 两个 checkpoint 尺寸/数值、各自 60k 训练账本、共享物理单位 VAL 最优选择规则通过独立读取审计。
- Python/MATLAB MLP15 前向 parity 最大绝对误差 `<=1e-5 rad/s²`；因果时序、首 14 event 的 zero-history padding、输出限幅、beta 和 `J0` torque map 与现有 runtime contract 一致。
- 关闭姿态 RBF 输出/更新；MLP frozen；拒绝 Jhat/Jdot、Plant truth、observer 与 physics feedforward 输入。运行静态检查、无 Plant smoke 和源码/模型/任务书 source lock。

任一项失败不启动 Plant，不覆盖前一版 MLP15、C5 raw 或历史产物。

### 同状态 teacher-action 误差对照与结果解释

在闭环运行前，将 B24 模型、C5-24 模型和旧 B-768 MLP15 分别应用到**同一批 C5 VAL48 因果特征窗口**，模型输出按部署 `dmax` 限幅后与该场 C5 `rbf_output_raw` 标签计算 teacher-action RMSE。主比较使用物理单位 rad/s² 的逐轴和场景宏平均误差。该对照不调用 Plant；VAL48 已参与 checkpoint 选择，因此仅是开发诊断，不是独立泛化证明。

结果分流：

- C5 raw/trace 审计失败：停在数据来源/标签身份问题，禁止训练。
- C5-24 在同一 C5 VAL48 上的 teacher-action RMSE 严格低于 B24 和旧 B-768：支持 B/C5 训练域差异是重要因素，但不证明闭环会优于教师。通过无 Plant 审计后才进入单场工程门。
- C5-24 不低于 B24：没有证据表明仅匹配 C5 域改善动作拟合；不得扩为 72 场闭环。若两臂均拟合差，主模型优先判断特征/表达/在线适应能力；若两臂均拟合好但闭环候选差，判断是闭环目标或 rollout 稳定性问题。不得把这些分流预写成已证实根因。
- 动作拟合改善但单场安全门失败：停止，不扩展。
- 动作拟合改善、单场门通过但 DEV72 未满足闭环验收：结论为动作模仿收益未转成所需闭环收益；这指向剩余的闭环状态漂移、特征/表达能力或缺少在线适应问题，不能把具体因素写成已证实根因，也不能宣称已解决。
- 只有所有闭环与安全门均通过，才可说该固定 MLP15 在本仿真 cohort 上达到预设应用目标；该结果仍不证明跨种子、实机或任意轨迹泛化。

## 6. 单场工程门与 72 场扩展

训练后先只运行一个预先锁定的工程场景：`DL1018_DEV_T1_C00_W03`。此场景只检查实现和安全，不用于调参、改阈值或宣称性能改善。使用同一输入身份绑定的 B、C5 raw 作只读对照。

扩展前必须确认：完整稳定 20,000 transitions；输出和状态有限；MLP trace 13 维、因果且逐事件与实际补偿 Nm 相等；姿态 RBF 输出/更新关闭；没有安全停止、电机饱和或 generalized clipping；tilt projection 样本数不高于同场 B 与 C5；run marker、输入、模型和源码 SHA 全部吻合。首场未通过即停止，不跑剩余场景。

首场通过后，最多新增 **72 个候选 Plant 航次总计**（首场计入上限，再跑剩余 71 场），严格按冻结 72 场清单运行。每次启动前核对无冲突重负载 MATLAB/Plant；单一重负载闭环作业；raw/status/attempt 不覆盖。只复用现存 B72 与 C5_RBF raw，不重跑对照。单场失败按真实启动计数、保留日志并停止后续扩展，除非主模型另行审核批准工程修正。

## 7. 评分、性能与安全门

沿用锁定的 DEV72 Q 与 SO(3) scoring rule：0–20 s、按场景等权宏平均；胜负按未舍入数值与 `1e-12` 容差。该 SO(3) 规则以锁定参考加速度/yaw 和固定名义 `P0` 离线重建姿态目标；它不进入控制器。由于 DEV72 raw 不含 `R_task`，报告中必须披露该评分构造及其探索性性质，不得把它描述为实测姿态传感器误差或 TEST 预注册指标。

候选通过需同时满足：

1. **相对 B：**完整 72 场宏平均位置 Q 严格更低、宏平均 SO(3) RMSE 严格更低；同时至少 `62/72` 场位置 Q 胜 B（未舍入数值，`1e-12` 容差）。
2. **相对 C5_RBF：**完整 72 场宏平均姿态 SO(3) RMSE 严格更低。
3. **位置对 C5 的容忍：**宏平均位置 Q 的相对退化 `(Q_MLP15 - Q_C5_RBF) / Q_C5_RBF <= 0.10`。这是主模型对用户“位置可稍微退化”的暂定量化解释，并冻结为本阶段验收门槛；不是既有理论阈值，不得查看结果后改门槛。
4. **分组限制：**W09–W14 高频组与 W15 无风组沿用既有组门：候选 Q 与 SO(3) 宏平均均不得高于 B，候选姿态 SO(3) 宏平均不得高于 C5_RBF。各组按场景等权，必须报告场景数、绝对值和相对 B/C5_RBF 的差值。
5. **工程安全：**72 场均完整稳定，无 safety stop；候选电机饱和及 generalized clipping 样本数均为 0；每场 tilt projection 计数均不高于同场 B 与 C5_RBF。

位置宏平均 Q 严格优于 B 与至少 `62/72` 场 Q 胜 B 两项都必须满足；胜场数不能替代宏平均门槛。仍报告 Q、SO(3) 逐场胜/平/负、X/Y/Z、早晚阶段、峰值、最大角速度、tilt、饱和、裁剪和控制耗时。所有输场保留，不能通过删场/换指标通过门。

## 8. 交付与决策

本阶段交付：C5 72 场 raw/trace 主审与 B72 对应 DEV24 raw/trace 审计；匹配的 B24/C5-24/VAL48 标签 manifest；两臂训练记录、checkpoint 与各自 normalizer；MATLAB parity/static/no-Plant 审计；候选单场与完整 72 场 markers/raw/status；逐场配对 CSV、风组/任务组统计、全部失败记录和复现命令。

主模型审核顺序：C5 raw/trace 审计 → 训练配置/source lock → 训练后模型与 parity → 单场工程门 → 是否扩至剩余 71 场 → 完整配对复算 → 是否进入后续 TEST 申请。当前任务书不会自动解封 TEST；候选若不达门，TEST 保持封存。

## 9. 主模型审核决定与状态（2026-10-26）

- **位置 Q 对 C5_RBF 的 10% 上限：**主模型暂定并冻结，公式为 `(Q_MLP15 - Q_C5_RBF) / Q_C5_RBF <= 0.10`。
- **位置胜 B 门槛：**保留原任务书要求，至少 `62/72` 场 Q 胜 B，并且 72 场宏平均 Q 严格优于 B。
- **高频/无风组别门与 tilt/执行器门：**主模型审核通过，沿用第 7 节冻结门槛。
- **C5 raw/trace 与身份：**主模型复核通过。独立审计报告为 `audits/C5_TEACHER_RAW_AND_MLP15_SAME_STATE_AUDIT_v1.md`，SHA-256 `fe577e5530a949472c319eb9adfee9d81c3c130fea95def57d474b8735c6edf4`。主模型用 PowerShell 7 复算 C5 batch 的 60 条记录与 input lock 的 12 条复用记录，共 360 个 raw/status/run_start/marker 文件哈希，全部匹配；72 个场景 ID 清单一致。审计报告核验 72/72 姿态事件 trace 的有限性、时序、限幅、beta 应用关系及固定 J0→实际 Nm 补偿闭合。12 条复用记录保留其既有 `PASS_C5_RAW_ALL_EVENTS`；60 条原 run status 继续保留 `RUN_COMPLETE_RAW_PENDING_AUDIT`，不回写或改签历史状态，但本次独立主审通过，允许本阶段读取它们作为 C5 教师数据。显式 `attitude_event_beta` 字段缺失；beta 由锁定源码与 raw applied-acceleration 关系复核，须在报告中披露。
- **诊断边界：**本轮 C5 教师蒸馏是受控候选，只直接优化已有状态上的教师动作误差，不能预先推断它会在闭环优于 C5。任务书已规定同一 C5 VAL48 状态上的新旧 MLP teacher-action 误差对照与失败分流；主模型确认该研究问题成立。
- **训练样本量更正：**主模型审查发现，已冻结的旧 B 教师训练数据有 768 条完整序列，而 C5 DEV train split 只有 24 条。若只训练 C5-24 并与旧 B-768 模型比较，训练来源与样本量同时改变，不能区分二者。此前单臂训练批准已撤回，不得按旧单臂草案启动。
- **B24 数据可用性复核：**C5 lock 所列 24 个 DEV 场对应 B72 raw/status 哈希由主模型以 PowerShell 7 独立复核 48/48 匹配；Luna 的只读全场检查确认 24/24 均有 1,999 个因果事件、13 维 finite 特征、3 维 finite 标签及 clip/beta 应用闭合。B status 的 `RUN_COMPLETE_RAW_PENDING_AUDIT` 历史状态保持不变；此处仅批准作隔离匹配训练对照。
- **输入特征一致性：**旧 B 数据提取器 `prepare_tcn_teacher_dataset_v2.py::load_scene` 与本阶段新 builder 都将 `filtered_attitude_reference − Euler` 用 `atan2(sin(error),cos(error))` wrap；旧 manifest 的字段名少写“wrapped”，数值特征语义一致，不新增预处理变量。形态命令由源码定义为 `rhoDot / morph_speed_mps`，是 [-1,1] 无量纲归一化指令；DEV24 的 B/C5 命令轨迹逐数组一致。
- **当前决定：**批准离线构建 B24 与 C5-24 等量训练臂（每臂 24 场×1,999 事件）及共同 C5 VAL48 评估数据；不训练、不运行 Plant。执行者生成逐场 input/data manifest、数据/脚本 SHA 与 source lock 后交主模型复核。复核通过后再放行两次同 seed/同配置训练。
- **训练/Plant 放行：**训练完成后先交两个模型、各自 normalizer、账本、MATLAB parity 和无 Plant 审计；主模型单独审核后再放行 C5-24 候选的单场工程门。B24 仅是离线训练对照，不启动 Plant。TEST48 继续封存。

## 10. 复用场景身份审计例外与失败账本（2026-10-26）

### 10.1 限定的父审计身份链例外

第一次修复后重试发现，C5 lock 的 12 条 `C5_reuse` 中，旧场景 `DL1018_VAL_T2_C00_W10` 的历史 C5 `run_status.json` 缺少 `scoring_B72_raw_sha256` 和 `scene_identity`；该行的旧 `B_source` raw SHA 与当前 B72 scoring raw SHA 不同。主模型核对父审计摘要 `reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/screen12_parent_review/SUMMARY.json`，SHA-256 `fe217ac8b259706b1953e07dd44586b6a64368a6d4f5e0145e8f507863d82ad8`：该场 C5 raw SHA 为 `9115113229c8fe3add21e1337216ceded2f829e06f4eb1d5a4930eb2e87020c4`，当前 B72 raw SHA 为 `5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957`，两边 `external_identity_sha256` 均为 `954cddfbe68c7682dc176ac98cfe9d7936e61101805a8cf4316c6fba4b10809a`，逐场审计状态为 `PASS_C5_RAW_ALL_EVENTS`，B identity 状态为 `PARENT_AUDITED_NEW_TRACEABLE_B72`。父摘要顶层状态是 `C5_SCREEN_PASS`、`TEST_accessed=false`、`training=0`、`new_Plant_in_audit=0`。

该情形采用父审计证据的逐场绑定，不放宽 SHA 或场景身份要求。离线 builder 必须固定并核验该摘要路径/SHA、顶层 PASS/TEST/训练/Plant 门，并将摘要中 12 条 audit scene ID 与 lock 的 12 条 `C5_reuse=true` scene ID 集合精确比对；每场还要精确比对 C5 raw 路径/SHA、B72 raw 路径/SHA、两侧 external identity、父审计 PASS、父审计 event-count metadata 与 lock 记录。若 C5 status 存在 `scoring_B72_raw_sha256`，仍必须与同场 B72 lock SHA 完全相等；仅该字段确实缺失且该行是 `C5_reuse=true`、父摘要逐场证据全部精确匹配时，才允许使用该父审计字段作绑定。若 `scene_identity` 存在，继续逐字段核验；只有该字段缺失且父审计逐场证据通过时，才能用父审计兜底。非复用行不允许任何此类回退。父摘要路径、SHA、逐场字段和回退方式必须写入数据 manifest；任何一项不匹配即停止，不改写历史 `run_status`、lock 或 raw。

### 10.2 离线构建失败账本

以下三次均在 NPZ/manifest/B24 audit 最终写入前停止，三项数据产物均未生成；没有训练、Plant 或 TEST 访问，历史 raw/status 未修改：

1. **首次尝试：**PowerShell 7 命令 `python experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/build_matched_teacher_dataset_v1.py --execute`。在首个 B24 场景 `DL1018_DEV_T1_C00_W03` 读取完 status 后，manifest row 直接索引不存在的 `run_status_path` 字段而抛 `KeyError`。失败时 builder SHA-256 `01103a4cd9ab76a8e97e44b5ebe237f9a345342bc1fbec7620f404f99f62a419`；完整日志 `DATASET_BUILD_FAILURE_v1.txt`，SHA-256 `22889c32e97fd15aea95fc9b49ed043d264c678d3bb578c16327a7f14271c3b7`，日志记录 UTC `2026-10-26T09:36:22.027Z`。
2. **修复后重试：**同一 PowerShell 7 命令。在 `DL1018_VAL_T2_C00_W10`，旧 C5 status 缺少同场 B72 SHA 字段，被严格身份门停止；随后主模型裁定按第 10.1 节使用已存在父审计逐场证据作有限回退。builder SHA-256 `4361a5728ad7a1e44780bcd7335ccadcf7bdc1fd947fa14bba00f11efad1c346`；完整日志 `DATASET_BUILD_FAILURE_RETRY01_v1.txt`，SHA-256 `2653d661d33c8926671dc94fb7c9a0edca8b5debd586bf2963fb777d38851d7f`，日志记录 UTC `2026-10-26T09:37:50.339Z`。
3. **父审计例外放行后的构建尝试：**同一 PowerShell 7 命令。失败发生在读取 C5 `DL1018_VAL_T2_C02_W12` 的 raw 后；此前 B24 以及该行之前的 C5 特征/标签已在内存处理，但所有数据产物尚未写入。失败仅因为比较锁定的仓库外旧 `B_source.path` 字符串时调用了 `repo_file()`，将身份路径误当作待读取输入而拒绝；没有打开该外部旧 `B_source` 文件。builder SHA-256 `feabb4a0b3b9bd4242e9761a4f96ade07ffb6e33684cf22583452bbab7b27d19`；完整日志 `DATASET_BUILD_ATTEMPT03_v1.txt`，SHA-256 `865d8de1d293e07c0c5cec9a03af03b726eca3bc98768cd1c2c84a6c0895512d`，日志记录 UTC `2026-10-26T09:48:58.614Z`。这是路径身份比较实现错误，不代表 raw 或其身份无效；修复后仅允许对两个绝对路径字符串进行 Windows 规范化比较，实际输入文件仍必须通过 `repo_file()` 仓库内边界。

上述账本保留为真实失败记录，不把这三次计为数据集成功，也不因使用父审计证据而改签旧状态。路径比较补丁须经静态主审；后续重新构建须按新授权命令执行。




