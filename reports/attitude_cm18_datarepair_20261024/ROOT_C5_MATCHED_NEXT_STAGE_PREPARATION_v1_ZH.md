# C5 匹配姿态数据：下一阶段准备任务书 v1

状态：IMPLEMENTATION_ONLY_NO_EXECUTION。Root 于 2026-10-25 审核；本任务书不放行新 Plant、标签批次或优化器。当前 TRAIN24 串行实际实验继续，不打断。

## 唯一优先问题

检验训练轨迹由 B-position 换为冻结 C5-position 是否能降低部署分布上的姿态补偿误差。24 场先导仅支持协议与小样本机制检验，不能代替完整 TRAIN768 覆盖。不能把 C5-24 对旧 B-768 的差异称为单因素。

## 当前批准实现

1. 准备 C5 VAL48 的直接补偿目标离线重标注源码。输入既有 C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3，路径 reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json，SHA256 3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501。该清单是旧 behavior-residual，不得冒充直接目标。
2. 逐场使用其固定 raw/run_start/cache 身份；现有清单 candidate manifest 提供路径时须实际读取并绑定，不猜路径。复用已审 X18 extractor 与七项物理 helper，复算 G、E0、cStar=G\E0、target=cStar/beta。G 按显式 row-major 保存；保留理想求解残差、clip 后残差、完整分配器残差及其差，禁止混淆。保留全部1999事件与不可达/clip记录，不删难例。
3. 精确核对 canonical VAL48、T2 corrected alias/参考、C5 模型/源码身份、源缓存 X18/时间/phase/index、原始请求与分配器闭合。参考当前冻结 TRAIN24 exporter 的已修正公式，但不修改或调用其正式运行入口；仅复用现有纯 helper。不同历史 run_start schema 逐分支明确处理。
4. 新源写 experiments/attitude_position_context_probe_20261024/c5_val48_cstar_v1/，输出拟写 reports/attitude_position_context_probe_20261024/c5_val48_cstar_v1/。预算128MiB；磁盘下限30GiB；无覆盖、无Plant、无engine、无optimizer、无TEST。失败输出不得覆盖，Root审核后才执行，正式离线批次避免与正在运行的仿真争夺重负载。

## 后续受控小训练拟议协议（尚未放行实现/训练）

同一24个 canonical TRAIN、1999事件、每场zero-based 0,5,...,1995 共400拟合行。B24来自冻结B Cstar ALL816；C5-24来自本次TRAIN24。两个分支保持共同CM18架构、初始W/b、seed2026102001、60000steps、batch512、Adam lr.001/weight_decay1e-5、SmoothL1 beta1，使用同一采样索引序列。共同使用冻结A1T TRAIN-only input mean/std和target axis-RMS，避免归一化成为额外变化；明确这是诊断性共同尺度，并非重新估计各自normalizer。部署clip/beta/时序/C5不改。

使用固定最终60000步权重作主要比较，不按结果切checkpoint；C5 VAL48只作固定验证/诊断，旧B VAL48为参照，均不是新独立测试。先报告相同输入和相同目标下的物理 action residual（E0-G*beta*clip(prediction)）、逐轴/phase/task/wind/zero-basis与饱和；不能跨各自normalized score比较。是否进入闭环以及开发12场验收另行冻结，不能将离线改善当闭环成功。

若小样本支持该假设，完整C5 TRAIN目标仍为768场、可复用身份合格的本次24场；补744场按当前实测约12.6小时、约37GiB raw估算，需独立新版本预算与任务书。当前2GiB先导预算不能自动继承到全量。

## 仍未消除的分布差异

新采集保持姿态 RBF 教师，部署则是 CM18；因此只匹配位置策略，不能称为完全 on-policy 学生轨迹。即便同输入离线误差改善，也必须经后续闭环筛查才能认定可用；不得据此直接承诺所有高频或三维八字改善。完整768场采集须由pilot证据支持后另作Root决定。
