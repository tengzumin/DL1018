# 延迟方向储能的实际扰动有限时域界

**结论。** 对冻结的 C5 固定轴掩码 \(M=\mathrm{diag}(1,1,0)\)，同一负方向记忆储能可扩展为一个显式、逐路径有限时域能量界。当前推导保留了状态采样余项、\(M\eta\)、输出/跟踪裁剪、beta ramp、积分标签对齐误差、固定比较器失配和投影残差，没有把它们假作独立外生常数。由此可以把这些实际有限序列条件式地接到 20,000 个计分位置样本的 \(Q_{0:20}\)。这些扰动仍依赖闭环状态，且本次不读取 raw 来代入数值，所以**没有**证明完整 Plant 闭环先验稳定、未来统一有界或论文理论门通过。

## 单位、事件与冻结实现映射

固定 \(T_0=1\,\mathrm{s}\)。以下 \(W,U,w\) 均表示归一化权重 \(T_0^2W_{\rm phys}\)，\(w_q=W_q-U\)，其数值与 helper 权重相同；\(U\) 是任意固定的盒内分析比较项，不按未来标签选择。\(x_n=[e_n,\sigma_n]^T\)，\(\sigma_n=T_0s_{M,n}=T_0(s_n-M\eta_n)\)。输出/标签用 \(T_0^2\) 缩放，跟踪面和 \(\eta\) 用 \(T_0\) 缩放，故储能
\[
V_q=\tfrac12\|x_q\|_F^2+\alpha\|w_q\|_F^2-\kappa\|\psi_q^Tw_q\|_2^2,
\quad \alpha=1/24,\quad\kappa=1/2500
\]
各项单位均为 \(\mathrm{m}^2\)。对储能递推使用的 \(q\ge1\)，\(\psi_q\) 是单位向量，故 \(\|\psi_q^Tw_q\|_2\le\|w_q\|_F\) 且
\[
V_q\ge\tfrac12\|x_q\|_F^2+(\alpha-\kappa)\|w_q\|_F^2
=\tfrac12\|x_q\|_F^2+\tfrac{619}{15000}\|w_q\|_F^2\ge0.
\]
常数为 \(h_e=0.01/T_0\)、\(\lambda_e=0.002T_0\)、\(\rho=0.01\)、\(c=h_e\gamma T_0^2=0.12\)、\(d_0=1-h_e\lambda_e=49999/50000\)。每个特征 \(\phi_q\in\mathbb R^{33}\) 为单位向量，\(\beta_q\in[0,1]\) 在整个 10 ms 事件区间保持。

源码对应关系如下：C5 runner 的 `positionCoordinateMask` 在第 24–30 行解析并在第 717 行强制为 \([1,1,0]^T\)；第 2014–2020 行形成 \(s_M=s-M\eta\) 并按 \([7,8,10]\) 裁剪；第 2030–2040 行只将上一个已完成区间的积分差构成标签并调用 helper；第 2258–2270 行更新 PCF \(\eta\) 并按 XY 用 \(a_f\)、Z 用 \(a^{req}\) 累加预测参考。冻结 helper 第 26 行在首 ready 事件令预测梯度为零，第 37–39 行使用 \(\psi_q(\psi_q^TW_q-y_{q-1})^T\)，第 41–43 行先输出 \(\beta C_3(W_q^T\phi_q)\)，再作 tracking/leak/旧梯度更新并投影到 \([-60,60]^{33\times3}\)。因此对 \(q\ge1\)，\(\psi_q=\phi_{q-1}\)、\(\psi_{q+1}=\phi_q\)；目标残差符号是 \(y_{q-1}-\psi_q^TU\)，不能反号。

冻结采样推导使用 \(x_n=[e_n,T_0(s_n-M\eta_n)]\)，其中本段沿用源文档的物理时间步长 \(h_{\rm phys}=dt=0.001\,\mathrm{s}\)；\(h_{\rm phys}/T_0=\delta=0.001\)。其 1 ms 方程为
\[
x_{n+1}=A_2x_n+
\begin{bmatrix}hM\eta_n+\rho_{p,n}\\
T_0\{h(u_n-d_{M,n})+\rho_{s,n}-M\rho_{\eta,n}\}
\end{bmatrix},\quad
A_2=\begin{bmatrix}.999&.001\\-.001&.996\end{bmatrix},
\]
其中 \(d_{M,n}=\bar Y_n+M(a^{req}_n-a_{f,n})\)。\(\rho_p,\rho_s,\rho_\eta\) 按实际相邻样本差分定义，保留 RK4、参考采样及滤波积分余项。对 \(n_q=320+10q\)、\(q=0,\ldots,1967\)，令 \(\delta=dt/T_0=0.001\)、\(F=A_2^{10}\)、\(g=\sum_{r=0}^9A_2^{9-r}[0,\delta]^T\)。下文对三个轴的量用矩阵/Frobenius 范数合并；因为 \(M\) 固定对角且各轴使用同一个 \(A_2\)，逐轴式求和成立。

## 逐项展开事件扰动

用上标 \(N\) 表示按上述 \(T_0\) 缩放后的信号。令 \(\tilde r_q=\phi_q^TW_q=\phi_q^TU+\phi_q^Tw_q\)，\(\mathcal C_N(v)=T_0^2 C_3(v/T_0^2)\)，\(\tilde u_q=\beta_q\mathcal C_N(\tilde r_q)\)。定义与旧推导一致的区间量
\[
\bar d_{M,q}=\tfrac1{10}\sum_{r=0}^9\tilde d_{M,n_q+r},\quad
\xi_q=\tilde y_q-\bar d_{M,q},\quad
\nu_{q,r}=\bar d_{M,q}-\tilde d_{M,n_q+r}.
\]
这里 \(\tilde y_q\) 是区间 \([n_q,n_q+10)\) 完成后可得的平均标签；它在本式只用于事后恒等分解，不会被当成 q 事件开始时可用的控制输入。于是实际控制误差有精确分解
\[
\tilde u_q-\tilde d_{M,n_q+r}
=\beta_q\phi_q^Tw_q+E_{q,r},
\]
\[
\boxed{E_{q,r}=(\phi_q^TU-\tilde y_q)
+(\beta_q-1)\phi_q^TU
+\beta_q[\mathcal C_N(\tilde r_q)-\tilde r_q]
+\xi_q+\nu_{q,r}.}
\]
五项依次是固定比较器对区间目标的当前失配、ramp 偏置、输出裁剪差、区间积分/标签表示差、窗口内变化。没有把 \(\xi\) 设为零，也没有把平均标签替成瞬时 \(d_M\)。

写 \(\tilde\eta_n=T_0\eta_n\)、\(\tilde\rho_{s,n}=T_0\rho_{s,n}\)、\(\tilde\rho_{\eta,n}=T_0\rho_{\eta,n}\)。第 \(q,r\) 个 1 ms 小步中，扣除名义反馈 \(\beta_q\phi_q^Tw_q\) 后的 forcing 是
\[
f^\perp_{q,r}=\begin{bmatrix}
\delta M\tilde\eta_{n_q+r}+\rho_{p,n_q+r}\\
\delta E_{q,r}+\tilde\rho_{s,n_q+r}-M\tilde\rho_{\eta,n_q+r}
\end{bmatrix},\qquad
d_{x,q}=\sum_{r=0}^9 A_2^{9-r}f^\perp_{q,r}.
\]
所以事件状态严格满足
\[
\boxed{x_{q+1}=Fx_q+g\beta_q\phi_q^Tw_q+d_{x,q}.}
\]
该式逐项保留了 \(M\eta\)、sampled \(\rho_p,\rho_s,M\rho_\eta\)、预测 ramp、输出裁剪、比较器失配、\(\xi,\nu\)。\(d_x\) 是本事件 10 个采样 forcing 经固定提升传播的结果，不是把所有项不加权地相加。

对权重更新，令 \(\sigma_q=T_0s_{M,n_q}\)，\(\sigma_{eff,q}=T_0s_{eff,n_q}\)，\(\mathcal W=[-60,60]^{33\times3}\)。对 \(q\ge1\)，helper 的未投影更新减去固定 \(U\) 后恰为
\[
\bar w_{q+1}=d_0w_q-\rho\psi_q(\psi_q^Tw_q)-c\beta_q\phi_q\sigma_q+d_{w,q},
\]
\[
\boxed{d_{w,q}=-h_e\lambda_eU
+\rho\psi_q(\tilde y_{q-1}-\psi_q^TU)
-c\beta_q\phi_q(\sigma_{eff,q}-\sigma_q).}
\]
第一项是泄漏对固定比较器的偏置；第二项是上一已完成标签对旧方向 \(\psi_q\) 上比较器的逼近误差，符号来自 \(-\rho\psi_q(\psi_q^TW_q-\tilde y_{q-1})\)；第三项是 helper 对 tracking 面裁剪产生的差。这里没有把 \(\sigma_{eff}\) 偷换成未裁剪 \(\sigma\)。实际权重满足
\[
w_{q+1}=\Pi_{\mathcal W-U}(\bar w_{q+1}),\quad
R_q=w_{q+1}-\bar w_{q+1},\quad\psi_{q+1}=\phi_q.
\]
因 \(U\in\mathcal W\)，平移盒 \(\mathcal W-U\) 包含原点，欧氏盒投影给出 \(\|w_{q+1}\|_F^2+\|R_q\|_F^2\le\|\bar w_{q+1}\|_F^2\)。

## 含扰动的一步能量式与精确常数

置 \(a_q=\phi_q^Tw_q\)、\(b_q=\psi_q^Tw_q\)、\(r_q=\phi_q^T\psi_q\)、\(m_q=d_0w_q-\rho\psi_qb_q-c\beta_q\phi_q\sigma_q\)，\(X_q=d_0a_q-\rho r_qb_q-c\beta_q\sigma_q\)、\(v_q=\phi_q^Td_{w,q}\)。再令 \(z_q=(e_q,\sigma_q,a_q,b_q)\)，按轴拼接。投影和记忆移位产生
\[
\alpha\|w_{q+1}\|_F^2-\kappa\|\phi_q^Tw_{q+1}\|_2^2
\le \alpha\|m_q+d_{w,q}\|_F^2
-\tfrac\kappa2\|X_q+v_q\|_2^2-(\alpha-\kappa)\|R_q\|_F^2.
\]
其中 \(-\frac\kappa2\|X+v\|^2\le-\frac\kappa2\|X\|^2+\kappa\|X\|\|d_w\|\)；这保留理想比较矩阵项，只把交叉项列作扰动。结合状态差分，增量相对理想式的额外上界是
\[
L_x\|z_q\|\|d_{x,q}\|+\tfrac12\|d_{x,q}\|^2
+(\kappa L_X+2\alpha c)\|z_q\|\|d_{w,q}\|
+2\alpha(d_0+\rho)\|w_q\|\|d_{w,q}\|+\alpha\|d_{w,q}\|^2,
\]
其中可取全有理数上界
\[
L_x=\sum_{ij}|F_{ij}|+\sum_i|g_i|,\qquad L_X=d_0+\rho+c.
\]
这是因为 \(\|Fx+g\beta a\|_F\le L_x\|z\|\)、\(\|X\|_2\le L_X\|z\|\)、\(\|m\|_F\le(d_0+\rho)\|w\|_F+c\|z\|\)。令 \(C_z=\kappa L_X+2\alpha c\)、\(B_w=2\alpha(d_0+\rho)\)。将两个含 \(\|z_q\|\) 的交叉项合并为 \(\|z_q\|(L_x\|d_{x,q}\|_F+C_z\|d_{w,q}\|_F)\)，再用 \(AB\le\zeta A^2+B^2/(4\zeta)\) 和 \((a+b)^2\le2a^2+2b^2\)；权重交叉项单独用 \(AB\le(\nu_w/2)A^2+B^2/(2\nu_w)\)。因此状态项总共只消耗一次 \(\zeta\)，余下 \(\mu_0-\zeta=1/50000\)；权重泄漏余下 \(\nu_w/2\)。其中
\[
\mu_0=4\cdot10^{-5}=1/25000,\quad \zeta=2\cdot10^{-5}=1/50000,\quad
\nu_w=\alpha(1-d_0^2)=33333/20000000000,\quad \nu_R=\alpha-\kappa=619/15000,
\]
得到对所有 \(q\ge1\) 的**显式逐事件不等式**
\[
\boxed{V_{q+1}-V_q\le-\tfrac1{50000}\|z_q\|^2
-\tfrac{33333}{40000000000}\|w_q\|_F^2
-\tfrac{619}{15000}\|R_q\|_F^2
+C_x\|d_{x,q}\|_F^2+C_w\|d_{w,q}\|_F^2.}
\tag{P}
\]
精确常数为
\[
C_x=\tfrac12+\frac{L_x^2}{2\zeta},\qquad
C_w=\alpha+\frac{C_z^2}{2\zeta}+\frac{B_w^2}{2\nu_w}.
\]
它们的约值分别约 \(9.8\times10^4\) 和 \(2.13\times10^3\)，很保守但有限。固定候选余量不是控制参数：标准库有理数脚本直接对冻结 \(\bar K\) 验证 \(-\bar K-(1/25000)I\succ0\)，四个顺序主子式精确为正；完整整数矩阵及主子式在 `PERTURBATION_EXACT_CERTIFICATE.json`。脚本还精确算出事件提升 forcing 的 \(\chi_x^2=\sum_{j=0}^9\|A_2^j\|_F^2\)，故
\[
\sum_q\|d_{x,q}\|_F^2\le\chi_x^2\sum_{q,r}\|f^\perp_{q,r}\|_F^2.
\]

令 \(B=V_1+C_x\sum_{q=1}^{1967}\|d_{x,q}\|_F^2+C_w\sum_{q=1}^{1967}\|d_{w,q}\|_F^2\)。由 \(V_{1968}\ge0\)，对最后一次 update 也保留的求和得
\[
\sum_{q=1}^{1967}\|z_q\|^2\le50000B,\quad
\sum_{q=1}^{1967}\|w_q\|_F^2\le\frac{40000000000}{33333}B,\quad
\sum_{q=1}^{1967}\|R_q\|_F^2\le\frac{15000}{619}B.
\]
这是真实输入序列的有限和界；它没有假定 \(d_x,d_w\) 与状态无关。

## 首 ready、20 秒评分与停止边界

首 ready 为 \(q=0,n_0=320\)。helper 明确没有历史四元组时令旧预测梯度为零，所以不能在该步插入 \(\rho\psi(y-\psi^TU)\)。记 \(w_0=W_0-U\)、\(\sigma_0=x_{2,0}\)、\(\beta_0=\min((n_0+1)dt/1.8,1)\)。实际首步相对 \(U\) 的扰动只有
\[
d_{w,0}=-h_e\lambda_eU-c\beta_0\phi_0(\sigma_{eff,0}-\sigma_0).
\]
对 \(x_1=Fx_0+g\beta_0\phi_0^Tw_0+d_{x,0}\) 和首步平移盒投影，记
\[
A_0=\|F\|_2\|x_0\|_F+\|g\|_2\beta_0\|\phi_0^Tw_0\|_2+\|d_{x,0}\|_F,\quad
B_0=d_0\|w_0\|_F+c\beta_0\|\sigma_0\|_2+\|d_{w,0}\|_F.
\]
则 \(\psi_1=\phi_0\)，记忆储能从 \(q=1\) 才开始，且有单独的有限起点界
\[
0\le V_1\le\tfrac12A_0^2+\alpha B_0^2.
\]
\(d_{x,0}\) 可由前述首事件 10 个采样 forcing 求和；其中若事后用 \(\tilde y_0\) 分解，它只是已完成区间的记账项，不是首步控制器历史标签。

同一 1 ms 状态递推在 20 秒窗口的计分集合 \(\mathcal S=\{0,\ldots,19999\}\) 上给出固定卷积界。将三轴按 \([e_x,e_y,e_z,\sigma_x,\sigma_y,\sigma_z]^T\) 堆叠，令 \(\mathcal A=A_2\otimes I_3\)、\(\mathcal C=[I_3\ 0]\)，于是 \(c_n=\mathcal C\mathcal A^n x_{init}\)。定义 \(\tilde\eta_n=T_0\eta_n\)、\(\tilde\epsilon_n=T_0^2\epsilon_n\)、\(\tilde\rho_{s,n}=T_0\rho_{s,n}\)、\(\tilde\rho_{\eta,n}=T_0\rho_{\eta,n}\)、\(\delta=h/T_0=dt/T_0=0.001\)。令
\[
f_{1,n}=\delta M\tilde\eta_n+\rho_{p,n},\qquad
f_{2,n}=\delta\tilde\epsilon_n+\tilde\rho_{s,n}-M\tilde\rho_{\eta,n},\quad \epsilon_n=u_n-d_{M,n},
\]
冻结 \(A_2\) 两个非负输出冲激通道的绝对 \(\ell_1\) 和为 800、200（有限窗不超过此和），Minkowski/离散 Young 给出
\[
\boxed{Q_{0:20}\le\frac1{\sqrt{20000}}\left[
\|c\|_{\ell_2(\mathcal S)}
+800(\delta\|M\tilde\eta\|_{\ell_2(\mathcal S)}+\|\rho_p\|_{\ell_2(\mathcal S)})
+200(\delta\|\tilde\epsilon\|_{\ell_2(\mathcal S)}+\|\tilde\rho_s-M\tilde\rho_\eta\|_{\ell_2(\mathcal S)})\right].}
\tag{Q}
\]
对 ready 后的事件，\(\tilde\epsilon_{q,r}=\beta_q\phi_q^Tw_q+E_{q,r}\)，故
\[
\sum_{q=0}^{1967}\sum_{r=0}^9\|\tilde\epsilon_{q,r}\|_2^2
\le20\|w_0\|_F^2+20\frac{40000000000}{33333}B
+2\sum_{q=0}^{1967}\sum_{r=0}^9\|E_{q,r}\|_2^2.
\]
令 \(S_{\epsilon,pre}=\sum_{n=0}^{319}\|\tilde\epsilon_n\|_2^2\)。由于 ready 区间恰好覆盖 \(n=320,\ldots,19999\)，有
\[
\|\delta\tilde\epsilon\|_{\ell_2(\mathcal S)}^2
=\delta^2\left[S_{\epsilon,pre}+\sum_{q=0}^{1967}\sum_{r=0}^9\|\tilde\epsilon_{q,r}\|_2^2\right].
\]
另将 \(n<320\) 的未 ready 前缀误差 \(S_{\epsilon,pre}\) 单独保留；它不由首 ready 后的储能界覆盖。于是上式和 \((Q)\) 把每轴位置误差、全部 3 轴 Frobenius 能量及 20,000 个计分点的 \(Q\) 连在一起。事件 \(q=1967\) 在 \(n=19990\) 先输出、再更新到 \(W_{1968}\)，其 held 输出覆盖最后 10 个 1 ms 区间并形成 \(n=20000\) 尾状态；计分只取 20,000 个位置样本，不把尾状态当第 20,001 个计分样本，也不虚构在 \(n=20000\) 再更新一次权重。

这里的 \(S_{\epsilon,pre},B,\sum\|E\|^2,\eta,\rho_p,\rho_s,\rho_\eta,\xi,\nu\) 都是实际路径量。特别是 \(s_{eff}-s_M\)、采样余项和标签对齐差会依赖闭环状态；\(d_x,d_w\) 还含当前 comparator loss 与输出裁剪差。它们没有被本推导从初始条件推出统一上界，因此 (P)–(Q) 是可在给定有限路径后代入的条件式后验界，不能据此解出无条件的 \(Q\) 上限或声称完整 Plant 稳定。本推导不假设 PE，也不声称参数收敛。数值上宽松的 \(C_x,C_w\) 也不应被解释为已获得有信息量的实际 RMSE 界。

## 复核输入与运行

本目录的 `verify_perturbation_margin.py` 只用 Python 标准库 `Fraction`，锁定并核对上一份冻结理想精确结果 SHA 后，检查 \(-\bar K-(1/25000)I\) 的有理数顺序主子式、事件 forcing 系数及 (P) 中的有理常数。运行命令：

```powershell
python 'reports/paper_continuation_20261023/finite_horizon_certificate/delay_storage_perturbation/verify_perturbation_margin.py'
```

本次不读取任何新 raw/MAT/TEST，不运行 MATLAB/Plant，也不把状态相关扰动当作外生统一界。任务书、冻结 C5 core/helper、采样方程和精确证书的 SHA 记录在同目录 `SOURCE_IDS.json`；脚本实际退出码与输出结果摘要在 `PERTURBATION_EXACT_CERTIFICATE.json`。

复核命令实际退出码：Python 0。来源 SHA-256：本任务书 `FB8B7571BFDAB31CCC4B56D231A8E96EB676B131A11571F493B6646A7DA4BF90`；冻结 C5 core `48350037B66EFE00301B138068F187C62CF92583F0F9BA2FABC9B24F248A963C`；冻结 helper `48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`；既有有限时域推导 `AF46370C993E32E09BA0957F73682A2A169080932668FEF03291743D93A4AEB0`；采样记账任务书 `104B9DA52F2885BD53C2D122BA84ED09ED121D79AF6215F9E59593C0EEF0E606`；固定对角 \(M\) 补充 `32E5B41673A5E7FDF8555AE2B4B5B1BE63F2E10C5783EF184DC53F65C530EEFC`；父级精确余量复核 `27DB96CED2C44C37976B5781023BAFBF34D50EC110E132BAEDA3A6ECBE7A4752`；理想储能报告/脚本/结果依次为 `B53BC4A50AD16B45DE0AF357B7484F1D41FDB28ECF997AB1EFA760607777FF73`、`7E2DC1A0188E2BB417D7D5FA8418DBCC1F7D35C553829C910A3E5B293DBA75C2`、`F785307FC7D6CE20F7A6267B50DFBA8DDA33DC1D072EA2323C91EA4930F858D7`。本次脚本 SHA-256 `761D1136FA4DF7EAC705BD8F5629839580488F221A3FB36FB53DF34552E9B261`，精确结果 SHA-256 `8E92FCA3D02584BCA289942BDB7946BE494FFB50AC944B6BD694DBD7EFCF2307`。
