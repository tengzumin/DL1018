# 方法替代方案审查 v1

日期：2026-10-28。只读审查指定的 C5 lineage audit、root 状态、full72 WN18 原始 59 控制源和现有 DEV/VAL raw；未改控制源码、未运行 Plant/TEST、未使用惯量重建或惯量真值输入。下列几何数字是开发集诊断，不是闭环结论。

## 审查结论

当前任务姿态落后不等于“姿态内环追踪差”，也不能由换评分解释。正式目标是 HF task SO(3) 不差于 B，同时在匹配 cohort 保留接近 C5 的位置收益（FULL72 B=17.058 mm、C5=11.559 mm，C5 优势 32.24%）。现有 GRU 双环位置约 11.129 mm，但 WN18 HF task=61.199 mrad 对 B=57.619 mrad。

源代码把位置控制目标、滤波器内部参考和任务评价参考分开了：位置 BS 用轨迹加速度加位置/速度反馈，再减位置残差，形成 `commanded_force`（`position_bs_step.m:24-49`）；力方向适配器把该加速度与偏航转为推力/滚转/俯仰（`baseline_force_to_attitude.m:15-23`）；活动路径将其 RP 与任务 yaw 拼成滤波器目标，命令滤波器输出内环参考（`run_mlp15_dev72_closed_loop.m:2384-2395`）；姿态分数则把实际姿态与从 `reference.acceleration + yaw + gravity + 30° tilt cap` 重建的任务姿态比较（`score_full72_candidate_v1.py:116-141,526-527`）。因此 GRU 只追滤波参考，并不直接最小化 task SO(3)；反过来，直接追任务角会改动外环所依赖的推力方向。

四旋翼平动方程是 `a = T R e3 / m - g e3 + F_ext/m`（`vehicle_derivative.m:31`）。给定外环所需加速度和推力大小，严格力闭合固定了机体推力轴；在固定 yaw 下，RP 没有额外自由度。风/气动外力要求的倾斜与轨迹任务角可能冲突，但这是有限误差预算下的 Pareto 问题，不能据此判“不可能”。

已有因子试验符合此耦合预期：GRU全局位置补偿缩放0.9时，HF task从61.199改善到60.303mrad，但Q从10.141恶化到11.717mm；将预测时间常数tau=1s改为0.1s时，HF task=59.610mrad仍差于B的57.619mrad，Q=12.175mm也高于父方法10.141mm。WN12把滤波频率整体降到[12,12,12]后，HF task仍为58.566mrad且Q宏平均增加2.476mm；另有单场实测姿态PCF将Q从9.621推至29.971mm、task几乎不变。统一降频、整体削弱位置补偿和直接以实测姿态替代PCF状态均已不支持。

## 原始力闭合预算扫描

数据：full72 WN18 同一六个 HF_W09_W14 DEV/VAL raw。重建任务姿态按评分器冻结定义。对每个 1 ms transition 取 `F_req=[position_commanded_force_N + m g e3]`、`T=allocated_generalized(1)`，分别用滤波参考和实测姿态算 `epsilon=||F_req - T R e3||/m`。没有读取 raw 中的风力字段。这里逐点 epsilon 是从 parent WN18 raw 事后算出的原轨迹预算，属于离线 oracle/反事实诊断；它不能作为候选控制器的未来输入。解析可行锥半角为 `delta=acos((T^2+||F_req||^2-(m epsilon)^2)/(2T||F_req||))`；将任务推力轴投影到该球冠、固定任务 yaw 反解姿态，得忽略速率、力矩、最大倾角、滤波动态和跨步 PCF/位置状态的逐点 task RMSE 乐观下限。

| HF scene | filtered 指令闭合 RMS/P95 (m/s²) | 实测姿态闭合 RMS/P95 (m/s²) | task 对实际姿态 RMSE (mrad) | task轴在原预算内可行比例：指令/实测 | 点态 task RMSE 下限：指令/实测预算 (mrad) |
|---|---:|---:|---:|---:|---:|
| DEV T1 C10 W09 | 0.259 / 0.485 | 0.335 / 0.689 | 43.31 | 25.4% / 30.4% | 31.26 / 28.33 |
| VAL T1 C07 W14 | 0.798 / 1.433 | 0.836 / 1.504 | 67.21 | 39.0% / 37.4% | 45.05 / 38.54 |
| DEV T2 C09 W10 | 0.736 / 1.376 | 0.763 / 1.438 | 73.06 | 33.8% / 34.7% | 47.18 / 44.11 |
| VAL T2 C04 W14 | 0.711 / 1.275 | 0.719 / 1.280 | 57.54 | 40.9% / 40.9% | 31.66 / 31.61 |
| DEV T3 C09 W09 | 0.334 / 0.616 | 0.352 / 0.620 | 60.66 | 20.6% / 22.0% | 42.95 / 41.87 |
| VAL T3 C01 W14 | 0.780 / 1.384 | 0.802 / 1.406 | 65.42 | 39.2% / 39.3% | 38.77 / 35.49 |

解释：零闭合预算时，task→外环命令 RMSE 为 47.28–100.39 mrad，说明任务角通常不是严格外环力解。若逐点允许当前滤波/实测姿态本已承受的力误差，task 推力轴在约 21–41% 的采样可直接进入原预算，其他时间取锥边界的理想下限约 28–47 mrad。它证明“没有可用空间”过强；但这是逐样本把父方法的事后闭合误差用满，不能作为部署预算、可达收益或 Q 预测。点态下限也忽略姿态变化率、GRU 动态、PCF 状态累积和位置误差积分。

仅作物理解释的外力反算也可做：用相同六场、`m=.695 kg`、实际 thrust/姿态和 10 ms velocity increment，算 `F_res=m*(Δv/Δt+g e3)-mean(T R e3)`；不读取 `wind_force_I`/环境风输入。六场净外力 RMS 为 0.328–0.531 N；按 `m(a_ref+g)-F_res` 反算的力方向相对任务名义力方向偏 2.43–4.44° RMS（中位 2.30–3.27°，P90最高 7.76°）。这是风载与其他未建模外力的合成残差，不能叫纯风真值；只说明固定轨迹角可能需要偏转来维持平动。

## 候选方法与优先级

1. **首选：位置闭合约束下的 task-aware causal reference governor。** 在生成 attitude filter target 时，把 task 姿态作为次级目标：只允许目标沿当前推力大小、外环 `F_req` 与闭合误差预算构成的球冠朝任务角移动；扫描使用的逐点父轨迹预算不得在运行时读取。候选只能用当步因果可算的 `||F_req−T R(e_filter)e3||/m`，或在 TRAIN 阶段预先锁定一个闭合阈值；以当前 filter Euler/rate 做一阶命令滤波预演，投影后仍受同一固定阈值约束。只新增一个目标生成机制，不直接叠 task torque，不改 C5 DSSM14/M110/PCF、WN18 [18,18,12]、GRU/在线 tracking head、或固定 J0。运行时只需已有因果量：trajectory acceleration/yaw、position BS commanded force、issued thrust、当前 filter Euler/rate、PCF eta；不需风 oracle、Plant 真值或惯量输入。闭合预算只可用当前信号因果计算或在训练集预先固定，绝不可暗用 parent raw 的未来残差。PCF 继续使用实际发出的 thrust 和改后滤波 Euler 计算 `a_f`、`r_f=a_req-a_f`，因此保持命令侧闭合一致。先用原始序列离线推进同一个 WN18 filter+PCF，检查实际可产生的 task 角变化、PCF eta/残差峰值和输入限幅，再由 root 决定单场 pilot。单因素证伪：若通过滤波后的目标变化不足以把单场 task RMSE 推到 B 门槛附近，或 PCF residual/位置 Q 超过预注册预算，则拒绝，不调参。它不同于固定 beta 插值；固定 beta HF28 记录的 9 次 attempt 均 FAILED_NO_RETRY，性能结论未形成。

2. **命令滤波误差补偿。** 经典 command-filtered backstepping 在递推控制中显式补偿 filter error；本项目 PCF 处理的是位置侧滤波加速度误差，不等于 task 对内环参考误差的补偿。[Farrell et al., *Command Filtered Backstepping*, IEEE TAC 2009](https://doi.org/10.1109/TAC.2009.2015562)。可作 governor 的后续实现参考，不能先把 WN 降低当作补偿。已测 WN12 单因素只让 HF task 改善 2.633 mrad，但 Q 增加 2.476 mm，12/12 场位置变差。

3. **优先级 MPC / 参考整形。** 如果点态 governor 通过但 filter/PCF 时域耦合使 Q 恶化，下一步可在短预测窗先约束位置加速度/误差预算，再最小化 task SO(3)，不要固定权重 blend。层级 MPC 对冲突任务可硬性保留高优先级约束，但已引文工作是异构多机器人模拟，不是本机型结果；quadrotor LMPC 工作可作实现参考。[De Benedittis et al., IEEE RA-L 2025](https://doi.org/10.1109/LRA.2025.3559843)；[Li, Tunchez & Loianno, ICRA 2022](https://doi.org/10.1109/ICRA46639.2022.9812077)。这是更重的第二选择。

4. **频率选择 / 双环迭代学习。** 当前 WN18 的位置学习 100 Hz、姿态 tracking 200 Hz 已有双环，但两者目标并不一致；相比统一改频率，可保留低频位置抗风分量，只在重复轨迹中学习高频 task 残差/相位项，并经闭环力预算过滤。限定：ILC 需要任务和扰动可重复，不能直接推广到本开发集所有风场。[Hehn & D’Andrea, *A frequency domain iterative learning algorithm for high-performance, periodic quadrocopter maneuvers*, Mechatronics 2014](https://doi.org/10.1016/j.mechatronics.2014.09.013)。同迹线低通和 WN12 结果都不是新闭环性能证据。

## 必要独立评估

当前 GRU 用 DEV24+VAL48 训练，DEV/VAL 都已参与开发或筛选。任何目标选择/阈值冻结后，须用未参与训练、筛选的全新匹配场景，配对 B 和 C5；独立报告 HF task SO(3) 是否不差于 B、全 cohort 位置优势是否仍接近约 32%、以及 PCF/安全计数。不得在独立 cohort 上回调 governor 预算。TEST 仍封存；新候选不使用惯量估计或 Plant 真值输入。

## Filter + PCF 顺序复放与一步门控审计

可复现脚本：[offline_governor_replay_devhf6.py](offline_governor_replay_devhf6.py)；逐场输出：[FILTER_PCF_GOVERNOR_DEVHF6_v1.json](FILTER_PCF_GOVERNOR_DEVHF6_v1.json)。只读取 full72 的指定 DEV/VAL 原始场景字段，没有访问 TEST、风力数据或 Plant。复放严格按源码顺序：本行滤波输出是旧 Euler/rate，PCF 用该输出、本行 a_req 和推力更新 eta；本行新 target 只推进滤波器下一状态。任务参考按冻结评分器从 reference.acceleration + yaw 重建，六场参考加速度并非零：T1/T2/T3 的 RMS 分别为 0.526/0.616/0.331 m/s²，参考姿态倾角 P95 为 5.41/7.50/2.69°。

基线顺序复放对 21 个父 GRU DEV 场景和 6 个 HF6 场景的滤波参考、rate、PCF a_f/r_f/eta 最大绝对差为 1.72e-13。固定闭合预算取 21 个其他 DEV 父 GRU raw 全部 transition 的 ||r_f|| pooled P95：ε=1.07273 m/s²。这 21 场与 HF6 的具体 scene ID 不重叠，未用三场 VAL；但使用的是父 GRU DEV，不是 C5 TRAIN，且其他 T1/T2/T3 记录复用了相同轨迹参考。目标 HF6 已知，因此这是开发诊断阈值，不是独立训练校准或预注册安全边界。它不按时间读取 parent 未来误差；Governor 每步只用当前 a_req、当前 measured yaw、当前轨迹加速度/yaw、滤波状态和固定 ε。

| 场景 | Filter 输出对任务姿态误差 P95：原→Governor | task 权重均值 / 无可行点回退 | 闭合残差 P95 (m/s²)：原→Governor | Governor 当前残差超 ε |
|---|---:|---:|---:|---:|
| DEV T1 C10 W09 | 4.17→0.56° | 0.997 / 0.3% | 0.485→0.847 | 0.3% |
| VAL T1 C07 W14 | 7.47→5.00° | 0.809 / 19.1% | 1.433→1.585 | 19.4% |
| DEV T2 C09 W10 | 7.56→4.87° | 0.843 / 15.7% | 1.376→1.396 | 15.9% |
| VAL T2 C04 W14 | 5.29→3.50° | 0.864 / 13.6% | 1.275→1.396 | 13.8% |
| DEV T3 C09 W09 | 4.98→0.89° | 0.978 / 2.2% | 0.616→1.031 | 2.3% |
| VAL T3 C01 W14 | 6.39→4.46° | 0.830 / 16.9% | 1.384→1.500 | 17.2% |

任务误差是 **滤波参考相对 task SO(3) 参考**，不是实际姿态评分；六场的 P95 都下降，但闭合残差六场都上升。PCF eta 与原基线差的 RMS 为 0.077–0.136 m/s，命令倾角峰值 ≤19.1°、滤波参考峰值 ≤13.3°，没有角加速度限幅触发。解析力锥在固定 ε 下包含 task 推力轴的比例为 70.7–99.4%，说明当前采样有静态方向空间；它忽略滤波动态和跨步位置误差，不能推出 Q 或闭环位置收益。

这个一步门控不够早：目标差在六场 P95 约 4.9–8.6°，但由于 dt=1 ms、wn=18 rad/s，一个采样后滤波输出相对原 position target 仅偏 0.0016–0.0028° P95，最大 0.0041°。未限幅局部模型给出 Δe_next ≈ wn² dt² Δtarget，增益仅 0.000324；反复更新后整条轨迹的滤波参考 P95 移位增至 3.37–4.59°。因此目标机制非零，但一步闭合预测几乎不约束当步 PCF；下一个样本的外环 a_req 也会改变，实际超 ε 比例已达 13.8–19.4% 的 VAL 场景。离线复放没有位置 Q，不能由残差上升直接断言 Q 数值，但这已是位置风险信号；当前版本不进入 Plant。

**10 ms held-input 可行性/成本。** 现有滤波器和 PCF helper 可直接用于纯离线前向传播：把当前选出的 task/position target、当前推力与 a_req 在 10 个 1 ms step 内零阶保持，依次推进滤波状态和 eta，再用同一固定 ε 检查十步 max ||r_f||。在滤波初始静止、未饱和的小角度线性模型中，常量 target 经过 10 ms 后的响应比例约 0.01598；10° target 差约产生 0.160° 参考位移，hover 附近对应约 0.027 m/s² 的推力轴加速度变化。这比 1 ms 有约 49 倍控制影响，但依然只是“当前输入保持”的预测，不能保证真实闭合：位置 BS 的 a_req 每 1 ms 随状态、参考和反馈改变，PCF eta 又会继续累积。101 点 task 方向扫描 ×10 步若每 1 ms 重新求解约为 1.01M 个小型传播/秒；若仅 100 Hz 更新约 101k/秒，但需把目标保持 10 ms，增加目标采样保持延迟。没有做时序 benchmark。考虑当前 ε 已偏宽、六场残差全增且 held-input 不保证跨步可行，本轮不实现或扫任何 10 ms 预算变体；若继续，应先解决滤波状态、PCF eta 和外环 a_req 的跨步可行性，并独立锁定预算后再做纯离线诊断，由 root 决定是否继续。

## 相关本地证据

- C5 位置链和 yaw 接口审计：`reports/attitude_experiment_reconciliation_20261027/C5_HF_INTERFACE_LINEAGE_AUDIT_v1.json`。
- 原始根状态、目标及 alpha/tau pilot：`reports/attitude_experiment_reconciliation_20261027/ROOT_REVIEW_STATUS_v1.md`；`experiments/dl_attitude_replacement_20261027/gru_tracking_force09_v1/audits/GRU_TRACKING_FORCE09_SCORE_final12.json`；`experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.md`。
- 全集评分与任务/内环定义：`experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/FULL72_PAIRED_SCORE_v1.json`。
- 18/(2π)Hz 频率与相位局限、已有提出的 phase-conditioned 位置残差备选：`experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/closed_loop_force09_v1/audits/FREQUENCY_PHASE_MECHANISM_REPORT_v1.md`。


