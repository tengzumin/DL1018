# A2 任务书非作者只读审查

审查范围：`reports/attitude_cm18_a1_20261024/A2_YAW_INVARIANCE_TASKBOOK_v1_ZH.md`（SHA256 `f8ab1e51aad38d3b070c5c4f39a4b4986d391ac42dadfb9ea9b4706a83b6d652`）和 `A2_PREREGISTERED_CONTINUATION_GATES_v1_ZH.md`（SHA256 `9efdf7763b9ba6e896bb0e970e065dd70574c6814fa38ff92f65e221a64abb56`）。本审查只读，无源码、数据或结果改动，也未运行实验。

## 审查结论

当前修订已处理先前提出的关键歧义，没有阻断训练准备的新增逻辑问题。继续门现在给出 physical vector RMSE 与 pooled yaw RMSE 的明确聚合公式，并增加每场位置 Q 不超过 A1 的 1.10 倍；标签边界也限定为仅改变参考角加速度、固定参考角/角速度及其他状态和历史，且说明 beta 与逐轴 clip 已包含在 `c_old` 中。文档明确把归因对象定为共享双视图训练/推理处理包，而非独立 yaw 头效应。

## 仍须遵守的适用边界

物理零偏导是固定状态、形态、推力、风、参考角和角速度，仅改变参考角加速度的局部条件命题。当前 `attitude_bs_step` 将姿态误差/滑模面与参考加速度分开；旧 RBF 的输入由误差和滑模面组成，因此在其权重及历史固定时，该反事实不改变旧动作。事件时刻固定时，beta 和逐轴 dmax 裁剪也不引入依赖。只有再满足同一无分配裁剪线性域，行为标签的偏航条件偏导才可继承为零。此结论不代表真实轨迹中的统计独立性，也不保证训练标签处处满足该先验。

双前向共享参数与联合三轴损失会共同改变整个模型。前向单元检查能证明所用 yaw 输出对被屏蔽输入严格不变，不能把闭环差异单独归因于某个独立 yaw 子网。100 Hz 事件频率与 A1 对齐，但双前向的 wall-clock 延迟及 10 ms 实时截止尚未验证；继续门已把公平运行耗时列为后续审核。

已有事后 mask 的负面证据在任务书中披露，包括 T3_C05_W02 偏航误差反例、三轴整体退化，以及 A1 固定 12 场仅 7 场姿态胜出。继续门明确为研发筛查，不是论文验收或闭环稳定性证明。任何训练或闭环放行仍应遵循任务书所列 Root 审核与独立复算步骤。

## 额外八场离线批次资源记录

直接 MATLAB batch 调用已返回进程 `exit_code=0`。未发现对应的独立 OS receipt JSON 文件，因此不提供虚构的回执路径。数值结果保存在 `reports/attitude_cm18_a1_20261024/refresh_interval_v1/ROOT_YAW_ALPHA_MASK_REMAINING_EIGHT_v1.json`（SHA256 `0a5538159534e8808420aa6c71405e7b6bc60d0e728d9d218d6e25402b5b150f`）；文件记录 8 个场景，每个场景均为 `plant_calls=0`、`engine_calls=0`、`episode_steps=0`、`state_integrated=false`、`optimizer_steps=0`、`training=false`、`TEST_accessed=false`。该 JSON 的实际根结构是 8 个 report 组成的数组，每个 report 内的 `scenes` 是单场。
