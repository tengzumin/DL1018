# TCN 训练与运行时代码审查 v1

审查时间：2026-10-26（Asia/Shanghai）  
范围：teacher dataset manifest、正式训练脚本、TCN Python/MATLAB 权重与推理接口、v4 runner 的特征构造、固定控制器惯量绑定、pilot release helper。静态审查；未启动 Plant 或读取 TEST。

## 结论

没有发现会使正式训练输入与 TCN runtime 输入维度、顺序或单位错配的遗留问题。Amendment 03 已将 runner 的第 7–9 个特征修正为 BS 名义力矩，当前 v4 runtime 顺序与训练 dataset manifest 一致：wrapped attitude error、body rate、nominal BS body torque、morph command。

候选 attitude arm 禁用 RBF 输出和更新。控制器保持 fixed morphology 的名义参数，网络输出经 beta 与 dmax 后由固定 J0 映射为补偿力矩；候选代码没有时变惯量重建、Jdot 估计或 observer。输入窗口只追加当前及过去事件，左侧归一化零填充与训练一致。

## 放行前需补齐

原 parity helper 只取一个 VAL window。冻结任务书要求逐样本 parity，因此增加 Amendment 05 的批量检查：48 个 VAL 场景各取事件索引 0、1、100、999、1998，共 240 个窗口、720 个标量输出；再对首个具有非零形态命令的 VAL 场景，用 1,999 个连续事件调用 MATLAB runtime step，核验历史缓冲和因果时序。Python helper 的 AST 检查通过，MATLAB Code Analyzer 报告 0 项；实际跨语言差值仍待正式 checkpoint 生成后运行，Plant 放行前必须满足最大绝对差不超过 1e-5。

## 研究解释边界

模型监督目标是 B attitude RBF 的原始动作。它能检验冻结 TCN 是否可作为 RBF 替代件，但监督本身不保证闭环性能优于 B。六场 TCN-only paired pilot 是下一个性能门，不能用离线 teacher RMSE 替代。

C5 的 72 场队列有 24 DEV + 48 VAL，48 个场景又参与 TCN checkpoint 选择；该队列必须称作 development evidence。独立结论依赖封存 TEST，不可把这 72 场重新描述为独立测试。

## 当前验证状态

- teacher TCN：训练进行中，暂未生成最终模型或 parity 输出。
- MATLAB/Python 批量 parity：脚本已准备且静态检查通过，执行待训练完成。
- Plant calls：TCN 训练启动后为 0。
- TEST：未读取。
- 资源偏离：错误残差标签的旧诊断训练与正式 teacher 训练并发使用 GPU，违反单 GPU 顺序约束。按现场保护要求不打断运行；旧诊断模型不得用于结论。正式训练结果审核时须保留此偏离记录。



## 2026-10-26：Amendment 05 发布门复核

复查发现旧冻结器只要求 parity 状态为 PASS 且误差小于报告自填 tolerance，因此旧单窗口报告可能满足门槛。现已在冻结器和评分器中强制要求 `verification_version=batch_v3`、48 个 VAL 场景的 240 窗口、固定索引 `[0,1,100,999,1998]`、1,999 步顺序运行、误差阈值不宽于 `1e-5`，并将 Amendment 05 与 parity 报告哈希纳入释放/评分核验。MATLAB R2025b `checkcode` 对两个文件均为 0 项。runner 源码树未改，v4 无 Plant 静态审计范围不变。

数值 parity 尚未执行：正式训练仅报告到 7,000/60,000 步，且还没有最终权重；pilot release 不存在、启动 marker 为 0。因此当前没有 TCN Plant 航次，TEST 仍封存。

### 06:25 训练状态更新

正式 v2 已推进到 8,000/60,000 步，当前最佳 step 为 8,000，VAL teacher-action RMSE 为 0.521359（此前 7,000 步为 0.535211）。PID 20056 和诊断 PID 23108 均仍存活；这只是离线模仿误差，尚无闭环 TCN 航次。PILOT_RELEASE_v2.json 不存在，attempt marker 为 0。

### 06:28 parity data-path复核

静态追踪 exporter→MATLAB verifier：Python 只读冻结 TRAIN/VAL 文件，以 TRAIN 统计量归一化，再导出全部 48 个 VAL 场景的五个固定窗口和首个非零变形命令场景的 1,999 个事件序列；MATLAB 分别比较批量前向与 runtime 历史缓冲输出，并核对模型和向量 SHA。该 parity 证明的是 TCN 原始角加速度动作一致性，不等价于闭环性能；固定 `J0 * beta * clip()` 接口另有合成权重 no-Plant smoke，误差在浮点舍入范围内。当前尚未生成正式 parity 数值结果，因为训练未完成。

### 06:32 process identity check

PowerShell 7 `Win32_Process` confirmed the live command lines, not just PID/state-file correlation: PID 20056 runs `train_tcn_teacher_v2.py` (the corrected formal run); PID 23108 runs `train_tcn_v1.py` (invalid residual-label diagnostic). Both use the expected Anaconda interpreter and remain responsive. No pilot release or attempt marker exists.

### 06:33 正式训练输入身份复核

重新计算 SHA-256 并交叉核对：live `train_tcn_teacher_v2.py` 与 `TRAINING_RELEASE_v3.json` 一致；训练 NPZ 同时匹配 `DATASET_MANIFEST_v2.json` 和正式训练进度文件；manifest 固定为 TRAIN 768 / VAL 48，`test_data_read=false`、`plant_truth_read=false`。当前正式作业仍使用任务书锁定的输入身份。

### 06:40 parity self-hash failure fixed; release source binding strengthened

The parity verifier passed the extensionless `mfilename('fullpath')` result to `sha256_file`, while the helper opens a literal path; MATLAB's release/scoring helpers correctly append `.m`. This would prevent writing the parity report after numeric comparison. The verifier now hashes `[mfilename('fullpath') '.m']`. The freeze helper also verifies the parity report's exporter/verifier SHA against live source files and records those plus its own SHA in the pilot release; the scorer independently checks all three. MATLAB R2025b Code Analyzer: freeze 0, scorer 0, parity verifier 0 diagnostics. Numeric parity remains gated on completion of the 60,000-step training.

### 训练指标量纲说明

`best_val_scene_macro_teacher_action_rmse` 来自 `validate(model, val_pad, val_t)`，其中 `val_t = val_y / target_rms`，而 `target_rms` 按 TRAIN 三轴分别计算。因此当前 0.521359 是无量纲、逐轴 TRAIN-RMS 归一化后的 scene-macro RMSE，不是 `rad/s^2`。最终报告需把它与按物理单位计算的逐轴误差分开呈现；不能直接把该标量乘一个平均尺度解释为物理 RMSE。

### 06:55 best-checkpoint 指标独立复算

对 best step 10,000 做了只读 CPU 重算（仅 VAL48，无 TEST/Plant）：归一化 scene-macro teacher-action RMSE 为 0.5188621803，与训练进度 0.5188621844 相差 `-4.1e-9`。以 `rad/s^2` 报告的逐轴 scene-macro teacher-action RMSE 为 roll 3.4638、pitch 3.7252、yaw 0.3100；pooled RMSE 为 3.8358、4.2965、0.4047。TRAIN target RMS 为 8.5138、8.5204、0.5159 `rad/s^2`。这些是对 B-RBF 动作的拟合误差，不是闭环姿态误差或控制性能。

### 07:25 step 12,000 best-checkpoint independent recalculation

The best checkpoint was independently evaluated on CPU using only the 48 VAL scenes (1,999 events each). Checkpoint SHA-256: 8562d55e7a300dbf758bbac81a9162022a8a7575d6e2ac8e43919c8de4c982eb. Recomputed normalized scene-macro teacher-action RMSE: 0.5132606913868659; training progress: 0.5132606907273783; difference: 6.59e-10. Physical-unit scene-macro RMSE by axis: roll 3.454498614, pitch 3.690248578, yaw 0.306722281 rad/s². Pooled physical-unit RMSE: roll 3.840817869, pitch 4.217893759, yaw 0.399053335 rad/s². TRAIN target RMS is unchanged at [8.513807707, 8.520418573, 0.515942422] rad/s². Checkpoint SHA was identical before and after evaluation. No TEST or Plant data were read, and no model/dataset files were written. These figures measure imitation of teacher RBF actions; they are not closed-loop attitude performance.

Reproduction command for future best checkpoints (PowerShell 7):

    & 'C:\ProgramData\anaconda3\python.exe' '.\experiments\dl_attitude_replacement_20261026\audit_tcn_teacher_checkpoint_val.py'

The read-only audit script verifies TRAINING_RELEASE and dataset manifest/NPZ identity, loads only TRAIN/VAL arrays, independently constructs causal windows, checks the checkpoint before/after hash, and compares its VAL48 metric with the progress record. It passed on step 12,000.

### 2026-10-26：pilot scorer failure-denominator audit

发现并修复 `matlab/score_tcn_ghp7_pilot_v2.m` 的统计风险：旧实现会对未完成轨迹计算局部 RMSE，并仅依据指标有限就计作配对胜场；不安全/失败场的指标也会进入候选及基线宏平均。这可能把短的部分轨迹算成有效胜利，并使均值的场景集合不一致。

修正后：

- 位置与 SO(3) 主指标只对完整时间线计算；不完整场景仍保留记录，但主指标为 NaN。
- 配对胜负只计 `SCORED_COMPLETE` 候选场。
- 候选与 B/C5_RBF/C5_10 均值使用同一组 `SCORED_COMPLETE` 场景。
- 汇总分别报告完整安全场、失败/不安全场、缺失/评分错误场，以及应用可行/不可行场；不改任务书门槛。

MATLAB R2025b `checkcode(...,'-id')` 对修改后的评分器无诊断，进程返回码为 0。未调用 Plant、未生成 pilot release，也未启动航次。当前评分器 SHA-256：`1F4AA332F738B216EE422112C7C9D9AA0B19D6FA869D5118CFEEFA6EEED126F7`。

