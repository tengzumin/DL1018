# GRU15 full72 训练完成记录

训练任务书与训练 source lock 的哈希保持不变；这份记录补充其执行结果。

- 训练状态：`PASS`，单次 CUDA 训练，seed `2026102001`，60,000 steps，72 个开发场景、143,928 个事件，耗时 198.144 秒。
- 训练收据：`runs/C5_GRU15_FULL72_SEED2026102001/run_receipt.json`；无 Plant 调用、无 TEST48 读取、无 B24 数组读取。
- 冻结 MATLAB 权重：`gru15_attitude_weights_v1.mat`，SHA-256 `cea74bb1f178b4716f9d10780bd643269703c0583479c2e6430998aecafea11c`。
- Python/MATLAB parity：`PASS`；直接前向和 runtime-step 最大误差均约 `2.05e-7 rad/s²`，容差 `1e-5 rad/s²`。
- 训练成功仅证明离线拟合完成；闭环筛查尚未启动。闭环候选须另行按 `GRU15_CLOSED_LOOP_PILOT_TASKBOOK_v1.md` 通过 no-Plant 审计后运行。
