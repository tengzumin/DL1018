# 姿态物理 observer 的固定惯量 J0 校正（v1.2）

日期：2026-10-25。状态：合成审计候选；未冻结，未授权闭环航次。

旧 helper 把 `cfg.plant.inertia` 当作 `J0`。该字段是机身基准惯量；正式 BS 与姿态 RBF 使用 `controller_parameters(cfg, fixedPlant, 'fixed').inertia`，即初始臂长下由 `arm_mass_properties` 计算的完整分布质量惯量。两者不同，使旧 helper 的 `tau_shape`、`J0\r_tau` 与输出扭矩坐标均偏离配对基线。旧 helper 和 v1/v2 合成证据保持原样，不能作为校正后候选的放行依据。

新增 `phys_attitude_replacement_candidate_v2.m` 从显式冻结字段 `cfg.attitude_replacement.J0_controller_fixed_kgm2` 读取 `J0`，在 `init` 检查 3×3、实数、有限、对称及正定，并把矩阵保存在 helper 内存中。隔离 runner 必须在两臂共用配置中将该字段设为其固定控制器的 `P.inertia`，逐元素及哈希核对；不能直接使用 `cfg.plant.inertia`。候选的部署输入和 prepare/commit 时序不变。

`run_phys_attitude_synthetic_audit_v3.m` 以不对称的合成初始臂长构造非对角完整控制器惯量，实际调用 v2 helper，并将它的 `estimateTorque_Nm` 送入真实 `attitude_bs_step`；同时核对符号、轴序、observer 区间命令、因果性和裁剪。审计仅限 synthetic，不调用 Plant、场景、闭环 runner 或数据加载器。`source_lock_candidate_v3.json` 状态为 `NOT_FROZEN`；三场 DEV 配对航次仍须独立审核完整 runner/输入身份/源锁后才可放行，不读 TEST。
