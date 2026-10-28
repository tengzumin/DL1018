# C5 同源配置、DSSM 推理修复与完整输入锁任务书 v1

日期：2026-10-25。root 批准**隔离工程修复、完整输入身份准备，以及经 root 审查脚本后的一次无 Plant MATLAB R2025b 调用**。不批准 runner 执行、Plant、闭环航次、训练、TEST 或方法/参数搜索。旧 scene-only launcher 不再启动；其失败记录和全部旧任务书、源码证据保留。本任务替代旧 scene-only 入口的 `default_config()` 有效配置来源要求。

## 已核实的问题和唯一修复范围

1. 首次 PowerShell launcher 在 MATLAB 启动前因空 pipeline 的 `.Count` 失败；已按 `SCENE_PAYLOAD_ENGINEERING_FIX_v1_ZH.md` 仅修正两处数组包装。资源账本为 launcher 调用 1、MATLAB 0、Plant 0、训练 0；保留 `LAUNCH_PRECHECK_FAILURE_v1.json`，不得把它算作候选方法的性能失败。
2. 隔离 `position_stage1_model_forward_v2.m` 错用了旧搜索版本 SHA `6e7d4d9fb221ea9e726df35fdd959c21e5a5eb63fe85760e15715ef6c8dd82e0`，没有冻结 DSSM14 所需的 `DSSM` 分支。root 与独立审查者已按 `C5_DEV72_INPUT_LOCK_v3.json` 全表比对；同名依赖仅该文件不匹配。先将旧文件、旧静态检查脚本及审计 JSON 按原字节归档到不可覆盖的 `preflight_v1/provenance_before_fix/`（不放入 MATLAB 搜索路径），再将该函数替换为下表 C5 锁定源的**原字节副本**，禁止自行重写算法。其余 38 个隔离 `.m` 源保持不变。
3. 真实 C5 cfg 来自有效配置/封存 snapshot，而非 `default_config()`；后者的 `controller_morphology_mode='morph'` 与 C5 `'fixed'` 不同。本轮有效 cfg 直接取下表 C5 v3 snapshot 的 `cfg`，仅由现有 `bind_paired_fixed_j0` 附加明确 J0 字段。不得按猜测逐项改 default cfg 来凑一致。

| 允许读取/复制的工件 | 身份与范围 |
|---|---|
| `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json`、`C5_DEV72_RUN_CONTRACT_v3.json`、`C5_DEV72_PREPARE_RESULT_v3.json` | 小型来源/契约 JSON；不遍历其 raw/outcome 路径 |
| `../REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_eval_v1/sources/local_runtime/position_stage1_model_forward_v2.m` | C5 锁定源 SHA `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`；复制前后验 SHA |
| `../REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_training/models/DSSM14/matlab_model_and_parity.mat` | 文件 SHA `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`；MATLAB 只 `load(...,'model')`，不读其它变量 |
| `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat` | 文件 SHA `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a`；只 `load(...,'cfg','opts','W0','modelIdentity')`，不读 sceneIdentity/sourceIdentity 或其它变量 |
| `../REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_training/data/normalizer_x14_train_only.npz` | 只验完整文件 SHA `520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404`；不解包，数组身份从 model 按 C5 契约计算 |
| 隔离 `configs/scene_specs_dev3.csv` 与 receipt | 沿用已有逐行 SHA 与三条 DEV 限定；不得读全场景 CSV、MAT/raw 或 TEST |

上表仅这些 model/config MAT 可读；其它 MAT、原始闭环结果、Teacher 数据、TEST 均不得读取。不改或复制外部 MAT，不删除任何内容。root 在本次 `.m` 来源盘点时曾对锁表内 `configs/effective_config.mat` 做完整文件 SHA，未解析变量；该 hash-only 访问须如实记入状态，不能宣称此前所有工具均未读取任何 MAT 字节。本任务不使用该 MAT 作为部署输入。

## 实施与无 Plant 验证

- 新实现/入口/结果限写 `paired_runner/preflight_v1/`；可以另建 `static_check_paired_runner_v2.py` 和新审计 JSON，旧静态脚本及 `CODE_ONLY_STATIC_AUDIT.json` 保留为修复前证据，明确标记其已过时。新检查须以 C5 v3 active source inventory 验证所有同名实际依赖，新增 helper/改名 runner/scene 及三个已有辅助 model 文件逐项列出来源和 SHA；不再用旧搜索 forward 作为权威源。除了上述 forward 复制，不改 helper、runner、BS、Plant 或学习律。
- 新 PowerShell 7 launcher 修正空列表包装，启动前检查既有 MATLAB/Octave，不结束或抢占进程；使用唯一新目录和 CreateNew，保存准确命令、源/输入/MATLAB exe 的运行前后 SHA、stdout/stderr、exit code、成功或失败 receipt。root 审查 launcher/probe 和静态结果前不得启动。这里只允许一次真正 MATLAB 调用；失败即停，重试由 root 另决。
- MATLAB `restoredefaultpath` 后只激活隔离树。先验证 allowlist 工件完整 SHA，再按表加载指定变量。模型须为 DSSM14、architecture=`DSSM`、seed=`2026102001`、selected_step=`60000`、input_dim=`14`、window=`32`；`output_W` 有限且为 33×3，与 snapshot W0 逐元素全等，其原始 double 列序字节 SHA=`88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`。按原 C5 prepare 的 header+double 字节算法计算 input_mu/input_sigma 的 normalizer 数组 SHA，必须等于 `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`；snapshot modelIdentity 必须同样匹配。
- 有效 cfg 取 snapshot.cfg 并验证固定控制器模式和 dt=.001。绑定 J0 后，`rmfield(cfg,'attitude_replacement')` 必须与 snapshot.cfg 完全相同；J0 与 fixed controller inertia 矩阵及 hash 全等。由此 cfg/model 重新构造原 C5 options（FEATURE、gamma12、kappa1、delayed prediction、M110），须与 snapshot.opts 完全相同。再调用现有 `make_paired_c5_options`；baseline 去掉仅新增的 paired_arm、paired_position_method_id、显式零 attitude 初权字段后须与 C5 options 全等，候选去掉 arm 及三项 attitude RBF 开关后须与 baseline 全等。显式零初权必须与原 runner 隐式零初权一致；锁定 position/attitude RBF 真实初值的形状和 double 字节 SHA。
- 修复后先执行一个人工 DSSM 模型、零窗口的无 Plant smoke：14 输入、32 步、32 状态、零 input_W/bias、单位 project_W/零 project_b、unit tau，断言 phi=`[zeros(32,1);1]` 且第二输出为空。再对冻结实际 model 使用重复 input_mu 的 14×32 合成窗口，验证 33×1 有限归一化 phi 并记录输出 SHA。不得用真实运行轨迹作 smoke。允许对隔离源运行 MATLAB `checkcode` 及静态依赖/路径解析，仅保存诊断和依赖版本，不执行 runner。
- 复用 synthetic v3 的实际 helper/BS 接口审计，只在当前 helper/BS/相关物理源 SHA 与该证据完全匹配时有效；不以修复前 v1/v2 成绩替代，不重复运行已匹配的合成审计。
- 在同一 MATLAB 调用中，以**上述 C5 有效 cfg**对原三条 DEV ID 各生成一次 scene；前次 scene-only 未启动，因此不存在成功生成的旧 payload。沿用原 probe 的 ID/seed、spec 一行、初态12×1全零、time 0:.001:20、全部输入数组尺寸/有限性、W15零风及 metadata 哨兵断言。三场分别哈希 out.spec/out.scene/out.metadata，输出只保存 SHA/尺寸/摘要，不保存 scene 或模型 payload、不写 MAT。

## 输出与后续放行

生成不可覆盖的候选完整清单 `preflight_v1/.../source_lock_paired_runner_v1_candidate.json`，包含 39 源及新入口/审计/launcher/任务书 SHA、来源替代关系、MATLAB/依赖版本、allowlist model/config/normalizer 工件和数值身份、cfg/J0、三场输入/seed/hash、两臂有效及规范化 common options SHA、RBF 初值身份、synthetic v3 证据身份、全部诊断与本轮真实启动账本。状态必须 `NOT_FROZEN`、`closed_loop_runs_authorized=false`、`executed=false`；不创建任何航次 marker。

任一来源/hash/配置/options/模型/推理/场景/有限性/单位/因果检查失败即保留失败 receipt 并停。root 独立审核源修复、实际 MATLAB 记录和完整候选锁后，才能冻结并另行放行最多六个 fresh DEV 配对航次。任务书不授权任何 Plant；原逐场性能/安全门槛和所有失败保留规则不变。
