# CM18-A1 离散 ISS 适用边界复核

复核范围为固定 BS、命令滤波、RK4 Plant 和 ROOT 的连续局部 ISS 草稿 v2；只读源代码和代数。没有运行 MATLAB、Plant、GPU 或训练，也未读取任何训练运行产物。

连续名义子系统的代数可以离散化成一个严格的**条件式** sampled bound，但源码不能给出所需的统一扰动上界。令 (x_k=[\sqrt{k_0}e_k;z_{2,k}])，(k_0=1\,\mathrm{s}^{-2})，则连续名义矩阵为

\[
A=\begin{bmatrix}-K_1&\sqrt{k_0}I\\-\sqrt{k_0}I&-K_2\end{bmatrix}.
\]

若实际固定配置中的 (K_1,K_2) 对称正定，则 (\operatorname{sym}(A)=\operatorname{diag}(-K_1,-K_2))，故令 (\mu=\min(\lambda_{\min}(K_1),\lambda_{\min}(K_2))>0)，有 (\|e^{hA}\|_2\le e^{-\mu h})。选 (F=e^{hA}) 是“连续理想名义误差流”的精确一步映射，不是代码的一步映射。对实际代码定义精确缺陷 (\delta_k=x_{k+1}^{\mathrm{impl}}-F x_k)，则

\[
\|x_k\|\le e^{-\mu hk}\|x_0\|+\frac{\bar\delta(1-e^{-\mu hk})}{1-e^{-\mu h}},\qquad
\limsup_k\|x_k\|\le\frac{\bar\delta}{1-e^{-\mu h}},
\]

前提是逐步 (\|\delta_k\|\le\bar\delta)，并且轨迹留在无 wrap 分支、增益/模型假设成立的紧集内。若能把连续有界扰动 (q) 与离散实现余项分开，(\bar\delta\le\bar q(1-e^{-\mu h})/\mu+\bar r_h)，从而上界为 (\bar q/\mu+\bar r_h/(1-e^{-\mu h}))。这个推导给出了论文可用的离散条件形式；它不证明本项目中的 (\bar\delta) 存在或足够小。直接选 (F=I+hA) 则是显式 Euler 的比较模型，至少还要验证 (\|I+hA\|_2<1)（一个充分条件为 (h\|A\|_2^2<2\mu)）；这也不等于当前 engine 实际的一步更新。

源码明确了缺陷必须覆盖哪些项。`command_filter_step.m:18-24` 返回旧滤波状态作为本步参考，同时用半隐式 Euler 更新状态：(v_{k+1}=v_k+h a_k)、(r_{k+1}=r_k+h v_{k+1})。若与本步常加速度的精确连续滤波流比较，位置端每步差为 (+\tfrac12h^2a_k)（远离 wrap）。effective-config 准备器把加速度限幅设为 ([\infty,\infty,6])，故滚转/俯仰滤波加速度没有代码级有限上界；还须假设目标与滤波状态有界。`run_cm18_closed_loop_v1.m:2378` 先更新滤波器；随后 `:2713`、`:2726` 算并分配一次控制，`:2758`/`:2783` 调一次 `rk4_vehicle_step`，`:2802` 才提交下一 Plant 状态。RK4 在一个 1 ms 步内四次评估时使用同一个 wrench、外力和 (P_{true})（`rk4_vehicle_step.m:11-18`），所以它对固定输入的 Plant 向量场是四阶积分，却没有在 RK4 子阶段重算 BS 反馈、滤波或 C5 目标。采样保持反馈相对连续反馈的误差应单列，不能只记作 (O(h^5)) 的 RK4 局部截断误差。

CM18 网络输出每 10 ms 更新一次、经 (D\) 裁剪和 (\beta) 渐入后保持 torque（engine `:2417-2467`），而 BS/allocator/Plant 每 1 ms 更新。故 (\delta_k) 还必须包含保持输出与 fresh 输出的错位、形态/分配/惯量/气动力矩、泛化请求和电机限制造成的实际力矩差。X18 中的 `u_current` 每个 Plant 样点直接读取，允许区间边界跳变；v2 草稿所加的分段连续变化总变差加跳幅项是必要的。RK4 的 (O(h^5)) 误差只在相应步内向量场足够光滑且高阶导数有界时成立；命令跳变应按分段输入处理，不跨跳变套用该光滑余项。

`attitude_bs_step.m:19-41` 支持名义连续反步误差式；`default_config.m:62` 给出的默认 (K_1,K_2) 为正对角阵，但 `prepare_effective_config_dl1018.m` 从外部 effective config 读取参数且未重设这两组增益。因此数值化 (\mu) 时应 pin 运行实际使用的 (P.bs.attitude)，不能只引用 defaults。现有源和运行记录没有给出闭环状态紧集前向不变性、部署分布上的统一网络/旧标签误差、每步总缺陷 (\bar\delta)，也没有 C5 外环与内环的小增益界。结论应保持为：可写出上述条件离散 ISS 引理；当前物理闭环稳定性和误差半径仍未证。

## 复核源身份

- `matlab/core/attitude_bs_step.m` SHA256：`cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc`
- `matlab/core/command_filter_step.m` SHA256：`15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b`
- `matlab/core/rk4_vehicle_step.m` SHA256：`7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5`
- `experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m` SHA256：`4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a`
- `ROOT_CM18_LOCAL_ISS_ERROR_BOUND_DRAFT_v2_ZH.md` SHA256：`9241ee3fff8558dddfcfe94c5b46404cf11ca84491469cd1391080759485d9d5`
