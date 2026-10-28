# 姿态替换证据台账（2026-10-27 更新）

只记录可定位的本地数据/审计结果。六场延迟结果已收齐；GRU_STREAM 一次训练及六场筛查均已完成，工程通过、任务姿态未胜 C5，已关闭该版本的新增航次。本文不是论文通过或新搜索放行。

## 固定边界与开发数据

- 姿态控制沿用锁定 C5 位置栈和公共选项；控制器名义形态固定，Plant 仍按预设主动变形，`J0` 固定且 BS `Jdot0=0`，滤波加速度限幅 `[Inf, Inf, 6]`。姿态特征不含 `Jhat/Jdot_hat`、真实惯量/质量或 Plant truth；本轮未重建真实惯量。见 `experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/LOCKED_CFG.json`、`mlp15_c5_teacher_full72_v1/MLP15_C5_TEACHER_FULL72_TASKBOOK_v1.md`。
- full72 有 143,928 个 C5-RBF teacher 事件：TRAIN24 + 原 VAL48（并入 `VAL48_AS_DEV_TRAIN`）；无独立验证/checkpoint 选择。本轮 TEST 未读。训练误差和这些同源场景闭环都属于开发证据，不是独立泛化验证。

## 已闭环候选及机制检查

- 冻结 MLP 及 causal RLS 六场证据未达最终 B/C5 门槛。causal RLS root 汇总：姿态胜 C5 0/6，位置相对 C5 退化 13.38%。见 `mlp15_causal_head_v1/ROOT_RESULT_v1.md`、`ROOT_RESULT_v1.json`。
- Composite 六场也 FAIL：宏平均 candidate `Q=9.676 mm`、任务 SO(3) `28.082 mrad`、inner `19.583 mrad`；B 为 `9.143 mm / 27.613 mrad / 17.567 mrad`，C5 为 `8.357 mm / 26.428 mrad / 17.602 mrad`。root 决策记录姿态胜 B 1/6、胜 C5 0/6、位置相对 C5 退化 15.79%。见 `mlp15_composite_dev_v3/ROOT_SIX_PYTHON_METRICS_v1.json`、`ROOT_SIX_SCENE_DECISION_v1.json`。
- 六场 C5 teacher 同状态标签/时钟偏差相对冻结 MLP 误差不足以支持它为主要瓶颈；common-state shadow 也不支持 tracking 显著牺牲预测。见 `attitude_target_semantics_diagnosis_20261027_v1/REPORT.md`、`attitude_composite_common_state_diagnosis_20261027_v1/REPORT_v2.md`。
- 同 1,200 个 C5 记录状态上，BS/RBF 的负局部 `λmin` 为 0/1200，冻结 MLP 为 711/1200；该局部差异支持继续研究反馈/记忆假设，但不证明闭环主因。固定神经 nominal-τ 特征后负值仍存在，说明 nominal-τ 路径不是唯一来源。见 `attitude_rbf_local_reference_20261027_v1/REPORT_v1.md`、`ROOT_SAME_STATE_REFERENCE_SUMMARY_v1.json`、`attitude_nominal_torque_path_diagnosis_20261027_v1/REPORT.md`。

## 单事件延迟：六场最终结果

六个候选 raw 均完整 20,000 transitions、状态 `STABLE`；v3 独立 raw replay 均 PASS，电机饱和/广义裁切均为 0。300-event queue 与 release0 配置拒绝检查 PASS。工程完整性通过，性能 FAIL：

| 六场等权宏平均 | Q | 任务 SO(3) | inner tracking |
|---|---:|---:|---:|
| one-event delay | **11.447 mm** | **30.820 mrad** | **27.851 mrad** |
| matched v3 no-delay | 9.676 mm | 28.082 mrad | 19.583 mrad |
| B | 9.143 mm | 27.613 mrad | 17.567 mrad |
| C5 | 8.357 mm | 26.428 mrad | 17.602 mrad |
| prediction-only | 9.475 mm | 28.167 mrad | 20.047 mrad |

Root 决策为 `REJECT_ONE_EVENT_DELAY`：candidate 三项宏指标均差于 no-delay、B、C5，位置相对 C5 退化 36.98%；不扩 DEV72/TEST、不扫延迟/增益。原任务书仍说明这是时序区分实验而非已证明方法：`luna_xhigh_dispatch_20261027_v1/ROOT_ONE_EVENT_DELAY_TASKBOOK_v1.md`。

结果与审计留档：`mlp15_one_event_delay_v1/ROOT_SIX_PYTHON_METRICS_v1.json`、`ROOT_SIX_SCENE_DECISION_v1.json`、`audits/*_ONE_EVENT_DELAY_AUDIT_v3.json`。历史 v1 时间轴端点数假设和 v2 不存在的 `residual_torque_estimate_Nm` 字段问题均为 post-run audit 工具错误；v2/v3 correction 只修审计，不改 raw/控制/模型/评分，也未重跑 Plant，见 `ROOT_AUDIT_CORRECTION_v2.json`、`ROOT_AUDIT_CORRECTION_v3.json`。首轮 remaining-five wrapper 在 T1_C08 raw 已完成后因 MATLAB path 找不到 v3 auditor 而失败；原 log 保留，该场随后单独 v3 审计通过且未重跑，后四场由留存的 remaining-four 命令完成。见 `audits/FIRST_FLIGHT_REMAINING_FIVE_v1.log`、`FIRST_FLIGHT_RAW_AUDIT_V3_T1_C08_W15.log`、`FIRST_FLIGHT_REMAINING_FOUR_COMMAND_v1.txt` / `.log`。

## 研究状态

### GRU_STREAM 六场最终筛查结果

GRU_STREAM 一次 60,000 步训练已完成，冻结模型 SHA-256 `963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021`；仍是 C5 TRAIN24 + 原 VAL48_AS_DEV_TRAIN 训练数据，不是独立验证。实际模型 Python/MATLAB 全序列 parity、真实 C5 cfg/which 与 release0 拒绝检查均 PASS。首场 `DL1018_VAL_T1_C08_W15` exit 0，raw audit PASS；root 独立 NumPy 重放 1,999 事件和 20,000 intervals，最大 raw output / full hidden / torque 差分别 `7.63e-14` / `3.49e-14` / `2.08e-16`，见 `gru_stream_dev_v1/ROOT_FIRST_GRU_TRACE_REPLAY_v1.json`。

六场均完成并通过 raw audit，安全/clip/tilt 计数均为 0；MATLAB 后续四场批次 session 29682 exit 0。root 独立从三组原始 MAT 复算，宏平均如下：

| 方法 | Q (mm) | 任务 SO(3) (mrad) | inner tracking (mrad) |
|---|---:|---:|---:|
| GRU_STREAM | 8.47238 | 26.93080 | 17.53797 |
| B | 9.14324 | 27.61315 | 17.56676 |
| C5 | 8.35653 | 26.42751 | 17.60190 |

GRU 位置胜 B 5/6、胜 C5 2/6；任务姿态胜 B 3/6、胜 C5 0/6。位置比 B 降低 7.337%，比 C5 高 1.386%；任务姿态比 B 降低 2.471%，比 C5 高 1.904%。三场高频任务姿态也均差于 B，尽管该组 inner tracking 宏平均比 C5 小。不能将 inner 替换成任务 SO(3) 来通过门槛。完整分组和全部输场见 `gru_stream_dev_v1/ROOT_SIX_PYTHON_METRICS_v1.json`。

root 决定 `SCREEN_FAIL_NO_DEV72_OR_TEST_EXPANSION`，当前 release 为 `CLOSED_SIX_SCENE_PERFORMANCE_FAIL`；实际新增 6 航次、1 次 60,000 步训练。Stage1、Stage2 的执行 release 快照保留，未改源码/模型、未读 TEST、未扩 DEV72。放行前 pending、首场后已完成 1 的状态均属历史快照。下一步只读核对同状态训练拟合/近似动力学目标与姿态参考可行性，尚未授权新训练或新结构搜索。

最终论文/性能目标仍未达到；full72 训练包含原 VAL48，六场开发筛查也不是独立 TEST。单事件延迟方案与本版 GRU_STREAM 航次均已关闭。相关范围与审阅记录见 `ARCHITECTURE_MEMORY_SCOPE.md`、`luna_xhigh_dispatch_20261027_v1/ROOT_STREAMING_GRU_TASKBOOK_v1.md`、`STREAM_GRU_TASKBOOK_REVIEW.md`、`GRU_STREAM_PILOT_SOURCE_REVIEW_v1.md` 和 `gru_stream_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json`。

### 余弦学习率单因素验证

GRU32_STREAM72_COSINE_S2026102001 仅改变预定lr日程；原数据、初始化、normalizer和全部60000步scene/cohort/chunk/样本序列逐项一致。训练exit0，全72教师拟合向量RMSE从1.63953降为0.62654 rad/s²（降低61.785%），readout bias梯度范数降低97.422%；这是拟合机制证据，不是闭环通过。

随后六场全部完成、raw审计通过；root实际监督的MATLAB会话26858和91284均exit0，新增6航次、无对照重跑。宏均Q/SO3/inner为8.60663 mm / 26.73101 mrad / 18.20415 mrad；位置相对B改善5.869%、相对C5退化2.993%，任务姿态相对B改善3.195%、相对C5退化1.148%。任务SO3六场全胜恒定lr GRU，但相对C5的Q/SO3/inner均0/6胜，未达到原门槛，已关闭本版本，不扩DEV72/TEST。各场和风组见 `gru_stream_cosine_dev_v1/ROOT_SIX_PYTHON_METRICS_v1.json`，决定见 `ROOT_SIX_SCENE_DECISION_v1.json`，运行命令与资源见 `ROOT_EXECUTION_RECEIPT_v1.json`。

下一步只授权新的名义命令残差监督数据准备，训练/Plant仍0：同一C5记录上余弦GRU→教师RMSE约0.578，而教师→近似名义残差约0.969 rad/s²，支持进一步检验目标语义，尚不证明新目标会改善控制。端口审阅确认requested是分配器请求、realized才是Plant体轴力矩；零饱和时两者也可不同。匹配固定J0/C0命令模型的R_cmd包含分配等lumped不确定性，不应误称真实瞬时外力；见 `NOMINAL_RESIDUAL_PORT_REVIEW_v1.md` 和 `ROOT_NOMINAL_COMMAND_TARGET_PREPARATION_v1.md`。不重建惯量，不将真实Plant量或未来量加入部署输入。





### NCMD监督单因素闭环否定结果

新名义命令端残差标签经全72场独立复算；60000步正式训练1次、无种子搜索，normalizer/初始化/余弦lr与原cosine相同。实际新增6航次，MATLAB sessions51231/76826均exit0，6份raw独立复放PASS，全部无执行器饱和、广义指令裁剪和倾角限制。root独立读取候选/B/C5共18份raw，宏Q=9.11256mm、任务SO3=27.32962mrad、inner=18.53451mrad；相对B位置4/6胜、姿态3/6胜，相对C5两项均0/6胜。宏Q比C5差9.0473%，SO3差3.4135%，未通过姿态门，已关闭版本且不扩DEV72/TEST。三维八字无风位置10.20713mm差于B9.67965mm和C5 7.89645mm。此证据否定“只改当前监督目标即可解决姿态差距”，不能单独确认是模型容量、数据分布或在线适应哪个因素。后续两项同状态只读诊断由Luna xhigh执行，不使用惯量重建。

限定理论结果已审核并经非作者复核：局部姿态条件有限时域界成立于明确假设下，不等于全双环稳定性或论文证据包通过。

### 当前GRU自身闭环误差检查

已读取6份NCMD raw并重建自身forward10ms残差目标；root以1ms残差再均值独立复算，最大差5.97e-13。三维八字无风roll预测RMSE在历史C5记录为0.48649，在自身闭环为0.95215 rad/s²；pitch0.42852→0.56415，目标幅值近乎不变。6场输出/标签clip均未触发。此为描述性误差放大，不是跨状态因果证据。当前GRU同状态/hidden-before局部反馈诊断已审批给Luna xhigh，0Plant/0训练；旧完整10ms输出应用延迟已在MLP做过且失败，不再误称只延迟RLS。

### 用户询问C5整体姿态后的完整DEV72复算

root重新读取原C5/B共144份已完成raw（原DEV24+VAL48）统一计分：任务参考SO3均值B62.36872/C558.49429mrad，C5改善6.212%，41胜31负；各自inner参考SO3 B16.33811/C516.38773mrad，C5退化0.30375%，27胜45负。高频W09–14任务SO3 C5退化7.2597%，2胜26负；无风任务姿态C5六场全胜、改善52.07%。因此“C5总姿态都弱于B”不成立，必须区分任务参考与inner口径。历史TEST小表仅含位置等字段，未读TEST raw/数组，不推断TEST姿态。详见ROOT_B_C5_DEV72_TASK_AND_INNER_RECHECK_v1.json。新纯tracking GRU head隔离helper与event接线已初审，可进行0Plant数学/parity与配置检查，未放行新航次。
