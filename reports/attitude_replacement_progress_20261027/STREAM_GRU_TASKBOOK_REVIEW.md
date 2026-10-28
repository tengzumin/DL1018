# GRU streaming 任务书独立复核

复核日期：2026-10-27。只读审阅任务书、既有 GRU15/full72 训练合同与回执、architecture screen 和 C5 RBF replay 证据；未读新实现目录，未启动训练/MATLAB/Plant，未读 TEST 或真实惯量。

## 结论

该候选**确实覆盖了既往 attitude screen 未覆盖的场内持续 hidden state**：每场 1,999 个按时序排列的事件，GRU hidden 从场首零初始化、跨 128-event chunk 携带，且只在 chunk 边界 detach；这样 forward state 可跨约 20 s，但反向梯度仅覆盖最近 128 个事件。它是检验 persistent-state 训练/推理策略的合理候选，不证明长记忆是闭环主因或必然改善。

结构动机也有限且成立：在未投影、后缀更新输入/学习 surface/dt 相同的条件下，RBF 两个权重状态的差分按 `(1−dt·sigma_w)^N` 缩小；C5 `dt=.01 s`、`sigma_w=[.11,.12,.20]` 时，15 次更新后差分仍保留约 `[.983626,.982150,.970416]`。这说明一般历史下短后缀可能不唯一决定 teacher 权重/输出，支持检查持久状态；它没有证明这些重复后缀存在于本数据、物理可达，或解释当前闭环失败。见 `ROOT_FINITE_WINDOW_MEMORY_NOTE_v1.md`。

## 合同核对

- **teacher、特征、目标合法且固定。** 同一旧 GRU15 的单层 GRU `(13,32)` 加线性 3 输出；输入仍为 wrapped attitude error×3、body rate×3、nominal BS torque×3、morph command×4；目标仍为 C5-RBF `rbf_output_raw`（post-DMAX/pre-beta，rad/s²）。排除 Jhat/Jdot、惯量/质量、Plant truth、RBF weights/hidden state、observer 和物理前馈。任务书只取 C5 TRAIN24 + VAL48_AS_DEV_TRAIN，TEST/B24 不用。
- **normalizer 复用符合固定要求。** 既有 GRU15 full72 训练配置记录 `normalizer_sha256=612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693`，与实际 `normalizer.npz` SHA 相同。任务书要求直接复用这份 mean/std/target_rms、不重拟合，方向正确；release/source lock 应把此确切 SHA 和模型 SHA 固化。
- **TBPTT 与 reset 规则足以表达持续状态。** 每个 1,999-event scene 分为 15 个完整 128-event chunk 和最后 79 个有效事件；batch 4 条 scene 流，场内携带 hidden、chunk 边界 detach、每场首事件 reset 0，不跨场串 hidden。若尾部 pad 到 128，loss 只含 79 个有效事件且最终 hidden 丢弃。TBPTT 梯度长度不是 20 s，但 forward state 可以跨全场，这两点任务书区分正确。
- **训练预算/发布规则清楚。** 固定 seed `2026102001`、fresh init、60,000 optimizer steps、Adam `1e-3/1e-5`、SmoothL1 beta 1、final-60000 唯一发布、无 checkpoint/seed 搜索；release0 阶段明确禁止训练，须 root 另行签发唯一授权。旧 GRU15 也是 15-window、60,000 steps，但每步从随机场/event 抽 512 个独立窗口（见其 trainer），不是流式序列更新。
- **验证项合理。** 任务书要求逐事件 Python/MATLAB parity、逐点 carry 与整序列一致、reset 可复现、未来扰动不改过去、padding 不影响有效前缀、normalizer/shape/source/which 校验。实现/receipt 还应记录每步 cohort 的 scene IDs/排列、chunk 起止、有效样本数、loss mask 分母、hidden reset/detach、尾部 padding 和累计样本账本；目前任务书要求有效数累计记录，但未把完整的 epoch/permutation 与每步 loss 分母格式完全定死。建议在训练 release 前固化这些字段。

## 解释边界和既有 GRU 比较

这**不是严格单变量的“只改 memory”因果 A/B**。候选固定网络结构、teacher、normalizer、优化器和 step 数，但同时改变了输入组织/采样顺序、batch 组成、state carry 与 TBPTT 梯度跨度；它比较的是 streaming 训练/推理协议这一整体策略。任务书已明确“不定根因”、不把 GRU 胜负说成 memory 因果，边界合适；后续只能据此判断该策略是否值得，而不能归因于 hidden 持久化单项。

旧 GRU15 full72 闭环结果应作为先验列出：GHP7 六场报告中宏平均 `Q=14.288 mm`、SO(3) `72.361 mrad`，均比 C5 差，final gates 未过。该结果与新任务使用相同 C5 teacher/full72 GRU15 权重家族，但场景是 GHP7 G1/G2/G3 × W00/W12，不是当前 C5 六场；不是同场配对记忆对照。现有 `pilot_runs_gru15_c5_full72_v1` 也是这六个 GHP7 scene。任务书第 33 行提出需要因果区分时先查同场窗口 GRU15、缺失再单独授权，是正确处理；不应跳过这项既有负结果，也不应把它当新 streaming 的反事实。

## 最小补充建议

允许继续 release0 trainer/no-Plant 准备，**不允许据本审阅启动训练**。训练前在锁/receipt 中固定 normalizer SHA、初始化权重 SHA、每步序列采样账本和 masked-loss 分母；明确报告这是“persistent-state sequence protocol”候选。若后续要证明 memory 单项作用，需 root 单独授权同场 GRU15-window 对照；当前任务书不应作这种强因果结论。

## 关键源码与记录

- 新任务书：`experiments/dl_attitude_replacement_20261026/luna_xhigh_dispatch_20261027_v1/ROOT_STREAMING_GRU_TASKBOOK_v1.md:7-35`。
- 有限窗口结构动机：`experiments/dl_attitude_replacement_20261026/luna_xhigh_dispatch_20261027_v1/ROOT_FINITE_WINDOW_MEMORY_NOTE_v1.md`。
- Attitude GRU15 定义与零初态调用：`architecture_screen_v1/screen_attitude_architectures_v1.py:65-73`；同脚本 DSSM 每窗口零 state：`:85-92`。
- 旧 GRU15 输入/label/window/seed/预算、随机窗口训练：`gru15_c5_teacher_full72_v1/train_gru15_c5_full72_v1.py:34-45,320-352,369-378`；旧 normalizer 计算与导出：`:222-228,301-303,414-442`。
- 有序 C5 数据与事件合同：`mlp15_c5_teacher_redistill_v1/build_matched_teacher_dataset_v1.py:38-41,277-303,528-559,590-595`。
- 旧 GRU15 full72 实际训练配置/normalizer：`gru15_c5_teacher_full72_v1/runs/C5_GRU15_FULL72_SEED2026102001/{training_config.json,normalizer.npz,run_receipt.json}`。
- 旧 GRU15 GHP7 六场结果：`gru15_c5_teacher_full72_v1/ROOT_REVIEW_GRU15_GHP7_SIX_SCENE_v1.md:3-20`。

