# C5 RBF Teacher 与冻结 MLP15 同状态动作复算

- **范围**：对已存在的 C5_RBF 72 场 raw，在 C5 姿态事件状态上离线重放冻结 MLP15；核对事件轨迹、动作单位、限幅、beta 和固定惯量到力矩映射。
- **未做事项**：没有调用 Plant、没有训练或调参、没有访问 TEST、没有改动 raw / 模型 / 历史审计。此报告是本任务唯一新写入的文件。
- **解释边界**：动作指标是按 C5_RBF 的闭环状态离线计算的同状态模仿误差，不是 MLP15 闭环复测，也不是与 B 的逐时动作比较。

## 1. 输入身份与审核边界

| 输入 | SHA-256 |
|---|---|
| `C5_DEV72_INPUT_LOCK_v3.json` | `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75` |
| `C5_DEV72_BATCH_STATUS_v3.json` | `20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22` |
| C5 batch runner `run_c5_dev72_v3.m`（batch记录的runner SHA） | `f51cdf746afa5c58b018d07e87778e54e711320ce6bd87491dbcd789e92c79a2` |
| C5 isolated runner `run_dl1018_closed_loop.m` | `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c` |
| 共享 `matlab/core/default_config.m` | `685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51` |
| 共享 `matlab/core/rbf_mimo_update.m` | `dde65f5f3b664ecdbd82a393dde0aea8da3b7401b5f54c8a92fcef5acd17f78a` |
| 共享 `matlab/core/attitude_bs_step.m` | `cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc` |
| MLP15 权重、normalizer MAT `mlp15_attitude_weights_v1.mat` | `07a115318b946852b844a9bfe7a805c2b9ac0432e4bd3489a586d3c378b1161a` |
| MLP15 frozen release | `858cfd988d74da7120ed0798e1ab8556514d490db1514261b67e2ccad5e61652` |
| MLP15 candidate source lock | `a289c6684b5e927969e49bd322dc72b8284ff7242dfa8f68ff6928cd9f43c194` |
| MLP15 forward / step / closed-loop source | `0f69185f36ba2d3ee5db5b930278e91e113a901b22c8315319eba64c6cb2b07d` / `65bb749dc8c26356e757e5a5ee2837267bda65724e09481e5d3ce849c53c0375` / `a95de4900383622a71d07205ba32b1fb969f753a984791c81e39faf47ab463c5` |
| MLP15 parity vector / recorded MATLAB parity audit | `103f39593cad55b14ff7dff75eb62f2674757b97fc55552570450fbe323c847f` / `86a5872b802bb89d81a0d4cb09fe9d6c3c3c6bf960389b4c9dd384481433153b` |
| MLP15 training config / TRAIN-only dataset manifest | `ab6fb198856f02fe1130c78d4ecc111b5c29d21c5613c1ddec868ad3c40c2d1f` / `4a98548618d799b01b96809ea274b6a4ffcf5eded0e24f2fde5401619ffc442d` |

C5 72 个场景及 raw 路径 / SHA 由 C5 lock 中的 12 条 `C5_reuse` 和 batch status 中的 60 条 records 绑定；此前的只读身份复核确认 72/72 条 raw、status、run_start 与相应记录对应。本次事件诊断直接读取这些记录指向的 raw，不重复生成或改写身份清单。

- **12 reuse**：锁定父筛查状态为 `PASS_C5_RAW_ALL_EVENTS`。它们全是 VAL 场景。lock 中 `parent_screen_event_count=1968` 是原 C5 screen 的另一事件计数；这次姿态 trace 的 `attitude_event_flag` 是 1999，二者不是同一个计数器。
- **60 new**：60/60 `run_status` 为 `RUN_COMPLETE_RAW_PENDING_AUDIT`，`log_status=STABLE`，20,000 transitions / 20,001 state samples；它们完成了本报告规定的 raw trace 检查，但仍待父级正式 audit，不能把它们称为已正式审计 PASS。
- 因而“72 场身份/姿态轨迹核验通过”只表示 manifest 绑定及本报告的只读 trace 门通过；不改变 60 场 pending-parent-audit 状态。

## 2. 复算方法

训练配置声明 MLP15 目标是 `B logged rbf_output_raw at event k, pre-beta, rad/s^2`，训练集、输入 normalizer 与输出 `target_rms` 均为 TRAIN-only。锁定模型是 195→64→32→3 的两层 SiLU MLP；输入是 13 特征的最近 15 个姿态事件，normalizer 后以 event-major / feature-minor 次序展平。按运行时代码，每个场景最初 14 个历史事件为零；模型输出乘 TRAIN `target_rms` 后为物理角加速度残差，运行时再按 `[45, 45, 4.7124] rad/s²` 限幅并乘 beta。

在每个 C5 `attitude_event_flag` 位置，用同一 C5 样本重建 MLP 输入：

1. `wrap(filtered_attitude_reference - state Euler angles)`（rad）；
2. `state(10:12)` 机体系角速度（rad/s）；
3. `attitude_bs_nominal_torque_Nm`（N·m）；
4. `arms.command` 四维形态命令。

这与 MLP15 runner 在事件 `k` 组装特征的顺序一致。窗口只含当前及过去事件，没有未来输入。比较量为 **运行时 clip 后、乘 beta 前**的 MLP 输出，与 C5 `rbf_output_raw`（RBF 限幅后、beta 前）；两者均为 rad/s²。符号率按逐轴分量计算，忽略 `|teacher| <= 1e-4 rad/s²` 的近零分量。表中 scalar RMSE 是所有事件和三轴分量合并后的 RMSE；vector RMSE 是 `sqrt(mean(||prediction-teacher||²))`。`slope0` 是所有轴合并、零截距最小二乘斜率 `sum(pred*teacher)/sum(teacher²)`；轴斜率是各轴分别含截距 OLS。

### MLP 推理 parity

对锁定 `parity_vector_v1.mat` 用导出的 MAT 权重、SiLU、TRAIN `target_rms` 和 `window(:)` 等价展平顺序复算：最大绝对误差 **9.914506975e-7 rad/s²**。这与存档 MATLAB parity audit 的 **PASS / 1e-5 rad/s²** 容差吻合。MAT 文件本身 SHA 与 MLP15 release 中 `mlp15_model_sha256=07a115…` 一致。

## 3. 姿态 event trace、单位和输出契约

| 检查 | 12 reuse | 60 new | 结果 |
|---|---:|---:|---|
| 场景数 | 12 | 60 | 72 total |
| 每场 `attitude_event_flag` / `rbf_event_count` | 1999 / 1999 | 1999 / 1999 | 全场一致 |
| 事件输入、RBF raw/unclipped、applied acceleration 有限 | 全部 | 全部 | 72/72 通过 |
| 事件索引递增且落在 20,000 transition 内 | 全部 | 全部 | 72/72 通过 |
| event 索引的 `transition_time` 与 `time` 最大差 | 0 s | 0 s | 72/72 通过 |
| `rbf_output_raw` 与 `clip(rbf_output_unclipped, dmax)` 最大差 | 0 | 0 | 72/72 通过 |
| `attitude_rbf_estimate_acceleration_rads2` 与 `beta * rbf_output_raw` 最大差 | 0 | 0 | 72/72 通过 |
| 显式 `attitude_event_beta` 在事件位有限数 | 0 / 23,988 | 0 / 119,940 | **日志缺字段** |

C5 `run_start.mat` 锁定 `dt=0.001 s`、`beta_rise_time=2.2 s`、`dmax=[45,45,4.7124]`，姿态事件索引每 10 个仿真步一次。源代码 beta 规则为 `min(k*dt/2.2,1)`；虽然 raw 中 `attitude_event_beta` 在所有事件位都是 NaN，但从该公式推得的 beta 乘 `rbf_output_raw` 与完整 applied-acceleration 日志逐样本相等（最大误差 0）。所以 beta 应用契约可从代码 + raw 输入/输出关系核验，**显式 beta 字段本身没有被记录**。

`rbf_output_raw` 是 `rbf_mimo_update` 当前更新前权重输出经过 `dmax` 限幅的值；随后才应用 beta。RBF 更新在当前输出之后进行，故这里的教师动作与当前事件状态同时间、没有把更新后的权重反向作用到当前输出。上述输出单位和训练目标一致，都是 beta 前的角加速度残差（rad/s²）。

### 固定 J0 到 C5 补偿力矩

每场 `run_start.mat` 均记录 `controller_morphology_mode=fixed`、`arm_initial=[0.15,0.15,0.15,0.15]`、相同质量几何输入和 `dt=0.001 s`。按 `simulation_parameters`、`controller_parameters(...,'fixed')` 及 `distributed_mass_properties` 的固定姿态控制路径，从 72 个 run-start 配置复算出的 J0 完全相同：

`J0 = diag([0.003257553333333334, 0.0032575533333333334, 0.006360648333333333]) kg·m²`。

72/72 raw 均包含 `attitude_rbf_compensation_torque_Nm`。以 raw 的 applied acceleration 计算 `J0 * acceleration` 并对实际 C5 补偿力矩比较，143,928 个姿态事件的最大绝对误差为 **1.39e-17 N·m**，合并 RMSE 为 **1.15e-18 N·m**。所以本批 C5 日志的固定 J0 角加速度到力矩映射可复现闭合；这个映射没有使用随形态变化的惯量重建。

## 4. 同状态 MLP15 对 C5 RBF 动作的拟合结果

下表使用 MLP **运行时限幅后**的 pre-beta 输出。`bias` 是 `(MLP − C5 RBF teacher)` 的 `[x,y,z]` 均值，单位 rad/s²。sign 是轴分量级正确率。

| cohort | wind 组 | 场景 / 事件数 | RMSE scalar / vector (rad/s²) | `slope0` | 各轴 OLS 斜率 [x,y,z] | sign | bias [x,y,z] |
|---|---|---:|---:|---:|---|---:|---|
| reuse12 | W09–W14 | 6 / 11,994 | 4.049 / 7.012 | 0.584 | [0.595, 0.555, 0.404] | 53.1% | [-1.958, -0.156, -0.048] |
| reuse12 | W15 | 3 / 5,997 | 1.802 / 3.122 | 0.891 | [0.843, 0.898, 0.499] | 70.6% | [-0.452, 0.139, 0.014] |
| reuse12 | W00–W08 | 3 / 5,997 | 1.407 / 2.437 | 1.036 | [1.160, 1.034, 0.470] | 54.1% | [0.342, -0.252, 0.006] |
| **reuse12** | **全部** | **12 / 23,988** | **3.083 / 5.339** | **0.764** | **[0.728, 0.805, 0.420]** | **57.1%** | **[-1.006, -0.106, -0.019]** |
| new60 | W09–W14 | 22 / 43,978 | 5.673 / 9.826 | 0.478 | [0.541, 0.448, 0.195] | 53.2% | [1.103, 0.273, -0.081] |
| new60 | W15 | 3 / 5,997 | 1.300 / 2.252 | 0.929 | [0.926, 0.930, 0.788] | 71.3% | [-0.146, 0.150, 0.015] |
| new60 | W00–W08 | 35 / 69,965 | 3.108 / 5.383 | 0.848 | [0.863, 0.837, 0.685] | 62.7% | [0.250, -0.039, 0.046] |
| **new60** | **全部** | **60 / 119,940** | **4.186 / 7.250** | **0.726** | **[0.765, 0.702, 0.564]** | **59.2%** | **[0.543, 0.085, -0.002]** |
| **all72** | **W09–W14** | **28 / 55,972** | **5.366 / 9.295** | **0.499** | **[0.551, 0.460, 0.235]** | **53.2%** | **[0.447, 0.181, -0.074]** |
| **all72** | **W15** | **6 / 11,994** | **1.571 / 2.722** | **0.900** | **[0.869, 0.909, 0.600]** | **70.9%** | **[-0.299, 0.145, 0.015]** |
| **all72** | **W00–W08** | **38 / 75,962** | **3.009 / 5.211** | **0.852** | **[0.869, 0.841, 0.680]** | **62.1%** | **[0.258, -0.056, 0.043]** |
| **all72** | **全部** | **72 / 143,928** | **4.023 / 6.968** | **0.732** | **[0.753, 0.716, 0.555]** | **58.8%** | **[0.285, 0.053, -0.005]** |

all72 的轴向 RMS 分别为：C5 teacher `[8.025, 9.252, 0.611]`、MLP15 `[7.267, 8.083, 0.495]` rad/s²。未限幅 MLP15 对 teacher 的合并 scalar RMSE 是 **4.027**，运行时限幅后为 **4.023**；因此输出 clip 不是主要拟合误差来源。

W15 的 yaw teacher RMS 只有 `0.02697 rad/s²`，MLP RMS 为 `0.05535 rad/s²`（约 2.05 倍），但绝对误差只有约 `0.054 rad/s²`；不应将这个相对比单独解释成大 yaw 力矩问题。相反，高频 W09–W14 的合并 `slope0=0.499`、轴斜率 `[0.551,0.460,0.235]`、符号正确率 53.2%，显示高频动作关系不是一个接近单位增益的映射。

六个 C00 场景的 C5 RBF teacher 姿态输出 RMS 近零（各轴均不超过约 `0.002 rad/s²`），但 MLP15 的相应场景动作 RMS 非零：逐场 RMS 范围约为 X `0.421–3.189`、Y `0.286–3.864`、Z `0.017–0.178 rad/s²`。这提供了低作用力工况下非零 MLP 输出偏置的证据；它与“单纯整体缩放偏大”不一致。

## 5. 判断与限制

1. 这不是可以由一个统一增益解释的偏差：高频斜率与低频 / 无风差别明显，轴间斜率也不同，且近零 teacher 工况存在非零 MLP 输出。简单乘一个全局比例不足以解释同状态误差。
2. 同状态证据指向高频工况的 MLP 训练状态 / 特征分布覆盖或映射拟合不足；低频组更接近但仍存在方向错误与偏置。它没有单独区分是标签与输入分布差异、模型容量/训练不足、特征语义问题，还是多个因素叠加。另一个已完成的候选输入 OOD 统计可作为佐证，但本复算本身不构成唯一因果证明。
3. reuse12 全部为 VAL，而 new60 包含 DEV 与 VAL；两批 aggregate 不可用于断言“复用 vs 新跑”造成差别。new60 raw 尚 pending parent audit。
4. 数据来源是 C5_RBF 闭环状态。MLP 输出只被离线计算，没有反馈给 Plant，因此这些动作误差不能替代 MLP15 闭环结果，也不能推出闭环稳定性或论文性能结论。

**可支持的结论**：冻结 MLP15 在相同 C5 高风姿态状态上对 C5 RBF 动作的逐事件拟合较差；低风/无风较好但非零偏置仍可见。**不能支持**：仅用全局校准即可修好、同状态 RMSE 足以推断闭环输赢、或 60 个 pending raw 已正式通过父审计。
