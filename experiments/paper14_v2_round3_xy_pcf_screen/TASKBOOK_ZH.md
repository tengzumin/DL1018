# DL1018 Round 3：仅 XY 应用 PCF eta 的 12 场机制筛查任务书

版本：`PAPER14_V2_R3_PCF_XY_ONLY_SCREEN_20261022_REVISION_2_FROZEN`  
冻结时间：2026-10-21 22:49 UTC（2026-10-22 06:49 Asia/Shanghai）  
主目标：`reports/paper14_v2/STATE.json` 中的 72 小时论文结果攻关目标，硬截止 2026-10-24 17:01 UTC。Round 1 与 Round 2 已各完成一次 12 场筛查；本任务书是最多三轮中的最后一轮。

## 当前决定和严格边界

Round 2 PCF-off 通过运行安全检查但未通过性能筛查：高频 W09–W14 的 OFF 平均 Q 比 ON 高 1.134 mm、比 B 高 1.214 mm；W15 比 B 高 1.508 mm；全 12 场宏平均比 B 高 0.640 mm。离线同状态审计显示水平 eta RMS 与 surface RMS 同量级，水平面 sign flip 比例约 36%/39%；Z eta 较小、Z sign flip 约 13%。这些只支持下一轮区分方向，不是 mask 候选的闭环因果结果。

本任务书只授权在本 Round3 子目录创建隔离 runtime/runner、冻结锁、离线/static smoke、预检、评分与报告。代码通过主模型独立复核前，不得启动任何 MATLAB Plant 航次。测试只允许 12 个已冻结 VAL 场景；此刻不授权 72 场、训练、TEST、模型搜索、超参搜索、教师/学生采集或重跑对照。

任何时刻都不得结束、抢锁、重启或改动其它正在运行的实验。只使用 PowerShell 7。输入原始 MAT、模型、normalizer、缓存、测试集与旧账本全部只读且原位保留；Round3 仅在本目录写新源码、报告、状态与候选 raw。不得删除任何文件或通过移动/复制/改名改变保护输入。

## 唯一优先假设与唯一处理因素

假设 H3：**PCF eta 对 X/Y 的 Head 更新面协调可能有用，而同时对 Z 应用该偏移可能造成不必要的垂直更新变化；只在 Z 轴 Head 更新面关闭 eta 扣除，有望保留 X/Y 的 PCF-on 行为并获得 PCF-off 的部分 Z 改善。** 这是可证伪假设；不预设通过或论文贡献成立。

唯一候选 `DSSM14_PCF_XY` 在每个 FEATURE 在线更新事件采用固定 mask：

```matlab
etaEffective = [1; 1; 0] .* etaBeforeEvent;
sCoord = surface - etaEffective;
sEff = clip(sCoord, -[7;8;10], +[7;8;10]);
```

实现允许将上述等价运算直接内联在隔离 runner。不得修改 eta 的 1 kHz 递推、PCF 参数、Head/网络/训练、W0、gamma、beta、泄漏、投影、输出限幅、X14 输入、B 姿态闭环、C0/J0、Plant、执行器、场景或步长。不得将 B 的任一轴输出拼入候选。

同一记录状态上必须逐元素满足：候选 `s_eff_x/y == PCF-on s_eff_x/y`，候选 `s_eff_z == PCF-off s_eff_z`；Head 输出先于 W 更新，所有其余向量与权重在 `[-60,60]` 投影规则不变。真实闭环状态允许因候选干预而分叉。方法的新颖性、理论贡献与闭环性能都未被此项恒等关系证明。

## 冻结输入、场景、训练与配对

- 只复用 Round2 输入锁 `experiments/paper14_v2_round2_pcf_screen/frozen_inputs.json`（SHA256 `92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58`）中身份合格的 model、normalizer、W0、runtime、Plant、ON raw、B raw；Round3 必须生成自己的 path/SHA 输入锁并逐项验证继承，不修改 R2 锁。
- 场景、顺序、种子及采样完全复用 Round2：seed `2026102001`，X14，1 kHz Plant、100 Hz Head，20 s/20,000 计分转换，optimizer steps=0；固定 12 场如下。

| 顺序 | VAL scene ID | 组 |
|---:|---|---|
| 1 | `DL1018_VAL_T2_C00_W10` | W09–W11 |
| 2 | `DL1018_VAL_T2_C02_W12` | W12–W14 |
| 3 | `DL1018_VAL_T2_C05_W15` | W15 |
| 4 | `DL1018_VAL_T2_C06_W00` | W00–W08 |
| 5 | `DL1018_VAL_T1_C02_W09` | W09–W11 |
| 6 | `DL1018_VAL_T1_C05_W12` | W12–W14 |
| 7 | `DL1018_VAL_T1_C08_W15` | W15 |
| 8 | `DL1018_VAL_T1_C00_W07` | W00–W08 |
| 9 | `DL1018_VAL_T3_C12_W09` | W09–W11 |
| 10 | `DL1018_VAL_T3_C00_W13` | W12–W14 |
| 11 | `DL1018_VAL_T3_C02_W15` | W15 |
| 12 | `DL1018_VAL_T3_C03_W00` | W00–W08 |

候选只新跑这 12 场；按各自 scene ID 精确复用 R2 PCF-on、PCF-off、B raw。ON/B/OFF/XY 的 `reference/position` 输入必须逐元素完全相等；不得要求不同方法的闭环 `state/position` 逐点相等。Q 使用 `[0,20)` 的三维位置 RMSE、场景等权宏平均，胜负沿用未舍入值和 `1e-12 m` 容差。所有运行和失败尝试都写入账本。不得重跑对照或把重复失败隐去。

## 交付代码、预检与审核步骤

执行者只使用 GPT-6-Luna xhigh、正常速度（工具若不能设置速度，记录限制）。一次只允许一个 MATLAB/Plant 重负载作业；不得并发改同一文件。单轮不训练，因此 GPU 空闲不替代进程/磁盘/输入身份预检。剩余空间低于 30 GB、磁盘预算超过 80 GB、输入或源码 SHA 不符、MATLAB 已有任务占用或硬截止剩余不足以完成授权批次时，停止并报告，不自动清理空间。

隔离包须至少包含 runner 与本地 runtime、候选选项构造、冻结 inputs JSON、逐场 identity/status verifier、预检/launcher、scorer、同状态 smoke、任务账本、`reports/`。运行源码必须拷贝到本目录隔离版本，不得直接改外部历史 runner 或 DL1018 正式 runtime。

静态与离线验证至少证明：

1. 以冻结 PCF-on options 为基准，候选除 Z 轴 eta mask 外与 PCF-on 逐字段一致；实际调用的是本 Round3 runtime/helper，身份逐字节锁定。
2. 同一 synthetic/logged event 上，XY 两轴 `s_eff` 与 PCF-on 完全一致，Z 与 PCF-off 完全一致；离散 eta、FEATURE 前向、W0 与输出先更新后更新的矩阵方向/尺寸一致。
3. MATLAB 与 Python 对 mask/限幅/更新式的离线计算一致到 `1e-12`；smoke 明确不调用 `run_episode_dl1018`、Plant、执行器、训练或 TEST。
4. 输入锁从 R2 引用路径/SHA，复核 12 组 B/ON/OFF raw 身份、候选模型与 normalizer；不复制任何 raw/MAT/cache/checkpoint/fixture。
5. preflight 读取-only 检查 PowerShell 7、MATLAB/Plant 进程、GPU compute 活动、输出目录、磁盘余量与剩余时间；每个候选状态包含 scene、`head_type=FEATURE`、update=true、PCF enabled、eta mask `[1,1,0]`、模型/normalizer/W0、runtime/Plant 源 SHA、raw SHA 及 R2 输入 SHA。候选 raw 必须直接留有 `surface/eta/s_coord/s_eff` 和每个 Head event 的 W 前后值，支持独立复核 mask。

主模型先审核完整 taskbook、实际源差异、options smoke、哈希锁、preflight 与 launcher，再批准 PROBE。PROBE 只运行顺序 1 的场景，完成后暂停，主模型独立审查 status、run_start、raw、分组指标、时间与安全记录。只有该审核通过才可 CONTINUE 固定余下 11 场一次。任何身份、代码、完整性或安全错误都停止；只有明确工程原因且事先有新审核的修复才允许一次复测。性能方向不佳不属于工程重试理由。

## 预登记 12 场联合筛查门槛

所有门槛同时满足才可请求 72 场扩展审核；本 taskbook 不自动授权 72 场。

1. XY 候选 12/12 `STABLE`、20,000 transitions、finite/complete/safe/identity verified；12 场每场在线更新事件数和 eta/协调日志完整；真实事件值符合固定 `[1,1,0]` mask。不得有新的非有限、完整性、安全、饱和或执行器异常。
2. 高频 W09–W14 的候选宏平均 Q 严格低于 PCF-on、严格低于 Round2 PCF-off，且不高于同组 B（只允许 `1e-12 m` 数值容差）。
3. 高频 W09–W14 至少 4/6 场 Z RMSE 严格优于 PCF-on，单场容差 `1e-12 m`。
4. W15 与 W00–W08 各组三场宏平均 Q 均不高于同组 B，允许 `1e-12 m` 数值容差。
5. 全 12 场候选宏平均 Q 严格低于 B；同时给完整逐场 Q、胜平负、改善幅度、逐轴 RMSE、0–5s/5–20s、峰值/安全/饱和/控制耗时和身份记录。不能用胜率取代收益幅度。

任一门槛失败：记录具体失败项，保留全部 12 场，Round3 作为第三轮收束；不调 mask、不扩场、不训练、不解封 TEST。即使全部通过，主模型仍需单独审查是否值得做完整 72 场开发验证。

## 资源与后续论文证据

Round2 12 场候选 attempt+raw 平均 20.776 s、最大 21.190 s。粗略按 21.19s×12×1.25 预留约 318s（5.3 分钟），另加一次 PROBE 审核、preflight 与报告整理；在正式运行前还必须使用新 PROBE 实测重新计算是否能在硬截止内完成。

闭环预算 684 航次上限包含已完成的 R1/R2 24 场；Round3 本任务最多 12 场，不含任何复用 B/ON/OFF。若 12 场通过并获主模型批准，72 场候选验证需另行冻结任务书；只有开发集满足 62/72 胜、场景宏平均 Q 严格优于 B、高频 W09–W14 与 W15 组均值不高于 B，且贡献/理论/关键消融审核通过，才能考虑一次独立 TEST48。TEST 最多六种方法，不重跑宣称成功；失败封存并报告。现有理论审查指出实际 1 kHz Plant、100 Hz projected-Euler Head、ZOH、姿态/执行器饱和的离散 ISS/UUB 证明仍未达标；此缺口未解决时 TEST 继续封存。

## 主模型审核记录

2026-10-21 22:49 UTC：主模型复核 R2 全 12 场配对复算和 23,616 个 PCF-on 事件的同状态重放，保留唯一待测假设为 X/Y eta 保持、Z eta 应用 mask 设为零。Luna xhigh 对加固后的离线审计器及产物作最终只读代码复核，无剩余 blocker；它确认实际 B raw SHA、初值/跨步 eta 连续性与冻结 DEV/VAL 范围检查都已补齐，未运行任何脚本/实验/MATLAB/Plant，也未访问 TEST。加固审计器重跑为 12 场、23,616 事件，初始 eta 与跨步连续误差均 0，递推舍入误差 `3.00454e−15`，输出重放误差 `4.44089e−16`。根因报告：[R2 根因审核](../paper14_v2_round2_pcf_screen/reports/round2_root_review_20261022.md)；审计脚本 SHA256 `1d7e78d855ccd4c11e996c86c9e244a48e78c60dc93346c55b06829d1d5fcacc`，审计 JSON SHA256 `6f4f75adc18b5f07cda29f60d5a7518670fb93613658cd8b8fbdd9fec3688aed`。本任务书冻结只授权在本目录搭建隔离候选包、做静态/离线 smoke 和只读预检，不授权任何 MATLAB Plant 航次。代码包交付后，主模型须独立审核实际差异、smoke、输入锁、preflight 与 launcher；只有通过后另行签发 PROBE 决定，再按 PROBE—审核—CONTINUE 顺序执行。

## 可复现入口

执行者补齐脚本后在此记录准确 PowerShell 7 命令、静态/离线检查命令、输入与源码 SHA、状态续跑入口和每次启动/资源账本。命令不得由执行者自行假定或扩展；PROBE/CONTINUE 均必须要求 `-ParentReviewed`，且每次运行先生成并检查新的 PASS preflight。
