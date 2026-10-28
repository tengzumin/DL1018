# 延迟创新方案独立审核（静态源码/数学预审）

日期：2026-10-23。范围：冻结 C1 ON1 Head、stage-1 feature、PCF 与 command-filter 源码；任务书允许的 12 条历史 ON1 日志契约。未运行 Plant/MATLAB/训练/GPU/TEST；本轮未重新读取 MAT/raw。A 的离线构造脚本已落盘，但其首条烟测与12条正式离线核验尚在进行，故这里仅给源码静态审核，不将其冒称为数值结果通过。

## 静态时序与物理量

C1 lock 中归档 `run_dl1018_closed_loop.m`、`position_only_search_head_step.m`、`position_stage1_model_forward_v2.m`、`position_filter_realization_pcf_step_v3_5.m` 与 `command_filter_step.m` 均按 SHA 固定。HEAD 每个 10 ms event 先以 `W_before` 输出 `beta*clip(W_before'phi, ±3)`，再执行跟踪更新、`0.002` 泄漏和逐元素 `±60` 投影；runtime 将输出按质量乘成力并在同一 1 ms plant/controller tick 注入位置控制。对应源码位置：归档 runtime 第 1923–1933、1965–2029 行；Head 第 14–19 行。

位置侧的命令加速度为 `a_req`。在完全启用三轴 PCF 的 C1 ON1 中，`a_f=(T_req/m)R(euler_filtered)e3-g e3`，`r_f=a_req-a_f`，`s_eff=clip(s-eta, ±[7,8,10])`。PCF 每个 1 ms tick 使用 held-input 精确指数步更新 `eta`，新值用于后续 tick；100 Hz Head event 使用事件前的 `eta`。`command_filter_step` 返回当前 filter state 的 `ir.euler`，再推进 filter 到下一状态。因此同一步滤波姿态不是 next-state，不能错移一拍。日志已核证的 event 时间为 0.32–19.99 s，每 10 ms 一次；第一对可用延迟样本为 `j=320, k=330`。

真实 Plant 用 RK4、1 ms ZOH 进行区间积分。故

`dbar(j:k) = (1/T) ∫[t_j,t_k] (a_actual-a_f) dt`

是 10 ms 区间平均，而不是某一个采样点的瞬时加速度。对 full-PCF 连续物理记号，`a_actual-a_f = (a_actual-a_req) + (a_req-a_f) = Y+r_f`；因此速度差分标签对应 `Y+r_f` 的区间平均近似，不能称为纯 `Y` 或瞬时 `Y`。RK4/日志采样会带来离散近似误差。

任务书规定的 causal label

`dhat(j:k) = (v[k]-v[j])/T - mean(a_f[j:k])`, `T=0.01 s`,

仅使用当前/过去速度及过去区间 `a_f`。带速度测量误差 `ε_v` 时，标签附加 `(ε_v[k]-ε_v[j])/T`。若每端点误差范数不超过 `σ_v`，则该项范数不超过 `2σ_v/T`；若单轴独立同方差、标准差为 `σ_v`，则单轴标签噪声标准差为 `sqrt(2)σ_v/T`。这里放大系数是 100 s⁻¹。现有仿真位置/速度没有传感器噪声，历史离线数据不能据此证明实机标签噪声可接受。

## 待实现核验的延迟目标与有限界

对 `j=k-10`，A 提议用 `phi_j`、旧 `beta_j`、当前参数 `W_before[k]` 计算 `u_rep=beta_j clip(phi_j'W_before[k], ±3)`，并用 `e=u_rep-dhat(j:k)`、`L=0.5||e||²`。这在代数上是**当前权重对旧特征和旧区间标签的回放预测**，不是当前或未来扰动预测，也不是日志里的历史实发输出 `u_hist=beta_j clip(phi_j'W_before[j],±3)`。标签是区间平均，回放特征却是区间起点单个 `phi_j`；它不是积分回归器，需把“局部预测损失”与“积分复合学习/前瞻预测”区分开。

因为 `||phi||=1`（冻结 forward 为 `[h;1]/sqrt(1+||h||²)`）、`beta` 无量纲、`W` 与 `u` 单位 m/s²，`L` 单位 m²/s⁴，梯度 `phi [beta m⊙e]'` 单位 m/s²。若另加归一化因子 `rho` 乘在此逐事件梯度上，`rho` 应无量纲；不能直接把跟踪更新的 `gamma=12 s^-2` 当作同量纲预测增益。历史 Head 更新还含 `gamma beta phi s_eff'`、`0.002 W` 与 ±60 投影；不改变这些项而只评估创新梯度，不能推得真实 `W_after` 或闭环误差必然下降。

可证明的界仅限固定历史样本、固定旧 `phi_j,beta_j,dhat`、无投影/无其他跟踪更新且 clip active set 不变的单次创新梯度步。若 `W⁺=W-ρ phi_j(beta_j m⊙e)'`，`m_l=1{|phi_j'W_l|<3}`，则对 active 轴：`e_l⁺=(1-ρ beta_j²)e_l`；饱和轴梯度为零。因而

`L⁺=0.5 Σ_active (1-ρ beta_j²)² e_l² + 0.5 Σ_saturated e_l²`。

当 `0<ρ beta_j²<2` 且至少一个 active 轴 `e_l≠0` 时，此固定样本 loss 严格下降；否则只能说非增或无变化。clip 边界处 A 选零子梯度是允许的 Clarke 选择，但不给该轴的严格下降。逐轴目标若超出可用输出幅值 `|dhat_l|>3 beta_j`，还有不可消除下界 `L_l≥0.5(|dhat_l|-3 beta_j)²`。这些是样本局部代数界，不是在线非平稳数据、复合梯度叠加或闭环性能保证。

## 相关先例与贡献边界

- Neural-Fly 使用在线残差估计、tracking correction、协方差/正则化及鲁棒稳定性条件；其 flight-specific 结果最相关，但状态/误差、估计律与证明条件不同。[论文](https://arxiv.org/abs/2205.06908)；[作者代码仓库](https://github.com/aerorobotics/neural-fly)。
- Control-Oriented Meta-Learning 把自适应控制律与参数更新放进闭环模拟，并优化控制目标；不能据此把本方案的回放误差称为 meta-learning，也不能把其理论结论转移过来。2204.06716 的论文与作者代码应配对为 [IJRR 2023 论文](https://arxiv.org/abs/2204.06716) 和 [spenrich 作者仓库](https://github.com/spenrich/Control-Oriented-Meta-Learning)；该仓库 README 明确列出此论文与 2021 RSS 论文。另一个 [StanfordASL 仓库](https://github.com/StanfordASL/Adaptive-Control-Oriented-Meta-Learning)及其 [`train_ours.py`](https://github.com/StanfordASL/Adaptive-Control-Oriented-Meta-Learning/blob/master/train_ours.py) README 对应的是 2021 RSS 论文 [arXiv:2103.04490](https://arxiv.org/abs/2103.04490)，不将它误称为 2204.06716 的代码。
- 更直接的先例已经把 command-filtered backstepping 与 NN prediction/composite error、tracking error 一起用于更新，并给出 IE 条件下的稳定性结果。因此“command filter + prediction/复合梯度”本身不是新颖性依据。这里可读取到的是 Pan et al. 出版社摘要（全文请求返回 403）；上述先例判断只按摘要公开内容，不声称逐式比较全文。[Pan et al., 2017](https://www.sciencedirect.com/science/article/pii/S0893608017301867)。相关有限时间 command-filtered composite NN 控制也有公开论文；NSF镜像PDF本次抓取超时，此处只按可检索到的论文摘要/元数据表述。[Sun et al., 2020 PDF](https://par.nsf.gov/servlets/purl/10338331)。
- Integral composite learning 使用积分 regressor/control stack 消除对状态导数的直接依赖，并依赖有限激励条件；我阅读了 Parikh et al. 2019 作者PDF的摘要与更新式；Pan et al. 2016 Wiley全文页公开摘要及引言/算法段说明移动窗口积分误差。当前方案的有限差分速度标签和单个历史 `phi_j` 不等同于这些积分regressor构造。[Pan et al., 2016](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/iet-cta.2016.0032)；[Parikh et al., 2019](https://ncr.mae.ufl.edu/papers/IJACSP192.pdf)。

完整闭环稳定性/性能证明仍缺：Plant 与 nominal BS/姿态滤波/执行器映射的耦合界；PCF eta 与 `r_f` 的内生性和有界性证明；100 Hz 更新与 1 kHz ZOH/RK4 下的采样/延迟误差；beta ramp、输出饱和、权重投影与泄漏的联合分析；测量噪声、模型失配及特征随闭环状态变化的界；tracking update 与新 prediction gradient 同时作用时的 Lyapunov/ISS 或稳定性证明；可验证的 excitation/identifiability 条件。不能把 `s_eff`、eta 或 residual 有限的经验事实当作已证明假设。

**状态：**静态时序、目标对齐及梯度公式通过。A 最新源码候选 `construction/delayed_innovation_audit.py` SHA-256 `340887a8390eb5bce030bbedb99a80cdf925d8344457d3b8c598aaeec7f54d62` 通过只读静态核对：首个合法配对、β/φ/k权重索引、梯度方向、原 tracking ΔW、历史输入第二遍FD读取的raw SHA/stat门均一致。曾发现的252/264行数断言冲突已在该版本修为252；L̃梯度β²因子已纠正。A 的首条纯函数烟测和12条离线运行结果仍待完成；本报告不宣称其数值通过。论文仍 `NOT_QUALIFIED`；不授权参数搜索、拟合、Plant 或新增航次。



