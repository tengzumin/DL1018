# 姿态补偿重设计：低维输入与离线可重建性审查

**状态：** 只读设计审查草稿；没有冻结特征或模型。没有读取 TEST 原始数据或 TEST 成绩；没有改控制器、训练模型、运行 MATLAB 或启动 Plant。C5 位置环证据继续冻结，C7 继续暂停。

## 结论先行

一个可以检验、但尚未批准的紧凑工作假设，是每个姿态学习事件使用 11 个当前量：

| 信号 | 维数 | 单位与来源 |
|---|---:|---|
| 机体系角速度 omega_B | 3 | rad/s；state 第 10–12 项 |
| 补偿前 BS 名义机体系角加速度 alpha_BS | 3 | rad/s²；由当前状态和滤波参考经 attitude_bs_step 计算 |
| 请求总推力除以质量 | 1 | m/s²；requested_generalized 第 1 项 / mass |
| 已发变形命令 | 4 | 无量纲归一化速率命令；场景 command，不是臂长或真实构型 |

这 11 个量是当前事件采样，**不是全部因果上下文**。为表示动作依赖，另把上一个完整 10 ms 事件区间的请求力矩均值（3 个 N·m）和形变命令均值（4 个无量纲值）作为显式的滞后上下文；若以递归状态保存，也必须把它们记为额外的 7 个输入信号。因而显式输入总数是 18 个标量/事件，而不是把历史藏起来后仍称 11 维。历史编码长度和模型结构暂不指定。

该假设刻意不直接加入真实臂长、真实惯量、真风或当步请求力矩，也不声称对瞬时残差充分。两种不同构型可能有相同的零形变命令，隐藏风也会令相同输入对应不同残差。短记忆最多利用命令和动作的时间相关性，不能保证恢复未知构型或突发风。

## 与 C5 位置环的关系

C5 位置数据源按事件构造 14 个输入：位置误差 3、位置误差面 3、Euler 姿态 3、请求推力/质量 1、四路形变命令 4；输入冻结的 DSSM14 模型前组成 14×32 事件窗。位置标签是 Plant 实际加速度减去“名义加速度减已施加补偿”的加速度，单位 m/s²。可复用的设计经验是：以部署可得量和因果历史预测物理残差，把命令和总推力显式呈现，并让归一化只由训练集确定。位置环的 PCF、误差面、学习符号和加速度标签不应照搬到姿态环。

C5 合同固定的是 DSSM14 位置候选；推理代码在本仓库的 position_stage1_model_forward_v2.m。DSSM14 的训练协议和模型来源位于外部冻结目录 REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_training/protocol.json。该协议记录 1536 个训练 episode、96 个验证 episode、32 事件窗、步长 5、单模型固定 60,000 次 Adam 更新和训练集归一化。当前仓库 training/models.py 只实现 KAN14/KAN29；不应把它描述为 C5 DSSM 的训练实现，也不能因此声称新姿态方案必须采用 DSSM 或 32 窗。

## 姿态目标、量纲与因果顺序

现有 BS 使用 ZYX Euler 跟踪误差，但把名义 Euler 角加速度经 T⁻¹(alpha_eta−Tdot·omega) 转为机体系角加速度。候选模型输出也应定义在机体系，单位 rad/s²；若按现有力矩接口补偿，则由固定名义 J0 映射为 tau_comp = beta·J0·clip(d_hat)，单位 N·m。不要把 Euler 轴误差与机体系角加速度直接混成同一向量。

既有 exporter 对事件时刻 k 的监督量定义为

d_k = omegaDot_true,k − J0⁻¹(tau_req,k − omega_k × (J0 omega_k) − Jdot0 omega_k),

其中 C5 固定名义控制器的 Jdot0 为零。真实角加速度由 Plant、实际分配/执行输入、真惯量及其变化和风力矩重建。这个标签是**给定旧控制策略和该策略请求动作的残差**，不是与补偿动作无关的外生风扰。新预测器不能把当前 tau_req 或由当前预测决定的电机命令放入同一步输入；它可用当前补偿前名义量和已完成动作的历史。模型在事件开始时先输出，再转换为补偿力矩；之后 BS 仍每 1 ms 计算请求，补偿力矩按现有事件机制保持到下一次更新。用旧策略标签训练后换补偿器会改变动作分布，因此必须把这种偏移作为模型限制和后续闭环验证目标。

标签保持现有事件时刻的瞬时定义，才与现有 H5 target_raw 对齐。由 10 ms 角速度差构造的区间平均加速度是另一种目标；不能与瞬时标签仅因单位相同而互换。若未来评估区间平均目标，须单独定义积分区间、时间权重、输出保持顺序和标签资格。

## 时序与可重建性

主循环的 Plant/控制步长为 1 ms，姿态模型事件按 100 Hz 采样；既有姿态事件 H5 每场有 1,999 个事件。root 的只读原始日志时序核查记录了 1,998 个完整相邻事件区间内请求力矩均有变化，而补偿力矩在区间内保持不变。请求力矩逐毫秒重算，所以单个事件时刻的请求样本不能冒充完整 10 ms 已执行动作。若输入用已完成动作，应从全部 1 ms 记录算区间均值或保留明确的逐步历史，并在事件边界以后使用。

候选 11 量可由当前全分辨率日志与配置重建：状态给出 omega；滤波参考、BS 参数和状态可重放名义 alpha_BS；requested_generalized 与 mass 给出总推力/质量；scene/log 的 arms.command 给出形变命令。现有 attitude exporter 只把 100 Hz 事件行、X29 和瞬时 target_raw 写入事件表；仅有事件 H5 不足以重建事件间请求力矩变化或已完成区间均值。必须有匹配的逐毫秒 raw、run_start/config 与场景命令记录，且身份绑定合格，才能进行该输入/动作重建。

在当前场景生成器中，arm command 是命令速率的无量纲归一化值（伸展/停止/回缩），不是 rho。command 为零可能表示初始臂长仍为 0.15 m，也可能表示已伸展后的保持阶段。因此，仅看当前 command 无法唯一确定真实构型；真 rho/rhoDot 仅可作离线标签与核验，不能作为学习器输入。命令历史在已知初值、理想执行假设下或许能近似推断构型，但不能据此声称部署可辨识。未观测风力矩同样构成不可消除的条件不确定性。

现有两个被独立抽查的 C00 TRAIN/VAL 样本通过了各自的事件对齐与标签回放，但均为静态臂、近零目标，不能证明非零变形残差训练信息。更多 TRAIN/VAL 文件的完整身份、动态构型监督和 raw 覆盖由独立数据资格审查继续核验；这里不重复读取事件元数据全集或任何 TEST 文件。参考 reports/attitude_redesign_20261024/data_qualification_minimal_v1.md、independent_physics_review_v1.md 和 ROOT_TRAIN_TIMING_DIAGNOSTIC_v1_ZH.md。

## 下一步只做可区分输入贡献的数据审查

在任何训练或 Plant 之前，先确认合格 TRAIN/VAL raw 是否足以逐毫秒重建 11 个当前量、7 个已完成动作上下文、瞬时 d_k 和事件时刻。至少须有一例非零形变及一例非忽略风力矩；静态 C00 样本不够。

身份与标签合格后，才在 TRAIN 拟合一个固定的离线估计器，并在 episode 级隔离的 VAL 上比较预先固定的输入组：11 个当前量；加入 7 个动作上下文；再按预先定义移除 command 或请求动作历史。所有对照须使用同一估计器、训练预算和事件标签，不从 VAL 选择结构或窗口长度。按轴、形变阶段、命令组和风组报告预测误差及残差范围。该离线实验只能说明现有行为数据中的条件预测信息，不能证明替换后闭环改善。

之后若获准做 DEV 闭环比较，只替换姿态残差器，固定 C5 位置环、BS、滤波器、分配器、Plant、场景/初态和事件频率；保留同一 J0、beta/限幅及补偿符号。原 RBF 是比较基线，不能借用或改写其参数来适配新候选。TEST 不参与特征或模型选择。

## 早期草案状态

先前 19 维方案已被否决，原因和边界见 ROOT_DESIGN_DECISION_v1_ZH.md；它没有实施。旧 A_KAN29 接入材料已单独标记为 superseded。本文没有选择网络、窗口长度、训练配置或闭环验收门，也没有任何新性能结论。## 本次核对的源码与协议身份

以下 SHA256 固定了本审查直接核对的主要本地代码及冻结训练协议；其余独立审查材料按上文路径引用，不在此重复其结论。

| 文件 | SHA256 |
|---|---|
| experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json | 6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150 |
| experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m | 48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c |
| matlab/models/position_stage1_model_forward_v2.m | 8db5a691dc1961e13956c1d6e76cdea346142e0cc04788ba17f39c72d4a122ee |
| matlab/data/stage1_events_source.m | 1bcfb55bdd7eefb2a4dd9610be08e56ac6ffbe1e00c45e02616bace5da2d4a48 |
| matlab/data/export_position_events_dl1018.m | 4506849cc2c888e078129772e6bb1927cb479f02b75c072778ed32d4cf094 |
| training/models.py | cbe307606f58a9f551a870037d1d94517d7842abe574abf69aee2f8ba4b1ceba |
| matlab/core/attitude_bs_step.m | cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc |
| matlab/data/attitude_feature_row_v3_6.m | ed65a4fa52321aace622549bb4f444410264f53fc753f12fd49e6acd02415616 |
| matlab/data/attitude_events_source_v311.m | a97bc8585e916e7fc78651200eaf2ae04e4a90ce575865ce5fa7989f52f94792 |
| matlab/data/export_attitude_events_dl1018.m | baeca25a27ee411e900d38333c888a91aa7ce2c5a17ad58cc6989f7aea684141 |
| matlab/core/tcn0916_morphology_scenario.m | 711a87e01e616ee141f9068a8c4e31758dc328ade3f692e1a92a5de723d30438 |
| matlab/core/default_config.m | 685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51 |
| REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_training/protocol.json | 28e63d588f1e693140a04f3bbcedc9f608cda74306e310ce5baee9e21961feba6 |
