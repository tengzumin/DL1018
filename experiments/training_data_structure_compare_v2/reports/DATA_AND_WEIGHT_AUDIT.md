# 数据与训练质量审计（零 Plant）

## 索引和缓存

- accepted TRAIN/VAL 记录与本轮复用的序列缓存清单逐 run_id 一一对应；accepted ID 唯一，TRAIN 与 VAL 没有共享 run 或 scene。
- TRAIN episode：B 768、POS_OFF 768、Student 384；共同 VAL：三类各 48。TRAIN 共 756,480 个 stride-5 就绪终点；每个终点仍来自原始100Hz序列，stride仅用于离线监督采样，不是部署更新率。
- 每条缓存均为1999事件、32事件 ready 边界；事件时间严格递增，Plant索引递增，X14/标签有限，`target_clip` 与 `clip(target_raw, -3, 3)` 闭合误差不超过4e-6 m/s²。32帧张量的部署 KAN 前向只使用最新帧，来源代码 `training/models.py`。
- accepted run_id 在 attempt_index 中均可唯一解析到最后一条 attempt 记录。append-only attempt 索引含重复 run_id 是重试记录，不会形成重复 accepted episode；训练打包按 episode_index 的 accepted 唯一 run 读取。

## 覆盖与质量权重

- Teacher 的每个 task×class 覆盖16个风格场景；Student 每个 task×class覆盖8个。每类在16个 C 配置均有记录；各角色与任务的采集覆盖见 `derived/EFFECTIVE_TRAINING_MASS_BY_STRATUM.csv`。
- 按当前正式权重函数重建：全局来源质量为 B 0.25、POS_OFF 0.25、Student 0.50；每个来源再将总质量平均分给三个任务，并在 task×class、scene、phase 与该 phase 的 endpoint 数上归一化。具体 config/wind/phase 汇总、单事件权重范围见同表及 `EFFECTIVE_TRAINING_MASS.csv`。
- 因同类 episode数为 Teacher 16、Student 8，且来源质量分别为0.25/0.50，Student 每场总权重是每个 Teacher 的4倍；这是明确的来源配方结果。新训练按均匀打乱 endpoint 抽样，在 loss 里乘一次冻结质量；不再叠加 WeightedRandomSampler，不双重加权。短/长 phase 总权重相等，phase内按 endpoint 平分。
- 每条 episode 内的 x14、target、event_time、phase、beta、ready、plant_index按同一 event index保存；训练窗口不会跨 episode 拼接，也不会将 VAL/DEV 作为 TRAIN。

## 有限近邻冲突探针

- 对每个 TRAIN run 固定随机抽8个 ready endpoint，只在同来源、同任务内寻找最近的跨 run 邻居；比较当前标准化X14与32事件真实历史（仅X14前10列）。本探针不用于选模。
- 当前X14最近5%跨 run 配对的X14距离阈值为 0.1404；逐来源/任务的样本数、距离和标签差分位数见 `derived/X14_HISTORY_COLLISION_SUMMARY.csv`，配对明细见 `X14_HISTORY_COLLISION_PROBE.csv`。
- 近邻标签差说明记录数据里存在状态相似但目标不同的关联样本；同 run 排除、只抽样、且该指标不是条件方差/可辨识性证明。历史向量相较当前帧的配对结果可显示它是否区分这些抽样邻居，但不能单独证明历史分支会改善闭环。

## 旧 DL1009 与本轮 DL1018 的协议差异

逐项和证据路径见 `OLD_NEW_PROTOCOL_DIFF.csv`。DL1009获胜包不是“同条件下一个浅KAN小数据fit”：旧研究有多架构筛选与后续分阶段训练/repair；其当前任务与 DL1018 三任务混合任务、数据来源比例、控制合同、Plant、选模协议均不同。旧包成绩可作历史参考，不能用单个权重包差异归因。本轮使用新数据、原始DL1018 Initial作同一起点，固定控制合同，只比较数据来源、容量、历史三项方案。

## 训练与验证口径

后续训练和共同 VAL 均报告物理 m/s² 的 RMSE/偏置、逐任务和逐来源值，使用同一标签、同一 clip 与同一固定 Head 目标；训练加权损失与物理 RMSE分开。VAL 是已有开发数据，不称blind test。Student 航次成绩较差不构成删样本理由。
