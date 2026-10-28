# A1R 固定 SCREEN12 闭环控制组准备任务书 v1

**状态：** `PREPARATION_PLAN_ONLY`；实现待 Root 审核；本文件不授权 Plant、训练或 TEST 访问。

## 目的与边界

冻结 A1R step 40000，作为后续 A1T 比较的固定闭环控制组。A1R 在此不作为新搜索候选，不因既有离线预测表现较弱而跳过，也不据离线预测指标承诺闭环收益。禁止训练、optimizer、TEST、改写已有 run、覆盖历史文件。

运行只使用原 A1 SCREEN12 的 12 个场景及各自已冻结的 C5 原始场景数据。C5 的 `cfg`、场景身份、物理参数、位置算法及 `position_coordinate_mask=[1;1;0]` 均保持原值。原 A1 engine 与纯前向函数按现有字节身份调用；只新增独立快照、准备器、单场 runner 和审计结果，不复制或修改 engine/forward。

## 冻结身份

| 输入 | 路径 | SHA-256 / 固定身份 |
|---|---|---|
| SCREEN12 场景清单 | `reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json` | `fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923` |
| A1R deployment 参数 | `experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1/deployment_parameters_v1.json` | `b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23` |
| A1R checkpoint | 上述 deployment 的 `identity.checkpoint_sha256` | `5fa4308b6220e530e6c2e7a6f45c4b6e22ddddef80d1bc5cafdcf58564bc5ef3` |
| A1R 选择步 | deployment identity | `selected_step=40000` |
| A1R canonical normalizer | deployment identity | `faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c` |
| A1R 数值 parity 记录 | deployment identity | `Torch_NumPy_parity_max_abs_rad_s2=7.105427357601002e-15` |
| 原 A1 engine | `experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m` | `4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a` |
| 原纯前向 helper | `experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m` | `1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9` |
| 原 prediction helper | `experiments/attitude_cm18_a1_20261024/delayed_prediction_step_candidate.m` | `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d` |
| C5 基准快照 | `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat` | `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a` |
| C5 活跃源码库存 | A1 SCREEN12 preparation result 的 `c5_active_source_inventory_sha256` | `6790dc2e5d3bdc5afece8f2577e9e3fa9694bda94a26433f723f271f2850a804` |
| A1 SCREEN12 原准备结果 | `reports/attitude_cm18_a1_20261024/screen12_remaining_v1/SCREEN12_REMAINING_PREPARATION_RESULT_v1.json` | 其 manifest、C5 snapshot、source inventory 身份均以上述固定值为准 |

每次准备和启动前均重新核实际文件 SHA、MATLAB `which` 路径及 C5 source inventory；缺文件、SHA 不符、路径解析到其他版本时立即拒绝。A1R deployment 必须保持 schema `CM18_A1R_DEPLOYMENT_PARAMETERS_V1`、checkpoint 与 step 如上。网络参数以 deployment 中 canonical double 数组加载，尺寸按既有 18→32→32→24 pure forward 契约检查，不从训练 float32 normalizer buffer 反推 canonical 值。

## 固定场景及配对原始身份

使用 `CM18_A1_DEV_SCREEN12_v1.json` 中全部 12 个场景，不增删、不换场。路径与 SHA 从清单逐行复制并再次校验。下表严格按冻结 manifest 顺序列出；所有 raw 都是已冻结的 C5 baseline 输入，不覆盖。运行顺序固定为首航 `DL1018_DEV_T1_C01_W15`，其后按表中顺序跳过首航执行余下 11 场。

|任务|类别|scene_id|C5 baseline raw（repo-relative）|raw SHA-256|
|---|---|---|---|---|
| T1 | STATIC | `DL1018_DEV_T1_C00_W03` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C00_W03/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `fa36bf4aa229279d964b40c10cb3579487b5c641d167572383ef49f63196af5d` |
| T1 | ACTIVE_NO_WIND | `DL1018_DEV_T1_C01_W15` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C01_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `b61f01ab5920de766b8596512490b596e3959fa87368cd40a3b30758831fe651` |
| T1 | ALL_ARMS | `DL1018_DEV_T1_C15_W14` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C15_W14/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `6c72ae52e3f39af36442935468af7d2a047af460b845223167ee206d0dc96707` |
| T1 | MULTI_ARM | `DL1018_DEV_T1_C05_W06` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T1_C05_W06/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `727febc0aedbd4f127eb46aec8d103ab5b2b1e4336d8e92882c4447b779b602e` |
| T2 | STATIC | `DL1018_DEV_T2_C00_W04` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T2_C00_W04/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `9b408641737fe13bcc290d87f0d02176c26701717fc9145e1ca0191be906442f` |
| T2 | ACTIVE_NO_WIND | `DL1018_DEV_T2_C02_W15` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T2_C02_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `f0e524b6bd8bbafc6e6ecccff3879500332371af068421db120cd795944f608b` |
| T2 | ALL_ARMS | `DL1018_VAL_T2_C15_W09` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_VAL_T2_C15_W09/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `6af25d0ace1feb24deb1891364444ad40973204af8e20ebe400afc673d42d431` |
| T2 | MULTI_ARM | `DL1018_DEV_T2_C06_W07` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T2_C06_W07/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `02869a1271b1a5483b03565cc2e2366fd370392e68e9265ca943251e212a56be` |
| T3 | STATIC | `DL1018_DEV_T3_C00_W05` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C00_W05/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `a88c5010bb1e264ddde36f9e1400d0f6947b5a0a7361dede183c59e0f9f634f3` |
| T3 | ACTIVE_NO_WIND | `DL1018_DEV_T3_C03_W15` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C03_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `6afcc865b94f06d8e9558f261fa97c1b90aac73d5e4daf985c4f3b4315ce8a58` |
| T3 | ALL_ARMS | `DL1018_DEV_T3_C15_W14` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C15_W14/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `2df0e35d32bff888c3225638d468b2e796d8942387002a48cf53b4242d3c6a27` |
| T3 | MULTI_ARM | `DL1018_DEV_T3_C05_W02` | `experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3/DL1018_DEV_T3_C05_W02/C5_AXIS_MASK_M110/attempt_01/raw_run.mat` | `6c7d83ee79e1549a6ef603739a8922ce73f4b1695237cd9eec94567a8126eb23` |
清单字段 `first_engineering_scene` 指向 `DL1018_DEV_T1_C01_W15`，因此它是本组首航；不是重新使用已存在的 A1 首航结果。A1R 的首航必须独立执行、独立审计。首航 PASS 后，依上表顺序跳过首航，逐场运行余下 11 场。

## 无 Plant 准备与放行前门

只在新隔离目录生成文件：

- `experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/`
- `reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/`

准备器读取原 C5 快照并从中复制 12 场的 `cfg`、`sceneIdentity`、C5 `opts` 和原始场景；每场只按已审 A1 契约设置 A1R model、marker，并将 `rbf_attitude_enabled`、`rbf_attitude_output_enabled`、`rbf_attitude_update_enabled` 明确设为 logical false。还原 model/marker/RBF 字段后，`cfg`、场景身份及其余 `opts` 必须与 C5 原件 `isequaln`；位置掩码仍为 `[1;1;0]`。准备阶段不调用 runner、engine、episode wrapper 或 Plant。

首个 ROOT release 前完成以下检查并保存真实 no-Plant receipt：

1. `checkcode` 新准备器与 runner；对原 engine、forward、prediction helper 和全部 C5 依赖核 SHA 与 `which` 实际路径，确认原文件字节不变。
2. 从固定 deployment 载入 A1R 参数和 canonical normalizer，检查 shape、finite、选中步、checkpoint、normalizer SHA。使用固定屏幕场景中预先明确的真实 X18 输入样本，在 MATLAB 运行原 `cm18_a1_forward_v1`，逐项与绑定的 Python/NumPy 参考输出比对；另测 synthetic zero-basis 输入。该检查仅验证实现 parity，不评估优劣、不选步、不改变模型。
3. 12 个 C5 raw 均与本清单 path/SHA、scene_id、`C5_AXIS_MIXED_COORDINATE_M110` 候选及 `[1;1;0]` 掩码吻合；每个新快照的 scene/time/cfg 与 C5 原件一致。
4. 每个快照均明确三项姿态 RBF flag 为 false；准备与 parity receipt 记录 `plant_calls=0`、`engine_calls=0`、`run_episode_calls=0`、`training_steps=0`、`optimizer_steps=0`、`TEST_accessed=false`。

以上门控全部通过后，Root 审核准备结果并对首场签发单场 ROOT release。当前没有 release，也没有可运行的 runner 命令。

## 单场运行与停止

runner 只接受固定 12 个 scene ID 中由当次 release 精确绑定的一场；release 绑定部署 SHA、清单 SHA、原 raw SHA、新快照 SHA、C5 snapshot/source inventory SHA、A1 engine/forward/helper SHA、准备结果 SHA、runner/preparer SHA 和该场 ID。每次一个独立 MATLAB 进程、一个场景、最多一次 `attempt_01`。已有 START、attempt 目录、未闭合 ledger、失败状态或 release 不匹配时均拒绝；不覆盖、不自动重试。首场 raw 经独立逐事件审计 PASS 后，Root 才逐个签发其余 11 场的单场 release；任一场失败立即停止后续场。

预期每场 20 s、dt=1 ms：20,000 transitions、20,001 state samples、100 Hz A1R 事件共 1,999 个。必须保留 raw、run_start、启动/首步 marker、run_status、逐事件输入/输出与安全日志。输出各自写入新 A1R 目录，不写回 C5 或 A1 历史目录。

## 审计与报告

每场独立审查 raw 时间轴、scene/cfg 与模型身份、事件数量和顺序、X18/预测/请求补偿、模型调用、RBF 输出/更新关闭、finite 状态、稳定终态和安全停止。通过后汇总全 12 场完整逐场表，并保留 20 s 全时域、逐轴及各阶段的姿态/位置误差，SO(3) 误差，均值/RMSE/峰值，clip 与 actuator saturation 计数和事件位置，安全事件及停止原因。指标计算沿用已冻结 A1 SCREEN12 audit 的定义，不新增筛选阈值或只报告有利片段。

最终将 A1R 每场与同 scene 的 C5 baseline raw 及既有 A1 SCREEN12 raw 配对列示；A1 首航 `DL1018_DEV_T1_C01_W15` 从 A1 first-flight 目录取，其他 11 场从 A1 `screen12_remaining_v1` 目录取。按 scene_id 对齐，不跨场替代。这个闭环控制组只提供固定模型在既定场景的实测表现；A1R 离线预测分数不保证闭环增益，也不能据此作模型结构或 A1T 训练标签的因果结论。

**未来命令形式（占位，当前不可运行）：** 无 Plant `prepare_a1r_screen12_control_v1` 完成并经 Root 审核后，再使用单场入口 `run_a1r_screen12_control_v1(scene_id, release_path, expected_release_sha256)`。执行命令、MATLAB 绝对路径和 ROOT release 由 Root 在实现审核后另行签发；本任务书不构成授权。