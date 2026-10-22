# DL1018 phase1 离散稳定性理论第二复核

日期：2026-10-22。结论：**部署闭环离散 ISS/UUB 定理门槛不通过。** 本复核能证明 PCF 的条件输入界、Head 输出裁剪和投影后的权重盒约束；也能给出理想采样双积分外环的条件离散 ISS 形式。但这些性质没有覆盖当前 RK4 六自由度 Plant、姿态/推力映射、执行器限幅、10 ms Head ZOH 与未界定的状态依赖扰动。不能把权重有界解释成闭环稳定，也不能把72条有限轨迹当作统一上界或证明。

## 审查对象和身份

phase1 记录的72个 run_start 行统一为 DSSM14 / FEATURE、context 32、Head/update/PCF enabled、`gamma=12`、`kappa=1`、`beta_scale=1`、位置更新周期0.01 s、Plant `dt=0.001 s`。每场有1999个计划事件、1968个有效在线事件；事件间隔实测范围为0.00999999999999801–0.010000000000001563 s。PCF与 Head 重放最大误差约 `3e-15` 和 `2.22e-16`，投影 mismatch 为0。这些结果核对的是已记录航次的执行与重放，不构成全运行域界。

外部配对入口先从项目根目录加载 `init_dl1018`，再将私有 `sources/local_runtime` 放到 MATLAB path 前端。故 runner、DSSM forward、FEATURE search Head 来自私有 runtime；Plant、PCF eta step、外环/姿态控制和分配函数来自项目 `matlab/core`、`matlab/models`。search Head 启用时，runner 实际走 `stage1SearchStep=@position_only_search_head_step` 分支；`position_stage1_update_head_pcf_v3_5` 是另一条未启用 search 的分支，不应用它替代本次 Head 方程。PCF 函数 `position_filter_realization_pcf_step_v3_5` 则由本次 runner 实际调用。

下表 SHA-256 是本次复核读取的源文件身份。私有来源路径根为 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\corrected_reference_training_v1\corrected_pair_eval_v1`；项目相对路径根为本仓库。

| 文件 | SHA-256 |
|---|---|
| 私有 `scripts/run_corrected_pair_eval_stage.m` | `8b1a21c3619ee03382b89fbaf7adb3167769801d933575a37dbb8114f3d84a21` |
| 私有 `sources/local_runtime/run_dl1018_closed_loop.m` | `01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b` |
| 私有 `sources/local_runtime/position_stage1_model_forward_v2.m` | `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676` |
| 私有 `sources/local_runtime/position_only_search_options.m` | `4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf` |
| 私有 `sources/local_runtime/position_only_search_head_step.m` | `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc` |
| 项目 `matlab/runtime/init_dl1018.m` | `df1cfe9fdbfd61da9636427784852d1fa72a6d3b2aa6a941a094967322afda1c` |
| 项目 `matlab/runtime/controller_options_dl1018.m` | `93633a5fd95f73d33982045c2fa372d49b1a0df8ea0cfb5ca4461208ca9d53b1` |
| 项目 `matlab/core/rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| 项目 `matlab/core/position_bs_step.m` | `ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681` |
| 项目 `matlab/core/baseline_force_to_attitude.m` | `ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039` |
| 项目 `matlab/core/command_filter_step.m` | `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b` |
| 项目 `matlab/models/position_filter_realization_pcf_step_v3_5.m` | `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0` |
| 项目 `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| 项目 `matlab/core/allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| 项目 `matlab/core/rk4_vehicle_step.m` | `7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5` |
| 项目 `matlab/core/vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| 项目 `matlab/core/morphology_aware_wind_load.m` | `51459cd2c09f1181e85bbee8f89ddbd75bd2ba923f1aebacbdd1ecfe7b3ba5ac` |
| 项目 `matlab/core/simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| 项目 `matlab/core/arm_mass_properties.m` | `8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5` |
| 项目 `matlab/core/allocation_matrix.m` | `5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d` |
| phase1 `mechanism_audit.md` | `411568b8c7f289459297e83533b1e10bee9b75b60cf4f7a6f29f244bd6ce0b39` |
| phase1 `mechanism_run_start_lineage.csv` | `99f630dd3702e4ea3e9638b875dc1d3d621ffa22daf8b88baa0232d6860fda50` |
| phase1 `mechanism_components_by_scene.csv` | `f1ba9ff2335ea75e992436f753fb75ff1678271f33bf6d2fe706db4b45572e3b` |
| phase1 `theory_and_literature.md` | `388b983350b55e1c15ec4878b57c4df53e302f96a9c461b6a3905a08ec4a0e7c` |
| 外部 `reports/PAIR_EVAL_FROZEN_IDENTITIES.json` | `278bb5e8c6011188290c1f59976adb13b5ce1f527f5516c96896f9be0d430da9` |

身份限制：冻结身份报告绑定了项目 `init_dl1018.m`、私有 runtime tree、配对入口和 effective-config SHA；phase1 另记录私有 runner、DSSM forward、search Head 与 PCF helper SHA。冻结身份/72个 run_start 没有逐项记录 `vehicle_derivative.m`、`rk4_vehicle_step.m`、分配器和风载函数的 SHA。因此表中这些共享 Plant 源是当前读取到的源码及其 SHA，不能仅凭此表声称它们与72次历史运行逐字节相同。effective config 的 MATLAB 二进制、模型 checkpoint 和缓存按约束未打开；run_start 文本摘要只用于读取已审计参数。

## 实际离散链

位置误差面为 `e=p_ref-p`、`s=de+k1 e`，`k1=1`；外环名义加速度在源码中为 `a_N=ddot(p_ref)+k1 de+e+k2 s`，`k2=4`。每1 ms重新计算外环与姿态/执行器命令。`position_bs_step` 将残差力从名义力中扣除，再由 `baseline_force_to_attitude` 映射成推力和姿态；倾角有硬限制。姿态参考通过 `command_filter_step` 的1 ms半隐式 Euler 状态更新和角加速度限制。`allocate_control` 对广义力/力矩作控制端限幅，解电机平方转速后裁剪负值与 Plant 电机转速；Plant 分配矩阵与控制端矩阵可不一致。当前 runner 每1 ms调用经典 RK4 推进12状态六自由度刚体 Plant；该步内广义输入、风力/力矩和当前形态参数对四个 RK4 子阶段保持不变。Plant 含姿态旋转、惯量耦合、时变惯量项、气动风载和形态变化，不是理想双积分器。

Position Head 在100 Hz事件点用 `W_n` 先输出、再更新。`phi` 来自冻结 DSSM encoder 对14维、32事件窗口的 forward，归一化成33维 FEATURE；其事件输出在后续事件前保持。`beta=clip(t/1.8,0,1)`；事件上下文未满32前没有有效推理。部署输出和更新是

\[
u_n=\beta_n\,\mathrm{clip}(W_n^\top\phi_n,[-3,3])\quad(\mathrm{m/s^2}),
\]
\[
W_{n+1}=\Pi_{[-60,60]^{33\times3}}
\left[W_n+h_n\left(-12\beta_n\phi_n s_{\mathrm{eff},n}^{\top}-0.002W_n\right)\right],
\quad h_n\simeq0.01\ \mathrm{s},
\]
\[
s_{\mathrm{eff},n}=\mathrm{clip}\bigl(s_n-\eta_{\mathrm{before},n},\pm[7,8,10]\bigr)\quad(\mathrm{m/s}).
\]

`u_n` 是先用 `W_n` 算出并保持的力级补偿加速度；`W_{n+1}` 不回算当前事件输出。`position_only_search_options` 令初值为 `kappa*W0`，run_start 为 `kappa=1`。本次 Head helper 只在更新方向中使用 `s_eff`；PCF eta 不是加入外环 Lyapunov tracking error 的补偿状态。源码的另一 helper `position_stage1_update_head_pcf_v3_5` 不在启用 search 的执行分支。

PCF eta 每个 Plant 步基于命令重构量更新：`r_F=a_req-a_F`，其中 `a_F=(T/m)R(euler_filtered)e3-g e3`，而非真实 Plant 平动加速度。零初值下，`k2=4 s^-1`、`dt=0.001 s` 给出精确 ZOH 递推

\[
\eta_{j+1}=a\eta_j+b r_{F,j},\quad
a=e^{-0.004}=0.9960079893,\quad
b=(1-a)/4=0.0009980027\ \mathrm{s}.
\]

这一步只在 `r_F` 于该毫秒内保持时等于连续一阶滤波器的精确 ZOH 离散化。源码每步重算 `r_F` 并套用该系数。PCF 采样为1 kHz，Head 只在100 Hz事件读取当时已积累的 `eta_before`；随后完成该Plant步时写入 `eta_after`。

## 可逐项成立的命题

**命题1：PCF 条件界。** 若所有步上 `||r_F,j||∞≤R`（单位 m/s²），则由几何级数

\[
\|\eta_j\|_\infty\le a^j\|\eta_0\|_\infty+(1-a^j)R/4,
\quad\text{故 }\eta_0=0\Rightarrow\|\eta_j\|_\infty\le R/4\ \mathrm{m/s}.
\]

`R` 未由源码常量或 phase1 有限数据证明。`a_req` 依赖位置/速度误差、轨迹导数及映射前补偿；输出经过滤波、倾角/推力映射，而真实执行器和 Plant 残差不进入 `a_F` 的重构。故这个是严格的条件滤波界，不是当前 eta 的无条件数值界。无论 eta 多大，Head 实际使用的 `s_eff` 都受逐轴 `[7,8,10] m/s` 硬裁剪，因此 `||s_eff||2≤sqrt(213)=14.5945 m/s`；但未裁剪差 `s-s_eff` 没有界。

**命题2：Head 参数与输出版界。** 对任意有限 `W_n,phi_n`，代码先将三轴输出裁到 `±3 m/s²`，且 `0≤beta≤1`，故 `||u_n||∞≤3 m/s²`、`||u_n||2≤sqrt(27)=5.1962 m/s²`。这是 head 注入命令界，不是位置误差或实际 Plant 加速度界。

若初始 `W_0∈C=[-60,60]^{33×3}`，逐项投影后所有事件 `W_n∈C`，且

\[
\|W_n\|_F\le60\sqrt{99}=596.9925,\quad
\|W_{n,:,j}\|_2\le60\sqrt{33}=344.6737.
\]

在该条件下，记 Euler 方向 `G_n=-12 beta phi s_eff^T-0.002 W_n`，源码支持 `||phi||2=1`，于是

\[
\|G_n\|_F\le12\sqrt{213}+0.002(60\sqrt{99})<176.33\ \mathrm{m/s^3}.
\]

`h=0.01 s` 时单次未投影增量至多约 `1.7633 m/s²`。对任意固定 `W*∈C`，硬盒投影的非扩张性只给出

\[
\|W_{n+1}-W^*\|_F^2\le\|W_n-W^*\|_F^2
+2h\langle W_n-W^*,G_n\rangle+h^2\|G_n\|_F^2.
\]

末项的统一粗界约 `3.11 (m/s²)^2`。源码/日志没有证明交叉项为负，亦没有将它与误差面、Plant 残差和输出裁剪余项合成负漂移。初始化本身是 `kappa*W0`，投影发生在更新后；本复核未打开 checkpoint，phase1 摘要没有给出初始 `W0` 的逐项绝对最大值，所以 `W_0∈C` 仍是这条全序列参数盒界的明确前提。即使补证此前提，也只得到参数有界。

**命题3：仅作参照的理想采样外环。** 明确定义 `delta_k := a_plant,k - a_N,k`（单位 m/s²），即 Plant 实际平动加速度减去未补偿外环名义加速度。源码将 Head 力 `m u_n` 从名义力中扣除；在理想平动通道中，Head 对 `delta_k` 的直接贡献为 `-u_n`，真实风载、姿态/推力/分配偏差、Plant 错配及数值/采样误差再加到该差值中。于是 `p''=a_N+delta_k`，`e''=ddot(p_ref)-p''=-k1 de-e-k2 s-delta_k`，这固定了下式两个负号的来源。若再假设每个1 ms区间上实际位置动力学是理想双积分器、参考加速度与该总 `delta_k` 在区间内 ZOH、姿态/推力/电机/Plant映射无损，并且 `|delta_k|≤D`，源码外环 `k1=1 s^-1`、位置项系数 `1 s^-2`、`k2=4 s^-1` 可化成一个每轴采样系统。对 `e=p_ref-p`、`s=de+k1 e`，取数值 SI 标度 `z=[e;s]`，`h=0.001 s`：

\[
z_{k+1}=A_hz_k+B_h\delta_k,\quad
A_h=\begin{bmatrix}.999&.0009975\\-.001&.9959975\end{bmatrix},\quad
B_h=\begin{bmatrix}-5\cdot10^{-7}\\-.0010005\end{bmatrix}.
\]

`A_h` 的特征值约为 `0.9986196`、`0.9963779`，故此**理想模型**是 Schur；如果 `||delta_k||≤D`，则 `z_k=A_h^kz_0+ΣA_h^{k-1-i}B_h delta_i` 给出标准几何衰减加有限输入增益界。系数不替代 `D`，也没有构成部署结论：现实 runner 不满足上列理想映射假设，且没有给出 `D` 或保持该模型有效的前向不变域。把所有适配作用直接并入 `delta` 也只给条件鲁棒界，不证明 Head 自适应改善稳定性或逼近参数收敛。

## 部署定理所缺的量

- **Plant 不变域和输入范围：** 需要同时约束位置/速度误差、欧拉角/角速度、参考及其导数、臂长/臂速、相对风速和气动力/矩。`vehicle_derivative` 含姿态变换、惯量逆、陀螺耦合、时变惯量和状态相关风载；1 ms RK4 步长本身不给出离散 Lyapunov 负漂移。source-level allocator/motor clip 有限幅，但它们不限制所有状态，也不限制误差输入或气动项。
- **PCF 输入数值界：** 缺少 `R=sup ||a_req-a_F||∞` 及可审计状态域。72条记录中的最大值只能是有限航次观察量。
- **自适应余项：** 要把在线输出写成消除未知匹配项的项，须给出固定或时变目标权重的存在/范围，以及 feature 近似误差 `Q`、`s-s_eff`、beta 渐入差、输出±3裁剪差、Head 10 ms ZOH/状态同步误差的统一界。现有 target `Y` 是离线物理诊断量，不是部署输入；同态残差的重放/改进不等于上述全域近似界。
- **控制链误差：** 须将1 ms命令滤波的状态/加速度限幅、目标倾角映射、推力变化、位置/姿态反步耦合、控制端与Plant分配矩阵差、广义命令和电机饱和、风载、时变形态以及 RK4 离散误差统一约束到定理中的 `delta`，并证明闭环轨迹留在该约束域。源文件和事件重放没有这些统一数值边界。
- **离散自适应负漂移：** 必须保留 projected Euler 的 `h²||G||²` 项，并证明被适配参数误差交叉项可吸收该项及 PCF/饱和/ZOH 余项；当前只证明投影有界。未见 PE 验证，因而不声明参数收敛，也不把 PE 当事实。无需以有限日志补造 PE 或不变集。
- **历史部署对应性：** current Plant 源逐项 SHA 没有写入 frozen pair identity/run_start。若论文结论要逐字节归因于72场部署，还须补齐该 source binding；本复核不回读 MAT、checkpoint、cache 或 raw。

因此本轮只能接受：Head 输出有界；若初值在盒内则权重盒不变；PCF 若输入有统一界则 eta 有上述条件界；理想 sampled outer loop 在额外 ZOH/无损假设下 Schur。**不接受**“当前闭环已稳定”“误差有可审计数值上界”“Head 参数收敛”或以72条仿真替代这些证明。

## 直接相关原始文献

只核对了以下原始论文的官方 DOI/出版方页面，不作系统综述或宽泛的新颖性判断：

- Farrell, Polycarpou, Sharma, Dong, “Command Filtered Backstepping,” *IEEE Transactions on Automatic Control*, 54(6), 1391–1395 (2009), [IEEE/DOI](https://doi.org/10.1109/TAC.2009.2015562)。出版方记录其连续设计下的滤波影响分析与 Tikhonov 稳定性论证；它不覆盖本项目的1 ms/100 Hz projected-Euler、硬裁剪和六自由度执行器链。
- Dong et al., “Command Filtered Adaptive Backstepping,” *IEEE Transactions on Control Systems Technology*, 20(3), 566–580 (2012), [IEEE/DOI](https://doi.org/10.1109/TCST.2011.2121907)。出版方摘要给出 generalized-parameter strict-feedback 假设下运行阶段与传统 adaptive backstepping 相同的理论性质；这不是当前 Plant 的离散证明。
- Choi and Bang, “Adaptive command filtered backstepping tracking controller design for quadrotor unmanned aerial vehicle,” *Proceedings of the Institution of Mechanical Engineers, Part G*, 226(5), 483–497 (2012), [SAGE/DOI](https://doi.org/10.1177/0954410011415001)。出版方摘要涉及四旋翼约束、参数更新和饱和期间的 Lyapunov 跟踪误差修正；其具体控制器假设不可移植到当前代码。
- Ioannou and Kokotovic, “Instability analysis and improvement of robustness of adaptive control,” *Automatica*, 20(5), 583–594 (1984), [Elsevier/DOI](https://doi.org/10.1016/0005-1098(84)90009-8)。出版方摘要强调扰动/未建模动态下有条件的区域吸引和残差集；它不证明当前 `gamma=12` 的 projected Euler 更新。

这些工作表明 command-filtered/adaptive backstepping 与受限四旋翼控制已有直接先例；本复核不据此评价方法新颖性，也不把连续定理挪用为当前离散实现的保证。

## 复核命令与边界

只读复核使用 PowerShell 7：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath <逐项列出的 .m/.md/.csv/.json>
rg -n 'position_only_search_head_step|position_filter_realization_pcf_step_v3_5|rk4_vehicle_step|vehicle_derivative|allocate_control|position_bs_step' <隔离 runner、对应源码目录>
Import-Csv -Delimiter ',' reports/paper14_v2/phase1/mechanism_run_start_lineage.csv
Import-Csv -Delimiter ',' reports/paper14_v2/phase1/mechanism_components_by_scene.csv
Get-Content reports/paper14_v2/phase1/mechanism_audit.md
Get-Content reports/paper14_v2/phase1/theory_and_literature.md
```

没有运行 MATLAB、Plant、训练或测试；没有打开/解封 TEST；没有读取或改动 MAT、checkpoint、cache、raw；本次只新增本报告。工具未提供模型推理速度读取/切换接口；未启用 Fast 专用工具，实际服务速度档无法本地独立核验。
