# C5 主动变形应用分层核查

输入包含 72 条 C5 parent-review batch 记录（原始 split 为 DEV 24 场 + VAL 48 场；其中 60 条新运行记录为 DEV 24 + VAL 36，12 条复用记录均为 VAL）及 48 场 TEST；这不是 72 场独立 DEV。TEST 统计使用米制未舍入 Q，W/L/T 按 ±1e-12 m 判定。完整分组数值见 `morph_active_count_performance.csv`，输场见 `morph_active_count_losses.csv`；该表以 `analysis_active_arm_group` 和 `analysis_task_group` 标明分组，因此同一场景可在 ALL 与具体任务组中各出现一次。JSON 中的 `loss_scene_ids` 按数据集×活动臂组×任务组保存名单。
活动臂数口径：DEV72 batch 由 scene_specs.csv 的四个 target_a*_m 相对 0.15 m 基准计算；TEST48 由冻结 scenePacks 的 rho_true 实际变化计算，并逐场验证活动臂掩码和配置目标一致。

冻结 TEST 共享场景中记录了 96 个实际活动臂实例；实际伸展幅度范围为 0.03–0.1 m，活动段 `rhoDot_true` 峰值范围为 0.05–0.05 m/s。全 TEST 的 `rho_hat` 为常值 0.15 m，`rhoDot_hat` 为常值 0 m/s。各任务参考速度/加速度范数峰值详见 JSON 和逐场 CSV。

方法范围是位置环补偿；原 B 姿态内环保持不变。本核查不声称姿态精度或双环学习收益。

TEST 分层是在冻结场景上的事后描述，不是预注册验收。`NONE` 与变形组对应不同场景，不能解释为同一轨迹/风场下的形态开关反事实；分组表现也不能单独证明形态规划、净空、能耗或形态估计收益。

复现命令（PowerShell 7）：
```powershell
$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:PYTHONDONTWRITEBYTECODE='1'
python reports/c5_active_morph_application_20261024/data_audit_v1/audit_active_morph_subgroups_v1.py
```
