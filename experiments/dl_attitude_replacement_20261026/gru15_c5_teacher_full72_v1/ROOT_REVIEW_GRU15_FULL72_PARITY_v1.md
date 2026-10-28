# 主审记录：GRU15 full72 MATLAB parity

日期：2026-10-26。只读检查本地训练权重与 parity fixture，没有调用 Plant 或访问 TEST。

- 训练 receipt：`PASS`，CUDA `cuda:0`，60,000 steps，72 场 / 143,928 事件；`plant_called=false`、`TEST48_read=false`。
- 权重 SHA-256：`cea74bb1f178b4716f9d10780bd643269703c0583479c2e6430998aecafea11c`。
- PyTorch gate 次序 `reset,update,new` 与 MATLAB 逐事件实现相同；15 步因果窗口、零初态、输入 normalizer、输出 RMS 均来自同一训练 receipt。
- MATLAB R2025b `checkcode` 对 forward、step、audit 三文件均为 0 diagnostics。
- MATLAB 与 Python 最大绝对误差：直接前向 `2.04530073e-7 rad/s²`；经 runtime history step `2.04530072e-7 rad/s²`，低于 `1e-5 rad/s²` 容差。
- parity 审计报告：`audits/MATLAB_PARITY_GRU15_FULL72_v1.json`，状态 `PASS`。

## 放行边界

通过仅说明冻结 GRU15 在 Python/MATLAB 间一致，不说明输入因果审计、闭环效果、稳定性或应用可行性已通过。接下来仍须完成隔离 runner source lock、No-Plant 13-D 特征复核和单场 G1/W00 工程门；在逐场人工复核前不启动余下五场。
