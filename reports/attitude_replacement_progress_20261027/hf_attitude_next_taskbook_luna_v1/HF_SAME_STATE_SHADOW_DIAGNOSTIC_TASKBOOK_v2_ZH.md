# 高频姿态替换：同状态 shadow 诊断任务书 v2

状态：只读诊断草案，待 ROOT 审核；不授权运行。2026-10-27 已完成执行前身份核验，未执行 shadow、MATLAB、Plant、训练或 TEST 访问。

## 决策与问题

下一项高频优先工作定为**同状态动作 shadow 诊断**，不改控制律、不改训练、不增加 Plant 航次。当前证据不足以支持一项有根因保证的单因素控制律变更。

要回答的问题：在高频 W09–W14 的同一条已记录状态轨迹、同一滤波参考和同一因果历史上，GRU tracking-head 与 C5 姿态 RBF 分别发出什么姿态补偿？动作差异是否在候选轨迹和 C5 轨迹上都存在？本诊断只隔离姿态模块的条件动作差异；不把 shadow 输出解释成闭环 SO(3) 收益。

位置控制保持 C5 DSSM14 与 M110。部署输入固定 J0/Jdot0，不重建部署端惯量，也不使用 Plant 真值作为模型输入。

## 现有结果与诊断动机

GRU_STREAM_COSINE_TRACKING_HEAD_FULL72 在 72 场 DEV/VAL 上的模型训练数据也包含这 72 场，因此属于开发筛查。高频 28 场宏平均如下：

| 方法 | 位置 Q (mm) | 任务 SO(3) (mrad) | inner SO(3) (mrad) |
|---|---:|---:|---:|
| GRU tracking-head | 9.715 | 58.854 | 13.817 |
| B | 10.719 | 54.816 | 15.506 |
| C5 | 10.179 | 58.795 | 15.688 |

候选相对 B 的任务 SO(3) 多 4.038 mrad，inner SO(3) 少 1.689 mrad；相对 C5 的任务 SO(3) 仅多 0.058 mrad，inner SO(3) 少 1.872 mrad。已有 W09–W14 路径分解显示，候选与 B 的差异集中在到达内环之前：task→command target 为 75.924/58.266 mrad，command target→filtered 为 56.383/14.023 mrad；filtered→actual 则是候选更低，为 13.817/15.506 mrad。候选与 C5 的 task 与 command 路径宏平均几乎相同。独立 DEV72 B/C5 复算也显示 C5 的高频 task SO(3) 比 B 高 7.26%、28 场中只胜 2 场。此证据支持先隔离同状态姿态动作，不能单独将 B 的高频任务差归因于 GRU。

CM18-A1 的 12 场旧汇总为 7/12 SO(3) 胜、7/12 位置 Q 胜，平均 SO(3) 0.5303° 对 0.6961°、Q 10.095 对 10.186 mm。A1 报表中的 SO(3) 按旧评分脚本是相对 filtered_attitude_reference 的 inner 指标，不是 external task SO(3)。两场 W14 退化（T1 +1.294°、T3 +0.850°），W09 的 T2 改善 0.405°。按 ROOT 对原 raw 的更正，A1 的 16 次 CM18 output clip 属 W02；W14 只有 T1 的 77 次 clip，T3 W14 无 clip；GRU tracking-head 全部 28 个高频场的 clip 计数为 0。上述 clip 归属不改变闭环评分，也不构成根因证明。

**旧数据缺项：**当前 CM18-A1 12 场报表没有 task SO(3) 字段；评分代码把 state 与 filtered_attitude_reference 比较。对应 12 个 A1 raw_run.mat 目前均不存在，目录中仅留 12 个 run_start.mat 与状态文件；状态记录的 raw_path/hash 仍在。12 个 C5 baseline raw MAT 仍存在。不得把 A1 的旧 SO(3) 数字改标成 task SO(3)，也不得声称可从现存 A1 raw 重算。

## 输入与冻结身份

1. **场景：**FULL72 配对评分中所有风编号 W09–W14 的 28 个唯一 DEV/VAL 场景。两条已执行状态轨迹为候选 GRU raw 与同场 C5 raw。准确场景清单如下：

   - DEV：DL1018_DEV_T1_C10_W09、DL1018_DEV_T1_C11_W12、DL1018_DEV_T1_C15_W14、DL1018_DEV_T2_C09_W10、DL1018_DEV_T2_C12_W13、DL1018_DEV_T2_C14_W14、DL1018_DEV_T3_C09_W09、DL1018_DEV_T3_C10_W11、DL1018_DEV_T3_C13_W12、DL1018_DEV_T3_C15_W14。
   - VAL：DL1018_VAL_T1_C02_W09、DL1018_VAL_T1_C03_W10、DL1018_VAL_T1_C04_W11、DL1018_VAL_T1_C05_W12、DL1018_VAL_T1_C06_W13、DL1018_VAL_T1_C07_W14、DL1018_VAL_T2_C00_W10、DL1018_VAL_T2_C01_W11、DL1018_VAL_T2_C02_W12、DL1018_VAL_T2_C03_W13、DL1018_VAL_T2_C04_W14、DL1018_VAL_T2_C15_W09、DL1018_VAL_T3_C00_W13、DL1018_VAL_T3_C01_W14、DL1018_VAL_T3_C12_W09、DL1018_VAL_T3_C13_W10、DL1018_VAL_T3_C14_W11、DL1018_VAL_T3_C15_W12。

2. **Raw：**逐场使用 `HF_RAW_INPUT_IDENTITY_v2.csv` 中的绝对路径和 SHA。候选路径来自 `FULL72_PAIRED_SCORE_v1.json` 对应行的 `methods.Candidate.raw_path`；C5 路径逐场来自 `C5_DEV72_INPUT_LOCK_v3.json` 的 `C5_reuse.raw_path`（复用）或 `C5_DEV72_BATCH_STATUS_v3.json` 的 `raw_path`（新跑），并与 paired score 行复核。不得从目录模板推导路径。28 场×2 条轨迹共 56 份 raw 全部存在、均在 DL1018 仓库根目录内，实际 SHA 与 FULL72 score 匹配；候选 raw 审计 SHA 28/28 匹配。身份清单：`reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2.csv`。

   C5 高频集合是 **6 条 lock reuse + 22 条新 raw**。6 条 reuse 场景为 `DL1018_VAL_T1_C02_W09`、`DL1018_VAL_T1_C05_W12`、`DL1018_VAL_T2_C00_W10`、`DL1018_VAL_T2_C02_W12`、`DL1018_VAL_T3_C00_W13`、`DL1018_VAL_T3_C12_W09`；实际 raw 在 `experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/...`。其余 22 条新 raw 在 `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/...`。每个场景的精确绝对路径均列于 CSV；这 6 条不能误写为 `runs_dev72_v3`。

3. **Raw 与状态身份：**候选 28 条 `audit_status=PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY`，每条 audit SHA 与 score 一致；其中 25 条为本 FULL72 raw、3 条沿用 parent raw。C5 6 条复用的 score audit 标记为 `PASS_C5_RAW_ALL_EVENTS`，C5 lock 记录 `parent_screen_event_count=1968`；C5 22 条新 raw 的 `audit_status=RUN_COMPLETE_RAW_PENDING_AUDIT`。**逐行保留 `run_status.json` 原状态：这 28 条 C5 的 status SHA 均匹配，但状态仍为 `RUN_COMPLETE_RAW_PENDING_AUDIT`；6 条旧 screen audit PASS 不会把原 status 晋级。**C5 22 条新 raw 的路径/raw SHA/status SHA 与 batch status 一致；6 条复用 raw 与 input lock 一致。任何 path/hash/status/audit identity 不一致即停止该场。核验摘要见 `HF_RAW_INPUT_IDENTITY_v2_summary.json`；score JSON SHA-256 `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff`，C5 lock SHA-256 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`，C5 batch SHA-256 `20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22`。56 份输入 raw 总计 3,951,882,219 bytes；输出预算只约束新生成诊断产物，不复制 raw。

4. **模型与配置：**固定 GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001，模型文件 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_c5_teacher_v1\runs\GRU32_STREAM72_COSINE_S2026102001\gru_stream_c5_teacher_weights_v1.mat`，SHA-256 b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567；训练配置 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\gru_stream_cosine_c5_teacher_v1\runs\GRU32_STREAM72_COSINE_S2026102001\training_config.json`，SHA-256 b85b9b545eba1939582b4e8909667338bfbff1e81dc4cfb295ec750c0a57739d。不训练、不重选 checkpoint。C5 位置模型为 DSSM14：锁定模型文件 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_training\models\DSSM14\matlab_model_and_parity.mat`，SHA-256 `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`；seed 2026102001、selected step 60000、W0 SHA `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`、normalizer SHA `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`。该模型文件是 C5 input lock 明确绑定的外部共享输入，路径在当前 DL1018 仓库根之外；不复制或改写。

C5 config 为 `configs/effective_config.mat`，SHA-256 `cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f`；候选 frozen config 记录固定 `J0` SHA-256 `8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75`、`Jdot0=0`、attitude `dmax=[45,45,4.7124] rad/s²`、beta rise time 2.2 s。命令滤波 `wn=[18,18,12]`、damping `[1,1,1]`、加速度限幅 `[Inf,Inf,6]`。C5 使用 1 ms Plant 采样、100 Hz attitude event；位置保持 DSSM14/M110。固定惯量是 controller 的名义 `J0` 映射，不从 deployed Plant truth 重建 `Jhat/Jdot_hat`。

5. **禁止输入：**不得输入 Jhat、Jdot_hat、真实可变惯量/质量、Plant truth、未来状态、未来参考、未来动作、未来滤波输出或 RBF/GRU 未来内部状态。原始 Plant 真值如有，可作为独立诊断 target 列；必须与输入矩阵隔离并标注字段来源。不得用惯量反演补造 target。

## 2026-10-27 执行前核验结果（只读）

- `HF_RAW_INPUT_IDENTITY_v2.csv` 包含 56 行（28 candidate + 28 C5）：全部 raw、run_status 存在；实际 raw SHA、status SHA 与 FULL72 score 相符；所有 raw/status 路径位于 DL1018 仓库根目录下。候选 28 份 audit SHA 均匹配。C5 6 条 reuse 路径/raw/status SHA 与 C5 input lock 一致；22 条新 raw 路径/raw/status SHA 与 batch status 一致。
- 56 份 raw 的 HDF5 `log` 组均包含任务需要的核心字段。Candidate 核验字段：`time, transition_time, state, initial_state, reference, arms, command_filter_target_euler, filtered_attitude_reference, filtered_attitude_rate, attitude_event_flag, gru_stream_attitude_trace, gru_stream_attitude_model_sha256, attitude_bs_nominal_torque_Nm, attitude_compensation_applied_torque_Nm`。C5 核验字段：共同状态/滤波字段及 `rbf_event_audit, rbf_event_count, rbf_event_dt, rbf_input_sample, rbf_output_raw, rbf_output_held, rbf_output_unclipped, rbf_update_dt, rbf_update_flag, rbf_weight_norm, attitude_rbf_compensation_torque_Nm, attitude_nominal_torque_Nm`。字段存在性已验证；本次没有逐字段读取数组 shape、有限值、事件计数或滤波重建误差，这些必须作为运行前 fail-closed 门。
- C5 active-source inventory 的 main runner、`rbf_mimo_update/basis`、`command_filter_init/step`、`attitude_bs_step`、`controller_parameters`、`init_dl1018`、`controller_options` 实际 SHA 与 C5 input lock 一致。C5 active source SHA 和候选模型身份见下方源码表/锁定身份。

## 执行定义：两条轨迹、每条轨迹两种姿态模块

诊断单元为 scene × state trajectory。每场有两条已记录轨迹：candidate state trajectory 与 C5 state trajectory。每条轨迹上分别做 GRU tracking-head 和 C5 RBF 两次 shadow replay；同一轨迹内两种方法必须逐样本使用完全相同的 state、arms、filtered attitude reference/rate、固定名义 BS 控制量及历史。共 28 场 × 2 条轨迹 × 2 个姿态模块。候选与 C5 两条真实闭环轨迹彼此不同；不得将两轨迹间的 RMSE 差称为同状态对照。

### 先过重建可行性门

1. **因果滤波重建：**从 raw 的 initial_state 欧拉角初始化 command_filter_init；按原 1 ms transition_time 顺序，只将当下/过去的 command_filter_target_euler 送入锁定滤波器，重建 filtered_attitude_reference 与 filtered_attitude_rate。重建只允许 causal step，不得一次性零相位滤波、使用未来 target 或事后平滑。`command_filter_step` 每步先用当前 target 计算请求/限幅加速度，返回的 `reference.euler` 和 `.euler_rate` 是**本步滤波状态更新前**的值；随后先更新 rate，再用新 rate 半隐式更新 Euler，并 wrap 到 [-π,π]。逐点与 raw `filtered_attitude_reference/rate` 比较，误差限为 attitude 1e-10 rad、rate 1e-8 rad/s；首点、事件边界、末点都纳入。再确认两个宿主的 1 ms time/state/sample 对齐、event flag 对齐、每场事件完整性；一旦事件样本计数或字段长度与锁定调度不符则停止该 scene。任一条轨迹不通过则该 scene 不做跨模块比较。

2. **GRU 原轨迹自复播：**复用 gru_stream_cosine_tracking_head_full72_v1/audits/audit_gru_stream_tracking_head_raw.m 已通过的模型/事件复播结果，不运行 MATLAB 审计器。按锁定模型 SHA 和该 raw 的 gru_stream_attitude_trace 校验；须确认 1,999 个事件、hidden 和 DeltaW 状态链完整，actual_event_dt 与 sample_index/time 对应，输出与 torque closure 通过。

3. **C5 RBF 原轨迹自复播：**C5 runner 在每场初始化 `rbfAtt.W=zeros(...)`；locked `controller_options_dl1018`/position options 路径不设置 `rbf_attitude_initial_weight`。执行时必须再以锁定 opts identity 验证没有 override；若字段存在或无法判定则停止该 scene。每个宿主轨迹、每场从 W=0 开始，不能跨场或跨宿主串接。姿态 RBF 输入顺序为 `[e1,s1,e2,s2,e3,s3]`；每个事件以 `W_before' * Phi` 产生未限幅输出，按 `dmax` clip，然后先将 `beta*datt` 乘固定 `J0` 得 torque，再按 RBF 更新式计算/投影 `W_after`。本 C5 选项 `formal_rbf_baseline=true`，runner 使用 fixedController；RBF 输出立即保持到下一事件（零延迟）。先在 C5 native state trajectory 上对齐 raw 的 `rbf_output_raw`、event flag、update flag、weight-before/after 与 applied torque；逐事件最大差须小于 1e-9 rad/s²，torque 小于 1e-10 N·m。C5 lock 的 6 个旧 screen 记录 `parent_screen_event_count=1968`，它不替代 raw per-step `attitude_event_flag/rbf_update_flag`。执行时须验证两者时刻和覆盖完整；若 1,999 个预期事件的任一输出/更新字段缺失或不能解释事件计数差异，停该 scene，不声称全事件 parity。

上述三个检查证明滤波器与模型记忆可从现存因果记录重建。做不到时，将阻碍、缺字段和已通过的局部检查写入结果；不以不同闭环整段 RMSE 替代同状态 shadow，不提出组件因果结论。

若同状态 shadow 被缺字段或重建误差阻断，最小替代产物为 FEASIBILITY_ONLY：分别验证候选 raw 的既有 GRU trace 与 C5 native raw 的 RBF 输出能否在各自原轨迹上复播，列出不能恢复的 filter/model-memory 字段，并引用现有 task→command→filtered→actual 分解。此替代只报告数据/实现可复现性；不做候选与 C5 动作优劣或闭环因果判断。

### 每条 shadow 轨迹的顺序

- Plant 记录为 1 ms，姿态事件按 raw 的事件 flag 每 10 ms 发生；第一事件按原时序 t=0.01 s，之后保持原 transition schedule，共 1,999 事件。中间 1 ms transitions 持有最近一次更新输出，禁止提前更新或回看下一事件。
- 每个 scene、每条宿主轨迹分别初始化 GRU hidden=0、GRU tracking DeltaW=0；C5 RBF 权重按冻结原始初始化（C5 原合同为零初值）初始化。不得跨 scene 或跨 candidate/C5 轨迹串接 memory。
- 每个事件都从同一宿主 raw state 与同一 causal filter state 计算姿态误差、body rate、nominal BS moment、滑动面与 Euler-rate map。GRU 特征按 error(3), body rate(3), nominal BS torque(3), arm command(4) 的冻结顺序构造。
- GRU 次序：用当前特征与 hidden-before 得 hidden-after；用 q_base 加 DeltaW-before 对应的 tracking output 得 q_raw；按 dmax clip、乘 beta、用固定 J0 形成 torque；然后仅用当前 surface/map/dt 更新 DeltaW，投影到锁定 wmax。下一 1 ms transition 持有该 torque。基模型参数不更新。
- C5 RBF 次序：用当前同状态形成 RBF 输入；先用 W-before 生成并 clip 当前输出、乘相同 beta、经固定 J0 映射 torque；再按冻结 C5 更新律写入 W-after；下一 transition 持有 torque。更新顺序与 native C5 raw replay 对齐。
- 每条轨迹内部，RBF 与 GRU 收到完全相同的 per-event states、filter reference/rate、arms、J0、beta 时钟；只有姿态补偿模型及其自身因果 memory 不同。shadow 不向任何实际 raw 写入，不推进 Plant 或 C5 DSSM。

## 指标与判读

主输出是**事件级条件动作**，按 scene 等权汇总，并分别列 candidate-host 与 C5-host：

- 每事件 q_raw、q_clipped、beta_scaled_residual、J0 torque、sample/event 时间、clip 标记、memory-before/after 摘要；GRU 另报 hidden norm、DeltaW norm/update/projection，C5 RBF 另报 W norm/update/projection。
- 同状态动作差：GRU−C5 RBF 的 roll/pitch/yaw beta-scaled rad/s² 与 N·m signed mean、RMSE、p95、最大值；按 W09…W14、任务 T1/T2/T3、场景和四个 5 s 区间分层。不得把 SO(3) RMSE 当作加法分解。
- 若 raw 中存在经身份验证的 Plant 真值诊断 target，分别报告每个模型动作对该 target 的 signed residual/RMSE；target 不得加入 feature、filter、controller memory 或 state update。
- FULL72 已有真实闭环 task SO(3)、inner SO(3)、Q 只作上下文重列；counterfactual 不传播下一状态，因此不生成 shadow SO(3) 收益、不与已执行闭环 RMSE 混算。

观察预期：若两条宿主轨迹上 GRU 与 RBF 的同状态动作差均小，且已有 candidate/C5 task SO(3) 几乎相同、inner 有改善，则高频任务差更符合 C5 外层命令/滤波路径与 B 位置路径的差异，不能用 GRU 内环动作解释 B 差距。若 GRU 相对 RBF 的动作偏差在两条轨迹重复出现，且对独立日志 target 的残差恶化，则可把后续单因素工作聚焦在姿态动作映射或 tracking head；仍需另行批准闭环干预。若偏差只在一条宿主轨迹出现，记录为 state-distribution interaction，根因未区分。

失败解释：raw/hash 或 event 丢失表示输入身份/完整性失败；滤波重建不通过表示缺少可复现的 causal reference state；GRU/RBF native self-replay 不通过表示模型记忆/输出顺序未能重建；真值 target 缺失表示不能做物理动作精度结论；任何一项失败都不能用候选与 C5 原闭环宏平均差替代同状态因果证据。

## 结果产物与安全边界

拟议离线入口：hf_same_state_shadow_diagnostic_v1.py；仅在本隔离目录创建，仅读 raw/locked JSON/CSV，绝不载入 MATLAB/Plant。此文件目前未创建、未运行。计划产物为 INPUT_LOCK_v1.json、FILTER_REPLAY_CHECK_v1.json、NATIVE_REPLAY_PARITY_v1.json、逐事件压缩 CSV、RESULT_v1.json、短报告；总产物上限 5 GiB，原始 raw 仅按路径引用、不复制。结果写入本隔离目录，不覆盖历史目录。

硬边界：0 新 Plant、0 MATLAB、0 训练/optimizer step、0 TEST 读取；不运行任何 taskbook 命令、不改 production runner/model/config/raw；不自动重试缺失项。C5 status 按现有 audit ledger 原样保留，诊断完成也不晋级为 parent-audited。需要任何闭环验证、补飞或模型变更时，必须另行提交 ROOT 单独审核。

## 源码与证据索引

| 来源 | 行 | 核对摘要 |
|---|---:|---|
| candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m | 81–135 | 强制 C5 delayed prediction、M110、冻结 position model/options 与 identity lock；支持位置 DSSM 不变。 |
| 同上 | 487、1305–1306、2386–2387 | 滤波器按场初始化，并在 1 ms 循环中使用当前 command target 做因果一步更新。 |
| 同上 | 2425–2545 | 100 Hz 事件生成冻结 13 维当前特征，调用 GRU tracking-head；记录 hidden/DeltaW/action，状态输出按事件保持。 |
| 同上 | 2951–2963、3194–3222 | raw 保存 state/reference、filtered reference/rate、command target、R_task 和 GRU trace；明确 RBF output/update 关闭、基模型固定、无变量惯量重建。 |
| experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m | 85–91、1032–1041、378–395 | `formal_rbf_baseline` 固定 controller；Plant 参数不传入 controller RBF 的动态惯量；每场 RBF W 清零，locked opts 可选 override 需 fail-closed 验证。 | 
| 同上 | 2250–2255、2274–2329、3397 | 当前命令 target；一步 causal command filter；RBF 事件输入/输出-before-update、beta×J0 映射与 hold；交错 6D RBF 输入。 | 
| 同上 | 2693–2725、2798–2810 | raw 保存 filtered reference/rate、target、state、arms、event/update/RBF 输出与 audit 记录。 | 
| matlab/core/rbf_mimo_update.m；rbf_mimo_basis.m | update: 13–49；basis: 13–42 | RBF basis 构造；用 W_before 输出和 clip，然后更新并投影 W_after。两文件 SHA 分别 `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a` / `4139c7d08daa5bea6e04702b966ce76cdb6a54ea33d9820cfd9c3a70529248f4`。 |
| matlab/core/command_filter_init.m；command_filter_step.m | init: 7–8；step: 10–24 | 初值 Euler、rate=0；本步输出更新前 reference/rate，随后 rate-first 半隐式更新 Euler。SHA `64fbd68ef652f419066e0546569ba4029bdc00da3eabb0f8019bdc12f66d14a5` / `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b`。 |
| matlab/core/attitude_bs_step.m；controller_parameters.m | BS: 11–55；controller parameters: 27–55、70–77 | 用同状态/滤波参考计算 error/surface/map/nominal torque；fixed 模式基于 nominal arms/base inertia，omit_jdot 为零。SHA `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` / `4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398`。 |
| matlab/runtime/init_dl1018.m；controller_options_dl1018.m | init: 20–25；options: 7–35 | 固定 morphology、1 ms、100 Hz、[Inf,Inf,6] filter contract；P_A 基础 options 打开 formal RBF、没有 attitude initial-weight override 字段。 | 
| C5_DEV72_INPUT_LOCK_v3.json；C5_DEV72_BATCH_STATUS_v3.json | SHA-256 见 v2 身份核验段 | 逐场 C5 reuse/new raw 与 status 身份来源；保留 status，不将 shadow parity 作为审计晋级。 | 
| FULL72_PAIRED_SCORE_v1.json；HF_RAW_INPUT_IDENTITY_v2.csv | score JSON SHA `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff` | FULL72 28-scene filter 与每场 raw/status/audit 路径、SHA；CSV 记录 56 个 raw 的实际路径和 SHA。 |
| candidate_runner_work/matlab/runtime/gru_stream_tracking_head_step_v1.m | 4–14、16–47、53–70 | 每场零 hidden/DeltaW；用因果当前 feature 与 hidden 更新，q 使用当前 GRU hidden 与 DeltaW-before；clip/beta/J0 后才更新 DeltaW。 |
| LOCKED_CFG.json | 14–31、67–98、103–106、119–135 | 固定 J0/Jdot0、dmax、beta、command filter、C5 DSSM14 SHA 与 tracking-head 更新/投影参数。 |
| audits/score_full72_candidate_v1.py | 39、141–142、526–527 | task SO(3) 以 external task attitude 评分；inner SO(3) 以 filtered_attitude_reference 评分，两者不可互换。 |
| audits/audit_gru_stream_tracking_head_raw.m；RELEASE.json | auditor SHA-256 70d6d3fdc3dc223d9cfb6bfd98971b67c53e0041c2a124bf414b0d27afd81e80 | 可复用既有 GRU/DeltaW、output-before-update、held torque 与模型 SHA raw 审计身份；本诊断不运行 MATLAB auditor。 |
| C5_DEV72_INPUT_LOCK_v3.json；C5_DEV72_BATCH_STATUS_v3.json | SHA-256 82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75；20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22 | C5 raw 路径/SHA/status 身份来源；维持其 raw-pending-audit 原状态。 |
| audits/FULL72_PAIRED_SCORE_v1.md、FULL72_PAIRED_SCORE_v1.json | JSON SHA-256 d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff | 当前候选/B/C5 72 场配对宏指标、门槛和 C5 审计限定；只作结果来源。 |
| reports/attitude_replacement_progress_20261027/ROOT_B_C5_DEV72_TASK_AND_INNER_RECHECK_v1.json | 独立复算记录 | C5 相对 B 的 DEV72 task/inner 分口径结果；HF task SO(3) 退化 7.26%、2/28 胜。 |
| attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/HF_W09_W14_attitude_path_diagnosis.md | 独立诊断脚本 SHA-256 e04c4bb9f867149c4230a98ad22c2c5b9c77023167a3725caa8d552f98c049b2 | 28 场 task→command→filtered→actual 已有分解，确认 inner 与 task 口径差异。 |
| reports/attitude_cm18_a1_20261024/root_screen12_metrics_v1.py | 8、20–22 | CM18-A1 旧 SO3 评分取 filtered_attitude_reference；依 raw_path/hash 配对 C5。 |
| reports/attitude_cm18_a1_20261024/ROOT_SCREEN12_PAIRED_METRICS_v1.json；SCREEN12_COMPLETE_PAIRED_TABLE_v1.csv | 12 scene、aggregate 与 scene rows | A1旧结果均为 filtered-reference SO(3)，当前候选 raw MAT 缺失；此结果不用于 task SO(3) 因果判断。 |



## v2 的 fail-closed 说明

本次只验证了路径/SHA/status 和 MATLAB v7.3 HDF5 字段存在性，未验证 raw 数组逐元素可用、filter parity、RBF/GRU native parity 或所有事件的值级闭环因果时序。`C5_reuse` 表示输入锁的路径归属；`PASS_C5_RAW_ALL_EVENTS` 表示 score 引用的旧 screen audit；`RUN_COMPLETE_RAW_PENDING_AUDIT` 是原 run_status。三者分别记录，任一历史状态不因本诊断改变。C5 旧 screen lock 的 1968 event-audit 数与原始 per-step event flag 的预期 1999 事件必须在进入该场 cross-model shadow 前解释，否则该场 STOP。所有失败场景只可报告 FEASIBILITY_ONLY/数据不足，不用不同闭环 RMSE 替代同状态对照。
