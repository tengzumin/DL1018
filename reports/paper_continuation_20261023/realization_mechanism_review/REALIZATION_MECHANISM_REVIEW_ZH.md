# C3 残差坐标与执行实现：短源审

## 结论

冻结 C3 的 (a_f) 是**包含当前 C3 补偿的命令侧滤波加速度**，不是 Plant 实际加速度。C3 标签是 10 ms 区间平均的 (dot v-a_f)，可写成 (Y+r_f)，其中 (a_{req}=a_{nom}-dF/m_c)、(Y=dot v-a_{req})、(r_f=a_{req}-a_f)。这正是旧 PCF 审核指出的 (s_c) 坐标自然输入；但 (dot e=s_c+eta-K_1e) 中仍有 (eta)，所以更好的 (W_k) 残差拟合不蕴含更小的位置误差。这个坐标关系本身不是实现错误，也不能单独解释闭环差异。

C3 raw 已记录重建**同一转移起点**即时 Plant 平动 RHS 所需的状态、请求/实际广义推力、滤波姿态参考、风力和 impulse 标志。故可不用速度差分，逐项还原推力/分配、姿态参考与真实姿态、重力参数差和外力对 (a_{Plant}-a_f) 的贡献。日志不直接存 (a_{Plant}) 或预计算的实现力误差；但配置、Plant RHS 与环境力函数均由输入锁绑定。此即时分解不等同于 10 ms 有限区间标签，后者还含 RK4 区间状态变化。

## C3 源码链与精确关系

在 `position_bs_step.m:24-27,55-56`，命令加速度为 (a_{req}=a_{nom}-dF/m_c)。C3 helper 在 `delayed_prediction_step_candidate.m:41-43` 用更新前 (W_k) 产生 `raw=W_k'phi`、`applied=beta*clip(raw,±3)`，再以一次 ±60 投影得到 (W_{k+1})。runtime 把该 applied 值变成 held force（`run_dl1018_closed_loop.m:2022,2082-2103`），随后作为 `dF` 传进 `position_bs_step`（2127）。因此该控制步的 `a_req` 已包含 C3 输出。

PCF 协调量在 `run_dl1018_closed_loop.m:1993-2003` 定为 (s_{eff}=clip(s-eta,[7,8,10]))，它进入 helper 的 tracking 更新项；(eta) 不直接加到预测输出。当前 delayed 标签由 runtime `2010-2014` 构成：

\[
y_{j:k}=\frac{(v_k-v_j)-\int_{t_j}^{t_k}a_f(\tau)\,d\tau}{0.01},
\]

其中事件 j 的特征 \phi_j 已缓存；后续事件 k=j+10 在 `2010-2019` 形成该区间目标，并把 previous pair (\phi_j,y_{j:k}) 传给 helper。helper 在事件 k 用更新前 W_k 作当前 readout 与延迟梯度，再生成后续 W_{k+1}。标签是区间平均 \dot v-a_f=Y+r_f，不是瞬时加速度差。`beta` ramp、输出 clip、延迟残差梯度和权重投影均在 helper 第 4-5、37-43 行。

`a_f` 由 `baseline_force_to_attitude` 得到的命令推力及 `command_filter_step` 当前滤波角计算，runtime `2222-2237` 调用 PCF helper 并积分 (a_f)。`position_filter_realization_pcf_step_v3_5.m:13-21` 明确给出
\[
a_f=(T_c/m_c)R_f e_3-g_c e_3,\qquad r_f=a_{req}-a_f,
\]
且 eta 按 (\eta^+=e^{-K_2dt}\eta+\int e^{-K_2t}dt\,r_f) 更新。`baseline_force_to_attitude.m:15-23` 从 (a_{req}) 计算推力，`command_filter_step.m:10-24` 给出当前滤波角。

复用已审推导（`reports/train_pcf_contract_parent_review_20261022/FINAL_REVIEW_ZH.md:36,40`）：理想 PCF 方程为
\[
\dot e=s_c+\eta-K_1e,\qquad
\dot s_c=-e-K_2s_c+u-(Y+r_f).
\]
因此 C3 学习的量可直接抵消第二式中的匹配输入，但即使 (Y+r_f) 预测无误，(eta) 仍驱动第一式。原 B 对应未补偿的 (\dot v-a_{req}=Y) 标签；B 与 C3 的闭环状态不同，不能用跨方法轨迹作组件因果证明。

## 同一记录上的 Plant 加速度拆分

`vehicle_derivative.m:27-32` 的 Plant 平动 RHS 为
\[
a_P=(T_r/m_p)R_a e_3-g_p e_3+f_{ext}/m_p,
\]
而 (a_f=(T_c/m_c)R_f e_3-g_c e_3)。令 (e_3=[0,0,1]^T)，则精确代数拆分是
\[
a_P-a_f=
\underbrace{(T_r/m_p-T_c/m_c)R_a e_3}_{推力/分配/电机实现}
+\underbrace{(T_c/m_c)(R_a-R_f)e_3}_{真实姿态与滤波姿态差}
+\underbrace{(g_c-g_p)e_3}_{重力参数差}
+\underbrace{f_{ext}/m_p}_{外力}.
\]
其中 (T_c) 是请求广义输入的推力分量，(T_r) 是 `realized_generalized` 的推力分量；(R_a) 由记录状态的 Euler 角得到，(R_f) 来自 `filtered_attitude_reference`。分配/电机限幅路径见 `allocate_control.m:16-44`，实际 `wrenchNow` 与风力合力送入 `rk4_vehicle_step` 见 runtime `2499-2531,2553-2556`。该分解是转移起点的瞬时 RHS 恒等式，不用速度差分；RK4 `rk4_vehicle_step.m:12-18` 在一步内重评 RHS，因此它不能冒充 10 ms 区间平均标签。

## raw 可行性与单一待证候选

对冻结 C3 manifest 的 72 个 raw 做了轻量 HDF5 字段存在性扫描（manifest SHA 见 `SOURCE_IDENTITY.json`）：72/72 都有 `state`、`requested_generalized`、`controller_clipped_generalized`、`allocated_generalized`、`realized_generalized`、`filtered_attitude_reference`、`wind_force_I`、`physical_impulse_force_I_N`、delayed target、(a_{req},a_f,r_f,\eta) 前后值及 `s_eff`。72/72 的 `physical_impulse_enabled` 和 `state_perturbation_enabled` 均为 0。三个可选直存量 `position_plant_acceleration_truth_mps2`、`position_realized_force_N`、`diagnostic_external_force_I` 均未记录；所以要依照冻结 RHS 与参数离线重建，而不是直接读取一个“真值加速度”字段。

日志控制数组有 20,000 个转移，`state/time` 有 20,001 个点；源码以 `q=1:last` 对应控制量、`qs=1:last+1` 对应状态（`run_dl1018_closed_loop.m:2632-2652`）。取每个转移的起点状态与同一行输入即可对齐，终点多出的状态不配控制量。外力当前只有记录的风力，物理 impulse 为零；条件诊断外力字段缺失，故这批记录不能分离任何未记录的诊断注入。

**唯一待证候选（尚未认定）：** 高频 Z 位置落差主要沿未被预测器消除的 eta_z 通道传播：即使 W_k 更准确地拟合 Y+r_f、从而改善 s_c 方程的匹配输入，eta_z 仍通过 dot e=s_c+eta-K_1e 影响位置误差。可只用同一 C3 轨迹的 state/reference 重建 e_z 与 s_c,z、使用已记录 eta_z 和锁定 K1 检查该误差方程闭合；若 eta_z 项小、反向，或无法解释误差变化，则该候选被削弱。a_P-a_f 的精确拆分仍可定位外力和实现项，但其幅值本身不能解释跟踪差，因为它正是拟合目标组成部分。不得跨 B/C3 闭环轨迹作组件因果结论，也不得把物理真值加入部署输入。

此次仅做源与 raw 字段核对；未改源码、参数或日志，未执行 Plant、训练或 TEST。

