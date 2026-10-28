# Streaming GRU trainer source review (snapshot)

**结论：** 静态源码与任务书的主要约束一致，当前没有发现会把短窗口训练误当持续状态、越过单次训练门、或读入禁用数据的实质性阻断。此结论只针对下列快照；未运行自检、训练、MATLAB 或 Plant。release0 仍是待主审状态，当前不授权训练。

## 审核快照与锁

- Trainer: `experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/train_gru_stream_c5_teacher_v1.py`，SHA-256 `ee65081287515b8c9bccf3a4cbcb27935c83c878d51b999a7b5602fc28c48b69`，文件时间 2026-10-26 20:22:03 UTC。
- Source lock: `experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/GRU_STREAM_C5_TEACHER_SOURCE_LOCK_v1.json`，SHA-256 `eed174fe8a5e3f8a5765a07f8a56b8d74f0b0ab3fdc2e72cc080a7c55cb8a207`。
- 文件 `experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/GRU_STREAM_C5_TEACHER_TRAINING_RELEASE0_v1.json` 中的 source-lock SHA 与该锁文件相符，状态 `RELEASE0_PENDING_ROOT_REVIEW`，`approved=false`、`authorized_jobs=0`、`formal_optimizer_steps_started=0`。
- 只读比较了 lock 中的 trainer、self-check、taskbook、原架构源码 SHA；四项均与当前文件匹配。运行入口会逐项复核 source hashes 与 dataset/manifest/normalizer 引用 SHA（源码第 123–168 行）。

## 具体核查

- **数据范围合法。** 源码第 178–230 行核验 C5 manifest、TRAIN_C5_24 与 C5_VAL48 各自数量/顺序及每场 1,999 个事件；第 233–262 行只索引 NPZ 的 6 个 C5 member，检查内容 hash 后拼成有序 72 场。标签契约锁定为 `rbf_output_raw`、post-DMAX/pre-beta（第 52、181–189 行），feature whitelist 为 13 维且排除惯量估计、RBF 状态、observer 等输入（第 44–50、112–120 行）。manifest 的禁用数据标记和数据读取范围也会被验证；代码未访问 TEST 或 B24 值。
- **复用原 normalizer。** 锁记录原 GRU15 full72 normalizer 文件 SHA `612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693` 及三个数组 SHA；运行前核对源文件与数组（第 265–279 行）。训练直接用这三组源统计量归一化输入/标签（第 599–600 行），并用 `copy2` 导出副本（第 636 行）。轻微封账建议：复制后在首次 optimizer step 前显式断言输出副本 SHA 等于锁定源 SHA；当前 receipt 会记录副本 SHA（第 778–796 行），但脚本未当场比较相等。
- **确为流式 GRU。** 实现复用原 `GRU15`（`experiments/dl_attitude_replacement_20261026/architecture_screen_v1/screen_attitude_architectures_v1.py`:65–73），其结构是单层 PyTorch `nn.GRU(13,32,batch_first=True)+Linear(32,3)`。包装函数把显式 `hidden` 传进 `model.gru` 并返回 `next_hidden`（trainer 第 282–296 行），不是原来默认每个窗口从零状态开始的 GRU15 `forward`。PyTorch 门序按 reset/update/new 写入锁（第 415 行）。
- **carry、detach、reset 与尾块。** 每个4场 cohort 以 `hidden=None` 开始（第 657–663 行），按事件顺序取每个 128 长度块（第 663–669 行），每次更新后 carry `next_hidden.detach()`（第 676–678 行），cohort 结束清零（第 713 行）。1999 = 15×128+79，最后一块只取79条有效事件，没有 padding（第 667–673 行）；self-check 静态定义也锁定 `[128]*15+[79]`、7,996 events/cohort、无 optimizer step 的检查（第 456–536 行）。每一步 SmoothL1 作用于实际 `[4, valid, 3]` 输出，逐步 JSONL 记录 valid 数、累计数、padding=0、cohort scene IDs 与 chunk 起止（第 680–712 行）。60,000步预算帐本为 29,985,000 次有效 event exposure；训练到预算后要求步数及累计数都与 schedule 重算值完全相等（第 729–732 行）。
- **一次性 60k 门与初始权重身份。** release 检查要求 lock 和 release 双方均已批准、单个 job，并且 release 指向当前 lock SHA（第 100–109 行）；入口在读取训练数据和建 optimizer 前做检查（第 577–598 行），已存在输出目录会拒绝重新启动（第 579–580 行）。source lock 保存 seed=2026102001 的初始 state_dict 和逐参数 SHA；prepare 时 CPU 构造并记录（第 354–358、404–408 行），train 时重播 seed 并在构建 Adam 前复验（第 590–598 行）。
- **最终导出。** 预算完成后只保存 step 60000 checkpoint（第 729–740 行）、MAT 权重/normalizer/parity fixture（第 741–762 行）、配置/每步历史/progress/receipt SHA（第 764–800 行）；无验证集 checkpoint 选择、续训或扩展（source lock 第 425 行）。这一点与任务书一致，但仍需主审单独授权正式训练，且数值部署验证不由此脚本证明。

## 当前需要主审知道的限制

1. 任务书本身说明 72 场由 TRAIN_C5_24 与 C5_VAL48_AS_DEV_TRAIN 组成；它们全用于拟合/复用 normalizer，不是独立验证集（任务书第 13、17、21 行；trainer 第 392–403、600 行）。因此即使 60k 训练成功，也不能表述为独立泛化验证。
2. 自检文件入口已存在且 source-lock SHA 匹配；本次是源码静态审阅，未执行其中 CPU toy checks，也未证明当前运行环境版本符合锁。
3. 建议的单一微小增强是输出 normalizer 复制后立即比较源/副本 SHA；除此外未发现此源码快照的高优先级实现缺陷。


