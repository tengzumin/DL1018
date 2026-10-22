# 首轮冻结 W0 自适应 Head/PCF 输出协调分支筛查：任务书与运行契约

## 目的与假设

冻结的待证伪假设是：W09–W14 高频场景的 Z 轴闭环劣势可能与“自适应 Head + PCF 输出协调耦合分支”的高频交互有关。离线同状态目标残差在线前后略有改善，不能排除该闭环分支机制。首轮筛查只判断整个耦合分支是否值得进一步扩展研究；12 场结果不能宣称方法达标、冻结 W0 已修复问题，也不能单独证明在线 W 更新有害或有益。

主模型审核记录（2026-10-22 03:41 +08:00）：通过代码与任务书审查，仅批准第1个VAL场景PROBE；不得自动续跑剩余11场。当前包只包含入口、身份锁、任务书和静态验证。静态测试中模拟传入 `-ParentReviewed` 只用于验证门禁和 harness 的 PROBE preflight 路径，不代表父审批准。审批前的无标记预检应为 `BLOCKED`；本次获批启动时 launcher 会重新生成带审查标记的 mode-specific preflight，且仅在其为 `PASS` 时启动 PROBE；harness PASS 另记在静态验证日志中。

## 唯一实验差异

OFF 只将 `opts.stage1_position_runtime.update_enabled` 从 `true` 改为 `false`。继续使用相同的 FEATURE Head、kappa=1、gamma=12、beta=1、PCF enabled、G12/R32 姿态控制、X14、模型、normalizer、W0、C0/J0/B 姿态与物理 Plant/执行器。Head 保持 enabled，仍以固定 W0 计算特征输出并执行 dmax 限幅和 beta 缩放；OFF 不会改变 W。没有关闭 Head，也没有拼接 B 输出。

runner 的 `stage1SearchEnabled && !updateEnabled` 路径把 FEATURE Head 输出从 `position_only_search_head_step(...,sEff,...)` 切到冻结分支 `raw=W'*phi`，并跳过 Head 的 PCF `s_eff` 输出协调项；PCF 仍启用并以 1 kHz 运行/记录，但 OFF 时其 `s_eff` 不再影响 Head 输出。因此本对照同时改变 W 在线更新和 PCF 对 Head 输出的协调作用，检验的是整个“自适应 Head + PCF 输出协调耦合分支”的高频交互，不单独识别权重学习效应。

## 固定身份和场景

- 模型：`CORRECTED_DSSM14_SEED2026102001_FINAL60000`，seed 2026102001，DSSM14，step 60000，optimizer steps=0。
- MAT 文件 SHA256：`6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`；模型绑定配置 SHA256：`cc5616b3c10def65b8cb3636d92219dd5ed4848a1651d4c1f1d81f147fd384af`；W0 `output_W` 33×3 数组内容 SHA256：`88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`。
- 历史 ON 机制审计的 `run_start` 模型数组身份为 `8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26`。其可复现算法在 `reports/paper14_v2/phase1/rebuild_mechanism_audit.py`：按顺序对 `input_W,input_b,input_mu,input_sigma,output_W,project_W,project_b,ssm_tau` 更新 SHA256，每项依次加入 ASCII 字段名、NUL、`repr((HDF5 读出 shape, dtype))`、NUL、C-order 连续数组字节。`mechanism_summary.json` 另记 `canonical_model_arrays_sha256=7621dbb6…`，它与该 `run_start` 自定义聚合身份不同；本锁和 OFF `run_start` 不将两个口径混用，也不保留未经本入口执行核验的聚合字段。实际模型身份由加载文件全 SHA、绑定 JSON SHA、W0 数组 SHA、normalizer 文件 SHA 与加载后 normalizer 数组 SHA 硬锁。
- normalizer NPZ 文件 SHA256：`520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404`；runner 实际 `input_mu/input_sigma` 数组身份 SHA256：`533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`；训练专用 normalizer 报告 SHA256：`b1d8a4e0386a6f91d11d51daeec0a01605dcf3fa58fd19f594dadd57e4e4d54e`。文件 SHA 与数组内容身份是不同口径。
- 冻结 VAL 名单路径：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\paper14_v2\phase1\ROUND_SCREEN_12_SCENES.csv`，SHA256：`176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e`。只读该文件，不读取 TEST。
- 配对重评分：candidate CSV SHA256 `cf0a4dc078f0cb751877695cabc58aba05bd0933b022d948410d376133a974e0`；B CSV SHA256 `27a77399470eda26fde5f1724d199de10235844c519e8d561547af6f1a8933b2`；现有 candidate `RAW_INDEX.csv` SHA256 `364367e46ae8e3eb3335efd34a834b984a2a87fc1cef0dd5bf4991bbf342d8b4`；运行起点 lineage SHA256 `99f630dd3702e4ea3e9638b875dc1d3d621ffa22daf8b88baa0232d6860fda50`。
- 预先核验的 `scene_payload_identity.csv` 路径：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\scene_payload_identity.csv`，SHA256：`d6a76d83d6e98ab9f29a1dff3ad479ccdfde6dc581cad70f2da4014367bddd16`。12 行必须均为 IDENTICAL，14 个物理字段，20,001 个时间点，最大绝对差 0。每次运行前检查此文件 SHA、场景 ID 和 ON/B raw SHA 绑定；B raw 用 `load(...,'scene')` 取得完整 20,001 点场景，且只允许对 scene_id 元数据别名做规范化。
- 独立只读复核器 `verify_scene_payload_identity.py` 对冻结 12 个 VAL 场景逐项打开 24 个已列名 raw（只读，不复制/写入），先后核验 raw SHA/size/mtime，再对 `scene` 中除 `scene_id` 外的 14 个物理数组做逐元素精确比较。字段固定为 `arms/command`, `arms/rhoDot_hat`, `arms/rhoDot_true`, `arms/rho_hat`, `arms/rho_true`, `environment_wind_I`, `initial_state`, `reference/acceleration`, `reference/position`, `reference/velocity`, `reference/yaw`, `reference/yaw_acceleration`, `reference/yaw_rate`, `time`。不做单位缩放或舍入；将每个数组规范为 little-endian float64、C-order，按字段名排序后以“UTF-8 路径+NUL、逗号分隔 shape+NUL、原始数组字节”顺序计算独立复核 SHA256；只接受 shape/数值完全一致且最大绝对差为0。HDF5 的 MATLAB string `scene_id` 只作为元数据，由冻结 manifest 映射；运行时 MATLAB 再校验其为精确 VAL ID 或唯一允许的 `_ACC_FIX_V1` 别名，并只规范化该元数据。复核命令（PowerShell 7）：`pwsh -NoProfile -Command "python 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\verify_scene_payload_identity.py'"`。preflight 每次也会调用同一复核器；它只处理锁定的 24 个 VAL raw，不发现/枚举任何其他数据。
- checkpoint 身份 SHA256（仅身份引用，不复制/加载）：544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5。模型 MAT：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_training\models\DSSM14\matlab_model_and_parity.mat；绑定配置：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\reports\PAIR_EVAL_MODEL_BINDING_FORWARD.json；normalizer NPZ：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_training\data\normalizer_x14_train_only.npz。
- 24 个复用 raw 的完整路径/角色/场景/哈希清单：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\reused_pair_raw_manifest.csv，SHA256：3bdfe154105f399607584a56ab0e67e498d200395a76adfe46fd1455880cf2b6；清单 raw_path 是本轮实际复用文件，B 的 paired_source_raw_path 仅记录来源 provenance。
- local MATLAB runner/helper/config 源码逐项固定如下；共享 Plant/执行器源码见下一表：

| MATLAB runner/helper/config | SHA256 |
|---|---|
| run_dl1018_closed_loop.m | 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b |
| run_episode_dl1018.m | fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330 |
| position_stage1_model_forward_v2.m | dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676 |
| position_only_search_head_step.m | 3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc |
| position_only_search_options.m | 4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf |
| controller_options_dl1018.m | 93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1 |
| position_filter_realization_pcf_step_v3_5.m | b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0 |
| init_dl1018.m | df1cfe9fdbfd61da9636427784852d1fa72a6d3b2aa6a941a094967322afda1c |
| effective_config.mat | cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f |

- 隔离运行入口、配置构造器、preflight、launcher、静态测试和未来评分器的 SHA256：

| 隔离入口/工具 | SHA256 |
|---|---|
| build_frozen_w0_options.m | 1123e7aade239cf728685bea7c0677ba71ec1597ef37eeaf0d6a774886b1045f |
| run_frozen_w0_screen.m | 34050502c83890e5a1268c90716abbd00421269b55053a959b7c21573ec73cbf |
| launch_round1.ps1 | 6f0e4c49c53748a9654f5b312d074169a02f432f7c909ce3805aa3e3ad2fbabd |
| preflight_round1.ps1 | 145bae5ace29b614d3f5434129f8af38a6cba0a27b00363f506a6964a1aaa9e0 |
| rescore_round1.py | cf0d212988cebd8fb11007e46f79d9de085216b5d53d31048f0a6385f7757ba9 |
| static_test_round1.ps1 | fe9193f577be94570f4cc073e48d417737099a6dfd36c7ba08ffe7e08b39b852 |
| verify_scene_payload_identity.py | e14dbe8b335b2bba342533f3387daba921e0cf770deddd3edb46f73ab51f499d |

- 每场 20 s；位置事件 100 Hz；Plant dt=0.001 s（1 kHz）；固定 seed=2026102001。

| # | 冻结 VAL ID | 场景/风带 | 复用 ON raw SHA256 | 复用 B raw SHA256 |
|---:|---|---|---|---|
| 1 | `DL1018_VAL_T2_C00_W10` | FIG8_3D / W09_W11 | `30bd63348a369911e8d14e48be3e48cf461c994ef054e9612fbc90487612d278` | `05ad0e797ca10ce164747709bca2f87967c4b928283e7eaaae7839de43e059b7` |
| 2 | `DL1018_VAL_T2_C02_W12` | FIG8_3D / W12_W14 | `928b42f96988bd237da2bc790674813b6470702ebcbee4504496dcbc6377428c` | `8bafacea5aa164f9ec12dea659ba9edc3c0ec8bf1d617ea5d8d5591566562404` |
| 3 | `DL1018_VAL_T2_C05_W15` | FIG8_3D / W15 | `8a1648e22fd7fd11c678d3505433784073f72d650daddc0f7914b2101880be42` | `64088a9da0d8a58a3d41ab4aa48ccef8adb44e32200101b37bba4e0e35db2c64` |
| 4 | `DL1018_VAL_T2_C06_W00` | FIG8_3D / W00_W08 | `3cf46555bce725143f713354e1fd95cbaded2f838aee8cf674643a89247b6f4a` | `90faa47e391b977f1df32dde668fa5bf252f3991eeb38f4db5789421e53a71c3` |
| 5 | `DL1018_VAL_T1_C02_W09` | HELIX / W09_W11 | `8529f802edf55ad195d40b552d17cec1e9c08148e4f1ad070609b10a1f027f09` | `7cf337cf777465c680da3dab2a123d63455f359f2cc3a9c61a1159336b32f1c4` |
| 6 | `DL1018_VAL_T1_C05_W12` | HELIX / W12_W14 | `d28c1ccc279b55a6fcbd9e131a271e4e56f2ef46edf4947934ee3f9cbd5b2223` | `97f1e5b074de8f4de8da8ef7d930580eb6b89774a09a8dea7b59d8cbe5c8f29e` |
| 7 | `DL1018_VAL_T1_C08_W15` | HELIX / W15 | `ca1511df873c65d104a4535dde6f6bfc7124c2eae056c01f5d3b3dbee5d2c483` | `22031939a953b244fbf2dcfe9e797dd4e059d8df0344b966e67f073ccab254b6` |
| 8 | `DL1018_VAL_T1_C00_W07` | HELIX / W00_W08 | `231a29949fe0f4ca1a900b909ee8ca9a003f99a71448c14974b68530b45f2b18` | `e3ec711f1108c2c9a0c78d9d1ce07211a12313c6c00c22d112eb515a16ddf927` |
| 9 | `DL1018_VAL_T3_C12_W09` | SQUARE / W09_W11 | `53fdade30b678ed42342625feffa2c7c5ac969c0944ec483f1cf18ae8570cf7d` | `b7d2b3f37d1f860f44935c238e7406b81ba2eab8ebf37bdb663c868fd03b0a27` |
| 10 | `DL1018_VAL_T3_C00_W13` | SQUARE / W12_W14 | `96a830d444c9a128c789df6d2b4250430fdb24a9cbc9e73a4a8776ef8aa29fde` | `d09b3b1e952264fab9a270c79ffadd85d617c8816757ef4b6d545a606073e733` |
| 11 | `DL1018_VAL_T3_C02_W15` | SQUARE / W15 | `1e5e7368871e5646530b4ddb03ea231b2a1b6f2d81805eaf3ccbb786dcb5b395` | `88ff5ca24b906f70bcc37d8dac9767b3e37b64ddfe3b0760a17b336b5a286505` |
| 12 | `DL1018_VAL_T3_C03_W00` | SQUARE / W00_W08 | `b6160a9137137df694bf173e18fd10cfe35d2b8b8b906458bc06381f74ed98c5` | `1238d9a55670a2e12d80d5eea6ea6edaebb6fb50586e99ad7d0fc18ed921e476` |

ON 与身份匹配的 B 仅复用以上现有 72-pair 原始结果；不重跑 ON 或 B。B 的部分 `manifest_source_raw_path` 是来源清单路径，实际配对重评分使用 `resolved_raw_path`；对每一场，实际被复用的是 manifest 中的 `raw_path/raw_sha256`，须与 B rescore CSV 的 `resolved_raw_path/resolved_raw_sha256_expected` 一致，并满足配对 Q 的 1e-12 m 容差。四场来源路径与解析后路径不同的情况会在 preflight 报告中显式列出。未来 rescore 对每个 ON/B raw 在哈希读取前后复查 size/mtime，并在 HDF5 scene 读取前后再次比较 SHA、size、mtime，改变即拒绝评分。未来 rescore 会对每个 ON/B raw 在哈希读取前后复查 size 与 mtime，并在 HDF5 scene 字段读取前后再次核验 SHA、size、mtime，变化时拒绝评分。

场景 payload 比对明细文件哈希锁定后，MATLAB 入口每次复查完整 12 行、14 个字段、差值为零、ON/B raw SHA 正确；不复制输入文件。过去 72 场 ON 的 run_start 没绑定下面 Plant/执行器源码 SHA，是历史审计缺口；不能据此声称旧 ON 与本轮使用逐字节相同 Plant 源码。本轮 runner 启动前检查并在 run_start 保存每个实际调用源文件的解析路径和 SHA256。scene_payload_identity.csv 的 SHA256 及 14 个物理字段/零差异证明在 PowerShell preflight 与 MATLAB 入口双重锁定。

本轮 MATLAB/core 全部 22 个源文件均纳入入口硬锁，覆盖 Plant、执行器、风、姿态、控制器及其内部依赖；历史 72 场 run_start 缺少其中关键链路的源码 SHA。

| matlab/core 源文件 | SHA256 |
|---|---|
| allocate_control.m | 5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53 |
| allocation_matrix.m | 5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d |
| arm_directions.m | 517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c |
| arm_mass_properties.m | 8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5 |
| attitude_bs_step.m | cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc |
| baseline_force_to_attitude.m | ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039 |
| command_filter_init.m | 64fbd68ef652f419066e0546569ba4029bdc00da3eabb0f8019bdc12f66d14a5 |
| command_filter_step.m | 15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b |
| controller_parameters.m | 4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398 |
| default_config.m | 685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51 |
| distributed_mass_properties.m | db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a |
| morphology_aware_wind_load.m | 51459cd2c09f1181e85bbee8f89ddbd75bd2ba923f1aebacbdd1ecfe7b3ba5ac |
| position_bs_step.m | ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681 |
| rbf_event_scheduler_step.m | cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618 |
| rbf_mimo_basis.m | 4139c7d08daa5bea6e04702b966ce76cdb6a54ea33d9820cfd9c3a70529248f4 |
| rbf_mimo_update.m | dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a |
| rk4_vehicle_step.m | 7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5 |
| simulation_parameters.m | 962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae |
| tcn0916_morphology_scenario.m | 711a87e01e616ee141f9068a8c4e31758dc328ade3f692e1a92a5de723d30438 |
| tcn0916_topologies.m | 3fd341fa2292c8118f8b363611671677517c44009550bdf82e96cd751e6dce5f |
| vehicle_derivative.m | c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786 |
| wind_velocity_profile.m | 88b500b0016225e21cde55fce0fbd6d54d0ffd2b34bed7a58f36d57e25b04f66 |

## 分阶段运行与审查门

第一阶段只运行名单中的第 1 场 `DL1018_VAL_T2_C00_W10`，用于估算耗时和输出大小。它结束后写入 `runs/<scene>/attempt_01/` 内的 raw、run_start、run_status，并写 `reports/probe_round1.json`，然后退出；run_start 保存 ON/B raw SHA、scene_payload identity、模型绑定/normalizer/W0 身份和 22 个 core/runtime 源 SHA；入口不会自动继续。主模型需检查该首场的 STABLE 状态、last_transition=20000、W_before/W_after 与 W0 的最大偏差不超过 1e-12、Head/PCF flags、运行秒数和输出大小。

只有首场完整安全、无重试，且主模型审核剩余 11 场后，才可显式续跑。续跑拒绝：首场缺失或失败、已有任意额外/部分 attempt、输出超预算、C: 剩余空间低于 30,000,000,000 bytes、预计剩余时长越过固定全局截止时间 2026-10-24T17:01:00Z（不是按 probe 时间重新起算 72 h），或任何源/输入 SHA 不匹配。单场不自动重试。24 个已复用 ON/B raw 实测总计 1,071,933,345 bytes，最大单文件 49,600,404 bytes，中位数 42,410,571 bytes。每个新 attempt 先按 64 MiB (67,108,864 bytes) 估算，较最大历史 raw 多 17,508,460 bytes 留作 run_start/status 等余量；12 场周期预估 805,306,368 bytes。probe 后按实测 attempt 大小更新，余下 11 场估算为 `max(64 MiB, probe attempt bytes) × 11 × 1.25`，且任何时点均不得超过 80,000,000,000 bytes。wall-clock 用首场实测秒数×11×1.25，并必须在固定全局截止前完成。launcher 与 MATLAB runner 在启动时都会复核安全条件。

### 已批准的启动命令（仅 PROBE；CONTINUE 需单独复核）

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\launch_round1.ps1" -Mode PROBE -ParentReviewed
```

检查 probe 输出和耗时后，如主模型明确批准剩余 11 场，再单独运行：

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\launch_round1.ps1" -Mode CONTINUE -ParentReviewed
```

不得把两条命令串联或自动执行第二条。launcher、独立 preflight、MATLAB runner 均要求 `-ParentReviewed`；launcher 转传该开关，MATLAB runner 还要求 preflight 报告中的 mode 和开关匹配、报告生成时间不早于 5 分钟。开关是显式审查门，执行前仍必须由主模型审核本任务书。每次 launcher 首先调用 PowerShell preflight，校验绑定、模型 MAT、normalizer、冻结场景/scene payload 身份、ON/B raw、隔离入口/runtime/Plant 源码 SHA、MATLAB 版本、现存 MATLAB 数量、Python 分类和磁盘时间/输出预算；任一不匹配就拒绝启动。硬截止时间固定为 `2026-10-24T17:01:00Z`，由 launcher、preflight 和 MATLAB runner 同时检查。所有未来输出只写入本目录的 `runs/<scene>/attempt_01/` 和 `reports/`。禁止复制或生成输入 MAT、模型、checkpoint、cache、fixture；新航次必需的 run_start.mat/raw_run.mat 仅写入隔离目录，不上传，禁止训练、调参、重跑 ON/B、读取 TEST、自动重试、重启或结束进程。

## 结果与预登记解释

全部差值定义为 OFF−ON，使用未舍入的 Q/RMSE 原值判断，显示时的舍入值不得参与判定。负差表示 OFF 改善；同场 raw 对齐容差为 1e-12 m。Q、XYZ RMSE 和 Z 分段 RMSE 使用 1 kHz Plant 位置轨迹的 20,000 个计分样本 `[0,20)`，排除 `t=20` 终态；Z 分段分别使用 `[0,5)` 的 5,000 点和 `[5,20)` 的 15,000 点。W00–W08 与 W15 的平均 Q 退步上限 0.5 mm 即 ΔQ ≤ 0.0005 m。

OFF 与 ON/B 的主要指标为 Q（0–20 s）、三维 position RMSE（X/Y/Z，0–20 s）、Z RMSE（`[0,5)` s 与 `[5,20)` s）；逐场指标对照须使用 1e-12 m 配对容差。建议向主模型申请扩展至 72 场，当且仅当：

1. 六个 W09–W14 场的 OFF 平均 Q 相对 ON 改善；
2. 六场中至少四场 Z RMSE 改善；
3. W00–W08 组与 W15 组的平均 Q 退步均不超过 0.5 mm；
4. 12/12 场安全且完整。

任一条件不成立，登记为整个自适应 Head/PCF 输出协调耦合分支的高频交互假设未通过首轮筛查；保留全部原始数据，不调参、不扩 72。probe 失败、unsafe/incomplete、预算中止或写出部分 attempt 时立即停止，保留现有证据；禁止自动/手工覆盖或重跑该 scene，PROBE/CONTINUE 入口会拒绝现存 attempt。需由主模型单独审查失败证据后再决定是否另立新任务。若全部通过，只说明这个组合分支值得继续检验；下一轮必须先设计并审核能分离 PCF 输出协调作用与 W 更新作用的最小单因素对照，之后再决定是否扩至 72 场。此次筛查的任何结果都不单独证明在线更新有害或有益；12 场本身不能作为达标结论。脚本 `rescore_round1.py` 是待未来使用的代码级评分器，目前没有对 OFF 真实输出评分。

## 静态验证与当前状态

静态测试只读取配置/CSV/源码，scene verifier 只读已锁定的 24 个 VAL raws；不调用 MATLAB，不调用 Plant，不创建航次。MATLAB runner 在 `init_dl1018` 前校验 preflight 绑定的 frozen_inputs SHA，并按锁重算模型 MAT、binding、normalizer、场景/复用清单、rescore、RAW_INDEX、lineage、评分 helper、机制证据、全部 runtime/Plant/setup 文件和任务书的 SHA；`inputIdentity`、`run_start.mat` 及首场 probe summary 保存实际 frozen_inputs 路径与 SHA。读取 B raw scene 前后均比较文件大小、mtime 和 SHA，不一致即拒绝该 scene。当前目录不得存在 runs 输出。未来 launch 运行前会重新检查 MATLAB 进程；当前过程检查中 Python 进程应分类为 `SOLIDWORKS_MCP_CAD` 或 `OTHER_PYTHON`，不得把 CAD 服务误报成“无 Python”。全局停止时间硬锁为 `2026-10-24T17:01:00Z`。MATLAB 可执行文件只读识别为 `C:\Program Files\MATLAB\R2025b\bin\matlab.exe`，Product Version `25.2.0.2978516`。

静态验证命令为 `pwsh -NoProfile -File "<实验目录>\static_test_round1.ps1"`、PowerShell AST parser 检查和 Python AST 检查；12 场 scene payload verifier 与 preflight 也都仅做只读身份核验。为检查门禁路径，曾给 read-only PROBE preflight 测试传入 `-ParentReviewed`，该 harness PASS 只表示开关路径测试通过，不代表主模型批准；不执行 launcher/MATLAB。`reports/static_validation.log` 保留审批前无标记 BLOCKED 的命令、退出码、摘要和 frozen_inputs SHA256。静态测试默认要求完全没有 `runs`；只有显式 `-AllowCompletedProbe` 才接受本任务书记录的唯一完整 raw/run_start/marker 集合及其固定 raw SHA，且该模式不改动结果文件。
## 主模型审查记录与当前决定

2026-10-22 03:41（北京时间）主模型独立审查了任务书、入口源码和身份锁。PowerShell 静态测试、PowerShell AST、Python AST、12/12场景 payload 复核通过；最终无标记 preflight 的唯一阻止项是按设计要求的父审查标记，除此之外77项SHA匹配、MATLAB进程为0、C盘可用168,466,518,016 bytes。MATLAB离线配置 smoke 通过：读取锁定模型并构造单因素OFF配置，W0/FEATURE Head/PCF状态匹配；未调用 run_episode 或 Plant。源码 Code Analyzer 报告4条建议级信息，无语法错误或运行失败。

审查决定：批准单场 `DL1018_VAL_T2_C00_W10` PROBE，用于实测耗时、输出大小和完整性；不批准自动/即时续跑其余11场。probe结束后主模型须读取实际 `run_start.mat`、`raw_run.mat`、状态和资源账本，重新审核再作 CONTINUE 决定。当前执行范围仍为X14/VAL，TRAIN/DEV外的新航次仅该probe；TEST保持封存，不训练、不调参、不重跑ON/B。此决定不代表通过首轮筛查或论文证据门槛。

入口故障记录（2026-10-22）：一次已批准的单场 PROBE 启动后，在 MATLAB 完成初始化与锁定身份核验后、创建 `runs/<scene>/attempt_01` 前退出。根因是 runner 读取冻结场景表不存在的 `split` 列；实际表头为 `task,band,scene_id`。该次退出未创建 runs/attempt，Plant 调用为 0。隔离修复只改为校验精确表头、冻结 ID 顺序及 `DL1018_VAL_` 前缀，并加入静态回归断言；本记录不构成再次启动授权，修复后须等待主模型复审。


## 修复后主模型复审与再次授权（2026-10-22）

首次获批 PROBE 启动在 MATLAB 初始化和输入身份校验后、创建 `runs/<scene>/attempt_01` 前退出。实际根因是入口误读不存在的 `split` 列；该启动未创建 `runs`、`run_start.mat` 或 `raw_run.mat`，Plant calls=0、transitions=0、TEST files read=0。此故障计入一次启动工程故障。

隔离修复只改场景表验证：准确要求 CSV 表头 `task,band,scene_id`、12 个冻结 VAL ID 的完整顺序及 `DL1018_VAL_` 前缀；静态回归测试验证实际 CSV schema 并禁止引用 `sceneTable.split`。主模型复审重新执行 PowerShell 7 静态测试及 parser、Python AST、只读 24-raw/12-pair payload 核验和 MATLAB `readtable` schema smoke，全部通过。真实 12 场清单为 14 个物理字段、每场20,001点、最大差0；检查时没有 MATLAB 进程，`runs` 仍不存在。审批前 preflight 为预期 BLOCKED，唯一阻断项是缺少父模型标记；所有文件 SHA、场景 payload verifier 和资源检查通过。磁盘可用约168.23 GB，已识别的10个 Python 进程均为 SolidWorks MCP CAD 服务。

**复审决定：通过修复审核，授权仅对 `DL1018_VAL_T2_C00_W10` 再启动一次 PROBE。** 该授权不覆盖其余11场、CONTINUE、训练、参数搜索或 TEST。若此 PROBE 完整安全结束，主模型必须检查真实 raw、run_start、status 和资源估算，再单独决定是否 CONTINUE；若失败、不安全、不完整或预算不满足，立即保留证据并停止，不能覆盖或重跑该 attempt。

此次审核绑定的修复版 runner、静态测试、任务书及 frozen_inputs SHA 以本文件末尾复审记录和 `reports/round1_parent_review.md` 为准。PROBE 前必须由 launcher 重新运行带 `-ParentReviewed` 的新鲜 preflight；该 marker 只传达以上明确的单场授权。

第二次启动记录（2026-10-22）：带标记 PROBE preflight 的锁定 SHA 与 12/12 scene payload 身份核验通过后，MATLAB 在 `restoredefaultpath` 后找不到 `init_dl1018` 并退出；runner 当时仅在 init 调用之后才把锁定 runtime 目录加入 MATLAB path。失败发生在创建 `runs/<scene>/attempt_01` 前，没有 runs/attempt、`run_start.mat`、`raw_run.mat`、状态文件或其他航次产物；Plant calls=0、transitions=0、TEST files read=0。根因修复从锁定 `runtimeFiles` 中查找 `init_dl1018.m` 条目，校验其目录并在调用 init 前将该目录前置加入 MATLAB path；静态回归测试检查锁定路径来源及执行顺序。此修复不授权再次启动；须由主模型复审后决定是否批准单场 PROBE。
## 第二次入口修复复审（2026-10-22）

主模型复核第二次入口故障的隔离修复：runner 在 `restoredefaultpath` 后，只从已锁定的 `runtimeFiles` 中查找 `init_dl1018.m` 文件条目，验证文件存在，将其目录先加入 MATLAB path，再调用初始化器；静态回归断言检查锁定来源和调用顺序。PS7 静态测试、PowerShell AST、Python AST、无标记 preflight 身份校验全部通过。preflight 检查 77 项 SHA、零失败；12/12 VAL payload 的14字段、20,001点完全一致；唯一 BLOCKED 项是父审查 marker。MATLAB 离线 path/init smoke 输出 `MATLAB_INIT_PATH_PASS`，只初始化项目配置，没有调用 runner/episode/Plant；runner Code Analyzer 有4条既存建议级提示，没有语法错误。`runs` 目录不存在，MATLAB进程为0，Plant/transition/TEST均为0，磁盘余量满足30 GB下限。

**主模型决定：批准对 `DL1018_VAL_T2_C00_W10` 再进行一次单场 PROBE 启动。** 这是新的、明确范围的审查授权，不含其余11场、CONTINUE、训练、调参或 TEST。启动通过 preflight 后若在 Plant 前再次失败，保留错误并停止；若开始航次，禁止覆盖/重跑，结束后由主模型审核真实产物和资源估算，再单独决定 CONTINUE。

授权命令：

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round1_frozen_w0_screen\launch_round1.ps1" -Mode PROBE -ParentReviewed
```

第三次启动故障记录（2026-10-22）：带标记 PROBE preflight 通过后，MATLAB 完成 init 和源码 SHA 核验，但 `runtime_source_path` 断言发现 `which('run_dl1018_closed_loop')` 实际路径不等于锁定的 REFERENCE_FIX `sources/local_runtime` 路径。此前只加入本地 `matlab/runtime` 中的 init 目录，并遗漏 init 后重新加入锁定 helper 目录。故障发生在创建 `runs/<scene>/attempt_01` 前，没有 runs/attempt、run_start、raw_run 或其他航次产物；Plant calls=0、transitions=0、TEST files read=0。修复后显式区分 `initRuntimeDir`（锁定 init 文件所在本地目录）与 `lockedRuntimeDir`（锁定 runtimeFiles(1) 对应的外部 helper 目录）；初始化后重新前置加入 lockedRuntimeDir，再 clear/rehash、验证锁定源码链及 which 路径。此单场 PROBE 授权已失败消耗；修复后须由主模型复审，不得自行再启动。

第四次单场 PROBE 记录（2026-10-22）：航次本身已完成并写出 `runs/DL1018_VAL_T2_C00_W10/attempt_01/run_start.mat` 与 `raw_run.mat`，但 `run_episode` 返回后 runner 在构造 `run_status.json` 时因 `struct(...)` 被长度分别为22和9的 Plant/runtime SHA 列表扩展成非标量结构而报维度错误。raw SHA256 为 `ad0810c2fc25f93b34e61432631d26d876712c4717946e6770f6fce58cbcda28`；主模型对原始记录的独立复核为 STABLE、20,000 transitions、计分区间 `[0,20)`（20,000点）、W0 前后最大差0、Head/PCF enabled、update disabled。离线 Q 为 B `0.00851665899477647` m、ON `0.008693982397142386` m、OFF `0.02999291272652684` m，OFF−ON `+0.02129893032938445` m。此单场不能构成筛查结论；当前缺少 `run_status.json` 和 `reports/probe_round1.json`，因此不能视作已通过的完整 PROBE，也不得重跑或覆盖。

主模型只读抽取的 `run_start.mat` 字段 `inputIdentity.frozen_inputs_sha256` 实值为 `e128c527cddcb81a42db9380775534b34d771e933e4bdaef7688ec78904cf1b6`，与该次 PROBE launch preflight 报告中的 `frozen_inputs_sha256` 一致；这才是航次实际绑定的历史 frozen_inputs 契约 SHA，不是当前修复后的 lock SHA。本次隔离修复仅改变航次结束后的 sidecar 结果包装：先构造标量结果，再分别赋值 Plant/runtime 源 SHA 列表；控制、Plant、输入、指标、raw 与航次执行均未修改。不得回写或伪称历史 run_start 绑定了修复后的契约。

恢复边界：只有主模型完成独立 raw/run_start 核验并另行审核后，才可生成带 `recovered_after_serialization_error=true` 标记的恢复 sidecar（`run_status.json` 与 `reports/probe_round1.json`）；只写不存在文件，不得覆写任何已有输出，也不修改 MAT/raw。若运行耗时不能由原始记录独立确认，恢复账本必须将耗时标为保守上界而非实测值。当前不生成 sidecar、不改 preflight/CONTINUE 接受逻辑；CONTINUE 因缺少成功 probe 的 status/summary 必须拒绝。该恢复记录不授权任何新航次。

结果包装修复的静态回归验证允许使用 `pwsh -NoProfile -File "<实验目录>\static_test_round1.ps1" -AllowCompletedProbe`，但仅在唯一的首场 `attempt_01` 恰好包含 `attempt_started.marker`、`run_start.mat`、`raw_run.mat` 且 raw SHA 与上列值完全一致时通过。无参数默认模式仍要求不存在 `runs`，用于保留新包 fresh-run 门禁；该测试仅读目录与 raw SHA，不加载或写入 MAT。修复后须主模型复审，不能据静态通过恢复 sidecar或继续航次。
## 锁定主源码路径修复复审与单场启动授权（2026-10-22）

第三次启动失败的原因已确认并修复：init 所在目录是 DL1018 本地 `matlab/runtime`，主要闭环 runner/helper 的冻结路径则在 `REFERENCE_FIX.../sources/local_runtime`。当前入口分别用 `initRuntimeDir` 和 `lockedRuntimeDir`；init 后重新前置加入 lockedRuntimeDir，再 clear/rehash 并核对 `verify_runtime_chain` 与 `which` 实际路径。静态测试检查这两类目录来自锁定条目且执行顺序正确。

主模型独立复审已通过：PowerShell 静态测试、PowerShell AST、Python AST；无标记 preflight 77/77 SHA、唯一 BLOCKED 项为父审查 marker、scene verifier 12/12；MATLAB 离线初始化及锁定 runner/helper `which()` smoke 通过；MATLAB Code Analyzer 对当前 runner 仅有4条建议级信息、无语法错误。全部检查没有运行闭环，`runs` 尚不存在，MATLAB/Plant/transitions/TEST 当前均为0，磁盘剩余空间满足锁定预算。

**主模型新增授权：仅执行一次 `DL1018_VAL_T2_C00_W10` PROBE。** 这是对三次启动故障后修复的单独审查决定；不含其余11场、CONTINUE、训练、调参或 TEST。若本次入口再失败，或者产生不完整/不安全 attempt，保存现有证据并停止，不覆盖、不自动或人工重跑该场景。若完整安全结束，主模型检查真实 raw、run_start、status、W0不变性和资源估算后再单独决定是否 CONTINUE。

## 主模型对 W10 原始 PROBE 的独立复核及一次性恢复决定（2026-10-22）

主模型使用 MATLAB 只读加载既有 `run_start.mat` 与 `raw_run.mat`，未调用闭环/Plant，也未访问 TEST。复核 `run_start.inputIdentity.frozen_inputs_sha256` 为 `e128c527cddcb81a42db9380775534b34d771e933e4bdaef7688ec78904cf1b6`，与启动 preflight 记录一致；此前记录的 `938b5b...` 是任务书笔误，现已更正。模型 MAT SHA 为 `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`，W0 SHA 为 `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`；run_start 中有22项 Plant 源身份与9项 runtime 源身份。

原始 `run_start.mat` SHA256=`ee6e1895ae4ce01ff42a8cda5c7f76362f7739677615583c982606bfa7a8d701`，`raw_run.mat` SHA256=`ad0810c2fc25f93b34e61432631d26d876712c4717946e6770f6fce58cbcda28`。读取时 scene ID=`DL1018_VAL_T2_C00_W10`、method=`FROZEN_W0_OFF`、20,001个场景时间点、STABLE、20,000 transitions；update disabled，Head/PCF enabled，W0 before/after最大偏差均为0。所有既有 raw/run_start 文件身份在复核前后不变。序列化错误只发生于航次完成后的结果包装；代码修复不改变控制、Plant、场景、模型或评分。

离线配对复算：B Q=`0.00851665899477647` m，ON Q=`0.008693982397142386` m，OFF Q=`0.02999291272652684` m；OFF−ON=`+0.02129893032938445` m。此场结果偏差明显，但它仅是预登记筛查首场，不足以代替12场风组均值或证明独立组件因果；继续本轮其余11场是完成已冻结的机制筛查所必需，不授权扩为72场。

文件时间仅能给出保守运行预算：marker=`2026-10-21T20:08:16.0327787Z`，raw最后写入时间=`2026-10-21T20:08:37.6321327Z`，区间约21.60 s；原runner精确tic/toc侧车缺失，恢复记录必须使用30 s保守上界，并明确不是实测耗时。恢复程序只可在两个目标文件均不存在时，从已核验MAT生成 `run_status.json` 与 `reports/probe_round1.json`；必须标记 `recovered_after_serialization_error=true`、`runtime_is_conservative_upper_bound=true`，不得写回或覆盖 MAT/raw。

**主模型决定：批准上述只读派生并新建缺失sidecar；批准随后使用新鲜 `CONTINUE -ParentReviewed` preflight/launcher，仅运行冻结清单第2–12场。** 不重跑W10；不批准72场扩展、训练、调参、TEST或任何其它候选。若新鲜preflight不为PASS、资源预算不满足、源/输入SHA不匹配或任一首场完整性条件不成立，则停止且不启动MATLAB。剩余11场执行期间无自动重试；所有产物保留在本隔离目录。

## Round 1 完成与下一轮边界（2026-10-22）

主模型的独立审查及配对逐场、分组复算见 `reports/paper14_v2/phase1/round1_screen_review.md`。12/12 OFF 航次安全完整；高频组 OFF−ON Q=`+24.604229235332852` mm、Z改善0/6；W00–W08退步`+23.092904448358743` mm，W15退步`+12.98357443172386` mm；预登记 gate 不通过。因此当前冻结 W0 假设被否定，Round 1结束，**不扩展72场、不调参、不读取TEST**。全部48个运行文件保留，周期输出560,781,729 bytes。W10恢复sidecar明确记30秒保守上界；其余11场均值21.08秒、范围20.84–21.44秒。W10 run_start 绑定历史lock SHA `e128c527cddcb81a42db9380775534b34d771e933e4bdaef7688ec78904cf1b6`；CONTINUE 11场绑定当时preflight SHA `13e4fc6da9a6ab4d4cdf81bcee978ca29a26d6e6c7ab5ee5018d7cc0dd9f5198`，后续审计追加不会覆盖历史身份。

代码路径审计确认：FEATURE Head 更新开启时，PCF on 使用 `clip(surface−eta_before)` 作权重更新方向；PCF off 使用 `clip(surface)`。若 update disabled，Head 仅静态输出，eta 不进入 Head 输出。因此 Round1只能说明这12场启停在线 W 更新的总效应，不能归因 PCF。

主模型决定仅推进 Round 2 的任务书与隔离静态实现准备：保持在线 W 更新和全部其余条件不变，只关闭 `command_filter_coordination_v3_5.enabled`，在相同12场 VAL screen上检验PCF eta扣除对高频弱项的影响。任务书及实现须另经主模型审查，未审查前不得运行；72场扩展、调参和 TEST 均未获授权。理论 gate 仍未通过，不得标记论文证据包达标。
