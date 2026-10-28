# C1 B/ON1 配置与运行记录审计

状态：24 条运行记录审计通过；未启动 MATLAB/Plant，未训练、未使用 GPU/optimizer/TEST。审计范围是 12 个固定场景的 B 与 ON1 配对记录。分层/场景清单、C1 per-run 索引、source lock、release 和任务书均按 SHA 固定；B 首场仍按 v8 授权复用身份记录，其余 11 条 B 和 12 条 ON1 为 v9。

## 可核验结果

- 24 份 raw、run_start、run_status 共 72 个文件的 SHA 与 C1 per-run 索引匹配；读前/读后 SHA 与 stat 均不变。`FULL12_RECORD_IDENTITY.csv` 的 336 项身份检查全部通过；run_status 字段表含 360 项配对比较，其中 261 项相同、99 项不同/单侧缺失。状态均为 STABLE，差异包括条件、发布来源、计时/执行时长、输出校验状态与输出指标，不是静态配置差异。
- 12 对配对输入共 312 项比较：300 个数组逐元素 SHA、shape、dtype 完全一致，另 12 项确认 `log/state` 初样本与 `log/initial_state` 自洽。数组含 reference、initial state、time、wind、physical-impulse/state-perturbation记录及完整 arms 子树。父审另对 24 条 raw 的 reference、initial state、wind 与 arms 做独立数值复核，最大输入差为 `4.44e-16 N`，见 `reports/c2_deployable_residual_parent_20261023/COMMON_POSITION_CHAIN_PARENT_CHECK.json`。
- 全部 24 份 raw/root 与 run_start 均没有逐运行的 `cfg` 或完整 `opts` 对象。**配置来源有身份**：冻结的 `configs/effective_config.mat` SHA 为 `cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f`，C1 runner 在初始化前校验锁定源并调用锁定的 `init_dl1018.m`；该函数从此 MAT 文件加载 `cfg`。完整字段、shape、dtype、有限值计数和值保存在 `FULL12_LOCKED_CFG_TREE.json`。因此静态 cfg 来源相同且可追溯，但没有逐航次 opts 快照，不能从保存件证明任意未记录内存字段逐位相同。
- 锁定 cfg 中主要共同量为：Plant `dt=0.001 s`、mass `0.695 kg`、`g=9.8`、惯量 `diag(0.012,0.012,0.022)`；position BS `k1=[1,1,1]`,`k2=[4,4,4]`；attitude BS `k1=[1.5,1.5,1.3]`,`k2=[22.5,22.5,12.7]`；command filter `wn=[18,18,12]`,`damping=[1,1,1]`,`acceleration_limit=[Inf,Inf,6]`；固定形态，motor limit `0..1900`，倾角上限 `π/6`。完整 cfg 树也保留其余执行器、风、RBF、TCN、参考与限幅字段。

## B 与 ON1 的已记录方法差异

冻结源码的构造链明确区分两种控制器。B 使用 `controller_options_dl1018(cfg,'B',[],[],'online')` 的既有 RBF baseline。ON1 使用 `position_only_search_options(cfg,model,'FEATURE',12,1)`：其 position FEATURE 头由冻结 DSSM14 seed `2026102001`、step `60000` 的 `W0` 初始化，`gamma=12`,`kappa=1`，启用在线更新与 command-filter PCF 协调，并关闭 position RBF 输出/更新；attitude 路径沿同一 locked cfg / RBF 控制器。来源脚本身份及逐条件构造见 `FULL12_AUDIT.json` 与下面差异表。

24 份 raw 的条件日志一致支持该区分：B 的 `stage1_position_pcf_coordination_enabled=0`、`replacement_enabled=0`、`search_head_enabled=0`，head type 为空，gamma/kappa 为 NaN 占位，stage1 initial-weight 字段为零占位；ON1 对应字段为 `1/1/1`、`FEATURE`、gamma `12`、kappa `1`，初始头权重在 12 场中完全相同。不要把 B 的 stage1 占位权重/NaN 当作实际 RBF 权重或 PCF residual。

有一项记录口径缺陷需要保留：`build_c1_options.m` 产生的是共享 `optionAudit`，`run_c1_screen.m` 把同一份结构写入每个条件的 `runStart.options_audit`。其 15 个字段在 24 份中一致，含 `pcf_enabled=1`、`update_enabled=1`、`head_type=FEATURE`、gamma `12` 和 ON1/ONC 模型哈希；这份公共 audit 主要描述候选设置，并非 B 的实际 opts 快照。`allowed_option_differences` 只列 ON1 与 ONC 间 weight/kappa 差异，不是 B 与 ON1 的完整差异表。审阅 B 时应以 condition 对应的构造源码与该场 raw 的有效日志共同判断。

`FULL12_PAIR_FIELD_DIFF.csv` 保留每个场景所有 473 条 raw/run_start 字段差异及两侧原值；`FULL12_STATUS_FIELDS.csv` 保留全部 status 字段。除预期方法/闭环结果与运行记录差异外，当前没有发现额外静态 cfg 输入变化。raw 未序列化完整 opts，因此此结论是“未见意外差异”，不是对未保存对象做过逐位比较。

## 产物与复核入口

- `PRE_REGISTRATION_ZH.md`：预先登记的样本、字段、比较口径与边界。
- `audit_b_on1_records.py --full`：24 份 raw/run_start/status 与 locked cfg 的只读审计；本次全量 wall time `8.69 s`。
- `audit_record_status.py`：status 字段和 raw/runStart/status 身份交叉核验；零失败。
- `FULL12_FILE_IDENTITY.csv`、`FULL12_RECORD_IDENTITY.csv`、`FULL12_STATUS_FILE_IDENTITY.csv`：文件哈希/统计信息与身份绑定。
- `FULL12_H5_SCHEMA.csv`、`FULL12_STATUS_FIELDS.csv`：24 份保存结构/字段值与 status 全量字段对照。
- `FULL12_PAIR_INPUT_MATCH.csv`、`FULL12_PAIR_FIELD_DIFF.csv`：配对输入核验与全部非相同字段。
- `FULL12_LOCKED_CFG_TREE.json`、`FULL12_AUDIT.json`、`FULL12_RECORD_METADATA_AUDIT.json`：完整 cfg 树、源身份与计数摘要。
- 首对 smoke、首次错误快照及 `FAILURE_LEDGER.json` 均保留；初次 smoke 的索引路径假设错误已修正。没有改动任何 C1 历史运行文件。

主要输入身份：任务书 SHA `f1b46337649ea3a1f73b0b8e8540dae61a849c453260274c4d47a4c1d642d6e4`；C1 source lock SHA `02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5`；C1 release-v9 SHA `7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0`；per-run 索引 SHA `43aab1c0fa906dfa5e3d7f175339a5607bd4ec2e2cc55687741524d34fa08bac`；12 场景清单 SHA `176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e`。
