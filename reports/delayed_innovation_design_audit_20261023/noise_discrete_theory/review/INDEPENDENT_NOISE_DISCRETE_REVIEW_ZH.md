# 独立审核：延迟创新标签的噪声、离散时间与理论边界

状态：**候选推导通过静态独立复核，控制器仍不放行。** 本报告只审理论和时间口径；不读取原始 MAT、不运行脚本或数值任务、不改变任何实现。

## 审核对象与结论

审阅的冻结候选为 [THEORY_CANDIDATE_ZH.md](../construction/THEORY_CANDIDATE_ZH.md)，SHA-256 484f28cb5bc88910ff147b1ba6e9280edf257e9255fec0aa0a8cea5d898d992f。冻结源身份沿用 C1 source lock v2：runtime 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b、Head step 3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc、PCF/helper 等身份见该候选首页和 source lock。没有发现本版本的一步代数错误；噪声和连续/离散边界也可以按下文作条件化表述。

本结论支持“固定历史样本的梯度和参数一步界推导正确”，不支持“更新会改善闭环”或“已得到完整稳定性证明”。主审的独立数值核对及原始记录完整性结论见 [PARENT_DECISION_ZH.md](../../PARENT_DECISION_ZH.md)；这里不重复读 raw，也不把主审数值结果冒充成本轮独立复算。

## 事件时序与物理量的精确定义

头部输出先于同一事件的权重更新；事件输出随后在 1 ms Plant 步之间保持，Head 更新间隔为 10 ms。对当前事件 k，上一事件 j=k−10，T=10dt=0.01 s，合法历史标签是
\[
\hat d_{j:k}=\frac{v_k-v_j}{T}-\frac1{10}\sum_{\ell=j}^{k-1}a_{f,\ell}.
\]
固定日志的首个合法配对是原始 Plant 索引 j=320,k=330。它是上一整个 10 ms 区间的残差近似，不是当前事件的瞬时真实扰动。该目标在 k 才完整可得；若新增更新，它只能在当前输出已算出后用于更新下一事件的权重，不能回写当前输出。

在冻结 runtime 中，a_f[ℓ] 是每个 1 ms 步计算并在该 Plant 步内保持的内部量。因此区间均值对 runtime 自己定义的 ZOH a_f 是精确积分，不应再给它附加一个没有依据的积分误差。rk4_vehicle_step 的一步速度增量满足
\[
\frac{v_{\ell+1}-v_\ell}{dt}
=\frac{a_1+2a_2+2a_3+a_4}{6},
\]
这里 a_i 是 RK4 的四个加速度阶段。故端点速度差给出整个区间的离散 RK4 加权平均；它不等于步起点 a_1，也不能称为当前瞬时加速度。若将其与连续 Plant 真值或 a_1 比较，才需要另列积分器误差/阶段差异，并给出光滑性或导数界。源码本身没有提供这些误差界。

该目标也与 Head 的应用方向一致：PCF 坐标下 d=Y+r_f=a_actual−a_f，其中 Y=a_actual−a_req、r_f=a_req−a_f。它不是单独的风力，也不是 BS 原坐标下未经变换的扰动。候选正确区分了 PCF 的连续理想恒等式与实际采样闭环。

## 标签噪声和可证的条件界

先把 velocity/state 日志误差与物理积分差异分开。设观测速度
\(\tilde v_n=v_n+b_n+\nu_n\)，重建的滤波参考为
\(\tilde a_{f,n}=a_{f,n}+\xi_n\)。相对于同一离散定义，标签误差恰为
\[
\epsilon_{j:k}
=\frac{b_k-b_j+\nu_k-\nu_j}{T}
-\frac1{10}\sum_{\ell=j}^{k-1}\xi_\ell .
\]
常值速度偏差 b 在端点差中消掉；时变偏差按 1/T 放大。若 \(\|\nu_n\|\le\epsilon_v\)、\(\|b_k-b_j\|\le B_b(T)\)、且所有 \(\|\xi_\ell\|\le\epsilon_f\)，则
\[
\|\epsilon_{j:k}\|\le\frac{B_b(T)+2\epsilon_v}{T}+\epsilon_f.
\]
这是条件性确定性界；当前没有真实部署传感器噪声、偏差或滤波参考重建误差界，不能给它代入数值。

令 \(P_n=\operatorname{Cov}(\nu_n)\)、\(C_{kj}=\operatorname{Cov}(\nu_k,\nu_j)\)，velocity 端点项的协方差为
\[
\frac{P_k+P_j-C_{kj}-C_{jk}}{T^2}.
\]
若另有 \(\xi\) 随机误差，总协方差还包括 \(10^{-2}\sum_{p,q}\operatorname{Cov}(\xi_p,\xi_q)\) 及 velocity 与 \(\xi\) 的交叉协方差。只有在平稳标量、端点方差相同为 \(\sigma_v^2\) 时，速度项才化为 \(2\sigma_v^2[1-\rho(10)]/T^2\)；独立端点才有 \(\sqrt2\sigma_v/T\) 的标准差。常值共同误差会抵消，相关误差不能直接套 \(\sqrt2\) 公式。相邻合法事件分别使用区间 [j,k) 和 [k,k+10)，不共享 a_f 样本；但两条速度差分共用端点 v_k，所以标签误差仍相关（即便速度端点噪声独立也会因共用项产生协方差），不能按独立样本处理。

这些式子只约束标签。部署状态估计误差还会经 X14/encoder 改变 \(\phi\)，当前没有对应的 encoder 扰动界。对 raw 梯度 \(G=\phi e^\top\)，有限扰动的范数界满足
\[
\|\delta G\|_F\le \|\delta\phi\|\,\|e\|
+\|\phi\|\,\|\delta e\|+\|\delta\phi\|\,\|\delta e\|,\qquad
\delta e=W^\top\delta\phi-\epsilon_{j:k}.
\]
因此标签协方差不能替代整个在线更新的噪声界。applied 梯度还含 clip 活跃集；穿越饱和边界时 mask 会跳变，需另有状态/特征误差和边界余量条件。

## 区间标签与起点特征的错配界

历史目标是区间均值，而预测器使用起点特征 \(\phi_j\)。这不是积分回归器。若额外假设存在固定 \(W^\star\)，连续特征 \(\phi(t)\) 满足 Lipschitz 常数 \(L_\phi\)，并且
\(d(t)=W^{\star\top}\phi(t)+r(t)\)，则
\[
\|\bar d_{j:k}-W^{\star\top}\phi_j\|
\le \|W^\star\|_F L_\phi T/2
+\frac1T\int_{t_j}^{t_k}\|r(t)\|\,dt.
\]
该界依赖固定表示、连续特征轨迹、其 Lipschitz 界和表示残差界；现有离线记录没有证明这些假设或给它们设界。实际 \(\phi\) 是 100 Hz 事件特征并被用于区间保持输出，不能仅凭输出保持就推出物理残差在区间内由常数 \(W^{\star\top}\phi_j\) 表示。

固定旧样本的 applied 映射是
\(g_\beta(W,\phi)=\beta\,\operatorname{clip}(\phi^\top W,\pm3)\)。
它对 raw 输出是 \(\beta\)-Lipschitz；对权重在固定 \(\phi\) 下的变化界为
\(\|g_\beta(W',\phi)-g_\beta(W,\phi)\|\le\beta\|\phi\|\|W'-W\|_F\)。
β 改变另加至多 \(3\sqrt3|\Delta\beta|\) 的向量输出差。物理标签 d 没有乘 β：若物理目标为 \(\phi^\top W^\star_{\rm phys}\)，且无饱和，applied loss 的比较器会变成 \(W^\star_{\rm phys}/\beta\)，随 ramp 漂移；它还必须留在 ±60 权重盒内。β 接近零时比较器和噪声敏感度都可发散。已审的 ready 记录最小 β 约 0.1778 只能描述该数据集，不能代替部署下界。若某轴 \(|d_a|>3\beta\)，该轴至少有 \((|d_a|-3\beta)_+\) 的不可消除应用残差；若当前 raw 已饱和，局部预测梯度又可能为零。

物理目标未乘 β 的标量反例只否定“applied 梯度相对同一个常数物理 \(W^\star\) 无条件耗散”。它不证明 applied loss 有害，也不证明 raw loss 必优。可改用时变比较器 \(W^\star_{\rm phys}/\beta\)，但必须明列比较器漂移、投影盒可行性和近零 β 条件。饱和例只证明单样本梯度盲区，不是历史数据里的实测原因。上述限定与 [PARENT_FINDINGS_ZH.md](../PARENT_FINDINGS_ZH.md) 的反例一致。

## 对冻结一步推导的复核

1. 投影参数距离界正确，前提是 \(W^\star\in\mathcal B_{60}\)。离散平方项 \(\|U\|^2\)、投影残差、leak 对非零比较器的项均保留，不能仅靠投影宣称耗散。
2. 当前 Head 的真实更新只有 \(U_{\rm orig}=h(\gamma\beta\phi s_{\rm eff}^{\top}+\lambda W)\)。最终候选另写的
\[
U_{\rm joint}=U_{\rm orig}+\alpha_pG_r
\]
明确是未执行的假设更新。其对应能量界必须含
\[
\frac{\alpha_p}{\gamma}\langle\tilde W,G_r\rangle
+\frac{\|U_{\rm orig}\|^2+
2\alpha_p\langle U_{\rm orig},G_r\rangle+
\alpha_p^2\|G_r\|^2-\|R^+\|^2}{2\gamma}.
\]
候选已补全这些项，并正确注明交叉项没有耗散符号保证。若 \(V+\mu L_r\) 只是监测组合量，它不等于执行 \(U_{\rm joint}\)；\(\mu\) 的量纲为 s²。
3. 固定样本 raw/applied loss 的精确增量、raw 梯度和 applied clip mask 方向导数正确。raw 梯度的单样本下降条件不覆盖 tracking、leak、projection 的复合更新。applied loss 仅在同一 β-clip 可实现的目标、活跃集条件和适当步长下有条件参数方向结论。
4. \(V_B\) 与 PCF 连续坐标恒等式正确地作为理想关系陈述。候选把 d 放在 \(s_c=s-\eta\) 方程的目标项，且保留 \(c_e e^\top\eta\)。它没有把该连续恒等式冒充实际一步定理。

### 主审补充的 raw 标签噪声一步式

主审另给的噪声展开经独立代数复核正确。令 \(\theta=W-W^\star\)、\(q=\phi^\top\theta\)、\(\|\phi\|=1\)，观测标签为 \(\phi^\top W^\star+\epsilon\)，所以 raw 残差 \(e=q-\epsilon\)。对单独的符号梯度步 \(W^+=\Pi_{\mathcal B}(W-a\phi e^\top)\)，且 \(W^\star\in\mathcal B\)，投影性质给出不等式
\[
\|\theta^+\|_F^2-\|\theta\|_F^2
\le -a(2-a)\|q\|^2+2a(1-a)q^\top\epsilon+a^2\|\epsilon\|^2-\|R\|_F^2 .
\]
这是从未投影平方展开后使用投影上界得到的 \(\le\)，不是一般等式；R 是投影修正。若仅有确定性 \(\|\epsilon\|\le\bar\epsilon\)，则交叉项最多按 \(2|a(1-a)|\|q\|\bar\epsilon\) 控制，仍留下噪声地板。若要在期望中删掉交叉项，需要 \(\epsilon\) 对当前 q 条件零均值等额外假设，本项目没有建立这一统计契约。这是纯 raw 单样本符号步，未选择 a、未执行学习，不能替代原 tracking+leak+projection 复合更新；后者仍需加入 \(\|U_{\rm orig}\|^2\) 及其交叉项。

主审 [PARENT_ALGEBRA_CHECK.json](../PARENT_ALGEBRA_CHECK.json) 的 beta 反例仅否定相对固定物理 \(W^\star\) 的无条件 applied 参数耗散，不证明 applied loss 有害、raw loss 更优，或历史轨迹的性能因果。

## 完整闭环界仍缺什么

把 tracking、参数和创新损失放在一起，仍留下 \(s^\top(u-d)\)、PCF 坐标中的 \(c_e e^\top\eta\)、ramp/clip 失配、\(s_{\rm eff}-s\)、参数 leak/投影/离散平方与更新交叉项、固定历史特征和时变标签误差，以及实际 RK4/采样保持余项 \(\rho_k\)。现有材料既未证明这些项为负，也未给出足以吸收它们的统一上界。W 被 box 限住并不控制 e、v、η、风/姿态/执行器误差或闭环状态；局部梯度下降也不是控制轨迹的因果梯度。

要声称完整闭环界，至少需要匹配的物理目标/比较器及其漂移和盒约束、encoder/测量/目标误差界、可验证的区间离散误差、PCF 与执行器/姿态/Plant 的闭合有界性条件、并能支配上述交叉项的具体更新/步长条件；需要的持续激励或可辨识性也不能由单样本界代替。现有候选没有这些条件，也没有选择新 \(\alpha_p\)。因此不放行新控制器、训练或闭环试验。

## 方法对照、过程记录

文献边界沿用已核的 [PARENT_DECISION_ZH.md](../../PARENT_DECISION_ZH.md)：Neural-Fly 的 composite tracking/prediction/regularization 及其条件性分析、command-filtered neural composite learning 的先例，都排除“command filter + prediction gradient 本身新颖”的说法。Integral composite learning 的回归积分项也不能直接等同于这里的 10 ms 速度端点差、区间 \(a_f\) 均值和起点 \(\phi_j\)。论文状态保持 **NOT_QUALIFIED**；本审查没有增加新文献或代码主张。

开发阶段的五次离线失败均保留于 [DEVELOPMENT_FAILURES.json](../../construction/DEVELOPMENT_FAILURES.json)：错误的 source SHA 常量；两次把非事件 NaN 当作错误的 finite guard；NumPy 梯度广播维度错误；烟测路径年份错误。它们都在最终冻结数值复核前修正，记录称没有输出产物或改变 raw；应保留在证据账本中，不把它们算成新实验或新的科学反例。

## 范围和最终审阅状态

本报告只做静态数学复核，未打开 raw/MAT、未运行作者脚本、未做新的数据计算或拟合。复核的候选文件 SHA 在首节给出；仅新增本文件。独立结论为 **THEORY_CANDIDATE_PASS_WITH_CONDITIONS; CLOSED_LOOP_NOT_PROVEN; CONTROLLER_NOT_RELEASED**。
