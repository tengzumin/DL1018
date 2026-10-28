# Root 审核：MLP15 C5 教师 GHP7 覆盖离线训练

日期：2026-10-26（Asia/Shanghai）  
决定：**批准一次离线训练**。当前 release 不授权 MATLAB/Plant、闭环航次、B/C5 重跑或 TEST。

## 审核结论

- 任务书预先固定唯一改变因素：把 GHP7 G1/G2 的 C5 教师轨迹加入训练分布，并固定每批 256/256 的基集与目标域采样。网络、特征、损失、优化器、种子和 60,000 步保持 MLP15 full72 配置。
- 提取脚本逐项核验 `GHP7_BASELINE_REUSE_MANIFEST_v1.json` 及六场 C5 raw SHA、同场 run_status 绑定、STABLE 状态、20,000 transitions、20,001 states 和 1,999 事件；G3 的两个数组单独封存，训练器只接收 G1/G2 包。
- 特征从同一事件的姿态误差、机体系角速度、BS nominal torque 和形态命令重建；共 13 维。监督目标是同一事件日志 `rbf_output_raw`，单位 rad/s²，post-dmax/pre-beta。没有惯量重建、Plant truth、RBF 内部状态、observer 或物理前馈输入。
- 新训练预检成功加载 72 场 C5 原有数组与 G1/G2 四场包，合并形状为 `(76,1999,13)` / `(76,1999,3)`；MLP15 输入窗口形状和输出维度检查通过。预检没有打开 G3 包。
- 原始边界问题保留披露：G1/W00 logger 的 `complete_transitions=false`，但状态记录为 COMPLETED/STABLE 且实际 20,000/20,001，独立计分完整；G2/W00 的原始 C5 记录 `application_feasible=false`，只用于离线监督诊断。
- 当前 checkout `matlab/core/default_config.m` 仍给 `max_tilt=pi/6` 与姿态残差 `dmax=[45,45,4.7124]`；配对任务继续沿用 C5 快照和用户刚确认的两项现有值。此训练不改限幅。
- 现有 6 场 GRU15 闭环筛查显示 dmax 未触发；30° 倾角投影仅在 G2/W00 触发。B/C5 配对 raw 继续复用，未重跑；本次没有运行 Plant。

## 固定 release

- 一次 MLP15 训练；seed `2026102001`；Adam `lr=1e-3, weight_decay=1e-5`；batch 512；SmoothL1 beta 1；60,000 步；最终 step only。
- 数据每批 256 个样本来自既有 C5 72 场，256 个来自新增 GHP7 G1/G2 四场。归一化按相同算法在 76 场混合训练集上拟合。
- G3/W00、G3/W12 在训练完成前不得打开；训练完成后只作本任务书所定义的离线开发诊断，不可称独立验证。
- 训练输入、代码、任务书、基模型数据、GHP7 数据包及相关模型 helper 均以 `MLP15_C5_GHP7_BALANCE_SOURCE_LOCK_v1.json` 中 SHA-256 为准。固定输出目录存在即拒绝第二次训练。

**审批记录**：`APPROVED_FOR_OFFLINE_TRAINING`；一个 job；审批人 Codex primary reviewer；依据 `ROOT_REVIEW_C5_GHP7_BALANCED_OFFLINE_20261026`。
