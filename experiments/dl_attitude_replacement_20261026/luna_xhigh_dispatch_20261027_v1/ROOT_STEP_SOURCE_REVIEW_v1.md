# 主模型：复合头 step 实码审核

审阅日期：2026-10-27。对象：mlp15_composite_head_v1/candidate_runner_work/matlab/runtime/mlp15_attitude_step_v1.m；本结论不代替真实 DEV 入口审核或闭环性能。

- 当前输出 residual 使用更新前 before；观测与跟踪更新随后执行，输出不回写，满足本事件输出先于更新。
- 过去标签要求11个gyro端点、10个历史已发力矩，1ms连续采样，终点对应当前feature角速度；只用固定J0。该区间残差是采样近似，不能称为真实扰动。
- 残差RLS需前/当前beta均成熟；tracking需当前beta成熟且已有上次事件。两路起点可差一个事件，已作为明确设计语义接受。
- tracking使用当前phi、当前T/s、Joseph更新后的P和实际事件时间差；两种增量合并后一次Frobenius范数投影。无新增惯量重建。
- dmax裁剪后理想交叉项抵消不再普遍成立；权重有界与P正定不能证明闭环稳定。当前只能安排单因素方向验证。

决定：保留数值核心，不改增益或门控。实际DEV入口与真实C5配置集成仍未通过，Plant保持0授权。由Luna极高在隔离v2修复，主模型审核后再决定首场。
