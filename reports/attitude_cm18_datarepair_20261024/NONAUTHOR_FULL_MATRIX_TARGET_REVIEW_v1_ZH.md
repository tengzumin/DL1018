# 非作者复核：三轴直接补偿目标诊断

2026-10-25。只读审查 `audit_full_matrix_replacement_target_v1.m` 与实际结果 JSON；未读 raw、未运行 Plant、训练或模型推理。

源码 SHA256：`fe48f2d9d812cfa92364bd859490858a0e3eec01b3e6e80c773c829f9975042c`。结果 SHA256：`bdb0ba18cd9d81aa176157c58f665c6ca2a0eb8946e75c3f652ea18ccffabee3`。两者与冻结 pin 一致。

公式与接口吻合：未裁剪/饱和时，分配器映射为 `G = Jtrue⁻¹ [Ct(C0⁻¹[0;J0])]torque`；于是 `alpha(c)-alphaBS=E0-Gc`，旧 residual 标签 `d_old=E0+(I-G)c_old`，回到同状态 BS 的直接补偿解为 `c*=G⁻¹E0`。实现保留 `Ct/C0`，对原请求、无补偿、旧标签和 `c*` 重放实际 allocator。beta 使用引擎原有 `k*dt` 时钟（比日志事件时刻提前 1 ms），先限幅后缩放，并分别保留施加加速度与 beta 前原始网络输出目标。

四场（各 1999 个事件）的 phase 计数均合计 1999。与旧 yaw 标量结果逐场交叉核对，标签差 RMS 最大绝对偏差 `3.33e-16`，精确输出旧标签时的 yaw 误差偏差小于 `1e-16`；直接目标/matrix 恒等式最大闭合 `1.23e-13`。四场 `G` 均满秩，最大条件数约 `4.05`（T1）和 `5.71`（T3）。旧标签与 beta 修正后的 `c*` 均无输出限幅、allocator clip 或电机饱和。受限 allocator 的 `c*` 加速度误差 RMS：roll/pitch 约 `2.4–3.0e-14`，yaw 约 `2.2–3.35e-15`，均为数值舍入量级。

结论限于依赖真实惯量、形态、风和当前记录状态的离线单步目标兼容性。它不证明重标注后模型可学或闭环会改善/稳定，也不否定带历史动作输入的 residual 学习可能收敛到递归固定点。源码有一次冗余 `tauNom` HDF5 读取，不影响结果；不修改冻结源码。
