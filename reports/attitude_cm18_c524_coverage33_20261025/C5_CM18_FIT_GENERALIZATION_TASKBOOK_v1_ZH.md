# C5_COVERAGE33 冻结模型拟合与跨场泛化离线评估任务书 v1

**状态：待主模型审核实现脚本。** 本文取代 `C5_CM18_OFFLINE_IDENTIFIABILITY_TASKBOOK_v1_ZH.md`；旧稿标记为 **未审批、已取代、未执行**。旧稿中的 `G_MORPH` 只是由现有 `u/z` 对形态状态作确定性物理重表达，没有增加信息，不能用来证明可辨识性或缺失特征收益。

本任务只评估已冻结的 `C5_COVERAGE33` checkpoint 对直接 `Cstar/beta` 标签的离线逐点残差。现阶段只交付本任务书；实现脚本必须先由主模型审核。未经该审核不得执行评估。本任务书及评估结果均不授权训练、改模型、调用 Plant、启动闭环或访问 TEST。

## 评估问题与边界

在同一冻结模型和同一冻结输出尺度下，对比：

1. 33 个训练场景缓存中，原定每场 400 行上的 **in-sample** 标签残差；
2. 15 个未参与训练的 C5 教师 EVENTS 缓存中，与训练端完全相同的 400 个事件 ordinal 上的 **scene-blocked DEV** 标签残差。

这是对这一个 checkpoint 的开发诊断。“泛化”仅指这些已指定 DEV 场景相对 TRAIN 场景的缓存标签误差变化，不代表独立验证、独立测试或 TEST 泛化。主比较不混用训练端 400 行与 DEV 端 1,999 行：DEV 全 1,999 行、首次形变事件、active phase、各 phase_code 和 W 分组都只作预先指定的附加分层，不改变主判定。

所有预测均为冻结模型对 cache 中 `X18` 的纯前向推理；不拟合参数、不更新权重、不选择 checkpoint、不做校准或超参数搜索。所有真值均为已确认的直接物理标签 `target_raw_output_rad_s2 = Cstar / beta`，不使用旧 behavior-residual 标签，不从 15 场拟合或改写监督目标。

## 固定输入及身份

执行只允许读取下列输入及其列明的验证材料，不搜索或枚举其他数据目录：

| 材料 | 固定身份与用途 |
|---|---|
| 33 场 TRAIN / 15 场 DEV 教师 EVENTS cache 身份、路径、逐文件 SHA、split 与事件数量 | `experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json`，SHA-256 `7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c` |
| 冻结训练划分与 checkpoint release | `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json`，SHA-256 `02f23f05b2fa20d5026e2dee1d4c77daa2572b34b3d95059f08c009315e7f803` |
| 冻结 checkpoint / 导出模型 | checkpoint：`experiments/attitude_cm18_c524_coverage33_20261025/training_C5_COVERAGE33_v1/final.pt`，SHA-256 `960ef67b7dd2ac1d2d1bca5d13e818674b2f14357d85ae6035590914c250cb07`；导出模型：`experiments/attitude_cm18_c524_coverage33_20261025/models/C5_COVERAGE33_model.mat`，SHA-256 `66f8053782e7afb823afa24368cea8002b55b536a587a8e8b13dbb9e13cf3142` |
| 已审核 15 场闭环 binding v3 | `experiments/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_CLOSED_LOOP_BINDING_v3.json`，SHA-256 `87ac859a29488d66f87330a7f0060183fb9a3e07178244677db28cbd8a527ee8`；只用于确认候选身份、固定 DEV 场景顺序及与既有审核的交叉核对 |
| 已审核 15 场结果报告与逐场 scene audit | `reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md` 与 `reports/attitude_cm18_c524_coverage33_20261025/scene_audits/`；用于核对已审身份与 TEST 边界，不复制15场 raw 逐场 SHA 表，也不读取 raw 时序 |
| 输出归一化尺度 | `experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json`，文件 SHA-256 `23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781`，canonical SHA-256 `12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a` |

relabel manifest 的完整 SHA 必须同时匹配 training release 与 binding v3 的 pin；任一 pin 与本文列值不一致时停止，不能自行接受磁盘上的新 manifest。

固定 TRAIN 划分为 24 个原 `C5 TRAIN24` cache 加 9 个 `TRAIN_EXTRA` cache，共 33 场、13,200 个训练行；15 个 DEV 场景使用 manifest 中 `holdout_dev_scenes` 所列 C5 教师 EVENTS cache，并须与 binding v3 的 15 个 scene ID 一一对应、顺序一致。不得增删、替换、重排或按场景类别重新切分。无需复制15个 raw 的逐场 SHA 表；逐 cache 路径、SHA、scene ID、split 与事件数均直接核对 relabel manifest，binding v3 与已审核结果报告作上游身份佐证。

按 scene ID 的 T 家族计数固定为：TRAIN 的 T1/T2/T3 分别 12/10/11 场；DEV 分别 4/6/5 场。预检须重算并核对这些计数，报告也须列出，以披露本次固定场景组合。

训练划分的固定采样行图为零基 event ordinal `0,5,...,1995`，每场 400 行。training release 记录 `row_map_sha256=bc202f6653fb04169990dac9dd209805bbf661b1797c3e64788206e6d6c75521`、`sample_index_stream_sha256=c3bbbf2f82a8bb50e4851b08614816024c7b912e36f9f6c6a0bc1a215d3ec9a9`；执行前须按同一规范重建并核对。15 个 DEV cache 每场应有 1,999 个 canonical 事件，主分析仅取同一零基 ordinal 列表，不得将 cache 行号误作 ordinal 或改变抽样。

模型、checkpoint、normalizer、manifest、training release、binding 或任何 cache 的 SHA、内嵌 scene ID、split、事件顺序、抽样行图任一不符，立即以 `STOP_IDENTITY` 停止；不继续推理或统计。训练与 DEV scene ID 有交集、15场中任一被 release 标为参与训练/模型选择，或出现不在固定清单中的 cache，也立即停止并报告 `STOP_SPLIT_LEAKAGE`。

## 严格预检与缓存闭合

实现须先进行**只读身份/字段预检**，所有预检通过后才可载入 checkpoint 做前向推理。预检至少完成以下检查：

1. 逐一核对本任务固定的完整 SHA、release、binding 与 cache manifest 引用；核对 checkpoint SHA 与 binding/release pin，确认模型 ID 为 `C5_COVERAGE33`、训练场景数为 33、训练行数为 13,200、训练步数/optimizer steps 均为固定 release 所记的 60,000，且 holdout/validation 未用于训练或 checkpoint 选择。
2. 对 33 个 TRAIN cache 与 15 个 DEV cache 分别验证磁盘 SHA 与 manifest、精确 scene ID、split、事件总数和列维度；确认输入/标签有限值、目标三轴次序固定、beta 有效且正值。
3. 逐场验证缓存 ordinal 与 canonical event index 的一一对应；训练 cache 的 400 行精确等于零基 ordinal `0,5,...,1995`。重建整份 row map 与 sample index stream，并逐字节匹配 release 中两个 row-map SHA。DEV 主分析按完全相同的 ordinal 选取 400 行；全 1,999 行仅进入次级分析。
4. 用 cache 中已确认的 `Cstar` 和 `beta` 重算 `Cstar/beta`，与直接标签逐轴比较；最大绝对闭合误差须 `<=1e-8 rad/s²`。若 cache schema 另存标签、物理闭合或 relabel receipt，须一并验证它们与 manifest/release 相符。不得因字段名不同而改用 `target_applied_acceleration`、剪裁后目标、raw 行为残差或另一个标签。
5. 对照 relabel manifest 中的 33 TRAIN / 15 DEV 清单，检查教师 cache 的闭合摘要与事件数；15 DEV scene ID 与 binding v3、审核报告顺序一一相同。审核材料已有的候选 raw 身份只通过 manifest/binding/audit pin 核对，不为本分析复制逐场 SHA 表，也不需打开 raw MAT 时序。

任一 cache 缺失、哈希失配、行图不闭合、标签重算误差超限、scene/split 混淆、事件计数不符或 release/binding 自相矛盾，立即停止并输出具体原因；不得补抓数据、按相邻事件填补、静默丢场或改用 TEST/C5_VAL48。对由于 schema 或上游材料导致无法完成的检查，应停止并报告 `STOP_CACHE_CLOSURE`，不能把“未检查”记作通过。

## 固定尺度与误差指标

模型与误差统一使用同一个冻结 normalizer 的输出轴 RMS：

| 轴 | 固定 RMS（rad/s²） |
|---|---:|
| X | 8.71283036857775 |
| Y | 8.721630269411728 |
| Z | 0.6125819446901479 |

该尺度来自 A1T normalizer 所引用的 768 个 TRAIN 场景、307,200 行，canonical SHA 如上；它不是 C5 这 33 场的重新估计值，也不代表 C5 的零输出预测误差。不得按 DEV、phase、W 组或本轮 33 个 C5 场重新拟合/重估任何均值或尺度；推理时沿用 checkpoint 所绑定的冻结输入均值、输入标准差和输出轴 RMS。

令 `e[s,i,j] = prediction[s,i,j] - target[s,i,j]`，轴尺度为 `S[j]`。对每场、每个分析子集及每个合并分组，先在场内计算：

- 物理逐轴 RMSE：`sqrt(mean_i(e_j²))`，单位 rad/s²；物理逐轴 signed bias：`mean_i(e_j)`，单位 rad/s²。
- 物理向量 RMSE：`sqrt(mean_i(sum_j(e_j²)))`，单位 rad/s²；物理向量 bias 为三轴 bias 向量 `mean_i(e_i)`，并报告其欧氏范数，单位 rad/s²。
- 归一化逐轴 RMSE：`sqrt(mean_i((e_j/S_j)²))`；归一化逐轴 bias：`mean_i(e_j/S_j)`。归一化向量 bias 为 `mean_i(e_i/S)`，并报告其欧氏范数，无量纲。
- 归一化向量 NRMSE：`sqrt(mean_i(mean_j((e_j/S_j)²)))`，无量纲。

主判定分数 `TRAIN_NRMSE` 与 `DEV_NRMSE` 分别是各自主集合中**场内归一化向量 NRMSE 的场景等权算术平均**。不把不同场景行拼接为一个微平均主分数。所有主结果均报告 TRAIN 33 场和 DEV 15 场各自的宏平均、逐场值、逐场相对本 split 宏平均的中心化差值，以及逐轴/向量物理与归一化 RMSE/bias（向量 bias 报三轴分量及其范数）。TRAIN 与 DEV 没有自然的同场配对，不输出伪造的逐场 DEV−TRAIN 配对差；两组总体差由下面的独立场景 bootstrap 给出。

同时报告同一组缓存标签上的**零输出基线**（prediction 恒为零，按相同尺度、相同行集和等场权重计算以上指标）。零输出基线只帮助理解标签与尺度；门槛不按此基线重定标。TRAIN 与 DEV 的物理指标、固定尺度归一化指标和零输出基线都需分别列出。

## 主比较、bootstrap 与附加分层

### 主比较

主比较仅使用每场 ordinal `0,5,...,1995` 的 400 行：TRAIN 33 场仍是训练中使用的原行；DEV 15 场取相同 ordinal 序列。它评估冻结模型在 TRAIN 行上的 in-sample 残差与未训练教师场景上同等大小的 scene-blocked 残差。DEV cache 的其余 1,599 个事件不得混入主分数、bootstrap 或阈值。

### 场景 bootstrap

TRAIN 与 DEV 没有同一场景配对键，不得虚构逐场配对。固定 10,000 次 scene-block bootstrap，伪随机种子 `20261025`。每次 replicate 分别对 33 个 TRAIN scene block 和 15 个 DEV scene block 独立、有放回抽样，保持各自样本数；每个抽中的 block 携带该场全部 400 行及其已算场级分数。分别计算 replicate 的 TRAIN 宏平均 `T*`、DEV 宏平均 `D*`、差值 `D*−T*` 和比值 `D*/T*`。若某 replicate 的 `T*=0`，当 `D*>0` 时将 ratio 记作 JSON 字符串 `"+inf"`，两者均为 0 时比值为 1；必须报告 `T*=0,D*>0` 的 replicate 数，并在 ratio CI 分位点为无穷时同样用 `"+inf"` 字符串序列化，不得写裸 `Infinity` 或 `NaN`。报告 `T`、`D`、`D−T`、`D/T` 的 percentile 95% CI（2.5%、97.5%分位点）；绝不在事件行层重抽样。此 CI 只刻画这些固定 TRAIN/DEV scene 混合下的场间变异，不外推到新的轨迹家族、场景总体或自然工况。

对于每个 W 子组和 phase 子集，也对完整场景 block 做同样的场景等权描述与 bootstrap；每次有放回抽样只能从该分层实际包含的 scene block 中抽取，并保持该层 scene 数。phase 内事件分析仍按每个场景内对应 phase 行计算该场指标，再在场景间等权；不能将拥有更多该 phase 行的场景赋予更大权重。若组中场景数少于 5，必须在报告中标明区间不稳定且只作描述，不用于预注册总判定。

### 附加分层

以下结果单独展示，不能改变主门槛或代替主样本：

1. **15场全事件**：对每个 DEV teacher EVENTS cache 的全部 1,999 事件计算场内指标并场景等权汇总。不得与 primary 的 400 行结果合并。
2. **首次形变事件**：按冻结 extractor 的 `phase_code` 规则，在每场中选最早一个当前形态命令非零的 canonical 事件，即最小 ordinal 且 `phase_code ∈ {2,4}`；每场最多一行。报告可用场景数、事件数、逐轴/向量物理及归一化 RMSE/bias。若某场没有该事件，不填补并报告该场缺项。
3. **active phase 与 phase_code**：active phase 定义为 `phase_code=2`（当前命令为正）或 `phase_code=4`（当前命令为负），两者分别报告并可另列合并 active。其余 phase_code 按 extractor 源逻辑分别报告：0 全程没有形态命令；1 当前无命令且不属于全程无命令、已展开保持或最后命令之后；3 当前无命令且至少一路形态 `rho>0.150001`；5 当前及后续已无命令、此前至少出现过命令，且没有触发已展开保持条件。phase code 只用于分层，不是模型输入。不得跨 phase 借行或借场补值。
4. **W 分组**：从 scene ID 的 `_Wnn` 固定解析 W00–W15，逐 W 值报告场景数和同一套指标；另汇总 W09–W14 组。每场等权，W 字符串原样保留前导零。分组缺少场景时照实报告，不插补。

每个附加分层均报告场景数、实际事件数、逐轴/向量物理及归一化 RMSE、signed bias、宏平均及场景 bootstrap CI。phase 和 W 结果是开发集上的描述性切片，不作为发现因果关系、重新选择阈值或声称统计独立的证据。

## 预注册判定门槛

只用 primary 400 ordinal 结果计算门槛。设 `T=TRAIN_NRMSE`、`D=DEV_NRMSE`，均为固定 A1T 输出 RMS 尺度下的场景等权宏平均归一化向量误差；`CI95_ratio` 是上述 scene-block bootstrap 的 `D*/T*` percentile 95% CI，`CI95_delta` 是 `D*−T*` 的相应 CI，后者保留作绝对差解释。

- **FIT_POOR**：`T >= 1.0`。这表示 TRAIN 上的场均残差至少达到一倍共同冻结 A1T TRAIN RMS 误差尺度；它不是“达到本轮 C5 零输出误差”的比较。
- **GENERALIZATION_GAP**：`D/T >= 1.2` 且 `CI95_ratio` 下界严格大于 1。该标签与 `FIT_POOR` 独立，可同时成立；不得因 `T>=1` 而隐藏相对跨场退化。若 `T=0`，当 `D>0` 时比值按 `+∞` 定义；若 `T=D=0`，比值定义为 1。
- **LOW_POINTWISE_ERROR_CLOSED_LOOP_GAP_REMAINS**：`T <= 0.25` 且 `D <= 0.25`。0.25 是预注册的研发描述阈值，用于标记离线点误差较低而历史闭环门槛仍失败的并存现象；它不是根因检验，也不能推导出闭环差异已定位。
- **INCONCLUSIVE**：以上标签均未触发。若同时触发 FIT_POOR 与 GENERALIZATION_GAP，两者均须报告；若触发低点误差标签，不再标成“不确定”。

所有点估计比较使用包含边界的 `>=` / `<=` 规则；GENERALIZATION_GAP 的 bootstrap ratio CI 下界要求严格 `>1`。如 bootstrap 无法生成、任何场无效导致 T/D 无法定义或 scene block 数与预期不符，则结果为 `STOP_STATISTICS`，不输出门槛标签。门槛仅用于研发判断，不自动触发任何训练、模型修改、Plant/闭环或 TEST 操作。

## 固定复现入口与隔离输出

实现材料固定放在 `reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_impl_v1/`：该目录只允许包含 `run_cm18_fit_generalization_v1.py` 与 `IMPLEMENTATION_ALLOWLIST_v1.json`（逐项固定依赖及其 SHA-256）；不得把实现材料放入结果目录。主模型须先审核脚本、依赖、哈希和 allowlist。本文不创建或运行脚本。从仓库根目录的 PowerShell 7、既有 Python 环境运行；审核通过后只允许使用以下固定入口：

```powershell
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
python -B reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_impl_v1/run_cm18_fit_generalization_v1.py `
  --taskbook reports/attitude_cm18_c524_coverage33_20261025/C5_CM18_FIT_GENERALIZATION_TASKBOOK_v1_ZH.md `
  --train-release reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json `
  --relabel-manifest experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json `
  --closed-loop-binding experiments/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_CLOSED_LOOP_BINDING_v3.json `
  --normalizer experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json `
  --audit-dir reports/attitude_cm18_c524_coverage33_20261025/scene_audits `
  --output-dir reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1
```

结果只能写入 `reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1/`；该目录须在首次运行前不存在或为空，若已存在任何历史文件，脚本须拒绝运行，不覆盖或清理文件。实现与输出目录必须分离：实现目录只含审核固定的脚本和依赖 allowlist，且不得用作输出目录；结果目录不得含脚本或依赖文件。不得写入 `experiments/`，不得复制 cache 或 raw。实现须先只做只读身份/字段预检，预检全部通过后才加载冻结 checkpoint 并执行一次确定性推理。它须将训练/优化/Plant/engine/episode/TEST 计数以零值回执记录。

至少保存：

- 按 scene 的 primary 逐轴/向量 RMSE、NRMSE、signed bias（向量 bias 的三轴分量与范数）与零输出基线 CSV/JSON；
- 15场 secondary 全事件、首次形变、active phase、逐 phase_code、逐 W 及 W09–W14 的同格式指标；
- scene-block bootstrap 采样规范、seed、每项宏平均与 CI、门槛结果；
- TRAIN/DEV 的 T1/T2/T3 场数，以及 ratio 为 `+inf` 的 bootstrap replicate 数；
- 输入文件路径/完整 SHA、模型/checkpoint/normalizer pins、manifest scene 列表核对结果、每场事件数/ordinal 行图/缓存闭合误差；
- 实现脚本与依赖 SHA、taskbook SHA、精确命令、执行环境摘要、最终报告 SHA，以及明确 `training_steps=0`、`optimizer_steps=0`、`Plant_calls=0`、`engine_calls=0`、`TEST_accessed=false` 的 receipt。

输出完毕后即停，交主模型审核报告；不得把门槛标签转成新的执行授权。TEST 数据、TEST cache、TEST raw、TEST 指标和任何 TEST 身份材料都禁止访问。`C5_VAL48` 不属于本任务输入。15 个 DEV 场景仍是开发证据；本评估没有“独立测试”结论。

## 实施补充：结果目录 staging 发布边界

本节补充“结果只能写入”一语：它限定最终交付物必须全部位于 `fit_generalization_v1/`，允许实现为避免半套结果而在同一项目版本目录（`reports/attitude_cm18_c524_coverage33_20261025/`）内创建一个唯一、隐藏、与结果目录直接同级的临时 staging 目录。脚本须在所有结果文件、receipt、SHA 与容量校验完成后，以一次目录重命名将完整 staging 发布到 `fit_generalization_v1/`；不逐文件发布。若目标已存在，仅允许在确认其为普通空目录后移除再发布；非空目录、符号链接、junction 或 reparse point 均须 fail closed。

若进程在发布前中断，最终结果目录仍可不存在或为空，但同级 staging 可能作为孤儿残留。脚本不得扫描、覆盖或自动清理不是本次运行创建且未识别的 staging；本次运行的 staging 仅在确认其仍位于该项目版本目录后才可清理。不得将此发布方式描述为 Windows 上具备跨平台的崩溃原子性保证。临时 staging 仅用于构建，最终报告、表格、summary 与 receipt 仍只能交付至 `fit_generalization_v1/`；其它输入、统计与实验边界不变。
