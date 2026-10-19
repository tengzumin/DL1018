# DL1018 正式论文工程：迁移、数据采集、KAN 替代与逐 Gate 执行任务书

**交付对象：GPT6LUNA / 代码执行代理。**  
**任务性质：实现并按顺序执行，不是再讨论路线。**  
**编制日期：2026-10-18。**  
**源工程：`tengzumin/DL1009`，实验分支 `codex/kan-position-repair-code`。**  
**编制时核实的分支提交：`3671d2d212af927abdb6d9149a1b249c372ac55e`。**  
**继承合同：V3.11 主干 + R2E 已生效的共享滤波修订，不是 main 分支默认入口，不是旧 V3.5 的全部合同。**

> 本文可以整体交给执行代理。先完整阅读，再实施。所有“新建”“采集”“训练”“运行”都是待执行任务；本文没有声称迁移、训练或仿真已完成。
>
> 唯一路线：先以位置 KAN **取代**位置 RBF，保持姿态 RBF；位置 Gate 通过并锁定本轮位置方案后，再以姿态 KAN **取代**姿态 RBF。两个环均保留原 BS 骨架。禁止改成 RBF+KAN 同环叠加。
>
> 执行顺序：G00 → G01 → … → G13。上一 Gate 有合格产物并判为 PASS 才能进入下一 Gate。通过后继续，不要求用户重复授权每一个正常阶段；真实失败、关键源缺失或科学合同冲突时停止并交付证据。不要用模糊报告代替实际运行。

---

## 0. 必须先理解的授权与禁止事项

### 0.1 本任务已确定，不需要再次选择的内容

1. 新工程名称为 **DL1018**，用于正式论文实验。不是“先做一版小实验再说”；DL1009 的小数据验证已经承担过探索角色。
2. DL1009 的小数据代码、关键模型和证据由用户保留。用户准备删除的只是 V3.11 大数据验证相关数据；**本任务不授权你删除 DL1009 的任何内容**。
3. DL1018 不使用 DL1009 的旧航次、旧事件文件或旧 checkpoint 作为训练/验证数据及模型初始化。可以只读参考源代码、实际配置、函数实现和旧报告。
4. DL1018 内部新采的同一条 B 航次，可以分别导出位置与姿态标签。它仍只是一条新航次，不重复采集、不重复计入运行数。
5. 旧 P_CF / P10 / V3.6 / V3.10 的模型不参加新比较，不作为新模型的 warm start。其算法函数可以作为实现来源；“参考旧结构”不等于“加载旧赢家权重”。
6. 每个环只采 **一种 Student 行为**。不要各采一整套冻结 Student 和在线 Student。
7. 正式规模已定：每环 Teacher TRAIN 1,536 条 + Student TRAIN 384 条；每环 VAL 144 条角色航次；位置 DEV24、双环 DEV24、最终 TEST48。
8. 所有正式数据和模型从 DL1018 开始建立。不要把旧执行累计、旧 1008/1700 调用上限当成新任务预算。
9. **不做 hash 扫描，不做 manifest 审计，不创建文件哈希清单，不运行全项目完整性扫描。** 合同核对使用实际参数、数组、维度、开关、时刻、运行状态和数值恒等式。
10. 保留必要的运行数据结构：`scene_specs.csv` 是场景参数表，`episode_index.csv` 是样本索引，`attempt_index.csv` 是实际运行记录。它们用于执行、训练和断点恢复，不是额外的文件完整性 manifest，不包含 SHA/MD5 列。

### 0.2 明确禁止

- 不修改 Plant 动力学以制造缺口；不改质量、惯量计算、C0 控制分配、BS 增益、RBF 中心/宽度/学习率来使 KAN 获胜。
- 不把位置/姿态 RBF 留在同环 KAN 输出下同时补偿；不把替代关系写成 augmentation。
- 不添加 TCN、MLP、GRU、LSTM、NDO、SMC、RL、滤波器新模块或新训练目标横评。
- 不恢复 X37，不把真实臂长、真实臂长变化率、积分重建臂长、风力真值、Plant 参数真值偷放进部署输入。
- 不把位置 KAN 采样率改成 1 kHz；不把 Plant 1 ms 与网络/自适应 10 ms 混为一谈。
- 不把关闭 Head 更新实现成清空 readout、清空 W0、停止网络输出、令 beta=0 或关闭 PCF 辅助状态。
- 不把 `trainable=False` 当成“离线不训练”；编码器和 readout 在离线训练时都应可训练，部署时编码器始终固定。
- 不重新运行同一个完整航次只为生成第二份报告；不通过更换 seed、删去高频或跳过 W08 填补物理失败。
- 不自动扩大数据量、搜索超参数、改 Gate 阈值、补充第二轮 Student、做数据量横评或训练种子横评。
- 不执行 `git reset --hard`、`git clean`、覆盖源 checkpoint、清理源目录、自动提交/推送/合并。
- 不宣称有限时长未发散等于 Lyapunov 稳定证明，不宣称离线残差 RMSE 改善等于闭环 Q/A 改善。

### 0.3 本任务内允许的最小必要修改

- 将当前有效代码迁到 DL1018，解除运行时对 DL1009 路径及旧模型的依赖。
- 用显式配置构造 V3.11/R2E 合同，替代依赖旧 `run_start.mat` 加载配置的机制。
- 新建本任务规定的场景参数表、采集入口、事件导出、数据加载与训练入口。
- 修复已知标签映射错误、RBF-update 与网络-event 混用、冻结模式的过强断言、运行依赖遗漏、错误状态被吞掉、epoch0 未入选模等问题。
- 为姿态分支增加本任务规定的“同一 Initial → 单一 Student → Final 候选”训练步骤；不改变 X29 网络结构或现有姿态 Head 更新算法。
- 精简无关日志和重复存储；前提是保留下面要求的复核所需信号，且不改变任何控制算术或采样时序。

---

## 1. 工程路径、源版本与查找次序

### 1.1 默认本地路径

```text
SRC_ROOT = C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009
DST_ROOT = C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018
REPO     = tengzumin/DL1009
BRANCH   = codex/kan-position-repair-code
REF      = 3671d2d212af927abdb6d9149a1b249c372ac55e
```

先检查以上路径，不要把 `drone_tcn_bs` 下的历史项目当成当前源。若执行环境已有明确的同一工程挂载根目录，允许通过 `DL1009_ROOT`、`DL1018_ROOT` 环境变量替换根路径；所有子路径仍按本文。不得在不知道目录身份时到全磁盘挑一个同名目录。

`DST_ROOT` 不存在则创建。已存在时只检查是否本任务工程，保留已有文件，进入幂等恢复；遇到同名但不同合同的产物停止，禁止整目录覆盖。

### 1.2 源版本定位规则

- 先读取本地实际入口和配置。记录当前分支/提交信息作为来源说明；这不是文件 hash 审计。
- 不将 `main` 视为最新 V3.11；编制时 main 仍是较早基线提交。
- 在线核对或恢复缺少的已跟踪源代码时，使用上面指定的实验分支及 REF。可以使用 `git show REF:相对路径` 或连接的 GitHub 文件读取，不要切换或 reset 用户正在工作的源工作区。
- 如果本地源比 REF 更新，逐项比较与本任务有关的有效合同。完全一致的纯编排修订可以采用并记录；任何 Plant/控制/输入/标签/频率/Head 数值变化均不得自动并入。
- 本文使用“最新 V3.11”指编制时已经核实的 **V3.11/R2E 实际合同**。后来的未知提交不能仅因为日期更晚就自动替换合同。

### 1.3 必须读取的合同来源（相对 SRC_ROOT）

```text
RBF-BS0/experiments/multitask_retrain_v311/configs/V311_FROZEN_OPTIONS.json
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/frozen_sources_v311.m
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/controller_options_v311.m
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/run_position_stage1_closed_loop_v311.m
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/make_scenes_v311.m
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/attitude_events_v311.m
RBF-BS0/experiments/multitask_retrain_v311/local_runtime/final_metrics_v311.m
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/configs/R2E_PROTOCOL.json
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/configs/R2E_SHARED_FILTER_CONFIG.json
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/local_runtime/r2e_controller_options.m
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/local_runtime/run_r2e_stage.m
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/local_runtime/evaluate_r2e_gate.m
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/training/train_position_r2e.py
RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/training/train_attitude_r2e.py
```

源 JSON 中旧场数、旧预算、`OLD_P10` 数据角色、是否必须加载旧模型等，是旧编排字段，不继承。数值物理/控制合同按本文件第 3 节继承。新场数、Student 身份、训练阶段、DEV/TEST 数量以本文为准。

### 1.4 有效配置的提取，禁止恢复旧模型依赖

按以下顺序确定源有效 `cfg` / 基础 `opts`：

1. 优先读取本地存在的：
   `RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/configs/R2E_EFFECTIVE_CONFIG.mat` 中的 `cfgEffective`，与 R2E 配置 JSON 和核心函数核对。
2. 若该文件不存在，读取 `frozen_sources_v311.m` 指向的配置来源：
   `RBF-BS0/experiments/x23_head_v38/runs/canary/attempt_6ac495b3-a44c-4564-ac6a-1d76221e4287/run_start.mat`，**只取 cfg/opts 的非训练参数**，应用已核实的 R2E `[Inf;Inf;6]` 滤波修订。
3. 若二者均不存在，可用本提交的核心参数生成函数和本文数值表显式构造；只有所有列出的活动配置均有源码依据并通过参数核对时才允许通过 G00。未知的活动覆盖项不得靠“应该差不多”补出。
4. 源文件可以只读作为合同证据，但不得把其中位置/姿态网络权重、归一化数组、原航次状态或原场景拷贝为新训练输入。
5. 新 `configs/effective_config.mat` 及 `contract_dl1018.json` 应不含旧模型和旧数据路径；DL1018 的正常入口不能再调用 `frozen_sources_v311`。

### 1.5 已核实的 GitHub 发布缺口：必须提前处理

当前主循环调用以下旧 helper：

```text
RBF-BS0/experiments/x29_head_v39/local_runtime/attitude_model_feature_x29_v39.m
RBF-BS0/experiments/x29_head_v39/local_runtime/attitude_kan_head_step_v39.m
RBF-BS0/experiments/x29_head_v39/local_runtime/trim_head_audit_v39.m
```

编制时 `attitude_kan_head_step_v39.m` 的该 GitHub 路径读取返回 404；源主循环仍明确调用它。最新路径审计记录了本地 `trim_head_audit_v39.m` 的上述路径，并记录过因 helper 未加路径导致的运行失败。**不要因此宣称 GitHub 已经包含完整可独立运行包。**

执行者应先从上面精确本地路径读取并迁移。这些是算法/日志函数，不是要复用的旧模型。若缺少活动姿态 Head 算法文件，停止 G00，报告 `BLOCKED_MISSING_AUTHORITATIVE_HELPER` 和缺失路径；禁止凭函数名、通用 Lyapunov 模板或别的 Head 公式自行重建。纯裁剪日志 helper 可在明确输入/输出结构后做等价实现，但必须通过空审计、单事件和多事件数值测试，不能改变控制计算。

---

## 2. 最小迁移映射与目标目录

### 2.1 核心算法迁移

将以下源目录中的**活动基础函数及其确定的函数依赖**迁移到 `DST_ROOT/matlab/core/`：

```text
源目录：RBF-BS0/code/code/

必须包含：
default_config.m
simulation_parameters.m
controller_parameters.m
arm_directions.m
arm_mass_properties.m
distributed_mass_properties.m
allocation_matrix.m
allocate_control.m
position_bs_step.m
attitude_bs_step.m
baseline_force_to_attitude.m
command_filter_init.m
command_filter_step.m
rbf_event_scheduler_step.m
rbf_mimo_basis.m
rbf_mimo_update.m
rk4_vehicle_step.m
vehicle_derivative.m
morphology_aware_wind_load.m
wind_velocity_profile.m
tcn0916_morphology_scenario.m
tcn0916_topologies.m
```

如上述函数调用同目录其他基础函数，读取后只补对应依赖。可以保留无副作用的辅助函数，但不要把 `run_RBFBS0_baseline.m`、`run_baseline_closed_loop.m`、旧 test 入口、历史场景/结果一股脑设为新正式入口。正式 Plant 主循环只允许有一个。

### 2.2 学习与控制运行函数迁移表

| 源相对路径 | 目标与处理 |
|---|---|
| `.../multitask_retrain_v311/local_runtime/run_position_stage1_closed_loop_v311.m` | `matlab/runtime/run_dl1018_closed_loop.m`；保留活动控制算术和时序，改入口名/路径/必要冻结断言/规范日志，不重写动力学 |
| `.../multitask_retrain_v311/local_runtime/controller_options_v311.m` | 实现 `matlab/runtime/controller_options_dl1018.m`；使用第 4 节矩阵，无旧模型加载 |
| `.../kan_position_attitude_followup_v2/local_runtime/position_stage1_model_forward_v2.m` | `matlab/models/position_stage1_model_forward_v2.m`，原前向算法 |
| `.../position_advantage_stage1_v1/methods/position_stage1_update_head.m` | `matlab/models/position_stage1_update_head.m`，原更新公式 |
| `.../k1_command_filter_update_coordination_v3_5/local_runtime/position_stage1_update_head_pcf_v3_5.m` | `matlab/models/`，原学习面协调公式 |
| `.../k1_command_filter_update_coordination_v3_5/local_runtime/position_filter_realization_pcf_step_v3_5.m` | `matlab/models/`，原 eta 精确保持输入更新 |
| `.../attitude_kan_legal_input_reuse_upgrade_v3_6/local_runtime/attitude_feature_row_v3_6.m` | `matlab/data/`，只启用 X29，不启用 X33 |
| 第 1.5 节三个 `x29_head_v39` helper | `matlab/models/`，本地原文件只读迁移；缺算法源时不得猜 |
| `.../position_advantage_stage1_v1/methods/stage1_events_from_log.m` | 参考后实现 `matlab/data/export_position_events_dl1018.m`；修复方法名识别，按实际施加量导出 |
| `.../multitask_retrain_v311/local_runtime/attitude_events_v311.m` | 参考后实现 `matlab/data/export_attitude_events_dl1018.m`；修复事件掩码与 Student 总行为力矩 |
| `.../multitask_retrain_v311/local_runtime/make_scenes_v311.m` | 抽取参考轨迹与物理生成方式到 `matlab/scenes/`；按第 6 节新分配，不调用旧 BUILD/manifest/hash 分支 |
| `.../multitask_retrain_v311/local_runtime/final_metrics_v311.m` | `matlab/metrics/metrics_dl1018.m`；保留 Q/A 的定义，补全失败时段标记 |
| `.../k1_command_filter_update_coordination_v3_5/local_runtime/measure_pcf_v3_5.m`（如源活动路径使用） | 只迁移被指标调用的纯测量逻辑；不依赖旧 W0 或旧模型文件 |
| `.../kan_position_attitude_followup_v2/training/train_models_repair_v2.py` | 抽取 PositionModel / spline 基函数 /导出结构到 `training/models.py`；不执行其旧路径/manifest/hash 主程序 |
| `.../attitude_kan_legal_input_reuse_upgrade_v3_6/training/train_initial_models_v3_6.py` | 抽取 AttitudeModel / X29 spline /导出结构到 `training/models.py`；不调用四架构横评 |
| `.../cf_shared_retrain_r2e/training/train_position_r2e.py` | 参考其 Initial→Final/epoch0 逻辑，写 `training/train_position.py` |
| `.../cf_shared_retrain_r2e/training/train_attitude_r2e.py` | 参考合法 X29、TRAIN-only normalizer、单位与评分，写 `training/train_attitude.py` 并增加一次 Final |

表中的 `...` 均指 `RBF-BS0/experiments`，不是让你搜索别的仓库。

### 2.3 目标结构

```text
DL1018/
  README.md
  run_dl1018.py                       # 唯一总编排入口，支持单 Gate / 顺序执行 / 状态查询
  configs/
    contract_dl1018.json              # 明确数值与版本，不含文件 hash
    effective_config.mat
    scene_specs.csv                   # 888 行场景参数：768+48+24+48
    dataset_plan.json                 # 角色/数量/权重/阶段
    selected_models.json
  matlab/
    core/
    models/
    runtime/
      init_dl1018.m
      controller_options_dl1018.m
      run_dl1018_closed_loop.m
      run_episode_dl1018.m
      run_gate_dl1018.m
    scenes/
    data/
    metrics/
    tests/
  training/
    models.py
    data.py
    common.py
    train_position.py
    train_attitude.py
    export_matlab.py
    tests/
  data/
    raw/<split>/<scene_id>/<collector_id>/attempt_01/raw_run.mat
    events/position/<split>/<scene_id>/<collector_id>.h5
    events/attitude/<split>/<scene_id>/<collector_id>.h5
  models/
    position/initial/
    position/final_candidate/
    position/selected/
    attitude/initial/
    attitude/final_candidate/
    attitude/selected/
  logs/
    attempt_index.csv
    episode_index.csv
    gate_status.json
    commands.log
  reports/
    contract_check.json
    G00_MIGRATION.json ... G13_FINAL_REPORT.json
    POSITION_DEV.csv
    ATTITUDE_DEV.csv
    FINAL_TEST.csv
    FINAL_REPORT.md
```

允许把很小的共用函数合并，禁止为每次继续运行再复制一套 `continuation_01/02/03` 入口。不要生成每阶段大量重复 MD；用每 Gate 一个 JSON、必要结果 CSV 和最终一份报告即可。

### 2.4 路径隔离

新 MATLAB 进程初始化时从干净路径开始，只加入 DL1018 必要子目录。不要 `addpath(genpath(SRC_ROOT))`，不要让旧函数遮蔽迁移函数。

对活动入口、前向、位置 Head、姿态 Head、标签导出及**运行结束时的日志处理**都做 `which -all` 检查。解析结果必须落在 DL1018；多路径冲突先解决，不许靠路径顺序碰运气。

训练模块不得保留读取 DL1009 的全局 `ROOT/EXP/MANIFEST/DATA`。仅抽取类定义还不够，要测试导入时没有读取旧数据或执行旧审计的副作用。

## 3. 最新 V3.11/R2E 的有效物理与控制合同

下面是迁移的数值合同，不是供执行者搜索的超参数空间。凡与源码/有效配置矛盾，停止并给出字段、两边数值及来源，不静默覆盖。

### 3.1 Plant、几何、执行器

| 项目 | 固定值/固定定义 |
|---|---|
| 质量模型 | `distributed_v1` |
| 总质量 | 0.695 kg，由既定分量质量组成；不得换回早期旧质量 |
| 重力 | 9.8 m/s² |
| Plant 步长 | 0.001 s |
| 每航次 | 20 s，20,000 个 transitions，20,001 个状态样本 |
| 构型 | X 型，`pi/4 + (0:3)*pi/2` |
| 臂长含义 | 机体原点至旋翼中心的径向距离，不是伸缩杆净长度 |
| 臂长初值/范围 | 四臂初值 0.15 m；范围 [0.15, 0.25] m |
| 根部半径 | 0.118/2 m |
| 变臂速度 | 0.05 m/s；沿用原形态发生器 |
| 长臂保持 | 每个活动臂实际到达目标后至少 5 s |
| 位置状态参考 | `instantaneous_total_cog` |
| 内部变形动量模型 | `neglected_quasi_static`；不擅自增加或删减物理项 |
| 舵机安装 | `root_fixed` |
| 推力系数 kf | 1.70e-6 N/(rad/s)² |
| 反扭矩系数 km | 3.20e-8 N·m/(rad/s)² |
| 电机范围 | [0, 1900] rad/s |
| 电机一阶时间常数 | 0 s，沿用当前无额外电机延迟合同；不新增滞后 |
| 控制器最大倾角 | pi/6 rad；不要与安全停止的 pi/3 混淆 |
| 机体投影面积 | [0.008240355616, 0.007699184218, 0.027129155540] m² |
| 风面积参考臂长 | 每臂 0.141623 m；不能替换成初始臂长 |
| 风力/力矩 | 沿用 morphology_aware_wind_load 和既有风载模型；force scale=1 |
| 风载参数 | rho_air=1.225 kg/m³，CdBody=1，CdArm=1；风速上升时间 0.8 s |
| 初始状态 | zeros(12,1) |
| 数值推进 | 沿用当前 RK4 主循环与 Plant 形态/风更新位置，不另建第二个动力学积分器 |

分量质量：body=0.130、battery=0.145、每臂 arm=0.040、motor=0.035、rotor=0.005、servo=0.025 kg。分量几何及质量属性函数从源文件原样迁移。

`cfg.plant.inertia=diag([.012,.012,.022])` 在默认文件中存在，但 **distributed_v1 的实际 J0 必须由质量属性函数生成**。禁止直接把这个占位矩阵写成控制器有效 J0。

广义量限幅按现有公式生成，不人为加大：

```text
F_one_max = kf * 1900^2
T_max     = 4 * F_one_max
Mx_bound  = sqrt(2) * 0.15 * F_one_max
My_bound  = Mx_bound
Mz_bound  = 2 * km * 1900^2
min       = [0, -Mx_bound, -My_bound, -Mz_bound]
max       = [T_max, Mx_bound, My_bound, Mz_bound]
```

实际电机分配与限幅继续调用原 `allocate_control`，不改成其他 allocator。

### 3.2 控制器已知模型与信息边界

- 所有正式方法都使用固定初始构型生成的名义 `J0`、`C0`。调用 `controller_parameters(...,'fixed')`。
- 新有效配置显式设 `controller_morphology_mode='fixed'`；相关同义活动字段保持一致，不能依赖默认 `'morph'`。
- `controller_inertia_derivative_mode='full'` 保留；在固定名义构型下名义 Jdot 为零，不等于删掉 Plant 的真实 Jdot。
- 每步真实 Plant 仍根据真实变臂计算质量属性与真实分配；controller/allocator 不能读取真实构型替换 C0。
- 位置输入允许四通道当前发出的离散变臂命令 {-1,0,+1}；这不是长度测量，也不是连续臂长估计。
- `rho_hat` 保持名义初始值、`rhoDot_hat=0`，不新建积分形态估计器。
- 不在本任务额外添加噪声、滤波、估计延迟或传感器模块。仿真状态观测沿用 V3.11；不据此宣称已验证真实传感器条件。
- 真值只可进入 Plant、离线标签或诊断字段。训练输入只读取第 9 节白名单。

### 3.3 BS 与命令滤波

| 项目 | 值 |
|---|---|
| 位置 BS k1 | [1,1,1] |
| 位置 BS k2 | [4,4,4] |
| 姿态 BS k1 | [1.5,1.5,1.3] |
| 姿态 BS k2 | [22.5,22.5,12.7] |
| command filter wn | [18,18,12] rad/s |
| damping | [1,1,1] |
| **有效加速度限幅** | **[Inf,Inf,6] rad/s²** |

重要：`default_config.m` 的 `[8,8,6]` 不是本任务的有效滤波限幅。R2E 已生效修订是 `[Inf,Inf,6]`，所有方法、Teacher、Student、DEV/TEST一致采用。只把这项换回8会制造另一套合同。

位置误差方向与接口：

```text
e_p = p_ref - p
s_p = v_ref + k1 .* e_p - v
a_nom = a_ref + k1 .* (v_ref-v) + e_p + k2 .* s_p
F_cmd = m0 * a_nom - F_est
```

- B：`F_est = 实际施加的原位置RBF残差力`。
- POS_OFF：`F_est = 0`。
- 位置 KAN：`F_est = m0 * a_KAN_applied`，不加 RBF。
- 加速度→力只乘一次 m0；力→加速度只除一次 m0；不改变原误差符号。

姿态状态是 `[roll,pitch,yaw]` 及机体系角速度 `omega_B`。原 BS 使用 Euler 误差面，先通过 `T\(eta_ddot_virtual - Tdot*omega)` 转成机体系角加速度，再形成名义力矩。禁止把 Euler 二阶导直接当机体系角加速度。

### 3.4 基线 B 的 RBF 合同

| 项目 | 位置 RBF | 姿态 RBF |
|---|---|---|
| 有效运行频率 | 100 Hz | 100 Hz |
| 中心数量 | 35，按源对称选中心函数 | 81，按源对称选中心函数 |
| 输入维数 | 3 | 6 |
| input_scale | [6,8,10] | [.6,4,.6,4,.6,3] |
| 原 gamma | 1.2 | [2.1,2.25,1.1] |
| 活动 gamma_scale | 5 | 19 |
| sigma（高斯宽度） | .95 | 1.2 |
| sigma_w（泄漏） | .002 | [.11,.12,.20] |
| 权重元素限幅 | ±60 | ±60 |
| 输出加速度限幅 | ±[3,3,3] m/s² | ±[45,45,4.7124] rad/s² |
| 学习面限幅 | ±[7,8,10] | ±[2.3,2.3,1.4] |
| beta 上升时间 | 1.8 s | 2.2 s |

基线 gamma_scale 只施加一次。不要既改 cfg.gamma 又在 opts 中再乘一次。保持原中心、基函数归一化、输出前/更新后顺序及 ZOH。不要把这些 RBF gamma 参数套用到 KAN Head。

`formal_rbf_baseline=true`，主循环方法仍是 `B2-RBF-Full-SPLIT`。Plant 1 kHz 并不意味着 RBF 或 KAN 1 kHz 更新。

---

## 4. 控制方法与 Student 身份：逐个写死

### 4.1 方法矩阵

| ID | 位置 RBF输出/更新 | 位置KAN | 位置Head | 姿态RBF输出/更新 | 姿态KAN | 姿态Head |
|---|---|---|---|---|---|---|
| B | 开/开 | 无 | 无 | 开/开 | 无 | 无 |
| POS_OFF | 关/关 | 无 | 无 | 开/开 | 无 | 无 |
| P_INIT_STUDENT | 关/关 | 本轮 Position Initial | 原PCF在线 | 开/开 | 无 | 无 |
| P_F | 关/关 | Position Selected | 冻结 W0 | 开/开 | 无 | 无 |
| P_A | 关/关 | 与P_F同一模型 | 原PCF在线 | 开/开 | 无 | 无 |
| P_STAR | 继承入选P_F或P_A | 同入选配置 | 同入选配置 | 开/开 | 无 | 无 |
| A_INIT_STUDENT | 同P_STAR | 固定P_STAR | 同P_STAR | 关/关 | 本轮 Attitude Initial | **冻结，DeltaW=0** |
| PA_F | 同P_STAR | 固定P_STAR | 同P_STAR | 关/关 | Attitude Selected | 冻结，DeltaW=0 |
| PA_A | 同P_STAR | 固定P_STAR | 同P_STAR | 关/关 | 与PA_F同一模型 | 原v39在线增量Head |

这里 `P_STAR` 是指向本轮选定配置的逻辑身份，不是旧 P_CF。若入选P_F，则PA_F/PA_A的位置Head都冻结；若入选P_A，则两者的位置Head都在线。不能在姿态Head消融时同时切换位置Head。

### 4.2 单一 Student 采集策略

- **位置 Student 只采 `P_INIT_STUDENT`。** 保留 V3.11 的本轮Initial + 原位置PCF在线Head方式，TR384/VA48。不要另采冻结位置Student。
- **姿态 Student 只采 `A_INIT_STUDENT`。** 固定本轮P_STAR，合法X29姿态Initial冻结Head，TR384/VA48。参考旧V3.6的冻结姿态行为，不采GRU、不采另一套在线姿态Student。
- 每个collector在开始采集前冻结模型、normalizer和全部活动选项；采集期间不能改模型、每隔几十条重新训练或自作主张切模式。
- 每条航次的在线权重重置，不能跨场保留在线学习状态。
- Teacher 不是人工网络标签：这里Teacher指数据的行为控制器。标签使用第10节物理定义，不能改为模仿RBF输出。

### 4.3 必须修复的冻结模式入口冲突

源 `with_position_head` 和主循环的PCF断言会要求 `update_enabled=true`，这与本任务 P_F 消融冲突。允许在DL1018副本中做以下**唯一语义扩展**：

- PCF协调开启要求“位置KAN运行开启”，不再强制“位置Head必须更新”。
- P_F仍运行同一encoder、phi、W0前向、beta、限幅、事件缓存、ZOH和eta更新。
- P_F分支使 `weightNext=weightBefore`，不执行泄漏、不投影改变W0，权重变化必须严格为零。
- P_A分支原更新公式、乘法次序与PCF学习面不变。
- source代码中的在线模式必须与DL1018在线模式逐事件数值一致。

不要靠移除PCF协调来让冻结断言通过。姿态λ固定为1，属于完全替代；不能退回0.25、0.5等融合权重。

---

## 5. 数据总量与阶段依赖：不要再自行增减

### 5.1 每环的逻辑数据池

| 位置数据角色 | TRAIN | VAL |
|---|---:|---:|
| B | 768 | 48 |
| POS_OFF | 768 | 48 |
| P_INIT_STUDENT | 384 | 48 |
| 合计 | **1920** | **144** |

| 姿态数据角色 | TRAIN | VAL |
|---|---:|---:|
| B（DL1018内部同一批B新航次） | 768 | 48 |
| P_STAR | 768 | 48 |
| A_INIT_STUDENT | 384 | 48 |
| 合计 | **1920** | **144** |

注意：位置P_INIT_STUDENT与姿态Teacher P_STAR不是同一身份。即便位置Selected最后等于Initial，也按本计划为P_STAR完成正式采集；不要擅自利用“可能一样”变更本任务新采配额。唯一预先批准的跨环航次共享是B，以及DEV中已经锁定P_STAR的同场结果。

### 5.2 各 Gate 的名义新增 Plant 数

| Gate | 新增内容 | 调用数 |
|---|---|---:|
| G00/G01 | 迁移、数值单元测试、场景生成预检 | 0 |
| G02 | 位置Teacher：TRAIN1536 + VAL96 | 1632 |
| G03 | 位置Initial训练/导出/无Plant前向一致性测试 | 0 |
| G04 | 单一位置Student：TRAIN384 + VAL48 | 432 |
| G05 | 位置Final训练/选模 | 0 |
| G06 | DEV24 × B/P_F/P_A | 72 |
| G07 | 姿态Teacher P_STAR：TRAIN768 + VAL48；B标签只导出 | 816 |
| G08 | 姿态Initial训练 | 0 |
| G09 | 单一姿态Student：TRAIN384 + VAL48 | 432 |
| G10 | 姿态Final训练/选模 | 0 |
| G11 | 同一DEV24 × PA_F/PA_A；B/P_STAR来自G06 | 48 |
| G12 | TEST48 × B/P_F/P_A/PA_F/PA_A | 240 |
| G13 | 汇总 | 0 |
| 总计 | 所有Gate通过、所有比较方法可安全完成时 | **3672** |

其中唯一的新TRAIN采集为3072次，VAL采集240次，DEV120次，TEST240次。3672是本计划工作量，不是要求失败也必须跑满，不是调用硬上限，也不包含获准的工程错误修复重试。每次真实启动都如实记录，但不要搬用DL1009的旧累计上限。

每个大采集阶段的首批安全检查取自该阶段正式清单，成功就计入正式目标，不能另起一批不必要的 canary。本文不授权数据量48/96/192横评或多模型多seed大横评。

### 5.3 “场景”“轨迹”“episode”的口径

- 参考轨迹类型只有 HELIX、FIG8_3D、SQUARE 三种。
- 一个场景是一个完整外部输入实现：参考、初态、机臂时序、风速方向/相位等。
- 一个episode是一个collector在该场景上运行一次。
- 同场B/POS_OFF/Student是多条行为航次，不是多个独立外部场景。
- 同一B raw被两个环导出标签，只计一次Plant；不同事件H5不额外算航次。
- 1920是每环TRAIN的角色航次数，不能写成1920种轨迹或1920组独立风场。

---

## 6. 场景分配的精确规则

所有整数编号从0起，落地参数表保留文本名称和数值编号。

```text
t=0: HELIX
t=1: FIG8_3D
t=2: SQUARE

c=0..15:
0 NONE, 1 "1", 2 "2", 3 "3", 4 "4", 5 "12", 6 "13", 7 "14",
8 "23", 9 "24", 10 "34", 11 "123", 12 "124", 13 "134", 14 "234", 15 "1234"

w=0..14: band=floor(w/3), level=w mod 3
w=15: 无环境风 W15
```

### 6.1 TRAIN：768组，Teacher完整交叉

```python
TRAIN = [(t,c,w) for t in range(3) for c in range(16) for w in range(16)]
```

B和POS_OFF分别运行全部768组；姿态Teacher P_STAR也运行同一TRAIN外部场景集合。

### 6.2 Student TRAIN：384组，固定均衡半组合

```python
S = {0, 2, 4, 6, 9, 11, 13, 15}
STUDENT_TRAIN = [(t,c,w) for (t,c,w) in TRAIN
                 if (w - c - 3*t) % 16 in S]
```

位置Student和姿态Student都使用这份384组外部场景子集，控制器不同。

必须由程序断言，而不是报告文字声称：

- 总计384；每任务128。
- 每个任务×构型恰好8个风单元。
- 每个任务×风单元恰好8种构型。
- 每个任务×构型在五个非零风频带中各至少出现一次；W15对构型的出现为均衡分配，不要求每个构型都有。
- 每个风单元全三任务共24条Student；W08不能缺。
- W09–W14 Student共144条，每任务48条。
- 不把这份半组合写成“每个三元组合都被Student覆盖”。完整三元组合覆盖只属于Teacher TRAIN。

### 6.3 VAL：48组

```python
VAL = [(t,c,(c+3*t+7)%16) for t in range(3) for c in range(16)]
```

VAL的外部实现与TRAIN不同，采用本节后面的独立split seed和频率数组。每个角色均在这48组上运行：位置阶段B/POS_OFF/P_INIT_STUDENT；姿态阶段B/P_STAR/A_INIT_STUDENT。

每任务16组、16构型各1组、16风单元各1组。VAL是选模集，允许用于Initial/Final模型选择，不允许进入梯度训练。

### 6.4 DEV：24组，固定下表，不许执行者挑有利场景

| task | c | w |
|---|---:|---:|
| HELIX | 0 | 3 |
| HELIX | 1 | 15 |
| HELIX | 4 | 0 |
| HELIX | 5 | 6 |
| HELIX | 7 | 8 |
| HELIX | 10 | 9 |
| HELIX | 11 | 12 |
| HELIX | 15 | 14 |
| FIG8_3D | 0 | 4 |
| FIG8_3D | 2 | 15 |
| FIG8_3D | 3 | 1 |
| FIG8_3D | 6 | 7 |
| FIG8_3D | 8 | 8 |
| FIG8_3D | 9 | 10 |
| FIG8_3D | 12 | 13 |
| FIG8_3D | 14 | 14 |
| SQUARE | 0 | 5 |
| SQUARE | 3 | 15 |
| SQUARE | 5 | 2 |
| SQUARE | 6 | 8 |
| SQUARE | 9 | 9 |
| SQUARE | 10 | 11 |
| SQUARE | 13 | 12 |
| SQUARE | 15 | 14 |

全DEV覆盖16构型和16风单元；每任务只有8组，不能要求/声称每任务覆盖全部16构型。每任务均包含W08、W15及高频代表。把W15安排在非NONE构型，避免同一零风/不变臂/同参考的确定性场景被换seed后冒称独立。

G06和G11用完全同一DEV外部输入。G11只新增两种姿态KAN，不重新跑G06已完成的B/P_STAR。

### 6.5 FINAL_TEST：48组

```python
TEST = [(t,c,(c+3*t+11)%16) for t in range(3) for c in range(16)]
```

每任务16构型、16风单元各出现一次。独立性来自新的外部实现和未参与选模，不是“这些频带从未在训练中出现”。

TEST的参数生成/无Plant安全边界检查可在G01做；**G12之前不启动TEST Plant，不生成TEST标签，不读取TEST预测/误差来选模。** 参数表可存储场景定义，不得把“封存测试”误解成不能预先定义测试输入。

### 6.6 split、seed及scene_id

```text
new split_code: TRAIN=0, VAL=1, DEV=2, TEST=3
scene seed = 2026101800 + 10000*split_code + 1000*t + 16*c + w
scene_id   = DL1018_<SPLIT>_T<t+1>_C<c:02d>_W<w:02d>
```

seed必须唯一、非负且小于2^31。使用MATLAB `RandStream('mt19937ar','Seed',seed)` 生成两正弦相位，顺序固定为phi1再phi2。不要用Python随机数替换MATLAB波形生成后期待相同序列。

位置与姿态、各角色在同一scene_id下使用同一套场景数组。不要让collector_id参与外部随机数seed。

---

## 7. 参考轨迹、风扰和变臂：继承物理发生器，只扩展分配

### 7.1 参考轨迹

时间 `t_grid=(0:0.001:20)'`。沿用 V3.11 `make_reference` 的公式，三类yaw均为0，yaw_rate与yaw_acceleration均为0。

HELIX和FIG8_3D使用：

```text
s=t/20, u=10*s^3-15*s^4+6*s^5
u_dot=(30*s^2-60*s^3+30*s^4)/20
u_ddot=(60*s-180*s^2+120*s^3)/400
v=p_u*u_dot
a=p_uu*u_dot^2+p_u*u_ddot
```

- HELIX：`theta=3*pi*u`；`p=[1.2*(cos(theta)-1), 1.2*sin(theta), 2*u]`。
- FIG8_3D：`theta=2*pi*u`；`p=[1.5*sin(theta), sin(2*theta), .4*u+.35*(1-cos(2*theta))]`。
- SQUARE：点列 `[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0]`，四段各5 s；每段使用同一五次平滑h、解析一阶和二阶导数。

直接迁移源解析导数实现，并检查参考数组有限、角点位置连续、速度/加速度符合源公式。不要另换七阶直线轨迹，不把SQUARE替换为悬停或圆。

### 7.2 风单元的频率表

这里频率数组的第三维是 **split**，不是task。不要误读为三个任务分别使用三张表。

| band（w对应三种幅值） | TRAIN f1/f2 Hz | VAL与DEV f1/f2 Hz | TEST f1/f2 Hz |
|---|---|---|---|
| 0：W00–W02 | .20 / .40 | .25 / .45 | .30 / .50 |
| 1：W03–W05 | .50 / .80 | .58 / .87 | .65 / .95 |
| 2：W06–W08 | 1.00 / 1.60 | 1.15 / 1.75 | 1.30 / 1.90 |
| 3：W09–W11 | 2.00 / 3.00 | 2.20 / 3.20 | 2.40 / 3.40 |
| 4：W12–W14 | 3.80 / 5.00 | 3.70 / 4.80 | 3.60 / 4.60 |

幅值level 0/1/2分别为 `[A1,A2]=[1.5,1.0]、[3.5,2.45]、[4.5,3.5]` m/s；均值V0=9 m/s。最大理论风速17 m/s，小于源约束18 m/s。

W15环境风速数组为零，不代表无人机飞行相对空气阻力一定为零。不要据W15把物理风载函数强行置零。

按源 `wind_velocity_profile` 构造biased dual sine及0.8 s上升，不自己更改包络。风频率是输入风速频率，不保证力、力矩或残差只含这些频率。

### 7.3 外部实现参数的确定规则

扩展组合后原来的r不再表示训练/验证划分。仅为沿用V3.11的物理实现模板定义：

```text
r_style = w mod 4
source_split_code = 0(TRAIN), 1(VAL), 1(DEV), 2(TEST)
az_index = (3*c + 5*t + 7*r_style) mod 8
az_offset_deg = 0(TRAIN), 15(VAL), 7.5(DEV), 22.5(TEST)
azimuth_deg = 45*az_index + az_offset_deg
elevation_deg = [-15,0,15][(c+2*t+r_style+source_split_code) mod 3]
arm_schedule = (c+t+r_style+source_split_code) mod 3
```

每个活动臂a使用MATLAB 1..4编号：

```text
target_values=[.18,.20,.22,.25]
target(a)=target_values[1+mod(c+t+r_style+a+source_split_code,4)]
```

非活动臂目标保持.15。活动臂按升序排列，第q个活动臂从q=1计：

| schedule | extend start | retract start |
|---|---|---|
| 0 | 5.2 s | 13.0 s |
| 1 | 5.2+.25*(q-1) s | 13.4+.15*(q-1) s |
| 2 | 6.2 s | 14.0 s |

调用源 `tcn0916_morphology_scenario`，传入这些target/start/retract覆盖值、速度.05、min_hold=5。NONE通过源NONE拓扑保持不变臂，不用伪命令。

G01实际生成全部888组场景并检查臂长、实际保持时间、回缩完成、风速界限和参考边界。不要仅凭上述公式算过就把发生器运行结果当成通过。

### 7.4 必要的范围声明

本任务Teacher覆盖全部三元组；Student半组合；TEST48是均衡代表性新实现，不穷举768个三元组。当前三种参考曲线形状固定，不宣称泛化到任意新路径。单次训练seed和小样本DEV不支撑任意参数/风场下的普遍稳定性主张。

## 8. 采样时序、缓存与实际施加量合同

### 8.1 时钟

| 信号/动作 | 时钟 |
|---|---|
| Plant/原BS主循环/命令滤波/位置eta | 1 ms |
| 位置RBF事件、位置KAN事件 | 10 ms |
| 姿态RBF事件、姿态KAN事件 | 10 ms |
| 离线训练窗口 | 32个连续事件，不跨航次、不跨缺口 |

沿用有效事件相位，`rbf_phase_start=-0.1`、`rbf_full_phase_start=-0.1`及原split调度。由程序生成事件时刻并断言：完整20 s航次的事件为0.01、0.02、…、19.99 s，共1999个；第32个事件在0.32 s，ready事件1968个。

若实际迁移后首事件变成0.009/0/0.02 s或事件数变化，G00/G02失败，不能更改预期计数来掩盖时序漂移。

### 8.2 单个Plant transition的顺序

以源循环的 `state(k,:)`、`transition_time(k)` 为准：

1. 读取同一步状态、参考和当前发出的机臂命令。
2. 若触发位置事件，追加当前14维特征，再判定历史是否达到32事件。
3. ready时用**更新前**W输出本次补偿，计算下一事件使用的W。未ready时KAN补偿为0。
4. 当前补偿经过原beta/输出限幅后进入力接口，并在事件间保持；不能输出一遍后又用更新后的W重算当前施加量。
5. 原位置BS和force-to-attitude映射产生姿态原始目标；命令滤波运行一次。
6. PCF辅助eta按源位置在本Plant步更新；位置Head事件使用的是本步这一更新之前的eta。
7. 姿态事件使用当前滤波参考和当前状态。X29的电机特征使用**上一姿态事件结束后保存的setpoint**；本事件新setpoint不可提前进入本事件输入。
8. 姿态KAN输出/更新，原姿态BS形成请求力矩，执行器限幅与C0分配后得到当前实际电机输入/realized wrench。
9. 在已知本步实际wrench后记录同一步的truth derivative作为离线标签来源。
10. Plant推进到state(k+1,:)；任何k+1状态不得用于k事件的部署输入。

不把执行推理耗时人工加进Plant，不用不匹配的未来状态做标签。计算时间独立记录；固定步长仿真通过不等于硬实时保证。

### 8.3 每航次必须重置

- 位置/姿态RBF权重回源规定初值。
- 位置KAN历史缓存、填充计数、事件相位、W=W0、held补偿、eta=0。
- 姿态KAN历史缓存、ready计数、DeltaW=0、held力矩、上一事件setpoint=zeros(4,1)。
- 命令滤波器由本航次初态初始化；不继承上条轨迹滤波状态。
- 所有在线统计、饱和标志、上次事件时刻、样本计数器清零。

### 8.4 beta的精确算术不能随意统一

位置KAN源循环用 `min(max(t(k)/1.8,0),1)`；位置/姿态RBF及姿态KAN的源循环有 `min(k*dt/rise_time,1)` 算术。MATLAB k从1开始，两者可差1 ms。

**本任务不把这项改成统一时刻。** 迁移保留各分支源算术，并从实际日志记录beta；标签不通过想当然的t重算beta替换真实施加量。不要把这1 ms差异悄悄“修正”后仍称源合同完全一致。

---

## 9. 部署特征白名单与网络结构

### 9.1 位置KAN X14

| 列 | 定义 | 单位 |
|---|---|---|
| 1–3 | e_p = p_ref-p | m |
| 4–6 | s_p = v_ref+k1*e_p-v | m/s |
| 7–9 | 当前roll/pitch/yaw | rad |
| 10 | 原位置BS零补偿预览所产生的thrust / m0 | m/s² |
| 11–14 | 当前四臂发出命令 | {-1,0,+1} |

第10列必须使用零位置残差预览的名义推力，不改成已补偿后的当前推力。特征由源 `stage1Preview` 相同方法计算。

不添加task、class、wind ID、真实臂长、风速真值、真实加速度、真实惯量或在线RBF输出到输入。它们可以是采样/分析元数据，不是网络列。

### 9.2 姿态KAN X29

| 列 | 定义 | 单位/说明 |
|---|---|---|
| 1–3 | ai0.error，期望减实际的Euler误差 | rad，主值wrap |
| 4–6 | ai0.surface，Euler速率BS误差面 | rad/s，不是直接omega误差 |
| 7–9 | 当前omega_B | rad/s |
| 10–12 | ir.euler_rate | rad/s，滤波参考 |
| 13–15 | ir.euler_acceleration | rad/s²，滤波参考 |
| 16–18 | 当前roll/pitch/yaw | rad |
| 19–21 | 当前惯性系速度 | m/s |
| 22–24 | ai0.nominal_body_angular_acceleration | rad/s²，固定名义模型 |
| 25 | 当前请求推力thrustN / m0 | m/s² |
| 26–29 | previousEventSetpoint / 1900 | 上一姿态事件电机setpoint归一化；不是平方转速，不是当前realized motor |

直接复用 `attitude_feature_row_v3_6(..., inputDim=29)`。不启用33维分支，不加机臂积分量，不能用X37旧缓存改列名冒充合法输入。

### 9.3 位置 N_KAN：必须与源结构一致

```text
输入张量：N × 14 × 32
每次前向只取窗口最后一帧（不是TCN）
mu/sigma：先归一化，再计算KAN
knots = [-4,-4,-4,-4,-2.4,-0.8,0.8,2.4,4,4,4,4]
spline_W: 32 × 14 × 8
linear_W: 32 × 14
feature_b: 32
readout: 3 × 33（PyTorch），MATLAB output_W: 33 × 3
```

归一化当前特征为z：

```text
z_spline = clip(z,-4,4)
h = tanh(spline(z_spline) + linear(SiLU(z)) + feature_b)
phi = [h;1] / sqrt(1 + sum(h.^2))
a_raw = W.' * phi
```

**位置SiLU分支不裁剪z**，继承repair后已生效的`kan_silu_unclipped=true`。样条分支裁剪到[-4,4]，右端点+4必须落入最后一基函数，不得重现端点全零错误。

参数数应为4163。不是增加一层、不改隐藏宽度、不用第三方KAN库替换。

### 9.4 姿态 KAN：X29与位置分支的一个重要区别

```text
输入张量：N × 32 × 29
spline_W: 32 × 29 × 8
linear_W: 32 × 29
feature_b: 32
readout: 3 × 33（PyTorch），MATLAB W0: 33 × 3
参数数：8483
```

姿态原X29结构对归一化当前特征先裁剪到[-4,4]，**样条分支和SiLU分支都使用裁剪后的特征**。不要把位置的unclipped-SiLU设置直接套到姿态。

```text
z_clip=clip((x-mu)/sigma,-4,4)
h=tanh(spline(z_clip)+linear(SiLU(z_clip))+feature_b)
phi=[h;1]/sqrt(1+sum(h.^2))
y_normalized_raw=W0.'*phi
D_A=[45;45;4.7124] rad/s²
```

输出是无量纲的归一化角加速度，不是Nm，也不是未归一化rad/s²。实际注入力矩按第11节。

### 9.5 初始化和导出

- spline权重按源正态std=.04，linear按源Xavier，feature_b=0，readout保留源类初始化。
- 位置Initial/姿态Initial从新随机初始化训练。Final只允许继承**本轮同环Initial**。
- 不载入DL1009任何checkpoint/normalizer。
- 导出必须绑定同一模型的encoder、W0、knots、normalizer、输出尺度及输入顺序。
- PyTorch float32与MATLAB double分别比较；禁止只比较W0shape就称前向一致。
- 所有部署模型`eval()`，无梯度、无dropout、无额外batch-dependent统计。

---

## 10. 标签：从实际控制行为构造，禁止方法名误判

### 10.1 必须新增规范日志字段

至少为每步记录或可精确重构：

```text
position_nominal_acceleration_mps2
position_commanded_force_N
position_compensation_applied_force_N
position_compensation_applied_acceleration_mps2
attitude_nominal_torque_Nm
attitude_compensation_applied_torque_Nm
requested_generalized
controller_clipped_generalized
allocated_generalized
realized_generalized
position_event_flag
attitude_event_flag
position_head_update_executed
attitude_head_update_executed
```

规范`applied`指实际进入BS残差接口、含beta/输出限幅/ZOH后的量，不是网络raw，不是before-update目标，也不是allocated/realized的最终电机差值。

使用collector元数据判断预期控制角色，并用实际信号闭合；不能使用`startsWith(method,'N_')`或一组不完整字符串决定是否把补偿当成零。

### 10.2 位置标签

对事件t_k，取同一步x_k、参考与实际wrench：

```text
a_nom = 位置BS零补偿预览的 nominal_acceleration
a_applied = position_compensation_applied_force_N / m0
a_virtual = a_nom - a_applied
a_true = vehicle_derivative(x_k, realized_wrench_k, Fwind_k, Twind_k, Ptrue_k)(4:6)
y_raw_P = a_true - a_virtual
y_clip_P = clip(y_raw_P,-3,3)      # 分量限幅，m/s²
```

适用于B、POS_OFF、P_INIT_STUDENT、P_F、P_A、PA_F、PA_A：

- B的a_applied是本步实际RBF补偿。
- POS_OFF是零。
- KAN是实际KAN补偿，包含Head当前W、beta及保持。

保留原四部分离线分解 `d_wind+d_alloc+d_att+d_map`（若数据管线需要）；闭合最大绝对误差≤1e-9 m/s²。不得将标签改成风力单项、RBF估计、网络自己的输出或`a_true-a_nom`而遗漏已施加量。

必须同时断言：

```text
F_cmd = m0*a_nom - F_applied
canonical_a_applied = F_applied/m0
canonical_a_applied 与角色专用实际施加日志一致
```

### 10.3 姿态标签

Teacher和Student共用物理定义，不把位置标签搬到姿态。

```text
ai0 = attitude_bs_step(x_k, 当步滤波参考ir_k, zero_torque, nominal_P)
tau0 = ai0.nominal_moment
tau_behavior = 本步实际进入姿态BS的总补偿力矩
tau_virtual = tau0 - tau_behavior
omega_dot_virtual = J0 \ (tau_virtual - cross(omega,J0*omega) - Jdot0_for_bs*omega)
omega_dot_true = vehicle_derivative(x_k, realized_wrench_k, Fwind_k, Twind_k, Ptrue_k)(10:12)
y_raw_A = omega_dot_true - omega_dot_virtual
y_clip_A = clip(y_raw_A, -D_A, D_A)
y_norm_A = y_clip_A ./ D_A
```

- B/P_STAR：tau_behavior是实际姿态RBF补偿。
- A_INIT_STUDENT/PA_F/PA_A：tau_behavior是实际姿态KAN总补偿力矩，含beta和Head贡献。
- `tau_virtual`应与**请求力矩**`requested_generalized(2:4)`闭合，不与clipped/realized力矩混用。
- torque闭合≤1e-8 Nm，truth derivative与直接动力学闭合≤1e-8 rad/s²。
- 真实参数只用于离线`omega_dot_true`；虚拟项仍用J0/Jdot0。
- 不除beta，不重复乘D_A，不把Euler角加速度当机体系角加速度。

### 10.4 源姿态导出器必须修的两项

原 `attitude_events_v311.m` 使用 `rbf_update_flag` 选事件，并只读取 `attitude_rbf_compensation_torque_Nm`。这对B/P_STAR教师可用，但不适用于关闭姿态RBF后的KAN Student：

1. 新导出器必须用独立的`attitude_event_flag`，不能用“是否更新RBF权重”或“权重是否变化>0”充当事件掩码。
2. 必须读取规范的`attitude_compensation_applied_torque_Nm`，不能在KAN Student下继续拿RBF力矩（通常为零）。

同理，位置事件与position_head_update_executed要分开。冻结模式仍有1999个事件，不能因为权重不更新就导出空数据。

### 10.5 真值、时间与数据合法性测试

G00建立人工日志fixture，不运行Plant，至少覆盖以下情形：

- B、POS_OFF、P_INIT_STUDENT、P_F、P_A的非零/零补偿映射。
- 姿态RBF已关闭且KAN力矩非零；事件仍完整、标签闭合。
- Head关闭但推理与非零固定输出保留。
- 两条连续航次不同长度/不同输出，缓存不串轨迹。
- method字符串变化不影响由规范实际量得到的标签。
- 原始标签超过输出上限仍保留raw及clip；clip计数正确。
- 输入中没有真值或未来值；post-step truth只作为y，不进入x。

正式采集每一条episode都运行数值合同检查；H5存储float32后的宽松舍入容差可以单独设置，但原double闭合门槛不能放宽。

---

## 11. 在线Head与冻结Head的精确边界

### 11.1 位置Head

位置编码器部署固定，W是33×3完整readout。P_A/P_INIT_STUDENT每事件：

```text
raw = W_before.' * phi
applied = beta * clip(raw,-[3;3;3],[3;3;3])
s_c = s_original - eta_before
s_eff = clip(s_c,-[7;8;10],[7;8;10])
W_dot = -beta * phi * s_eff.' - 0.002*W_before
W_next = clip(W_before + 0.01*W_dot, -60, 60)
```

这是原位置Head，不乘RBF gamma=1.2，不再乘5，不使用旧P_SLOW的0.25更新时间倍率。

P_F保持同一W0；只跳过W_dot/W_next更新。输出公式和beta保持不变。W每个episode重置到选定模型的W0。

### 11.2 PCF辅助状态

每Plant步使用源函数：

```text
a_filtered = thrust/m0 * R(euler_filtered)*[0;0;1] - [0;0;g]
r_f = a_requested - a_filtered
decay = exp(-k2*dt)
integral = -expm1(-k2*dt)./k2       # k2=0时用dt
eta_next = decay.*eta + integral.*r_f
```

eta具有速度量纲m/s；不能与位置误差m混为一谈。P_F与P_A都保留eta计算；只有P_A用它驱动W更新。不要用命令滤波后的角误差直接替代该实现。

### 11.3 姿态Head

固定离线W0与可变DeltaW分离：

```text
DeltaW初始 = zeros(33,3)
raw_normalized = (W0 + DeltaW_before).' * phi
实际补偿 = 同一事件的beta × 分量限幅后的归一化输出 × D_A × J0
```

更明确的单位顺序：先得到归一化输出，经±1限幅和beta后乘D_A成为机体系角加速度，再左乘J0成为Nm。beta、D_A、J0均只施加一次。

**DeltaW更新调用源 `attitude_kan_head_step_v39`，不得另造更新律。** 固定参数：

```text
gamma = 0.002
sigma_per_s = 0.02
projection_fro = 0.20
event_dt = 0.01 s
surface clip = [2.3;2.3;1.4]
ready_event = 32
saturated policy = leakage_and_projection_only
output_before_update = true
```

源调用需要 `aiHead=ai0; aiHead.J0=P.inertia`，以及源Euler运动学相关字段。不要把这些字段删掉后用未经验证的 `-gamma*phi*surface'` 代替。

- PA_F/A_INIT_STUDENT：DeltaW始终零，W0不变，编码器/输出/clip/beta/J0映射照常运行。
- PA_A：只更新DeltaW，不能对W0整体泄漏或投影到0.2。
- 初次ready之前KAN力矩为零；不偷偷用姿态RBF回退填空。
- 每条航次复位DeltaW，禁止跨航次学习。
- 源helper的`raw/applied`内部命名可能与普通前向分支含beta方式不同；新规范日志始终由实际注入力矩及`J0\tau`生成，不能靠字段名猜是否再乘beta。

### 11.4 同模型配对验收

P_F/P_A必须共享完整position model_id、归一化器数值、W0数组和采样参数。PA_F/PA_A必须共享完整attitude model_id及同一个P_STAR。

验证开关贡献时比较：

```text
冻结：所有事件 W_next==W_before，或DeltaW==0
在线：人工非零surface fixture下有非零更新，且和源单步及递推一致
两模式：相同x、W0、首次ready时的更新前输出相同
```

不能要求每个在线实际事件权重数值都必须变化（零surface/饱和/泄漏等可能使变化为零）。分别记录“执行了更新分支”的计数与“权重数值发生变化”的计数。

---

## 12. 离线训练、归一化、采样权重和选模

### 12.1 四个fit，不做额外路线搜索

| fit | 数据 | 初始化 | seed |
|---|---|---|---:|
| Position Initial | B768 + POS_OFF768 TRAIN | 全新随机 | 2026101801 |
| Position Final候选 | 上述Teacher + Student384 TRAIN | 本轮Position Initial | 2026101802 |
| Attitude Initial | B768 + P_STAR768 TRAIN | 全新随机 | 2026101803 |
| Attitude Final候选 | 上述Teacher + Student384 TRAIN | 本轮Attitude Initial | 2026101804 |

Final不是重新从随机权重训练，也不是旧模型warm start。Final重新创建Adam优化器，不继承Initial的动量状态；恢复同一个中断fit时则恢复该fit的优化器和随机数状态。

仅四个fit。不要做A/B适应导向训练、BPTT Head重放loss、新训练集规模比较或多seed搜索。

### 12.2 归一化器

**位置：** 仅用本轮Position Initial的Teacher TRAIN（B/POS_OFF共1536条）原始事件拟合。第1–10列按全部1999事件的population mean/std，std下限1e-4；第11–14列mu=0、sigma=1。不得把Student、VAL、DEV、TEST加入统计。

**姿态：** 仅用本轮Attitude Initial的Teacher TRAIN（B/P_STAR共1536条）的ready事件拟合29列population mean/std，std下限1e-6。每episode只计真实ready事件，不从已重叠的窗口反复计权。

- 两环normalizer分别拟合，不共用14维统计去裁29维。
- Final全程复用同环Initial normalizer，不因Student状态范围不同重新拟合。
- 部署使用checkpoint绑定的normalizer，不读训练目录之外同名json。
- normalizer统计用float64；模型buffer按源float32；MATLAB导出包含同一数值。
- 所有特征的非有限值必须定位到episode和event。不得整段`dropna`后跨断点拼窗口。

### 12.3 训练窗口与事件采样

本任务保持V3.11的训练节奏，不把数据扩容同时变成采样算法实验：

- 窗口长32，训练stride=5；位置VAL stride=5，姿态VAL stride=1（全部ready事件）。
- 以每条episode自身事件序列构窗，0-based端点从31开始，严禁跨episode。
- 每条完整episode为1999事件、1968ready；stride5恰好394个窗口。
- PositionInitial/AttitudeInitial各605,184个训练窗口/epoch；Final各756,480个。
- 位置Initial VAL：96×394=37,824；位置Final混合VAL：144×394=56,736。
- 姿态Initial VAL：96×1968=188,928；姿态Final混合VAL：144×1968=283,392。
- 100 Hz完整事件必须保存；不要只保存stride5端点而无法重建在线时序。
- 当前KAN只用最新帧，但仍保留既定窗口接口、ready门槛与缓存。不能把32事件缓存写成额外320 ms计算延迟，也不能声称KAN学到了32步动态记忆。

为控制内存：按episode读取或缓存原始事件，按batch构窗；不要在磁盘展开保存所有重叠窗口，不生成全量重复CSV。

### 12.4 来源、任务、构型、风单元、阶段权重

Initial来源权重：

```text
Position: B=.5, POS_OFF=.5
Attitude: B=.5, P_STAR=.5
```

Final来源权重：

```text
Position: B=.25, POS_OFF=.25, P_INIT_STUDENT=.5
Attitude: B=.25, P_STAR=.25, A_INIT_STUDENT=.5
```

这是单一Student总权重50%，不是384条再按条数获得未声明权重。按以下层次精确均衡：来源 → 三任务 → 16构型 → 该角色该任务该构型的场景 → episode内实际存在的阶段 → 阶段内窗口。

对窗口i：

```text
w_i = source_mass[r]
      / (3 * 16 * N_scenes[r,t,c] * N_phases[episode] * N_windows[episode,phase_i])
```

Teacher TRAIN的N_scenes=16，Student TRAIN=8，VAL各角色=1。完整性正确时，各source×task权重恰为source_mass/3；每个风单元的有效权重也应均衡，独立汇总验证，不靠场数推测。

NONE构型只有STATIC/NONE阶段是合法情况，不能要求它有EXTEND。训练阶段名统一为STATIC、PRE、EXTEND、HOLD、RETRACT、RECOVERY；用于分层的phase可由离线真实形态分类，但绝不能作为网络输入。不要把PRE与回缩后的RECOVERY混成一个长阶段而使权重失衡。

每epoch报告有效样本数、source/task/wind/phase权重和；缺少某角色某任务等核心单元时停止，不改成“只在实际存在任务中均分”。

### 12.5 loss、optimizer、batch实现

```text
Adam: lr=1e-3, weight_decay=1e-5
batch_size=256
max_epochs=60
patience=8
float32 train
```

位置loss：`SmoothL1(pred_mps2/3, target_clip_mps2/3)`，先对三输出分量平均，再按样本权重。姿态loss：`SmoothL1(pred_normalized, target_normalized)`，同样按样本权重。

训练loss不先裁pred再求梯度，避免饱和区梯度被静默清零；clip仅用于部署与规定的验证评分。

不使用自归一化mini-batch权重让来源权重被批内样本偶然组成改变。推荐：所有训练窗口均匀打乱，每轮遍历一次，预先令全局sum(w)=1；若总窗口N，batch大小b：

```python
loss = (N / b) * sum(w_batch * per_sample_loss)
```

这给出全局加权目标的等价期望缩放，不叠加WeightedRandomSampler再次加权。若采用等价分层采样，必须证明期望权重一致，不要同时采样加权和loss加权造成平方权重。

epoch训练目标汇总用全局权重累计，不把不同有效权重的batch均值直接无权平均。

开启固定随机种子；环境支持时使用deterministic PyTorch选项。若某算子不能确定性运行，记录并停止排查，不静默关闭后仍写“完全可复现”。不要在本任务自动升级CUDA/PyTorch/MATLAB。

### 12.6 位置选模分数

定义全局归一化验证权重为w：

```text
pred_clip = clip(pred,-3,3)
S_P = sqrt(sum_i w_i * ||pred_clip_i-y_clip_i||² / 3)
```

单位m/s²。Initial用Teacher VAL96，来源各.5。Final在混合VAL144上使用B=.25/POS_OFF=.25/Student=.5，并**先在同一个混合VAL144上重新评价Initial（epoch0）**。

另报告Teacher-only VAL96分数、Student-only VAL48分数、逐任务/风单元/阶段/三轴误差和raw/clip比例。不能拿Initial旧Teacher-only分数与Final混合分数直接比较。

### 12.7 姿态选模分数

恢复物理单位：`pred_phys=clip(pred_norm,-1,1).*D_A`。先算每个episode×phase的三分量RMSE（rad/s²），再按第12.4节的来源/任务/构型/scene/phase层次平均，得到S_A。

这保持“按阶段宏平均的物理角加速度RMSE”口径，不将角加速度rad/s²与闭环角度rad相混加。

Initial用B/P_STAR Teacher VAL96；Final使用混合VAL144并先重评同一Initial epoch0。另报告两Teacher来源与Student来源分别的分数。用于训练的normalized loss与用于选模的physical S_A同时保存，名字必须区分。

### 12.8 epoch0保护、停止与checkpoint选择

1. Initial训练开始前保存随机模型epoch0的验证分数作为参考；正常选模必须得到有效改进，否则Initial Gate失败，不强行用未学会的随机模型采Student。
2. Final初始化后，先保存本轮Initial作为`epoch0_reference`，计算混合VAL评分，并把它作为best候选。
3. 每个epoch结束按同一验证集/权重评分。改进判据统一`score < best - 1e-10`。
4. 连续8个epoch未改善即early stop；最多60轮。无效/非有限loss停止，不改lr继续碰运气。
5. 若Final最佳仍是epoch0，Selected指向Initial完整包；标记`student_changed_selected=false`，不宣称Student改善了模型。
6. 若Final最佳为训练后的epoch，Selected绑定那一轮完整包；同时记录Teacher/Student分项变化，不用一个小数掩盖明显组间退化。
7. 位置和姿态分别执行上述流程；不共享优化器、W0、normalizer或resume状态。
8. resume按fit_id、contract_version、数据角色/计数、normalizer数值、模型结构与最后完成epoch校验。不通过则停止，不覆盖已有SUCCESS或其他fit。
9. `SUCCESS`只表示训练任务完成；进入闭环还必须通过导出/推理一致性Gate。

### 12.9 前向/在线数值一致性验收

无Plant测试至少64组确定性fixture，覆盖训练内输入、z在±4边界、超界、beta=0/中间/1、正负surface及限幅情况。

- Position PyTorchfloat32→MATLAB物理输出最大误差≤1e-5 m/s²；phi误差≤1e-5；double分解误差≤1e-10。
- Attitude PyTorchfloat32→MATLAB恢复物理加速度误差≤1e-5 rad/s²；归一化输出和phi分别记录；double读出分解误差≤1e-10。
- 同一helper复制前后double单步与多事件递推误差≤1e-10；冻结W/DeltaW保持严格不变。
- 检查+4端点、零输入、偏置、readout转置和D_A/J0单位。
- 将实际打算部署的模型包重新加载后再做fixture测试；不是只测试训练内存对象。

## 13. 指标与正式性能 Gate 的计算规则

### 13.1 主要闭环指标

完整航次统一使用transitions `0 <= t < 20`，不把最后一个无控制transition的终端状态额外混入。位置误差为参考减实际；姿态误差是**当步滤波后Euler参考减实际Euler**，逐分量wrap到[-pi,pi]。

```text
Q_0_20 = sqrt(mean_k(sum_axis(e_position(k,:).^2)))    # m，三维向量RMSE
Q_5_20 = 同一定义，仅 5<=t<20                         # m
A_0_20 = sqrt(mean_k(sum_axis(e_filtered_euler(k,:).^2))) # rad
peak_Q = max_k(norm(e_position(k,:),2))              # m
```

这与离线残差评分中除以3的component RMSE不是同一个量，不得混用。

- 先逐场算Q/A，再按任务求场景均值，再对三任务等权平均得到macro_Q/macro_A。
- 对照比较必须按scene_id一一配对；不能分别丢弃失败场再比较不同剩余场景均值。
- 同时报告全时段/5–20 s、逐轴、峰值、p95、变臂阶段、风单元、构型分组。
- 无风且误差很小时，相对改善分母接近零应记NA，优先报告绝对差；不制造极大百分比。

### 13.2 约束与运行指标

- 电机饱和、广义量裁剪：使用实际源标志，按每transition是否任一通道激活统计fraction。
- 电机范围：所有实际指令/施加转速有限，0–1900 rad/s；源log区分command/setpoint/realized，表名明确。
- TV：沿用源 `measure_pcf_v3_5`/V3.11的归一化电机总变差口径，记录采用的样本范围和归一化分母。不得以另一种更小的定义替代源TV；它是报告项，不在本任务临时增加TV淘汰门槛。
- 控制器时延：保存joint-event计时和worst；正式门槛沿用每场controller event p99<10 ms。不要拿GPU离线批处理每样本时间替代MATLAB闭环event时间。
- 同时报告1 ms基础控制循环的测量值；p99<10 ms不代表1 kHz硬实时证明，不人为把测量耗时加入Plant。
- 源安全停止至少包括：位置误差范数>1 m持续0.2 s，实际倾角>pi/3持续0.1 s，机体系角速度范数>20 rad/s持续0.05 s，非有限状态。迁移保留源持续时间判定，不放宽安全界限。
- 失败航次保留其实际时段指标和time_to_stop；不能把2秒prefix标成Q_0_20的完整合格值。

### 13.3 位置性能规则：G06 DEV24；G12相同规则检查TEST48

对P_F、P_A**分别**判定。DEV每任务8场、TEST每任务16场。

| 检查 | 通过条件 |
|---|---|
| 完整性 | 该方法N/N完整、有限、20000 transitions，无硬停 |
| 配对 | 对应B也是N/N完整；scene_id无重复、参数完全对应 |
| 覆盖 | DEV全局16构型/16风，三任务各8；TEST每任务16构型/16风各1 |
| macro_Q | Q_C < Q_B - 1e-9 m |
| 每任务Q非劣 | Q_C,t <= 1.05*Q_B,t + 0.002 m |
| 总Q胜率 | >=75%；DEV至少18/24，TEST至少36/48 |
| 每任务Q胜率 | >=50%；DEV至少4/8，TEST至少8/16 |
| macro_A与每任务A | <=1.10*对应B + 0.002 rad |
| 每任务饱和/裁剪fraction | <=对应B + 0.005 |
| 每场p99/电机范围 | p99<10 ms；0–1900 rad/s |
| 位置峰值预警 | 单场peak_C >1.2*peak_B+0.01 m算一次；总数<=max(1,floor(.05*N))，即DEV1次、TEST2次 |
| 严重峰值 | 同时满足peak_C>2*peak_B且peak_C-peak_B>0.05 m；任何任务少于3次 |

从源R2E的48场门禁适配到DEV24时，必须修改样本数和每任务计数；不能把“每任务至少12对”原样保留，使8场/任务天然无法通过。比例、单位和主性能规则保持上述明确值。

若两种模式都通过，按macro_Q最小选择P_STAR；差不超过1e-9 m时按较小位置峰值宏均值，再相同优先P_F。选择仅用DEV，不看TEST。若只有一个通过选它；两者都不通过则停止，禁止开始姿态采集。

无论哪一个入选，都保留另一模式的真实结果。冻结模式不必先获胜才允许在**同一个G06内**评估在线模式。

### 13.4 姿态/双环性能规则：G11与G12

此任务不运行R2E旧的A_NEW（位置RBF+姿态KAN）支线。只检查固定本轮P_STAR的PA_F/PA_A。沿用R2E的基本性能尺度，并在采集前明确加入“相对P_STAR的姿态增量”条件，不能只赢B就把全部收益归给姿态KAN。

对每个PA模式分别要求：

1. N/N完整、有限、无硬停；同场B与P_STAR有效，覆盖与G06/G12相应场景表一致。
2. macro_A_PA < macro_A_B -1e-9 rad，并且 < macro_A_PSTAR -1e-9 rad。
3. macro_Q_PA < macro_Q_B -1e-9 m；且macro_Q_PA <=1.03*macro_Q_PSTAR +0.002 m。
4. 每任务Q_PA <=1.10*Q_B+0.002 m，且<=1.05*Q_PSTAR+0.002 m。
5. 每任务A_PA <=1.10*A_B+0.002 rad，且<=1.10*A_PSTAR+0.002 rad。
6. 每任务饱和/裁剪fraction不超过B或P_STAR各自+0.005；每场p99<10 ms，电机在0–1900。
7. 峰值预警分别相对B和P_STAR计数，两项各自<=max(1,floor(.05*N))；严重峰值按第13.3节定义，对两个对照均要求各任务<3次。
8. TV、变化率、阶段瞬态及Head幅值必须报告，但不临时加入新的综合加权分数或未声明硬门槛。

两种PA都通过时按macro_A最小选定最终双环模式；1e-9 rad内相同则看macro_Q，再相同优先PA_F。若只有一个通过选它；都失败停止在G11，不用TEST救场。

PA_A对PA_F的Head增量另列配对差、macro_A/Q、峰值、饱和、TV。PA_A没有增益就如实报告“该配置下在线姿态Head无增益/退化”，不能因它带Head就自动选它。

### 13.5 最终TEST不再选模型

G12预定比较B、P_F、P_A、PA_F、PA_A，共48×5=240次。TEST中的P_STAR指G06已经选择的P_F/P_A结果，不额外跑第六个方法。

- DEV安全完整但性能未入选的消融模式可以按预登记进入TEST，作为未入选对照，不能被悄悄删除。
- DEV已经发生物理不安全的模式不强迫进入TEST；预先标记`EXCLUDED_UNSAFE_IN_DEV`，说明不能得到完整五方法表，不替换成更容易的条件。
- TEST若发生不安全，停止该模式剩余场次并保留失败/未运行状态；其他安全模式可完成既定任务，但最终必须写明锁定方案测试是否通过。
- 不根据TEST重新挑checkpoint、切Head、改阈值或训练。未入选模式即使TEST更好，也不能把它事后当预先选定赢家。
- 最终48场是代表性留出确认，不声称覆盖全部768个三元组合，不声称已经完成跨训练seed泛化或完整闭环稳定性证明。

---

## 14. 逐 Gate 执行清单

每个Gate仅当所有硬验收项成立才保存PASS。`NOT_RUN`、`CODE_WRITTEN`、训练脚本退出0、报告文件存在，都不是PASS。

### G00_MIGRATION：迁移与基线合同核对（0 Plant）

**目的：** 新工程脱离旧数据/模型路径，并保留V3.11/R2E有效数值控制合同。

**步骤：**

1. 确认SRC/DST身份，读取第1节源文件和必要本地helper。
2. 建立第2节结构与最小代码迁移；源只读。
3. 输出显式contract_dl1018.json、effective_config.mat与新options factory；彻底解除frozen_sources旧模型依赖。
4. 在隔离的源环境生成确定性数值fixtures，再在隔离的DL1018环境运行同一输入：
   - cfg、m0、J0、C0、nominal morphology、广义限幅。
   - position_bs_step、attitude_bs_step、force-to-attitude、command_filter_step。
   - RBF基函数、输出/更新一步及多事件序列。
   - 位置KAN前向、位置PCF Head与eta、姿态X29前向和v39 Head。
5. 人工fixture至少含零状态、正负位置/姿态误差、非零omega、风/形态多个合法参数、输出/投影边界。生成这些静态数值输入不推进闭环Plant，不计航次。
6. 测试new runner的完整函数解析链，含首推理、第一次更新、日志trim、数据导出、结果写入。不能只对runner本身`which`。
7. 测试控制开关矩阵与零输出反事实：
   - KAN关闭、位置RBF开启 → B路径。
   - 位置RBF关闭、位置KAN固定零输出 → POS_OFF路径，不是B。
   - 冻结Head非零W0仍输出非零补偿。
   - 姿态RBF关闭后姿态事件仍发生，X29/标签能导出。
8. 检查所有活动依赖解析落在DL1018，不调用任何hash/manifest入口。

**验收：**

- 第3节活动数值逐项一致；形态fixed、C0/J0固定、R2E滤波正确。
- 源与迁移纯double参数/代数函数误差≤1e-10；Head递推≤1e-10；冻结权重严格不变。
- 初始事件相位、1999事件/1968ready/首ready=.32 s的调度单元测试通过。
- 缺少姿态算法helper、未知有效opts或外部旧数据路径均不得PASS。
- `reports/contract_check.json`记录字段、expected、actual、source、pass，不含文件hash。

**产物：** 可导入/可调用的新代码、显式配置、无Plant数值测试结果、G00_MIGRATION.json。通过后进入G01。

### G01_SCENES：生成全部场景和运行配额（0 Plant）

**步骤：**

- 按第6/7节生成888行scene_specs：TRAIN768、VAL48、DEV24、TEST48。
- Student TRAIN384由确定公式选择，Student VAL用全部VAL48；不再按R0/R3重新划分。
- 生成dataset_plan并初始化状态为NOT_STARTED的运行配额。TEST标为SEALED。
- 无Plant生成每个场景数组，核对参考、风、臂长、保持/回缩、初态、shape和数值范围；无需把全部场景数组长期重复存盘。

**验收：**

- 场景ID唯一、seed唯一、split计数准确、Student半组合计数全部通过。
- TRAIN/VAL/DEV/TEST不是同一个外部实现改ID；同场多控制器输入一致。
- TEST仅做定义和无Plant预检，未调用controller/Plant产生轨迹、未产生标签。
- 三任务参考一致、风速峰值<18、输入频率≤5、每活动臂保持≥5、20 s内回缩完成。
- 名义轨迹预检按源计算，若需要超出现有限幅不能通过修改轨迹掩盖，停止并记录。

**产物：** scene_specs.csv、dataset_plan.json、G01_SCENES.json。通过后进入G02。

### G02_P_TEACHER：位置Teacher全量新采（1632 Plant）

**运行：** TRAIN B768+POS_OFF768；VAL B48+POS_OFF48。

先从TRAIN中取三个任务各W08/W14/W15的预定场景，共9组，每组跑B/POS_OFF两次。选择规则：对每个(t,w)，取满足Student子集公式且c>0的最小c。这个小批在运行前由参数表确定，不看结果选场。成功后计入正式配额，再执行其余场景，不重复运行。

**每航次必须保存：** 实际配置引用、scene参数引用、collector身份、开始/结束状态、20000步或失败prefix、规范raw、位置事件H5、同场scene信息和关键指标。B raw保留后续姿态标签所需信号。

**验收：**

- TRAIN各来源768/768完整，VAL各48/48完整；所有三任务/构型/风计数符合计划。
- B两环RBF启用；POS_OFF只关闭位置RBF，姿态与Plant不变。
- 每航次1999位置事件、1968ready；位置标签闭合≤1e-9；特征/时间一致。
- 没有旧数据混入、重复accepted tuple、失败prefix补完整数量。
- 首批后如有物理失败停止本Gate，不丢场继续宣布“足量通过”。

**产物：** B/POS_OFF raw和位置H5、episode_index、G02_P_TEACHER.json。通过后进入G03。

### G03_P_INITIAL：新位置Initial训练与导出（0 Plant）

**运行：** 第12节Position Initial，Teacher TRAIN1536、Teacher VAL96，seed2026101801。

**验收：**

- 数据/归一化仅用允许的Teacher TRAIN；参数4163、X14、位置SiLU-unclipped。
- 训练有限、保存实际history；Initial选定模型的Teacher VAL S_P低于同权重零预测分数至少1e-10。
- 输入特征与标签raw/clip分开，loss尺度正确；不要求低于某个历史绝对RMSE数值。
- 导出后64fixture数值一致性通过；采集器P_INIT_STUDENT使用这个包的W0/normalizer。
- 保存Initial model_id，后续Student采完前不覆盖。

**产物：** models/position/initial、normalizer、training_history、fit_status、parity、G03_P_INITIAL.json。通过后进入G04。

### G04_P_STUDENT：单一位置Student新采（432 Plant）

**运行：** P_INIT_STUDENT TRAIN384+VAL48，位置Head在线，姿态RBF保留。

先执行与G02首批相同的TRAIN9组；成功计入384，继续剩余。不是另外运行P_F/P_A两种Student。Initial不必在这9场战胜B，但必须安全且合同正确。

**验收：**

- TR384/VA48全部完整；每任务128/16，TR每任务×构型8、每任务×风8。
- 全部由同一Initial包和同一collector配置生成；W每航次复位；不混入Selected或旧model。
- 位置RBF输出/更新均关；head使用原PCF在线规则；实际更新分支与日志一致。
- 事件、标签、实际施加量与输入重建通过；W08/W14等没有因失败缺失。
- 任何物理失败保留prefix并暂停，不另换seed补齐。

**产物：** 单一Student raw/H5、计数/权重检查、G04_P_STUDENT.json。通过后进入G05。

### G05_P_FINAL：一次追加训练、epoch0保护、位置锁模（0 Plant）

**运行：** TRAIN1920、混合VAL144，warm start本轮Initial，seed2026101802。

**验收：**

- 同环normalizer严格不变；混合VAL上重评epoch0后才训练。
- 按S_P选checkpoint；Final不改善则保留Initial，不强制替换。
- 无Student VAL/DEV/TEST进入训练；来源权重正确。
- Selected从磁盘重载后parity通过；P_F/P_A共享同一模型和W0。
- 不因Final未改变Selected额外再做一次fit或新Student采集。

**产物：** final_candidate、selected、selection.json、G05_P_FINAL.json。通过后进入G06。

### G06_P_DEV：24场位置配对与Head消融（72 Plant）

**运行：** 固定DEV24，按场景依次B、P_F、P_A。三模式都执行明确的单场安全保护。

可以先完成DEV表中每任务最先出现的3组（共9组）观察接线/安全，随后继续其余；它们本身属于24组，不能额外跑新canary。无安全问题时不能因为前几场Q暂时输B就提前改模型或换场。

**验收：**

- 每个候选独立按第13.3节评分；B对照必须有效。
- P_F与P_A只有位置更新开关差异，eta/输出/beta/ZOH不变。
- 一种候选不安全时可停止该候选剩余DEV；另一种按原计划继续，不以“冻结先赢”作为在线模式准入条件。
- 至少一个位置模式全部性能门槛PASS才G06 PASS。否则状态STOP_POSITION_NOT_QUALIFIED，不启动姿态训练。
- 按固定选择规则写P_STAR；不得引入旧P_CF或把姿态KAN用于修补位置失败。

**产物：** POSITION_DEV.csv、P_STAR配置引用、G06_P_DEV.json。通过后进入G07。

### G07_A_TEACHER：固定位置方案下的姿态Teacher（816新增 Plant）

**运行：** P_STAR TRAIN768+VAL48；B使用G02的同一批DL1018新raw，不新跑B。

先从已保存B raw离线导出姿态X29/标签；再按预定首批及剩余场景采P_STAR，导出对应姿态数据。位置模型和其Head模式从G06起固定。

**验收：**

- 逻辑Teacher TRAIN=B768+P_STAR768，VAL=B48+P_STAR48。
- B来自本轮G02，并且raw支持同一合同的姿态标签；不读取DL1009旧B日志。
- P_STAR物理运行全部完整；进入姿态Teacher时不得偷换为P_INIT_STUDENT配置。
- 1999姿态事件/1968ready；X29合法、上一事件setpoint时间对齐；torque/dynamics闭合通过。
- 三任务、构型、风完整Teacher交叉覆盖。

**产物：** 两角色姿态H5、P_STAR新raw、G07_A_TEACHER.json。通过后进入G08。

### G08_A_INITIAL：新合法X29姿态Initial（0 Plant）

**运行：** Teacher TRAIN1536/VAL96，seed2026101803；8483参数；同第12节。

**验收：**

- 29列顺序、输入归一化只用Teacher TRAIN ready；D_A和normalized loss正确。
- 姿态SiLU裁剪行为符合原X29，不套用位置unclipped分支。
- S_A相对同权重零预测有有效改进，训练有限；parity通过。
- 固定P_STAR；A_INIT_STUDENT的姿态Head为冻结DeltaW=0，λ=1，姿态RBF输出/更新关闭。

**产物：** models/attitude/initial、fit/normalizer/parity、G08_A_INITIAL.json。通过后进入G09。

### G09_A_STUDENT：单一姿态Student（432 Plant）

**运行：** A_INIT_STUDENT TRAIN384+VAL48；只这一种姿态行为，位置P_STAR保持固定合同。

先执行TRAIN首批9组，成功计入384。不能为了“姿态Student与在线部署一致”额外启动一整套PA_A采集。

**验收：**

- 384/48完整且覆盖正确；同一Attitude Initial和同一P_STAR采完整池。
- 姿态RBF关闭，但独立attitude_event_flag仍给出1999事件。
- 标签使用实际KAN总补偿力矩，不读零RBF量冒充行为力矩。
- DeltaW始终零，固定网络正常输出；位置Head状态每航次按P_STAR重新初始化。
- 特征/时序/闭合通过。

**产物：** 单一姿态Student raw/H5、G09_A_STUDENT.json。通过后进入G10。

### G10_A_FINAL：姿态追加训练与锁模（0 Plant）

**运行：** TRAIN1920/VAL144；warm start本轮Attitude Initial；seed2026101804。

**验收：**

- Teacher/Student来源权重及相同VAL epoch0基线正确；normalizer不变。
- Final改善才替换，否则保留Initial；如实标记Student是否改变Selected。
- PA_F/PA_A共享同一完整姿态包、相同P_STAR；从落盘模型重载后parity通过。
- 不训练/修改位置模型，不在姿态loss中混加位置Q或重新调Head参数。

**产物：** attitude final_candidate/selected、selection、G10_A_FINAL.json。通过后进入G11。

### G11_PA_DEV：同一DEV24的姿态Head消融（48新增 Plant）

**运行：** PA_F24、PA_A24。B和P_STAR使用G06同场完整结果，禁止重复运行相同配置获取“更好一次”。

**验收：**

- 按第13.4节对PA_F/PA_A独立判定。
- 位置设置两模式完全一致；唯一变化为姿态DeltaW更新开关。
- 至少一个PA模式通过才G11 PASS，按固定规则锁定论文最终双环模式。
- 都未通过则STOP_ATTITUDE_NOT_QUALIFIED，保留位置结果，不开启TEST试图寻找胜出场景。

**产物：** ATTITUDE_DEV.csv、最终选定双环配置、G11_PA_DEV.json。通过后进入G12。

### G12_FINAL_TEST：独立48场、最多五方法（名义240 Plant）

**前置锁定：** 两个Selected模型、normalizer、P_STAR、最终双环模式、所有门槛、方法安全准入状态在第一次TEST运行前写入selected_models.json，之后不可变更。

按第13.5节运行。顺序固定为每场B → P_F → P_A → PA_F → PA_A；所有活动方法共用同一新TEST外部输入。

**验收与结论：**

- 区分“TEST执行完成”与“锁定方案性能通过”。完整但失败要写FAIL，不强行让G12科学判据通过。
- 位置/双环按第13节同样规则复核；同时报告每个模式全部单场原值与失败。
- 不把仅某个未入选模式获胜解释为锁定路线已通过独立测试。
- 若TEST执行完成但性能FAIL，仍允许进入G13写最终否定/边界报告；这不是允许继续调参。

**产物：** FINAL_TEST.csv、测试状态与结论JSON、G12_FINAL_TEST.json。之后只进入G13汇总。

### G13_FINAL_REPORT：闭环完成与证据交付（0 Plant）

汇总数据采集完成量、四个fit、Initial/Final选择、位置Head消融、姿态Head消融、最终TEST和所有失败/未执行事项。

必须明确：

- 哪些数是offline m/s²或rad/s²，哪些是closed-loop m/rad。
- 哪些是DEV选择结果，哪些是未参与选择的TEST。
- 每个环的Student是否让Selected发生变化，是否真的有性能增益。
- Head冻结是否更好，在线是否更好；没有收益不能隐藏。
- 所有安全、峰值、饱和、TV和时间数据；不只写macroQ/A。
- 本任务没有实机验证、没有SITL、没有完整稳定性证明、没有训练seed横评；不额外宣称这些已经完成。

只生成一份FINAL_REPORT.md和已有机器可读表。停止，无后续自动扩展。

## 15. 文件、事件索引与断点恢复的最小合同

### 15.1 每条航次的唯一身份

```text
physical_tuple = (contract_version, split, scene_id, collector_id, model_id, runtime_mode)
run_id        = physical_tuple + attempt_number
```

B/POS_OFF的model_id可以是`NO_NEURAL_MODEL`，但baseline contract_version必须明确。P_STAR记录实际P_F/P_A模式和选定model_id，不是仅写`P_STAR`一个字符串。

只有完整、有限且数据检查通过的一个attempt能进入accepted episode索引。旧失败attempt仍保留。不能把同一物理tuple的两次完整运行都计成两个训练样本。

### 15.2 最小 attempt_index.csv 字段

```text
run_id, gate_id, split, scene_id, task, class_index, wind_cell,
collector_id, model_id, contract_version, runtime_mode,
attempt_no, status, plant_started, returned_transitions,
complete, finite, safety_stop_reason, error_kind, error_message,
raw_path, position_event_path, attitude_event_path,
started_at, finished_at, elapsed_s, accepted_for_training
```

不增加hash、SHA、manifest列。路径必须落在DL1018；空/缺文件不能被状态字符串掩盖。

### 15.3 最小 episode_index.csv 字段

```text
run_id, split, scene_id, task, class_index, wind_cell,
source_role, collector_id, behavior_model_id, contract_version,
position_event_path, attitude_event_path,
complete, finite, transition_count, event_count_position,
event_count_attitude, ready_count_position, ready_count_attitude,
accepted, rejection_reason
```

B一条raw可以对应两个环H5，索引通过run_id关联，实际Plant次数仍为1。索引是训练加载器的唯一入口，不允许`glob('**/*.csv')`把历史、失败、VAL或TEST扫进训练。

### 15.4 H5事件结构

建议统一按event-major存储，读者看到的shape必须如下：

```text
time_s                 [1999]          float64
plant_index             [1999]          int64，注明MATLAB 1-based
index                   [1999]          1..1999
ready                   [1999]          bool/uint8，index>=32
phase_code              [1999]          固定映射
x                       [1999,14] 或 [1999,29]
target_raw              [1999,3]
target_clip             [1999,3]
target_normalized       [1999,3]          姿态必须；位置可不存，训练时/3
applied_compensation    [1999,3]          位置m/s²或姿态Nm，单位属性明确
```

元数据含scene/role/model/contract/split/units/feature_order/array_layout，不含不可获得真值作为x列。

MATLAB/HDF5维度顺序与h5py读取容易转置。用非对称人工矩阵验证跨语言第i行、第j列内容，不允许仅看到某个维数不对就无条件转置直到shape通过。

原double闭合先验收，再转存float32特征/裁剪标签。time、关键raw标签与闭合证据可保留float64；存储舍入后的相等检查用明确容差，不混用double级精度要求。

### 15.5 规范raw日志：保留足够证据，不重复膨胀

每航次保存一份规范raw_run.mat（v7.3或同等可读压缩存储），至少含：

- state、transition_time、reference或其精确可重建定义；初态。
- 当前实际机臂状态/命令与风载，或能够用该航次固定参数精确重建的场景信息；标签需要的truth字段不得丢。
- 请求/裁剪/分配/实际wrench；motor_command、motor_setpoint和实际电机转速。
- 位置/姿态规范实际补偿、名义量、原始/滤波姿态参考及滤波速率/加速度。
- 独立位置/姿态事件标志、Head update_executed、beta、ready、held补偿。
- 网络特征和phi按事件记录；W0、每事件W_after或DeltaW_after按事件记录；不在每1ms保存重复完整权重矩阵。
- PCF eta、学习面、输出限幅/投影/饱和、推理event耗时；失败原因与真实停止时刻。
- 本航次有效cfg/opts的必要数值及model_id，不包含旧模型或旧绝对数据路径。

不要在raw_run、run_start、events.csv、合并CSV、debug目录各保存一套同样的大数组。run_start只存开始状态与小元数据；事件H5是训练输入；原始完整矩阵审计优先按100Hz而非1kHz保存。

V3.11 runner有大量不活动TCN/NDO历史诊断数组。允许不写出不活动字段；不得删掉当前B/KAN的实际作用量及未来姿态标签所需字段。优化前后对同一人工fixture的控制输出、更新和标签必须一致。

### 15.6 Gate状态机

允许状态：

```text
NOT_STARTED
RUNNING
PASS
FAIL_DATA_CONTRACT
FAIL_RUNTIME_CONTRACT
FAIL_PERFORMANCE
BLOCKED_MISSING_SOURCE
BLOCKED_CONTRACT_CONFLICT
PAUSED_ENGINEERING
PAUSED_RESOURCE
STOPPED_UNSAFE
COMPLETE_WITH_NEGATIVE_TEST_RESULT
```

`gate_status.json`至少记录当前Gate、所有上游状态、实际产物路径、数据角色计数、当前模型/配置版本和下一允许动作。运行前与运行后原子写入状态。

G00–G11只有PASS可以解锁下一研究阶段。G12的完整否定测试结果允许进入G13仅写报告；不解锁训练、改配置或新测试。

### 15.7 幂等执行与工程错误恢复

- 已accepted且合同一致的完整tuple直接跳过，不重跑。
- 开始运行即记录attempt；真正进入首个Plant transition后标记plant_started，不能用MATLAB是否返回log推断0次调用。
- 执行过程中出现UndefinedFunction、I/O、序列化或训练恢复错误，保存失败状态，不得catch后仅打印“完成”。
- 仅编排/路径/I/O工程错误允许一次最小修复后、在相同物理tuple下使用新attempt恢复；不改控制/场景/训练超参数，前一失败attempt保留并如实计数。
- 第二次同类工程失败或无法确定是否已完成Plant的未决状态，停止并先核对存盘文件。若完整raw已存，只修复导出/指标，不重新跑Plant。
- 物理失败不自动重试，不改seed，不用另一场代替；停在对应Gate，交付具体原因。
- 训练中断保存/恢复同一fit的最后完整epoch、optimizer、RNG；不得把半个epoch当完整继续累计。
- resume不能仅依据文件名或`SUCCESS`：要比较数据角色/计数/版本、normalizer数组、模型结构和配置。无hash条件下依靠显式版本与数值合同，不假装实现了字节级防篡改。

### 15.8 退出码与实际状态

总入口对子进程使用明确返回码和机器可读状态双重检查。MATLAB异常或Gate失败必须导致非零退出码/明确失败状态；不能被`catch`吞掉后继续下一Gate。

建议退出码：0=本请求范围内成功完成，10=数据/合同失败，20=缺源/路径阻断，30=科学性能失败或不安全，40=资源/工程暂停。具体码可由统一入口集中定义，但0不能用于伪装FAIL。

若当前会话或执行环境无法继续，交付到最后一个真实完成Gate、下一条恢复命令和待处理事项；不能承诺后台继续执行，也不能把代码完成写成实验完成。

---

## 16. 执行入口、运行命令与交付格式

### 16.1 环境准备

先读取当前可用MATLAB、Python、PyTorch、CUDA、NumPy、SciPy、pandas、h5py版本；优先复用已有可用环境。缺依赖时明确报告，并只在DL1018独立环境内补齐本任务必需包；不改其他项目环境、不自动升级全部软件。

MATLAB计算使用源双精度控制实现；神经网络训练有CUDA则优先CUDA，无CUDA可用CPU但必须记录。不要为了GPU加速重写Plant或变更采样。

磁盘不足先暂停，不自动删除DL1009或新raw。可以删除本任务明确可重建的临时窗口缓存，但不能删除已接受原始航次、Selected模型或失败证据。真实资源状态与旧累计预算是两回事。

### 16.2 必须实现的CLI

总入口 `run_dl1018.py` 至少支持：

```text
--source-root PATH
--root PATH
--stage G00_MIGRATION              # 单Gate
--through G13_FINAL_REPORT         # 从当前状态顺序执行到指定Gate
--resume                          # 恢复，而不是覆盖
--status                          # 只读输出当前状态，不运行Plant/训练
```

`--stage`不能绕开上游Gate；直接请求G09而G08未PASS时应拒绝。`--through`逐Gate执行并在每Gate保存真实验收，失败立即停止。

### 16.3 用户默认Windows环境的命令示例

实现入口后，使用已核实的Python解释器执行，下面`python`代表该解释器：

```powershell
$SRC = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009'
$DST = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
Set-Location $DST

# 先真实完成迁移与合同验收；这不是手工把状态写成PASS。
python .\run_dl1018.py --source-root "$SRC" --root "$DST" --stage G00_MIGRATION

# 只有G00 PASS，才按顺序继续全部已授权阶段。
python .\run_dl1018.py --source-root "$SRC" --root "$DST" --through G13_FINAL_REPORT --resume

# 只看状态，不产生运行副作用。
python .\run_dl1018.py --root "$DST" --status
```

若需要单独定位某Gate：

```powershell
python .\run_dl1018.py --root "$DST" --stage G04_P_STUDENT --resume
```

具体MATLAB调用封装在总入口，例如：

```text
matlab -batch "addpath('<DST_ROOT>/matlab/runtime'); run_gate_dl1018('<DST_ROOT>','G02_P_TEACHER');"
```

总入口必须正确转义路径和传播MATLAB失败。禁止用`start`启动后不等待完成，再把阶段写成PASS。若实施中采用其他参数名，README与实际运行命令必须同步，并保持相同Gate语义。

### 16.4 每个Gate结束时的最小汇报

只写实际发生的内容：

```text
Gate:
状态:
运行命令:
实际新增Plant调用 / 完整 / 物理失败 / 工程错误:
实际完成fit:
关键合同检查及最大误差:
关键结果（单位、统计范围）:
产物路径:
下一步（仅在本Gate PASS时）:
```

不生成重复长篇背景报告，不用“全部正常”“大体通过”“应该一致”代替具体数值。源码只读但未执行的项目标为未执行。

### 16.5 最终交付物

- 可独立运行的DL1018代码与显式V3.11/R2E配置。
- 一份必要依赖/合同说明，不含文件hash或manifest扫描结果。
- scene_specs、dataset_plan、accepted episode索引、全部attempt状态。
- 位置/姿态各Initial、Final候选、Selected完整模型包及配套normalizer。
- 四个fit的history、epoch0与最终选模依据、前向/Head数值一致性证据。
- POSITION_DEV、ATTITUDE_DEV、FINAL_TEST逐场CSV及完整失败记录。
- FINAL_REPORT.md，明确哪些Gate完成、哪些未完成、是否通过科学目标。
- README中的真实运行命令和恢复方法。

不自动推送GitHub；不自动清理DL1009；不执行实机、SITL或硬件操作。

---

## 17. V3.11已出现或本次扩展必须防止的错误：对照检查表

| 错误模式 | 本任务必须采用的处理 |
|---|---|
| 把main或default_config当作最新有效合同 | 以指定实验分支V3.11/R2E为源，显式fixed与[Inf,Inf,6] |
| 将KAN替代误改为RBF+KAN叠加 | 第4节矩阵，数值检查RBF输出/更新均关闭 |
| 直接复制frozen_sources，运行仍依赖旧模型 | G00提取非训练配置，DL1018构造新S/opts，不加载旧模型 |
| 只迁移runner，漏掉前向/Head/日志trim helper | 首推理、首更新、末端日志路径全部做无Plant依赖/数值测试 |
| PCF断言强制online，冻结模式被拒绝 | 只放开冻结断言，保留eta/前向/beta/ZOH，在线算术不变 |
| R0/R3分法使Student训练只有HELIX | split在场景创建时固定；Student按384半组合规则，不从rep推split |
| Teacher增大而Student只有48条 | 单一Student TRAIN384，VAL48；明确区分训练与验证条数 |
| 为冻结/在线分别采全量Student造成冗余 | 只P_INIT_STUDENT一套、A_INIT_STUDENT一套 |
| 旧P_NEW方法名不被标签导出器识别，applied误写0 | 规范实际补偿字段＋力/力矩闭合，不靠不完整method字符串集合 |
| 姿态Student关闭RBF后rbf_update_flag全0，事件消失 | 独立attitude_event_flag；update flag不能当采样时钟 |
| 姿态Student仍读取RBF力矩导致标签错误 | 使用实际总姿态KAN补偿，tau_virtual与requested torque闭合 |
| 位置与姿态SiLU裁剪语义混用 | 位置unclipped分支；姿态X29 clipped分支 |
| 输出层转置/归一化器错配 | 保存成套模型，磁盘重载64fixture测试 |
| 冻结Head被实现为零输出或beta=0 | W0保留、输出正常；只有权重更新关闭 |
| 位置Head套用RBF gamma或旧0.25倍率 | 原位置公式：beta系数1、dt=.01、sigma=.002 |
| 姿态DeltaW投影误用于W0 | W0固定，只有DeltaW更新/泄漏/Fro投影 |
| 使用当前event的新setpoint作为当前X29输入 | 上一姿态事件setpoint；当前动作完成后才保存 |
| 全局滑窗随机拆TRAIN/VAL | 整个scene归同split、各行为同步；episode内构窗 |
| normalizer从Student/VAL/TEST拟合 | Initial Teacher TRAIN专用，Final不重算 |
| Student50%权重因缺任务全部落在HELIX | 核对source/task/wind实际有效权重，不按存在任务临时重新分配 |
| batch自归一化改变实际权重或双重加权 | 全局目标权重，避免sampler与loss重复加权 |
| Final从epoch1选，忘记Initial epoch0 | 先同一混合VAL重评epoch0，并将其作为best候选 |
| 不同VAL口径分数直接比大小 | Initial/Final在同一混合VAL上选，Teacher-only另列 |
| 为Teacher-only旧分数强制部署变差Final | epoch0保护、无改进保留Initial |
| 原48场门禁min12/task使DEV24天然失败 | 适配为DEV8/task、TEST16/task；保留比例门槛 |
| 捕获MATLAB错误后退出0被误判完成 | 退出码和Gate状态双检查，FAIL不解锁 |
| 已保存完整raw但指标脚本错误又重跑Plant | 用原raw恢复导出/指标，不重复物理航次 |
| 删除物理失败场、换seed补齐漂亮数据 | 保留失败、停止对应Gate，不伪装完整覆盖 |
| 各控制器采用不同风向/形态随机seed | 同scene_id外部实现与collector无关 |
| 用旧DL1009 B当新测试对照 | 只用DL1018新B；内部跨环共享有明确run_id |
| 改动Selected后继续沿用旧P_STAR/PA结果 | 模型配置冻结；改变即不同实验，不混表 |
| 用TEST反复挑最终方法 | G12前锁定，TEST不再选择 |
| 一个宏平均掩盖局部失稳或单位混合 | 完整率、峰值、饱和、阶段/任务、单位单列 |
| 自动扩为多模型/多seed/更多轨迹 | 不在授权范围；按本任务四fit与既定场数执行 |

---

## 附录 A：可直接实现的数据分配零Plant断言

下面只验证本任务设计的整数分配，不代替MATLAB物理场景生成预检。

```python
from collections import Counter

TASKS = ('HELIX', 'FIG8_3D', 'SQUARE')
S = {0, 2, 4, 6, 9, 11, 13, 15}
TRAIN = [(t, c, w) for t in range(3) for c in range(16) for w in range(16)]
STUDENT = [x for x in TRAIN if (x[2] - x[1] - 3*x[0]) % 16 in S]
VAL = [(t, c, (c + 3*t + 7) % 16) for t in range(3) for c in range(16)]
TEST = [(t, c, (c + 3*t + 11) % 16) for t in range(3) for c in range(16)]
DEV = [
    (0,0,3), (0,1,15), (0,4,0), (0,5,6), (0,7,8), (0,10,9), (0,11,12), (0,15,14),
    (1,0,4), (1,2,15), (1,3,1), (1,6,7), (1,8,8), (1,9,10), (1,12,13), (1,14,14),
    (2,0,5), (2,3,15), (2,5,2), (2,6,8), (2,9,9), (2,10,11), (2,13,12), (2,15,14),
]
assert len(TRAIN) == len(set(TRAIN)) == 768
assert len(STUDENT) == len(set(STUDENT)) == 384
assert len(VAL) == len(TEST) == 48
assert len(DEV) == len(set(DEV)) == 24
assert {c for _,c,_ in DEV} == set(range(16))
assert {w for _,_,w in DEV} == set(range(16))

for t in range(3):
    assert sum(tt == t for tt,_,_ in TRAIN) == 256
    assert sum(tt == t for tt,_,_ in STUDENT) == 128
    assert sum(tt == t for tt,_,_ in DEV) == 8
    for c in range(16):
        ws = [w for tt,cc,w in STUDENT if tt == t and cc == c]
        assert len(ws) == 8
        assert {w//3 for w in ws if w < 15} == set(range(5))
    for w in range(16):
        assert sum(tt == t and ww == w for tt,_,ww in TRAIN) == 16
        assert sum(tt == t and ww == w for tt,_,ww in STUDENT) == 8
    for pool in (VAL, TEST):
        rows = [x for x in pool if x[0] == t]
        assert len(rows) == 16
        assert {c for _,c,_ in rows} == set(range(16))
        assert {w for _,_,w in rows} == set(range(16))

assert sum(9 <= w <= 14 for _,_,w in STUDENT) == 144
pools = {'TRAIN': TRAIN, 'VAL': VAL, 'DEV': DEV, 'TEST': TEST}
seeds = []
for code, (split, pool) in enumerate(pools.items()):
    for t,c,w in pool:
        seed = 2026101800 + 10000*code + 1000*t + 16*c + w
        assert 0 <= seed < 2**31
        seeds.append(seed)
assert len(seeds) == len(set(seeds)) == 888

# 不同split允许相同(t,c,w)类别，但必须使用不同外部实现；
# 不能用set(TRAIN)&set(TEST)非空就判数据泄露，也不能只看seed不同就保证独立。
# 还要由MATLAB生成后检查有效风/形态/参考内容及各角色同场输入一致。

stage_calls = [1632, 432, 72, 816, 432, 48, 240]
assert sum(stage_calls) == 3672
assert 1536*394 == 605184
assert 1920*394 == 756480
assert 96*394 == 37824
assert 144*394 == 56736
assert 96*1968 == 188928
assert 144*1968 == 283392
```

---

## 附录 B：机器可读Gate结果建议结构

这是结果结构示例，不是预填PASS：

```json
{
  "gate_id": "G04_P_STUDENT",
  "status": "NOT_STARTED",
  "contract_version": "DL1018_V311_R2E_PAPER_FINAL",
  "upstream_passed": false,
  "model_id": null,
  "actual_counts": {
    "train_complete": 0,
    "val_complete": 0,
    "plant_started": 0,
    "physical_failures": 0,
    "engineering_errors": 0
  },
  "checks": {},
  "max_errors": {},
  "artifacts": [],
  "next_gate_allowed": false,
  "blocking_reason": null
}
```

合同标识固定为`DL1018_V311_R2E_PAPER_FINAL`。这是正式论文工程，不另开小数据试跑版本；不得随结果改动同名合同的内容。

模型选择结果至少包含：

```text
initial_model_id
final_candidate_model_id
normalizer_id
epoch0_score_on_current_val
best_epoch
best_score_on_current_val
selected_model_id
selected_origin = INITIAL 或 FINAL
student_changed_selected = true/false
teacher_val_score
student_val_score
per_task_scores
```

不要用checkpoint文件名相同就证明模型身份；要核对数值数组、结构与本轮选择记录。

---

## 附录 C：本任务书依据的源文件

以下链接固定到编制时核实的实验分支提交，用于解释合同和实现来源。执行不要求计算任何文件hash；链接中的Git提交号仅用于源码定位。

- [S01 V3.11冻结参数与输入/Head定义](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/configs/V311_FROZEN_OPTIONS.json)
- [S02 R2E已生效共享滤波配置](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/configs/R2E_SHARED_FILTER_CONFIG.json)
- [S03 Plant/BS/RBF基础参数源](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/code/code/default_config.m)
- [S04 固定名义参数与C0/J0构造](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/code/code/controller_parameters.m)
- [S05 旧配置加载依赖，需要在DL1018解除](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/frozen_sources_v311.m)
- [S06 KAN替代RBF的原options factory](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/controller_options_v311.m)
- [S07 V3.11活动闭环主循环](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/run_position_stage1_closed_loop_v311.m)
- [S08 V3.11参考轨迹、风频表与机臂模板](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/make_scenes_v311.m)
- [S09 位置物理残差标签源](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/position_advantage_stage1_v1/methods/stage1_events_from_log.m)
- [S10 姿态教师标签源及需要扩展的事件/力矩读取](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/attitude_events_v311.m)
- [S11 X29合法特征精确定义](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/attitude_kan_legal_input_reuse_upgrade_v3_6/local_runtime/attitude_feature_row_v3_6.m)
- [S12 位置KAN结构与unclipped-SiLU来源](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/kan_position_attitude_followup_v2/training/train_models_repair_v2.py)
- [S13 姿态KAN结构、归一化输出与clipped-SiLU来源](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/attitude_kan_legal_input_reuse_upgrade_v3_6/training/train_initial_models_v3_6.py)
- [S14 原位置Head输出后更新公式](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/position_advantage_stage1_v1/methods/position_stage1_update_head.m)
- [S15 原PCF学习面协调](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/k1_command_filter_update_coordination_v3_5/local_runtime/position_stage1_update_head_pcf_v3_5.m)
- [S16 原PCF eta精确更新](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/k1_command_filter_update_coordination_v3_5/local_runtime/position_filter_realization_pcf_step_v3_5.m)
- [S17 R2E位置Initial/Final及epoch0机制](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/training/train_position_r2e.py)
- [S18 R2E合法姿态训练入口](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/training/train_attitude_r2e.py)
- [S19 V3.11闭环Q/A和失败时段指标源](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/local_runtime/final_metrics_v311.m)
- [S20 R2E性能门槛及峰值定义](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/multitask_retrain_v311/cf_shared_retrain_r2e/local_runtime/evaluate_r2e_gate.m)
- [S21 旧位置Gate标签映射错误的范围说明](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/r2e_position_regression_diagnosis_v1/LABEL_TIMING_AUDIT.md)
- [S22 helper路径遗漏的真实执行记录](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/experiments/position_adaptation_aligned_training_v1/reports/CANARY_ENTRYPOINT_PATH_AUDIT_CONTINUATION_01.json)
- [S23 Euler与机体系角加速度转换](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/code/code/attitude_bs_step.m)
- [S24 原事件调度器](https://github.com/tengzumin/DL1009/blob/3671d2d212af927abdb6d9149a1b249c372ac55e/RBF-BS0/code/code/rbf_event_scheduler_step.m)

本任务对场数、Student半组合、单一Student身份、Final姿态追加训练、DEV24/TEST48及新增P_STAR增量比较的规定，是本次用户确认后的DL1018实验设计；不要把这些新配额写成已经存在于DL1009历史代码的事实。

---

## 执行开始指令

现在开始G00。先读取源和确认活动合同，再迁移。不要直接训练；不要先删任何数据；不要运行hash/manifest；不要重新策划另一条路线。

G00完成且数值合同PASS后，自动按本任务书顺序继续。每一步都以真实代码、数据、配置和结果为依据。任何必须猜算法、缺少权威helper或发现物理合同冲突的地方，停止并明确指出，不用自创实现填补。

**最终目标是可解释、可复核的DL1018结果，不是保证某个KAN/Head一定获胜。**
