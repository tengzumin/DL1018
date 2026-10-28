# C3 实际联合更新：条件性离散误差界与未闭合项

状态：这是对冻结 C3 源码的一步条件性推导，不构成闭环稳定性证明，也不授权新实验。只读取 runtime/helper 与已有噪声离散理论审计；未读取模型、raw 或训练数据，未修改实现。

## 源码对应关系与时序

C3 helper 的更新位于 experiments/position_delayed_prediction_c3_20261023/delayed_prediction_step_candidate.m:4–5, 26–43，SHA-256 为 48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d。调用、区间标签和延迟缓冲位于同目录 run_dl1018_closed_loop.m:1995–2035，SHA-256 为 e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f；两者均由 C3_SOURCE_LOCK.json（SHA-256 863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2）绑定。

调用方先在本事件构造 delayedTarget，再调用 helper；标签与当前输出属于同一事件，并非输出之后才可用。helper 在写入新权重前，以事件前 W_k 计算当前 raw = W_k^T phi_k 和 applied = beta_k clip_3(raw)；当前输出不依赖 delayedTarget。随后 tracking、leak 与 prediction 增量合并并投影为 W_{k+1}，所以 prediction 项影响之后事件使用的权重，不改变本事件已经算出的输出。

冻结 helper 的一次完整更新写成：
\[
\begin{aligned}
T_k &= h\gamma\beta_k\,\phi_k s_{\mathrm{eff},k}^{\mathsf T},\\
L_k &= h\lambda W_k,\\
P_k &= \rho\,\phi_j e_{j:k}^{\mathsf T},
\qquad e_{j:k}=W_k^{\mathsf T}\phi_j-y_{j:k},\\
A_k &= T_k+L_k+P_k,\\
W_{k+1} &= \Pi_{\mathcal B_{60}}(W_k-A_k).
\end{aligned}
\]
其中 W_k∈R^{33×3}，phi_k,phi_j∈R^{33}，s_eff,k,e_{j:k},y_{j:k}∈R^3。参数为 h=0.01 s、dt=0.001 s、gamma=12 s^-2、lambda=0.002 s^-1、tau=1 s、rho=h/tau=0.01。beta_k=min((n+1)dt/1.8 s,1)。特征单位范数且无量纲；W, raw, applied, y, e, T, L, P, A 的单位均为 m/s²。s_eff 的单位为 m/s，逐轴限幅为 (7,8,10) m/s；输出另逐轴限幅为 ±3 m/s²；新权重逐元素投影到 ±60 m/s²。

在 PCF 协调分支，调用方使用 s_c=s-eta 并逐轴限幅得到 s_eff；非协调分支则限幅 s 本身。因此一般不能假设 s_eff=s_c。源码要求当前零基步 n 和历史步 j 满足 n-j=10，相隔 h=10 ms。标签为
\[
y_{j:k}=
\frac{(v_k-v_j)-\sum_{\ell=j}^{k-1}dt\,a_{f,\ell}}{T},
\qquad T=0.01\,\mathrm{s}.
\]
它是这段区间的残差加速度，与旧特征 phi_j 配对；既不是 j 时刻的瞬时目标，也不是当前特征 phi_k 的同刻标签。旧特征、区间标签错配的含义必须保留在以下界中。

## 一次联合投影后的参数误差界

定义盒
\[
\mathcal B_{60}=\{W\in\mathbb R^{33\times3}: |W_{ia}|\le60\},
\]
并暂作固定比较器假设 $W^*\in\mathcal B_{60}$。令 $\widetilde W_k=W^*-W_k$、投影残差 $R_k=W_{k+1}-(W_k-A_k)$，以及
\[
E_{W,k}=\frac{\|\widetilde W_k\|_F^2}{2\gamma}.
\]
由于 W^* 在投影盒内，凸集欧氏投影的 Pythagorean 不等式给出
\[
\|W_{k+1}-W^*\|_F^2
\le \|W_k-A_k-W^*\|_F^2-\|R_k\|_F^2.
\]
展开 $W^*-W_k=\widetilde W_k$ 后，真实的联合更新满足
\[
\boxed{
E_{W,k+1}-E_{W,k}
\le
\frac{\langle \widetilde W_k,A_k\rangle_F}{\gamma}
+\frac{\|A_k\|_F^2-\|R_k\|_F^2}{2\gamma}.
}
\]
令 $q_j=\widetilde W_k^{\mathsf T}\phi_j\in\mathbb R^3$，则线性项为
\[
\frac{\langle \widetilde W_k,A_k\rangle_F}{\gamma}
=
h\beta_k\,s_{\mathrm{eff},k}^{\mathsf T}\widetilde W_k^{\mathsf T}\phi_k
+\frac{h\lambda}{\gamma}\langle \widetilde W_k,W_k\rangle_F
+\frac{\rho}{\gamma}q_j^{\mathsf T}e_{j:k}.
\]
联合平方项必须保留三个增量之间的所有交叉项：
\[
\begin{aligned}
\|A_k\|_F^2={}&
(h\gamma\beta_k)^2\|\phi_k\|^2\|s_{\mathrm{eff},k}\|^2
+(h\lambda)^2\|W_k\|_F^2
+\rho^2\|\phi_j\|^2\|e_{j:k}\|^2\\
&+2h^2\gamma\beta_k\lambda\,
s_{\mathrm{eff},k}^{\mathsf T}W_k^{\mathsf T}\phi_k\\
&+2h\gamma\beta_k\rho\,
(\phi_k^{\mathsf T}\phi_j)(s_{\mathrm{eff},k}^{\mathsf T}e_{j:k})\\
&+2h\lambda\rho\,e_{j:k}^{\mathsf T}W_k^{\mathsf T}\phi_j.
\end{aligned}
\]
三项交叉项分别来自 tracking–leak、tracking–prediction、leak–prediction；符号可正可负。R_k 是对总增量 A_k 的单次投影修正，不能拆成互不作用的三个子步投影损失。由上式可见，一个直接的充分条件是
\[
2\langle \widetilde W_k,A_k\rangle_F+\|A_k\|_F^2
\le \|R_k\|_F^2.
\]
冻结实现和离线样本没有证明该条件逐步成立。

若固定样本精确满足 y_{j:k}=W^{*\mathsf T}phi_j，则 q_j^{\mathsf T}e_{j:k}=-\|q_j\|^2，但它只约束 prediction 的线性项，不消除联合平方项、tracking 项、leak 项或当前/旧特征差。特别地，
\[
\langle \widetilde W_k,W_k\rangle_F
=\langle \widetilde W_k,W^*\rangle_F-\|\widetilde W_k\|_F^2
\]
对一般非零比较器并无固定符号，故 leak 不是对参数误差必然耗散的项。

作一个仅用于对照的单独 prediction 步：令 A_k=P_k，没有 tracking 或 leak，并假设 \|\phi_j\|=1、y_{j:k}=W^{*\mathsf T}\phi_j+\epsilon_{j:k}。此时 e_{j:k}=-q_j-\epsilon_{j:k}，联合投影界化为
\[
\Delta E_W\le\frac1\gamma
\left[
-\rho\|q_j\|^2-\rho q_j^{\mathsf T}\epsilon_{j:k}
+\frac{\rho^2}{2}\|q_j+\epsilon_{j:k}\|^2
-\frac12\|R_k\|_F^2
\right].
\]
若 $\epsilon_{j:k}=0$，上界为
\[
-\frac{\rho-\rho^2/2}{\gamma}\|q_j\|^2
-\frac{\|R_k\|_F^2}{2\gamma}.
\]
C3 的 $\rho=0.01$ 对应 $\rho-\rho^2/2=0.00995$。这是 isolated raw prediction 步的条件性平方距离界，不能替代 A_k=T_k+L_k+P_k 的实际联合界，也不表示控制状态会收敛。

## 与控制误差项相加时的精确余项

在额外的理想连续模型假设下，令 d_k^*=W^{*\mathsf T}phi_k∈R^3，z_k=W_k^{\mathsf T}phi_k∈R^3，u_k=beta_k clip_3(z_k)。定义 clip_3 为逐轴 ±3 m/s² 裁剪，则恒等式为
\[
u_k-d_k^*
=
-\beta_k \widetilde W_k^{\mathsf T}\phi_k
+(\beta_k-1)d_k^*
+\beta_k\bigl(\operatorname{clip}_3(z_k)-z_k\bigr).
\]
注意 $\widetilde W_k^{\mathsf T}\phi_k$ 是 $3\times1$；转置次序不能反过来。

仅为呈现账目，假设控制 Lyapunov 函数的单步连续部分满足
\[
\Delta V_{c,k}
\le -h c_e e_{p,k}^{\mathsf T}k_1e_{p,k}
-h s_{c,k}^{\mathsf T}k_2s_{c,k}
+h c_e e_{p,k}^{\mathsf T}\eta_k
+h s_{c,k}^{\mathsf T}(u_k-d_k^*)
+r_k^{\mathrm{impl}},
\]
其中 r_impl 汇集实际离散 PCF、Plant、积分器和采样保持相对该理想式的余项。把这个假设式与参数界相加得到
\[
\begin{aligned}
\Delta(V_c+E_W)_k\le{}&
-h c_e e_{p,k}^{\mathsf T}k_1e_{p,k}
-h s_{c,k}^{\mathsf T}k_2s_{c,k}
+h c_e e_{p,k}^{\mathsf T}\eta_k+r_k^{\mathrm{impl}}\\
&+h s_{c,k}^{\mathsf T}
\left[(\beta_k-1)d_k^*
+\beta_k(\operatorname{clip}_3(z_k)-z_k)\right]\\
&+h\beta_k(s_{\mathrm{eff},k}-s_{c,k})^{\mathsf T}
\widetilde W_k^{\mathsf T}\phi_k\\
&+\frac{h\lambda}{\gamma}\langle \widetilde W_k,W_k\rangle_F
+\frac{\rho}{\gamma}q_j^{\mathsf T}e_{j:k}
+\frac{\|T_k+L_k+P_k\|_F^2-\|R_k\|_F^2}{2\gamma}.
\end{aligned}
\]
tracking 的两个一阶参数项为
\[
-h\beta_k s_{c,k}^{\mathsf T}\widetilde W_k^{\mathsf T}\phi_k
+h\beta_k s_{\mathrm{eff},k}^{\mathsf T}\widetilde W_k^{\mathsf T}\phi_k.
\]
因此只要两处使用相同 beta_k 且 s_eff,k=s_c,k，它们对任意 beta_k∈[0,1] 都抵消；不要求 beta_k=1。输出 clipping 并不改变这个代数抵消条件，但会留下上式中的 clipping 残差；beta_k<1 会留下 (beta_k-1)d_k^* 项。若有效面与 PCF 面不同，还留下表面 mismatch 项。剩余的 leak、prediction、联合平方交叉项、投影项和实现余项仍需分别控制。该相消只是一阶代数事实，不是联合 Lyapunov 下降证明。

本节控制式是明确标注的理想连续假设，不是对 runtime 的已证离散不等式。既有噪声离散审计已讨论 PCF 连续误差恒等式、RK4/ZOH 解释、测量噪声及固定样本 raw/applied 界；实际闭环若要使用上式，必须另给 r_impl 的符号或绝对值界，且证明它可由负项吸收。此处没有该证明。

## 幅值、标签噪声、采样与特征扰动的条件

若当前 W_k 已在盒内且 \|\phi_k\|=\|\phi_j\|=1，源码量限给出
\[
\|W_k\|_F\le60\sqrt{99}\approx596.993,\qquad
\|T_k\|_F\le0.12\sqrt{213}\,\beta_k\approx1.7514\beta_k,\qquad
\|L_k\|_F\le0.01(0.002)60\sqrt{99}\approx0.01194.
\]
这些权重增量的单位为 m/s²。$\|P_k\|_F=0.01\|e_{j:k}\|$，但代码仅检查 y 与 W 为有限数，没有统一的 y 或 e 幅值上界。故仅靠源码无法得到 P_k 或完整 A_k 的统一步长上界。输出限幅只给出 $\|u_k\|\le3\sqrt3\,\beta_k$ m/s²。helper 对输入 W_k 检查有限性并投影下一权重；它不强制当前输入已经在盒内，因此上述 W_k 范数界还需要初始权重位于盒内这一未核实假设。本任务没有读取模型来验证初值。权重盒也不约束状态、PCF 辅助量 eta、扰动或位置误差。

历史标签须解释为 y_{j:k}=W^{*\mathsf T}phi_j+epsilon_{j:k} 时，epsilon_{j:k} 需要容纳固定特征模型误差、窗口内目标变化、传感器/滤波误差和区间平均与起点特征不匹配。前一份离散噪声审计说明：若速度观测噪声、端点偏差变化和 a_f 误差分别满足 \|\nu_n\|\le\epsilon_v、\|b_k-b_j\|\le B_b(T)、\|\xi_\ell\|\le\epsilon_f，则测量噪声部分有条件界
\[
\|\epsilon_{j:k}^{\mathrm{meas}}\|
\le \frac{B_b(T)+2\epsilon_v}{T}+\epsilon_f,
\qquad T=10\,\mathrm{ms}.
\]
端点速度误差会被 1/T 放大；相邻标签窗口共享端点，残差不是独立样本。runtime 对自身 ZOH 信号 a_f 的区间积分就是离散求和，不应额外声称内部积分误差；若将它解释为连续 Plant 的瞬时扰动估计，还需单独界定 RK4 阶段/采样误差。

若连续特征满足 L_phi-Lipschitz，且目标可写作 d(t)=W^{*\mathsf T}phi(t)+r(t)，则区间平均与旧特征的错配满足
\[
\left\|\bar d_{j:k}-W^{*\mathsf T}\phi_j\right\|
\le \|W^*\|_F L_\phi T/2+
\frac1T\int_{t_j}^{t_k}\|r(t)\|\,dt.
\]
此界需要共同固定 W^*、连续特征 Lipschitz 常数和残差积分界；源码/样本并未证实这些前提，也没有证实 raw 目标由固定特征模型精确表示。

若特征和标签有扰动 phihat_j=phi_j+deltaphi_j、yhat=y+deltay，则
\[
\delta e=W_k^{\mathsf T}\delta\phi_j-\delta y,
\qquad
\|\delta P_k\|_F
\le\rho\left(
\|\delta\phi_j\|\|e_{j:k}\|
+\|\phi_j\|\|\delta e\|
+\|\delta\phi_j\|\|\delta e\|
\right).
\]
当前 tracking 增量也会受到 phi_k 与 s_eff,k 扰动影响。helper 检查输入特征有限且单位范数，但没有给出部署时观测到特征的误差界；扰动还可能改变 clip 是否激活。因此只能在外加扰动界后给条件估计，不能据此宣称本批数据验证了扰动鲁棒性。

## 结论边界与未闭合项

参数界依赖一个固定、共同且位于盒内的 W^*，并依赖区间标签相对 W^{*\mathsf T}phi_j 的有界误差；这些是假设而不是已由运行数据确认的事实。即使这些条件成立，联合一步界仍含 tracking 与 leak 线性项、三项平方交叉项、beta ramp 与输出 clipping 残差、s_eff-s_c mismatch、prediction 标签噪声和旧特征错配、PCF 的 eta 项，以及 Plant/RK4/保持实现余项。当前没有统一且经证实的上界能保证它们被控制误差的负项吸收。参数辨识还需可辨识性/持续激励条件；权重有界或固定输入下局部残差下降都不验证这些条件。

因此能成立的仅是：在 W^*∈B_60 的条件下，C3 的一次实际联合投影满足上述参数平方距离上界；单独的精确 raw prediction 样本步另有条件性界。没有证明实际联合更新逐步耗散，也没有证明整体 PCF/Plant Lyapunov 稳定。权重投影盒只约束参数，不推出闭环稳定。

噪声、10 ms 标签构造、RK4/ZOH、旧特征与区间目标错配、raw/applied 单样本性质沿用 [独立噪声离散理论审计](/C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/delayed_innovation_design_audit_20261023/noise_discrete_theory/review/INDEPENDENT_NOISE_DISCRETE_REVIEW_ZH.md)（SHA-256 86087852cd330eee97a9e84ad5ba6f9db52f6c01a6db165ce04709aa644260dc）与 [理论候选](/C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/delayed_innovation_design_audit_20261023/noise_discrete_theory/construction/THEORY_CANDIDATE_ZH.md)（SHA-256 484f28cb5bc88910ff147b1ba6e9280edf257e9255fec0aa0a8cea5d898d992f）；本文重点是 C3 tracking、leak、prediction 的联合离散一步账目，不重复前述单样本证明。源码绑定见同目录 SOURCE_BINDING.json。唯一数值核验是本目录脚本对固定合成矩阵进行的代数恒等式和投影不等式检查，不读模型或实验记录；结果见 ALGEBRA_CHECK.json。




