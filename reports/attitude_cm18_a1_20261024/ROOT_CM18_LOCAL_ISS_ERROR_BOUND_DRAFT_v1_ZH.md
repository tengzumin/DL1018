# CM18-A1 固定补偿器的局部条件误差界（草稿）

状态：独立理论草稿，供 ROOT 审核。下述命题是“若这些条件成立，则有此界”，不是对当前模型或首航的证明结论。此处只审阅源码与既有同状态代数；未运行 Plant、engine 或训练。

## 实现对应关系

`attitude_bs_step` 以 ZYX 误差 `e=wrap(eta_d-eta)`、`de=etaRate_d-T(eta)omega` 构造 `z2=de+K1 e`，并取虚拟欧拉角加速度 `v=alphaDot+e+K2 z2`。它用 `T\(v-Tdot*omega)` 转为名义机体系角加速度，再由名义惯量、陀螺项和 BS 惯量导数形成 `tau_BS`，最后输出 `tau_BS-estimateTorque`。参见 [`attitude_bs_step.m`](../../matlab/core/attitude_bs_step.m:14)、[同文件](../../matlab/core/attitude_bs_step.m:24)、[同文件](../../matlab/core/attitude_bs_step.m:33) 和[同文件](../../matlab/core/attitude_bs_step.m:39)。

CM18 强制固定名义 `J0`、固定形态控制器、`Jdot_for_bs=0`，并限制加速度输出逐轴裁剪到 `D=[45,45,4.7124] rad/s^2`、以 `beta=min(k*dt/2.2,1)` 渐入。每次 100 Hz 事件网络只前向一次，`c_k=beta_k Pi_D(f_theta(X_k))` 转成力矩 `J0*c_k`，并在后续事件前保持。X18 的状态、名义角加速度、当前命令及过去窗口由 engine 构造；见 [`run_cm18_closed_loop_v1.m`](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:140)、[同文件](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2425)、[同文件](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2436) 和[同文件](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2443)。

分配器先裁剪广义请求，再以控制器分配矩阵求平方转速，并受真实电机界限限制；返回实际广义输入时使用真实 Plant 分配矩阵。若关闭裁剪和电机动态，实际动作仍可因 `C(t) != C0` 偏离名义映射。见 [`allocate_control.m`](../../matlab/core/allocate_control.m:16) 至[同文件](../../matlab/core/allocate_control.m:26)。Engine 每 1 ms 更新控制与状态；可选电机时间常数会另引入执行器动态。实际刚体角动力学含真实 `J(t)`、`Jdot(t)`、陀螺项和外力矩，见 [`vehicle_derivative.m`](../../matlab/core/vehicle_derivative.m:31)。

## 同状态动作映射

记 `T` 为 ZYX 机体系角速度到欧拉角速度矩阵，`a_BS=T^{-1}(v-Tdot*omega)` 为名义 BS 机体系角加速度。令 `S=[0_(3x1), I3]` 选取力矩分量，`B=[0_(1x3); I3]`，`C0` 为固定控制分配矩阵，`C(t)` 和 `J(t)` 为当前真实分配矩阵和惯量。取补偿加速度坐标 `c=J0^{-1} tau_comp`，单位 `rad/s^2`。在无广义裁剪、无电机饱和、无电机动态的局部仿射模型中，若请求为 `[F; tau_BS-J0*c]`，则

`M(t)=J(t)^(-1) S C(t) C0^(-1) B J0`

是从名义补偿坐标到真实角加速度的动作映射。定义无补偿时的瞬时偏差 `E0=omegaDot(0)-a_BS`，则

`E(c)=omegaDot(c)-a_BS=E0-M c`.

`E0` 吸收真实/名义惯量及陀螺差、`Jdot`、外部力矩以及无补偿时的真实形态分配误差。若实际执行器不能实现上述仿射动作，另以 `delta_tau` 表示实际力矩相对该理想仿射映射的误差，则 `E(c)=E0-Mc+J^(-1)delta_tau`。`M` 一般不等于单位阵，也未被代码或当前审计证明可逆。仅在 `C=C0` 且执行器理想时，`M=J^(-1)J0`；再有 `J=J0` 才得到 `M=I`。

若训练目标确实是既有同状态推导中的旧动作残差 `d_old=E(c_old)+c_old=E0+(I-M)c_old`，那么不裁剪、`beta=1`、模型在此输入精确输出 `d_old` 时，新补偿 `c_new=d_old` 仍留下

`E(c_new)=(I-M)(d_old-c_old)`.

所以“准确复现旧动作标签”一般不等于“精确抵消真实加速度残差”。这与既有代数推导一致，参见 [同状态动作推导](ROOT_SAME_STATE_ACTION_DERIVATION_v1_ZH.md:5)。当 `M` 病态或奇异时，某些动作方向无法由这条力矩路径校正；任何对未知形态的普遍消除承诺都不成立。

含网络误差、输出裁剪和渐入时，记 `Pi_D` 为逐轴投影到 `[-D,D]`，`epsilon_N=||f_theta(X)-d_old||`，则非扩张性给出

`||c_new-d_old|| <= beta*epsilon_N + beta*||Pi_D(d_old)-d_old|| + (1-beta)*||d_old||`.

因此，在事件时刻、上述仿射执行条件下，

`||E(c_new)|| <= ||I-M||*||d_old-c_old|| + ||M||*epsilon_c + ||J^(-1)delta_tau||`,

其中 `epsilon_c` 为上一式右侧。这一界把三种不同来源分开：动作映射偏差、固定网络误差，以及渐入/输出限幅；它不声称它们在当前数据上已经足够小。

事件间隔为 `Delta_e=0.01 s`。若 `E0`、`M` 沿状态、形态、参考及命令上下文局部 Lipschitz，且该上下文变化速度有界，则零阶保持新增项可界为

`delta_hold <= (L_E0 + L_M*c_max)*nu_X*Delta_e`,

其中 `nu_X` 是所选上下文的变化速度上界，`c_max <= ||D||_2`。此条件不能从“每 100 Hz 更新”本身推出；若快速形态或参考变化使 `nu_X` 大，保持误差也会大。CM18 事件确实按 `k*dt/2.2` 渐入并持有 torque/acceleration，见 [engine event update](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2445) 至[同文件](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2470)。

## 条件 ISS 命题草稿

**命题（相对滤波姿态参考的局部 ISS）**。令参考为 engine 实际使用的滤波姿态参考 `eta_d`。在某个局部误差图内，假设：

1. ZYX 俯仰角保持在远离奇异区的紧集内，wrapped 误差不跨越 `±pi` 分支；`T,T^{-1},Tdot` 有界，参考及其一、二阶导数存在且有界。
2. `K1,K2` 对称正定；真实 `J(t)` 一致正定且有界，`C(t),Jdot(t)` 有界，闭环状态留在上述紧集。
3. 所有形态、外力矩、执行器非仿射误差、模型预测误差、10 ms 保持误差及 1 ms 参考/采样实现误差，合并后在欧拉角加速度坐标中满足 `||q(t)|| <= q_bar`。这个 `q_bar` 必须由独立界或明确假设给出，不能由单次运行不发散替代。
4. 对连续时间陈述，使用与命令滤波输出一致的可微参考；若实际 1 ms 离散滤波/控制输入和该连续信号不一致，其导数失配与 RK4/采样误差必须包含在 `q` 中。

在上述条件下、未穿越角度误差分支时，代码名义控制结构给出

`dot e = z2-K1 e`, `dot z2 = -k0 e-K2 z2-q`,

其中代码中的裸 `+e` 按 SI 解释为 `k0=1 s^-2` 的误差反馈项。取 `V=(k0*||e||^2+||z2||^2)/2`，并令 `lambda=min(lambda_min(K1),lambda_min(K2)/2)`，则

`dot V <= -2*lambda*V + q_bar^2/(2*lambda_min(K2))`.

故

`V(t) <= exp(-2*lambda*t)*V(0) + q_bar^2/(4*lambda*lambda_min(K2))*(1-exp(-2*lambda*t))`,

并有 `limsup ||(sqrt(k0)e,z2)|| <= q_bar/sqrt(2*lambda*lambda_min(K2))`。这是关于有界加速度扰动的局部 ISS 界；只有 `q_bar=0` 才退化为该子系统的名义渐近跟踪结论。实现是 1 ms 离散积分且滤波量采样更新；要给离散闭环严格结论，还应导出一步 Lyapunov 差分界，不能仅把连续式当作代码已证明的稳定性。

这个命题以滤波参考为目标。若要声称跟踪 C5 未滤波的外层姿态目标，还要给出滤波幅值、相位/导数误差的上界；源码记录 `raw_outer_attitude`、`filtered_attitude_reference` 和实际滤波加速度，参见 [engine reference log](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2890)。CM18 的 100 Hz 输出保持、C5 的 1 ms 外层状态/命令闭环会相互耦合；该命题把它们当有界输入/扰动，并未证明 C5 平移子系统。要扩展为完整位置—姿态闭环，至少还需分别证明外层 C5 的局部 ISS 增益，并验证相互增益乘积小于 1；当前材料没有这些增益界。

## 应用价值、证据边界与待补项

应用上的价值是：把离线学得的、固定参数 CM18 状态—动作补偿器接入现有反步内环，仍由已实现的 BS 反馈提供名义误差动态；不需要宣称或依赖在线参数收敛。旧标签经同状态分析后能明确指出 `M` 才是“补偿坐标到真实加速度”的关键桥梁，并把学习偏差、输出限幅、渐入及保持分别纳入可审查的误差预算。若将来能独立给出小的 `||I-M||`、模型误差、保持变化及执行器误差上界，ISS 式可转成有量纲的误差半径。

当前冻结网络是前向固定映射；engine 对 CM18 调 `cm18_a1_forward_v1`，未在该分支更新参数（事件代码见 [engine](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2439) 至[同文件](../../experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m:2448)）。因此这里没有在线学习的参数收敛命题，也没有 PE 假设或 PE 证据。单航事件审计证明的是指定日志、输入、输出和 held torque 的实现闭合；它不提供分布外统一 `epsilon_N`、真实形态的 `M` 条件数界、未来执行器无饱和保证或 C5 小增益证明。首航饱和计数为零也只描述该次运行，不能作为所有形态/状态的假设证明。

要把草稿变成可引用的稳定性结论，仍缺：

- 由物理形态域给出 `J(t)` 正定上下界、`C(t)` 有界以及 `M(t)` 可逆/接近 `I` 的范围（若采用逆映射方案）。
- 对固定网络在部署上下文的误差上界，而非训练/验证均方误差或事件回放一致性。
- 限幅、`beta` 初始渐入、100 Hz 保持、1 ms 滤波和电机/分配非理想项的显式界；确定每种硬裁剪何时使局部仿射映射失效。
- 对 ZYX 局部图、参考导数和整个 C5 平移—姿态闭环的紧集前向不变性及小增益条件；再用实际采样/RK4模型给出离散 Lyapunov 差分验证。

在这些缺口补齐前，恰当结论只能是：名义 BS 子系统具有上述条件 ISS 结构；CM18 是否实际满足足够小的扰动界，仍未证明。
