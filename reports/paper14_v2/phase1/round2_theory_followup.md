# DL1018 Round2 离散理论跟进审计

日期：2026-10-22。范围按 Round2 前提：FEATURE Head 的 W 更新开启，PCF eta coordination 关闭。结论：**可以严格证明 Head 输出限幅、投影后的权重盒约束，以及权重态相对于裁剪误差面的条件 ISS 递推；可以给出位置外环在加速度残差有界时的条件离散 ISS/UUB 界。不能据此判定当前完整部署链通过稳定/误差界门槛。** 后一命题中的实际加速度残差、RK4 局部缺陷和维持假设域的不变性都没有经源码或允许证据数值化。权重投影有界不是闭环稳定；未验证 PE 不作事实使用。

## 审查对象与 Round2 分支

只读对象为锁定 runtime 的 runner、FEATURE Head、DSSM forward/options，项目中的 PCF、位置外环、姿态指令滤波、力到姿态映射、姿态反步、分配器、RK4 和 Plant/风载结构，以及既有两份理论审计。没有运行仿真、训练或航次；没有读取 TEST、MAT、checkpoint、cache、raw；没有改运行源码。有效配置文件不在本轮读取范围内。

锁定 runner 的 PCF 状态在第716行初始化为零；只有 pcfCoordinationEnabled 为真才会调用 eta 更新（第2152–2159行）。在 Stage1 + FEATURE search + W 更新分支中，PCF 开时使用 clip(surface−eta)，PCF 关时直接使用 clip(surface)（第1952–1964行）。因而 Round2 该分支满足

\[
\eta_n\equiv 0,\qquad
s_{c,n}=\operatorname{clip}(s_n,\pm[7,8,10]),\qquad
s_n=\dot e_n+k_1e_n .
\]

这不是“PCF 滤波仍在跟踪而误差为零”：PCF eta realization 不执行，且未计算其重构残差；但 Euler 目标的 command_filter_step 仍逐个 1 ms 控制步运行。runner 对启用 AttitudeFusion 的分支另有断言：若位置 Head active，则要求原 PCF coordination 开启（runner 第62–63行）。因此“W 开、PCF 关”仅适用于不触发该 fusion contract 的配置；本轮未读取 effective-config MAT，不能判断该假设是否对应某一具体有效配置。

Head 在有效位置事件处先用当前 W 输出，再作更新；runner 将 applied acceleration 乘质量为 force，并保持到下一位置事件（第2027–2029行）。既有审计识别该计划事件率为100 Hz，Plant步长为1 ms；事件更新的实际间隔由 rbfFullDt 提供。DSSM forward 的最后一层构造 \(\phi=[h;1]/\sqrt{1+\|h\|_2^2}\)，因此只要前向计算有限，\(\|\phi\|_2=1\)（锁定 forward 第136行）。

Head 的实际 FEATURE 方程为

\[
u_n=\beta_n\operatorname{clip}(W_n^\top\phi_n,\pm d_{\max}),\qquad
W_{n+1}=\Pi_C\!\left(W_n+h_nG_n\right),
\]
\[
G_n=-\gamma\beta_n\phi_ns_{c,n}^{\top}-\lambda W_n,\qquad
C=[-60,60]^{33\times3},\quad \gamma=12,\quad \lambda=0.002 .
\]

这里 \(h_n=\texttt{rbfFullDt}\)，计划事件约为0.01 s；Round2 search contract 要求 scheduler scale 与 beta scale 为1。已有审计所记录的三轴 Head dmax 为3 m/s²，\(0\le\beta\le1\)，并按 \(\beta=\operatorname{clip}(t/1.8,0,1)\) 渐入。Head 源码对应位置为 locked position_only_search_head_step.m 第14–20行。

## 命题一：可证明的 Head 参数态 ISS 与限幅

设每次有效更新输入有限，\(\|\phi_n\|_2=1\)，且 \(0<h_n\lambda\le1\)。PCF 关闭分支逐轴裁剪误差面，所以

\[
\|\beta_ns_{c,n}\|_2\le S:=\sqrt{7^2+8^2+10^2}
=\sqrt{213}=14.5945195 .
\]

由于 \(0\in C\)，盒投影相对于原点非扩张。令 \(q_n=1-\lambda h_n\)，便有

\[
\begin{aligned}
\|W_{n+1}\|_F
&=\|\Pi_C((1-\lambda h_n)W_n
-h_n\gamma\phi_n(\beta_ns_{c,n})^\top)\|_F\\
&\le q_n\|W_n\|_F+h_n\gamma S .
\end{aligned}
\]

迭代并使用 \(\lambda h_n=1-q_n\) 得到

\[
\|W_n\|_F\le
\Bigl(\prod_{i=0}^{n-1}q_i\Bigr)\|W_0\|_F+
\frac{\gamma S}{\lambda}
\left(1-\prod_{i=0}^{n-1}q_i\right).
\]

这是 W 参数态对有界输入 \(\beta s_c\) 的离散 ISS 形式，常数 \(\gamma S/\lambda=87{,}567.12\)。在 \(h=0.01\) s 时 \(q=0.99998\)。该 ISS 半径极松；更紧且直接由投影给出的结论是：每次有效更新后 \(W_{n+1}\in C\)，所以 \(\|W_{n+1}\|_F\le60\sqrt{99}=596.9925\)。首个有效更新之前的 W0 未读取，故不能声称整段事件序列一开始就在盒内。

对盒内 W，原始输出各轴满足 \(|(W^\top\phi)_j|\le60\sqrt{33}=344.6738\)；应用输出仍严格满足 \(\|u_n\|_\infty\le3\) m/s²、\(\|u_n\|_2\le\sqrt{27}=5.1962\) m/s²。以未裁剪 raw 作参照时，更新后盒内的 Head clip 残差逐轴最多为 \(344.6738-3=341.6738\) m/s²。渐入相对于“beta=1 的已裁剪输出”的差最多为 \(3(1-\beta_n)\) m/s²/轴。事件间 ZOH 的实际输出保持不变；若比较对象是另一条逐时刻变化、同样处于 ±3 的命令，只有平凡的6 m/s²/轴幅度差界。若要得到随事件间隔缩小的 \(L_u h\) 采样误差，还需要 feature/state/reference 的变化率或 Lipschitz 界，源码没有给出。

更新方向的统一粗界为

\[
\|G_n\|_F\le\gamma S+\lambda\,60\sqrt{99}
=176.3283 .
\]

在 \(h=0.01\) s，单次 Euler 增量 \(h\|G_n\|_F\le1.7633\)，平方差中的离散正项 \(h^2\|G_n\|_F^2\le3.1092\)。对任何 \(W^\star\in C\)，投影非扩张性只给出

\[
\|W_{n+1}-W^\star\|_F^2
\le\|W_n-W^\star\|_F^2+
2h_n\langle W_n-W^\star,G_n\rangle+
h_n^2\|G_n\|_F^2.
\]

源代码没有提供使内积项非正、或能吸收 \(h^2\) 项的匹配模型关系。泄漏项 \(-\lambda W_n\) 使 W 朝原点收缩，但目标若为非零 \(W^\star\)，其误差交叉项不是自动负值；Surface-driven 项的符号也依赖误差/未知残差关系。因此该 Head 定理不推出误差衰减、W 收敛或闭环稳定。若论文要声称参数收敛还需 PE 等条件；本审计没有验证 PE，也不作此主张。

## 命题二：位置外环的条件离散 ISS/UUB

该命题精确限定于位置双积分 sampled-ZOH 误差模型，不等价于本项目六自由度 RK4 闭环定理。按项目 position_bs_step 第24–27行，定义

\[
e=p_{\rm ref}-p,\quad s=\dot e+k_1e,\quad
a_{N,k}=\ddot p_{{\rm ref},k}+k_1\dot e_k+e_k+k_2s_k,
\]

本配置审计值 \(k_1=1\ {\rm s}^{-1}\)、位置项系数 \(1\ {\rm s}^{-2}\)、\(k_2=4\ {\rm s}^{-1}\)。明确取

\[
\delta_k:=a_{{\rm plant},k}-a_{N,k}
\quad(\text{真实惯性系加速度减去外环名义加速度}).
\]

position_bs_step 把 Head force 从名义 force 中扣除。因此在理想力/加速度跟踪时 \(a_{\rm plant}=a_N-u_n\)，即 \(\delta_k=-u_n\)；若额外 Plant/执行误差为 \(d_k:=a_{\rm plant}-(a_N-u_n)\)，则 \(\delta_k=-u_n+d_k\)。这个定义直接给出后续两个 \(B_h\) 负号，不把 Head 补偿符号藏进未定义扰动。

附加假设为：每个 \(h=0.001\) s 区间位置动力学是理想双积分器；采样时算出的名义加速度在区间内 ZOH；参考加速度在区间内 ZOH；\(\delta_k\) 在区间内常值；暂不含 RK4 与姿态/执行器映射缺陷。由 \(s_k=\dot e_k+e_k\) 得 \(\dot e_k=s_k-e_k\)，而
\[
\ddot e=-\dot e-e-4s-\delta_k=-5s_k-\delta_k .
\]
对该常值加速度精确积分：

\[
e_{k+1}=(1-h)e_k+(h-2.5h^2)s_k-\tfrac12h^2\delta_k,
\]
\[
s_{k+1}=-he_k+(1-4h-2.5h^2)s_k-(h+\tfrac12h^2)\delta_k.
\]

因此在固定 SI 数值标度 \(z=[e/(1{\rm m});s/(1{\rm m\,s^{-1}})]\)、
\(\delta\) 以 m/s² 数值表示时，

\[
z_{k+1}=A_hz_k+B_h\delta_k,\quad
A_h=\begin{bmatrix}.999&.0009975\\-.001&.9959975\end{bmatrix},\quad
B_h=\begin{bmatrix}-5.0{\times}10^{-7}\\-0.0010005\end{bmatrix}.
\]

矩阵无穷范数 \(\|A_h\|_\infty=q=0.9999975<1\)，\(\|B_h\|_\infty=b=0.0010005\)。故对 \(|\delta_k|\le D\)，

\[
\|z_k\|_\infty\le q^k\|z_0\|_\infty+
\frac{bD}{1-q}(1-q^k)
=q^k\|z_0\|_\infty+400.2D(1-q^k).
\]

此式确为该理想采样模型的 ISS/UUB 界。由于 Head 命令逐轴有界，若完整实现的其余加速度误差和参考插值误差另有统一界 \(D_0+R_{\rm ref}\)，则可条件代入 \(D=3+D_0+R_{\rm ref}\)。这个半径很保守；更关键是 \(D_0,R_{\rm ref}\) 目前均不是已证明的部署常数。

若加速度残差在1 ms内变化，以下把 \(\delta_k(t)\) 定义为总残差
\[
\delta_k(t):=a_{\rm plant}(t)-a_{N,k}-
\bigl(\ddot p_{\rm ref}(t)-\ddot p_{{\rm ref},k}\bigr).
\]
它在参考加速度 ZOH 时退化为前述 \(\delta\)；若令
\(d_k(t):=a_{\rm plant}(t)-(a_{N,k}-u_j)\)，则
\(\delta_k(t)=-u_j+d_k(t)-(\ddot p_{\rm ref}(t)-\ddot p_{{\rm ref},k})\)。
取 \(\bar\delta_k=h^{-1}\int_0^h\delta_k(t_k+\tau)d\tau\) 后，同一 \(A_h,B_h\) 递推另有位置积分残差
\[
\epsilon_{\rm var,k}=
\begin{bmatrix}
-\int_0^h(h-\tau)\delta_k(t_k+\tau)d\tau+\tfrac12h^2\bar\delta_k\\
-k_1\int_0^h(h-\tau)\delta_k(t_k+\tau)d\tau+
\tfrac12k_1h^2\bar\delta_k
\end{bmatrix}.
\]
若 \(\|\delta_k(t)\|_\infty\le D\)，按上述 SI 标度 \(\|\epsilon_{\rm var,k}\|_\infty\le h^2D=10^{-6}D\)。对于代码中的 RK4 数值 Plant，还要再加其 RK4 状态更新相对该精确流的局部缺陷 \(\epsilon_{\rm RK,k}\)。仅在有前向不变紧集、分段光滑性和向量场导数统一界时，才能把该缺陷界定为数值 \(E_{\rm RK}\)；当前源码和允许审计未给出此域或该常数。若额外假设 \(\|\epsilon_{\rm RK,k}\|_\infty\le E_{\rm RK}\)，上述条件界变成
\[
\|z_k\|_\infty\le q^k\|z_0\|_\infty+
\frac{bD+h^2D+E_{\rm RK}}{1-q}(1-q^k).
\]
这仍只是“给定 \(D,E_{\rm RK}\)”的条件结果。因 \(1/(1-q)=400{,}000\)，未量化的小局部缺陷也会显著放大该粗界。若把非 head 残差进一步假设为 \(D_0+L\|z\|_\infty\)，且忽略 RK4 缺陷，则简化模型还需 \(q+bL<1\)；即 \(L<0.00249875\)（固定上述数值标度）。源码没有证明这个小增益条件。

## 与当前 PCF / ZOH / 1 kHz Plant 的断点

Round2 的 PCF-off 分支让 eta 恒为零，因此不存在可归入 Head 更新的 \(s-\eta\) 修正；被裁剪的只是原始 surface。PCF helper 的 \(r_F=a_{\rm req}-a_F\) 在这个分支并不计算，不能声称其输入满足某个有限 R。若论文讨论命令滤波作用，必须单独处理 runner 仍调用的 Euler command_filter：它以半隐式 Euler 更新角度/角速度，角加速度按配置裁剪；其状态/目标角跟踪误差和对应惯性系平动加速度误差没有统一界。

真实位置加速度为 Plant 状态相关的推力旋转项与风力项；姿态反步产生力矩，分配器先裁切广义请求、解平方转速并裁切电机，实际 wrench 由 Plant 分配矩阵生成。倾角映射、姿态滤波滞后、反步姿态误差、控制/Plant 分配矩阵差、推力/力矩饱和、风/形态变化都进入 \(d_k\)。电机输出有限不等于实际加速度与可能随位置误差增大的 \(a_N-u\) 之间误差有统一有限界；这正是条件命题中 \(D_0\) 不能由执行器限幅直接推出的原因。

Plant 每1 ms调用经典 RK4；四个子步采用同一步首控制 wrench，风载/力矩也由 runner 步首计算后保持。实际姿态和转动状态影响后续推力方向，Plant 的惯量、陀螺和形态项为状态相关。有限步 RK4 代码本身不是 Lyapunov 不等式，也不自动给连续模型截断误差常数。既有全链审计给出的条件有限步增长包络同样不代表误差衰减或 ISS，本轮不将它改称稳定证明。

因此要把命题二提升为计划可接受的部署结论，至少需要以下闭合条件之一：

- 给出完整 sampled controller + allocator + RK4 Plant + Head 的前向不变集，数值列明位置/速度、姿态/角速率、command-filter 状态、形态、风、质量/惯量、参考导数和执行器范围；并在该域证明 \(\delta\) 及 \(\epsilon_{\rm RK}\) 的统一界，再把条件递推的半径算成有意义的数值。
- 或直接对包含 W、滤波器、姿态和 Plant 的离散复合映射构造 Lyapunov/ISS 证明，显式吸收 Head projected-Euler 的交叉项与 \(h^2\|G\|^2\)，PCF-off 的表面裁剪、Head 输出裁剪、渐入和100 Hz ZOH、1 kHz RK4 缺陷、姿态及执行器饱和残差。
- 若要声称 Head 更新逼近不确定动力学，需要提供匹配分解（例如固定目标 \(W^\star\)、FEATURE 逼近残差上界及裁剪/ZOH 余项）并证明离散负漂移。若进一步声称参数收敛，需另行验证 PE；本轮没有该证据。

现有证据没有上述不变集、全链残差常数或联合 Lyapunov 关系。可诚实报告的最强结论是：Head 输出逐轴不超过3 m/s²并在100 Hz事件间保持；每次有效更新后 W 投影入盒，且对裁剪 surface 的 W 态有上述条件 ISS/有界结果；在假定位置双积分 sampled-ZOH 以及给定残差和 RK4 缺陷界时，位置误差满足命题二。**不能结论为当前实际部署已稳定、误差具有已审计数值界、Head 已收敛或适配改善了稳定性。**

## 源码与审计输入 SHA-256

锁定 runtime 根目录：
C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1\sources\local_runtime

| 审查文件 | SHA-256 |
|---|---|
| 锁定 runtime run_dl1018_closed_loop.m | 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b |
| 锁定 runtime position_only_search_head_step.m | 3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc |
| 锁定 runtime position_stage1_model_forward_v2.m | dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676 |
| 锁定 runtime position_only_search_options.m | 4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf |
| 项目 matlab/models/position_filter_realization_pcf_step_v3_5.m | b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0 |
| 项目 matlab/core/position_bs_step.m | ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681 |
| 项目 matlab/core/command_filter_step.m | 15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b |
| 项目 matlab/core/baseline_force_to_attitude.m | ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039 |
| 项目 matlab/core/attitude_bs_step.m | cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc |
| 项目 matlab/core/allocate_control.m | 5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53 |
| 项目 matlab/core/rk4_vehicle_step.m | 7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5 |
| 项目 matlab/core/vehicle_derivative.m | c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786 |
| 项目 matlab/core/morphology_aware_wind_load.m | 51459cd2c09f1181e85bbee8f89ddbd75bd2ba923f1aebacbdd1ecfe7b3ba5ac |
| 项目 matlab/core/arm_mass_properties.m | 8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5 |
| 项目 matlab/core/allocation_matrix.m | 5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d |
| 项目 matlab/core/rbf_event_scheduler_step.m | cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618 |
| 既有 phase1/discrete_theory_second_review.md | 2b8cbffe6503b6c00347d4865ceadc8239e4dee8c7c66d93f85ace01406783d4 |
| 既有 phase1/deployment_chain_finite_horizon_audit.md | 8fa79b7fec35422a0cb0a12c738ff57e9f6daa7221719736c2e08c9056abfa6b |

文件SHA针对本轮复核读取到的字节。既有审计指出部分共享 Plant 源没有逐项绑定到72场历史 run identity；当前 SHA 不补造历史逐字节归因。风载源码 SHA 已按准确32位十六进制串重算，无空格。

## 复核命令与限制

本轮只读复核命令（不触及 MAT/checkpoint/cache/raw/TEST）：

    Get-FileHash -Algorithm SHA256 -LiteralPath <上表源码与两份审计的逐项绝对路径>
    rg -n 'pcfCoordinationEnabled|stage1PcfEta=zeros|stage1SearchEnabled&&stage1PositionUpdateEnabled|stage1PositionHeldForce=P.mass|position_filter_realization_pcf_step_v3_5' <锁定 runner>
    rg -n 'raw=state|unprojected=state|stateNext=max|min|max|min\(raw' <锁定 Head>
    rg -n 'phi=\[h;1\]|aNominal =|commandedForce =|requestedAcceleration =|actualGeneralized =|nextState = state|acceleration = R' <锁定 forward 与项目模型源码>
    Get-Content -LiteralPath reports/paper14_v2/phase1/discrete_theory_second_review.md
    Get-Content -LiteralPath reports/paper14_v2/phase1/deployment_chain_finite_horizon_audit.md

本次仅新增本报告。推理工具没有本地接口用于检查或切换服务模型、xhigh推理量和服务速度；任务指定 GPT-6-Luna xhigh、正常速度且不用 Fast，本轮未调用 Fast 专用工具，服务端实际速度档无法从本地独立核验。