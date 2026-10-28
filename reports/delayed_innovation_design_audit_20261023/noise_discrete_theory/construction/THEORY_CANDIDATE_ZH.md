# 原离散 Head 更新与延迟预测项：理论候选

状态：源码推导候选，待独立审核。只讨论冻结 Head 的离散更新和一个固定延迟样本的一步关系；不提出或运行新控制律，不据此宣称闭环稳定。

## 锁定源码与口径

本推导针对 C1 的 FEATURE Head。归档运行时文件 run_dl1018_closed_loop.m（SHA-256 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b）在 1947–1968 行计算当前事件的 \(\phi_k\)、\(\beta_k\)、PCF 有效表面 \(s_{\mathrm{eff},k}\)，调用 Head 得到当前 raw/applied 输出及下一权重；2027–2030 行再用当前 applied 输出构造 held force。position_only_search_head_step.m（SHA-256 3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc）第 12–19 行是 FEATURE 分支：先算 raw 与 \(\beta\)-scaled clipped output，再更新权重并投影。position_bs_step.m（SHA-256 ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681）第 17–27、52–59 行给出位置误差、表面、名义加速度与实际请求加速度。C1 源锁 C1_SOURCE_LOCK_v2.json SHA-256 为 02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5；其中冻结配置 configs/effective_config.mat SHA-256 为 cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f。

设事件间隔 \(h\)，状态 \(W_k\in\mathbb R^{33\times3}\)，特征列向量 \(\phi_k\in\mathbb R^{33}\)，Head raw 向量 \(z_k=W_k^\top\phi_k\in\mathbb R^3\)。实际输出为
\[
u_k=\beta_k\,\operatorname{clip}_{d_{\max}}(z_k), \qquad
\operatorname{clip}_{d_{\max}}(z)_a=\max(-d_{\max,a},\min(z_a,d_{\max,a})).
\]
FEATURE 权重的一步更新为
\[
\bar W_{k+1}=W_k-U_k,\quad U_k=h\bigl(\gamma\beta_k\phi_k s_{\mathrm{eff},k}^{\top}+\lambda W_k\bigr),\quad
W_{k+1}=\Pi_{\mathcal B_{60}}(\bar W_{k+1}),
\]
其中 \(\lambda=0.002\,\mathrm{s}^{-1}\)，\(\mathcal B_{60}=\{W:|W_{ia}|\le60\}\)，\(\Pi\) 为逐元素 box projection。源码中的 \(\gamma\) 是跟踪自适应系数（C1 为 \(12\,\mathrm{s}^{-2}\)），不是 prediction gain；配置给出 \(d_{\max}=(3,3,3)\,\mathrm{m/s^2}\)、\(dt=1\,\mathrm{ms}\)、\(\beta=\min(t/1.8\,\mathrm{s},1)\)。Head 事件间隔 \(h\) 来自 rbfFullDt，本组记录为 10 ms。

量纲按物理单位解释：位置误差 \(e\) 是 m，表面 \(s\) 与 \(s_{\rm eff}\) 是 m/s，\(\phi,\beta\) 无量纲，\(W,z,u\) 是 m/s²；所以 \(h\gamma s_{\rm eff}\) 与 \(h\lambda W\) 均与 \(W\) 同量纲。position_bs_step.m 第 24 行写入的数值 \(e\) 项在物理单位下应读作 \(c_e e\)，其中 \(c_e=1\,\mathrm{s}^{-2}\)；不得把 \(e^2\)（m²）直接与 \(s^2\)（m²/s²）相加。

## 参数误差的一步关系

若作条件性假设：存在常数理想权重 \(W^\star\in\mathcal B_{60}\)，并定义 \(\tilde W_k=W^\star-W_k\)，则投影位移 \(R_k=W_{k+1}-\bar W_{k+1}\) 满足
\[
\|\tilde W_{k+1}\|_F^2\le \|\tilde W_k+U_k\|_F^2-\|R_k\|_F^2.
\]
这是欧氏 box projection 对任意盒内参考点的投影性质。取 \(E_{W,k}=\|\tilde W_k\|_F^2/(2\gamma)\)，得到冻结离散更新的精确上界
\[
E_{W,k+1}-E_{W,k}\le
h\beta_k\langle\tilde W_k,\phi_k s_{\mathrm{eff},k}^{\top}\rangle_F
+\frac{h\lambda}{\gamma}\langle\tilde W_k,W_k\rangle_F
+\frac{\|U_k\|_F^2-\|R_k\|_F^2}{2\gamma}.
\]
这里的 \(+\|U_k\|^2\) 是离散显式步的二阶项，不能省略后再称为逐步耗散。投影只给出相对盒内 \(W^\star\) 的非扩张修正；它不抵消任意 tracking 交叉项。leak 项也不是相对任意非零 \(W^\star\) 的纯耗散，因为
\[
\langle\tilde W,W\rangle=\langle\tilde W,W^\star\rangle_F-\|\tilde W\|_F^2
\]
可为正或负；只有 \(W^\star=0\) 时 leak 单独收缩到零（当 \(0<h\lambda<2\)）。
若仅作符号化比较，令 \(U_{\rm orig}=U_k\)，并取固定旧样本 raw 梯度 \(G_r=\phi_j e_r^\top\)，假设另加一项但不执行：\(U_{\rm joint}=U_{\rm orig}+\alpha_pG_r\)，\(\bar W^+=W_k-U_{\rm joint}\)、\(W^+=\Pi_{\mathcal B_{60}}(\bar W^+)\)、\(R^+=W^+-\bar W^+\)。同一投影论证给出
\[
E_W^+-E_W\le h\beta_k\langle\tilde W,\phi_k s_{\rm eff,k}^\top\rangle_F
+\frac{h\lambda}{\gamma}\langle\tilde W,W_k\rangle_F
+\frac{\alpha_p}{\gamma}\langle\tilde W,G_r\rangle_F
+\frac{\|U_{\rm orig}+\alpha_pG_r\|_F^2-\|R^+\|_F^2}{2\gamma},
\]
其中平方项含 \(2\alpha_p\langle U_{\rm orig},G_r\rangle_F+\alpha_p^2\|G_r\|_F^2\)。\(\alpha_p\) 只是未选取的符号系数；若改用 applied loss，须将 \(G_r\) 换成该样本处的 \(G_a\)。这项显式参数更新与后文仅作为分析/监测组合量的 \(V+\mu L_r\) 不同；后者不会把 \(G_r\) 加入更新，也不自动获得耗散符号。原冻结代码仍只有 \(U_{\rm orig}\)；这里没有选择或执行新增 prediction 更新，也未证明其交叉项有耗散符号。

## 与 BS 跟踪能量的条件性连接

冻结 BS 源第 17–27 行给出 \(e=r-p\)、\(\dot e=\dot r-v\)、\(s=\dot e+k_1e\)，以及
\[
a_{\rm nominal}=\ddot r+k_1\dot e+c_e e+k_2s,\qquad
a_{\rm req}=a_{\rm nominal}-u .
\]
若另作理想连续外环假设 \(a_{\rm actual}=a_{\rm nominal}-u+\xi\)，则
\[
\dot s=-c_e e-k_2s+u-\xi,\qquad
V_B=\tfrac12c_e\|e\|^2+\tfrac12\|s\|^2,
\]
\[
\dot V_B=-c_e e^\top k_1e-s^\top k_2s+s^\top(u-\xi).
\]
\(V_B\) 两项均为 m²/s²。这里 \(\xi\) 是进入理想 BS 误差方程的等效加速度扰动；它没有被源码或本离线构造证明等于延迟目标。

再作更强的理想假设 \(\xi=d_c=\phi_k^\top W^\star\)，令 \(z_k=W_k^\top\phi_k\)。实际 \(\beta\)-clip 输出满足恒等分解
\[
u_k-d_c=-\beta_k\phi_k^\top\tilde W_k
+(\beta_k-1)d_c+\beta_k\bigl(\operatorname{clip}(z_k)-z_k\bigr).
\]
所以连续名义 tracking 交叉项与无 leak、无投影的自适应能量项仅在 \(\beta_k=1\)、未 clipping、\(s_{\rm eff,k}=s_k\) 时精确抵消。一般还剩：
\[
s^\top[(\beta-1)d_c+\beta(\operatorname{clip}(z)-z)]
+\beta(s_{\rm eff}-s)^\top\phi^\top\tilde W,
\]
另有上式离散 \(\|U\|^2/(2\gamma)\)、leak 与 box projection 项。C1 的 PCF 路径在归档运行时 1953–1963 行先取 \(\eta\) 的事件前状态，再令 \(s_{\rm eff}=\operatorname{clip}(s-\eta,\pm[7,8,10])\)；它通常既不等于 \(s\)，也不是延迟 prediction 残差。若把实际 RK4/采样闭环的一步变化写成
\[
\Delta V_B=h[-c_e e^\top k_1e-s^\top k_2s+s^\top(u-\xi)]+\rho_k,
\]
则该式可定义精确余项 \(\rho_k\)，但本推导没有给出其符号或上界；它包含 RK4、10 ms 保持、滤波/姿态实现、参考和扰动变化等离散差异。因此连续式的交叉抵消不是实际 C1 闭环的一步稳定性证明。
在 PCF 坐标下还可明确标签对应关系。令瞬时 \(Y=a_{\rm actual}-a_{\rm req}\)、\(r_f=a_{\rm req}-a_f\)，则 \(d=Y+r_f=a_{\rm actual}-a_f\)。在理想连续关系 \(\dot s=-c_e e-k_2s+u-Y\)、\(\dot\eta=-k_2\eta+r_f\)、\(s_c=s-\eta\) 下，
\[
\dot e=s_c+\eta-k_1e,\qquad \dot s_c=-c_e e-k_2s_c+u-d.
\]
因此 \(d\) 是 \(s_c\) 方程中的目标项；在原 \(s\) 坐标中扰动项是 \(Y\)，并非 \(d\)。取 \(V_c=\tfrac12c_e\|e\|^2+\tfrac12\|s_c\|^2\)，其导数为 \(-c_e e^\top k_1e-k_2\|s_c\|^2+s_c^\top(u-d)+c_e e^\top\eta\)，多出 \(c_e e^\top\eta\)。这只是连续理想坐标恒等式；用于延迟事件的区间均值目标是对 \(d\) 的采样近似，仍有前述离散余项，不能把 \(d\) 直接认作原坐标的 \(\xi\)。

## 延迟 prediction loss 的一步关系

本诊断使用固定旧样本 \((\phi_j,d_{j:k})\)，其中 \(j=k-10\)；\(d_{j:k}\) 是该 10 ms 区间目标，只在 k 可得。对同一个旧样本，以当前 \(W_k\) 及更新后的 \(W_{k+1}\) 比较，定义
\[
z_j(W)=W^\top\phi_j,\quad
e_r=z_j(W_k)-d_{j:k},\quad
L_r(W)=\tfrac12\|W^\top\phi_j-d_{j:k}\|^2.
\]
设 \(\delta W_k=W_{k+1}-W_k=-U_k+R_k\)、\(\delta z_j=\phi_j^\top\delta W_k\)，则 raw prediction 的一步关系是精确恒等式
\[
L_r(W_{k+1})-L_r(W_k)=e_r^\top\delta z_j+\tfrac12\|\delta z_j\|^2.
\]
所以单样本 raw loss 下降的充要条件为 \(e_r^\top\delta z_j<-\frac12\|\delta z_j\|^2\)。这不是原 tracking 更新自动满足的条件：原更新使用当前 \((\phi_k,\beta_k,s_{\rm eff,k})\)，延迟 loss 使用旧 \((\phi_j,d_{j:k})\)。

对同一固定旧样本的 applied 预测，使用它自己的历史 \(\beta_j\)：
\[
e_a=\beta_j\operatorname{clip}(z_j(W_k))-d_{j:k},\quad
\delta u_j=\beta_j[\operatorname{clip}(z_j(W_k)+\delta z_j)-\operatorname{clip}(z_j(W_k))],
\]
\[
L_a(W_{k+1})-L_a(W_k)=e_a^\top\delta u_j+\tfrac12\|\delta u_j\|^2.
\]
逐轴可写 \(\delta u_j=\beta_j\,\mathrm{diag}(\rho)\delta z_j\)，其中 clip 的 secant slope \(\rho_a\in[0,1]\)。applied loss 下降仍需其自身负内积条件；饱和轴 \(\rho_a=0\) 时旧输出对权重变化完全不敏感。若把 \(V+\mu L_r\) 作为分析/监测组合量加入 raw prediction 项（\(\mu\ge0\)，单位为 s²），上述参数/BS 一步界只需再加
\[
\mu\left(e_r^\top\phi_j^\top(-U_k+R_k)
+\tfrac12\|\phi_j^\top(-U_k+R_k)\|^2\right).
\]
没有可证明的符号抵消时，组合项不自动下降；对 \(L_a\) 用同样式替换为 \(e_a^\top\delta u_j+\tfrac12\|\delta u_j\|^2\)。

## 常数理想权重：raw 与 applied 的区别

对单个固定样本，若 raw 目标确由常数 \(W^\star\) 精确表示，即 \(d=\phi^\top W^\star\)，则 \(e=\phi^\top(W-W^\star)\)，raw loss 的梯度为 \(G_r=\phi e^\top\)。单独做梯度步 \(W^+=\Pi_{\mathcal B_{60}}(W-\alpha G_r)\) 时，在 \(W^\star\) 位于盒内的条件下，
\[
\tfrac12\|W^+-W^\star\|_F^2-\tfrac12\|W-W^\star\|_F^2
\le-\alpha(1-\tfrac12\alpha\|\phi\|^2)\|e\|^2-\tfrac12\|R\|_F^2 .
\]
因此 \(0<\alpha\|\phi\|^2<2\) 时该固定 raw 样本使参数误差不增，非零可见误差时严格下降；C1 记录 \(\|\phi\|=1\)。它只控制 \(\phi\) 可见方向，一个样本不能辨识全部 33 行参数；多样本全参数收敛还需足够激励和不漂移标签。此结论是单独 raw 梯度步，不是冻结 Head 实际更新的性质。

applied loss \(L_a=\frac12\|\beta\operatorname{clip}(\phi^\top W)-d\|^2\) 在非 kink 处的梯度为 \(G_a=\beta\phi(m\odot e_a)^\top\)，其中 \(m_a=1\) 仅当当前 raw 轴未饱和。若目标也满足 applied-realizable 条件 \(d=\beta\operatorname{clip}(\phi^\top W^\star)\)，则
\[
\langle W-W^\star,G_a\rangle_F
=\beta^2\sum_a m_a(z_a-z_a^\star)
[\operatorname{clip}(z_a)-\operatorname{clip}(z_a^\star)]\ge0,
\]
因为 clip 单调、\(\beta\ge0\)。故连续的 \(-G_a\) 方向不增到 \(W^\star\) 的平方距离；稳定活动集上的有限梯度步还需步长条件 \(0<\alpha\beta^2\|\phi\|^2<2\)。这不保证严格参数辨识：若轴饱和则 \(m_a=0\)，可以剩非零应用误差而无梯度；\(\beta=0\) 时 applied 输出对 \(W\) 完全无信息。target 若不满足同一 \(\beta\)-clip 映射，参数内积甚至可反号。

两个纯代数例子说明边界（非本数据参数选择或闭环证据）。(1) **满足 applied-realizable 仍有饱和盲区：**单轴 \(\phi=1,d_{\max}=3,\beta=0.5,W^\star=0.8,d=0.4,W=4\)。理想值给出 \(d=\beta\operatorname{clip}(W^\star)\)，但当前输出为 1.5、误差为 1.1，因 \(W\) 饱和而 \(m=0\)，所以 \(G_a=0\)，参数误差 3.2 不被该单样本梯度改变。(2) **物理 raw target 未乘 beta：**\(\phi=1,W^\star=d=1,\beta=0.5,d_{\max}=3,W=1.5\)。当前 applied 输出 0.75、误差 \(-0.25\)，\(G_a=-0.125\)，于是 \((W-W^\star)G_a=-0.0625<0\)；沿 \(-G_a\) 会先远离 raw 物理 \(W^\star\)，尽管可能在降低 applied loss。故 applied \(\beta\)-clip 不能无条件继承 raw prediction 的参数能量耗散性质。

## 时变标签与结论边界

延迟标签按此前核验的离线定义 \(d_{j:k}=(v_k-v_j)/(10dt)-10^{-1}\sum_{\ell=j}^{k-1}a_{f,\ell}\)。它随闭环速度、滤波姿态和 PCF 状态变化；PCF 的 \(\eta\) 又是控制器内部状态。不能因此假定样本独立、存在常数 \(W^\star\)，或把该标签自动等同于 BS 方程的外扰 \(\xi\)。若换到下一对 \((\phi_{j'},d_{j':k'})\)，误差还出现 feature/target drift：
\[
e'_{r}-e_r=\phi_{j'}^\top\delta W+(\phi_{j'}-\phi_j)^\top W_k-(d_{j':k'}-d_{j:k}),
\]
applied 情形还多出 \(\beta\) ramp 与 clip 变化。因此逐个固定样本的 raw 梯度下降不推出整个时变样本序列下降。

结论限于：冻结 Head 的参数步、projection 下的距离界，以及 fixed-sample raw/applied prediction 的条件性性质。实际 tracking 项、leak、beta ramp、clip、PCF \(s_{\rm eff}\)、投影和 RK4/采样余项均会留下未定符号项。现有离线结果只核对历史输出、更新方程和目标构造；它没有验证常数理想 \(W^\star\)、持续激励、目标外生性或闭环 Lyapunov 条件，也没有进行权重更新、仿真或性能评估。

## 冻结源码绝对路径与行号

- run_dl1018_closed_loop.m：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\sources\local_runtime\run_dl1018_closed_loop.m；1947–1968 行的当前 FEATURE Head 调用与 PCF 有效表面，2027–2030 行的 held force，2152–2158 行的滤波实现量；SHA-256 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b。
- position_only_search_head_step.m：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\sources\local_runtime\position_only_search_head_step.m；1–19 行（FEATURE 输出、Euler tracking/leak 更新、±60 projection）；SHA-256 3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc。
- position_bs_step.m：C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\matlab\core\position_bs_step.m；17–27、52–59 行；SHA-256 ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681。
- 配置身份 C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\configs\effective_config.mat；SHA-256 cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f；此 MAT 无代码行号。
参考的延迟目标代码/结果身份（只作为定义来源，不重读 raw）：reports/delayed_innovation_design_audit_20261023/construction/delayed_innovation_audit.py SHA-256 bb6a90e4489825709995900bdb9fe69896c0a902b1239bb515859d131b2259ad；DELAYED_INNOVATION_SUMMARY.json SHA-256 4d542a1d80d2633e9bbcbd4f6e86dbc4786989a80323cf5785a171ff36698f4f。