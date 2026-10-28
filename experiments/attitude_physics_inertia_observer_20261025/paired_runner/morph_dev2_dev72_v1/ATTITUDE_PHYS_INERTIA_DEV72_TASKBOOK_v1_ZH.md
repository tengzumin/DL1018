# 姿态 RBF 替代：补齐固定 DEV72 配对验证任务书 v1

日期：2026-10-25。阶段范围：使用冻结 C5 位置栈，比较原 B online attitude RBF 与冻结物理惯量/observer 替代。此任务书只放行 58 个未配对 DEV 场景；12 个 screen12 配对及两个既有 DEV 配对按下文复用。TEST48 仍封存。

## 依据与阶段门

Screen12 已由独立 raw 复算器逐臂核验 24 个 raw SHA、完整 20,000 transitions、场景与 C5 同栈身份、candidate 因果 trace、位置/姿态误差与安全计数。审计摘要 SHA-256：`4d1b106fc680ef4b349fecb96bf92851d145445bdf9f63e020ca538bd18b8ce2`。Screen12 candidate−C5+原 B 姿态 RBF 的 macro Q 为 −0.0011481427915635087 m，SO(3) 为 −0.0054252912336536004 rad；W09–W14 SO(3) 差 −0.0050029600522005961 rad；W15 差 −0.0084837023583066874 rad。独立加载这 12 场对应的 B72 raw 后，candidate−B 的 Q 为 −0.0024416233575749939 m、SO(3) 为 −0.0053871645363634006 rad；高频 6 场分别为 −0.00133838575853247 m、−0.00493261279791757 rad，无风 3 场分别为 −0.00365929341373411 m、−0.00848577828272772 rad。Q 赢 10/12，SO(3) 赢 9/12；pilot 的宏观两项及目标风组均通过，详见 `review/SCREEN12_CANDIDATE_VS_B_RAW.json`。该 12 场仍是开发筛查，不是最终证据。原 runner 因 post-run CSV 导出 `csv_metric` 漏参而保留 STOPPED 状态；24 raw/12 pair audit 完整，独立复算保留原状态与 raw。

冻结来源：C5 DEV72 input lock v3 SHA-256 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`；screen12 source lock SHA-256 `8ed83584545f38224899982e6e5dfd6faf26f640efde2d9cf396191cc262a24b`。场景取 C5 锁内 `scene_ids_all_72` 原序，减去 screen12 固定 12 场和既有 DEV 复用对 `DL1018_DEV_T2_C02_W15`、`DL1018_DEV_T3_C10_W11`，严格得到 58 场。完整 ID 列表见下方；不得排序、重选或扩到 TEST。

## 固定比较

- **主基准 B**：`B_TRACEABLE_C3CORE_V1` 原始 B，位置与姿态在线 RBF 均开启。C5 DEV72 lock 为每个 DEV/VAL 场景锁定一个 B72 raw、状态文件和 SHA；72 个 B 日志均为 20,000 transitions、`log_status=STABLE`，每场 1 次 Plant 调用。冻结 runner 以 `controller_options_dl1018(cfg,'B')` 重建选项，并断言原始位置/姿态 RBF 开启、没有 C3/C5 候选输入。
- **Candidate**：C5 DSSM14/M110 位置栈（冻结 encoder、normalizer、初始 W0；位置 33×3 头按原算法在线更新）+ 关闭姿态 RBF 输出/更新，并启用 `phys_attitude_replacement_candidate_v2.m` 的解析惯量前馈与有界 disturbance observer。
- 屏幕 12 场中的 `C5 + 原 B 姿态 RBF` 仅作为机制控制；candidate 对 C5 的位置回退允许存在，不作主验收门。主结论必须以每个同场 B72 raw 为基准，同时比较位置 Q 与姿态 SO(3)。
- Candidate 参数、输入和源代码完全继承 screen12 frozen lock；不训练、不调参数、不加输入、不改 J0/Plant/allocator/滤波/限幅。
- 已有 screen12 的 12 个 candidate raw 与两场已审 DEV candidate raw 复用，不重跑；屏幕控制臂 raw 只用于诊断。新跑剩余 58 场，每场只运行 candidate 1 次，1 ms、20 s、20,000 transitions；同场 B 直接复用锁定的 B72 raw。

## 58 场 ID（原 C5 DEV72 锁内顺序）

`DL1018_DEV_T1_C00_W03, DL1018_DEV_T1_C01_W15, DL1018_DEV_T1_C04_W00, DL1018_DEV_T1_C05_W06, DL1018_DEV_T1_C07_W08, DL1018_DEV_T1_C10_W09, DL1018_DEV_T1_C11_W12, DL1018_DEV_T1_C15_W14, DL1018_DEV_T2_C00_W04, DL1018_DEV_T2_C03_W01, DL1018_DEV_T2_C06_W07, DL1018_DEV_T2_C08_W08, DL1018_DEV_T2_C09_W10, DL1018_DEV_T2_C12_W13, DL1018_DEV_T2_C14_W14, DL1018_DEV_T3_C00_W05, DL1018_DEV_T3_C03_W15, DL1018_DEV_T3_C05_W02, DL1018_DEV_T3_C06_W08, DL1018_DEV_T3_C09_W09, DL1018_DEV_T3_C13_W12, DL1018_DEV_T3_C15_W14, DL1018_VAL_T1_C01_W08, DL1018_VAL_T1_C03_W10, DL1018_VAL_T1_C04_W11, DL1018_VAL_T1_C06_W13, DL1018_VAL_T1_C07_W14, DL1018_VAL_T1_C09_W00, DL1018_VAL_T1_C10_W01, DL1018_VAL_T1_C11_W02, DL1018_VAL_T1_C12_W03, DL1018_VAL_T1_C13_W04, DL1018_VAL_T1_C14_W05, DL1018_VAL_T1_C15_W06, DL1018_VAL_T2_C01_W11, DL1018_VAL_T2_C03_W13, DL1018_VAL_T2_C04_W14, DL1018_VAL_T2_C07_W01, DL1018_VAL_T2_C08_W02, DL1018_VAL_T2_C09_W03, DL1018_VAL_T2_C10_W04, DL1018_VAL_T2_C11_W05, DL1018_VAL_T2_C12_W06, DL1018_VAL_T2_C13_W07, DL1018_VAL_T2_C14_W08, DL1018_VAL_T2_C15_W09, DL1018_VAL_T3_C01_W14, DL1018_VAL_T3_C04_W01, DL1018_VAL_T3_C05_W02, DL1018_VAL_T3_C06_W03, DL1018_VAL_T3_C07_W04, DL1018_VAL_T3_C08_W05, DL1018_VAL_T3_C09_W06, DL1018_VAL_T3_C10_W07, DL1018_VAL_T3_C11_W08, DL1018_VAL_T3_C13_W10, DL1018_VAL_T3_C14_W11, DL1018_VAL_T3_C15_W12`

## 预注册比较与门槛

主指标为 0–20 s 位置三维 RMSE Q；姿态为相对滤波目标的 SO(3) geodesic RMSE。所有值未舍入，按同场 candidate−B 做配对。将 58 个新 candidate 与已审核的 14 个 candidate 复用，和锁定的 72 份 B raw 组成 DEV72；逐场及 HELIX/FIG8_3D/SQUARE、全部风组、W09–W14 高频、W15 无风、W00 低/无风、XYZ、早/晚段、峰值/P95、saturation/clip/tilt、安全停止与控制耗时均报告。置信区间以配对场景为单位；时间点不作独立样本，不宣称跨训练种子泛化。

进入下一步必须同时满足：

1. 72/72 candidate 与 B raw 同场，双方完整 STABLE；scene、运行、raw SHA 和控制身份通过独立复核。Candidate 不得出现安全停止、非有限值、电机饱和或 generalized clip，tilt count 如实报告。
2. DEV72 等权 macro Q(candidate) 严格低于 Q(B)。
3. DEV72 等权 macro SO(3)(candidate) 严格低于 SO(3)(B)。
4. W09–W14 高频组与 W15 无风组的 Q、SO(3) 均值均不高于 B；全部场景配对胜率及配对置信区间如实报告，不以 C5 回退作为失败理由。
5. 72 个 candidate 与 B 比较均绑定同一 locked scene/seed/reference/wind/morphology 输入；C5 模型、normalizer 和在线头身份完全一致。

逐场 raw 独立重算后，由 root 决定消融/论文评估/TEST48。开发门失败则锁住 TEST，不临时切方法或重命名指标。该 58 场不是独立测试，不能据此声称泛化。

## 执行授权与资源

- 当前阶段准备及运行上限：58 场 × 1 candidate 臂 = **58 runner/Plant calls**、1,160,000 transitions、原始与汇总新产物不超过 **20 GiB**。B raw 全部复用，不新跑 B。启动前 C: 可用空间须≥30 GiB；每次开始前复查空间，低于30 GiB即停止，不删除数据。
- 单个重负载闭环作业；启动前确认已有 MATLAB/Octave 及其他正在运行的重负载闭环实验均已自然结束。不得结束、抢锁、暂停或打断现有实验。离线无 Plant 准备与评分可继续。
- 只用 PowerShell 7 启动。训练、TEST、C7、重跑屏幕12和重跑两个既有 DEV pair 均未授权。唯一输出根在 `experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_dev72_v1/`，历史路径只读。
- 运行器必须逐场 CreateNew 写 marker/raw/status；执行前后校验 lock SHA、scene/cfg/options、B comparator identity 与磁盘空间。任何真实 invocation 都计入 58；未知 invocation 或第一次完整性/安全失败立即停，保留所有失败/半成品，不对同 attempt 重试。post-run 汇总错误用隔离 reviewer 从 raw 修复，不能改写批次状态或重跑。
- 独立 no-Plant 输入准备以 C5 lock 的 `scene_ids_all_72` 为唯一行选择名单，从根目录 `configs/scene_specs.csv` 逐行定位这 72 个 DEV/VAL scene ID；定位到第 72 行后立即停止读取。不得按文件前 72 行切片，不得把 TEST 行载入表格或写入产物，也不得触碰 TEST raw/MAT。仅将 58 个未配对 ID 的原始行写入隔离 CSV；另 14 行只核验身份并复用。记录 72 个匹配行的 row SHA、58 行 CSV SHA、每场 scene/spec/metadata SHA、模型/C5 快照/运行器 SHA 和全部禁用状态。源文件完整 SHA 只作为既有来源收据中的完整性元数据，不通过解析 TEST 行来生成筛选结果。
- 本任务书本身没有 TEST 放行；全 DEV72 gate 通过后，还要独立规划比较消融和独立测试任务书。

## 版本冻结方式

任务书先冻结。随后只做 58 行输入导出、隔离复制、MATLAB 无 Plant 场景重建/代码检查、静态验证 candidate-only runner 与 B72 raw 对照身份；产出 `NOT_FROZEN` candidate lock。Root 独立复算 screen12 candidate 对 B 的位置/姿态指标，核对 58 IDs/seed/spec hashes、代码/输入 SHA、B raw 谱系、预算与运行器。通过后冻结 source lock 并签发 root release，才可执行精确 58 calls；不得自行扩场、训练、改参数或打开 TEST。
