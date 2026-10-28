# Full72 姿态候选与 C5 父级审计补记

日期：2026-10-27

## 决定

GRU_STREAM_COSINE_TRACKING_HEAD_FULL72 保留为失败的开发筛查，不进入 TEST，也不扩成论文候选。它的部署输入与安全审计通过，但高频组任务姿态不达标；此外训练场景与全部 72 个评分场景重叠，结果只能作为开发诊断，不能作独立泛化证据。

## C5 对照审计

冻结 C5 v3 轴坐标候选的父级 raw 审计完成：72 场全 PASS，其中 60 场逐 raw 审计，12 场按 raw/status SHA 复用既有审计；新审计复算 118,080 个更新事件，最大方程偏差为 `6.0674e-13`，未新增 Plant，也未访问 TEST。证据：`reports/c5_axis_coordinate_parent_audit_prep_v3_20261027/audit_output_v2/C5_AXIS_COORDINATE_DEV72_PARENT_RAW_AUDIT_v2.json`，SHA-256 `ac57547a91db6e55c4010af477b742ec6308efc0de4288103bdbe5e7a7f75fbe`。

Full72 冻结评分 JSON 仍保留其生成时的“60 场 C5 raw 待审”说明，不修改历史评分文件。该限制现由上面的独立审计补齐。B 的历史 runtime 身份缺口仍保留在原评分报告中，因此不把这次 C5 审计说成已经消除了 B 的全部来源限制。

## GRU 候选结果

从冻结的 `FULL72_PAIRED_SCORE_v1.csv` 独立重算，比较均采用候选减基线，负值表示候选较低：

| 场景组 | 位置 Q 对 B | task SO(3) 对 B | inner SO(3) 对 B | task SO(3) 对 C5 |
|---|---:|---:|---:|---:|
| ALL72 | 68/72 胜，均值 −5.929 mm | 41/72 胜，均值 −3.889 mrad | 65/72 胜，均值 −1.878 mrad | 32/72 胜，均值 −0.0145 mrad |
| W09–W14 | 24/28 胜，均值 −1.004 mm | 2/28 胜，均值 +4.038 mrad | 25/28 胜，均值 −1.689 mrad | 7/28 胜，均值 +0.0582 mrad |
| W15 | 6/6 胜，均值 −2.010 mm | 6/6 胜，均值 −3.062 mrad | 6/6 胜，均值 −1.946 mrad | 2/6 胜，均值 +0.0739 mrad |

候选没有电机饱和、广义指令裁剪或倾角限制。高频问题不是这些安全限幅触发导致的。配对路径诊断显示，候选对自身 filtered attitude reference 的 inner 误差更低，但其外部 task-to-command/reference 链与 B 有差异；不能把 inner 改善等同于 task 姿态改善，也不能据路径 RMSE 拆出未经证明的因果比例。

## CM18-A1 现有筛查的边界

CM18-A1 12 场审计记录覆盖其 X18 推理输入、forward、输出 clip、beta、保持补偿与固定 `J0` 力矩映射；部署输入没有 `Jtrue`、`Jhat`、`Jdot` 或风真值。其离线监督标签使用 Plant 的 `Jtrue/JdotTrue` 和风力矩，属于应在论文中披露的物理教师监督，不是运行时输入。

现存 A1 paired `SO3_RMSE_deg` 是 actual attitude 对 filtered reference 的 inner 指标，不是对外部 task attitude 的 task SO(3)。高频三场 A1 inner 均值为 `1.4561°`，C5 为 `0.8764°`，B 为 `0.8635°`；A1 仅 1/3 场胜 C5。A1 的旧 raw MAT 现已不在其 run 目录，task SO(3) 缺失，因此不将其升格为高频解决方案。A1 12 场审计记录中的 16 次 yaw clip 属于 T3/W02，不属于 T3/W14；W09–W14 中只有 T1/W14 有 77 次 yaw clip，T2/W09 与 T3/W14 均为零。该分布不能解释全部高频退化。

## 下一步门

仅在审核通过一个针对高频任务姿态的单因素候选任务书后，才运行冻结的开发筛查。每个候选都必须报告 task SO(3) 与 inner SO(3)，复用身份一致的 B/C5，不重跑基线；训练只用锁定 TRAIN 数据，VAL 用于开发选择。候选通过开发门前 TEST 继续封存。
