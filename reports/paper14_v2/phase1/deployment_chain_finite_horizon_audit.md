# DL1018 全部署链离散界复核：条件有限时域包络与当前证据门槛

复核日期：2026-10-22。结论先行：**现有可访问证据不能给出覆盖实际72场部署的数值离散 ISS/UUB 或有限时域跟踪误差界。** 可以给出两个更窄的结果：一是 Head/PCF 的逐步条件界；二是一个覆盖实际 RK4 离散 Plant 的、带明确参数前提的有限步增长包络递推。后者不是 ISS，不说明误差衰减，也不能在当前受限资料下实例化为这72场的数值界。投影后的权重有界不推出闭环稳定。

## 复核范围与执行链

仅只读复核当前隔离 runner、FEATURE Head、DSSM encoder forward、PCF helper、外环、姿态滤波/反步、控制分配、RK4 Plant、风载/质量属性源码及 phase1 mechanism audit。没有启动 MATLAB、仿真、训练或测试；没有读取/解封 TEST、raw、MAT、checkpoint 或 cache；没有改动运行代码。有效配置由 `init_dl1018.m` 从 `configs/effective_config.mat` 加载，本轮没有打开该文件。源码 SHA 列于文末。

实际闭环每个 dt=0.001 s 控制周期按当时状态算位置外环、姿态参考、反步力矩与电机命令，再调用经典 RK4。runner 在步首根据 xk 计算风载与力矩，并将这两个量及实际电机生成的广义 wrench 固定给 RK4 的四个子阶段；不是每个 RK 子阶段重新查询风场。100 Hz 位置事件将 FEATURE Head 输出力保持到下一事件；DSSM 的32步上下文未就绪时保持零力。PCF 每个1 ms步更新 eta，只在 Head 事件更新方向中用 s−eta_before；它没有改写外环位置 Lyapunov 面。Head 启用时调用私有 position_only_search_head_step，不调用另一个未启用的 position_stage1_update_head_pcf_v3_5。

Plant 状态与代码方程对应为 `x=[p;v;theta;omega]`：

\[
\dot p=v,\quad
\dot v=R(\theta)e_3 T/m-ge_3+F_w/m,\quad
\dot\theta=E(\theta)\omega,\quad
\dot\omega=I^{-1}\{\tau+\tau_w-\omega\times(I\omega)-\dot I\omega\}.
\]

其中 vehicle_derivative.m 的 Euler-rate 映射将 pitch 夹在 ±(π/2−10⁻⁴)，但 Plant 不保证 roll/pitch 状态不变域；RK4 结束后只把 yaw 折回主值区间。风载是相对风速逐轴二次阻力，变臂力还带由 CoG 和臂位置产生的力矩。allocate_control 先裁剪控制端广义命令，再解控制分配矩阵并将电机转速裁到 Plant 额定区间；实际 Plant wrench 由真实分配矩阵和实际电机平方转速生成。因此实际 wrench 有界（前提是形态和分配矩阵有界），但命令到 wrench 的失配不因裁剪而有界于一个常数：如果外环请求随跟踪误差增长，actualGeneralized−command 也可随之增长。

## 可逐项成立的离散子界

**FEATURE 表征与 Head 输出。** DSSM forward 对状态施加 `tanh`，构造

\[
\phi_n=[h_n;1]/\sqrt{1+\|h_n\|_2^2},\qquad \|\phi_n\|_2=1
\]

（前提是 checkpoint 参数/输入运算有限，runner 的 finite 检查通过）。FEATURE Head 先算 `W_n^T phi_n`，逐轴裁到 ±3 m/s²，再乘 `beta in [0,1]`。因此不需要知道 W0 数值就能严格得出

\[
\|u_n\|_\infty\le3\ {\rm m/s^2},\qquad
u_n\text{ 在相邻100 Hz事件之间保持}.
\]

这界的是送入位置外环的 Head 命令加速度：runner 将 m·u_n 作为 residual force 传给 position_bs_step。它不是 Plant 实际加速度界，也不能直接解释为飞行器每10 ms的真实速度改变量，因为该项之后仍经过倾角/推力映射、反步姿态回路、分配矩阵与电机饱和。

FEATURE 更新逐事件为（gamma=12，leakage=0.002）：

\[
W_{n+1}=\Pi_{[-60,60]^{33\times3}}
\{W_n+h_n[-12\beta_n\phi_n s_{eff,n}^T-0.002W_n]\},\quad
s_{eff}=\operatorname{clip}(s-\eta,\pm[7,8,10]).
\]

对任意有限 W_n，投影后 W_{n+1} 属于 [-60,60]^(33×3)；所以从第一个有效更新之后，

\[
\|W_n\|_F\le60\sqrt{99}=596.9925.
\]

对盒内更新前状态，‖G_n‖F≤12√213+0.002·60√99<176.33；在 h_n≈0.01 s 时未投影更新量不超过约1.7633（W 的 SI 数值标度）。这只界定参数更新幅度/投影后盒约束；离散平方误差差分仍有 h_n²‖G_n‖² 正项，源码没有保证交叉项吸收它，更没有建立它与 Plant 误差的负漂移。未读取 checkpoint，所以首个事件前的 W0 绝对范围不可复核；首个命令仍受输出裁剪，首个更新后投影盒界成立的前提是输入权重有限且该事件被执行。

**PCF 条件界。** helper 每1 ms计算 `r_F,k = a_req,k − a_F,k`，以命令重构比力而非真实 Plant 加速度更新：

\[
\eta_{k+1}=e^{-k_2 h}\eta_k+\frac{1-e^{-k_2 h}}{k_2}r_{F,k},\quad h=0.001s.
\]

在 phase1 audit 记录的 k2=4 s^-1 下，a=exp(-0.004)=0.9960079893、b=(1-a)/4=0.0009980027 s。若所有步都有 ‖r_F,k‖∞ ≤ R，才可推出

\[
\|\eta_k\|_\infty\le a^k\|\eta_0\|_\infty+(1-a^k)R/4.
\]

源码和 phase1 机制报告没有给出覆盖运行域的 R。但即使 eta 本身没有数值界，Head 使用的 s_eff 仍逐轴受 ±[7,8,10] m/s 裁剪，因而其范数不超过 √213=14.5945 m/s。这保住了 Head 更新方向的条件常数，不代表 PCF tracking error 或物理闭环误差有界。

**ZOH、姿态和执行器。** 源码将 Head applied force 保持至下一100 Hz事件；position outer loop、姿态滤波、反步控制和电机命令则每1 ms重算。ZOH 只给保持输入的幅度界，不给它与某个连续更新理想命令的误差界；后者还需 feature/state/reference 的变化率或 Lipschitz 界。姿态 command filter 的速率用半隐式 Euler 更新，命令角折回主值，角加速度配置不是全轴有限裁剪（初始化契约中 roll/pitch 为 `Inf`、yaw 为 `6 rad/s²`）；filter rate 没有源码投影盒。姿态反步力矩可随角速率及 Tdot·omega 增大，最后由分配器/电机裁剪限制实际 Plant 输入。由此可证实际输入上界，不能证明姿态跟踪误差界。

## 覆盖完整离散 Plant 的条件有限步包络

不能由当前资料实例化72场的数值界，但可给出覆盖实际 RK4 执行图的参数化有限步包络。它是绝对状态增长界，不是 ISS/UUB，也不是对连续系统的 RK4 截断误差估计。

令 \(h=0.001\mathrm{s}\)、\(N<\infty\)。Plant 状态为 \(x=[p;v;\theta;\omega]\)。为避免把不同物理单位直接混成一个范数，选定正尺度
\[
D=\operatorname{diag}(p_*I_3,v_*I_3,\theta_*I_3,\omega_*I_3),\qquad
\bar x=D^{-1}x,
\]
例如 \(p_*=1\mathrm{m},v_*=1\mathrm{m/s},\theta_*=1\mathrm{rad},\omega_*=1\mathrm{rad/s}\)。有限步命题假设：

1. \(\|\bar x_0\|\)、姿态 command filter/PCF/Head 的初态有限；每步参考及其导数、模型前向和控制器中间计算均有限，不出现 NaN/Inf。
2. 全部 \(N\) 步中 \(m\ge m_->0\)，臂长/臂速属于已知紧集；从而 \(I\succeq I_-I_3\)、\(\|I\|\le I_+\)、\(\|\dot I\|\le I_{\dot+}\)，CoG/臂位置和真实分配矩阵 \(C(\ell)\) 有已知有限上界。
3. 实际 motor speed 有已知上界 \(\Omega_{\max}\)，Plant wrench 由 \(C(\ell)\omega_m^{\circ2}\) 产生。若启用 motor time constant，初始 motor 也在额定盒内；额外注入力/矩有已知上界 \(F_0,\tau_0\)。
4. \(\|w_k\|\le\bar W\)，空气密度、阻力系数、CAD 面积、臂尺寸、CoG 和风载比例有已知有限界。按源码的二次阻力，存在常数 \(c_F,c_\tau<\infty\)，使每步步首采样风力和力矩满足
\[
\|F_{w,k}\|\le c_F(1+\|v_k/v_*\|^2),\qquad
\|\tau_{w,k}\|\le c_\tau(1+\|v_k/v_*\|^2).
\]
5. 初始化分配及命令滤波等运算对有限状态返回有限值；pitch kinematics 使用源码里的 \(\pm(\pi/2-10^{-4})\) 截断。

由 motor clip 和有界几何，取 UT=sup|Tk|、Uτ=sup‖τk‖₂；例如使用二范数时，UT、Uτ≤2 supℓ‖C(ℓ)‖₂ Ωmax² 是安全的共同上界。
\[
K_E\le\sqrt{2+\tan^2(\tfrac\pi2-10^{-4})+\sec^2(\tfrac\pi2-10^{-4})}
<1.4143\times10^4.
\]
设 \(q\) 是当前 RK 中间状态的缩放范数上界、\(B_k\ge\|\bar x_k\|_2\)。由 vehicle_derivative 的四个分量、惯量下界、陀螺项二次增长和步首采样后保持的风载，可取
\[
C_s=\frac{v_*}{p_*}
+\frac{U_T/m_-+g+F_0/m_-}{v_*}
+\frac{K_E\omega_*}{\theta_*}
+\frac{U_\tau+\tau_0}{I_-\omega_*}
+\frac{I_+\omega_*}{I_-}
+\frac{I_{\dot+}}{I_-},\qquad
C_w=\frac{c_F}{m_-v_*}+\frac{c_\tau}{I_-\omega_*},
\]
使
\[
\|D^{-1}f(D\bar y;u_k,F_{w,k},\tau_{w,k},P_k)\|_2
\le \rho_k(q):=C_s(1+q^2)+C_w(1+B_k^2)
\quad\text{whenever }\|\bar y\|_2\le q.
\]
\(C_s,C_w\) 以固定 SI 尺度下的数值范数理解；它们是增长系数，不是稳定性常数。\(C_w\) 保留 \(B_k\)，因为本 runner 在步首 \(x_k\) 计算风载并将它固定用于四个 RK 子阶段；没有假设每个子阶段重算风。

对实际经典 RK4，定义
\[
Y_1=B_k,\quad Y_2=B_k+\tfrac h2\rho_k(Y_1),\quad
Y_3=B_k+\tfrac h2\rho_k(Y_2),\quad Y_4=B_k+h\rho_k(Y_3),
\]
\[
B_{k+1}=B_k+\tfrac h6\{\rho_k(Y_1)+2\rho_k(Y_2)+2\rho_k(Y_3)+\rho_k(Y_4)\}.
\]
**证明。** 若 \(\|\bar x_k\|\le B_k\)，第一个导数缩放范数不超过 \(\rho_k(Y_1)\)，故第一中间状态不超过 \(Y_2\)；依次应用同一增长界，第二和第三中间状态不超过 \(Y_3,Y_4\)，第四导数不超过 \(\rho_k(Y_4)\)。代入源码 RK4 组合
\[
x_{k+1}=x_k+\tfrac h6(K_1+2K_2+2K_3+K_4)
\]
并用三角不等式即得 \(\|D^{-1}x_{k+1}\|\le B_{k+1}\)。RK4 末尾只 wrap yaw；在 \(\theta_*=1\mathrm{rad}\) 时，wrap 不增加该缩放欧氏范数。对任意有限 \(N\)，若假设常数有限，该递推逐项产生有限 \(B_0,\ldots,B_N\)。若另有 \(\|p_{ref,k}\|\le R_p\)，则位置跟踪误差满足
\[
\|e_k\|_2\le R_p+p_*B_k,\qquad k\le N.
\]

该命题覆盖每1 ms的姿态/力矩/电机映射和 RK4 更新；Head、PCF、ZOH 对实际 Plant 的影响通过实际有限 motor wrench 与上面假设进入包络。它只有条件绝对增长界：递推允许 \(B_k\) 快速增大，既不给误差衰减，也不给 disturbance-to-state 增益、吸引域或连续模型截断误差。有限 \(B_N\) 还只在实数运算中成立；要保证 MATLAB double 不溢出需另核数值范围。

## 为什么这个条件命题还不能过计划门槛

将上面的 Cs、Cw、Bk、Rp 变为适用于72场的数值，需要在不泄露/读取受限资料的前提下给出并绑定：

- 每场 Plant 初始12状态及 filter/PCF 初值的认证上界；每步参考位置/速度/加速度及 yaw 范围。
- 全时域环境风上界、形态长度与长度速率紧集；明确风力比例和所有可能的注入力/矩为零或有界。
- mass、惯量最小特征值/范数/变化率、CAD 面积/尺寸/风系数、CoG 与旋翼臂范围；motor 上限及 supℓ‖C(ℓ)‖。当前这些实数由未打开的 effective-config MAT、场景/模型资产或 runtime data 提供；simulation_parameters 读取/传递参数但不在该函数证明相应全时域紧界。
- 以上 Plant 来源与72场实际部署的逐字节绑定。phase1 frozen identity/lineage 报告记了 runner/runtime/config 身份，但没有对 `vehicle_derivative`、RK4、风载/分配等共享 Plant 源逐项绑定 SHA；本报告 SHA 是现在复核到的字节，不补造历史绑定。

如果仅需要数学上某固定输入序列的有限维数值上界，可对完整公开的初值、配置、风/形态/参考序列和模型权重逐步区间传播；但当前约束禁止打开其中若干源，且当前审计没有这些逐步包络。有限仿真统计最大误差不能替代上述先验递推。若计划门槛是“稳定/鲁棒 tracking 或有用有限域误差界”，最小还需要：一套经验证的前向不变域与控制链误差上界，或一个覆盖整个 sampled/limited/RK4 复合映射的离散 Lyapunov/ISS 证明，含 Head projected-Euler 的 h²‖G‖² 项及所有 ZOH、滤波、分配/电机饱和余项。当前没有这些证据；也没有 PE 验证，故不能声称参数收敛。

因此目前最强可诚实采用的结论是：**Head 命令逐轴限幅为3 m/s²并在事件间保持；完成一次有效更新后 FEATURE 权重在盒内（假设有限输入权重）；PCF eta 在 r_F 有统一界时满足上列条件界；电机命令在其额定盒内；对完整 RK4 离散 Plant 可给条件的固定有限步增长递推。** 不能宣称72场部署闭环稳定、ISS/UUB、误差数值上界、Head 收敛或连续模型 RK4 误差已量化。

## 源码 SHA-256 与复核命令

私有 runner 根：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1`。项目源码根为本仓库。

| 文件 | SHA-256 |
|---|---|
| 私有 `sources/local_runtime/run_dl1018_closed_loop.m` | `01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b` |
| 私有 `sources/local_runtime/position_only_search_head_step.m` | `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc` |
| 私有 `sources/local_runtime/position_stage1_model_forward_v2.m` | `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676` |
| 私有 `sources/local_runtime/position_only_search_options.m` | `4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf` |
| 项目 `matlab/models/position_filter_realization_pcf_step_v3_5.m` | `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0` |
| 项目 `matlab/core/position_bs_step.m` | `ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681` |
| 项目 `matlab/core/baseline_force_to_attitude.m` | `ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039` |
| 项目 `matlab/core/command_filter_step.m` | `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b` |
| 项目 `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| 项目 `matlab/core/allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| 项目 `matlab/core/vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| 项目 `matlab/core/rk4_vehicle_step.m` | `7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5` |
| 项目 `matlab/core/morphology_aware_wind_load.m` | `51459cd2c09f1181e85bbee8f89ddbd75bd2ba923f1aebacbdd1ecfe7b3ba5ac` |
| 项目 `matlab/core/arm_mass_properties.m` | `8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5` |
| 项目 `matlab/core/simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| 项目 `matlab/core/allocation_matrix.m` | `5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d` |
| 项目 `matlab/core/rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| phase1 `reports/paper14_v2/phase1/mechanism_audit.md` | `411568b8c7f289459297e83533b1e10bee9b75b60cf4f7a6f29f244bd6ce0b39` |
| 外部 `reports/PAIR_EVAL_FROZEN_IDENTITIES.json` | `278bb5e8c6011188290c1f59976adb13b5ce1f527f5516c96896f9be0d430da9` |

复核采用只读 PowerShell/rg：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath <上表文件绝对路径>
rg -n 'position_only_search_head_step|position_filter_realization_pcf_step_v3_5|rk4_vehicle_step|vehicle_derivative|allocate_control|position_bs_step|command_filter_step|attitude_bs_step' <私有runner及项目源码路径>
Get-Content -LiteralPath reports/paper14_v2/phase1/mechanism_audit.md
```

本轮没有哈希或读取 `effective_config.mat`、任何 MAT/checkpoint/cache/raw/TEST。推理服务的速度档/服务端 `xhigh` 设置无法从当前工具本地读取或切换；按要求未使用 Fast 专用工具。
