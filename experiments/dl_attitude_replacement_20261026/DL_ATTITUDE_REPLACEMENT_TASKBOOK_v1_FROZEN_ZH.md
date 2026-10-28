# DL1018 姿态 RBF 替代：任务书 v1（冻结）

状态：冻结研究方案，待实现源锁后启动训练。  
冻结日期：2026-10-26（Asia/Shanghai）。  
主结论依据：GHP7 54-call 对比复核见 `experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/GHP7_FULL_PILOT_ROOT_CAUSE_AND_DL_NEXT_STEP_v1.md`。

## 1. 目标与比较对象

设计一个深度学习姿态补偿头，替换 C5 attitude RBF。保留 C5 DSSM14 位置环、现有 BS 姿态名义控制器、Plant、allocator、执行器和场景；只替换 attitude RBF 输出。

主要目标是在主动变形仿真中，让候选位置误差和姿态误差都优于 B。报告与原 C5_RBF 的差异，但不要求候选位置优于 C5；所有已有 B/C5 原始记录在身份匹配时复用。C5+10 只作物理模型前馈诊断参照，不作为本方法或主要基线。

本方法运行时禁止形态依赖惯量重建和显式 observer：不计算、不读取 `Jhat`、`Jdot_hat`、Plant `rho_true/rhoDot_true`、Plant 真值力矩或 RBF 隐状态。不加入 physics feedforward F。控制器可沿用 C5 固定名义 `J0` 和原有 `dmax/beta` 输出边界；`J0` 不随形态变化。

## 2. 唯一候选架构

采用 13 输入、3 输出的因果 TCN。输入通道固定顺序：

1. BS 姿态角误差 `ai0.error`（3）。
2. 机体系角速度 `omega_body`（3）。
3. BS 名义机体系角加速度 `alpha_bs_body`（3）。
4. 当前四臂形态命令 `morph_command`（4）。

每个姿态事件 100 Hz，窗口长度 15 个事件；只包含当前与过去 14 个事件。左侧不足长度以训练归一化后的零填充。网络由 3 层因果 `Conv1d` 组成，通道数 32、kernel size 3、dilation 1/2/4、每层 ReLU；最后用 pointwise 线性层输出三轴残差角加速度。无 BatchNorm、无未来特征、无在线权重更新。

网络原始输出以 TRAIN 集逐轴 RMS 反归一化，按 C5 attitude 的 `dmax` 裁剪并乘现有 startup `beta`。它作为 `attitude_bs_step` 的 `estimateTorque`：

`estimateTorque = J0 * beta * clip(r_hat, -dmax, +dmax)`

BS 现有代码从名义力矩中减去 `estimateTorque`。`J0`、`dmax`、`beta_rise_time` 从冻结 C5 配置取值并写入新 release lock；不把配置外插成变形惯量估计。

## 3. 训练目标与数据身份

训练/验证只用既有 B raw 的 768 TRAIN 场景与 48 VAL 场景，来源由 `reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json` 锁定。读 raw `.mat` 时逐文件核对 manifest SHA-256；只读原数据，不覆盖缓存、模型或 raw。旧 `C*` 标注和 X18/X29 特征不作为本轮训练目标/输入；它们只用于审计谱系。尤其旧 `C*` 由仿真 Plant 的 J/Jdot 构造，属于物理特权标签，不能当作纯观测监督。

每个 10 ms 姿态事件 k 的监督目标是后续一个事件间隔的角加速度残差：

`r_k = (omega[k+10] - omega[k]) / 0.010 - alpha_bs_body[k]`  （rad/s²）

该标签只从 B raw 的状态序列差分得到，不使用形态真值、J/Jdot、仿真外力或未来数据作输入。标签允许离线读取事件之后的状态；推理特征必须完全因果。以 TRAIN 场景拟合特征均值/尺度及输出逐轴 RMS；窗口不得跨场景。VAL 仅用于 checkpoint 选择，不参加归一化、优化或梯度更新。

原始 1 ms 日志以每 10 个 transitions 取一个 10 ms 角速度差分标签；事件时间、事件行和下一事件的 state index 必须严格配对。若原始数据字段、时间步或 SHA 任一不一致，则在数据导出阶段终止，不回退到旧 C* 标签。

## 4. 固定训练方案

- 训练场景：manifest 中全部 768 个 TRAIN；模型选择：全部 48 个 B VAL 场景，按 scene 等权平均、逐轴按 TRAIN RMS 归一化的残差预测 RMSE 最低；并列选最早 step。
- 单次训练，seed `2026102001`，60,000 optimizer steps，batch size 512，Adam，lr `1e-3`，weight decay `1e-5`，SmoothL1 loss，目标按 TRAIN 逐轴 RMS 归一化。固定此唯一候选，不做架构/种子/阈值搜索。
- 输出 checkpoint、输入/输出 normalizer、训练日志、scene 划分与 SHA 清单到 `experiments/dl_attitude_replacement_20261026/` 独立子目录；不写入 `models/` 或任何历史实验目录。
- 在任何 Plant 调用前完成：原 raw SHA 与 scene split 核验、Python label-only 导出审计、训练归一化审计、Causal TCN Python/MATLAB 逐样本 parity（最大绝对差 `≤1e-5`）、启动状态/限幅/因果顺序审查及源文件 SHA release。检查失败则不启动闭环。

## 5. 闭环验证顺序

1. **复用 GHP7 六场 pilot**：G1/G2/G3 × W00/W12；只新增 DL candidate 的 6 个 ACTIVE 航次。相同 payload、R_task、B、C5_RBF 身份通过 hash 核验后，复用已完成的 B 与 C5_RBF raw/score，不重跑这两臂。报告 pilot 方向与安全，不以 6 场作论文显著性结论。
2. **DEV72**：通过 pilot 的完整性/安全检查后，在既有 DEV72 scene IDs 上运行 candidate。优先复用身份严格匹配的 B/C5 数据；控制器、payload、Plant、计分口径不一致时不得伪称配对，不为凑数字覆盖历史结果。若必须补跑对照，单独记录并保持场景/配置完全配对。
3. **一次性 TEST48**：只在 DEV 决策、源码/模型/normalizer 冻结、完整 source lock 完成后运行。优先复用且只复用身份严格匹配的既有基线；TEST 成绩不得用于选 checkpoint、调输入、选 head 或改阈值，失败不得在同一 TEST 上修改后重跑声称成功。测试 ID/seed 与 v2 holdout taskbook 的封存清单绑定；payload 只能在候选冻结后生成。

先前已完成的 GHP7 六场 B/C5_RBF 记录是唯一允许直接复用的当前筛查对照；不读取未解封 TEST raw，不更改或重命名旧数据状态。

## 6. 通过标准与报告

### DEV72 放行 TEST

- 72 场完整配对，候选与 B 的位置 Q0–20 宏平均严格更低，至少 62/72 场胜；SO(3) 宏平均也严格更低，逐场胜场完整报告。
- W09–W14 与 W15 的 Q、SO(3) 组均值均不劣于 B；W15 为唯一零风组，不以 W00 代替。
- 候选所有场景 finite、完整 transitions、无 safety stop、电机饱和、广义量裁剪或 tilt limit；保留并报告所有失败场。
- C5_RBF 作为已存在的次级比较完整列出，但相对 C5 不设位置优势门槛。

### TEST48 论文证据门

- 48 场完全配对；位置 Q 与 SO(3) 都严格优于 B 的场景至少 41/48，两个场景宏平均都严格优于 B；同时按 W09–W14、W15 分组报告。
- 不宣称跨训练种子或实机泛化。按 scene 做配对不确定度分析，不把同一航次时间点当独立样本。
- 报告逐场和分组指标、逐轴误差、峰值、安全、饱和、推理耗时、输入/标签定义、训练配置、完整命令、模型/源码/data hashes、失败场和偏离方案。

## 7. 资源与保护

- 新代码、cache、checkpoint、日志和图只写入本目录；历史 raw/MAT/cache/model/账本只读，不删、不覆盖、不迁移。
- MATLAB/Plant 同时最多一个闭环重负载作业；训练最多一个 GPU 作业；不打断正在运行的实验。正式训练前复查活进程与磁盘。
- 新的 6+72+48 candidate call 总数最多 126；配对基线只在 hash 身份不合格且确需公平比较时补跑，并记入 ledger。训练一次、不得自动增加第二候选或调参轮。
- 最终目标是方法、机制与主动变形窄门应用证据共同支撑论文级仿真结果；若本轮未通过门槛，保留完整失败证据并明确下一轮决定，不把失败写成通过。
