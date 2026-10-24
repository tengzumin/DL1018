# C5 控制路径与位置响应分解源码审计

审计结论：位置补偿 \(u\) 到外环期望加速度的输入系数精确为 \(-I\)；从期望加速度到本样本 PCF 实际加速度 \(a_f\) 的映射经过推力方向、姿态滤波和限幅，瞬时局部灵敏度通常不是单位阵。这表明实现是带采样延迟的级联近似，不能把外环的 \(\phi s\) 梯度直接解释为实际闭环加速度灵敏度；仅凭此差异也不能判定控制器有 bug，或断言连续推导已经被代码违反。

## 路径及时序

matlab/core/position_bs_step.m 第24–27、49–59行先形成名义加速度，再以 commandedForce = nominalForce - residualForce 得到 commanded_acceleration = commandedForce / mass。因此令已施加补偿为 \(u\)，同一状态下 \(a_{\rm req}=a_{\rm nom}-u\)，有 \(\partial a_{\rm req}/\partial u=-I\)。

experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m 第2118–2138、2155、2237–2262行显示：事件输出被保持后交给位置反步；随后 baseline_force_to_attitude 从期望加速度计算推力与倾角目标，command_filter_step 推进姿态滤波，PCF helper 计算本样本 \(a_f,r_f\) 与下一 \(\eta\)。command_filter_step 将旧滤波姿态放入本样本 reference.euler，再更新 nextState（matlab/core/command_filter_step.m 第18–24行），所以倾角目标变化先影响下一样本滤波姿态；本样本推力幅值仍会变化。

固定当前滤波姿态 \(\theta_f\)，记 \(f=a_{\rm req}+g e_3\)、\(q=R(\theta_f)e_3\)，则
\[
a_f=\|f\|q-ge_3,\qquad
\frac{\partial a_f}{\partial a_{\rm req}}=\frac{qf^\top}{\|f\|},\qquad
\frac{\partial a_f}{\partial u}=-\frac{qf^\top}{\|f\|}.
\]
该矩阵通常为秩一；在 \(\|f\|=0\) 处不可微，倾角或加速度限幅处则分段变化。matlab/models/position_filter_realization_pcf_step_v3_5.m 第9–21行实现 \(a_f=(T/m)Re_3-ge_3\)、\(r_f=a_{\rm req}-a_f\) 和精确指数 \(\eta\) 更新。非单位瞬时灵敏度限定了外环梯度映射到实际响应时所需的级联、滤波与未饱和假设，不单独证明错误。

Plant 每个 1 ms 转移使用 matlab/core/rk4_vehicle_step.m 第12–18行的经典 RK4，当前输入在四个导数求值中保持不变。日志 state 与参考含20,001个端点；transition_time、PCF与held-command字段对应20,000个左端转移。计分使用状态索引0–19,999，索引20,000只用于末端递推核对。

## 日志覆盖与最小诊断

DEV日志包含每步 filtered_attitude_reference、filtered_attitude_rate、目标角、请求及实际角加速度（run_dl1018_closed_loop.m 第2693–2696行），也包含PCF的 a_req、a_f、r_f、eta 前后值（第2876–2880行）。内部样本可还原旧滤波状态与PCF状态，并从同状态重算命令映射。最后一次滤波更新后的状态没有独立终端滤波状态行；RK4四个子步的中间Plant状态也未记入日志。日志没有直接给出 \(u\mapsto a_f\) 的有限差分灵敏度。

若后续确需量化，可固定内部样本 \(k\) 的Plant状态、参考、旧滤波状态与 \(\eta_k\)，分别对三个轴的 \(u_k\) 加减小扰动；每次重算 position_bs_step → baseline_force_to_attitude → command_filter_step → PCF，记录 \(a_{\rm req}\)、倾角目标、滤波下一状态、当步 \(a_f,r_f,\eta_{k+1}\)，并标记限幅状态。为观察滤波滞后一拍，可在 \(k+1\) 冻结实际下一Plant状态与参考，沿用扰动后滤波状态再算一次；不推进Plant。这个局部映射不能单独证明位置误差的闭环因果变化，也不代替轨迹扰动实验。

## 既有核验与响应Gram准备

ACTUAL_PHYSICAL_BRIDGE_DEV72_CHECK_v1.json 已对72条现有C5路径核对请求加速度、离散 \(e,\sigma\) 递推、held输出及F强迫项分解。最大残差分别为 \(8.88\times10^{-16}\)、\(1.39\times10^{-17}\)、\(2.36\times10^{-16}\)、\(6.66\times10^{-16}\)、\(8.88\times10^{-16}\)。这是双精度数值恒等式核验，不是区间认证、稳定性证明或因果消融。

dev_physical_response_decomposition_v1/full72_response_gram_v1.py 准备将初值、采样余项、pre-ready/tail、F四项经固定 \(A\) 递推，并输出逐轴、0–5/5–20秒、逐场及分组全交叉Gram。脚本同时设置补偿输出与 beta·clip(z)、F项与实际 u-d0、以及 e/sigma 重构的残差失败门。

F1=beta(z-y) 与 F2=beta y-dM 中的 y 会代数消去，单独能量取决于目标拆分方式。因此脚本另报 epsilonM=F1+F2+F3、epsilonM+F4及两者交叉项；应按完整Gram和分组响应读数，不能从F1/F2单通道能量推断可修复瓶颈。该分析只描述冻结C5路径上的线性响应恒等式，不是新方法、因果归因或候选优劣评估。

根对准备脚本启动过一次OS1；该版已读取并计算前24个DEV raw，随后在首个VAL场路径超出单一DATA_ROOT白名单处失败；该VAL raw内容未被读取，未产生完整72场分析结果。该v1保留，根将另行制作允许DEV72与原C5根目录的隔离v2。此次源码审计未读取TEST、启动Plant或训练。

## 输入与源码身份

- 父审核清单 C5_DEV72_RAW_PARENT_REVIEW_v3.json：SHA256 bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab。
- 既有检查器 check_actual_physical_bridge_dev72_v1.py：SHA256 403deab9f7b096ca118ba2de65c7b60df9ce772638d30ca7b77c57f310d75194；结果JSON SHA256 381685296211cbdaf16dafe6e5593711abeb17d6764a11703d09f143d5d91c2c。
- 单场通道计算参考 parent_response_pilot_v1/pilot.py：SHA256 504daa88eb891ddac4f54f66e3f9fc085a3891f67e27366a93b900b3c8e74ed4；T1_C00_W03单场重构已由根审核。
- 响应Gram脚本 full72_response_gram_v1.py：SHA256 96dcd838784551b672080de40cd0b3d39826ed299a7b653c1276eb6a089071ad；已通过Python AST静态解析。v1当前路径门失败，不能作为72场结果。
- 控制源码 SHA256：run_dl1018_closed_loop.m 48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c；position_bs_step.m ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681；baseline_force_to_attitude.m ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039；command_filter_step.m 15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b；position_filter_realization_pcf_step_v3_5.m b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0；rk4_vehicle_step.m 7e10a8c77b2740f2f9f222f3b06c6c021cb3a9342070ad7f3ebaba3c47395ef5。
