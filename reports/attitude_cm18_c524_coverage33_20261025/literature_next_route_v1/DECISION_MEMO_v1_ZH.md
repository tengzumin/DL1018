# 决策备忘录：下一步先做输入充分性诊断

日期：2026-10-25。**路线判断，仅基于已有 DEV 证据；不是独立验证。**

## 决定

首要动作选**输入充分性诊断**，暂不安排源码身份闭合重跑。理由是后续诊断最直接回答当前未决问题，而 C5_COVERAGE33 已有完整场景身份闭合，且本地审计未发现能解释误差的接线、事件、标签方程或前向实现错误。重跑代码身份只有在输入锁/源码 SHA 复核出现冲突时才应先行。

## 依据

- C5_24 对同栈 C5+在线 RBF 的固定 12 场筛查为位置 Q 2胜/10负、SO(3) 2胜/10负；报告记录逐场日志审计、64 行 MATLAB/Torch parity，最大差 1.42e-14，未发现已查的接线、单位、符号、频率或开关错误。[结果](../../attitude_cm18_c524_screen12_20261025/C524_SCREEN12_RESULT_v1.md)、[根因决策](../../attitude_cm18_c524_screen12_20261025/C524_ROOT_CAUSE_DECISION_v1_ZH.md)
- 较新的 C5_COVERAGE33 在 15 场 DEV 中位置 Q 仅 3/15 胜、SO(3) 1/15 胜。15/15 官方 scene audit 为 PASS，binding、模型、checkpoint、候选 run_start/status/raw 的 SHA 与身份均匹配；逐场标签、X18、前向输出也可按既有链路重建。[闭环结果](../C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md)、[诊断](../C5_COVERAGE33_ROOT_CAUSE_DIAGNOSIS_v1_ZH.md)
- 固定模型 TRAIN/DEV NRMSE 为 0.015295/0.267078（DEV/TRAIN 17.46 倍）；首个形变事件的 0.897 rad/s² 映射误差也在教师状态存在。身份重跑不能区分可用输入不足与拟合/泛化不足，输入诊断能直接检验仍未回答的问题。[拟合报告](../fit_generalization_v1/FIT_GENERALIZATION_REPORT_v1_ZH.md)

## 依赖与停止条件

依赖：使用现成、哈希已审的 TRAIN33/DEV15 划分和冻结标签；先锁定新的输入组定义与统计门槛，按 scene 阻断报告首次形变、active-phase 和逐场结果。不得把由 command 与 z 可重建的 rho/rhoDot/phase 额外拼接称作新增信息。旧离线可辨识性任务书明示“未审批 / 已取代 / 未执行 / 不得运行”，不能直接执行；需另立有效方案。[旧任务书状态](../C5_CM18_OFFLINE_IDENTIFIABILITY_TASKBOOK_v1_ZH.md)

出现任一输入/模型身份 SHA 不匹配、标签闭合复核失败、候选部署信号无法从允许来源因果重建，立即停止诊断；若输入充分性比较未达到事先固定的实质改善门槛，也停止这条特征假设，不自动转训练、闭环或 TEST。若身份门失败，才将源码闭合改为先决动作。现有 12/15 场和拟合差距均属开发证据，不能写作独立确认。

核心输入 SHA-256：C5_24 结果 `b2bb74826dd11ab82f6af714df15345b1a9db419dc93412204e075a694857988`；C5_24 决策 `f040721064031668b7b8ae9bc14c444fc605645a462d22c9754e168a5de9c2d6`；C5_COVERAGE33 结果 `41c38fe91ff121be1853826db94e830ad4c3a76ebee8623bcab0de5cd6a2a3c3`；泛化诊断 `d2305c87118e638345b9da13784d3c58d00d01a9cbf3394d5866befdbafba34c`；根因诊断 `d564d77133e2752d327450c9cedb5d7c3d946c1988dc58fc7720fa39b25d4894`。
