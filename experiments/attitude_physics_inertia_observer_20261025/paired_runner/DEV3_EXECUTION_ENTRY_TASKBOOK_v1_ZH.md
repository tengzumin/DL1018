# DEV3 配对执行入口、冻结锁与六航次条件任务书 v1

日期：2026-10-25。root 已独立审核无 Plant 预检：receipt SHA `f770cfe55688314b104848ae1b7176245dd2ffc5592726be813c412897619bd6`；候选输入锁 SHA `ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2`（两者位于 `preflight_v1/runs/full_input_preflight_20261025T140223_0872c2df/`）。39 个部署源与 17 个输入的当前/运行前/运行后 SHA 全部一致，实际 MATLAB 退出 0；36 条 checkcode 诊断均属已记录的样式/未使用变量等类别，未见语法错误。模型身份、实际 DSSM 推理、C5 cfg/options parity、J0 与三场 scene 断言均通过。

**当前仅授权在 `paired_runner/dev3_v1/` 实现执行入口、静态检查及最终冻结候选锁。尚不授权 MATLAB/runner/Plant/航次。** root 审核实际代码和最终锁后另写 release，方可执行。不得改现有 39 个部署源、preflight 文件或历史证据；如发现必须改源，停报原因，不自行扩大。

## 最小执行入口和身份

编写一个 MATLAB wrapper 和一个 PowerShell 7 隐藏启动的串行 launcher，不另造调度框架。launcher 以明确的 release 路径和 SHA 为参数，wrapper 同样先验 release 文件 SHA，再验证 root release 的最终 source-lock SHA、候选输入锁 SHA、全部实际源/输入、MATLAB 版本、预算、固定场景与臂顺序。没有 release、release 未批准、任一 SHA 不符或已经有该 attempt 的 marker/产物，均须在调用 runner 前拒绝；不得自动续跑或重试。

最终 source lock 包括原候选锁的全部身份，加上本任务书、wrapper、launcher及其实际新依赖 SHA；不得把缺失执行入口身份的旧候选锁直接当作最终 flight lock。锁与 root release 不互相嵌入自身 SHA，避免循环哈希。最终源锁可以冻结输入，Plant 权限仅来自 root 后续明确 release。

只按已批准的两个 MAT 路径加载指定变量：model 工件只取 `model`；C5 v3 snapshot 只取 `cfg/opts/W0/modelIdentity`。使用 snapshot.cfg，现有 binder、现有 options builder，以及候选锁中的 cfg/J0/W0/normalizer/common/baseline/candidate options SHA 逐项复核；不得新造配置。三条 DEV ID、seed 与顺序原样沿用输入锁。每场重新生成一次场景，先验 spec/scene/metadata SHA 与候选锁全等；baseline 与 candidate 使用同一个内存 scene、同一个 cfg/model 和共同选项。两臂各在调用前设置该场 spec 的同一 rng seed；每次运行重新构造本臂零初态学习状态，模型不训练。

两臂只按现有预注册姿态处理区别运行，同一 `run_paired_observer_closed_loop(...,'B2-RBF-Full-SPLIT',cfg,opts)`：

| 顺序 | scene ID | seed | 臂顺序 |
|---|---|---:|---|
| 1 | DL1018_DEV_T1_C00_W03 | 2026121803 | baseline → candidate |
| 2 | DL1018_DEV_T2_C02_W15 | 2026122847 | baseline → candidate |
| 3 | DL1018_DEV_T3_C10_W11 | 2026123971 | baseline → candidate |

每次前后校验 scene、cfg、options 的规范 JSON UTF-8 SHA，所有 source/input 的 SHA 也须保持与锁全等。不得读取旧 baseline 或其它 raw，不跑72场或TEST。

## 记录、计分和严格停止

每臂用不可覆盖的独立目录保存 `run_start.json`、真实 runner invocation marker、`run_status.json`、`scene_audit.json`、原样 `run_raw.mat`及原始异常；唯一 MATLAB 进程的 stdout/stderr 由 batch launcher 原样保存，每臂引用同一 batch 日志，最终 batch receipt 绑定其 SHA。start/status 至少绑定 release SHA、最终 source-lock SHA、候选锁 SHA、runner/scene/spec/metadata/cfg/common/effective-options SHA、model/RBF 工件身份、ID/seed/arm、开始/结束 UTC、步数与状态。wrapper 的 marker 必须叫 runner invocation，不能在调用前伪称实际 first Plant step 已发生。异常若无返回日志，实际已完成 transition 数标为 unknown；该真实启动仍占一次额度，停止且不重试。

原始 `log` 返回后先保存，再做严格 gate；不得因输或失败而丢弃。仅验证已启用/有意义字段，旧 runner 的未启用占位 NaN 不构成故障。必须检查 state/reference/control、candidate 全部 20,000 个 helper trace 及事件量有限、时间与时序正确。注意 `log.time/state/reference` 为 20,001 个状态点，`log.transition_time/filtered_attitude_reference/phys_attitude_trace` 为20,000个控制区间，不要伪造末端姿态参考或忽略真实 trace。

计分在看到任何新闭环结果前固定如下，不仅照抄 runner.metrics：

- 主指标 Q=`sqrt(mean(sum((log.state(:,1:3)-log.reference.position).^2,2)))`，完整0–20 s、20,001状态点，单位m；另报逐轴RMSE与位置峰值。
- SO(3) 指标用20,000个 `transition_time`（0–20 s左闭右开）：实际 Euler=`state(1:20000,7:9)`、期望=`filtered_attitude_reference`，各用同一 ZYX 旋转矩阵，`theta=acos(clip((trace(Rref'*R)-1)/2,-1,1))`，报告`sqrt(mean(theta.^2))`和峰值（rad）。不补造t=20的参考。
- motor saturation 及 generalized clipping 按 `any(log.motor_saturated,2)`、`any(log.generalized_clipped,2)`计出现的 transition 数；tilt按`log.tilt_limited`计数；20,000 transitions/20,001 states、`STABLE`、无安全停止缺一不可。
- candidate 必须两个饱和/clip计数均0，tilt计数不高于本场baseline；本场Q与SO(3) RMSE均不得高于baseline超过`1e-12`。baseline工程/安全失败即不跑该场candidate；candidate任一门槛失败即停止后续场景。三场全过且至少一个指标严格改善超过`1e-12`才是DEV3筛查通过；仍不构成论文性能/稳定性/泛化达标。

candidate 还须核验 attitude RBF inference/update实际未执行、RBF输出/权重为零，以及helper prepare/commit的time、command、omega血缘与日志相符，`estimateTorque=-tau_comp`；输出只经同一BS接口。离线诊断可用本轮新raw，禁止把Plant真值回灌候选。两臂position规则与事件时钟相同不意味着闭环状态/Head数值输出应相同；不得用这种数值差异误判比较不一致。

报告原 controller_call_time 的测量口径：该字段不含candidate在allocator后执行的commit，不能据此声称完整控制耗时优势。DEV3可报原字段和实际run墙钟；正式论文计时后续另作完整测量。

## 资源与交付

真正获root release后最多6次 fresh runner/闭环调用，顺序固定，不训练、不扫参、不新跑其它对照，不重试。一个MATLAB进程串行；不结束既有MATLAB/实验，不并发重负载。全流程只用PowerShell7。启动前及每航次前C盘至少30GiB可用；本轮新增闭环/审计产物总预算1GiB，首对真实bytes和墙钟用于估计后续，不启动明显超余量的批次，不删除产物。

保存真实启动账本、逐场pair audit、完整输/失败原因、三场结果CSV及短报告；失败保留，未启动场景标NOT_RUN，不能当作胜/平。统计成功后也不自动扩DEV/TEST。root将从本轮新raw独立复算指标、检查接线与输入，再决定继续、修复或否定。代码、任务书、小表格可在主审后提交DL1018；MAT/checkpoint/缓存不上传GitHub。
