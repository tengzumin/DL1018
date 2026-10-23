# 局部域内的条件式先验误差界

**结论范围。** 对冻结 C5 的固定掩码 $M=\operatorname{diag}(1,1,0)$，若每个 10 ms 更新事件均留在原 tracking/output 未裁剪域，且下列比较器表示、滤波请求和采样余项假设在考察区间内成立，则冻结储能给出一个显式离散 ISS 递推，进而给出事件位置误差、事件间位置误差及 20,000 点 $Q_{0:20}$ 的条件上界。它是一个**假设成立时的先验命题**；它没有从初始条件证明这些状态相关假设对真实 Plant 成立，也没有证明域前向不变、全局稳定或论文理论门通过。若所得上界不能满足域条件，结论只适用于首次离域之前。

## 归一化、时钟与假设

固定 $T_0=1\,\mathrm{s}$。令
\[
\tilde W=T_0^2W_{\rm phys},\quad \tilde U=T_0^2U_{\rm phys},\quad
w_q=\tilde W_q-\tilde U,\quad x_n=[e_n,\sigma_n]^T,
\quad \sigma_n=T_0s_{M,n},\quad \tilde\eta_n=T_0\eta_n.
\]
输出、标签、扰动加速度分别按 $T_0^2$ 缩放，故均以 m 计；采样步长为 \(\delta=dt/T_0=1/1000\)。$T_0=1\,\mathrm{s}$ 时归一化数值与冻结实现一致。比较器 $U$ 是任意预先固定的权重矩阵，满足 $\tilde U\in[-60,60]^{33\times3}$，不按未来标签选择。记
\[
\bar U=\|\tilde U\|_F,\qquad u_* =\max_{k=1,2,3}\|\tilde U_{:,k}\|_2.
\]
冻结的事件为 $n_q=320+10q$、$q=0,\ldots,1967$，\(\beta_q=\min((321+10q)/1800,1)\)，并在该 10 个采样步内保持。精确日程为 \(\beta_0=107/600\)，最后一个未饱和事件 $q=147$ 的值为 $199/200$，从 $q=148$ 起为 1。未饱和事件数及 ramp 均来自冻结 clock，不另设时钟。

以下是条件假设，不是已经验证的 Plant 事实：

1. 每个事件特征满足 \(\|\phi_q\|_2=1\)。在所有更新时刻，\(|s_{M,q}|\le[7,8,10]^T\) 且 \(\|\tilde W_q^T\phi_q\|_\infty\le3\)。因此原 tracking 面裁剪和输出裁剪差均为零；权重盒投影仍允许激活。
2. 对所有 ready 区间 $q=0,\ldots,1967$ 及 $r=0,\ldots,9$，逐采样表示误差满足
   \[
   \|\tilde d_{M,n_q+r}-\phi_q^T\tilde U\|_2\le E.
   \]
   完成区间后得到的标签满足
   \(\|\tilde y_q-\bar{\tilde d}_{M,q}\|_2\le\Xi\)，其中
   \(\bar{\tilde d}_{M,q}=\frac1{10}\sum_{r=0}^9\tilde d_{M,n_q+r}\)。
3. 在整个计分区间 (n=0,\ldots,19999)，滤波器请求残差满足 \(\|\tilde r_{f,n}\|_2\le\tilde R_f\)。对采样方程的逐样本余项，满足 \(\|\rho_{p,n}\|_2\le R_p\)、\(\|\tilde\rho_{s,n}\|_2\le R_s\)。这里 \(\tilde\rho_s=T_0\rho_s\)；滤波离散余项 \(\tilde\rho_\eta=T_0\rho_\eta\) 不另作假设，而由 PCF 精确更新和 \(\tilde R_f\) 推出。
4. pre-ready 前缀 (n=0,\ldots,319) 的实际归一化控制误差满足 \(\|\tilde\epsilon_n\|_2=\|T_0^2(u_n-d_{M,n})\|_2\le E_{\rm pre}\)。给定初态 \(x_{\rm init}=x_0\)；冻结 runner 的 PCF 初值为 \(\tilde\eta_0=0\)。

这些条件显式保留对闭环状态的依赖：例如 (E,E_{\rm pre},R_f,R_p,R_s,\Xi) 可能只在指定局部轨迹域内成立。把它们命名为常数并不使其自动外生，也不意味着已由 (x_{\rm init}) 推出。

## PCF 的滤波状态与离散余项

冻结 helper 实现
\[
\tilde\eta_{n+1}=a\tilde\eta_n+b\tilde r_{f,n},\qquad
a=e^{-4\delta},\quad b=(1-a)/4.
\]
由于 runner 以零初始化，迭代并用 (\|\tilde r_{f,n}\|\le\tilde R_f\) 得
\[
\|\tilde\eta_n\|_2\le b\tilde R_f\sum_{j=0}^{n-1}a^j
=\tfrac{1-a^n}{4}\tilde R_f\le\tilde R_f/4.
\]
固定掩码是欧氏范数收缩，故同一界适用于 \(M\tilde\eta_n\)。定义任务书的 Euler 采样余项
\[
\tilde\rho_{\eta,n}=\tilde\eta_{n+1}-\tilde\eta_n-
\delta(-4\tilde\eta_n+\tilde r_{f,n}).
\]
代入精确 held-input 更新可得
\[
\tilde\rho_{\eta,n}=c_\eta(\tilde\eta_n-\tilde r_{f,n}/4),\qquad
c_\eta=e^{-4\delta}-1+4\delta,
\]
因此 \(\|\tilde\rho_{\eta,n}\|\le c_\eta\tilde R_f/2\)。标准库有理数脚本以 (e^{-0.004}\) 的交错级数上下和严格包住指数，给出
\[
\frac{11059467878820370502249}{1384277343750000000000000000}
<c_\eta<
\frac{4915319057253498001}{615234375000000000000000}
\approx7.989344\times10^{-6}.
\]
后续取右端 \(c_{\eta,+}\)，令
\(R_\eta=\tilde R_f/4\)、\(R_{\rho\eta}=c_{\eta,+}\tilde R_f/2\)。这同时覆盖 ready 与 pre-ready；没有把滤波余项遗漏或视为独立测量误差。

## 单事件扰动界

沿用冻结采样方程，单轴状态满足
\[
x_{n+1}=A_2x_n+\begin{bmatrix}\delta M\tilde\eta_n+\rho_{p,n}\\
\delta\tilde\epsilon_n+\tilde\rho_{s,n}-M\tilde\rho_{\eta,n}\end{bmatrix},
\quad A_2=\begin{bmatrix}999/1000&1/1000\\-1/1000&249/250\end{bmatrix}.
\]
逐轴堆叠后同式对 Frobenius 范数成立。令 \(\mathcal C_N(v)=T_0^2C_3(v/T_0^2)\)。原离散代数分解为
\[
\tilde\epsilon_{q,r}=\beta_q\phi_q^Tw_q+E_{q,r}.
\]
在上述未裁剪域，输出裁剪差为零；因 \(\tilde y_q=\bar{\tilde d}_{M,q}+\xi_q\)，\(\|\xi_q\|\le\Xi\)，且窗口内逐样本表示假设给出 \(\|\phi_q^T\tilde U-\tilde d_{M,n_q+r}\|\le E\)，原五项分解中的标签差 \(\xi_q\) 与平均目标恰好代数抵消，故
\[
\|E_{q,r}\|_2\le \mathcal E_q:=E+(1-\beta_q)\bar U.
\]
这里 (\Xi) 不需要重复加进当前输出误差：它用于旧标签权重梯度，而当前逐样本 (d_M) 表示界直接控制 (E_{q,r})。ramp 不能删除，且其真实日程满足
\[
\sum_{q=0}^{1967}(1-\beta_q)=4588/75,\qquad
\sum_{q=0}^{1967}(1-\beta_q)^2=27234257/810000.
\]

每个小步中扣除名义输入 \(\beta_q\phi_q^Tw_q\) 后的 forcing 两通道分别有界为
\[
\delta R_\eta+R_p,\qquad
\delta\mathcal E_q+R_s+R_{\rho\eta}.
\]
记
\[
F_q^2=(\delta R_\eta+R_p)^2+
(\delta\mathcal E_q+R_s+R_{\rho\eta})^2.
\]
以冻结 (A_2) 的提升矩阵作 Cauchy–Schwarz，
\[
d_{x,q}=\sum_{r=0}^9A_2^{9-r}f^\perp_{q,r},\qquad
\|d_{x,q}\|_F^2\le D_{x,q}^2:=10\chi_x^2F_q^2,
\]
其中精确有理数
\[
\chi_x^2=\frac{25035358596004514198498141185492820413677608904997}
{1280000000000000000000000000000000000000000000000}.
\]
这包括 \(M\eta,\rho_p,\rho_s,M\rho_\eta\)、ramp 与当前比较器表示误差。

对 (q\ge1)，旧方向 \(\psi_q=\phi_{q-1}\) 是单位向量；上一完成标签满足
\[
\|\tilde y_{q-1}-\psi_q^T\tilde U\|_2
\le E+\Xi.
\]
在 tracking 裁剪差为零后，helper 相对固定 (\tilde U) 的权重扰动严格为
\[
d_{w,q}=-h_e\lambda_e\tilde U+
\rho\psi_q(\tilde y_{q-1}-\psi_q^T\tilde U),\quad
D_w:=\|d_{w,q}\|_F\le h_e\lambda_e\bar U+\rho(E+\Xi),
\]
其中 \(h_e=1/100,\lambda_e=1/500,\rho=1/100\)。首 ready 事件 (q=0) 没有历史标签或旧方向梯度，不能代入上式；其单独界是
\[
d_{w,0}=-h_e\lambda_e\tilde U,\qquad D_{w,0}=h_e\lambda_e\bar U.
\]

## 储能 ISS 递推与事件位置误差

不改冻结储能或系数。对 (q\ge1)，其已核验扰动式为
\[
V_{q+1}-V_q\le-\frac1{50000}\|z_q\|^2-
\frac{33333}{40000000000}\|w_q\|_F^2-
\frac{619}{15000}\|R_q\|_F^2+
C_x\|d_{x,q}\|_F^2+C_w\|d_{w,q}\|_F^2,
\]
\(z_q=(e_q,\sigma_q,\phi_q^Tw_q,\psi_q^Tw_q)\)，(R_q) 是平移盒投影残差，且
\[
C_x=\frac{2509296895893346752463319889653854486846609796137360841}
{25600000000000000000000000000000000000000000000000},\quad
C_w=\frac{44331185622045154333}{20833125000000000}.
\]
使用 \(V_q\le\tfrac12\|x_q\|^2+\alpha\|w_q\|^2\)、\(\|z_q\|\ge\|x_q\|\)，并取
\[
\lambda=\min\{2/50000,(33333/40000000000)/\alpha\}
=99999/5000000000,\quad
\theta=1-\lambda=4999900001/5000000000<1,
\]
得到
\[
V_{q+1}\le\theta V_q+u_q,\quad
u_q=C_xD_{x,q}^2+C_wD_w^2,\qquad q\ge1,
\]
以及明确的几何卷积
\[
V_q\le\theta^{q-1}V_1+
\sum_{j=1}^{q-1}\theta^{q-1-j}u_j,\quad q=1,\ldots,1968.
\]
若能另给统一 \(u_j\le\bar u\)，则
\(V_q\le\theta^{q-1}V_1+\bar u(1-\theta^{q-1})/(1-\theta)\)。由于
\(1/(1-\theta)=5000000000/99999\approx50000.5\)，即使输入很小，此储能衰减也很慢且增益宽松。

首步从实际初态单独起算。令 (x_0=x_{n_0},w_0=\tilde W_0-\tilde U)，用 (\|A_2^{10}\|_2\le1) 与精确提升输入列的
\(\|g\|_2\le\|g\|_1=15785908290249111577339877/1600000000000000000000000000\)，得
\[
A_0=\|x_0\|_F+\|g\|_2\beta_0\|w_0\|_F+D_{x,0},\quad
B_0=(1-h_e\lambda_e)\|w_0\|_F+0.12\beta_0\|\sigma_0\|_2+D_{w,0},
\quad 0\le V_1\le\tfrac12A_0^2+\alpha B_0^2.
\]
首步同样允许权重投影；平移盒含原点，故投影不增范数。\(D_{x,0}=\sqrt{10\chi_x^2}F_0\)。预备阶段可用
\[
F_{\rm pre}^2=(\delta R_\eta+R_p)^2+
(\delta E_{\rm pre}+R_s+R_{\rho\eta})^2,
\quad \|x_{n_0}\|_F\le\|x_{\rm init}\|_F+320F_{\rm pre}.
\]
此式使用 (A_2) 的严格欧氏收缩，不把 (n<320) 的误差藏进 ready 后储能。

对 ready 事件内 $r=0,\ldots,9$，同一严格收缩给出可直接检验的状态界
\[
\|x_{q,r}\|_F\le\sqrt{2V_q}+r\left(F_q+
\delta\sqrt{V_q/(\alpha-\kappa)}\right),\quad q\ge1.
\]
因此事件位置误差满足
\(\|e_{q,r}\|_2\le\|x_{q,r}\|_F\)，右侧对所有事件、事件间采样均给出条件先验包络。首 ready 区间单独有 $\|x_{0,r}\|_F\le\|x_0\|_F+r(F_0+\delta\|w_0\|_F)$，其中 $r=0,\ldots,9$；它不使用未定义的 $\psi_0$。

## 20 秒评分连接与局部自洽条件

计分集合精确为 (n=0,\ldots,19999)。令
\[
S_{\epsilon,pre}=320E_{\rm pre}^2,\quad
B=V_1+\sum_{q=1}^{1967}u_q.
\]
由储能求和及 \(\nu_w=33333/40000000000\)，ready 后误差能量满足
\[
S_{\epsilon,ready}\le20\|w_0\|_F^2+
20\frac{40000000000}{33333}B+
20\sum_{q=0}^{1967}\mathcal E_q^2.
\]
于是冻结的 800/200 两个采样滤波通道给出
\[
Q_{0:20}\le\|x_{\rm init}\|_F+
800(\delta R_\eta+R_p)+
200\left[\delta\sqrt{S_{\epsilon,pre}+S_{\epsilon,ready}}+
R_s+R_{\rho\eta}\right].
\]
首项来自初始位置状态的 (A_2) 响应，故按 20,000 点 RMS 归一化后不增加 \(\sqrt{20000}\)；其余各项用对应采样通道的绝对 (\ell_1) 增益。末事件 (q=1967) 在 (n=19990\) 输出并覆盖最后十个计分样本；不计 (n=20000\) 的尾状态。

要把局部条件提升为该有限区间内的“无离域”，还须实际给定上述误差常数并验证以下自洽检查。令 (V_q^{\rm bd}) 为几何卷积上界。对 (q\ge1)，
\[
|s_{M,q,k}|\le\sqrt{2V_q^{\rm bd}}/T_0,\quad
\|\tilde W_q^T\phi_q\|_\infty\le u_*+
\sqrt{V_q^{\rm bd}/(\alpha-\kappa)}.
\]
故一个方便的充分条件为 (u_*<3) 且所有 ready 状态满足
\[
V_q^{\rm bd}\le V_{loc}:=\min\{(7T_0)^2/2,
(\alpha-\kappa)(3-u_*)^2\};
\]
另须在首次 ready (q=0) 直接检查未裁剪域，并确认 (E,E_{\rm pre},R_f,R_p,R_s,\Xi) 对局部域确实有效。若这些常数只是观测序列最大值，或上界超过 (V_{loc})，则不能推出不离域；但前述假设成立期间的一步 ISS 和误差不等式仍是有效数学结论。C5 已报告的 12 场无裁剪与观测峰值只描述那些轨迹，不是此处所需的不变性/先验界，本证明不以它们替代常数。

当前没有把 (E,E_{\rm pre},R_f,R_p,R_s,\Xi,U,x_{\rm init},w_0\) 代成真实 Plant 数值，因此没有声称获得有信息量的实际 (Q) 数值上界。尤其 \(C_x\approx9.802\times10^4\)、\(C_w\approx2.128\times10^3\)、\(1/(1-\theta)\approx5.00005\times10^4\) 较松，域自洽很可能是此证书的限制。没有假设 PE 或参数收敛。

## 当前离散标签的特殊值与代码映射

任务书允许一般 \(\Xi\ge0\)。但 C5 当前标签是速度端点差减同一预测参考的区间积分：XY 用 (a_f)，Z 用 (a^{req})；冻结采样定义的 (d_M=\bar Y+Mr_f) 展开后给出同一个区间平均。因此在**精确算术**中，当前实现满足 \(\xi_q=\tilde y_q-\bar{\tilde d}_{M,q}=0\)。有限精度下只可说有累计舍入差；本次没有标签噪声/滤波标签注入实验，故没有证据将 \(\Xi>0\) 当成已观察到的物理误差。

源码定位（文件均以 `SOURCE_IDS.json` 的 SHA-256 锁定）：

- C5 core `experiments/position_axis_coordinate_c5_20261023/run_dl1018_closed_loop.m`：掩码为 XY=`[1,1,0]` 的断言在 717 行；position 初始权重在 678 行取运行配置值；PCF `eta=zeros(3,1)` 在 764 行；tracking `s_M` 与 `[7,8,10]` 裁剪见 2014–2020 行；旧区间标签差和 `n-10` 关联见 2023–2040 行；滤波器调用及 eta 更新见 2257–2262 行；预测参考对 mask=0 的 Z 轴切换为请求加速度见 2264–2270 行。
- 延迟更新 helper `experiments/position_axis_coordinate_c5_20261023/delayed_prediction_step_candidate.m`：边界/常数在 4–5 行；无历史时 `predGrad=0` 在 26 行；旧标签梯度在 37–39 行；beta、原输出限幅、tracking 更新、leak/预测更新及权重投影顺序在 41–43 行。
- PCF helper `matlab/models/position_filter_realization_pcf_step_v3_5.m`：`rFiltered=aRequested-aFiltered` 在 14 行，精确 held-input `exp`/`expm1` 更新在 17–21 行。
- 采样方程和余项定义逐字沿用 `EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md` 第 5–16 行；储能、投影和已认证 ((P)) 沿用 `DELAY_STORAGE_PERTURBATION_BOUND_ZH.md`，不重选系数、不改冻结推导。

## 精确复核、退出码与停止边界

在本目录执行的复核器仅用 Python 标准库 `Fraction` 与 SHA-256：它锁定 taskbook、冻结扰动报告/证书、C5 core/helper、PCF helper、采样方程来源和固定 (M) 补充；有理数复核 \(\theta\)、beta 日程、(A_2^TA_2\) 的严格收缩主子式，并对指数做交错级数有理区间封闭。最终命令为：

```powershell
python 'reports/paper_continuation_20261023/finite_horizon_certificate/conditional_prior_bound/verify_conditional_bound.py'
```

最终实际进程退出码为 **0**。精确输入和常数摘要在同目录 `CONDITIONAL_EXACT_CERTIFICATE.json`；来源、脚本/结果哈希及本次命令记录在 `SOURCE_IDS.json`。不使用 MATLAB/Plant，不读取 raw/MAT/TEST，不做控制参数搜索。此前开发中的两次自检失败分别是脚本对已 Young 后权重耗散常数重复除以 \(\alpha\)，以及尝试读取旧证书中不存在的输入增益字段；当前脚本已将常数定义纠正并直接以 `Fraction` 重算提升向量，随后本次冻结复核 exit 0。冻结输入和控制器未被修改。

本结论只给局部域及显式假设下的有限时域 ISS 与误差包络；不证明这些假设被真实 Plant 满足，不推导未来统一界，不声称全局或闭环稳定，不把 C5 观察轨迹上没有裁剪升级为前向不变性。
