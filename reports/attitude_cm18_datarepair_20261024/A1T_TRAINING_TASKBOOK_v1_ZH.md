# A1T：直接补偿目标单因素训练任务书

**状态：`IMPLEMENTATION_APPROVED_TRAINING_NOT_RELEASED`**  
Root，2026-10-25。仅批准实现、源码审查与零步自检准备；未批准 optimizer、正式训练或 Plant。

## 目的与边界

A1R 修复参考教师后，B/C5 同记录状态评估改善有限，yaw 仍变差。四场完整三轴诊断显示直接目标 `c*=G\E0` 在同状态代数上可行。A1T 只检验把训练目标换成当前姿态补偿接口对应的直接目标，不能据此宣称旧 behavior-residual 是实现错误，也不预设训练或闭环会改善。Residual 递归固定点仍是可行替代解释。

本次仅改变监督目标。继续使用 A1R 的 CM18 输入、架构、训练/选模协议与运行时 clip、beta、时序；不加风、真实几何、时钟或其他输入，不改限幅、不改 `X18`，不读 TEST，不启动 Plant。C5/C7 和历史 A1/A1R 工件保持不变。

## 直接目标定义

对每个真实事件，复用已审的完整矩阵定义和 source helper：

```text
G = Jtrue⁻¹ [Ct (C0⁻¹ [0; J0])]torque
E0 = Jtrue⁻¹ (wrench0_torque + windTorque − gyroTrue − JdotTrue·omega) − alphaBS
c* = G⁻¹ E0
```

其中 `Ct/C0` 均来自对应固定物理配置，不能化简成 `Jtrue⁻¹J0`；奇异/病态 `G` 不正则化。保持原 beta 时钟（包括既有 1 ms 接口偏移）和输出 clip。网络原始训练标签为 `target_raw_output_rad_s2 = c*/beta`，运行时仍执行原 `clip → beta`。同时保留 `c*`（beta 后施加目标）、`target_after_clip_beta_rad_s2`、beta、G column-major、限幅/可达性标志和物理/source身份，供闭合和可行性审计。beta=0 且 `c*` 超容差非零时数据不可训练；不得删行或编造有限标签，整个候选数据标为不 eligible 并停止放行。

## 数据与读取

- 顺序、scene ID、split 和 `X18` 沿用已 PASS 的 B_REF_REPAIRED ALL816：源 manifest SHA `0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5`；原 repaired ALL816 SHA `3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0`。新标签必须独立 schema，不能把新目标冒充旧 `target_raw`。
- 数据 agent 正在实现的 C* manifest/reader 尚未冻结。预期为 816 原序、768 TRAIN/48 VAL；专用 target 字段 `target_raw_output_rad_s2`，按 scene/event ordinal 绑定原 cache 的路径与 SHA，从原 cache 读取 `X18`、时间、phase、plant_index。路径、schema、API 和 SHA 均以其最终冻结结果为准；当前不据此写入正式 pins。
- Root 独立审计须核逐场身份、事件全覆盖和物理闭合；不筛不可达、高误差或 zero-basis 事件。记录每轴 clip、allocator 限幅、电机饱和、beta=0 不可达、zero-basis 目标计数。若网络零 basis 无法表达的目标非零，保留该事件并披露，不以过滤改善评分。

## 单因素训练协议

- 架构固定 `18→32 tanh→32 tanh→24` 系数模型及 `[z/2;u]` basis，保留精确 zero-basis 输出为零。
- seed `2026102001`；60,000 optimizer steps；batch 512；有放回均匀采样；Adam `lr=0.001`、`weight_decay=1e-5`；SmoothL1 `beta=1`；A1R 相同 deterministic float32 CUDA、无 AMP/TF32 协议。禁止换 seed、加步数、调结构或搜索目标。
- 每个 TRAIN 场仍取 zero-based `0,5,...,1995` 共 400 行；总 307,200 行。输入 `mean/std` 必须从 A1R 冻结 normalizer JSON 的 canonical float64 数组逐元素原样复用并核验，不能因布局重算造成末位变化。A1R 完整 normalizer SHA `faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c` 仅作为来源身份；A1T 新 normalizer 整体 SHA 会因目标轴 RMS 改变。
- `train_axis_rms_rad_s2` 只从 307,200 TRAIN stride 行的 `target_raw_output_rad_s2` 以 float64、ddof=0 重算，`std` floor 规则不变。其变化是标签变化带来的标准化伴随量，单独记录。保持 seed 同初始规则，并核 A1R 与 A1T 初始 W/b 逐元素相同。
- B C* VAL48 每 1,000 步完整计算、场景等权、按新 TRAIN target axis-RMS 归一化，严格下降才替换 best、平分保留最早。C5 不参与训练或 checkpoint 选择。

## 实现、自检与放行

先新增隔离的 A1T trainer，复用 A1R 的训练循环/模型纯数值模块，不调用或修改 A1R 正式入口；reader 与 target manifest 依赖必须锁定最终 SHA。零步自检验证 ALL816 TRAIN/VAL 隔离和场景顺序、所有事件 shape/finite、采样行数、原 X18 与输入 mean/std 一致、target-only RMS 和其独立审计值一致、A1R/A1T 初始 W/b 一致、zero-basis 为零、前后向有限且 optimizer-step 调用数为零。源码/source/data/taskbook SHA、零步 receipt 经 ROOT 审核并另行签发单次正式 release 后，才可运行唯一 60,000-step job。

正式输出建议 `experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/`，路径最终由 Root release 冻结；必须不存在才创建，真实失败和已完成步数留账，不覆盖、不从不完整状态续训。C* 缓存与训练产物分目录，模型权重/normalizer/checkpoint 标记 `DO_NOT_GIT_UPLOAD`。

## 结果解释

B VAL48 上 A1、A1R、A1T 需在**同一目标**分别报告：旧 behavior-residual 目标的原单位误差，以及 C* raw-output 目标的原单位误差；不得把各模型各自 normalized score 横向比较。另报逐场、逐轴、向量和 task/wind 组。

C5 当前只有旧 behavior 标签，旧标签评分只作历史诊断，不能被解释为 A1T 的直接补偿能力评分，也不能据此否定 A1T。需要 C5 direct-action 判断时另行设计无 Plant 的同状态物理 action replay 并经 Root 审核；不得用旧行为标签代替。

本任务书不批准正式训练、Plant、TEST、新结构或部署。训练 release 与启动权由 Root 单独持有。
