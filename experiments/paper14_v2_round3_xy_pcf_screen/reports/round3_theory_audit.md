# R3 `[1,1,0]` eta mask 理论复核

**审计者：** GPT-6-Luna xhigh（独立理论/证据复核）  
**结论：理论验收未通过/待补证。**  
**范围：** 复核冻结 R3 任务书中的 `[1,1,0]` eta mask 数学定义，并将其与冻结 R2 锁定运行链中的 Head、PCF、双时钟和 Plant 方程对应。证明限于这些方程直接蕴含的结论。此报告不审计 R3 新生成运行代码是否逐行实现任务书定义；部署一致性仍须由实现审查确认。

## 1. 结论摘要

当前可严格陈述的结果有三类：

1. **同输入等价：** 在给定相同的 surface、eta、feature、beta、初始权重和逐列投影条件下，mask 的 x/y 列更新与全量 PCF-on 相同，z 列更新与 PCF-off 相同。该结论是输入相同条件下的代数/递推恒等式，不代表两个闭环运行会保持相同输入。
2. **PCF 条件滤波界：** 若 PCF 滤波输入残差逐步有界，可由实际离散递推得到 eta 的指数加权界。代码与任务书没有给出该残差在闭环运行中的统一上界，故不能将条件界升级为无条件数值界。
3. **参数与命令有界：** 每次 Head 更新后的逐元素投影将权重限制在指定盒内；Head 输出裁剪限制注入加速度命令。它们不蕴含跟踪误差有界、闭环 ISS/UUB 或参数收敛。

尚不能证明：六自由度闭环 ISS/UUB、H3 改善方向或改善幅度、DSSM 参数收敛。有限仿真场景、权重投影有界以及 eta mask 的代数结构都不能填补闭环 Lyapunov 漂移、Plant 残差界和持久激励等缺失条件。

## 2. 部署方程和时序对应

以下符号按锁定 R2 方程整理：n 表示 100 Hz Head 事件，j 表示 1 kHz Plant/PCF 步。Head 每 10 ms 更新一次；其输出在两个事件之间零阶保持。Plant 与 PCF 每 1 ms 更新。

### 2.1 位置面、DSSM 特征与 Head

在 Head 事件，运行器先用零残差预览位置滑模步。锁定实现中的面量可写为

\[
e_n=p_{d,n}-p_n,\quad \dot e_n=v_{d,n}-v_n,\quad
s_n=\dot e_n+k_1e_n,\quad k_1=1,
\]

名义加速度为

\[
a_{nom,n}=a_{d,n}+k_1\dot e_n+e_n+k_2s_n,\qquad k_2=4.
\]

DSSM 前向使用 14 维状态窗口（最多 32 个事件），逐事件重放其隐藏状态；输出特征记作 \(\phi_n\)。实现将隐藏特征与常数项归一化为 \(\phi_n=[h_n;1]/\sqrt{1+\|h_n\|_2^2}\)，故 \(\|\phi_n\|_2=1\)。上下文准备完成前的 beta ramp 为 \(\beta_n=\operatorname{clip}(t_n/1.8,0,1)\)。这里的单位、窗口重放和 ramp 都是离散实现的一部分，不能被视作连续时间自适应律。

令逐坐标裁剪为 \(C_L(x)_i=\operatorname{clip}(x_i,-L_i,L_i)\)，其中 \(L=(7,8,10)\)。R2 FEATURE Head 使用 output-then-update：

\[
u_n=\beta_n C_{d}(W_n^T\phi_n),\quad d=(3,3,3),
\]

\[
W_{n+1}=\Pi_{[-60,60]}\left(W_n+h[ -\gamma\beta_n\phi_n s_{eff,n}^{T}-\sigma W_n]\right),
\]

其中 \(h=0.01\) s、\(\gamma=12\)、\(\sigma=0.002\)，\(\Pi\) 是逐元素盒投影。当前事件输出使用更新前的 \(W_n\)，更新后的权重最早影响下一次事件输出。

任务书中的 mask 定义为

\[
M=\operatorname{diag}(1,1,0),\quad
\eta_{eff,n}=M\eta_n,\quad
s_{eff,n}=C_L(s_n-M\eta_n).
\]

这一操作只改 Head 权重更新的 surface 输入。PCF 的 eta 状态本身仍按三轴递推；没有从此 mask 推出 eta_z 恒为零。

### 2.2 PCF 及其 1 kHz 离散递推

锁定实现每个 1 ms Plant 步重构由当前滤波姿态和推力产生的加速度：

\[
a_{F,j}=\frac{T_j}{m}R(\theta_{F,j})e_3-ge_3,\quad
r_{F,j}=a_{requested,j}-a_{F,j}.
\]

eta 是该命令重构残差的滤波状态，不是实测 Plant 加速度误差。实现中的离散滤波式为

\[
\eta_{j+1}=a\eta_j+b r_{F,j},\quad
a=e^{-k_2\Delta t},\quad b=\frac{1-e^{-k_2\Delta t}}{k_2},
\]

其中 \(k_2=4\,s^{-1}\)、\(\Delta t=0.001\,s\)，所以

\[
a=0.9960079893439915,\qquad b=0.000998002664002129\,s.
\]

Head 事件读取的是该事件入口的 eta；其后 eta 仍每个 1 ms 前进。一个 10 ms Head 间隔的自由滤波系数是 \(a^{10}=e^{-0.04}=0.9607894391523232\)，对应输入权重和为 \(b(1-a^{10})/(1-a)=(1-a^{10})/4=0.009802640211919206\,s\)。这不等于一个只在 100 Hz 更新的 eta 递推：10 个 1 ms 残差样本会分别进入滤波。

### 2.3 从 Head 到 Plant 的耦合

Head 残差加速度命令经基线力到姿态映射变成推力和姿态请求；姿态/命令滤波以 1 ms 步更新，并存在姿态倾角、角加速度、分配广义力矩及电机速度等限幅。六自由度 Plant 以 1 ms RK4 步积分，包含姿态旋转、角动量/陀螺项、形态变化引起的惯量项及二次风载。Head 注入命令在 100 Hz 更新、10 ms ZOH；PCF、命令滤波和 Plant 在 1 kHz 更新。限幅、滤波延迟、姿态到力的非线性映射及 Plant 积分误差都会使实际闭环不等同于只含 \(s_n\) 和 \(\eta_n\) 的 Head 更新式。

## 3. 可证明结论及证明边界

### 3.1 mask 的同输入列等价

记 \(v_M=C_L(s-M\eta)\)、\(v_{on}=C_L(s-\eta)\)、\(v_{off}=C_L(s)\)。对完全相同的给定 \(s,\eta\)，逐坐标裁剪立即给出

\[
(v_M)_x=(v_{on})_x,\quad (v_M)_y=(v_{on})_y,\quad (v_M)_z=(v_{off})_z.
\]

若两组递推还具有相同的 \(\phi_n,\beta_n,W_0\)，且投影逐元素进行，则权重更新按列分离：第 \(i\) 列的梯度只含 \((s_{eff})_i\)，泄漏与投影也不跨列。因此归纳可得每个事件的 \(W_{M,n}[:,x/y]=W_{on,n}[:,x/y]\)，以及 \(W_{M,n}[:,z]=W_{off,n}[:,z]\)。这是精确的**共同输入重放**结论。

本结论的关键假设是 surface、eta、特征、beta 和初始权重共同相同。实际闭环中，任一轴的输出经姿态/推力与 Plant 耦合后都可能改变全维状态窗口，因而改变后续 \(s,\eta,\phi\)。共同输入条件一旦失效，归纳即不再适用。由于 output-then-update，mask 不改变事件 \(n\) 已产生的 \(u_n\)；在相同初态/相同前序输入的确定性重放下，首次可能不同的是更新后权重对下一事件输出的影响。

另外，\(C_L\) 是 1-Lipschitz 且有界。由此无条件有

\[
\|v_M\|_2\le\sqrt{7^2+8^2+10^2}=\sqrt{213}=14.5945195193,
\]

\[
|(v_M-v_{on})_z|\le\min(|\eta_z|,20),\quad
|(v_M-v_{off})_x|\le\min(|\eta_x|,14),\quad
|(v_M-v_{off})_y|\le\min(|\eta_y|,16).
\]

这些是 update 输入的界，不是 tracking error 或加速度残差界。

### 3.2 PCF eta 的条件滤波界

若另行假设对所考虑的全部 Plant 步 \(\|r_{F,j}\|_\infty\le R\)，递推的精确解为

\[
\eta_j=a^j\eta_0+b\sum_{i=0}^{j-1}a^{j-1-i}r_{F,i}.
\]

故

\[
\|\eta_j\|_\infty\le a^j\|\eta_0\|_\infty+\frac{R}{4}(1-a^j).
\]

在 \(\eta_0=0\) 时可得条件界 \(\|\eta_j\|_\infty\le R/4\)。这是有实际数值系数的离散滤波 ISS 界，但前提是统一的残差上界 \(R\) 已知。锁定源码和任务书未提供闭环全时域的 \(R\)，因为 \(a_{requested}\) 受跟踪误差、参考加速度和 Head 输出影响，\(a_F\) 又受限幅姿态、推力与状态影响。因此报告不声称存在数值化、无条件 eta 界。mask 不改变 eta 方程；但两条闭环轨迹一旦分离，二者的 \(r_F\) 也可能不同。

### 3.3 投影权重界与 Head 命令界

每次实际执行投影后都有 \(W_{n+1}\in[-60,60]^{33\times3}\)，不论投影前梯度多大。若初始化在盒内，则此界从初值起成立；当前审计没有打开 checkpoint，故不确认初始化是否在盒内，也不能将“首个投影后”说成全程初值界。投影后可得

\[
\|W\|_F\le60\sqrt{99}=596.9924623,\qquad
\|W[:,i]\|_2\le60\sqrt{33}=344.6737588.
\]

输出裁剪给出 \(\|u_n\|_\infty\le3\) 与 \(\|u_n\|_2\le\sqrt{27}=5.1961524\)。这是 Head 残差加速度命令的限幅，不是实际加速度、跟踪误差或总控制力的同一界。

即使 \(\|\phi_n\|_2=1\)、\(\|s_{eff,n}\|_2\le\sqrt{213}\)，更新也包含投影。投影的非扩张性可给出相对于任意盒内 \(W^*\) 的一步上界

\[
\|W_{n+1}-W^*\|_F^2\le\|W_n-W^*\|_F^2
+2h\langle W_n-W^*,G_n\rangle+h^2\|G_n\|_F^2,
\]

其中 \(G_n=-\gamma\beta_n\phi_ns_{eff,n}^T-\sigma W_n\)。利用盒内 \(W_n\) 得 \(\|G_n\|_F\le12\sqrt{213}+0.002(60\sqrt{99})=176.3282192\)，故二次项至多 \(3.1091641\)。但交叉项没有已证的非正性或可吸收性；所以该式没有给出权重误差收敛，投影有界本身也不是闭环稳定性证明。

在**同输入**情形，mask 与 PCF-on 的 z 列差 \(D_n\) 还满足

\[
D_{n+1}\le(1-h\sigma)D_n+h\gamma\beta_n\min(|\eta_{z,n}|,20),\quad 1-h\sigma=0.99998,
\]

因而

\[
D_N\le(1-h\sigma)^ND_0+h\gamma\sum_{i=0}^{N-1}(1-h\sigma)^{N-1-i}\beta_i\min(|\eta_{z,i}|,20).
\]

这是带投影、泄漏的权重差上界，仍依赖共同特征/共同输入。它没有闭环跟踪含义；实际 z 权重差还受全维特征反馈影响。

## 4. 闭环主张的断点

**六自由度 ISS/UUB。** 要得到 tracking ISS/UUB，至少需要对包含位置/速度误差、姿态和角速度、推力/执行器滤波状态、eta、Head 权重及 DSSM 特征窗口的增广离散闭环映射建立 Lyapunov 漂移不等式，或建立可验证的不变紧集并证明其中的收缩/扰动增益。当前只有局部模块方程和命令/参数限幅，没有该增广系统的漂移不等式，也没有全局或任务域不变集。Plant 的 RK4 采样本身不提供 Lyapunov 下降；姿态和执行器饱和可能破坏基于未饱和连续控制律的抵消关系。

**H3 改善方向/幅度。** 同输入恒等式说明 mask 仅将 x/y 更新输入设为 PCF-on、z 更新输入设为 PCF-off。它没有符号保证表明 z 误差下降、x/y 不恶化或总性能改善。由于姿态、推力、饱和和 DSSM 输入窗口耦合，某轴残差更新变化会反馈到其他轴；从当前方程无法推出 H3 的符号结论或定量效应量。

**参数收敛。** 投影盒只给权重有界。参数收敛还需至少指定可实现的目标参数/残差结构、噪声与离散化误差界、适用于闭环 feature 序列的可辨识/持久激励条件，以及投影边界与目标参数的关系。现有审计未验证 PE，也没有从有限仿真场景证明 PE；因此不能声称参数收敛、收敛率或辨识出物理参数。

**离散项、限幅和双时钟。** 若用连续时间定理近似部署链，需要将 100 Hz Head 的 ZOH、1 kHz eta/命令滤波/Plant 更新、output-then-update、DSSM 窗口重放与 beta ramp、RK4 局部截断误差、姿态/执行器/分配限幅及其导致的控制残差全部纳入界。当前无这些误差项的统一上界，也无执行器未饱和/控制可行性证明。有限场景和有限时长的观测不是适用于整个仿真域的状态或残差上界。

## 5. 最小补证要求

如需把理论门槛提升到闭环误差结论，最低限度还需：

1. 证明任务域内增广状态的正向不变性，或给出可审计的状态、参考、风载、形态变化、滤波及执行器状态统一界；由此导出每个 1 ms 的 \(r_F\) 界。
2. 针对实际离散、含投影和全部饱和的增广映射，证明明确的 ISS/UUB 漂移不等式，并列出 ZOH、RK4 和限幅残差在增益中的位置；或者明确声明定理只适用未饱和且满足另列可验证条件的子域。
3. 将同输入掩码递推与真实闭环递推区分；定量处理 feature 因全维状态分离而变化带来的误差传播。
4. 若主张参数收敛，另行证明相应 feature 回归量的 PE/可辨识性及逼近误差条件；若主张 H3 改善，还需有能证明该方向的比较定理或充分条件，不能从 mask 定义推断。
5. 核对 R3 实际运行代码确实按任务书 mask 只改 Head 更新输入，且更新顺序、投影坐标、ZOH 和 PCF 状态与本报告的方程一致。该实现符合性未由本报告审核。

## 6. 审计范围、文件身份与复核边界

SHA-256 记录如下。R2 锁内 31 个 runtime/Plant 条目均逐项与冻结锁清单一致；表列出与本推导直接相关的条目。所有 hash 均为文件身份核对，不代表运行或复现。

| 文件 | SHA-256 |
|---|---|
| R3 `TASKBOOK_ZH.md` | `a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a` |
| R2 `frozen_runtime_lock.json` | `92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58` |
| `run_dl1018_closed_loop.m` | `01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b` |
| `position_stage1_model_forward_v2.m` | `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676` |
| `position_only_search_head_step.m` | `3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc` |
| `position_only_search_options.m` | `4e8322934ddb524961fa762426800564f6c758e00b943b622c9143ed734f19bf` |
| `position_filter_realization_pcf_step_v3_5.m` | `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0` |
| `run_episode_dl1018.m` | `fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330` |
| `rbf_event_scheduler_step.m` | `cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618` |
| `position_bs_step.m` | `ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681` |
| `baseline_force_to_attitude.m` | `ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039` |
| `command_filter_step.m` | `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b` |
| `allocate_control.m` | `5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53` |
| `rk4_vehicle_step.m` | `7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5` |
| `vehicle_derivative.m` | `c3258dd5b70268d1465ca7701855b065244aebfaf5816c85e959d39015cd2786` |
| `morphology_aware_wind_load.m` | `51459cd2c09f1181e85bbee8f89ddbd75bd2ba923f1aebacbdd1ecfe7b3ba5ac` |
| `simulation_parameters.m` | `962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae` |
| `theory_and_literature.md` | `8d1f7e7793e0f92c19a5bda3d5024c46d3aa358a3fb71e5d67200f53a01f361b` |
| `discrete_theory_second_review.md` | `2b8cbffe6503b6c00347d4865ceadc8239e4dee8c7c66d93f85ace01406783d4` |

先前理论/文献审计被用于避免将连续、自适应或独立四旋翼控制器结果直接移植到此离散 DSSM/PCF/六自由度部署链；本报告没有新增文献主张。复核限于冻结任务书、冻结锁清单、锁定源码和既有理论报告的静态读取/哈希核对。未运行 MATLAB、Plant、航次、训练、预检或 scorer；未打开 TEST、MAT 内容、checkpoint、cache 或 raw 数据；未修改源码、任务书、锁、账本或既有报告。本报告为唯一新增文件。

## 7. 验收判断

**理论验收未通过/待补证。** 当前充分支持的是同输入 mask 列等价、条件 PCF 滤波界、Head 输出限幅和投影后权重盒界。闭环 ISS/UUB、H3 改善方向/幅度与参数收敛均没有从已锁定的离散部署方程得到证明；在补齐上一节的假设和逐项证明前，不应将这些主张写作已证理论结论。
