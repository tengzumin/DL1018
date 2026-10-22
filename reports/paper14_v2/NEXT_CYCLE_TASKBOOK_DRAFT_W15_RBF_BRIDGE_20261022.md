# DL1018 下一周期候选任务书草案：W15 的 RBF→DSSM 启动过渡

状态：**未授权执行的草案**。本文件不构成第四轮或新预算授权，不启动新航次、训练或 TEST48。当前周期三轮已用尽，论文证据包仍为 `NOT_QUALIFIED`；按冻结计划，所有新 Plant/闭环运行继续封存，直至用户另行明确开启新周期。

## 依据与待检验假设

当前 corrected DSSM14 在 DEV72 为 46/72 胜，宏平均 Q 优于 B，但开发胜场、高频 W09–W14 和 W15 均未达到资格门。R3 的 12 场筛查因 W15 子门失败而停止。W15 离线审计发现：三场 B 在 20 ms 已启用并应用 formal position-RBF 输出/更新；P_A/DSSM 分支则关闭这两项，DSSM Head 在准备期保持零补偿。相同状态的首个请求差异与这一预设控制器分支切换吻合，后续 20 ms 控制链复算未发现公式实现错误；但这不能解释 20 s 的 X-RMSE 差距，也不能证明启动差异是长期根因。见 [原始变量审计](phase1/w15_raw_offline_causal_audit_20261022.md)、[位置同状态复核](phase1/w15_same_state_replay_feasibility_20261022.md)和[控制链重放](phase1/w15_control_chain_replay_20261022.md)。

唯一假设 H4：**在 DSSM 第一次有效预测出现前，用现有 B formal position-RBF 路径替代当前的零位置补偿；首次有效 DSSM 输出出现时无重叠地切换至原 DSSM14_PCF_XY 输出，可能改善 W15 的早期水平跟踪。** 这是待检验的启动策略假设，不是已确认根因，也不能单独构成方法贡献。旧 `position_causal_repair_v1` 的 P_INIT/C1/C2 使用不同模型、训练包和场景配对，没有测试同一 RBF→DSSM 过渡，不能当成本假设的正结果；旧 G06 STOP 保持不变。

## 只读身份门（新预算开启后、任何代码修改或航次之前）

1. 冻结起点为 [R3 taskbook](../../experiments/paper14_v2_round3_xy_pcf_screen/TASKBOOK_ZH.md) 与 [R3 frozen inputs](../../experiments/paper14_v2_round3_xy_pcf_screen/frozen_inputs.json)。候选模型固定为 `CORRECTED_DSSM14_SEED2026102001_FINAL60000`：checkpoint SHA256 `544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5`；训练 normalizer 文件 SHA256 `520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404`；W0 SHA256 `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`。实际可用文件及身份必须在开工前重新核对；任一缺失或不符即停止。
2. 固定研发筛查为原冻结 VAL12，清单 SHA256 `176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e`：
   - W09–W11：`DL1018_VAL_T1_C02_W09`、`DL1018_VAL_T2_C00_W10`、`DL1018_VAL_T3_C12_W09`
   - W12–W14：`DL1018_VAL_T1_C05_W12`、`DL1018_VAL_T2_C02_W12`、`DL1018_VAL_T3_C00_W13`
   - W15：`DL1018_VAL_T1_C08_W15`、`DL1018_VAL_T2_C05_W15`、`DL1018_VAL_T3_C02_W15`
   - W00–W08：`DL1018_VAL_T1_C00_W07`、`DL1018_VAL_T2_C06_W00`、`DL1018_VAL_T3_C03_W00`
   这些是已看过的开发筛查场景，只能称 DEV 复用，不能称独立测试。
3. 目前 B 原记录没有逐航次 `runtime_tree_sha256`。方程重建可核对公式与日志一致性，但不能补回历史可执行文件的身份；除非找到可信的逐航次 runtime 身份并验证其与冻结源码相符，旧 B 一律标为“历史参考、源码身份未闭合”，不能称为身份已核验，也不能用于严格组件因果配对。新预算下须在候选 PROBE 前另行批准并完成同一锁定 runtime 的 B 配对参考，或者先找到可审计的历史 runtime 身份；仅方程重建通过不能放行。若两条路径都未完成，**不启动候选航次**，不在执行中增加航次。
4. 新预算明确开启后，所有实现放入新的隔离目录，例如 `experiments/paper14_v2_nextcycle_rbf_bridge_v1/`；不改正式 runtime、Round1–3 历史包、raw/MAT、checkpoint、normalizer、缓存或参考文件。完整 source/runtime、MATLAB/Python 公式 parity、输入/模型/normalizer/Plant SHA、预检和评分器经主模型审核后，才申请 PROBE。PROBE 固定为清单顺序第一场 `DL1018_VAL_T2_C00_W10`，只验证集成、身份、完整性和安全，不单独检验 W15 假设；PROBE 计入 12 场，结束后暂停，主模型审核后才可申请继续余下 11 场。

## 单因素处理与对照

处理因素定义为一个启动期策略包：DSSM ready 前是否启用 formal position-RBF 的输出与在线更新。该筛查不能再区分“RBF 更新状态”与“RBF 控制输出”各自的贡献；即使通过，也只能支持启动过渡策略的整体效果。

- Control：原 `DSSM14_PCF_XY`，其 X14、PCF_XY mask `[1,1,0]`、Head 更新、PCF 递推、beta、泄漏、投影、限幅、姿态 B、C0/J0、Plant、执行器和步长全部不变；Head 首次有效输出前保持当前零补偿。
- Treatment：同一候选及全部设置，只将“首次有效 DSSM 预测前的位置补偿策略”改为 formal B position-RBF 输出并执行其在线更新；该策略是一个联合处理，不再把输出与 RBF 更新拆作两个因素。以首个实际应用 DSSM 输出的事件作为切换点，立即改用原 DSSM 输出，并同时关闭 position-RBF 输出与更新；不得叠加、融合或拼接 B 的任何轴输出。在线 DSSM Head 更新规则保持相同，但闭环状态与特征可因干预而分叉。
- 单一因素为“DSSM ready 前的位置补偿策略：zero→DSSM 与 B-RBF（含原在线更新）→DSSM”。不做离线训练、不改模型或训练种子、不加 X20、不改其他控制器、Plant 或实验条件；Treatment 只在 ready 前运行既有 RBF 在线更新。

## 预登记观察量与停止门

1. 离线 smoke 必须逐事件验证 RBF 事件、DSSM 事件、源选择和命令。定义 `k_ready` 为首个实际应用 DSSM 输出的 Plant 转换索引，`t_ready=transition_time(k_ready)`；不得只用 `history_fill>=32` 推定。Ready 判定必须在该事件的任何 RBF 更新前完成：在 `k_ready` 禁止再更新/输出 RBF，替换 held RBF 命令为 DSSM 的既有 applied 输出，并从 `t_ready` 起由 DSSM 驱动 Plant。误差窗口 `[0,t_ready)` 只计入其左端 transition time 小于 `t_ready` 的样本。离线日志须明确记录 `source_selector`、`k_ready`、`t_ready` 及相邻 Plant transition，证明没有多执行一次 RBF 更新、输出重叠或零输出空档；MATLAB/Python 逐事件差异按冻结的变量单位容差核验，无量纲量绝对差不超过 `1e-12`，否则不运行。
2. 运行次序固定且串行。候选、身份闭合的同 runtime B 参考与 R3 原始配对记录必须共用相同 scene/reference 时间序列；允许干预后闭环状态分叉。旧 B 若仍无法闭合身份，只能作为描述性外部基准，不能支撑严格配对因果结论或宣布 DEV 资格通过。若以后要宣称通过 DEV72，必须先验证历史 B 的逐航次 runtime 身份覆盖全部 72 场，或在另行批准的预算中用同一锁定 runtime 生成匹配的 B 全 72 场基线；新跑 VAL12 的 B 只能支持屏查级配对诊断，不能闭合 DEV72 资格门。保留所有失败尝试，不重跑对照、不删失败场。
3. 主要机制观察为三场 W15 的 `X RMSE` 在首个实际应用 DSSM 输出前（区间 `[0,t_ready)`）是否逐场下降；同时报告每场 `k_ready`、`t_ready`、切换命令跃变和切换后轨迹。若任一 W15 场景未下降，记录为假设筛查失败，不调参。
4. 同报全 12 场 `Q_0_20`、X/Y/Z RMSE、0–1.8/1.8–5/5–10/10–20 s 分段误差、峰值、安全、限幅/饱和和实际控制耗时；未注册为资格子门的 W00–W08 组只作完整报告。申请扩至 DEV72 必须同时满足：12 场全稳定/完整/有限且无安全失败或新增执行器饱和/限幅；三场 W15 的 `[0,t_ready)` X RMSE 均严格下降；W09–W14 与 W15 组宏 Q 均不高于对应 B。12 场全体宏 Q 必须完整报告，由主模型据此决定是否批准扩展，不设自动放行。筛查通过也不等于资格通过。
5. 任一身份不匹配、失败航次、安全/完整性失败、切换逻辑不符、磁盘剩余不足 30 GB、预算预测超出 80 GB 或无法在新批准周期内完成时，立即停止，不自动清理、不新增预算。筛查失败则本方向停止，不进入 DEV72、不解封 TEST48。

## 后续资格门与权限边界

本草案只定义一个可能的下一轮筛查，不批准运行，也不改变当前三轮结论。即便该筛查通过，仍须另行审核 DEV72 全指标、方法贡献与直接相关文献对照、部署匹配的理论证明、关键消融以及资源余量；只有这些门全过，才可冻结源码/模型/normalizer/统计规则并提出一次 TEST48 解封审查。独立 TEST 不得用于重选模型或调参。

执行者模型只请求 GPT-6-Luna xhigh、正常速度；协作工具不能独立验证实际模型或速度。无新预算授权、无主模型审批、无 TEST 解封审查时，所有实验命令均不得运行。本草案不提供虚构的“可直接运行命令”；经批准后先实现隔离 launcher/preflight，再由主模型审核并将实际命令与 SHA 写入任务账本。
