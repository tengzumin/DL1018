# 非作者只读审查：匹配 TRAIN 来源与位置分支配对探针

审查对象：`ROOT_MATCHED_POSITION_PROBE_TASKBOOK_v1_ZH.md`（SHA256 `D4974F42B3B305FA9728BBBF9AB924BF7DC41099BBF404BE2CEA2DACF06898C2`）。本审查只读任务书、配置、收据和清单；未读取 raw MAT、模型权重或缓存，未启动 Plant。

## 现有 TRAIN/VAL 身份

仓内当前 DL1018 数据计划列出的 TRAIN/VAL collector 是 B、POS_OFF、P_INIT_STUDENT，没有 C5/M110 collector。B/POS_OFF 各有 768 TRAIN、48 VAL；P_INIT_STUDENT 有 384 TRAIN、48 VAL（`configs/dataset_plan.json`、`matlab/scenes/make_scenes_dl1018.m:275-278`）。G02 收据确认 B/POS_OFF 的姿态事件已导出；`controller_options_dl1018.m:10-20` 中两者姿态 RBF 开关默认开启，但位置路径分别是 B 位置 RBF 与 POS_OFF 关闭位置 RBF，不能替代当前 C5 位置分支。

P_INIT_STUDENT 使用初始位置模型、online head 和 PCF coordination（`matlab/runtime/collect_position_role_dl1018.m:18-31`）。G04 收据的姿态事件数为 0，表示该 G04 collector 未导出/验收姿态事件；不能据此断言运行时 RBF 未执行，因为其 controller options 未关闭默认姿态 RBF。它仍不是当前固定 M110 C5/selected position branch，故不构成已认证的匹配轨迹。

旧 KAN 复用清单（SHA256 `354C9FC22FA8F2A10EFC3057DE5306E16CB2CFE232A886CECB22FCB9E97EFB60`）记录 TRAIN128：T_B64、T_PCF64；VAL32：T_PCF32。其 raw 来自旧 DL1009 的 B 与 `k1_command_filter_update_coordination_v3_5/.../P_CF` 来源。既有独立审查明确指出该 VAL 是旧 T_PCF，不能认证为当前 C5 位置输出分布。A1 当前 runtime 任务书锁的是 C5/PCF 位置路径和 `[1,1,0]` mask，且明确禁止复用旧 KAN 功能或权重。结论限于：已检查的清单/收据没有认证一组满足 C5 位置身份且带原姿态 RBF 事件的 TRAIN+VAL；这不证明仓内绝无其他可重导 raw。

## 四航次任务书审查

配对设计的核心成立：固定两条原始场景的外生时序和初态，在同一 parent engine、同一 Plant/BS/滤波/分配器和姿态 RBF 条件下，各跑 B-RBF 与 C5 位置分支。唯一处理包是 B→C5 必需的位置 runtime/PCF/mask/position-RBF 开关差异。这样可估计在这两条固定场景上切换完整位置算法包对轨迹及冻结 A1 预测误差的总影响。任务书已明确旧 B producer 源码未恢复，不把新 B 说成历史 B 逐步复现；也明确不能把不同闭环轨迹对照解释成 NN 内部组件因果，不能据此归因于风项或 alphaXY 代理。选择两条既有失败场景使探针适合定向机制筛查，但不支持跨场景总体推断；任务书对此有边界说明。

一个需在 release 前闭合的配对状态身份细节：逐航次应从各自规定的初始状态独立启动，并证明 C5 的 position W0/PCF 历史、B 的 position-RBF 状态、以及姿态 RBF 初值均未从前一航次带入。任务书已写明姿态 RBF 同初值，但未明确列出两种 position 分支各自的初始可变状态重置/记录。若 parent runner 每次入口本来会重新初始化，源审与 run_start 记录即可证明，不需额外实验。

25% 与 `0.02 rad/s²` 双门可作为预登记工程优先级规则；任务书已把它限定为非显著性、非论文验收门。为防执行口径差异，建议加一行精确定义：每场以全部 1999 个共同有效事件计算 `R_s = sqrt(mean((pred_yaw−target_yaw)^2))`，令 `Δ_s=R_s(C5)−R_s(B)`、`p_s=Δ_s/R_s(B)`；仅当两场都满足 `Δ_s≥0.02 rad/s²` 且 `p_s≥0.25` 才过门。这样把“增加25%”的分母和事件集固定，避免事后改口径。

审查结论：未发现配对处理包或因果解释上的原则性错误；正式 release 前应锁定每航次 position mutable-state reset 证据，并将双阈值的 per-scene 计算式写入任务书。该准备审查不构成 Plant 放行。
