# NCMD 目标、反馈耦合与 C5 在线适应：只读机制审阅

**快照：2026-10-27。** 只读了静态源码、已完成的结果摘要和既有离线审计；未读仍运行中的 raw，未启动 Plant/MATLAB/训练，未读取 TEST，也未重建真实惯量。

## 结论

NCMD 的监督标签不是 C5 RBF 输出，而是**在 C5 teacher 闭环轨迹上、使用实际 requested torque 和固定 C5 J0 计算的 command-port residual**。因此标签数值条件于 teacher 当时发出的命令和 C5 配置；但它不是直接复制 teacher compensation。若实际分配与固定名义模型不一致，或 Plant 有外扰/参数差异，命令及其造成的状态轨迹会进入残差。固定 J0、事件时钟与 DMAX 对当前锁定部署匹配，所以本次问题不是锁配置意外错配，而是这个学习目标的可迁移性尚未证明。

**更值得先判别的是 frozen GRU 的闭环反馈导数和缺少 tracking-error 在线更新这一结构差异。** C5 RBF 每事件根据 backstepping surface 更新隐权重；NCMD GRU 仅从当前特征和 carried hidden 输出补偿，权重不更新。现有 C5 同状态审计显示 RBF 反馈 Jacobian 在抽样点很小且没有负最小特征值；旧 MLP 的负阻尼诊断不能外推到 GRU。建议把当前 GRU 放到已核验的同状态/同 hidden 冻结局部 Jacobian 检查中，与 BS 和 RBF 参照对照。目标多值性或闭环分布偏移仍是可能机制，但现有证据没有直接证明它们。

## 目标与部署的实际关系

nominal_command_target_data_v1/build_nominal_command_target_v1.py 第 146、170–180 行从历史 C5 raw 读取 requested_generalized，以 1 ms 状态/命令窗口形成 10 ms 区间标签：

\[
R_{\rm cmd} =
\frac{\omega_{e+10}-\omega_e}{0.01}
+\frac{1}{10}\sum_{i=e}^{e+9}
J_0^{-1}\bigl(\omega_i\times(J_0\omega_i)-\tau_{\rm req,i}\bigr),
\]

再按固定 DMAX clip。数据说明明确指出 allocator/actuator mismatch 留在标签中、标签不读取 realized torque（nominal_command_target_data_v1/REPORT_v1.md:11,19）。

旧 C5 路径在 run_mlp15_dev72_closed_loop.m:2554 调 RBF 更新器；更新器先用 W_before' * Phi 形成当拍输出，再以 tracking surface 更新权重，含逐输出 leakage 和逐元素投影（rbf_mimo_update.m:29–43）。运行器把当拍输出乘 beta、固定惯量映射成补偿力矩，再由 BS 输出形成 command（run_mlp15_dev72_closed_loop.m:2554–2565,2679,2761–2764,2853）。隐权重从零初始化（同文件第 497 行），场景内持续更新。故 R_cmd 来自一条已经受该 teacher 自适应补偿影响的轨迹，但标签 builder 只用已记录的 state 和请求命令；历史 rbf_output_raw 只作比较，没有用来直接构造标签（builder 第 149、207 行）。

当前 GRU 每事件输入为 [Euler error(3), body rate(3), nominal BS body torque(3), morph command(4)]，nominal moment 来自当前 BS 状态/参考，因而是内环的反馈派生量，不是外生扰动信号（run_mlp15_dev72_closed_loop.m:2502–2512；attitude_bs_step.m:20–47）。GRU 将当前特征与 carried hidden 前向，clip 后乘 beta 和固定 J0，随后仅更新 hidden，不更新网络权重（gru_stream_attitude_step_v1.m:33–46）。特征没有显式包含 beta、C5 RBF 权重、actual allocation、外扰或真实时变惯量；hidden 只能从过去输入间接推断其中部分。训练集是 DEV24+VAL48 的 72 个 C5 development scenes，不是独立验证集；训练配置列明 143,928 个事件和非 RBF-output 监督（training_config.json:49,71–72,151,180）。

## 证据与边界

- **标签语义确实不同，但不足以证明它是主要失败原因。** 已有同一 C5 状态/时钟的 10,674 个成熟区间审计：cosine 对 RBF teacher 的向量 RMSE 为 0.578 rad/s²，teacher 对固定 J0 command-port 近似残差为 0.969 rad/s²（gru_stream_cosine_dev_v1/ROOT_C5_SAME_STATE_TARGET_REVIEW_v1.json）。这是同轨迹目标语义差异，不是跨航次因果比较。
- **只换成 NCMD 标签尚未解决闭环姿态指标。** 六场已完成，审计 PASS；NCMD 任务 SO3 六场均未胜 C5，宏均值 27.330 mrad 对 C5 的 26.428 mrad，最终决策为 REJECT_NCMD_SIX_SCENE_EXPANSION（gru_stream_ncmd_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json）。这否定“新标签本身足以修复”的强命题，不区分表示能力、闭环分布偏移和反馈耦合。
- **C5 的在线更新有可观测的不同控制机制。** 旧 RBF 同状态重放逐事件误差不超过 1.78e-14，其冻结权重局部 Jacobian 在 1200 点中无负最小特征值，RBF 增量范数相对 BS 的中位比为 0.00038（attitude_rbf_local_reference_20261027_v1/RESULT_v1.json）。这是成功 teacher 轨迹上的局部诊断，不是全局稳定证明，也不保证 GRU 能复制该性质。
- **旧 MLP Jacobian 结果支持检查 feedback compatibility，但不能代表当前 GRU。** full72 MLP 在同一批 C5 状态上有 711/1200 个负最小特征值；nominal-torque-only 冻结后负值比例仍 13.5%，omega-only 仍 54.5%（attitude_rbf_local_reference_20261027_v1/RESULT_v1.json、attitude_nominal_torque_path_diagnosis_20261027_v1/REPORT.md）。这说明 nominal torque 派生路径并非唯一来源；当前没有 NCMD GRU Jacobian 证据。
- **泛化的在线头或延迟不能当作已验证替代。** causal-head 六场 task SO3 胜 C5 为 0/6（mlp15_causal_head_v1/ROOT_RESULT_v1.json）；one-event-delay 六场宏 SO3 30.820 mrad，差于其 no-delay、B、C5 对照（mlp15_one_event_delay_v1/ROOT_SIX_SCENE_DECISION_v1.json）。这些实现与 C5 RBF 更新律不同，失败只说明简单加头/加延迟不够，不否定 RBF 式误差适应。
- **理论参照不能直接移植。** Neural-Fly 使用共享表征和在线线性系数自适应，结构上比当前冻结输出更接近“表征加在线适应”思路，但不等于本项目的 RBF 更新律（https://arxiv.org/abs/2205.06908）。Neural Lander 将谱归一化约束与特定反馈设计/稳定性分析配套使用；当前 GRU 没有该 Lipschitz 约束，也没有相同证明（https://arxiv.org/abs/1811.08027）。

## 建议的最小区分检查

优先对**当前 frozen NCMD GRU**做一次已成熟 C5 状态上的冻结局部 Jacobian 检查：固定姿态、reference、arms、历史输入和 GRU hidden，仅扰动当前 body omega，按实际部署重新计算当前 nominal BS torque 特征；固定本次事件前的 GRU hidden，重新前向取得当拍 output/hidden-after，纳入 clip、beta、固定 J0，用双 epsilon 核对。与已完成的 BS/RBF 同状态 Jacobian 参照并排报告 Sym(-d tau_net/d omega) 的最小特征值及跨轴增量。此检查可以判别 GRU 是否引入不同的瞬时反馈耦合；不能证明闭环稳定性或判定分布偏移是主因。

不建议把“冻结状态下替换 requested torque，再按定义重算 R_cmd”作为首选诊断：该变化直接由标签公式中的 -J0^-1 tau_req 给出，能说明代数端口敏感性，但不能检验替代命令下未来状态/目标，也不能证明 off-policy 是失败主因。当前也没有基于同一 GRU hidden 的近邻目标散度审计；多值性仍待单独证据。

## 术语限定与 Jacobian 操作定义

在理想固定 J0、requested torque 被精确实现且无外扰的条件下，状态加速度项会与 command-port 公式中的请求项抵消，R_cmd 为零且不依赖补偿输出。因此这里说“标签条件于 teacher 命令”，指历史闭环样本中的残差可能通过实际分配、Plant 与扰动相对名义模型的差异依赖该命令及轨迹，不表示公式把 teacher RBF 输出直接作为监督 Y。对于同一组 feature+hidden，GRU 是确定性函数；未核实的是近邻可观测输入是否对应足够窄的 future R_cmd 条件分布。

C5 RBF 实际特征是 error/surface 交错的 6 维向量，见 run_mlp15_dev72_closed_loop.m 第 3683 行；GRU 的 13 维输入则另含 body rate、nominal BS moment 和 morph command。旧 RBF 与新 GRU 的输入路径、状态量及更新律均不同。

执行所建议 GRU Jacobian 时应固定事件前的 hidden-before 和过去输入，扰动当前 omega，重新计算 nominal BS moment 特征并重新运行当拍 GRU 前向，取得新的 hidden-after 与 torque；保持姿态、reference、arms、beta、J0、dmax 不变。这样覆盖当前 13 维反馈路径，但仍是冻结历史的局部导数，不测下一事件 hidden 演化、闭环分布变化或稳定性。


## 主要源码路径

- experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1/build_nominal_command_target_v1.py
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/candidate_runner_work/matlab/core/rbf_mimo_update.m
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/candidate_runner_work/matlab/runtime/gru_stream_attitude_step_v1.m
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/candidate_runner_work/matlab/core/attitude_bs_step.m
- experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/candidate_runner_work/matlab/runtime/mlp15_attitude_step_v1.m
