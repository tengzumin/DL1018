# 延迟原始残差预测项：独立设计审阅

**结论：纯单步 kernel 数学与合成守门通过；MATLAB 执行、runtime 集成和闭环效果均未验证，当前仍不得运行 Plant。** 这是新增 prediction 项相对 C2 tracking+leak 基线的候选实现审查，不是稳定性或性能结论。

## 源码与输入身份

本审阅固定于任务书 `TASKBOOK_ZH.md`（SHA-256 `E50D013A9D0A2D5F3B5A0FC54AB3D13B2320A9E0A54AC64BEF5D3441FC0280F4`）、Python kernel `delayed_prediction_kernel.py`（`6615A9D9A6096777429065A598D631CA844F46CF4131032E7FF0A3D3067D9EBC`）及 MATLAB 纯函数文本 `delayed_prediction_step_candidate.m`（`48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`）。C2 合同/源锁 SHA 分别为 `9C42275D3214A9AC85A98B66518234FCE16E8B5D7AD6826DCBF4FD8488A88BE3`、`390888537A0138F36A0D9B3A1E1FC607ECDC57939A38DABB66DB79C0887ACA87`；冻结 head helper `position_only_search_head_step.m` SHA 为 `3BD0FE9686C3B75793575E517D4CC5F08DE58AB6A26A2BC7516AA690422BB7DC`。

C2 合同将基线定为 `C2_ON1_BETA_ALIGNED`，FEATURE、gamma=12、kappa=1、锁定 W0，beta=`min(k_MATLAB*dt/T,1)`；原 head helper 是先算 raw/applied、再作 tracking+leak 更新和一次 ±60 投影。新 kernel 保留这些量，只增加 `−rho*phi_prev*r_prevᵀ` 后再做同一次投影。C2 终审记录 `C2_SCREEN_COMPLETE_STOP_NEW_CLOSED_LOOP`、已用新 Plant 航次 12、剩余授权 0、论文状态 `NOT_QUALIFIED`。旧 C2 raw 只能作为冻结比较器；若将来另获批准，候选必须是独立 condition/新 run 目录，不能覆盖或重用旧 attempt。

## 单步与因果核验

`n` 为零基 Plant index，`t_n=n·0.001s`，MATLAB index 为 `n+1`。因此 beta=`(n+1)·0.001/1.8`：n=320 时是 `0.321/1.8`，n=330 时是 `0.331/1.8`。这与 C2 的 one-based 时钟一致，没有把旧 ON1 的 `t/1.8` 混入候选。

对相邻有效 head 事件 j=n−10，标签是过去 10 ms 的区间平均残差：`y_prev=(v[n]−v[j])/0.01−(AF_integral[n]−AF_integral[j])/0.01`；累计项只覆盖 i∈[j,n)，不取当前或未来 `a_f`。它是端点速度差所给的区间平均量，不是瞬时真实加速度或真风。若每个速度端点误差范数不超过 ε_v，速度差分标签误差上界是 `2ε_v/0.01`；若端点误差独立、零均值、每轴方差 σ_v²，其速度项标准差为 `√2 σ_v/0.01`。相邻不重叠区间的速度标签仍共享端点，独立端点噪声会使相邻差分项负相关；各区间的 `a_f` 序列不共享样本，但其滤波误差协方差未知。没有部署 encoder/feature 扰动界，标签误差界不能代替在线更新总噪声界。

预测误差用当前权重和旧特征：`r_prev=W_nᵀphi_j−y_prev`，梯度为 `phi_j*r_prevᵀ`；不除 beta、不裁剪训练残差。raw/applied 输出均在当前更新之前计算：`raw=W_nᵀphi_n`、`applied=beta*clip(raw,±3)`。β=0 时映射仍有定义。n=320 是固定首 ready 事件，允许没有合法历史样本，预测项退化为原 tracking+leak；代码拒绝首事件伪造 j=310，也拒绝 n>320 缺 previous。后续有效配对必须严格 j=n−10 且时间差 10 ms。

联合更新先形成 `W−hγβ phi_n s_effᵀ−hλW−rho phi_j r_prevᵀ`，最后只做一次 ±60 投影；符号、矩阵方向和尺寸与标量平方损失的梯度相符。`rho=h/tau=0.01` 无量纲，tau=1s 是固定待审批设计常数，不是拟合/搜索/安全最优值。即使无投影、定特征且只看单个预测项，局部收缩直觉也不能扩展成含 tracking、leak、时变特征/标签、clip 和闭环 Plant 的稳定性证明。

raw 目标与 applied 目标在 β<1 或输出饱和时语义不同；β=1 且未饱和时相同。因此仅切换 raw/applied 目标定义，不能直接解释 β 已到 1 的晚段局部差异。这里提出的新增延迟预测项则是独立于目标命名的更新干预，即使在 β=1 时仍可能影响后续轨迹；候选对 C2 的闭环比较只能估计有限场景下该整项干预的总效果，不能把不同闭环状态上的残差差异冒充梯度组件的因果效果。任务书规定的双 host 固定输入回放可作局部机制诊断，但不是新的独立场景样本，也不替代闭环 Q。

## 合成验证与运行边界

我以 `python -B` 独立运行冻结 kernel 的确定性自检，退出码 0，状态 `PASS_SYNTHETIC_SINGLE_STEP_ONLY`，prediction gradient 中心差分最大绝对误差 `1.8828050230013105e−11`。检查覆盖首事件回退、beta 时钟、输出先于更新、旧 phi/当前 W、n>320 漏历史拒绝、伪 j=310 拒绝和联合投影。源内保留的一次开发期失败是修改 beta clock 后，合成投影断言仍用旧 β 期望；已通过按 C2 时钟更新断言解决，未用真实数据或 Plant。

Python 与 MATLAB 文本的方程对应；MATLAB 未执行，故数值 parity 和 runtime/API 集成仍未证明（MATLAB raw/applied 为 3×1 列向量，Python 为长度 3 的一维数组，集成时应显式统一并断言方向）。没有完整闭环 Lyapunov/ISS 证明，也没有噪声和 encoder 误差界、延迟标签与时变特征失配界。故当前仅判为“纯 kernel 草案可进入后续代码审查”，不是试验放行。

原 C2 12 场预算已耗尽。任何新 12 场候选必须有新的明确授权、冻结的新 condition/source/scene/run ledger、真实 MATLAB 无 Plant parity 和 runtime 输入门；在这些完成并获批前，禁止 MATLAB/Plant/optimizer/训练/TEST。即使后续 12 场通过，也只是有限机制证据，不自动恢复 72 场或论文资格。


## Source integration static review

本节按更新后的任务书 SHA-256 `E50D013A9D0A2D5F3B5A0FC54AB3D13B2320A9E0A54AC64BEF5D3441FC0280F4`，审查隔离 runtime 草案 `construction/runtime/run_dl1018_closed_loop.m`（SHA `E5F1E30C433EE3F8206B36446CDE71776589C161FE2A3EC60FBAF070585EB07F`）、helper `delayed_prediction_step_candidate.m`（SHA `48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`）和差异 `runtime_candidate.diff`（SHA `31400A5D753F8F080962B9A26807FD895BA3986F66628653EA5ABE9325ECB6A4`）。原 C2 runtime SHA 仍为 `62943C0247AFD94295776916A1D5370D4BE2B5F93984FF4E52CE734F7F772992`；只读核验确认原文件未改。

- **AF 积分与因果区间：通过静态核验。** 累积分量从零初始化；事件处在读取当前 `x(k,4:6)` 和当前累计量后先算目标/更新，随后才保存当前事件的 `phi`、速度、累计量作为下一对的起点。每步的 `a_f` 来自本步 `position_filter_realization_pcf_step_v3_5`，只在该调用后加 `a_f*dt`，故 n 与 j=n−10 事件所用积分差覆盖 j 到 n−1 的 10 个 1ms held-input 样本，不含当前或未来 `a_f`。本步滤波姿态由 `command_filter_step` 返回的本步 `ir.euler` 进入 PCF；没有把下一滤波姿态错配到本步。
- **head 时序/更新：通过静态核验。** 事件使用 `n=k−1` 和 `t(k)`；helper 先求当前 raw/applied，再用当前 W 与上一事件特征构造预测梯度，将 tracking、leak、prediction 项合并后一次投影。结果的 `applied` 被缓存为当前新请求，权重随后用于下一事件；C2 beta 仍以 MATLAB 一基 k 计算，且 runtime 断言 helper beta 与原 beta 一致。首 ready n=320 无 previous 时预测项为零并缓存本事件历史；后续漏历史会由 helper 拒绝。
- **默认关闭与 head bias：通过静态核验。** 最初宽松的 `logical(...)` 强转已修为只接受 logical 标量或有限实数 0/1。flag 缺省为 false；false 时 FEATURE 仍调用原 `stage1SearchStep`，BIAS 分支未改。true 时的 pre-loop 合同守门只允许 FEATURE、已启用位置头与 PCF、冻结 X14/32、100Hz/1kHz、gamma/kappa、beta-rise、dmax、模型张量及同目录 helper；不满足即在主循环/Plant 前失败。新日志字段记录 enable、目标、前一事件索引、事件速度、积分快照和 prediction term 范数，可与既有 event phi/weight-before/after 字段合并核验。
- **结论与边界：静态源集成通过，parity 未通过也未声称通过。** 没有 MATLAB parser/checkcode、MATLAB 数值调用、真实 runtime、Plant 或 launcher/source-lock 集成；这些都仍是任务书后续运行门。当前副本没有接入入口，不能运行。C2 最终决定仍是停止新闭环，12 场额度已用尽、剩余授权为 0；此代码审阅不是新额度批准。
