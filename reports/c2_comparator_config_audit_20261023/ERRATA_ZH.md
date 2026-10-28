# C2 配置审计报告勘误

本勘误补充已冻结的 `COMPARATOR_AUDIT_SUMMARY_ZH.md`，不修改原报告、CSV、JSON 或 `AUDIT_INDEX.json`。

1. 报告中“reference/initial/wind/arms 最大输入差 4.44e-16 N”表述有误。B/ON1 输入配对全数组逐元素完全相等，差值为 0。`4.44e-16` 是主审对位置 BS / 注入力物理方程复算的残差，单位应按该检查自身量纲表述，不能称为输入差或统一写成 N。
2. `cfg.plant.inertia = diag(.012,.012,.022)` 是保存配置中的字段；它不能单独证明实际 `fixedController` 使用该惯量。`simulation_parameters(cfg,arm_initial,zeros(4,1))` 与 `controller_parameters(...,'fixed')` 会按冻结源码从质量分布重建控制器名义参数。后续无 Plant smoke 保存的 mass、J0、C0 是按这条冻结源码链重建的值，不是历史运行快照。
