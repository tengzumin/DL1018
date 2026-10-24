# 历史 TEST 场景输入重叠核对

**结论：** 对 `TEST_C10_34_J1/J2`，未发现与当前 C5 TEST48 的 48 个共享输入场景有完整外生输入重叠。旧场景的时间、初始状态和 yaw 相关数组与当前场景一致；位置、速度、加速度参考、风及形态输入数组均没有与当前任一场景逐位相同的数组。

本次只读取 incident JSON 的路径/ID 元数据、旧场景配置 MAT、旧 D1 `run_start.mat` 中的 scene 输入数组，以及当前 TEST48 冻结输入 MAT/索引。没有读取旧报告正文、历史 TEST 成绩、`raw_run.mat`、事件日志、轨迹状态误差，也没有调用 scorer。

旧配置文件位于 DL1009 的 `k1_position_attitude_fusion_v3/configs/blind_test_position_scenes_v3/`；执行快照取自 `kan_position_attitude_followup_v2/runs/D1/TEST_C10_34_J{1,2}/P_SLOW/.../run_start.mat`。配置与执行快照对齐 8/12 个共同数组；4 个形态/风字段（`arms.command`、`arms.rho_true`、`arms.rhoDot_true`、`environment_wind_I`）不同。两份旧来源分别与当前 48 场比较，均无完整 12 字段匹配。当前输入另有 `arms.rho_hat` 与 `arms.rhoDot_hat` 两字段，旧输入 MAT 未包含；因此不宣称 14/14 字段都可追溯，但多个共同核心字段已明确不同，足以排除同一完整场景。

逐字段精确匹配数（每个旧来源均相同）：时间、初始状态、yaw、yaw rate、yaw acceleration 各为 48/48；位置、速度、加速度参考、风、arm command、rho_true、rhoDot_true 各为 0/48。数组 shape/dtype 相同后直接逐位比较；JSON 附有输入文件哈希与关键外生数组哈希。
