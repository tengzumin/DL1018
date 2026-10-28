# DSSM14 表示诊断预登记

本阶段只做固定模型的离线表示诊断；不访问原始 MAT，不读 VAL，不训练、不调用 Plant/GPU/TEST。只在主审检查本计划与脚本 SHA 后运行全部 TRAIN。

## 冻结身份

- 唯一模型 `CORRECTED_DSSM14_SEED2026102001_FINAL60000`；源运行 raw SHA `f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5`，数组身份 `8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26`。
- DSSM encoder 源 `teacher_models.py` SHA `7d38948b0ea2f70ec7d1f3c433063cdc7f264080e5f717262e56ba4fd8ec1c22`；训练目标/端点源 `teacher_data.py` SHA `3d6ec20f544cda2ec99c3bddf17e595a75683c90fbd6b542475d006b6d2badad`；训练器 `fit_models.py` SHA `31a08407f5b3fe66b42a7e930925e5ae4cdabfa0a764c218356eedb82ca4e9ff`；数据注入链 `pair_workflow.py` SHA `a82f92465587f64f60b3c3109875a480a8ae164bf8562670808347820dbc233b`。
- 固定 checkpoint `final_step.pt` SHA `544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5`，payload 为 DSSM14/seed 2026102001/step 60000。训练 normalizer NPZ SHA `520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404`；脚本要求其中 mu/sigma 与 checkpoint buffers 逐 float32 相等。TASKBOOK 的 `normalizer identity=533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0` 是单独记录的模型/数组身份，不与文件 SHA 混用。
- 导出清单将该 checkpoint 映射至 DSSM14 MATLAB 导出 SHA `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`；已有 G6 parity 报告引用相同 checkpoint/导出 SHA，DSSM feature/output 最大差分别 `9.690539659601427e-08`、`6.75780600312148e-07`，容差 `1e-5`。本诊断只读两份 JSON 清单，不读导出 MAT。
- TRAIN sidecar 索引 `TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv` SHA `4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190`；1536 条 sidecar 已由既有 parent gate 全部 SHA 核验。只读其中 `TRAIN` 记录及对应 `fixed_model_sidecars` 文件。

## 固定样本与时间

全 TRAIN 每 run 取四个由原 stride-5 合法端点组成的窗口：其 `event_time_s` 首个不小于 5、10、15 秒的端点，以及最后一个 stride-5 端点。端点位置集合仍为 0 基 `31+5k`；选择依赖 sidecar 中的时间列，脚本记录实际时间，不用“索引×0.01”推定时间。对 row0=0.01s 的既有样例，预期位置 501/1001/1501/1996 对应 5.02/10.02/15.02/19.97s。最多 6144 个窗口；32 行 X14 按时间正序，target 为同端点 `Y_clip`（float32 训练标签）。phase 取该端点 sidecar `phase_code`。

小批 smoke 固定三条 TRAIN run，每 task 一条：

- FIG8_3D：`G02_P_TEACHER_DL1018_TRAIN_T2_C00_W00_ACC_FIX_V1_B`
- HELIX：`G02_P_TEACHER_DL1018_TRAIN_T1_C00_W00_B`
- SQUARE：`G02_P_TEACHER_DL1018_TRAIN_T3_C00_W00_B`

smoke 只核对四个端点的时间选择、输入/身份守门、CPU PyTorch float32 phi/output 与该 sidecar 同端点 `pred_raw_valid` 的 parity；不做近邻推断。

## 表示对照

不导入旧 training runner。最小 CPU 模型只按冻结 `teacher_models.py` 中 DSSM14 运算搭建，checkpoint state dict 严格加载；每个 32×14 窗口独立零状态，先用模型内固定 mu/sigma 得到 float32 normalized history `z`，再算 float32 `phi33` 和未 clip readout。与 sidecar `pred_raw_valid` 的输出差以已存在 G6 parity 容差 `1e-5` 守门。

全 TRAIN 比较仅在 `(task, role, endpoint phase_code)` 内进行；候选必须来自不同 run 和不同 `cache_scene_id`。使用 RUNS 冻结类别，不新推频率阈值：`wind_band` 原样报告，其中 `W09_W14` 是现有计划 HF 组，`W15` 单列；同时保留 `wind_cell` 作同/跨风判断。

- 精确相同只定义为模型实际 float32 normalized `z` 或 `phi33` 逐字节相同；按 task/role/phase 分组，并剔除同 run/同 scene 对。
- 连续距离：历史 `dX = sqrt(mean((z_i-z_j)^2))`，对 448 个数求均方根；表示 `dphi = ||phi_i-phi_j||_2`。每个样本分别保留同一 wind_cell / 不同 wind_cell 中 `dX` 最近和 `dphi` 最近的跨 run/scene 对，按无向 pair 去重并记录被多少 query 选中。
- 每个候选 pair 一并报告两种距离、同端点 `Y_clip` 三轴差/模、固定 readout 原始输出差/模、wind_cell/band、run/scene/时间/phase。近邻不设二值阈值，不把运行条数或 pair 数当独立场景数。

该诊断能识别这批预登记 TRAIN 样本中固定 phi 的精确合并及其训练标签差，也能描述近似历史/phi 与目标差的连续关系。冻结 phi 相同而标签不同只表明当前固定表示加 readout 无法区分该对；不证明 DSSM 参数族数学上不可辨识或重新训练 encoder 仍无法分开。没发现碰撞也不证明表示充分；全部结果不支持闭环因果结论。

## 资源、输入保护与输出

CPU 单线程，批量 128 前向；全 TRAIN 仅 6144 个历史（float32 约 10.5 MiB）、phi（约 0.8 MiB）及标签。分组逐 query 流式计算距离，不建或保存全 pair 矩阵；无向候选对理论上限 `6144 choose 2 = 18,871,296`，实际另受 task/role/phase、run、scene 过滤。所有输入先核 SHA/stat，读取后复核；sidecar SHA 必须匹配已冻结 TRAIN RUNS 表。仅写本目录，输出总量设 100 MiB 硬上限。

主审审核本文件与 `inspect_dssm_phi_contract.py` SHA 并批准后才允许 `--full-train`。完成后冻结所有端点、距离、去重与汇总规则；原训练 VAL 至多按相同规则另跑一次，需主审另行放行，不允许调参或调门槛。
