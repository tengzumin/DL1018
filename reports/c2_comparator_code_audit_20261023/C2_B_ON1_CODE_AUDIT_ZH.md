# C1 的 B 与 ON1 执行分支审计

审查范围：冻结 C1 v9 归档 runtime、option builder、实际 B/ON1 记录和共用控制/Plant helper；没有启动 MATLAB、Plant、训练或 TEST。本报告只覆盖代码路径与样本 raw 语义，不替代 A 侧 12 对的 cfg/opts、scene 与安全记录审计。

## 结论

B 与 ON1 使用同一冻结 `B2-RBF-Full-SPLIT` runtime、同一单次加载的 cfg、同一固定名义控制器和相同 post-position 链。未发现 method 标签、fallback、NDO/SMC/oracle、姿态路径或 Plant 选择导致暗中换了控制器家族。预定方法差异是位置 RBF 被 DSSM14 FEATURE head 替换、32 个位置事件 readiness、PCF 全轴协调及不同位置学习律；因此这是两种位置补偿方法在共同控制/Plant 框架中的比较，不是“只换网络、其余位置算法完全相同”。

发现一处真实、可量化、非预先声明的位置补偿渐增时标差异，需放入比较差异账本：B 的位置 RBF 用 `k*dt`，ON1 的 active stage1 head 用 `t(k)`。有效位置 beta rise time 为 1.8 s；同一 transition_time=0.320 s 的首场 raw 中，B beta 为 0.1783333333，ON1 active stage1 beta 为 0.1777777778，差 `dt/T=0.0005555556`。beta 未饱和阶段持续此绝对差，归一到 beta 约 0–1 的量级较小；它会稍改 B 与 ON1 的位置补偿/在线更新，不能说两条位置路径使用相同 beta 时钟，也不能据此断言该差异是 C1 结果的根因。

## 可复核的来源与实际记录

C1 v9 source lock SHA-256 为 `02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5`，release SHA-256 为 `7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0`。锁定的 9 个 runtime/config 文件与 18 个 core/Plant 文件当前 SHA 均与 lock 相符。关键来源包括：归档 `run_dl1018_closed_loop.m` `01d83dec…08450b`、`run_episode_dl1018.m` `fcc1f5de…e2330`、`position_only_search_options.m` `4e832293…19bf`、`position_only_search_head_step.m` `3bd0fe96…2bb7dc`、`position_bs_step.m` `ea533c3a…e73c681`、`command_filter_step.m` `15c7eb27…0d262b`、`attitude_bs_step.m` `cf6b20ff…caccbc`、`allocate_control.m` `5ac26d8c…7f3d53`、`rk4_vehicle_step.m` `7e10a8c7…95ef5`、`effective_config.mat` `cec90417…96522f`。完整 hash 列表见随附 JSON。

核对样本是 scene `DL1018_VAL_T2_C00_W10`：B 是 C1 v8 的精确复用记录，raw SHA-256 `0ae9e49e…896b7a`；ON1 是 C1 v9 记录，raw SHA-256 `2377ee61…e854e`。这保留了不同 release 的身份；共同 source lock 相同，不把 v8 B 伪称为 v9 新跑。

raw 的 `run_start` 保存身份与 `options_audit`，不是完整 opts/cfg 快照。替代证据是锁定的 effective config SHA、`init_dl1018` 的确定性 load、C1 对同一 `cfg` 一次构造 B/ON1 选项、source/path hash 门和 raw 中的执行开关。结论应表述为“冻结源码推定 + raw 执行模式证据”，不能称为重建出了历史完整选项快照。

## 发现：beta 时间索引差异和 warm-up 字段陷阱

- B scheduled Position-RBF 分支在 `experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m:1830-1833` 设置 `beta=min(k*dt/T,1)`。
- ON1 的有效 DSSM head 在同文件 `:1950-1955` 设置 `betaOriginal=min(t(k)/T,1)`，再在 `position_only_search_head_step.m:14-19` 同时用于输出缩放和在线权重递推。`T=1.8 s` 由锁定 `default_config.m:75-77` 给出；首场 B/ON1 raw 的 beta 数值也与此 T 相符，effective_config.mat 本身以 source lock SHA 固定。
- 首场 `B/ON1` raw 的 `transition_time=0.320 s` 对应 B `position_event_beta=0.1783333333`，ON1 `stage1_position_event_beta=0.1777777778`；ON1 stage1 beta 与事件时刻 `t/T` 对齐。差异是一个 Plant tick 的索引偏移，非不同限幅或不同质量换算。
- ON1 前 32 个事件的 DSSM history 未 ready，stage1 输出为零；`stage1_position_event_beta`/`stage1_position_event_inference_valid` 才表示 active head。此期间通用 `position_event_beta` 仍由关闭的旧 RBF scheduled 分支写入，不能当成 ON1 实际 DSSM beta。首场 raw 的 active inference-valid 数为 1968/20000，旧 RBF update flag 为 0；B 的旧 RBF update flag 为 1999/20000。两者的不同 readiness 是方法定义，不能以通用 beta 字段抹平。

该偏差的证据范围是 source 实现加首场 B/ON1 raw；其影响大小只从 beta 差异判断，未把它当作轨迹/Q 的因果解释。若后续另做“clock-aligned”条件，应只把 ON1 active beta 的时间索引对齐到冻结 B 的 `k*dt`，保持 c、W0/normalizer、DSSM、PCF、gamma、事件频率、限幅、姿态和 Plant 不变；新代码与审批应单独封存。此动作是对照条件对齐测试，不是已证实性能根因或闭环修复。固定旧 c 不应在 VAL 重拟合；probe 失败应原样保留，之后才依冻结规则决定是否扩至同一固定 12 场。当前审计没有授权/执行该复测。

## 共用路径与预定方法差异

1. `build_c1_options.m:23-42` 用同一 cfg 构造 B、ON1 与 ONC。B 走原 `controller_options_dl1018(cfg,'B',...)`；ON1 走 `position_only_search_options(cfg,model,'FEATURE',12,1)`。P_A 选项仅创建 active stage1 runtime，关闭旧位置 RBF output/update；共用 builder 基础仍保留姿态 RBF enabled/output/update、位置/姿态 100 Hz、phase start -0.1、fixed formal baseline。ONC/ON1 断言只允许初始 `weight=c*W0` 和 `kappa` 元数据不同。
2. `run_c1_screen.m:95-101` 从锁定的 `init_dl1018` 只加载一次 cfg；`run_episode_dl1018.m:13-14` 对三条件都调用固定 method `'B2-RBF-Full-SPLIT'`，条件 label 只写入 collector，不用于 controller 路由。`run_dl1018_closed_loop.m:66-73,981-989` 对 formal baseline 用由相同 cfg、arm_initial 构造的 fixedController；Plant 参数则每个 1 ms transition 同源从场景 arm trajectory 建立。
3. 两条件的共同位置律见 `matlab/core/position_bs_step.m:17-27,49-61`：先由误差构造同一名义力 `F_nom`，把惯性系残差力 `dF` 以 N 从 `F_cmd=F_nom-dF` 扣除，再形成 `(F_cmd/m)+g e3` 供后续姿态/推力映射。B RBF 及 ON1 FEATURE 输出都按同一 dmax 裁剪；各自应用 beta 后为加速度量，统一乘 `P.mass` 形成 dF N。父审的 24 raw 位置力链核验通过；本报告不重算这些全场数值。
4. 从 Position BS 后，两者使用同一个 `baseline_force_to_attitude`、目标偏航、`command_filter_step`、attitude RBF update/output、`attitude_bs_step`、`allocate_control`、电机路径和 RK4 Plant。滤波返回当前滤波 Euler/rate 给当前步，另将 nextState 用于下一采样；配置的 motor time constant 为 0。父审静态确认同状态共同链，A 侧核验场景配对。
5. ON1 的 PCF 在 `run_dl1018_closed_loop.m:2160-2168` 用请求 aReq 与本步当前 `ir.euler` 计算，并在 stage1 event 的 `:1957-1975` 进入 `s_eff` 和 Head 更新；它不在 B 路径，也不是独立直接加到 Plant 命令的扰动力。该全轴 PCF、自身的 32-event history/readiness、DSSM 输出和 FEATURE Head 更新律是预定候选方法组成，意味着 B/ON1 比较不是“固定全部学习机制只换模型”。
6. formal baseline assertion `:797-805` 禁止 NDO、SMC、oracle、位置宽度 hook、其它 adaptive/diagnostic injection 和 state/physical impulse；`stage1PositionActive` 时 `:620-624,808-815` 要求同一 formal family、100-Hz 位置事件且旧 Position-RBF 输出/更新关闭。RBF 权重从零初始化 `:368-376`，未发现随机初始化。未发现 global/persistent 状态或基于 collector 标签的隐藏 controller 选择。

## 后续 clock 对齐试验的边界判断

将 ON1 beta 从 `t(k)` 改成冻结 B 使用的 `k*dt`，从比较设计上属于一个单因素实现对齐，不是模型重训，也不能证明先前差异造成了 C1 的劣势。它会改变在线 Head 更新，因为 beta 同时缩放 output 和 gamma 项；因此不能只称“输出时间戳修正”，应把它作为新的 DSSM运行版本/状态轨迹。建议保持既定 c 与 PCF配置，完整保存失败和安全记录，1 条 probe 通过后再按原冻结的场景名单决策剩余数量。不得拿该复测覆盖原 C1 结果、重拟合 VAL 或声称已修复闭环因果问题。

