# DL1018 X14 的限定理论结果（非资格通过证明）

日期：2026-10-22。本文把现有实现可直接支持的局部结论收拢为论文可引用的限定结果，并列出不能跨越的推理边界。**这些结果不满足冻结计划的完整部署理论门，不构成闭环稳定性证明，也不把 R3 的性能筛查解释成理论贡献。** 所有仿真数据与独立 TEST48 均未用于下述推导。

## 1. 实际分支与符号

考虑 R3 `DSSM14_PCF_XY` 的位置 Head 更新分支。设位置事件索引为 `n`，Plant/PCF 步索引为 `k`。实际 32 事件 DSSM 前向产生
\[
\phi_n=\frac{[h_n;1]}{\sqrt{1+\|h_n\|_2^2}},\qquad \|\phi_n\|_2=1
\]
（前提是前向数值有限）。R3 用 `M=diag(1,1,0)`选择 PCF 协调量，
\[
s_{\mathrm{eff},n}=\operatorname{clip}(s_n-M\eta_n,\;\pm[7,8,10]).
\]
FEATURE Head 在事件开始先计算并应用
\[
u_n=\beta_n\operatorname{clip}(W_n^\top\phi_n,\;\pm[3,3,3])\quad (\mathrm{m/s^2}),
\]
随后以 \(h_n\simeq0.01\,\mathrm{s}\) 更新权重
\[
W_{n+1}=\Pi_C(W_n+h_nG_n),\quad
G_n=-12\beta_n\phi_ns_{\mathrm{eff},n}^{\top}-0.002W_n,
\quad C=[-60,60]^{33\times3}.
\]
应用的 \(u_n\) 在下一位置事件前保持；PCF 按 \(0.001\,\mathrm{s}\) 推进。SI 单位约定为：`s_n`、`eta_n` 与 `s_eff,n` 为 m/s，`W_n` 与 `u_n` 为 m/s^2，`gamma=12 s^-2`，泄漏率 `0.002 s^-1`，`G_n` 为 m/s^3；`beta_n` 与 `phi_n` 无量纲，`h_n` 以 s 计，因此 `h_n G_n` 与 `W_n` 同为 m/s^2。
以上限定来自实际 R3 runner/forward/Head 分支；它不把其他候选或另一个未启用 Head helper 的方程代入本结果。复核的实际隔离文件 SHA-256 为：R3 runner `86e7f7ec42492341e58daf30879f7aec9153924e80a76f6f029fce2a628c38d9`、DSSM forward `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`、FEATURE Head `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc`、PCF helper `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0`。runner 使用 R3 本地隔离副本；本附录的身份是该实际 R3 路径，不以 FULL72 上游 runner 身份替代。

## 2. 命题一：Head 的命令与投影界

假设事件前权重、`s_eff,n`、事件步长 `eventDt` 及 Head 更新中间运算均有限，DSSM 前向有限、\(0\le\beta_n\le1\)，且实现执行了上述盒投影。则：

1. 应用命令逐轴满足 \(\|u_n\|_\infty\le3\,\mathrm{m/s^2}\)，并在事件间保持；
2. 每次有效更新后 \(W_{n+1}\in C\)，故 \(\|W_{n+1}\|_F\le60\sqrt{99}=596.9925\)；
3. 由于 \(\|s_{\mathrm{eff},n}\|_2\le\sqrt{213}\)，投影后盒内状态满足
\[
\|G_n\|_F\le12\sqrt{213}+0.002(60\sqrt{99})<176.33.
\]
其中 `G_n` 单位为 m/s^3；
名义 \(h_n=0.01\,\mathrm{s}\) 时，未投影单步增量范数不超过约 `1.7633 m/s^2`。

对任意 \(W^\star\in C\)，盒投影非扩张给出
\[
\|W_{n+1}-W^\star\|_F^2\le
\|W_n-W^\star\|_F^2+2h_n\langle W_n-W^\star,G_n\rangle+h_n^2\|G_n\|_F^2.
\]
其中 \(h_n^2\|G_n\|_F^2\) 是正项；当前实现审计没有证明交叉项非正或足以吸收它。因此这里只得到输出限幅、更新后权重有界和单步更新量界，**不能**推出权重误差收敛、位置误差衰减或闭环稳定。首个有效投影前的 \(W_0\) 数值也未由本命题界定。

## 3. 命题二：PCF 状态的条件输入界

PCF helper 的实际重构残差 `r_F` 单位为 m/s^2，状态 `eta` 单位为 m/s，递推为
\[
\eta_{k+1}=a\eta_k+b r_{F,k},\qquad
 a=e^{-4(0.001)}=0.9960079893,\quad
 b=\frac{1-a}{4}=0.0009980027\,\mathrm{s}.
\]
若能证明全部步骤满足 `||r_F,k||_infty <= R`（`R` 的单位为 m/s^2），则
\[
\|\eta_k\|_\infty\le a^k\|\eta_0\|_\infty+\frac{R}{4}(1-a^k).
\]
特别地，\(\eta_0=0\) 时有 \(\|\eta_k\|_\infty\le R/4\)。该结论是带前提的稳定滤波器界；源码与审计未证明部署域上的统一 `R`，所以不声称当前部署已证明 PCF 状态全程有界。

## 4. 命题三：R3 mask 的同输入代数关系

固定相同的 \(s_n,\eta_n,\phi_n,W_n,\beta_n,h_n\) 和投影算子，R3 的 mask 只从 Head 更新输入中去掉 z 轴 PCF 项；x/y 更新输入与全轴 PCF 分支相同。此恒等式只描述**同输入单步映射**。真实闭环中，两种策略会产生不同状态、特征窗和未来输入，因此恒等式不给出 H3 的改善符号或幅度，也不证明 R3 的收益来自 mask。参数收敛另需可实现的目标/残差结构及适用的持久激励证据；现有审计未验证 PE。

## 5. 命题四：实际 RK4 Plant 的条件有限步状态包络

全链审计给出了与实际 1 ms RK4 执行图一致的参数化增长递推。令 `D=diag(p_* I3, v_* I3, theta_* I3, omega_* I3)`，其中各尺度为正，单位依次为 m、m/s、rad、rad/s；因此归一化状态 `xbar=D^-1 x` 无量纲。Plant 向量场中的 `g_k^P` 表示经分配与限幅后的实际 Plant 输入，不是前文以 m/s^2 表示的 Head 命令 `u_n`。若对每一步的 RK4 中间状态球均可验证
\[
\|D^{-1}f(D\bar y;g_k^{P},F_{w,k},\tau_{w,k},P_k)\|_2\le\rho_k(q),
\]
其中 `rho_k(q)=C_s(1+q^2)+C_w(1+B_k^2)`，`B_k`、`Y_i` 与 `q` 为无量纲缩放范数，`rho_k`、`C_s`、`C_w` 单位为 s^-1；且参考、风、形态、质量/惯量、分配与电机等参数满足该审计列明的紧界假设，则从 \(B_0\ge\|\bar x_0\|_2\) 递推
\[
Y_1=B_k,\quad Y_2=B_k+\tfrac h2\rho_k(Y_1),\quad
Y_3=B_k+\tfrac h2\rho_k(Y_2),\quad Y_4=B_k+h\rho_k(Y_3),
\]
\[
B_{k+1}=B_k+\tfrac h6\{\rho_k(Y_1)+2\rho_k(Y_2)+2\rho_k(Y_3)+\rho_k(Y_4)\}
\]
即可由 RK4 更新和三角不等式归纳得到 \(\|\bar x_k\|_2\le B_k\)。若另有参考位置界 \(\|p_{\mathrm{ref},k}\|_2\le R_p\)，则 \(\|e_k\|_2\le R_p+p_*B_k\)。

该命题是**条件绝对状态增长包络**，递推可随时间增长；它不是 ISS/UUB、不是误差衰减结论，也不是 RK4 截断误差界。其紧集假设、历史 Plant 源逐项绑定及数值常数尚未对 72 场部署实例化，故不能报告为 72 场适用的数值误差界。

## 6. 理论资格判定与不得作出的主张

上述局部结果不能补齐完整理论门。当前缺少：增广闭环（位置/速度、姿态/角速率、滤波状态、PCF、Head 权重和 DSSM 窗口）的已证明前向不变域；从该域导出的统一 \(r_F\) 与实际位置加速度残差界；纳入 100 Hz projected-Euler、1 kHz PCF/Plant、输出保持、姿态/分配/电机饱和及 RK4 余项的负漂移或 ISS/UUB 证明；以及与历史 72 场绑定的 Plant 参数数值界。因此不得声称当前 72 场闭环稳定、闭环 ISS/UUB、Head 参数收敛、H3 改善方向已被理论证明，或这些局部性质构成已确立的方法贡献。

完整条件推导、部署实现范围和缺失参数清单见[全链有限步理论审计](deployment_chain_finite_horizon_audit.md)、[理论与文献审查](theory_and_literature.md)及[R3 mask 理论审计](../../../experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_theory_audit.md)。实现对应文件为[R3 runner](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m)、[DSSM forward](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_stage1_model_forward_v2.m)、[FEATURE Head](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_head_step.m)和[PCF helper](../../../matlab/models/position_filter_realization_pcf_step_v3_5.m)。
