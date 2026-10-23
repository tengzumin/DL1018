# 延迟方向记忆储能：理想子情形的精确诊断

**结论。** 给定候选能量
\[
V_q=\tfrac12\|x_q\|^2+\alpha\|w_q\|^2-\kappa(\psi_q^Tw_q)^2,
\qquad \alpha=\tfrac1{24},\quad\kappa=\tfrac1{2500},
\]
在本文明确限定的理想模型中，过去预测方向与当前输出方向的错位可被一个统一的一步能量不等式吸收。证明不要求 \(\phi_q=\psi_q\)，也不要求特征方向缓慢变化；只要求二者为单位向量、\(|\phi_q^T\psi_q|\le1\)，且 \(0\le\beta_q\le1\)。这是理想零残差子情形的解析证书，不是实际控制器、含扰动系统或部署闭环的稳定性证书。

## 模型、时序与储能

先显式统一物理单位：固定 \(T_0=1\,\mathrm{s}\)，令 \(x_q=[e_q,T_0s_{M,q}]^T\)（两个分量均为 m），并将权重写为 \(w_q=T_0^2W_q\)（单位 m）。为简记，以下把第二分量 \(x_{2,q}=T_0s_{M,q}\) 记为 \(s_q\)。增益为 \(\gamma_{\rm norm}=\gamma T_0^2=12\)，事件步长 \(h_{\rm norm}=h_{\rm phys}/T_0=0.01\)，且 \(\lambda_{\rm norm}=\lambda_{\rm phys}T_0\)，故 \(h_{\rm norm}\lambda_{\rm norm}=h_{\rm phys}\lambda_{\rm phys}\) 不变；同时 \(c=h_{\rm norm}\gamma_{\rm norm}=0.12\)。以下数值矩阵都使用这些归一化变量，\(\phi,\psi,\beta\) 无量纲；因此储能各项的单位一致，均为 \(\mathrm{m}^2\)。

按已核对的10步保持提升，取归一化输入方向 \(b_u=[0,dt/T_0]^T=[0,1/1000]^T\) 和 \(A=\begin{bmatrix}999/1000&1/1000\\-1/1000&996/1000\end{bmatrix}\)，并令
\[
F=A^{10},\qquad g=\sum_{j=0}^{9}A^j b_u.
\]
只分析理想 \(W^\star=0\)、旧标签为零的子情形：残差、逼近误差、\(\eta\) 及其他提升扰动均设为零，输出未裁剪。当前事件先输出
\[
u_q=\beta_q a_q,\qquad a_q=\phi_q^Tw_q,
\]
随后才更新归一化权重；故 \(x_{q+1}=Fx_q+g\beta_q a_q\)。这里沿用任务书中的零旧标签情形。令 \(b_q=\psi_q^Tw_q\)、\(r_q=\phi_q^T\psi_q\)、\(d_0=1-h_{\rm norm}\lambda_{\rm norm}=49999/50000\)、\(\rho=1/100\)、\(c=h_{\rm norm}\gamma_{\rm norm}=3/25\)、\(t_q=c\beta_q\)。未投影更新为
\[
\bar w_{q+1}=d_0w_q-\rho\psi_qb_q-t_q\phi_qx_{2,q}.
\]
记 \(R_q=w_{q+1}-\bar w_{q+1}\)。能量中的方向必须随实际更新时序前移：
\[
\boxed{\psi_{q+1}=\phi_q.}
\]
因此下一步记忆项是 \(-\kappa(\phi_q^Tw_{q+1})^2\)，不是 \(-\kappa(\psi_q^Tw_{q+1})^2\)。又因 \(\|\psi_q\|=1\)，有
\[
V_q\ge \tfrac12\|x_q\|^2+(\alpha-\kappa)\|w_q\|^2,
\qquad \alpha=1/(2\gamma_{\rm norm})=1/24,\quad \alpha-\kappa=619/15000>0.
\]

## 投影与记忆项不等式

若权重投影是包含原点的欧氏盒投影，则投影变分不等式给出
\[
\|w_{q+1}\|^2+\|R_q\|^2\le\|\bar w_{q+1}\|^2.
\]
在当前理想“投影不激活”子情形，\(R_q=0\)；保留上式可核对投影若激活时的余项符号。由 \(\|\phi_q\|=1\) 及 \((p+v)^2\ge\frac12p^2-v^2\)，
\[
-\kappa(\phi_q^Tw_{q+1})^2
\le-\frac\kappa2(\phi_q^T\bar w_{q+1})^2+\kappa\|R_q\|^2.
\]
结合权重范数项后，投影残差系数是 \(-\alpha+\kappa=-619/15000<0\)，故它不会破坏上界。

又有
\[
\phi_q^T\bar w_{q+1}=d_0a_q-\rho r_qb_q-t_qs_q.
\]
对任意实数 \(X,Y\)，\((X-Y)^2\ge\frac12X^2-Y^2\)；对 \(Y=\rho r_qb_q+t_qs_q\)，\(Y^2\le2\rho^2b_q^2+2t_q^2s_q^2\)。因此
\[
-\frac\kappa2(d_0a_q-\rho r_qb_q-t_qs_q)^2
\le-\frac{\kappa d_0^2}{4}a_q^2+\kappa\rho^2b_q^2+\kappa t_q^2s_q^2.
\]
这正是当前方向 \(a_q\) 的负平方项；旧方向 \(b_q\) 留下的正项没有被假称为抵消，而是在下述矩阵中由泄漏与旧预测更新吸收。

## 一步差分与统一比较矩阵

先展开未投影权重范数：
\[
\begin{aligned}
\|\bar w_{q+1}\|^2={}&d_0^2\|w_q\|^2+(-2d_0\rho+\rho^2)b_q^2-2d_0t_q a_qs_q\\
&+2\rho t_qr_qb_qs_q+t_q^2s_q^2.
\end{aligned}
\]
设 \(z_q=(e_q,s_q,a_q,b_q)^T\)。将状态提升差分、以上权重展开、下一步方向记忆项及 Young 界合并，得到
\[
V_{q+1}-V_q\le z_q^TK(\beta_q,r_q)z_q
+\alpha(d_0^2-1)\|w_q\|^2-(\alpha-\kappa)\|R_q\|^2,
\]
其中对称矩阵的非零元素为
\[
\begin{array}{ll}
K_{ee}=\tfrac12(F^TF-I)_{11}, & K_{ss}=\tfrac12(F^TF-I)_{22}+(\alpha+\kappa)c^2\beta_q^2,\\
K_{es}=\tfrac12(F^TF-I)_{12}, & K_{aa}=\tfrac12\beta_q^2g^Tg-\kappa d_0^2/4,\\
K_{bb}=\alpha(-2d_0\rho+\rho^2)+\kappa\rho^2+\kappa, & K_{ea}=\tfrac12\beta_q(F^Tg)_1,\\
K_{sa}=\beta_q[\tfrac12(F^Tg)_2-\alpha cd_0], & K_{sb}=\alpha c\rho\beta_qr_q.
\end{array}
\]
其余元素为零。对 \(0\le\beta_q\le1\)、\(|r_q|\le1\)，用对角项的端点上界和非对角项绝对值上界构成 \(\bar K\)：
\[
\begin{gathered}
\bar K_{ee}=K_{ee},\quad \bar K_{ss}=\tfrac12(F^TF-I)_{22}+(\alpha+\kappa)c^2,\\
\bar K_{aa}=\tfrac12g^Tg-\kappa d_0^2/4,\quad \bar K_{bb}=K_{bb},\\
\bar K_{es}=\tfrac12|(F^TF-I)_{12}|,\quad\bar K_{ea}=\tfrac12|(F^Tg)_1|,\\
\bar K_{sa}=|\tfrac12(F^Tg)_2-\alpha cd_0|,\quad\bar K_{sb}=\alpha c\rho,
\end{gathered}
\]
並令 \(\bar K\) 对称、其余项为零。对带符号的 \(z_q\)，严格使用
\[
z_q^TK(\beta_q,r_q)z_q\le |z_q|^T\bar K|z_q|;
\]
这里不能把 \(\bar K\) 当作对原带符号向量的直接 Loewner 上界。

将 \(F=A^{10}\)、\(g=\sum_{j=0}^9A^jb_u\) 以有理数精确计算后，脚本得到
\[
\bar K\approx\begin{bmatrix}
-0.009901612550&0.000143395866&0.000026035618&0\\
0.000143395866&-0.037904513826&0.000281941794&0.000050000000\\
0.000026035618&0.000281941794&-0.000051761250&0\\
0&0.000050000000&0&-0.000429110000
\end{bmatrix}.
\]
该小数矩阵仅便于阅读；正定性由精确证书判定。对 \(P=-\bar K\)，精确有理运算取公分母 \(D=5120000000000000000000000000000000000000000000000000000\)，并验证整数矩阵 \(DP\) 的四个顺序主子式严格为正：
\[
\begin{aligned}
\Delta_1={}&50696256258003573202853782383317937128357183428813350,\\
\Delta_2={}&9838139734420621913912620589856329799793558334374108488429186276120675569566074836735255459615121237500625,\\
\Delta_3={}&2497907508193993690637129311282509393523678952206817687325435627987797123769553460019463977662121053149860751360128000000000000000000000000000000000000000000,\\
\Delta_4={}&5487131367273213893427340817532374127829377148723939827098147659968739486768003533376223931695461493982906506322659973529600000000000000000000000000000000000000000000000000000000000000000000000000000000000000.
\end{aligned}
\]
Sylvester 判据遂给出 \(P\succ0\)，所以存在 \(\mu>0\) 使 \(|z|^T\bar K|z|\le-\mu\|z\|^2\)。另外两项也严格非正且在非零量上严格耗散：
\[
\alpha(d_0^2-1)=-\frac{33333}{20000000000}<0,
\qquad -(\alpha-\kappa)\|R_q\|^2=-\frac{619}{15000}\|R_q\|^2.
\]
故该储能在所述理想模型中得到严格一步差分界。这个结果说明过去方向记忆在此处确实吸收了当前/旧特征错位；它依赖候选储能系数和已给定固定 \(A\)，不是由轨迹采样推断出来。

## 适用边界与复核

本结论不覆盖非零旧标签/残差、\(\eta\)、逼近误差、滤波误差、ramp的真实切换语义、输出饱和、非单位或未归一化特征、其他提升矩阵，或任何会改变状态方程的机制。若这些输入界依赖状态或跟踪变量，不能直接视为外部有界量；若要扩展，必须额外证明不会形成循环条件。没有据此给真实控制器颁发稳定性结论。

精确复核命令：

```powershell
python 'reports/paper_continuation_20261023/finite_horizon_certificate/delay_aware_energy_diagnosis/verify_delay_storage_exact.py'
```

脚本只用 Python 标准库 `fractions.Fraction`，重算 \(A^{10}\)、10步输入和、\(\bar K\)，再对 \(-\bar K\) 的精确有理数公分母整数矩阵执行 Sylvester 检查。完整精确矩阵、四个有理主子式、公分母和整数主子式见 [DELAY_STORAGE_EXACT_CERTIFICATE.json](DELAY_STORAGE_EXACT_CERTIFICATE.json)。

来源与可复核产物 SHA-256：任务书 `05873F513C93BE7E5021FF87C11A527451EE0F54ADCAFE489D3DEE4169FA5C75`；验证脚本 `7E2DC1A0188E2BB417D7D5FA8418DBCC1F7D35C553829C910A3E5B293DBA75C2`；精确结果 `F785307FC7D6CE20F7A6267B50DFBA8DDA33DC1D072EA2323C91EA4930F858D7`。本次复核命令的 Python 进程真实退出码为 0。
