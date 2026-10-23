# 原物理残差坐标的精确采样引理

## 命题与归一化

取 \(T_0=1\,\mathrm{s}\)、\(h=0.001\,\mathrm{s}\)、\(\delta=h/T_0=0.001\)、\(K_1=I\)、\(K_2=4I\)。令
\[
e_n=r_n-p_n,\qquad s_n=\dot r_n+e_n-v_n,\qquad
\sigma_n=T_0s_n .
\]
用 \(\tilde u=T_0^2u\)、\(\tilde d_0=T_0^2d_0\)、\(\tilde r_f=T_0^2r_f\)、\(\tilde\rho_s=T_0\rho_s\)、\(\tilde\eta=T_0\eta\)、\(\tilde\rho_\eta=T_0\rho_\eta\) 归一化。这样 \(e,\sigma,\tilde\eta,\tilde\rho_s\) 均以米为单位。这里
\[
d_{0,n}=\frac{v_{n+1}-v_n}{h}-a^{req}_n
\]
是相邻样本速度增量定义，不能替换成连续时间瞬时加速度误差。\(u_n\) 表示位置反步命令中实际施加的补偿加速度；\(a^{req}_n\) 是扣除该补偿后的命令加速度。

按冻结采样定义
\[
\rho_{p,n}=(r_{n+1}-r_n-h\dot r_n)-(p_{n+1}-p_n-hv_n),\qquad
\rho_{s,n}=(\dot r_{n+1}-\dot r_n-h\ddot r_n)+\rho_{p,n}.
\]
本命题是相邻样本的代数命题，\(\rho_p,\rho_s\) 保留参考采样及 Plant 积分余项，不假设为零。

## 物理坐标递推

由定义直接得到
\[
e_{n+1}=e_n+h(s_n-e_n)+\rho_{p,n}.
\]
同时
\[
s_{n+1}-s_n=h(\ddot r_n+s_n-e_n-a^{req}_n-d_{0,n})+\rho_{s,n}.
\]
冻结的 BS 公式是
\[
a^{req}=\ddot r+K_1(\dot r-v)+K_1^2e+K_2s-u
=\ddot r+5s-u
\]
（最后一等号只在本命题的 \(K_1=I,K_2=4I\) 下成立）。所以
\[
\begin{bmatrix}e_{n+1}\\ \sigma_{n+1}\end{bmatrix}
=A_2\begin{bmatrix}e_n\\ \sigma_n\end{bmatrix}
+\begin{bmatrix}\rho_{p,n}\\ \tilde\rho_{s,n}\end{bmatrix}
+\begin{bmatrix}0\\ \delta(\tilde u_n-\tilde d_{0,n})\end{bmatrix},
\quad
A_2=\begin{bmatrix}0.999&0.001\\-0.001&0.996\end{bmatrix}.
\]
置
\[
d_{M,n}=d_{0,n}+Mr_{f,n},\qquad
\epsilon_{M,n}=u_n-d_{M,n}.
\]
恒等地，\(\tilde u-\tilde d_0=\tilde\epsilon_M+M\tilde r_f\)。因此物理位置递推的补偿残差是
\[
\delta(\tilde\epsilon_M+M\tilde r_f),
\]
而非单独的 \(\delta\tilde\epsilon_M\)。

## 保留 PCF 离散余项的增广坐标

PCF helper 实际使用精确指数保持：
\[
\tilde\eta_{n+1}=\alpha\tilde\eta_n+\beta\tilde r_{f,n},
\qquad \alpha=e^{-4\delta},\quad \beta=\frac{1-\alpha}{4}.
\]
定义
\[
\tilde\rho_{\eta,n}
=\tilde\eta_{n+1}-(1-4\delta)\tilde\eta_n-\delta\tilde r_{f,n}
=(\alpha-(1-4\delta))\tilde\eta_n+(\beta-\delta)\tilde r_{f,n}.
\]
这是实际指数更新相对 Euler 采样式的精确余项；不得把它丢掉或视作与 \(\eta,r_f\) 无关的独立物理输入。

令 \(y_n=\sigma_n-M\tilde\eta_n\)，\(z_n=[e_n;y_n;\tilde\eta_n]\)。固定对角掩码 \(M\) 与标量 \(0.996I\) 可交换，故精确增广式为
\[
z_{n+1}=
\underbrace{\begin{bmatrix}
0.999I&\delta I&\delta M\\
-\delta I&0.996I&0\\
0&0&0.996I
\end{bmatrix}}_{\mathcal A_M}z_n
+\begin{bmatrix}
\rho_{p,n}\\
\tilde\rho_{s,n}-M\tilde\rho_{\eta,n}\\
\tilde\rho_{\eta,n}
\end{bmatrix}
+\begin{bmatrix}
0\\
\delta\tilde\epsilon_{M,n}\\
\delta\tilde r_{f,n}
\end{bmatrix}.
\]
把第二、三行相加并恢复 \(\sigma=y+M\tilde\eta\)，恰得前一节物理递推。尤其是 \(-M\tilde\rho_\eta\) 与 \(+M\tilde\rho_\eta\) 在物理坐标中抵消；它们不能分别当成独立因果通道。

## 传递函数及 PCF 极点抵消

以单边 \(z\) 变换 \(X(z)=\sum_{n\ge0}x_nz^{-n}\) 记号。令
\[
D(z)=\det(zI-A_2)=z^2-\frac{399}{200}z+\frac{199001}{200000}.
\]
直接由 \((zI-A_2)^{-1}=D^{-1}\begin{bmatrix}z-0.996&\delta\\-\delta&z-0.999\end{bmatrix}\)，得到
\[
E(z)=
\frac{z((z-0.996)e_0+\delta\sigma_0)}{D(z)}
+\frac{z-0.996}{D(z)}P(z)
+\frac{\delta}{D(z)}R_s(z)
+\frac{\delta^2}{D(z)}\bigl(\mathcal E_M(z)+M R_f(z)\bigr),
\]
其中 \(P,R_s,\mathcal E_M,R_f\) 分别是 \(\rho_p,\tilde\rho_s,\tilde\epsilon_M,\tilde r_f\) 的变换。故零初值通道
\[
H_{\epsilon_M\to e}(z)=\frac{\delta^2}{D(z)},\qquad
H_{r_f\to e}(z)=\frac{M\delta^2}{D(z)}.
\]

同一结论可从 PCF 增广式独立得到。记 \(d=1-4\delta\)，则 \(\eta\) 到 \(e\) 的子系统通道为 \(\delta M(z-d)/D(z)\)。对实际指数 PCF，\(R_\eta=((\alpha-d)\Eta+(\beta-\delta)R_f)\)，且 \(\Eta=\beta R_f/(z-\alpha)\)（零初值）。\(r_f\) 经 \(\eta\) 与 \(-M\rho_\eta\) 两条坐标路径之和为
\[
\frac{\delta M}{D(z)}
\left[
\frac{\beta(z-d)}{z-\alpha}
-\frac{(\alpha-d)\beta}{z-\alpha}
-(\beta-\delta)
\right]
=\frac{M\delta^2}{D(z)},
\]
因为
\[
\beta(z-d)-\beta(\alpha-d)-(\beta-\delta)(z-\alpha)
=\delta(z-\alpha).
\]
因此 \(z=\alpha\) 的 PCF 极点严格抵消。首状态也一致：将固定物理 \(\sigma_0\) 表成增广初态 \(y_0=\sigma_0-M\tilde\eta_0\) 后，\(\tilde\eta_0\) 经增广状态与余项的贡献抵消，\(E(z)\) 只剩所列 \(e_0,\sigma_0\) 初值项。

## 20,000 点有限卷积界

令 \(N=20{,}000\)，并记 \(\|x\|_{2,N}^2=\sum_{n=0}^{N-1}\|x_n\|_2^2\)。所用评分量为
\[
Q_N=\sqrt{\frac1N\sum_{n=0}^{N-1}\|e_n\|_2^2};
\]
这是三轴平方和后除以 20,000 的均方根，与冻结 scorer 的样本选择一致。物理递推的显式分解为
\[
e_n=CA_2^nx_0+
\sum_{i=0}^{n-1}(A_2^{n-1-i})_{11}\rho_{p,i}
+\sum_{i=0}^{n-1}(A_2^{n-1-i})_{12}
(\tilde\rho_{s,i}+\delta\tilde\epsilon_{M,i}+\delta M\tilde r_{f,i}),
\quad C=[1\;0].
\]
初值项记为
\[
J_N=\left(\sum_{n=0}^{N-1}
\|(A_2^n)_{11}e_0+(A_2^n)_{12}\sigma_0\|_2^2\right)^{1/2}.
\]

两个卷积核在全部 \(k\ge0\) 非负。精确特征根为
\[
\lambda_\pm=\frac{399}{400}\pm\frac{\sqrt5}{2000},\qquad
0<\lambda_-<\lambda_+<0.999<1.
\]
因而
\[
(A_2^k)_{11}
=\frac{(0.999-\lambda_-)\lambda_+^k-(0.999-\lambda_+)\lambda_-^k}
{\lambda_+-\lambda_-}>0,
\quad
(A_2^k)_{12}
=\delta\frac{\lambda_+^k-\lambda_-^k}{\lambda_+-\lambda_-}\ge0.
\]
稳定性与正项求和给出
\[
\sum_{k=0}^\infty(A_2^k)_{11}=[(I-A_2)^{-1}]_{11}=800,\qquad
\sum_{k=0}^\infty(A_2^k)_{12}=[(I-A_2)^{-1}]_{12}=200.
\]
有限核是这些正项级数的截断，因此其 \(\ell_1\) 范数不超过 800 与 200。Young 卷积不等式遂给出严格的有限序列界
\[
\boxed{\displaystyle
Q_{20\,000}\le
\frac{J_N+800\|\rho_p\|_{2,N}
+200\|T_0\rho_s\|_{2,N}
+200\delta\|T_0^2(\epsilon_M+Mr_f)\|_{2,N}}
{\sqrt{20\,000}}.}
\]
其中 \(200\delta=0.2\)。这也推出较松的拆分界：最后一项可用
\(0.2(\|T_0^2\epsilon_M\|_{2,N}+\|T_0^2Mr_f\|_{2,N})\)
替换。上述增益是对任意 20,000 点 forcing 序列成立的有限时域条件界，不是本任务对 forcing 的数值估计。

所有分解量都在同一条物理轨迹上。令 \(E^0,E^p,E^s,E^\epsilon,E^r\) 分别代表初值、\(\rho_p\)、\(\rho_s\)、\(\epsilon_M\)、\(Mr_f\) 的位置响应，则准确恒等式是
\[
\|E^0+E^p+E^s+E^\epsilon+E^r\|_2^2
=\sum_j\|E^j\|_2^2+2\sum_{i<j}\langle E^i,E^j\rangle.
\]
同样，
\[
\|u-d_0\|_{2,N}^2
=\|\epsilon_M\|_{2,N}^2+\|Mr_f\|_{2,N}^2
+2\langle\epsilon_M,Mr_f\rangle_{2,N}.
\]
交叉项不能假设为零。特别地，\(\epsilon_M=0\) 时仍留下 \(Mr_f\) 位置通道；但仅从同轨迹分解不能推断移除或修改该通道后的闭环反事实，也不能比较处于不同状态轨迹的 B 与 C5 组件。

## 对自适应坐标与旧条件证明的边界

当 \(M=0\) 时，该等式中的直接 \(r_f\) 项消失；当 \(M=I\) 时，完美拟合 \(d_M\) 仍可有 \(Mr_f=r_f\) 的实际物理 forcing。真实部署中 \(u,d_0,r_f,\epsilon_M\) 均由闭环状态、BS 请求、姿态/推力映射和有界/投影 Head 共同生成。\(d_M\) 能否被当前特征、权重约束和输出裁剪实际表示也未由此证明。因此 \(M=0\) 的理想代数不意味着实际自适应系统总优于 \(M=I\)，\(M\) 的分解项也不是互相独立可操纵的因果变量。

这项物理坐标引理与旧 delay-memory/leak/projection 证明相容：旧证明在 \(x_c=[e,T_0(s-M\eta)]\) 坐标中显式保留 \(M\eta,\rho_p,\rho_s,M\rho_\eta\)，并给定有限路径的 comparator、ramp、裁剪、标签对齐和投影扰动后导出事件级储能与位置界。本引理把同一采样关系改写回物理 \([e,T_0s]\) 坐标，说明这些 PCF 坐标项整体恢复为 \(\epsilon_M+Mr_f\) 的物理 forcing；它不取代旧证明中对权重记忆和投影的条件储能步骤，也没有从初始条件推出该 forcing 或其余项的统一上界。

**可支持的结论仅为：** 对任务中冻结 \(A_2,K_1,K_2,M\) 和精确定义的采样余项，以上一步关系、PCF 极点抵消、转移函数与 20,000 点卷积增益是精确代数/有限时域结果。对实际 C5 的 \(\epsilon_M,r_f,\rho_p,\rho_s\) 路径，本报告没有代入 raw 或证明先验界、域自洽、反馈可吸收或 Plant 全局稳定；理论门仍不能据此从 NOT_MET 升级。

## 源码映射

- 冻结采样定义：EXACT_SAMPLED_ERROR_ACCOUNTING_TASKBOOK_ZH.md 第 5–19 行给出 \(\rho_p,\rho_s,\bar Y,d_c,\rho_\eta\) 与离散递推；任务书中的 \(d_0\) 正是 \(\bar Y\)。
- BS 输入和请求：matlab/core/position_bs_step.m 第 19–56 行定义 \(e,de,s\)、\(a_{\rm nominal}\)、\(a_{\rm commanded}=a_{\rm nominal}-\mathrm{residualForce}/m\)。故本命题的 \(u\) 是实际传入残差力除以质量，\(a^{req}\) 是 helper 返回的 commanded_acceleration；C5 runner 第 2128、2138、2155 行把 Head applied 转为残差力并送入该 helper。
- PCF 物理定义：matlab/models/position_filter_realization_pcf_step_v3_5.m 第 13–21 行定义 \(a_f\)、\(r_f=a^{req}-a_f\) 及指数保持 \(\eta^+=e^{-4h}\eta+(1-e^{-4h})r_f/4\)。C5 runner 第 2257–2261 行以 commanded_acceleration 调用 helper 并记录 \(a^{req},a_f,r_f\)。
- 固定掩码和预测参考：C5 runner 中 positionCoordinateMask 设为 \([1,1,0]\)；第 2267–2268 行在被屏蔽轴保留 \(a^{req}\)，其它轴使用 \(a_f\)。本命题对固定掩码成立，不扩展到时变或非对角 \(M\)。
- 与旧条件储能的衔接：DELAY_STORAGE_PERTURBATION_BOUND_ZH.md 第 21–29、51–64、174 行采用 \(x_c=[e,T_0(s-M\eta)]\)，逐项保留 \(M\eta,\rho_p,\rho_s,M\rho_\eta\) 与延迟更新扰动，并明确它们是实际路径量、未获统一先验界。
- 评分索引：reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py 第 81–85 行使用 state/reference 的前 20,000 样本，按三轴平方和除以样本数计算 \(Q_{0:20}\)。

## 可复核对象

- checker：verify_physical_residual_tracking_lemma.py，只用 Python 标准库 Fraction 和符号多项式，核验坐标相似变换、\(\rho_\eta\) 强制保留、PCF 极点抵消恒等式、精确 \(A_2\) 常数及正核增益。
- 实际执行结果：EXACT_CHECK_RESULT.json；PowerShell 调用与操作系统退出码见 EXECUTION_RECORD.json。
- 冻结输入及其 SHA、源码行号见 SOURCE_IDS.json。
