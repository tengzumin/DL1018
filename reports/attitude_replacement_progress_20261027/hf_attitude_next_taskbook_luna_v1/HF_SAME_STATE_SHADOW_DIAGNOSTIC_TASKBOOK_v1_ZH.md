# 高频姿态替换：同状态 shadow 诊断任务书 v1

状态：只读诊断草案，待 ROOT 审核。此文件不授权运行；本次仅核对既有报告与实现，没有执行 shadow、训练、MATLAB、Plant 或 TEST 访问。

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

2. **Raw：**候选 raw 从 gru_stream_cosine_tracking_head_full72_v1/runs/<scene>/raw_run.mat 读取；若 FULL72 行为 reuse reference，按其锁定的原始候选 raw 路径读取，不复制或重跑。C5 raw 从 position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/<scene>/C5_AXIS_MASK_M110/attempt_01/raw_run.mat 读取。只读已绑定的 28 对 DEV/VAL raw；不扫描或打开 TEST 路径。

3. **Raw 与状态身份：**逐文件核对 FULL72_PAIRED_SCORE_v1.csv 中的 raw SHA，以及对应 candidate reuse/audit 身份；C5 对照核对 C5_DEV72_INPUT_LOCK_v3.json、C5_DEV72_BATCH_STATUS_v3.json 和 paired score 中的路径、SHA、status。候选新跑审计为 PASS；六条候选复用项沿用原审计引用。C5 DEV72 中 60/72 status 仍为 RUN_COMPLETE_RAW_PENDING_AUDIT；本诊断保留每条原 status，不升级审计等级。任何 path/hash/status 不一致即停止该场。

4. **模型与配置：**固定 GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001，模型 SHA-256 b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567；训练配置 SHA-256 b85b9b545eba1939582b4e8909667338bfbff1e81dc4cfb295ec750c0a57739d。不训练、不重选 checkpoint。C5 位置模型为 DSSM14，SHA-256 6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e；位置选项、M110 与 DSSM 身份保持输入锁定值。固定 J0 SHA-256 8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75，Jdot0=0，attitude dmax=[45,45,4.7124] rad/s²，beta rise time=2.2 s。命令滤波 wn=[18,18,12]、damping=[1,1,1]、加速度限幅=[Inf,Inf,6]。

5. **禁止输入：**不得输入 Jhat、Jdot_hat、真实可变惯量/质量、Plant truth、未来状态、未来参考、未来动作、未来滤波输出或 RBF/GRU 未来内部状态。原始 Plant 真值如有，可作为独立诊断 target 列；必须与输入矩阵隔离并标注字段来源。不得用惯量反演补造 target。

## 执行定义：两条轨迹、每条轨迹两种姿态模块

诊断单元为 scene × state trajectory。每场有两条已记录轨迹：candidate state trajectory 与 C5 state trajectory。每条轨迹上分别做 GRU tracking-head 和 C5 RBF 两次 shadow replay；同一轨迹内两种方法必须逐样本使用完全相同的 state、arms、filtered attitude reference/rate、固定名义 BS 控制量及历史。共 28 场 × 2 条轨迹 × 2 个姿态模块。候选与 C5 两条真实闭环轨迹彼此不同；不得将两轨迹间的 RMSE 差称为同状态对照。

### 先过重建可行性门

1. **因果滤波重建：**从 raw 的 initial_state 欧拉角初始化 command_filter_init；按原 1 ms transition_time 顺序，只将当下/过去的 command_filter_target_euler 送入锁定滤波器，重建 filtered_attitude_reference 与 filtered_attitude_rate。重建只允许 causal step，不得一次性零相位滤波、使用未来 target 或事后平滑。逐点与 raw 记录比较，误差限为 attitude 1e-10 rad、rate 1e-8 rad/s；首点、事件边界、末点都纳入。任一条轨迹不通过则该 scene 不做跨模块比较。

2. **GRU 原轨迹自复播：**复用 gru_stream_cosine_tracking_head_full72_v1/audits/audit_gru_stream_tracking_head_raw.m 已通过的模型/事件复播结果，不运行 MATLAB 审计器。按锁定模型 SHA 和该 raw 的 gru_stream_attitude_trace 校验；须确认 1,999 个事件、hidden 和 DeltaW 状态链完整，actual_event_dt 与 sample_index/time 对应，输出与 torque closure 通过。

3. **C5 RBF 原轨迹自复播：**从每场开始的 C5 RBF 锁定初值重放 1,999 个 attitude event，复算当前误差/滑动面/基函数与 nominal BS 量。先在 C5 native state trajectory 上对齐 raw 的 rbf_output_raw、event flag、output-before-update 状态更新和保持 torque；逐事件最大差须小于 1e-9 rad/s²，torque 小于 1e-10 N·m。不能匹配时，停止该 scene 的跨模块 replay，不猜测 RBF 内部状态。

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
| experiments/position_axis_coordinate_c5_20261023/run_dl1018_closed_loop.m | 2312–2422、2724–2808 | C5 native 姿态 RBF 的当前事件输出/更新和 raw log 字段；用于固定代码路径与 C5 自轨迹 parity。 |
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

