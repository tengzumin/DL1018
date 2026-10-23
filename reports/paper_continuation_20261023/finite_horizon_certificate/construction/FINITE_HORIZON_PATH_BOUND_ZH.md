# 有限时域路径位置误差界（符号构造）

状态：完成独立符号推导与合成代数自检，等待未撰写者复核；理论门仍为 **NOT_MET**。本文件覆盖冻结 C3 的 (M=I)、C4 的 (M=0)，以及批准补充中的固定 C5 (M=\operatorname{diag}(1,1,0))。不涉及动态或扫描 (M)，不读取 Plant raw，不据此声称闭环稳定。

## 实际采样递推与区间标签

令 (h=0.001\,\mathrm{s})、(T_0=1\,\mathrm{s})、(e_n=r_n-p_n)、(s_n=\dot r_n+K_1e_n-v_n)，并令 (z_n=T_0(s_n-M\eta_n))。冻结 (K_1=I,K_2=4I)，故三轴的归一化状态递推使用同一个

\[
A_2=\begin{bmatrix}.999&.001\\-.001&.996\end{bmatrix},\qquad
A=A_2\otimes I_3=\begin{bmatrix}.999I_3&.001I_3\\-.001I_3&.996I_3\end{bmatrix}.
\]

定义仅供离线核验的采样量

\[
\begin{aligned}
\rho_{p,n}&=(r_{n+1}-r_n-h\dot r_n)-(p_{n+1}-p_n-hv_n),\\
\rho_{s,n}&=\dot r_{n+1}-\dot r_n-h\ddot r_n+K_1\rho_{p,n},\\
\bar Y_n&=(v_{n+1}-v_n)/h-a^{req}_n,\\
\rho_{\eta,n}&=\eta_{n+1}-\eta_n-h(-K_2\eta_n+r_{f,n}),\
d_{M,n}&=\bar Y_n+M r_{f,n}=\bar Y_n+M(a^{req}_n-a_{f,n}).
\end{aligned}
\]

这里的 \(\rho_p,\rho_s\) 由实际相邻采样差分定义，保留 Plant RK4、参考采样及一阶展开余项；证明中不把它们置零或替换成连续时间理想轨迹。

由实际 BS 命令关系 (a^{req}=a_{nom}-u) 及 (a_{nom}=\ddot r+K_1(\dot r-v)+e+K_2s)，直接整理相邻样本差分可得

\[
\begin{bmatrix}e_{n+1}\\z_{n+1}\end{bmatrix}
=A\begin{bmatrix}e_n\\z_n\end{bmatrix}
+\begin{bmatrix}hM\eta_n+\rho_{p,n}\\
T_0[h(u_n-d_{M,n})+\rho_{s,n}-M\rho_{\eta,n}]\end{bmatrix}.
\tag{1}
\]

式 (1) 对 (M=I,0,\operatorname{diag}(1,1,0)) 分别给出 C3、C4、固定 C5。C5 的预测参考是 (a_{f,XY}+a^{req}_{Z}=a^{req}-M r_f)，所以其区间残差正是 (d_M)。(M) 与 (K_1,K_2) 可交换且对角，因而坐标变换后 (A) 不变；此处没有推出非对角、动态 (M) 的结论。

事件时刻为 (n_q=320+10q)，(q=0,\ldots,1967)。(y_q\in\mathbb R^3) 是与事件特征 φ_q 配对、在下一事件可用的 10 ms 平均残差；它对应输出 (u_q) 在 ([n_q,n_q+10)) 的保持区间，不是 1 ms 瞬时加速度。可复核时应从实际积分重算区间均值，不能预设其与离散 ̄(d_M) 完全相等。

## 联合投影给出的累计预测损失界

冻结 helper 的特征满足 (\|\phi_q\|_2=1)，权重 (W_q\in C=[-60,60]^{33\times3})。令

\[
L_q(W)=\tfrac12\|W^T\phi_q-y_q\|_2^2,\quad
G_k=\phi_{k-1}(W_k^T\phi_{k-1}-y_{k-1})^T,
\]

其中 (k=1,\ldots,J)、(J=1967)。事件 (q=0) 没有历史标签，只做 (H_0) 更新得到 (W_1)；之后 helper 在事件 (k) 用 (G_k) 和 (H_k) 联合更新 (W_{k+1}=\Pi_C(W_k-\rho G_k-H_k))，其中

\[
H_k=h_e\gamma\beta_k\phi_k s_{eff,k}^T+h_e\lambda W_k,\quad
h_e=.01,\ \gamma=12,\ \lambda=.002,\ \rho=.01.
\]

这一定义保留 tracking/leak 的状态依赖。对任一固定比较器 (U\in C)，设 (D_k=\|W_k-U\|_F^2)、(p_k=W_{k+1}-(W_k-\rho G_k-H_k))、(R=\max_{1\le k\le J}\|W_k-U\|_F)，并取 (a=(1-\rho)/2)。单位范数特征给出精确恒等式

\[
\langle W_k-U,G_k\rangle=L_{k-1}(W_k)-L_{k-1}(U)
+\tfrac12\|(W_k-U)^T\phi_{k-1}\|^2.
\]

投影到闭凸盒满足
\(D_{k+1}\le\|W_k-U-\rho G_k-H_k\|_F^2-\|p_k\|_F^2\)。展开后只对交叉项作明确 Young 上界
\(2\rho\langle G_k,H_k\rangle\le a\rho\|G_k\|_F^2+(\rho/a)\|H_k\|_F^2\)，且 ‖(G_k)‖²=　2(L_{k-1}(W_k))。因此

\[
\begin{aligned}
D_{k+1}-D_k\le{}&-\rho(1-\rho)L_{k-1}(W_k)+2\rho L_{k-1}(U)
-\rho\|(W_k-U)^T\phi_{k-1}\|^2-\|p_k\|_F^2\\
&-2\langle W_k-U,H_k\rangle+c_H\|H_k\|_F^2,
\quad c_H=1+\frac{2\rho}{1-\rho}.
\end{aligned}
\]

对 (k=1,\ldots,J) 求和并丢弃有利的非正项，得到

\[
\rho(1-\rho)\sum_{q=0}^{1966}L_q(W_{q+1})\le D_1+2\rho\sum_{q=0}^{1966}L_q(U)
+2R\sum_{k=1}^{1967}\|H_k\|_F+c_H\sum_{k=1}^{1967}\|H_k\|_F^2.
\tag{2}
\]

(U=W_0\) 是已核验落在投影盒内的固定初始权重时，(D_1\le\|H_0\|_F^2)。式 (2) 是任意已实现序列上的路径代数：(H_k) 可以依赖 (s_{eff,k})、φ 和闭环状态，不需要独立性假设；但右侧仍含实际 comparator loss 和实际 (H_k)，所以它是可事后复算的路径证书，不是闭环先验界。记录有限也不能推出未来统一有界或稳定。

## 实际输出、ramp/clip 与保持区间

事件 (q) 输出 (raw_q=W_q^T\phi_q)，下一事件以当前 (W_{q+1}) 评价旧标签。故精确地

\[
raw_q-y_q=[W_{q+1}^T\phi_q-y_q]-(W_{q+1}-W_q)^T\phi_q.
\]

helper 的实际作用是 (u_q=\beta_q C(raw_q))，其中 (C) 是逐分量 ([-3,3]) clip，
\(\beta_q=\min((n_q+1)h/1.8,1)\)。于是

\[
u_q-y_q=(raw_q-y_q)+(\beta_q-1)raw_q+\beta_q(C(raw_q)-raw_q).
\]

使用 ‖(φ_q)‖=1 及三项 Young/Cauchy 后，对 (q=0,\ldots,1966) 有

\[
S_\delta:=\sum_q\|u_q-y_q\|^2\le12\sum_qL_q(W_{q+1})+6\sum_q\|W_{q+1}-W_q\|_F^2
+3\sum_q(1-\beta_q)^2\|raw_q\|^2+3\sum_q\beta_q^2\|C(raw_q)-raw_q\|^2.
\tag{3}
\]

为把 10 ms 标签连接到每个计分采样，定义 ̄(d_{M,q}=10^{-1}\sum_{r=0}^9d_{M,n_q+r})、ξ_q=(y_q-̄d_{M,q})、ν_{q,r}=(̄d_{M,q}-d_{M,n_q+r})。则 Σ_rν_{q,r}=0，且有精确分解

\[
u_q-d_{M,n_q+r}=(u_q-y_q)+\xi_q+\nu_{q,r},\quad
\sum_{r=0}^9\|u_q-d_{M,n_q+r}\|^2
=10\|u_q-\bar d_{M,q}\|^2+\sum_{r=0}^9\|\nu_{q,r}\|^2.
\]

因此保守但直接由损失界控制的形式为
\[
S_{\epsilon,int}\le20S_\delta+20\sum_q\|\xi_q\|^2+\sum_{q,r}\|\nu_{q,r}\|^2.
\tag{4}
\]
此处 ξ 捕获目标积分与离散采样残差之间的对齐/积分误差；ν 保留窗口内变化，不把平均标签替换成瞬时残差。

## 固定矩阵有限时域卷积与 0–20 s 分数

(A_2) 特征根为
\(\lambda_\pm=(1.995\pm\sqrt{5\times10^{-6}})/2\)，即约 0.998618034 与 0.996381966。令 (C=[1,0])，两通道冲激系数

\[
C_2=[1,0],\qquad h_1[k]=C_2A_2^k[1,0]^T,\qquad h_2[k]=C_2A_2^k[0,1]^T.
\]

由二阶递推可写为
\[
h_1[k]=c_+\lambda_+^k+c_-\lambda_-^k,\quad
c_+=\frac{.999-\lambda_-}{\lambda_+-\lambda_-}>1,\ c_-=\frac{\lambda_+-.999}{\lambda_+-\lambda_-}<0,
\]
故 (h_1[k]/\lambda_+^k=c_++c_-(\lambda_-/\lambda_+)^k\ge c_++c_-=1)；另
\(h_2[k]=.001(\lambda_+^k-\lambda_-^k)/(\lambda_+-\lambda_-)\ge0)。两根在 (0,1)，所以核非负且可和。由几何级数

\[
\sum_{k\ge0}h_1[k]=C_2(I-A_2)^{-1}[1,0]^T=800,\qquad
\sum_{k\ge0}h_2[k]=C_2(I-A_2)^{-1}[0,1]^T=200.
\]

在 20,000 个计分状态对应的 19,999 个有效冲激 tap 上，独立脚本得到 (h\sum h_1=0.799999999999174)、(h\sum h_2=0.199999999999684)；式 (5) 使用更简单的解析上界 800、200，不依赖这些浮点近似。

对任意 20,000 个计分位置样本，有限因果卷积的绝对 (\ell_1) 增益不超过上述和；对三轴向量序列，Minkowski 与离散 Young 不等式逐通道成立。记 (\mathcal C=[I_3\quad0])、(c_n=\mathcal CA^n x_0)、(f_{1,n}=hM\eta_n+\rho_{p,n})、(f_{2,n}=T_0[h\epsilon_n+\rho_{s,n}-M\rho_{\eta,n}])，其中 (\epsilon_n=u_n-d_{M,n})、(T_0=1\,s)。则

\[
\begin{aligned}
\|e_{0:19999}\|_{\ell_2}
&\le \|c_{0:19999}\|_{\ell_2}+800\|f_{1,0:19999}\|_{\ell_2}+200\|f_{2,0:19999}\|_{\ell_2}\\
&\le \|c\|_{\ell_2}+800(h\|M\eta\|_{\ell_2}+\|\rho_p\|_{\ell_2})
+200T_0(h\|\epsilon\|_{\ell_2}+\|\rho_s-M\rho_\eta\|_{\ell_2}).
\end{aligned}
\tag{5}
\]

若把实际位置 forcing 写成物理通道，PCF eta 的增益为 800h=0.8 s，预测/保持误差的增益为 200T_0h=0.2 s^2（因 T_0=1 s）；位置项采样余项系数为 800，速度坐标采样余项系数为 200T_0。式 (5) 用完整离散 forcing 序列，避免把 h epsilon 的单位漏掉。

计分代码取 (state[0:20000]) 对 (reference[0:20000]) 的 20,000 个三轴误差，故
\[
Q_{0:20}=\sqrt{\frac1{20000}\sum_{n=0}^{19999}\|e_n\|_2^2}
\le \frac{\text{式 (5) 右侧}}{\sqrt{20000}}.
\]
启动边界为 ([0,320)\) 共 320 个样本；学习/保持区间为 (q=0,\ldots,1966)，共 19,670 个样本，覆盖 ([320,19990)\)；末边界 ([19990,20000)\) 共 10 个样本，没有后继在线预测更新。令 (S_{\epsilon,start})、(S_{\epsilon,tail}) 为从实际 1 ms 输出直接计算的边界误差能量，则式 (5) 中
\[
\|\epsilon\|_{\ell_2}^2=S_{\epsilon,start}+S_{\epsilon,int}+S_{\epsilon,tail}.
\]
边界输入按实际命令记录记账，不补造 n=20000 标签或更新。包括 n=19999 的 forcing 只会让式 (5) 更保守，因为该输入影响未计分的 (e_{20000})。

把式 (2) 代入式 (3)，再用式 (4) 和边界能量，得到复合有限时域上界：
\[
Q_{0:20}\le\frac{1}{\sqrt{20000}}\left[\|c\|_{\ell_2}+800(h\|M\eta\|_{\ell_2}+\|\rho_p\|_{\ell_2})+200T_0\left(h\sqrt{S_{\epsilon,start}+S_{\epsilon,tail}+20S_\delta+20\sum_q\|\xi_q\|^2+\sum_{q,r}\|\nu_{q,r}\|^2}+\|\rho_s-M\rho_\eta\|_{\ell_2}\right)\right].
\]
其中 (S_\delta) 由式 (3) 控制，其累计损失项再由式 (2) 控制。右侧全是已实现路径或固定初值上的有限序列；没有把平均标签当瞬时信号，也没有把采样余项置零。

## 松弛、适用范围与状态

对盒内比较器 (U=W_0)，(R\le(60+1.336968184)\sqrt{99}\approx610.5)。又因 ‖(φ)‖=1、(\|s_{eff}\|\le\sqrt{213})、(\beta\le1)，有
\(\|H_k\|_F\le.12\sqrt{213}+.00002(60\sqrt{99})\approx1.764\)。逐事件都取该最坏值后，式 (2) 仅 (2R\sum\|H_k\|) 一项就会令累计损失上界达到约 (4\times10^8) 量级（尚未计比较器损失）；这是有限但无实用解释力的盒界。须用实际锁定轨迹的 (H,L(U),\Delta W,\eta,\rho,\xi,\nu) 才能得到有信息量的后验数值，不可由此臆报该数值已经通过。

目前产物只证明：固定实现下存在明确的、有限时域、逐路径可复算的位置误差充分界；它在形式上把预测损失/参数增量/ramp/clip、保持区间变化、PCF eta 与采样余项接到 (Q)。当前没有读取指定 raw 来代入右侧，也没有证明路径 forcing 可由状态反馈吸收、没有未来统一界、没有持续激励/参数收敛或闭环稳定证明。故本构造不能将理论门从 **NOT_MET** 改成 PASS，论文充分性仍待主审判断。

## 符号与冻结源码对应

| 数学对象 | 冻结来源与对应位置 |
|---|---|
| (M=I,0) 的延迟标签、过去区间索引、先输出后更新 | C3 runner `run_dl1018_closed_loop.m:2005–2031`；C4 runner `:2020–2045, 2059–2065`。C4 分支 (M=1) 积分 (a_f)，(M=0) 积分 (a^{req})，并用 `nZero-previousIndex==10` 检查完整过去区间。 |
| (M=\operatorname{diag}(1,1,0))、混合参考和 (M\eta,M\rho_\eta) 位置 | C5 runner `run_dl1018_closed_loop.m:2014, 2030–2033, 2266–2267`；`CONSTANT_DIAGONAL_M_ADDENDUM_ZH.md:1–6`（固定 C5 理论范围；不外推动态矩阵）。 |
| 单位范数 (φ)、(H)、旧标签梯度、beta 与联合盒投影 | 两份锁定 helper `delayed_prediction_step_candidate.m:3–12, 41–46`；helper SHA `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`。 |
| held (u_q)、权重事件差 | C4 runner `:2113–2125`；10 ms 积分按 1 ms 更新见 `:2269–2277`。 |
| 1 ms (\rho_p,\rho_s,\rho_\eta,\bar Y) 与递推定义 | `EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md:5–19`；PCF 实际滤波/eta 积分 `position_filter_realization_pcf_step_v3_5.m:17–24`。 |
| (a^{req}=a_{nom}-u) 与 (a_{nom}) | `position_bs_step.m:25–31`（残差力命令关系），与上述冻结 runner 的 applied acceleration 对齐。 |
| 20,000 样本、20,001 状态和 Q 归一化 | `parent_raw_metrics.py:75–89`，取 `state[:-1]`、`reference[:-1]`，窗口为 (t\in[0,20))。 |
| 实际固定矩阵极点、核非负与离散卷积核和 | 本文解析式；独立可运行数值交叉检查见 `verify_finite_horizon_bridge.py` 及其输出 JSON。 |
