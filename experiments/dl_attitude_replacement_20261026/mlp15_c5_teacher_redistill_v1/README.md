# MLP15 匹配 B/C5 教师训练阶段

**状态：主模型已批准离线匹配数据集构建。** 发现旧 B 教师训练集有 768 条完整序列，而 C5 训练 split 只有 24 场；因此改为等量 B24/C5-24 对照。当前没有训练或闭环运行放行。

Luna 已确认 B72 对应 DEV24 可用于只读抽取：24 场 raw/status hashes 与 C5 lock 一致，姿态事件数、有限特征/标签、clip/beta 关系均通过。本阶段先构建 B24/C5-24 和共同 C5 VAL48 的独立 manifest/source lock；主模型审核通过后才启动两次匹配训练。动作蒸馏只直接优化 teacher-action RMSE，不能保证闭环姿态优于 C5。C5 72 场 raw/trace 已由主模型复核：360 个 raw/status/run_start/marker 哈希一致；原 60 条 status 保持待父审计，不回写历史账本；显式 beta 日志缺失，需在产物中披露。TEST48 保持封存。

> “位置相对 C5 只允许小幅退化”暂以宏平均位置 Q 退化不超过 10% 量化：`(Q_MLP15 - Q_C5) / Q_C5 <= 0.10`。此阈值由主模型暂定并冻结为本阶段验收门槛；它不是既有实验结论或理论阈值。

详细方案见 [MLP15_C5_TEACHER_REDISTILL_TASKBOOK_DRAFT_v1.md](MLP15_C5_TEACHER_REDISTILL_TASKBOOK_DRAFT_v1.md)。

