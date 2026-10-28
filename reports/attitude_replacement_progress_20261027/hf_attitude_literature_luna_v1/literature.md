# 高频姿态内环替换：文献与代码库调查

- 调查日期：2026-10-27（UTC/系统工作日期）
- 范围：主动变形/可折叠四旋翼的高频姿态内环；重点检查学习残差、时序模型、命令滤波、增量控制与扰动观测；只用原始论文/作者实验室页面、官方项目页面和官方文档。
- 边界：未训练、未运行 Plant、未读取 TEST 原始数据/结果/数组。一次广泛文本搜索只命中了 `configs/scene_specs.csv` 中的场景配置元数据；未继续查看/使用其中 TEST 行。下文的 W09–W14 只按用户指定的评估目标处理，不从 TEST 或配置推断效果。

## 项目代码基线（只读）

1. `matlab/core/default_config.m:16` 把仿真/控制离散步长设为 `1e-3 s`（1 kHz）。这说明代码步频，不证明 W09–W14 是 1 kHz 的物理激励；评估时应把参考/风/变形频率与控制采样率分别说明。
2. `matlab/core/command_filter_step.m:1-23` 是共享的因果二阶姿态命令滤波器，输出角度、角速度和限幅角加速度。高频对比应固定这条参考路径与限值，单独报告滤波相位/幅值衰减，避免候选模型与命令滤波重复平滑。
3. `matlab/data/attitude_feature_row_v3_6.m:1-23` 的 X29 明确不接受几何、惯量或形态代理特征；主体由误差/滑模面、机体系角速度、姿态参考导数、姿态、平动速度、名义角加速度、归一化推力和上一事件电机设定点组成。
4. 这不等于整条控制路径 J-free：`matlab/core/attitude_bs_step.m:34-41` 用 `P.inertia` 形成陀螺项和名义力矩，并可将 `P.inertia_dot_for_bs * omega` 前馈进去；`matlab/core/controller_parameters.m:27-37,70-77` 在 morph 模式从传入的 Plant/controller 参数复制惯量和惯量导数。`matlab/runtime/run_dl1018_closed_loop.m:2125,2206,2213` 还把若干角加速度残差乘 `P.inertia` 转成力矩；X29-v39 力矩 head 则在 `:2162-2171` 使用 `aiHead.J0=P.inertia` 初始化。
5. 所以如果目标是“部署路径不输入真实 J / Jhat / Jdot”，仅保持 X29 不含 J 不够。要么将基线也换成无 J 的 rate-error → torque/actuator 控制器；要么至少让候选 head 直接预测有界 N·m 残差/控制增量，不在推理时将角加速度乘运行时 J，同时移除 BS/Jdot 依赖。物理力矩到电机的分配通常依赖电机几何/效能矩阵而非惯量；若还要禁止几何输入，需把目标定义为归一化电机命令增量并单独处理可控性/饱和。

## 可迁移先行机制

| 来源 | 可迁移机制 | 与本项目的差异/边界 | 不能据此声称 |
|---|---|---|---|
| Cobo-Briesewitz, Wahba & Hönig, “Learned Incremental Nonlinear Dynamic Inversion for Quadrotors with and without Slung Payloads,” L4DC 2026（作者实验室列出；早期预印本题为 “Neural-Augmented … with Payload Adaptation”）；[arXiv:2503.09441](https://arxiv.org/abs/2503.09441)、[作者实验室论文页](https://imrclab.github.io/publications.html)、[作者 PDF](https://imrclab.github.io/assets/pdf/2026-lindi-grc.pdf) | 将 IMU/RPM 形成的 INDI 残差先做平滑，再用 MLP 学残差；早期 arXiv 版本给出 19 输入/6 输出，并报告 Crazyflie 上约 203 μs/次（约 4.93 kHz）。作者比较“仅学习”“仅 INDI”“学习 + INDI”，指出平滑预测可减小噪声，组合在部分场景最好；复杂悬挂载荷下 INDI 仍更强。对应到本项目：离线用物理仿真真值构造力矩残差标签，在线仅用合法状态/命令历史预测；保留传统 rate controller 作安全基线。 | 论文对象是固定平台/载荷与外部扰动，不是主动变形臂；其角力矩标签计算用动力学量，移除 RPM 输入不代表论文证明了变惯量形态泛化。论文网络预测残差/INDI 输出，而非独立稳定性证明过的完整姿态控制器。作者实验室出版页列 PDF/arXiv，本次未找到该论文对应的官方 GitHub 实现链接。 | 不能声称“首次用神经网络学四旋翼残差”“无需专用传感器即可高频补偿”“可直接跨形态泛化”，也不能把 4.93 kHz 推理吞吐等同于闭环带宽/飞行性能。 |
| Bezerra, de Paiva & Cordeiro, “Incremental Neural Inverse Dynamics for the Attitude Control of a Quadcopter,” CBA 2026 preprint；[CBA 官方论文页/PDF](https://ojs.sba.org.br/index.php/cba/article/view/5785) | INDI-NN 用 NARMAX 网络预测 INDI 所需的逆控制效能矩阵，增量控制每步仍利用角加速度反馈；作者报告在模型扰动/不确定性下相对 DIC 的表现，以及与经典 INDI 接近的结果，并称无需预先测量/估计效能矩阵。若姿态替换的重点是消掉 J 显式输入，这比“黑箱直接输出姿态角”更贴近：学局部控制效能逆映射，让 rate 误差与角加速度目标转成控制增量。 | 2026-10-05 发布的 CBA 预印本，研究对象是一般四旋翼姿态而非主动变形；当前页面/全文摘要未提供可支持 W09–W14 的变形高频证据。它仍需高频角加速度测量/滤波与快速执行器，不是纯状态静态映射。页面未见 DOI 或作者官方 GitHub 链接。 | 不能声称 INDI-NN 已在可折叠/伸缩臂机体实飞通过，或不需要在线加速度估计/执行器效能处理；不能将其 NARMAX 逆效能模型包装成通用新原理。 |
| Bauersfeld et al., “NeuroBEM: Hybrid Aerodynamic Quadrotor Model,” RSS 2021；[DOI:10.15607/RSS.2021.XVII.042](https://doi.org/10.15607/RSS.2021.XVII.042)、[arXiv 原文](https://arxiv.org/abs/2106.08015)、[UZH 官方项目/数据/代码页](https://rpg.ifi.uzh.ch/neuro_bem/Readme.html) | 用过去 20 帧、每帧 2.5 ms（50 ms 历史）的速度/电机转速，经 TCN 或 MLP 估计未建模力和力矩；TCN-medium 在精度/算力间折中。1 kHz IMU/电机信号、400 Hz 位姿数据和经过滤波的导数说明时序残差可利用滞后/隐藏气流状态。可迁移的是短历史 head、低延迟因果输入与平滑监督标签，而不是照搬 BEM。 | 它主要是动力学模型/仿真闭环，不是替换姿态率控制器；结构上有 BEM 解析项与已知惯量，低层仍用 BetaFlight rate loop。论文明确指出纯学习残差反馈可能形成反馈环并导致坠毁；论文数据中的偏航激励/力矩范围也较弱。 | 不能称“TCN/历史残差用于无人机控制为本项目创新”；不能以预测误差下降代替内环稳定性或 W09–W14 闭环指标；其 400 Hz 数据率也不代表 1 kHz 学习头可用。 |
| Patnaik & Zhang, “Adaptive Attitude Control for Foldable Quadrotors,” IEEE Control Systems Letters 7, 1291–1296 (2023)；[DOI:10.1109/LCSYS.2023.3234045](https://doi.org/10.1109/LCSYS.2023.3234045)、[arXiv 原文](https://arxiv.org/abs/2209.08676) | 把离散折叠形态建模为 SO(3) switched systems；几何姿态反馈 + 每形态惯量参数自适应估计，并加鲁棒项处理扰动；通过最小 dwell time/控制感知最小 jerk 轨迹安排切换。可迁移稳定性论证中的“切换后误差、等待时间、参考轨迹协同”以及有界不确定项，而不是把控制器照搬。 | 这项最直接针对可折叠机体，但其控制明确估计惯量参数 `ĥp`，并使用惯量相关 Lyapunov 条件；结论主要是仿真、离散模式切换，目标不等同于无 J/Jhat/Jdot、高频连续伸缩或高频风扰。 | 不能说现有折叠机控制已无需惯量状态，也不能声称本项目首次把神经补偿用于折叠机；该论文的稳定性结论不能直接套用到学习姿态头。 |
| Wang et al., “Onboard Actuator Model-Based Incremental Nonlinear Dynamic Inversion for Quadrotor Attitude Control,” Chinese Journal of Aeronautics 34(11), 216–227 (2021)；[DOI:10.1016/j.cja.2021.03.018](https://doi.org/10.1016/j.cja.2021.03.018) | 外姿态 NDI + 内角加速度 INDI，并在板载控制器显式考虑执行器动态；作者报告其修改执行器模型可消除“控制器采样快于执行器”时的振荡，且做了数值仿真和飞行测试。对本项目的高频目标，关键迁移项是把电机/舵机迟滞、保持和采样差作为闭环对象；比较总延迟，而不只看网络推理时间。 | 仍是 INDI/角加速度结构，有控制效能/执行器模型，未专门研究形态切换。需要确认仿真中“ideal instantaneous”执行器与将来真实执行器差异，否则高频结论不可外推。 | 不能声称只要将学习器跑到 1 kHz 就会改善带宽；忽略执行器带宽/时延的学习器可能激发振荡。 |
| Choi & Bang, “Adaptive command filtered backstepping tracking controller design for quadrotor UAV,” Proc. IMechE G 226(5), 2012；[DOI:10.1177/0954410011415001](https://doi.org/10.1177/0954410011415001)；一般命令滤波理论：[Farrell et al., “Command Filtered Backstepping,” DOI:10.1109/TAC.2009.2015562](https://doi.org/10.1109/TAC.2009.2015562) | 二阶命令滤波器为反步虚拟控制提供有限、可实现的导数，处理姿态/角速率/执行器约束，并通过补偿跟踪误差维持稳定性分析。可迁移：保留一条确定、因果、共享的命令参考模型，比较控制器时不改变它；高频报告滤波和候选网络共同产生的相位/幅值滞后。 | 该四旋翼方案本身在线更新质量/惯量/执行器参数，不能满足 J-free；本项目已有二阶滤波器，新增滤波可能重复加相位滞后。 | 不能把“有命令滤波”视为创新，也不能仅靠提高滤波自然频率证明高频跟踪改善；滤波器限幅、时延与饱和同样要报告。 |
| PX4 开发者官方文档：[Controller Diagrams](https://docs.px4.io/main/en/flight_stack/controller_diagrams)、[Multicopter PID Tuning Guide](https://docs.px4.io/main/en/config_mc/pid_tuning_guide_multicopter) | 官方架构示例将姿态误差映射到角速度设定，再由最内层 rate PID 用陀螺角速度产生控制输出；角加速度导数路径做低通滤波，姿态设定采用二阶临界阻尼参考模型并将参考率前馈、速率限幅。可作为“保持姿态/角速率职责分层、滤除角加速度噪声、把 rate feedback 放在快速内环”的工程参照。 | PX4 文档描述标准通用多旋翼实现，不是学习残差论文，也不证明其控制足以处理本项目的变形惯量/配置。 | 不能把 PX4 的分层 PID 作为本项目的专有贡献；其实现有控制分配/电机配置知识，不能据此说完全无模型。 |
| He et al., “GPI observer-based active disturbance rejection control for a morphing quadrotor,” Intelligence & Robotics 3 (2023), 274–287；[DOI:10.20517/ir.2023.18](https://doi.org/10.20517/ir.2023.18)、[出版社原文](https://site.oaecdn.com/articles/ir.2023.18) | GPI 高阶观测器把内部模型失配与外扰并入扩张状态，PD+观测补偿；作者报告观测响应快于 ESO。可迁移的是“把变形引起的未建模力矩作为可估扰动”这一监督/观测接口，并为残差输出加带宽与幅值界。 | 原文形态为四臂旋转；作者实时重算 CoG/MoI、控制分配矩阵，控制增益 `b=1/Jyy`，案例是位置 PD+GPI、以仿真为主，内扰估计延迟报告不超过 0.2 s。与 kHz 高频 rate loop / 不输入 J 目标不匹配。 | 不能说 GPI 本身解决了 J-free 高频姿态控制，也不能把“估计到总扰动”外推成一定改善 W09–W14。 |
| Smeur, de Croon & Chu, “Cascaded Incremental Nonlinear Dynamic Inversion for MAV Disturbance Rejection,” Control Engineering Practice 73 (2018), 79–90；[DOI:10.1016/j.conengprac.2018.01.003](https://doi.org/10.1016/j.conengprac.2018.01.003)、[TU Delft 官方记录](https://repository.tudelft.nl/record/uuid:3079ef6f-907b-4b55-b21f-4a3ad8b65401) | 级联姿态/位置 INDI 在风洞 10 m/s 气流入口/出口实验中展示了相对 PID 的扰动拒斥提升。可迁移为对比基线：用测得角加速度增量而非重新拟合全套非线性项作为鲁棒对照，并将外扰拒斥和姿态跟踪分开度量。 | 它不是主动变形控制，也仍需部分效能模型和测量链；不直接验证学习网络，也不是无 J 的完整内环实现。 | 不能把文献的风洞增益视作本项目高频形态变化上的结果。 |

## 对本项目可落地的方案假设（待后续 DEV/VAL 证伪）

1. 固定 C5 DSSM 位置环输出、力到姿态适配器、共享命令滤波器及控制分配；候选只替换姿态/RBF 通道，防止外环变动混淆 W09–W14 对比。
2. 把内环拆为“姿态误差 → 期望 body rate”和“rate error → 基础 N·m/归一化 actuator command”。基线可用 quaternion/几何 P + rate PI(D)；其输出不用 `J` 或 `Jdot`。学习器优先预测有界、可限速的 `Δτ`（离线标签可用仿真物理真值，在线推理不需要 J），或直接预测归一化电机命令增量；不要推理时用真实/估计 J 把 `Δα` 转成力矩。
3. 机制候选：短因果窗口 TCN/GRU/MLP 预测时延/形态耦合残差；或 NARMAX/轻量前馈网络预测增量控制效能的逆映射。前者适合隐藏状态/滞后，后者保留 INDI 的反馈闭环结构。两者都设严格输出/变化率限幅、启动 ramp、在线权重投影/泄漏（若自适应），并保留可回退的无学习 rate 控制器。不要把 GPI 高阶观测器的 0.2 s 级结果外推为高频有效。
4. W09–W14 的比较至少分别报告：候选闭环与基线相对态误差的 RMS/峰值、扰动/命令频率响应的幅值和相位、实际执行器/混控命令增量 RMS 与饱和占比、滤波/网络/执行器总延迟、各轴分项结果。若受控激励没有覆盖目标频带，只能报告现有场景分数，不能称为“高频带宽”。所有验证限 DEV/VAL；本调查不触碰 TEST。

## 创新性边界

- 已有先行工作分别覆盖了折叠四旋翼切换姿态控制、神经/时序残差模型、学习型 INDI 效能逆映射、扰动观测、命令滤波以及高频执行器建模。不能笼统宣称这些机制“首次用于四旋翼/姿态内环”。
- 可能的项目特定贡献需限定为：**在 C5 DSSM 位置环固定条件下，比较一个不向部署端提供真实 J/Jhat/Jdot 的姿态 rate/力矩或 actuator 学习内环，并在预先锁定的 DEV/VAL W09–W14 高频用例中证明相对 RBF 的改进**。这仍需先实现并做配对闭环验证；文献不能代替该证据，也不能支持 TEST 表现。
- 对“无惯量输入”的严格定义应覆盖整个推理/控制路径：删掉基线对 `P.inertia`、`P.inertia_dot_for_bs` 的读取，以及角加速度残差 `J·Δα` 映射；仅让网络输入不含 J 不满足此定义。

## 来源登记

所有来源均于 **2026-10-27** 访问/核对；优先链接出版社、arXiv 原文、作者实验室论文/项目页或官方飞控文档。无作者官方代码链接的论文未用第三方复现替代。

- Cobo-Briesewitz, E., Wahba, K., & Hönig, W. (2026). *Learned Incremental Nonlinear Dynamic Inversion for Quadrotors with and without Slung Payloads*. L4DC 2026; the earlier preprint is titled *Neural-Augmented Incremental Nonlinear Dynamic Inversion for Quadrotors with Payload Adaptation* (arXiv:2503.09441). [arXiv](https://arxiv.org/abs/2503.09441) · [IMRC lab bibliography](https://imrclab.github.io/publications.html) · [author-hosted PDF](https://imrclab.github.io/assets/pdf/2026-lindi-grc.pdf).
- Bezerra, J. V. A. P., de Paiva, E. C., & Cordeiro, R. A. (2026). *Incremental Neural Inverse Dynamics for the Attitude Control of a Quadcopter*. Congresso Brasileiro de Automática preprints, published 2026-10-05. [official article page and PDF](https://ojs.sba.org.br/index.php/cba/article/view/5785). DOI not listed on the page as checked.
- Bauersfeld, L., Kaufmann, E., Foehn, P., Sun, S., & Scaramuzza, D. (2021). *NeuroBEM: Hybrid Aerodynamic Quadrotor Model*. RSS 2021. DOI: 10.15607/RSS.2021.XVII.042. [DOI](https://doi.org/10.15607/RSS.2021.XVII.042) · [arXiv](https://arxiv.org/abs/2106.08015) · [UZH author project/data/code page](https://rpg.ifi.uzh.ch/neuro_bem/Readme.html).
- Patnaik, K., & Zhang, W. (2023). *Adaptive Attitude Control for Foldable Quadrotors*. IEEE Control Systems Letters, 7, 1291–1296. DOI: 10.1109/LCSYS.2023.3234045. [DOI](https://doi.org/10.1109/LCSYS.2023.3234045) · [arXiv](https://arxiv.org/abs/2209.08676).
- Wang, Z., Zhao, J., Cai, Z., Wang, Y., & Liu, N. (2021). *Onboard Actuator Model-Based Incremental Nonlinear Dynamic Inversion for Quadrotor Attitude Control: Method and Application*. Chinese Journal of Aeronautics, 34(11), 216–227. DOI: 10.1016/j.cja.2021.03.018. [publisher/DOI record](https://doi.org/10.1016/j.cja.2021.03.018).
- Choi, I.-H., & Bang, H.-C. (2012). *Adaptive Command Filtered Backstepping Tracking Controller Design for Quadrotor UAV*. Proc. IMechE G, 226(5). DOI: 10.1177/0954410011415001. [publisher record](https://doi.org/10.1177/0954410011415001).
- Farrell, J. A., Polycarpou, M. M., Sharma, M., & Dong, W. (2009). *Command Filtered Backstepping*. IEEE Transactions on Automatic Control, 54(6), 1391–1395. DOI: 10.1109/TAC.2009.2015562. [IEEE/DOI record](https://doi.org/10.1109/TAC.2009.2015562).
- PX4 Development Team. *Controller Diagrams* and *Multicopter PID Tuning Guide*, official PX4 documentation. [controller architecture](https://docs.px4.io/main/en/flight_stack/controller_diagrams) · [rate/attitude tuning](https://docs.px4.io/main/en/config_mc/pid_tuning_guide_multicopter).
- He, C., Sun, H., Wu, Q., Su, Y., & Sun, N. (2023). *GPI Observer-Based Active Disturbance Rejection Control for a Morphing Quadrotor*. Intelligence & Robotics, 3, 274–287. DOI: 10.20517/ir.2023.18. [publisher record](https://doi.org/10.20517/ir.2023.18) · [publisher full text](https://site.oaecdn.com/articles/ir.2023.18).
- Smeur, E. J. J., de Croon, G. C. H. E., & Chu, Q. (2018). *Cascaded Incremental Nonlinear Dynamic Inversion for MAV Disturbance Rejection*. Control Engineering Practice, 73, 79–90. DOI: 10.1016/j.conengprac.2018.01.003. [DOI](https://doi.org/10.1016/j.conengprac.2018.01.003) · [TU Delft repository record](https://repository.tudelft.nl/record/uuid:3079ef6f-907b-4b55-b21f-4a3ad8b65401).

## 已检查的本地代码文件

- `matlab/core/default_config.m`
- `matlab/core/command_filter_step.m`
- `matlab/core/attitude_bs_step.m`
- `matlab/core/controller_parameters.m`
- `matlab/data/attitude_feature_row_v3_6.m`
- `matlab/runtime/run_dl1018_closed_loop.m`（仅上述 attitude runtime 源码行）
