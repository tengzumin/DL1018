# 局部反馈 Jacobian 同行复核与 C5/RBF 参照可行性

## 判定

建议先补成功 C5/RBF 的同状态局部 Jacobian 参照，再据负特征值决定是否改 MLP 补偿结构。当前诊断说明 composite 的冻结状态灵敏度不可忽略，但不能区分这是失败 candidate 特有行为，还是成功 RBF 也具有的瞬时补偿方向。即使补了 RBF 参照，结果仍只是局部敏感性证据，不是闭环稳定性或根因证明。

RBF 参照在现有 C5 日志上**可前向重放**，不需要逆推权重，也不需要 MATLAB/Plant。成熟区间没有逐事件完整 `W` 快照：`rbf_event_audit` 只留最初 8 个事件；但 raw 和对应 `run_start.mat` 保存了其余所需输入与固定 RBF 配置。

## 对 `RESULT_v1` / `local_feedback_sensitivity.py` 的复核

- **SiLU 与窗口序正确。** `forward()` 中虽然辅助函数名为 `sigmoid`，激活实际是 `z * sigmoid(z)`，即 SiLU。窗口为 `(13,15)`，按 `order="F"` 展开后是逐事件、每事件 13 个特征的顺序，与训练模型相同；原点 MLP 与 phi 对日志 parity 分别为 `2.89e-14` 与 `9.93e-16`。
- **重算了完整当拍 BS torque 反馈链。** 有限差分扰动当前 `omega` 后，`bs_nominal()` 重算 `tau_BS`；新的 `tau_BS` 又进入当拍 MLP 特征，随后重算 MLP/RBF-head 输出和 `tau_net=tau_BS-J0*beta*clip(output)`。姿态、参考及其导数、arm 命令、过去 14 个网络输入、模型和当前 head `W_before` 冻结。原点 torque parity `1.04e-17 N·m`，net torque parity `7.63e-17 N·m`。
- **固定物理量和差分核验合适。** 诊断使用锁定 `J0` 与零矩阵 `Jdot0`，并断言 `J0==Pfixed`、`Jdot0==0`；未读变量惯量。中心差分 `eps=1e-5` 与 `5e-6` 的 Jacobian 最大差分别为 BS `3.47e-12`、frozen MLP `6.05e-8`、composite `1.51e-7`；BS 解析导数与差分最大差 `1.47e-12`。1200 个原点无 Dmax clipping。
- **负特征值的解释必须保留限定。** `Sym(-d tau_net/d omega)` 的负值表示固定姿态、参考、历史、权重下存在瞬时交叉轴反阻尼方向。它不能单独说明闭环不稳定或造成六场失败；当前 1200 点来自 composite 自己的轨迹，直接与原 C5 不同轨迹上的特征值比例比较会混入状态分布差异。

## 原六场 C5 raw 的 RBF 状态库存

六条原始 C5 teacher trace（scene IDs 见 [DATASET_MANIFEST_v1.json](../mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json)）的 raw 和 `run_start.mat` 均由该 manifest 锁定 SHA。六场日志字段一致；每场 1999 个 attitude events：

- 全 transition 日志记录 `rbf_input_sample`（6 维）、`rbf_output_raw`、`rbf_output_unclipped`、`rbf_update_flag/dt`、`rbf_attitude_surface_original/learn`（各 3 维）、`rbf_attitude_gamma_scale`（3 维）、`rbf_basis_norm/max` 和权重范数/最大值。上述更新输入在 1999 个 event 上均有限，update flag 全真，`dt` 约 0.01 s。
- 直接 `W_before/after/derivative/unprojected` 与基函数向量只在 `log/rbf_event_audit` 中保留 8 次，时间为 0.01–0.08 s；HDF5 `weight_before` shape 为 `(8,3,81)`（MATLAB shape `81×3×8`）。所以成熟 200 个选定事件的 W 必须重放，不能从单个 weight norm 反解。
- 每场 `run_start.mat/runStart/cfg/rbf/attitude` 含实际 81 个 centers、`input_scale`、`sigma=1.2`、`gamma`、`sigma_w`、`s_limit`、`dmax`、`wmax=60`、`rbf_input_dim=6`、`linear_dim=0`。没有 `basis_override`、`basis_gamma_scale` 或 `width_scale`。这是本次只读读取的 RBF 配置子组；没有访问任何真实/变量惯量字段。
- `runStart/opts` 不含 `rbf_attitude_initial_weight`；原 runtime 在 `run_dl1018_closed_loop.m:388` 将姿态 `rbfAtt.W` 初始化为零 `(81×3)`。第一条 audit 的 `W_before` 范数在六场均精确为 0。runStart 根级 `W0` 是 `(3×33)` 的位置权重，不能拿来当姿态 RBF W。

精确 C5 源由 `C5_AXIS_COORDINATE_INPUT_LOCK_v1.json` 锁定：`run_dl1018_closed_loop.m` SHA `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`；`rbf_mimo_basis.m` SHA `4139c7d08daa5bea6e04702b966ce76cdb6a54ea33d9820cfd9c3a70529248f4`；`rbf_mimo_update.m` SHA `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a`；`attitude_bs_step.m` SHA `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc`。

## 可重放更新顺序与矩阵方向

源函数位置：`run_dl1018_closed_loop.m:388, 1697–1725, 2318–2435, 3397`；`rbf_mimo_basis.m:20–88`；`rbf_mimo_update.m:20–49`。

1. 当拍输入由 `attitude_input` 组装为 `z=[e_roll,s_roll,e_pitch,s_pitch,e_yaw,s_yaw]`。raw 每事件记录该 `z`、实际 `surface_learn`、`gamma_scale`、update `dt`；重放应优先使用日志中的 learn surface 和 gamma scale。
2. basis 是 `(81×1)` 列向量：`z_scaled=z./input_scale`；对 MATLAB `centers` `(6×81)` 计算 `Phi_i=exp(-||center_i-z_scaled||²/(2*sigma²))`。日志没有完整逐事件 `Phi`，但静态 centers 和每事件 `z` 足以重算。
3. 每事件输出先使用更新前矩阵 `W_before (81×3)`：`d_raw=W_before.'*Phi`，再逐输出 clip 到 `±dmax`。成熟时 beta 为 1，compensation torque 为固定 `J0*(beta*d_hat)`。必须用 **W_before** 求当前 Jacobian；本事件更新后的 W 只影响后续 event。
4. 随后计算更新。MATLAB 中 `s_eff=clip(surface_learn,±s_limit)` 是 `(3×1)`；`gamma_vec=(cfg.gamma.*logged_gamma_scale).'` 是 `(1×3)`；`Phi` 是 `(81×1)`。若 `basis_gamma_scale` 缺省为全 1，则 `W_dot=-(Phi .* basis_gamma) * (gamma_vec .* s_eff.') - W_before .* sigma_vec`，结果为 `(81×3)`。`W_unprojected=W_before+W_dot*dt`，然后逐元素投影 `W_after=clip(W_unprojected,±wmax)`，不是 Frobenius 球投影。重放可直接执行该前向投影，不存在反解投影的问题。
5. runtime 将 `cfg.gamma` 与逐事件 `rbf_attitude_gamma_scale` 相乘后传入 helper（`run_dl1018_closed_loop.m:1698`）；应只乘一次，不能又把 `cfg.rbf.attitude.gamma_scale` 重复乘上。更新律是 tracking surface 驱动、含逐输出泄漏 `sigma_w`、逐元素 `wmax` 投影。它与当前 candidate head 的 RLS 型更新及 Frobenius 范数投影不同；这只是结构差异，不等于泄漏或投影本身有缺陷。

## 同状态比较的合法条件与建议

要判断负特征值是否为 MLP/composite 特有，必须在相同 C5 记录状态上比较成功 C5/RBF 和 frozen MLP：RBF 的成熟 `W_before` 从该场景零初始化沿 1999 事件重放；MLP 的过去 14 个输入窗口则用同一 C5 raw 的历史事件重建，当前特征使用该事件 `state/ref/rate/accel/arms` 和重新计算的固定 `J0` nominal torque。不要把 v3 candidate trace 的 MLP history 或 head `W_before` 搬到不同的 C5 raw，也不要把 C5 RBF W 与 composite RLS head 的更新解释成仅一个参数差异。

因此，**若准备基于负特征值修改补偿结构，成功 C5/RBF 同状态参照是必要证据**；它能判断这个局部方向是否也出现在成功 teacher 上，但仍不能单独判定根因或闭环稳定性。本审计只做日志/源代码可行性核查，没有实现 RBF 重放、训练、MATLAB 或 Plant 运行，也没有修改历史文件。
