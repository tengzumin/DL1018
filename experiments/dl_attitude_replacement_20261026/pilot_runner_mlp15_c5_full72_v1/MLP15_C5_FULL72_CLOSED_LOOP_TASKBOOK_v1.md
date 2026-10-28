# MLP15 C5 full72 姿态替代闭环筛查任务书 v1

状态：root 已审核静态身份、MATLAB Code Analyzer 与 G1/W00 no-Plant 准备，并仅授权 G1/W00 一次工程门航次。其余五场仍待首场结果审核后另行放行。训练源锁只批准过一次 full72 训练，不包含 Plant/闭环航次授权。

## 冻结模型与在线接口

使用 `mlp15_c5_teacher_full72_v1/runs/C5_MLP15_FULL72_SEED2026102001/` 中唯一的 `mlp15_attitude_weights_v1.mat`，并绑定该 run 的 config、progress、receipt、`final_step_60000.pt`、parity 报告和已批准训练 source lock。训练为 C5-RBF 教师全量开发重训；只用 final step 60000，不存在 checkpoint 选择或在线权重更新。

MLP 输入是历史因果 15-event 窗口，每个事件严格 13 维，顺序为 wrapped 姿态误差 3、机体系角速度 3、名义 BS 力矩 3、归一化变形命令 4。姿态误差按 `atan2(sin(reference − Euler), cos(reference − Euler))` 在每个姿态事件生成。禁止 `Jhat/Jdot_hat`、惯量/质量属性、Plant 真值、RBF 权重/隐状态、observer 和 physical feedforward。在线仍用固定 J0 作残差力矩映射，不重建时变惯量。姿态 RBF 输出和更新关闭；MLP 冻结。

位置栈保持原已锁定的 C5 DSSM14/M110，位置头、BS 名义姿态环、Plant、allocator、执行器和其他共同控制配置不变。评估对象是完整 B→位置控制→姿态 MLP→Plant 系统的闭环结果，不能用单独离线 MLP 指标代替。

## 六场与基线复用

场景固定为 GHP7 G1/G2/G3 × W00/W12 的六个 ACTIVE payload。配对 B 与 C5_RBF raw 只复用 `GHP7_BASELINE_REUSE_MANIFEST_v1.json` 中已锁定的12条历史记录；raw、payload 和基线不复制、不覆盖、不重跑。输出目标为 `pilot_runs_mlp15_c5_full72_v1` 和后续独立 scorer 目录。

首个候选只允许 G1/W00，作为工程门。当前 release 为 pending、Plant call 数 0。root 首次放行后只可跑 G1/W00 一次；完成后先复核该航次。其余 G1/W12、G2/W00、G2/W12、G3/W00、G3/W12 必须由 root 在首场审核后另行扩展 release。总候选 Plant 航次预算最多 6；已写 started marker 的失败也计入预算并保留。TEST 数据保持封存。

必须保留并披露历史基线例外：C5_RBF G1/W00 有 logger completion-flag mismatch；独立 scorer 记录 20,000 个 transitions、20,001 个 states、有限数据且 raw hash 已核验，原记录不可改写。B 与 C5_RBF 的 G2/W00、B 的 G2/W12 `application_feasible=false`。不得删场、过滤异常基线、用 feasible 子集替代六场比较；逐场报告完成标志、可行性和原始指标。

## 筛查门与结论范围

对同一场、同一 payload、同一 `R_task` 的候选、B、C5_RBF raw 做逐场比较，并给出 W00、W12 风组和六场等权宏平均：

- 位置 Q 宏平均严格优于 B；相对 C5_RBF 的位置 Q 退化不超过 10%，即 `Q_MLP15 ≤ 1.10 × Q_C5_RBF`。
- SO(3) 姿态 RMSE 宏平均严格优于 B 与 C5_RBF。
- 逐场披露 completed/stable、安全停止、motor saturation、generalized clip、tilt limit、application-feasible 和 completion-flag consistency；保留所有六场和未舍入原始值。
- 六场只作小样本方向/工程筛查，不外推泛化、实机安全或论文结论。全六场完整且筛查门通过后，才可另行讨论 DEV72；本任务书不授权晋升。

## 审核门与当前授权

本目录只隔离复制 C5-24 runner，52 个 MATLAB 文件中仅 `prepare_gate_candidate_no_plant.m` 与 `run_mlp15_candidate_gate_attempt.m` 为 full72 绑定改动，其余50个文件保持原字节。PowerShell 7 静态 preflight、MATLAB Code Analyzer、G1/W00 MATLAB no-Plant scene preparation 和主审代码检查均已完成；每份报告哈希绑定在 pilot release 中。静态 preflight 本身不授权闭环。

不读 TEST、不再训练、不重跑 B/C5。pilot release 初始状态为 `PREPARED_PENDING_ROOT_APPROVAL` 且 `plant_calls_authorized=0`。主审完成输入合法性和身份复核后，可将 release 改为 `RELEASED`，只授权 G1/W00 一次工程门航次。该次航次后必须先审 raw、状态、安全和指标；其余五场不在本次授权内。
