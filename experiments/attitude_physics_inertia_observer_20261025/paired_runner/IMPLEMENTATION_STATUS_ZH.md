# 配对 runner 隔离实现状态

状态：代码与纯静态检查完成，待 root 审查。尚无 MATLAB 解析/执行、Plant 航次、合成审计或完整 source lock。

- 同一 `run_paired_observer_closed_loop.m` 从 C5 DEV72 runner 复制位置路径，并在两臂强制 delayed prediction、M110 mask、FEATURE/γ=12 C5 position head、100 Hz position/attitude event、1 kHz Plant。`make_paired_c5_options.m` 用同一模型/初始 RBF 权重构造两臂；规范化后仅 `paired_arm` 和三个 attitude RBF 开关不同。
- Baseline 保持 online attitude RBF output/update；candidate 在相同事件调度和 `ir` 后逐 1 ms 调用 v2 helper `prepare`，将 signed `estimateTorque_Nm` 送入同一 BS 接口。allocation 返回后，仅把 `a.clipped_generalized(2:4)` 与 `t(k)` 交给 `commit`。candidate 不进入 attitude RBF inference/update，也不把候选力矩记作 RBF 输出。
- `bind_paired_fixed_j0.m` 由 `controller_parameters(...,'fixed')` 写入显式 `cfg.attitude_replacement.J0_controller_fixed_kgm2` 及 SHA；runner 对冻结字段与 `fixedController.inertia` 校验矩阵和 SHA，v2 helper 只用冻结 J0。原 v1 helper 副本保留作来源身份，不被 runner 调用。
- `extract_dev3_specs.ps1` 已用 PowerShell 7 从固定源只提取三个精确 DEV 行及 header，写入 `configs/scene_specs_dev3.csv` 和逐行 SHA receipt；源 SHA 为 `d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3`，隔离 CSV SHA 为 `bd68a24a0d87764e8d6fabcf5372d8a36a38104a3a246df6523f514548ac7630`。`make_paired_dev_scene.m` 现以三场之一的 scene ID 和冻结 cfg 为输入，只读取隔离 DEV CSV/receipt，校验 `split_code=2`、`source_split_code=1`、`sealed=0` 和 seed 等身份后构造 `out.spec/out.scene/out.metadata`。尚未调用生成器，实际 payload 留待下一阶段生成与锁定。
- `CODE_ONLY_STATIC_AUDIT.json` 包含 39 个隔离 MATLAB 源 SHA、原始依赖 SHA、三个 DEV 原始行 SHA、隔离 CSV/receipt/提取脚本 SHA、草案与 v1.1 addendum SHA、词法符号闭包；静态脚本核对 candidate 只旁路姿态 RBF、两臂仍共享 C5 位置零步长兼容调用及 Head 覆盖。`RUNNER_PATCH_AGAINST_C5.patch` 是隔离 runner 相对 C5 DEV72 源的差异。检查命令：`python experiments/attitude_physics_inertia_observer_20261025/paired_runner/static_check_paired_runner.py`。结果：`STATIC_CODE_PASS_PENDING_ROOT_REVIEW_NO_MATLAB`。

下一阶段仅生成并锁定场景 payload 的 MATLAB 入口：先取得冻结 cfg，调用 `activate_paired_runner()`、`cfg=bind_paired_fixed_j0(cfg)`，然后对三个明确 DEV ID 各调用一次 `out=make_paired_dev_scene(sceneId,cfg)`。逐一保存并规范化哈希 `out.spec/out.scene/out.metadata`，核对三场 seed/字段与隔离 DEV CSV；本阶段不调用这些入口。
