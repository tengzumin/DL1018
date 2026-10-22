# DL1018 corrected DSSM14 G12/R32：控制理论与原始文献审查

日期：2026-10-22  
范围：只审查 corrected DSSM14 G12 的隔离 FEATURE Head、PCF eta/filter 与其可支持的理论结论；未运行实验、未读取 TEST 数据或指标、未改代码、未触碰现有作业。

## 现场保护与资源

使用 PowerShell 7.6.6 只读检查。C 盘剩余 168,768,356,352 字节（约 168.8 GB）。进程快照未见 MATLAB；列出的 8 个 python.exe 都是 SolidWorks MCP 服务进程，未结束或操作它们。未启动 Plant、训练或 TEST。子任务工具没有服务速度读取/切换选项；未主动启用 Fast，实际服务速度无法在本地独立核验。下文只引用源码、实验协议和原始文献；没有访问 TEST 原始文件或 TEST 指标。

## 审计对象与身份边界

corrected DSSM14 G12/R32 实际运行的隔离 runtime 位于 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\sources\local_runtime\`。runner `run_dl1018_closed_loop.m` SHA-256=`01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b` 在第1947行直接调用同目录 `position_stage1_model_forward_v2.m`（SHA-256=`dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`）；FEATURE 更新 helper `position_only_search_head_step.m` SHA-256=`3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc`。同目录未被 runner 调用的 `position_stage1_model_forward_current.m` SHA-256=`aab7861aa2eb9a1ceff6cd8808ea069ccc39c181f2f296c466c9d34b07b81d1a`；两份 sibling helper 的 DSSM 分支（第54–61行）逐行相同：零状态启动，`alpha=exp(-0.01./ssm_tau)`，`drive=tanh(W*x+b)`，`state=alpha.*state+(1-alpha).*drive`，最后 `h=tanh(project_W*state+project_b)`。因此纠正被调用文件身份不改变本文针对 DSSM14 的前向公式或理论推导。仓库根目录 `matlab/models/position_stage1_model_forward_v2.m` 是另一文件（SHA-256=`8db5a691dc1961e13956c1d6e76cdea346142e0cc04788ba17f39c72d4a122ee`），其中没有 `case DSSM`，只有 `case N_DSSM`，不能代替隔离目录的实际前向。项目内 `experiments/old_kan_fig8_transfer_compare_v1/local_runtime/position_only_search_head_step.m` 与本次隔离 FEATURE helper 字节相同，但不是本次 runner 的实际路径。审计针对实际 FEATURE 分支，不代入仓库根目录默认 Head。

模型身份边界：历史 `NN_RUNTIME_REPLAY.csv` 属于旧 FULL72 raw 批次，不是本次 corrected pair 的运行身份来源。按 `split/task/source_scene_id/method_id` 与当前 `PAIR14_SCENE_RESULTS_VS_B.csv` 联结，DSSM 与 KAN 各有 72/72 场景及 contract 标签对应，但候选 raw SHA 均为 0/72 相同；场景名和合同标签不能替代数据身份。当前 pair 的模型与 forward 身份以 `corrected_reference_training_v1/corrected_pair_eval_v1/reports/PAIR_EVAL_MODEL_BINDING_FORWARD.json`（SHA-256 `CC5616B3C10DEF65B8CB3636D92219DD5ED4848A1651D4C1F1D81F147FD384AF`）及发布后的配对结果为准：其中绑定实际 `local_runtime/position_stage1_model_forward_v2.m`（SHA-256 `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`）、DSSM14 MATLAB 导出（SHA-256 `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e`）和 checkpoint（SHA-256 `544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5`），并记录 64 个 parity fixtures 通过。该 binding 不证明每个 pair raw 的 runtime opts。历史 replay 的逐行 `run_start` 字段（CSV SHA-256 `FCC9176B0B7A49602F0AA4B7B5C199C163632A76D958023B0C5855A8F672B471`；生成器 SHA-256 `610A4F36D3B8555795643D135E7E6AD6BF3FAF282299E187C72A02C1EEB05AA9`）只能证明其旧批次 72/72 行的 `gamma=12`、`kappa=1` 等历史参数，不能移植为当前 pair 参数。当前 manifest 仅说明计划配置；pair 每次运行的 `run_start` 参数仍待独立核验。此前把 legacy replay 当作 corrected pair 配置身份的表述不成立，现已撤回。

隔离 FEATURE 头的实际递推为：

\[
\begin{aligned}
\phi_k&\in\mathbb R^{33},\quad \|\phi_k\|_2=1,\\
y_k&=W_k^\top\phi_k,\\
u_k&=\beta_k\,\operatorname{clip}_{[-d_{\max},d_{\max}]}(y_k),\\
W_{k+1}&=\Pi_{\mathcal C}\left[W_k+h_k
\left(-12\beta_k\phi_k s_{\mathrm{eff},k}^{\top}-0.002W_k\right)\right],
\quad \mathcal C=[-60,60]^{33\times3}.
\end{aligned}
\]

\(\Pi_{\mathcal C}\) 是对矩阵元素逐项截断，等价于该盒子上的欧氏投影。G12 的 12 只乘误差驱动项；它没有乘泄漏、事件间隔、beta 或当前前馈输出。每次事件先用更新前的 W_k 生成输出，再保存 W_{k+1}，事件间输出由 runner 保持。位置 Head 每 100 Hz 产生事件，Plant 以 1 ms 步长推进。此处 h_k 是 runner 实际传入的事件间隔，名义值 0.01 s。

模型输出特征构成为 [h;1]/sqrt(1+||h||²)，所以特征范数确为 1。运行器要求 32 个事件历史填满后才推理；beta 按仿真时钟计算为 beta_k=clip(t_k/1.8,0,1)。在事件时间表下首次有效推理为 0.32 s，届时 beta 约为 0.178；beta 在 1.8 s 后为 1。beta=0 时网络注入和误差驱动更新均为零，但泄漏仍生效。PCF eta 在每场开始设为零；DSSM forward 每次从零隐状态开始并重放当前 32 事件特征窗；FEATURE 的 W 初值则是 kappa*W0，仅当 kappa=0 才是零权重。

源码配置输出限值为各轴 3 m/s²，面限值为 [7,8,10] m/s。eta 不是出力限值，也没有代码投影或裁剪。Head 实际应用补偿恒满足逐轴 |u_i|≤3 m/s²，因为 raw 先 clip 且 0≤beta≤1。这不是位置误差界。

## 由实际离散代码能证明的性质

### 1. 投影保证的是参数盒约束，不是闭环稳定

若一次更新后执行盒投影，则 W_{k+1}∈C，与更新方向大小无关。若初值也在盒内，则所有事件后的权重都在盒内。对任意固定 W*∈C，逐项截断是非扩张的，因此精确有

\[
\|\widetilde W_{k+1}\|_F^2
\le \|\widetilde W_k+h_kG_k\|_F^2
=\|\widetilde W_k\|_F^2+2h_k\langle\widetilde W_k,G_k\rangle
+h_k^2\|G_k\|_F^2,
\]
其中 \(\widetilde W_k=W_k-W^\star\)，\(G_k=-12\beta_k\phi_k s_{\mathrm{eff},k}^{\top}-0.002W_k\)。这里必须保留正的 \(h_k^2\|G_k\|^2\) 项；把 projected Euler 更新当作连续投影微分方程会漏掉它。

在 W_k∈C 时，\(\|W_k\|_F\le60\sqrt{99}\approx596.993\)；每个输出列的范数不超过 \(60\sqrt{33}\approx344.673\)。面限幅给出 \(\|s_{\rm eff}\|_2\le\sqrt{213}\approx14.595\)，故 G12 下
\[
\|G_k\|_F\le12\sqrt{213}+0.002(60\sqrt{99})\approx176.33.
\]
名义 h=0.01 s 时，上述平方差界中离散余项最多约为 h²||G||²≤3.11（权重平方范数单位）。这是保守的更新代数界，不是发散结论，也不能忽略后宣称离散稳定。

特征范数为 1、权重在盒内时，未裁剪 raw 各轴上界为 60√33，而真正注入仍由 ±3 m/s² 输出裁剪限制。即使权重不变集成立，参数有界和注入有界也不蕴含位置状态有界。

### 2. PCF eta 的精确 ZOH 递推及条件界

隔离 runner 调用相同的 V3.5 PCF 实现。每个 1 ms Plant 步骤计算
r_{f,j}=a_{req,j}-a_{filtered,j}，然后以 k2=4 s⁻¹ 做精确零阶保持离散：

\[
\eta_{j+1}=a\eta_j+b r_{f,j},\qquad
a=e^{-4(0.001)}=0.9960079893,\quad
b=(1-a)/4=0.0009980027\ {\rm s}.
\]

eta_0=0。这是线性滤波器稳定的直接证据。如果另外能证明全部步都有 ||r_{f,j}||∞≤R m/s²，则几何级数给出

\[
\|\eta_j\|_\infty\le (R/4)(1-a^j)\le R/4\ {\rm m/s}.
\]

非零初值的对应界为 a^j||eta_0||∞+(R/4)(1-a^j)。源码没有提供可验证的 R 或把 eta 限在某个不变集。a_req 依赖闭环状态及名义反步命令；姿态/推力/电机路径含限幅和分配，不能只从滤波器系数推出 r_f 的统一数值上界。日志中的有限航次最大值最多是该航次的观察量，不是全运行域上的 R 证明。因此本报告不声称代码已证明 PCF eta 有界，只给出上述条件界。

每个位置推理事件使用 s_c=s-eta，再逐轴限幅得到 s_eff。PCF 状态不是当前预测注入的一部分，而是在线更新所用误差信号的协调项；若要用于闭环证明，必须证明 eta 的输入界和误差闭环的不变域。

### 3. 与实际位置误差对应的理想外环条件界

源码反步量为 e=p_ref-p、s=dot(e)+k1 e，名义加速度
a_N=ddot(p_ref)+k1 dot(e)+e+k2 s，且 corrected 实验 k1=1、k2=4。在理想双积分器上，若命令精确实现、没有姿态/推力/电机饱和、采样保持误差已经合并进扰动 delta，则可写成

\[
\dot e=s-e,\qquad \dot s=-e-4s+\delta.
\]

对 V_x=(||e||²+||s||²)/2 直接求导并用 Young 不等式，有

\[
\dot V_x=-\|e\|^2-4\|s\|^2+s^\top\delta
\le-2V_x+\|\delta\|^2/8.
\]

若 ||delta(t)||₂≤D，则
\[
V_x(t)\le e^{-2t}V_x(0)+(D^2/16)(1-e^{-2t}),\qquad
\limsup_{t\to\infty}\|e(t)\|_2\le D/\sqrt8.
\]
这是真正由该位置反步结构导出的 ISS/UUB 型条件位置界。但该结论仅适用于上述理想连续外环；代码没有证明实际六自由度 Plant/姿态/执行器采样系统可化成该模型，也没有给出 D 或其状态域。故不能把它标为 corrected DSSM14 的闭环定理。

### 4. G12 连续近似最多能得到的自适应残差界

为准确看出 gamma 的作用，可将离散 Head 暂时替换成连续梯度流，并在理想外环中假设存在固定 W*，满足同一特征域上的残差表示。令
\[
\dot W=-\gamma\beta\phi s_{\rm eff}^{\top}-\sigma W,\quad
s_{\rm eff}=\operatorname{clip}(s-\eta,L),\quad \sigma=0.002,\quad\gamma=12.
\]
若还能在明确的运行域上证明 ||phi||≤1、||W*||_F≤M、||q||≤Q、||s-s_eff||≤P，其中 q 汇集固定特征近似误差、beta 渐入差、输出饱和残差和 Plant/采样失配，那么采用参数能量系数 1/gamma 才能与实际 G12 梯度项配对：
\[
V=V_x+\frac{1}{2\gamma}\|W-W^\star\|_F^2.
\]
直接代入该更新律后，beta〈Wtilde,phi(s-s_eff)ᵀ〉是 PCF/限幅剩余交叉项；leakage 产生 W* 残差。对这两项逐一 Young 估计，可得一个保守条件式：
\[
\dot V\le-\lambda V+
\frac{\sigma}{2\gamma}M^2+\frac{1}{2k_2}Q^2+\frac{2\gamma}{\sigma}P^2,\qquad
\lambda=\min(2k_1,k_2,\sigma/2)=0.001.
\]
于是 V(t)≤e^{-lambda t}V(0)+(C/lambda)(1-e^{-lambda t})。G12 下 2gamma/sigma=12000，说明 eta/限幅造成的 P 需要有实际小而可验证的上界；权重 leakage 有限并不能替代它。

这是连续理想化下的条件推导，不是当前程序的证明：程序是 100 Hz 的 projected Euler 权重更新，PCF/Plant 按 1 kHz 推进，注入在事件间保持，并有姿态映射、推力分配和执行器限幅。连续 proxy 没有保留 h² 离散项，也不能把当前事件面的梯度和十个 Plant 子步的 Lyapunov 增量直接抵消。上述 M、Q、P、状态域和整个分段采样闭环不变性均未由代码常量证明；因此不得将这个式子写成无条件稳定性保证。

## 论文理论门槛判断

当前 G12/R32 实现能合法支撑的结论是：更新是因果的、面和输出有裁剪、权重更新使用盒投影；eta 是输入有界时有界的稳定离散滤波器；理想位置外环在有界总残差时有明确条件位置误差界。没有证据证明闭环状态不变域、PCF 输入统一有界、输出饱和残差有足够小的数值界，或 1 ms Plant/姿态/100 Hz 更新/ZOH 组合系统满足 ISS/UUB。

**因此，仅按当前结构和现有证据，不能通过计划中的“新控制理论推导”验收。** 即使把上述条件误差界完整写入论文，它仍是已知命令滤波补偿、泄漏自适应和投影更新结构上的条件式重述；G12 是离散更新的数值学习增益，kappa 是读出层初值缩放，单独搜索 gamma/kappa 或观察位置Q改善不构成新控制理论。Farrell/Dong 的 CFB 结果、带泄漏/鲁棒修改的自适应控制、以及面向四旋翼饱和的 adaptive CFB 已有直接前例。自适应更新增益作为设计参数是既有 adaptive backstepping 框架中的常规量；本次核验没有把与本项目完全相同的数值网格 [1,4,12] 认定为文献结果，因此也不把 gamma=12 说成已有特定实验先例。单独搜索一个标准增益仍不构成新控制理论。没有做系统综述，故不据此宣称文献空白。

若要继续把理论列为论文贡献，唯一最小下一步条件是：**给出并审核一个与实际 1 ms Plant、100 Hz G12 projected-Euler、beta、输出裁剪、姿态/执行器饱和及精确 PCF eta 更新逐项一致的离散闭环 ISS/UUB 定理；写清一个可核查的不变运行域，并从源码/参数/可验证模型推导 eta 输入 R、特征残差 Q、投影初值和 ZOH/饱和误差的数值界，使 Lyapunov 离散差分得到负漂移加显式残差项。** 把这些量当作未经验证的假设，或只用有限航次日志最大值代替上界，仍不达标。此处仅给验收条件，不选择或改动实现方案。

## 原始论文对照

下表已另存为 CSV。检索和核对限于上述五篇直接相关原始论文、DOI/出版方页面及可访问作者原文，不是系统性文献综述。Farrell 作者上传的 ACC 2008 会议稿 PDF 可读，但不是 TAC 2009 期刊版；本次未能访问 TAC 全文。Dong et al. 与 Choi–Bang 本次只能核对出版方页面/摘要和元数据，未访问全文，因此不声称精确 theorem 编号或摘要之外的证明细节，也不据此宣称文献空白。

- Farrell、Polycarpou、Sharma、Dong，*Command Filtered Backstepping*，IEEE TAC 54(6), 1391–1395 (2009)，[TAC DOI/出版记录](https://doi.org/10.1109/TAC.2009.2015562)。先前链接的作者上传 PDF **不是这篇 TAC 期刊版**，而是同题作者的 ACC 2008 会议稿：[ACC DOI](https://doi.org/10.1109/ACC.2008.4586773)、[ACC 2008 PDF](https://skoge.folk.ntnu.no/prost/proceedings/acc08/data/papers/0104.pdf)。已核读可访问的 ACC 稿：其 Theorem 1 在 Assumptions 1、4、5 与控制律 (11) 下证明末级误差 x̃_n 和补偿误差 v_i 指数收敛；不是所有 x̃_i。Theorem 2 在 Assumptions 1–4 下给出跟踪误差相对标准反步解的 O(ε) 差，以及滤波状态相对理想命令及其导数的 O(ε) 差，其中 ε=1/ω_n。IEEE 上 TAC 期刊全文本次不可访问，以上具体定理陈述仅归于 ACC 2008 稿，不外推为已核实的 TAC 版本。与项目相似的是通过补偿误差处理滤波误差；这两篇 CFB 结果均未覆盖 DL1018 的 1 ms/100 Hz 更新、硬裁剪、DSSM 读出和真实执行器链。

- Dong、Farrell、Polycarpou、Djapic、Sharma，*Command Filtered Adaptive Backstepping*，IEEE TCST 20(3), 566–580 (2012)，[DOI/IEEE 出版页](https://doi.org/10.1109/TCST.2011.2121907)。出版方摘要称其按 initialization/operating phases 建立短初始化有界与有限时间初始化性质，并给出 generalized parameter strict-feedback 下运行期与传统 adaptive backstepping 相同的理论性质；本文未能访问出版全文，故不标引具体定理号。它明确已有 adaptive update 与 filter-error compensation，故本项目的 G12 数值倍率或“PCF eta+adaptive Head”组合不能单独作为理论新颖性；其一般形式也不是本项目六自由度闭环的证明。
- Choi、Bang，*Adaptive command filtered backstepping tracking controller design for quadrotor unmanned aerial vehicle*，Proceedings of the Institution of Mechanical Engineers, Part G: Journal of Aerospace Engineering 226(5), 483–497 (2012)，[DOI/SAGE 出版页](https://doi.org/10.1177/0954410011415001)。出版方摘要描述了含质量、惯量、执行器增益/错位不确定性的四旋翼自适应 command-filtered backstepping，并提到执行器约束下修改 Lyapunov 跟踪误差；本文未能访问出版全文，故不补写具体定理号或超出摘要的结论。它已显示“四旋翼 + 自适应 + command filter + 饱和处理”有直接先例；其动力学和补偿机制与 DL1018 learned FEATURE Head 不同。
- Ioannou、Kokotovic，*Instability Analysis and Improvement of Robustness of Adaptive Control*，Automatica 20(5), 583–594 (1984)，[DOI/出版页](https://doi.org/10.1016/0005-1098(84)90009-8)。原文分析未建模高频动态/有界扰动导致的自适应不稳定机制，并对修改后的 adaptive law 给出鲁棒性条件、区域吸引与残差收敛结果。它支撑 leakage/鲁棒修改的背景，但不直接证明项目当前 0.002 leakage 的离散 G12 闭环。
- Cai、de Queiroz、Dawson，*A Sufficiently Smooth Projection Operator*，IEEE TAC 51(1), 135–139 (2006)，[DOI/IEEE 出版页](https://doi.org/10.1109/TAC.2005.861704)。原文构造可任意阶连续可微的参数投影，服务于需对自适应律多次求导的 backstepping 设计。DL1018 使用元素硬截断盒投影，两者不等价；该文也不意味着参数限幅即可推出闭环稳定。

## 不确定性与可复核边界

- 从隔离 helper、runner、模型 forward 和 V3.5 eta step 可验证公式、更新顺序、限值、采样频率、beta、||phi||=1 和 eta 初始化。
- `NN_RUNTIME_REPLAY.csv` 的 72/72 `run_start` 派生参数只适用于历史 raw 批次。当前 corrected pair 身份优先按模型绑定报告、实际 forward SHA 与最终配对表记录；当前 pair 每次 `run_start` 中的 gamma/kappa 尚未逐条审查，不能从 legacy replay 或 nominal manifest 推定。
- 源码本身没有可证明的统一 r_f 上界、闭环紧集、近似残差界或离散 Lyapunov 负漂移；未从 TEST 或有限航次日志补造这些前提。
- 未运行数值复测、未改代码。所有“连续/理想”结果均明确标作条件分析。




