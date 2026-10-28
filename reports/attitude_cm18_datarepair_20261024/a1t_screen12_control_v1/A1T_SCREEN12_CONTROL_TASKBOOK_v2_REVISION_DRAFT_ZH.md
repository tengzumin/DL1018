> Root review pending: this contract-detail revision does not replace the previously approved v2 taskbook.

# A1T 固定 SCREEN12 闭环控制任务书 v2

**状态：** `IMPLEMENTATION_APPROVED_PLANT_NOT_AUTHORIZED`。批准实现 no-Plant 准备器与逐场 runner；不授权实际 MATLAB、Plant、engine flight、训练、optimizer 或 TEST。

## 目的与解释边界

在固定的 A1 SCREEN12 12 个场景上，评估已冻结 A1T checkpoint 的闭环表现。A1T 与 A1R 使用相同场景、C5 `cfg`、物理场景和基线 raw；A1T 只替换姿态网络参数及其身份。这个对比评估的是“C* 新标签训练流程及其诱导的 target-axis-RMS 变化”这一组合，不把差异单独归因于标签公式，也不把闭环结果说成只由训练标签造成。A1T 不是超参数搜索，不调参、不重训、不选新模型。

本任务仅作隔离的实验闭环评估。A1T deployment 内的 `deployment_authorized=false` 保持原值；未来 per-flight ROOT release 即使批准一次 Plant 实验，也不构成一般部署许可。

## 冻结身份

| 输入 | 固定路径 / 身份 | SHA-256 或选择值 |
|---|---|---|
| 场景清单 | `reports/attitude_cm18_a1_20261024/CM18_A1_DEV_SCREEN12_v1.json` | `fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923` |
| A1R no-Plant 准备结果 | `reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json` | `4792a168e5057827cbec184d9c7354e76641c02a7c6509680642585c6b7c1b2b` |
| A1R 参考任务书 | `reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/A1R_SCREEN12_CONTROL_PREPARATION_TASKBOOK_v1_ZH.md` | `f69704d003b880e263ba85fef17b79ebb59517d8b5fed871622ef40c5a1ada47` |
| A1T deployment 参数 | `experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1/deployment_parameters_v1.json` | `dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42` |
| A1T checkpoint | deployment `identity.checkpoint_sha256` | `58c72450fcc1e9aaa04f7454ad2a8aa551f161a95e52bb9946f0c99c23957cea` |
| A1T 选中步 | deployment identity | `selected_step=40000` |
| A1T canonical float64 normalizer | deployment `identity.canonical_normalizer_float64_sha256` | `12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a` |
| A1T MATLAB parity | `reports/attitude_cm18_datarepair_20261024/ROOT_A1T_ACTUAL_MATLAB_PARITY_v1.json` | `e9fac82b7d713195b8de0a79a213693138ef49001b02a3c1437d58fd9e9e5323` (`PASS`, 11 cases) |
| A1T parity fixture | `experiments/attitude_cm18_datarepair_20261024/postselection_a1t_v1/matlab_parity_fixture_v1.json` | `a94ef0be146563ea2fe9f6cb43a78c43d2918e77e42b44a85ad3a3cbc4d55996` |
| 原 A1 SCREEN12 paired scorer | `reports/attitude_cm18_a1_20261024/root_screen12_metrics_v1.py` | `3b345050b31cabdfcb08dab405d9e34b736e1f65c02bc9fd22d3a0f08c9aeb52` |
| Frozen A1 engine | `experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m` | `4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a` |
| Frozen pure forward | `experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m` | `1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9` |
| Frozen prediction helper | `experiments/attitude_cm18_a1_20261024/delayed_prediction_step_candidate.m` | `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d` |
| C5 原始参数快照 | `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat` | `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a` |
| C5 source inventory | A1R 准备结果 `c5_active_source_inventory_sha256` | `6790dc2e5d3bdc5afece8f2577e9e3fa9694bda94a26433f723f271f2850a804` |

A1T 网络结构固定为 `18→32→32→24`。参数从上述 deployment 读取，normalizer 使用 canonical float64 原件；不得由实际 float32 normalizer buffer 反推。该部署记录的 float32-to-canonical rounding 偏差仍按其 metadata 保留。纯 forward 继续使用冻结 A1 helper 和上述实际 parity receipt，不另写或修改 forward/engine。

## 固定 12 场与配对要求

使用 manifest 的全部 12 个场景，按固定 `scene_id`、C5 raw path/SHA 与 A1R 准备结果逐行配对，不增删换场。下表仅按 manifest 原顺序展示；执行时必须先运行 `first_engineering_scene`（T1/C01/W15），其余 11 场再按 manifest 原顺序执行（跳过已先行的首场）：

1. `DL1018_DEV_T1_C00_W03`
2. `DL1018_DEV_T1_C01_W15`（固定首航 `first_engineering_scene`）
3. `DL1018_DEV_T1_C15_W14`
4. `DL1018_DEV_T1_C05_W06`
5. `DL1018_DEV_T2_C00_W04`
6. `DL1018_DEV_T2_C02_W15`
7. `DL1018_VAL_T2_C15_W09`
8. `DL1018_DEV_T2_C06_W07`
9. `DL1018_DEV_T3_C00_W05`
10. `DL1018_DEV_T3_C03_W15`
11. `DL1018_DEV_T3_C15_W14`
12. `DL1018_DEV_T3_C05_W02`

每个 A1T prepared scene 必须从对应 A1R 快照复制同一 `cfg`、`scene`、`sceneIdentity`、C5 输入和共同 `opts`。替换项仅限 A1T model/deployment identity 及当次运行 marker；`isequaln` 核对 `cfg`、场景和其余选项与对应 A1R 快照一致。A1R 对应 scene 的 Plant raw 独立审计 PASS 后，才可为同一 scene 签发 A1T 单场 release；无同场 A1R PASS 时拒绝。A1T 首场必须是 T1/C01/W15，首场 audit PASS 后 Root 再逐场批准后续 11 场。

## 固定控制语义

A1T 与 A1R 一样，使用 100 Hz 姿态事件，物理积分 `dt=1 ms`，20 s horizon；保持 C5 配置、参考、位置控制器和 `[1;1;0]` 位置坐标掩码不变。模型推理仅用既有 18 维输入、过去事件窗口、原 beta、原 clip 和原 J0；不增加时钟、风、真实惯量或额外特征，不改变输出变换、限幅、事件时序、位置支路或 Plant 方程。

`rbf_attitude_enabled=false`、`rbf_attitude_output_enabled=false`、`rbf_attitude_update_enabled=false`，均须为 logical false；不得因 A1T 准备或运行更新姿态 RBF。运行前必须对快照和实际 runtime opts 逐项核验；flags 缺失、真值或类型不符即拒绝。

## 实现与放行门

实现获 Root 批准后，只在以下独立目录写 A1T 专属准备器、runner 和结果：

- `experiments/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/`
- `reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/`

不得修改 A1R、A1/A1T 训练源、冻结 engine/forward/prediction helper、C5 文件、历史 raw 或既有 audit。实现沿 A1R 单场 runner 模式但独立命名与 release 身份；每场单独 MATLAB 进程、一个 ROOT release、一个唯一 attempt，不自动重试。已有 start marker、attempt 目录、失败状态、未闭合 ledger、身份/SHA/`which` 路径不符时立即拒绝。失败停止后续场。输出只写新目录，不覆盖任何历史文件；12 场总输出不超过 1.5 GiB，运行前检查可用磁盘空间并记录实际输出字节数。

每场开始前核对 A1T deployment、checkpoint、selected step、canonical normalizer、parity receipt、A1R 同场 PASS 身份、C5 raw/SHA、A1R snapshot/SHA、C5 snapshot/source inventory、scene/config/opts、engine/forward/helper SHA 和 `which` 路径。A1T 准备器不得调用 engine、episode wrapper 或 Plant；其 receipts 明确记录 `plant_calls=0`、`engine_calls=0`、`run_episode_calls=0`、`training_steps=0`、`optimizer_steps=0`、`TEST_accessed=false`。Root 先审核准备结果与首场 v1 release，再决定是否授权首航；本任务书本身不授权 Plant。

未来 release 采用单场 schema，固定绑定 `scene_id`、sequence index、model/deployment/checkpoint/normalizer/parity pins、同场 A1R PASS raw/audit、C5 raw 和 prepared snapshot、C5/source/engine/helper pins、prep 与 runner SHA。每一场都需新的 Root release；不能用一份 release 批跑或预先批准剩余 11 场。

实现接口固定为 `run_a1t_screen12_control_v1(sceneId,releasePath,expectedReleaseSha256)`。release 路径为 `reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/ROOT_A1T_SCREEN12_CONTROL_RELEASE_<sceneId>_v1.json`；schema 为 `A1T_SCREEN12_CONTROL_ROOT_RELEASE_V1`，decision 为 `APPROVE_ONE_A1T_SCREEN12_FLIGHT`。release 必须显式 `plant_authorized=true`、`training_authorized=false`、`optimizer_steps_authorized=0`、`TEST_accessed=false`，并提供 `scene_id`、`sequence_index`、`prior_a1t_audit_sha256`（首场为空，其余为每个前序 A1T PASS audit SHA）、`baseline_C5_raw_sha256`、`same_scene_a1r_raw_sha256`、`same_scene_a1r_audit_sha256`，以及本文冻结的 taskbook、manifest、A1R preparation、C5 snapshot/source inventory、deployment/checkpoint/step/normalizer/fixture/parity、prepared snapshot、engine/forward/prediction helper、prepare 与 runner 各自 SHA。每场独立审计结果写入 `A1T_SCREEN12_LOG_AUDIT_<sceneId>_v1.json`。runner 仅接受与当前 scene 对应的文件名和身份；即使 release 存在，也须在本地重新验证同场 A1R PASS 和此前 A1T PASS。

## 预先固定的评分

主姿态指标固定为原 A1 SCREEN12 scorer 定义的全时域 `SO3_RMSE_deg`，按 20,000 个 left-sampled state 计算。次指标固定包括 transported body-rate vector/逐轴 RMSE、三轴 Euler RMSE、位置 `Q` RMSE、姿态/位置/角速度峰值、safety duration/stop、clip 与 actuator saturation 计数和事件位置。以上都报告全 12 场，并同时按原 A1 scorer 的 `pre`（0–5 s）与 `post`（5–20 s）窗口输出，不按首场结果改模型、阈值、clip、beta 或统计窗口。

每个 scene 按同一 scene_id 配对列出 A1T、A1R、原 C5+RBF 与原 A1。主指标是实际闭环 SO(3) RMSE；不以静态 angle-acceleration 屏幕的 `43/48` 作为闭环胜率或闭环表现。该 12 场只作机制筛查，不能代替独立论文验证；扩场或任何 TEST 使用必须另由 Root 冻结方案后授权。

## 记录与报告

每场保留 raw、run_start、start/first-Plant marker、run_status、release 身份、安全日志与独立逐事件审计。物理记录必须完整 20 s、20,000 transitions、20,001 states 和 1,999 姿态事件。沿预先固定的评分输出全时域、逐轴、早/晚阶段的指标、clip 与 actuator saturation 计数和索引、安全事件及终止原因；不新增有利片段筛选或性能阈值。

最终按 scene_id 配对列出 A1T、A1R、同场 C5 baseline 与原 A1 的实际闭环指标，另标明动作分支的输入身份与输出 SHA。核心结论限于该固定 C*+induced-RMS 训练流程在这 12 场中的实际表现；不能用旧 behavior-residual 标签 RMSE 作为 A1T 的 direct-compensation 能力主评价，也不能把结果外推为纯 label 效果、普遍部署收益或因果证明。仅模型 JSON、快照、raw、fixture 等数据产物须带 `DO_NOT_GIT_UPLOAD` 标记；任务书、小型审计报告与结果表可供审核并按项目规则纳入版本控制。

**当前不可执行：** 无准备器/runner命令、无 ROOT flight release。Root 完整审核并批准实现及无 Plant 检查后，再单独决定是否签发首场 release。




