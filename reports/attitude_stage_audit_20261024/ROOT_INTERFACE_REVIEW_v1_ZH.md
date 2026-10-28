# 姿态补偿替换：主审核记录

范围：只替换原姿态 RBF 残差补偿器，保留 C5 位置环、姿态反步主体、命令滤波、分配器和物理模型。C7 暂停，历史 C5 证据不改写。

## 已实读源码的结论

- C5 冻结 runner 的 `attitudeFusionActive` 分支允许在姿态 RBF runtime/output/update 三开关均关闭时继续执行姿态事件与模型输出；`lambda=1` 直接采用学习模型力矩。
- 融合分支内仍会调用 `rbf_mimo_update`，但 updateDt=0；关闭 output 后原 RBF 力矩清零。不能仅因源码存在调用就声称仍混合 RBF，也不能仅凭开关就证明无影响。运行检查应验证权重不变、最终补偿力矩等于模型力矩。
- `attitude_head_v39` 字段存在会选择 X29 evaluator，即便 enabled=false；同时必须填写既有接口要求的 gamma=0.002、sigma_per_s=0.02、projection_fro=0.20。关闭 head 时这些参数不应产生权重更新。
- KAN 输出为归一化 body 角加速度残差，经限幅、dmax、beta 和 J0 映射为补偿力矩，由 BS 从名义力矩中减去。原 C5 的固定名义参数条件必须保留。
- 32 个姿态事件之前模型力矩为零；不得删除热身区间来提高主指标。
- `command_filter_step` 返回当前滤波状态为 reference，下一状态另返回；runner 同行保存 ir.euler/ir.euler_rate。原日志的前 20,000 行 state 与这些控制记录对齐，末尾第 20,001 状态没有对应参考，不可自行补造。

## 评价口径

主姿态角指标为实际姿态与滤波后参考的 SO(3) 夹角 RMSE。任务 yaw、逐轴 Euler 误差和峰值另报。

几何角速度误差采用 `omega - R_actual' * R_ref * omega_ref`，其中 `omega_ref = T(eta_ref)^(-1) * etaDot_ref`。直接相减两个姿态各自的 body 分量仅可列为坐标分量诊断。

全 0–20 s 位置 Q、安全和执行器表现必须同时报告。保持位置算法和初始权重一致，不意味着替换姿态后闭环轨迹与在线权重历程仍相同。

## 当前证据边界

模型结构与原 normalizer 数组一致已经由主审核实际读取验证，见 `ROOT_MODEL_READONLY_AUDIT_v1.json`。这不证明运行一致性，也不证明迁移到 C5 后有效。

单场已有 DEV 的独立诊断见 `ROOT_SINGLE_DEV_ATTITUDE_METRICS_v1.json`：几何角 RMSE 约 0.002056 度。该结果说明此场基线改善空间小，不能推广到全部场景或据此选参数。正式比较前仍需独立复核时序与实现。

当前尚未批准启动本姿态阶段的 Plant 或训练；先完成隔离接入与无 Plant 一致性检查，再由主审核冻结开发场景和执行任务书。此处是内部工程检查顺序，不要求用户重复批准已授权研究范围。
