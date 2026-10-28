# B vs ON1 记录与配置差异审计：预登记

状态：仅完成首场 B/ON1 的 `run_start.mat` schema/value 观察与首条 ON1 raw schema 观察；尚未批处理其余 11 场，尚未生成差异结论。本文件在全 12 场比较前固定审计口径。

## 冻结输入与样本

- C1 source lock：`experiments/position_prior_calibration_c1_20261022_v9/C1_SOURCE_LOCK_v2.json`，SHA256 `02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5`。
- C1 v9 release：`experiments/position_prior_calibration_c1_20261022_v9/C1_RELEASE_v9.json`，SHA256 `7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0`。
- C1 per-run index：`experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv`，SHA256 `43aab1c0fa906dfa5e3d7f175339a5607bd4ec2e2cc55687741524d34fa08bac`。
- 固定 12 场表：`reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv`，SHA256 `176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e`。
- 逐场只配对 `scene_id` 相同的 `condition=B` 与 `condition=ON1`；不纳入 ONC。按冻结 12 场表顺序输出全部 12 对。首场 B 的 `reused_prior_run=true`、实际 release 为 v8 `82dcf11c…ded69b7`；同场 ON1 与其余新 B 的 release 为 v9。不得把首场 B 改标为 v9。

## 首场 schema 观察与记录边界

首场 B/ON1 的 `run_start.mat` 均为 HDF5/MATLAB 结构，根包含 `runStart` 和 MATLAB reference store `#refs#`。`runStart` 有逐运行身份、release/hash/timing 字段及 `options_audit`，但没有完整 `cfg` 或 `opts` 树。当前已见 `options_audit` 字段为 `model_id, seed, selected_step, c_star, pcf_enabled, update_enabled, head_type, gamma, beta_scale, model_output_W_sha256, normalizer_arrays_sha256, on1_initial_weight_sha256, onc_initial_weight_sha256, allowed_option_differences, b_baseline`；这不是完整 opts 快照。首条 ON1 raw 根为 `log, runIdentity, #refs#`，也未见根级 `cfg/opts`。之后逐一核对 24 个 raw/run_start，不由首场推断全体。

C1 source lock 同时固定了 `configs/effective_config.mat` 的 SHA256 `cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f`；C1 runner 在调用 Plant 前验证该文件身份，所有航次使用同一锁定 config 输入。故结论需区分“实际 cfg 值有共同冻结来源”与“逐航次没有保存完整 cfg 快照”。`opts` 完整值没有逐航次快照；可以读取锁定 builder/runner 作“源码推定配置”，不能称为当时实际 opts 快照。

## 比较与分类规则

1. 对 24 个 raw、24 个 `run_start.mat` 以及对应 `run_status.json` 记录存在性、大小、mtime 与读前/读后 SHA；先比对 C1 per-run 中记录的 SHA。所有输出留在本目录，不复制 raw。
2. 递归枚举 `runStart`、`runStart.options_audit`、raw `runIdentity` 与 `log` 下真实保存的字段。对每字段登记 MATLAB class、逻辑 shape、HDF5 dtype、值/有限性；MATLAB 字符串、cell/reference 只解码被记录字段所指向的对象，不把 `#refs#` 内部对象误当额外配置。
3. 完整配对并逐元素比较输入身份：scene/payload hash、initial state、reference、time/transition clock、arms/morphology、环境风序列、impulse/state perturbation 与其他 exogenous input。对 config scalar 与 small static input 数组比较实际值；对长时序输出、状态轨迹、控制命令、在线权重演化只登记 schema/非有限性和摘要，不以闭环结果不同判作配置不公平。
4. 每个观察差异归入且只归入以下审计类别：`预定方法差异`（明确属于所选位置补偿/PCF/online-head 方案的选项）、`非预定配置差异候选`（共同位置BS/姿态BS/RBF/滤波/名义C0/J0/Plant/limits/gains/scheduler/motor-lag/fallback/safety/input字段不匹配）、`运行记录元数据`（scene/run/condition/release/preflight/start time/timing/CPU负载等）、`闭环输出差异`（state/command/online weights及其下游结果）或 `未记录/未知`。疑似非预定项需保留原字段、值、shape、源，不先宣判bug。
5. 方法解释与执行分支语义由独立代码审计核对；本审计只凭实际记录与冻结来源，不因同一源码文件或同一 cfg hash 推断执行分支完全相同。

## 预定的重点字段检查

位置 BS 请求/补偿输入及开关；DSSM/RBF 位置头初值、类型、bias、PCF 与更新设置；姿态 BS/RBF/head 与开关；命令滤波；固定模型 C0/J0、质量/重力/惯量/形态；推力/倾角/分配/电机限幅、motor lag；event scheduler/frequency/readiness/context；增益、dmax、beta/scale、gamma/kappa；风/形态/参考/初态；seed、fallback、safe-stop 条件。未保存字段必须逐项列出并标明只能从哪个冻结源码/文件重建。

## 执行边界

仅 PowerShell 7 `pwsh`（login:false）与单线程离线读取；不启动 MATLAB/Plant、不训练、不用 GPU/optimizer、不访问 TEST、不改/移动/删除历史文件。此任务新增预算以主审总账为准；代码、表与报告仅写本目录。只有全部 12 对完成且差异账本可审，才报告是否存在配置公平性证据；不据此自行运行实验。
