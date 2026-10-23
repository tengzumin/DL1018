# 联合状态—权重最小诊断

**结论：** 固定特征的一轴必要子情形有严格离散二次Lyapunov函数；但这不能推出特征时变、旧样本与当前特征不同的全域闭合。一个明确无PE的两事件例子仍稳定，不过任意特征切换的共同二次能量尚未建立。理论门保持 **NOT_MET**，不建议把当前结果扩写成闭环稳定性证明。

## 实际10步提升与事件顺序

按冻结C5的一个 (m=1) 轴，令 (x=[e,T_0z]^T, z=s-m\eta)，并固定 (T_0=1)。1 ms矩阵为
\[
A=\begin{bmatrix}.999&.001\\-.001&.996\end{bmatrix}.
\]
事件 (q) 的输出先于权重更新，且在随后10个采样步保持：
\[
x_{q,r+1}=Ax_{q,r}+b_u u_q+d_{q,r},\quad b_u=[0,\ T_0dt]^T,\quad r=0,\ldots,9,
\]
\[
d_{q,r}=\begin{bmatrix}dt\,m\eta_{q,r}+\rho_{p,q,r}\\
T_0(-dt\,d_{M,q,r}+\rho_{s,q,r}-m\rho_{\eta,q,r})\end{bmatrix}.
\]
因此
\[
x_{q+1}=F x_q+g u_q+\delta_q,\quad F=A^{10},\quad
g=\sum_{r=0}^{9}A^{9-r}b_u,\quad
\delta_q=\sum_{r=0}^{9}A^{9-r}d_{q,r}.
\]
数值为
\[
F=\begin{bmatrix}.990000594775&.009777384319\\-.009777384319&.960668441818\end{bmatrix},\quad
g=\begin{bmatrix}4.440418116\cdot10^{-5}\\.009821788500\end{bmatrix}.
\]

helper的 `applied` 是当前事件输出，随后才以当前 (W_q,\phi_q,s_{eff,q}) 更新到 (W_{q+1})：见冻结helper第41–46行；旧预测梯度在第37–40行，常量在第4–5行。令 (psi_q=phi_{q-1})，一输出轴的精确未裁剪更新写成
\[
w_{q+1}=D_{\psi_q}w_q-c\beta_q\phi_qs_{eff,q}
 +\rho\psi_qy_{q-1},\quad
D_{\psi}=(1-h\lambda)I-\rho\psi\psi^T,\quad c=h\gamma=.12.
\]
以下更新式仅用于有历史标签的 (q\ge1) 事件；首次ready事件 (n=320) 没有旧标签，helper令预测梯度为零。
这保留了“输出 (u_q=\beta_q\operatorname{clip}_3(\phi_q^Tw_q)) 后再更新”的顺序；不是用当前标签替换 (y_{q-1})。

## 固定特征必要子情形

只为代数必要子情形设 (phi_q=psi_q=1, y_{q-1}=0, eta_q=1, s_{eff,q}=z_q)，并令 (eta,delta_q) 为零、裁剪和投影不激活。该条件等价于选一个可表示的零残差工作点，不代表实际启动时ramp已满。于是 (u_q=w_q)，联合矩阵为
\[
J=\begin{bmatrix}
.990000594775&.009777384319&.000044404181\\
-.009777384319&.960668441818&.009821788500\\
0&-.12&.98998
\end{bmatrix}.
\]
实算根为 (0.9900398825, 0.9753045770pm0.0325576068i)，谱半径 (0.9900398825<1)。用 (J^TPJ-P=-I) 解得 (P\succ0)，最小特征值 (11.2499662)，方程残差Frobenius范数 (1.47\cdot10^{-14})。所以**这一固定矩阵**的联合二次能量严格闭合。

## 不同当前/过去特征、无PE检查与停止点

取 (phi_q=e_1,e_2,e_1,e_2,\ldots) 于三维特征空间。其周期协方差为 (operatorname{diag}(1/2,1/2,0))，秩2，小于特征维数3，故无全维PE；同时每步当前/过去特征不同。实际两事件提升矩阵的最大乘积根模为 (0.9999600004)，对应每事件 (0.99998)。其余四个根模均小于1。该特定周期稳定，但最慢方向正是未激励权重只靠泄漏衰减；这不是任意切换证明。

精确阻碍“直接抵消”的项可从候选能量 (E=x^TP_xx+\alpha\|w\|^2) 看出。权重部分变化含
\[
-2\alpha c z_q\,w_q^TD_{\psi_q}^T\phi_q.
\]
状态输入交叉项只含 (phi_q^Tw_q)。当 (w\perp\phi) 但 (w^T\psi\ne0) 且 (psi^T\phi\ne0) 时，状态输入交叉项为零，而
\[
w^TD_\psi^T\phi=-\rho(w^T\psi)(\psi^T\phi)
\]
仍留下符号不定的能量项。比如 (phi=e_1,psi=(e_1+e_2)/\sqrt2,w=e_2) 时，该交叉项为 (+0.0012\alpha z_q)。它可能被其他状态/权重耗散吸收，但本诊断没有给出对所有单位特征切换统一有效的矩阵不等式；这**不是**“不存在任何共同Lyapunov函数”的反例。

因此停止在这里：固定特征判为闭合；对任意特征变化、旧样本差异和无PE路径，统一联合二次界 **未闭合**。若要继续，需另行核实能否以统一矩阵不等式吸收上述错位项；否则不可从现有有限轨迹或路径界推出闭环稳定。这里未假设滤波误差、特征变化、逼近误差或 \(\eta\) 有独立统一界；若这些上界由闭环状态本身给出，会形成循环条件。

## 可复核产物

- 代数脚本：[diagnose_joint_state_weight.py](diagnose_joint_state_weight.py)，SHA-256 `5EF156235776CBE34246DF602553E46F8E55E1B14E2CBF3A1B4F3A932148C034`。
- 实际结果：[joint_state_weight_matrix_results.json](joint_state_weight_matrix_results.json)，SHA-256 `56A997361D3BC0C09F8AE68F160694BE8020E81EA0408CF6900FC663717E85D6`。
- 命令：`python 'reports/paper_continuation_20261023/finite_horizon_certificate/joint_state_weight_diagnosis/diagnose_joint_state_weight.py'`；Python进程真实退出码0。
- 依据：主任务书SHA-256 `0AEFCBBFD9914EF27FAC95F6B3E6A74A1477ECB02056A7A9C634C87FD76439C7`；固定M补充 `32E5B41673A5E7FDF8555AE2B4B5B1BE63F2E10C5783EF184DC53F65C530EEFC`；采样递推任务书 `104B9DA52F2885BD53C2D122BA84ED09ED121D79AF6215F9E59593C0EEF0E606`；冻结helper SHA-256 `48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`。
- 本次仅作矩阵代数；未读取72场raw，未启动MATLAB/Plant、训练或TEST；未更改理论原文或控制器。
