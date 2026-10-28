# MLP15 C5-24 姿态替代候选：闭环筛查任务书 v3

状态：准备完成，等待 root 对首个候选航次作出明确放行。创建日期：2026-10-26。

## 目标与冻结对象

把已完成训练审核的 `mlp15_c5_teacher_redistill_v1/runs/C5_24_seed2026102001/` MLP15 权重接入 GHP7 六场 ACTIVE pilot。runtime 用 `DL_MLP15` arm 接口，候选 identity 标记为 `DL_MLP15_C5_24`；锁定 `best_step=1000`。仅使用 C5-24 `mlp15_attitude_weights_v1.mat`，不替换、不临时覆盖 v1/v2 或其他 runner 的权重文件。

位置环继续使用已锁定的 C5 DSSM14 M110，BS 姿态名义环、Plant、allocator 和执行器保持 v2 设置。姿态 RBF 输出/更新、惯量重建、observer 和物理前馈均关闭；MLP15 权重冻结，不做在线更新。

## 场景、配对基线与运行次序

- 六场为 G1/G2/G3 × W00/W12，geometry arm 为 ACTIVE。复用已冻结的六场 payload 和匹配 B、C5_RBF raw；不得重跑 B 或 C5。
- 第一个候选航次只能是 `DL1018_GHP7_G1_W00`，只作工程门。检查完整结束、STABLE、无安全停止/饱和/通用裁剪/倾角限制后，交 root 复核；只有 root 后续批准才可继续其他五场。
- 最多消耗 6 个候选 Plant 航次；任何已写 `attempt_started.marker` 的失败都计入预算并保留。TEST48 保持封存，不读、不运行。
- 首场 G1/W00 的既有 B 与 C5_RBF baseline 均 application-feasible，可用于工程门配对。六场 baseline manifest 的既存状态须在最终结果中原样披露：C5_RBF G1/W00 的 completion flag mismatch（父审计记录 raw/score 有效）；G2/W00 的 B 与 C5_RBF，以及 G2/W12 的 B，标记 `application_feasible=false`。不得更改、剔除或重跑这些 baseline；六场统计仍保留全部场景，并同时报告各自完成标志、可行性标志和原始指标。

## 筛查和报告口径

六场小样本只作方向及工程安全筛查，不作论文统计结论。六场候选全部完整结束且安全后，按未舍入原始数值对齐同场、同 payload、同 R_task 基线，并报告逐场、W00/W12 风组、六场宏平均：

1. 位置 Q 六场宏平均严格优于 B，且相对 C5_RBF 宏平均退化不超过 10%（candidate Q ≤ 1.10 × C5_RBF Q）。
2. 姿态 SO(3) RMSE 六场宏平均严格优于 B 和 C5_RBF。
3. 报告每场完成/稳定/安全停止、饱和、通用裁剪、倾角限制和 application-feasible 标志。不得因基线异常排除场景或隐藏指标。

六场全部完成且以上筛查门通过，才可另行讨论进入后续 DEV72 阶段；本任务书本身不作该晋升授权。

## 实施、验证与审批门

- 候选源码复制自 `pilot_runner_mlp15_v2/candidate_runner_work` 到独立 `pilot_runner_mlp15_c5_24_v1/candidate_runner_work`。除 C5-24 training identity/path 和 C5-24 release/output identity 外，其余 50 个 MATLAB 源文件 SHA 与 v2 相同；所有源码由新 source lock 绑定。
- 新训练目录的 progress/config/dataset manifest/run receipt/parity report、MAT 权重和 best checkpoint 均作 SHA 与 identity 校验，要求 `best_step=1000`、parity PASS、Plant 未调用、TEST 未读取。
- 必须通过 MATLAB Code Analyzer 改动文件检查、G1/W00 no-Plant scene preparation，以及真实 C5-24 权重的一步内存 runtime smoke。静态检查确认 TEST 不在任何读取路径中，Plant 只从显式 closed-loop attempt entry 进入。
- `MLP15_C5_24_PILOT_RELEASE_v1.json` 初始为 `PREPARED_PENDING_ROOT_APPROVAL`，`plant_calls_authorized=0`；闭环入口在该状态下硬拒绝。root 批准首场后须更新独立 release，且只授权 G1/W00 和 1 次调用。首场结束并经 root 检查后，如需继续，root 再显式扩展授权场景和预算；总预算不得超过 6。
- 新输出仅写到 `pilot_runs_mlp15_c5_24_v1` 与 `pilot_score_mlp15_c5_24_v1`。不覆盖 v1/v2、B-768、C5 代码、release、raw、缓存或历史结果。

当前无闭环航次已启动；TEST 未读取。
