# MLP15 姿态替代候选：探索性 DEV72 闭环任务书 v2

日期：2026-10-26。v2 纠正 v1 预检发现的场景接口差异。v1 预检在 Plant 前失败且未消耗航次；v1 的 payload、manifest、源码与错误记录保留。新的 72 场阶段仍是原 GHP7 六场 pilot 判 FAIL 后新增的探索性开发，不把原 pilot 改写为通过。

## 1. 候选、场景和对照

- 候选为冻结 DL_MLP15，best step 59,000；13 个因果输入、15 个事件窗口、监督目标为 B 日志姿态 RBF 原始输出。位置环为 C5 DSSM14/M110，位置头保持原在线更新。姿态 RBF 输出/更新关闭，BS 名义姿态环、Plant、allocator、执行器、固定 J0 与输出边界不变。
- 控制器不读取/计算形态依赖 Jhat/Jdot_hat、Plant 真值 `rho_true/rhoDot_true`、Plant 真值力矩、RBF 隐状态；无 disturbance observer、无 physics feedforward。
- DEV72 正好采用 C5 输入锁 v3 的 24 DEV + 48 VAL 场景。每个场景使用同一锁定 B72 raw 中的 `scene` 变量；仅在内存中添加 `reference_contract_id='DL1018_SCENE_REF_FIG8_A2_V2'` 标签，供冻结闭环入口检查接口。该标签不改 reference、initial state、arm schedule、wind 或任何 Plant 物理数组。
- 原 GHP7 六场 payload 与 B72 cohort 不同，不能代替 72 场；这 72 场各新增一次 MLP15 candidate 航次。
- B 对照完全复用 C5 lock v3 引用的 `B_TRACEABLE_C3CORE_V1` raw/status，不重跑 B/C5_RBF。只对严格匹配的 C5_RBF raw 做次级比较；缺少匹配时标缺失。
- TEST48 不读取、不解封、不运行。

## 2. v1 预检失败说明

v1 错把 GHP7 专用 `gate_holdout_validate_scene` 当成通用 DEV72 validator。该检查要求 GHP7 的 `reference_contract_id`、专用姿态参考/arm schedule，拒绝了真实 DEV72 B scene。失败发生在 Plant 前，消耗 Plant calls=0。v2 改用 DEV72 专用输入身份验证；只接受 C5 lock v3 的 72 个 scene IDs、72 个 B raw/status SHA 与 external identity，不将 GHP7 与 DEV 场景混为一谈。

## 3. 冻结评估门

- 72/72 candidate 与 B 场景、reference、wind、arm schedule、seed 通过锁定身份验证；raw/status SHA、20,000 transitions、稳定状态复核。
- Candidate finite 且完整；无 safety stop、电机饱和或 generalized clipping。
- 共用 `baseline_force_to_attitude` 的 tilt projection 单独统计；每场 candidate 投影次数不得高于同场 B。完整报告次数和时长；此条件不等于零 tilt 或闭环安全证明。
- 72 场等权位置 Q(0–20 s) 与 SO(3) RMSE 均严格优于 B；位置至少 62/72 场胜 B；姿态逐场胜数完整报告。
- W09–W14 高频组与 W15 无风组的 Q、SO(3) 均值均不劣于 B。
- GHP7 六场不与 DEV72 合并计算。C5_RBF 仅作次级参照。若门失败，TEST 继续封存。

## 4. 执行边界

- 新 source tree、release、attempt markers、run starts、raw、status、审计和图只写入 `mlp15_dev72_v2/`。v1、pilot v2、B72/C5 历史数据只读。
- 72 B raw/status 与场景 payload 的 identity/hash 先在 no-Plant 阶段完整验证。无 Plant 检查、MATLAB Code Analyzer、closed-loop smoke 与 source-lock 审核通过后，最多新增 72 个 candidate Plant calls；无训练、调参、架构搜索、补跑对照或 TEST。
- 首个 DEV 场景做一次工程核验；其 raw 经独立复算、输入 trace/姿态补偿路径/安全日志检查通过后，继续剩余 71 场。任何接口或身份异常立即停；保留状态与 marker，不覆盖 attempt。
- 每次启动前检查无其他 MATLAB/Plant 重负载运行；不打断正在运行的实验。仅用 PowerShell 7 启动。
- 磁盘余量低于 30 GiB 时停止启动新航次，不自动删除数据。

## 5. 交付

提供完整配对表、各任务/风组/XYZ/早晚阶段/峰值指标、tilt projection 与安全/执行器计数、控制耗时、逐场 raw/status hashes、所有失败及重试记录。统计不把单航次时间点当独立样本，不宣称跨训练种子、实机或任意轨迹泛化。此阶段是基于 pilot 观察新增的探索性 DEV，不是 TEST 或确认性论文证据。
