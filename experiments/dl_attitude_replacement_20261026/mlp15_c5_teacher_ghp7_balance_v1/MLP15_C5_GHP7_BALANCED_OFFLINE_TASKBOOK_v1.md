# MLP15：C5 教师 GHP7 覆盖诊断任务书 v1

日期：2026-10-26（Asia/Shanghai）  
状态：冻结；只授权一次离线训练与一次离线复算。不授权 Plant、闭环、B/C5 重跑或 TEST。

## 目标与假设

检验一个单一假设：此前 MLP15/GRU15 在 GHP7 同状态回放误差很大，部分来自训练状态分布缺少 GHP7 主动变形轨迹。使用 C5-RBF 在 G1/G2 的既有闭环状态与 `rbf_output_raw` 标签进行定向覆盖后，模型应在**未参与本次训练的 G3 教师轨迹**上降低动作模仿误差。

这只是离线机制诊断。即便通过，也不代表闭环改善、安全通过、独立验证或论文结果达标。

## 冻结输入

- 原始基集：`mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz` 中仅 C5 的 72 场 `c5_train_x/y`、`c5_val_x/y`，数据 SHA-256 `b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f`；manifest SHA-256 `98766ddac3125b81d4637eeb2576349b6ce181c94564c1a444d1d4cab734d55c`。不索引或展开 NPZ 中任何 B24 成员。
- GHP7 来源：`GHP7_BASELINE_REUSE_MANIFEST_v1.json`，SHA-256 `8a34df2807cfe10486ee1dc5c3d698b6e530d2fdf901ca9d815ae1f5d1f71b25`。要求状态 PASS、六个场景身份完整、`test_data_read=false`、`raw_files_copied=false`、`baselines_reexecuted=false`；逐条验证 C5 raw SHA、完成状态、20000 transitions、20001 state samples 和 1999 个姿态事件。
- 本次训练只提取 G1/G2 四份 C5-RBF raw：

| 训练场景 | C5 raw SHA-256 | 记录说明 |
|---|---|---|
| `DL1018_GHP7_G1_W00` | `35046519a6485abd2d9370f363cf3f1ecd3c65e1958199ea2071f6282f617e02` | 保留原始 logger 完成标志不一致记录；实际 20000 transitions / 20001 states，独立计分完整 |
| `DL1018_GHP7_G1_W12` | `0c6e96231b0fed51ac529eff73d940a7ae56f85bbf3db2f37a7fee3d54427a3f` | 完整 |
| `DL1018_GHP7_G2_W00` | `bcb0b97af5c9b6d4305f4a6c2cadf210ede130118eb5ab6d976a408c59051f80` | C5 原记录 `application_feasible=false`；仅供离线教师拟合，不得作为可行闭环证据 |
| `DL1018_GHP7_G2_W12` | `db14af895c39f3ce7c14d2ec305867650b9e1759307459736108ca5c935efdec` | 完整 |

- G3 两场只放入单独的离线评估包，训练程序不得打开：

| 留出场景 | C5 raw SHA-256 |
|---|---|
| `DL1018_GHP7_G3_W00` | `0ee3dc655540b877fa3728194da2a02677dcc00601a29bbfa313813305128bc4` |
| `DL1018_GHP7_G3_W12` | `9823a4745a6d221c17958c53fd570345a536268f5b4f373fc0ca795fda368789` |

这两场此前已经用于 GHP7 候选筛查，因此称为“开发诊断留出”，不称独立验证或 TEST。

## 标签与合法输入

- 标签是 C5 日志中同一姿态事件的 `rbf_output_raw`，单位 `rad/s²`，在 `dmax` 限幅后、`beta` 应用前。
- 唯一输入为 13 维：wrapped attitude error ×3、body rate ×3、BS nominal torque ×3、morph command ×4。事件 k 的输入窗口只含 k 及之前 14 个姿态事件，开头以零补齐。
- 禁止输入惯量/质量属性、`Jhat/Jdot_hat`、Plant truth、RBF 权重或隐状态、observer、物理前馈、未来状态或未来命令。特征从同一 C5 raw 的合法日志重建，并与日志记录特征（若存在）逐事件核对。

## 唯一变更与固定训练条件

唯一研究变量为训练状态分布：把 72 场原始 C5 教师数据与上述 G1/G2 四场并用，每批 512 个样本中固定 256 个从原 72 场均匀抽取、256 个从 G1/G2 四场均匀抽取。不得读取 G3 训练包。

其余沿用 MLP15 full72：13×15 因果输入、隐藏层 `[64,32]`、SiLU、3 输出；Adam，学习率 `1e-3`、weight decay `1e-5`；SmoothL1 beta=1；batch=512；seed `2026102001`；恰好 60000 步；只保留最终 checkpoint，不做验证选模、参数搜索或中途发布。输入均值/标准差和目标逐轴 RMS 按既有定义在 72+4 训练场上重算。输入数据类别、采样分配、归一化数据范围作为同一个预注册“训练分布”因素。

运行时保持已确认的比较配置：`max_tilt=30°`，姿态残差 `dmax=[45,45,4.7124] rad/s²`。本任务不运行闭环，也不修改限幅。

## 离线复算与晋级门

训练结束后，才打开 G3 留出包；以相同的 G3 raw、C5 状态和 `rbf_output_raw`，对比既有 MLP15 full72 与本次新 MLP15。两模型均按各自训练 normalizer 推理、因果零填充，并应用相同 `dmax`；报告每场每轴绝对 RMSE、以同一 G3 teacher RMS 归一的 RMSE、合并向量误差和输出裁剪次数。

仅当 G3 两场合并归一化 RMSE 至少降低 10%，且任一留出场的向量 RMSE 未恶化超过 5%，才建议另行放行一个冻结的闭环开发筛查任务书。否则停止本条数据覆盖假设，不继续改网络或扫参。此门只决定是否值得做开发闭环筛查，不构成最终性能验收。

## 资源与保护

- 预期新增训练约 3–5 分钟；训练和审计包总新增不超过 2 GiB。
- 不启动 MATLAB/Plant；不重跑 B、C5、C7、DEV72 或 TEST48；不解封 TEST；不删除或改写历史 raw、模型、缓存和账本。
- 新代码、提取包、训练产物、离线结果和状态都写入本目录。固定输出目录存在时拒绝重跑；所有输入输出留 SHA 与准确命令。
