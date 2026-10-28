# 复合姿态头独立同伴审阅

**独立复核模型：** GPT-6-Luna，xhigh，default service tier；最终实验决策由 root 负责。

**范围与结论。** 只读核对任务书、v1 理论说明、指定 MATLAB 源码和三个 JSON；未读 TEST，未进入 composite 工作目录，未运行 MATLAB/Plant，也未改任何控制代码。当前 v1 源码中未发现与本审阅问题直接相关的实现错误。任务书公式的负号、坐标链和维度在**未触发 dmax 裁剪的理想连续时间误差项**下是对的；这不是离散闭环稳定性证明。本文不放行实验。

## 发现

### 1. tracking_drive 的符号、scale 与 BS 坐标相符，但只抵消理想交叉项

任务书定义 \(D\in\mathbb R^{33\times3}\)、单位范数 \(\phi\in\mathbb R^{33}\)，MLP 修正为 \(S D^T\phi\)，其中 \(S=\mathrm{diag}(\texttt{target\_rms})\)。因此 \(\beta S D^T\phi\) 是 body 轴角加速度坐标中的补偿；BS surface \(s=z_2\) 在 Euler 角速度坐标，T=euler_rate_map 满足 \(\dot\eta=T\omega\)，残差 body 角加速度对 \(\dot z_2\) 的映射是 T。误差项于是为 \(s^T T\beta S\tilde D^T\phi\)。若定义 \(\tilde D=D-D^*\)，并取参数项 \(\frac12\mathrm{tr}(\tilde D^T P^{-1}\tilde D)\)，则 \(\dot D=-P\phi[\beta S T^T s]^T\) 给出相反项。任务书的 target_rms .* (T' * s)、矩阵形状 \(33\times3\) 与负号均吻合。依据：COMPOSITE_HEAD_EXECUTION_TASKBOOK_v1.md:17-25；mlp15_attitude_step_v1.m:44-52；attitude_bs_step.m:11-26, 44-50, 58-82；THEORY_SCOPE_v1.md:45-56。

这只核对瞬时、未饱和项。应把 Dtilde 约定写明为“估计减理想值”；若相反定义，符号也应反向。输出还有逐轴 dmax 裁剪（mlp15_attitude_step_v1.m:31-32），裁剪外该轴对 D 的导数为零，未遮罩 tracking_drive 就不再抵消该轴的实际误差交叉项。此前 v1 已记录裁剪事件（ROOT_RESULT_v1.json:123-126, 140-143；SHARED_BASIS_DIAGNOSIS.json:22-24）。这是**放行前需处理或披露的设计边界，不是现有 v1 代码 bug**：应明确作为启发式律验证，或把饱和导数/门控纳入更新和验证。权重投影也会破坏边界上的等式，任务书已列为理论边界。

### 2. 时序因果基本正确；事件间隔和 beta 启动语义需钉清

当前头先用更新前权重计算 residual，再计算 torque，随后做 RLS/Joseph 更新（mlp15_attitude_step_v1.m:50-52, 88-102）；runner 将本事件 torque 用于 BS 命令（run_mlp15_dev72_closed_loop.m:2435-2447, 2679-2686）。因此新增项按任务书放在更新后、投影前，当前输出仍由旧权重决定，只影响下一事件；时序正确。历史 RLS 标签是前一事件起点到当前端点的 10 个 1-ms 区间，力矩索引到当前样本前一拍（mlp15_attitude_step_v1.m:73-87；runner:2428-2434），tracking 项不应改用该历史 phi。

任务书使用 actual_event_dt。runner 的分支间隔为 dtUpdate（run_mlp15_dev72_closed_loop.m:2370-2386；split scheduler 在1216-1218），但 MLP 输入只带 time_s、没有独立 event_dt（2423-2427）。实现可由 time_s - previous_time_s 取得真实事件间隔，也可传本事件分支的 dtUpdate；须验证使用事件间隔，而非 1-ms Plant dt 或未经核实的固定 10-ms，并定义丢事件/不等间隔行为。当前 v1 在 RLS 更新处立即投影权重（mlp15_attitude_step_v1.m:96-98）；若在该投影后简单追加 tracking 更新，就不符合任务书第17–23行“合并增量后再投影”。实现需把最终一次投影放到两项更新之后。另需消除歧义：任务书第15行“beta成熟后才更新”紧邻旧 RLS；新式第19行乘 beta_current，在 beta 从0上升时会非零更新。可有意令 tracking 提前启用，但须写明 beta 只门控 RLS 还是门控全部更新，并在首个事件/trace 验证。这些是**设计选择/实现契约要求，不是现有 v1 的实现错误**。

### 3. 信号在线可得；固定 J0 不等于时变惯量重建

runner 在当前采样从状态和当拍滤波参考 ir 计算 ai0，surface、euler_rate_map 与 BS 同源（run_mlp15_dev72_closed_loop.m:2346-2351, 2416-2427；attitude_bs_step.m:11-26）。姿态/角速率测量估计、滤波后的 BS 参考、当前网络特征、beta、常量 scale 和内部 P 都是合法在线量。trace/replay 必须用同一时刻的这些量，不能换成外层未滤波参考、未来状态、RBF 学习输出或 Plant 真值；任务书第23、37行已有该限制。

学习头要求 formalRbfBaseline=true（run_mlp15_dev72_closed_loop.m:160-169），该路径逐步令 P=fixedController（1128-1137），并检查其惯量等于锁定的 J0；固定控制器由固定初始构型和零臂速建立（153-158）。因此本路径中 BS 的 P.inertia 是固定名义值，不能说成时变惯量重建。核心函数仍允许 P.inertia_dot_for_bs 覆盖 P.inertia_dot（attitude_bs_step.m:34-40）；授权文件未显式断言该字段为零或其来源。Plant 前应核对此固定控制参数不含 Jdot_hat/Plant truth。J0 是学习器用来将估计角加速度转成力矩的固定惯量，旧 step 也断言其不变（mlp15_attitude_step_v1.m:32, 67-69）。理论把实际与名义差异定义为 \(d_a\)，明确不假定 \(J(t)=J_0\)（THEORY_SCOPE_v1.md:45-49）。runner 中 Ptrue 由真实形态构造并用于 Plant 积分（1128、2728、2753），这不等于它进入控制器；部署仍禁止 Jhat/Jdot_hat 或 Plant 真值。

### 4. 未见无条件稳定承诺；新增律没有完整闭环证明

THEORY_SCOPE_v1.md:3, 51-72, 74-79 把误差界限定于连续理想名义 BS、Euler 未跨 wrap 分支、pitch 在有效域、T 有界等条件，并把采样/保持、滤波参考、执行器和标签近似并入 r；同时明确未证明双环稳定性，也不能从权重界或 P 正定推出收敛。任务书第25行也说不是完整证明。ROOT_RESULT_v1.json:101 的“六场稳定/安全”只描述旧 v1 六条已跑轨迹，且旧版最终 B/C5 门失败（4、31–35、98–109）；不能外推给新增律。没有发现无条件稳定承诺，但 release 说明需列出适用条件、wrap/pitch 域、裁剪与离散更新误差。事件采样、RLS 改变 P、有限步长 Euler 更新和投影使瞬时抵消式不能推出离散 Lyapunov 单调或双环稳定。

### 5. 单因素对照能估计策略总效果，不能证明理论机制

任务书锁住模型、归一化、C5 栈、J0、BS、Plant、beta、dmax，只变 MLP 更新及入口；计划绑定 v1 prediction-only raw 和同一物理 scene arrays，并单列 prediction-only 指标（第13、35–40行）。若同时锁住 cfg、初态、事件调度、运行产物与安全阈值并核验源码差分，可以估计“复合更新策略相对 v1 prediction-only 的匹配场景总效果”。之后 RLS 轨迹因 D 改变而变，是这项策略的中介结果，不是另一个独立改动。

这些闭环指标不能证明 Lyapunov 交叉项机制或稳定性，也不能由三场 W15 推广。应按任务书记录 T、surface、tracking_drive、权重更新并独立重建，检查符号/数量级，配对旧 raw 与新候选的完整身份、初态及场景数组。若 prediction_only 是旧轨迹的 state-conditioned raw replay，应标为旧闭环匹配场景对照，不能称作同一新轨迹下的反事实。

## 真实 Plant 放行前必须解决

1. 实现契约明确实际事件间隔来源/校验，写明 beta ramp 期间 tracking 项是否启用，并定义 Dtilde 符号。
2. 合并 RLS 与 tracking 增量后再作最终权重投影；明确丢事件/不等间隔策略。
3. 完成任务书 35–38 行的独立数值参考与因果检查：当前输出不变、11 点历史/命令索引、Joseph SPD、裁剪/投影分支、符号与维度；独立 trace 从测量状态和滤波 BS 参考重建 T/s。本审阅未运行这些检查。
4. 核验 formal 固定控制路径的 P.inertia_dot_for_bs/P.inertia_dot 取值与来源，确保不接 Jdot_hat 或 Plant truth；J0 固定本身不替代这项检查。
5. 首航 release 条件明确 dmax 饱和、Euler/wrap 有效域的处理和观测/安全门；允许饱和时不得宣称该轴仍精确抵消。
6. 按任务书做源码差分与哈希，核对 prediction-only raw 与 matched scene/config/initial-state 身份；由 root 审查并独立放行。本 peer review 不代替 root 决策。

## 不阻塞方向验证但必须披露

- 没有 composite 闭环稳定性证明；现有界是条件误差界，残差、采样项和有效域需量化。
- tracking 公式是离散系统中的单位增益启发式律；P 时变、投影、输出裁剪、有限事件步长会破坏精确抵消。
- 固定先验/共享基底 JSON 是 recorded-state 预测诊断：共享基底 pooled RMSE 2.856 高于原 2.566 且筛查未过（SHARED_BASIS_DIAGNOSIS.json:3,6-10,153）；zero-prior pooled RMSE 2.749 高于记录先验 2.566，但场景方向混合且筛查未过（FIXED_STATE_PRIOR_DIAGNOSIS.json:3,6-7,12-14,44-46,202）。它们不证明闭环收益，也不是时变惯量诊断。固定原归一化与先验、只试一个更新项是合理的单因素设计。
- 三场 W15 是方向/安全筛查，不是 B/C5 最终门或泛化性能证明；任务书也说明不能把方向门称为最终成功。

**审阅限制：** 仅静态读指定文件；未运行 MATLAB/Plant、未读 TEST、未访问 composite 工作目录、未修改控制代码、未批准实验。