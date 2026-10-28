# C5 姿态替换分支对照审查

**结论：** 代码与冻结审计支持“同一 C5 位置/Plant 名义栈上替换姿态补偿模块”；未发现候选改写名义反步力矩、滤波或分配路径的迹象。但它不是只换网络权重：CM18 与在线 RBF 的输入、学习/更新机制及可能的输出延迟均不同。旧 C5+RBF 航次的实际运行源码身份未被现有逐场审计与锁清单直接联结，因此不能称为已严格证明的单因素对比，也不能据此单独归因性能差。

## 对比对象与共同栈

任务书 v2 第 9–11 行说明，`C5_24` 是冻结的历史候选；本次 15 场主比较是 `C5_COVERAGE33 + CM18` 对同场景 `C5 + 在线 RBF`，不是 C5_24 与 C5_COVERAGE33 两个模型的直接比较。候选入口 [run_c5_coverage33_scene_v1.m](../../../experiments/attitude_cm18_c524_coverage33_20261025/run_c5_coverage33_scene_v1.m:121) 将三个 RBF flag 显式置 false 并注入冻结 CM18 模型。逐场审核 [audit_c5_coverage33_scene_v1.m](../../../experiments/attitude_cm18_c524_coverage33_20261025/audit_c5_coverage33_scene_v1.m:199) 检查场景身份、C5 `cfg/opts`；移除候选专属字段和 RBF flag 差异后，断言其余选项完全相等（第 208–224 行）。因此滤波、位置栈配置、Plant 场景载荷与名义参数有同栈证据；两条闭环的实际状态轨迹会因补偿输出不同而自然分叉。

C5 输入锁 `C5_DEV72_INPUT_LOCK_v3.json` 绑定了 `run_dl1018_closed_loop.m`（SHA-256 `48350037…48a963c`）、`attitude_bs_step.m`（`cf6b20ff…fdaccbc`）、`command_filter_step.m`（`15c7eb27…d0d262b`）和 `allocate_control.m`（`5ac26d8c…27f3d53`）。候选入口另由 binding v3 固定；其 runner、CM18 engine 和 forward helper 的 SHA-256 分别为 `a16e561b…cb44cf9`、`4f72db75…ba1092a`、`1ff450f9…40f42e9`。候选 runner 第 140–157 行按锁定路径解析依赖。

## 两个补偿分支

冻结 C5 engine 的在线 RBF 更新块（`run_dl1018_closed_loop.m:2291–2330`）与 CM18 engine 中对应的 RBF 块（`run_cm18_closed_loop_v1.m:2473–2512`）逐行去缩进对照一致。CM18 新分支在该位置加入：X18 状态与动作历史输入（候选 engine 第 2425–2437 行）、冻结模型前向推理、角加速度限幅、beta ramp 和 `J0` 映射（第 2440–2468 行）。它运行时不更新 RBF；15 场审计确认 CM18 事件 1,999 次且 RBF 输出/更新全零。基线每场记录 1,999 次 RBF 更新；审计证明的是更新计数，不是逐事件时刻完全相同。

RBF 输入由 `attitude_input(ai0)` 构成 error/surface 交错的 6 维即时量（engine 第 2475–2500、3617 行），随后在线以 surface 更新权重。CM18 使用 18 维量，含机体系角速度、名义角加速度、推力/质量、当前命令、命令积分及前 10 个已完成请求力矩的均值。故替换的是整套姿态补偿模块（特征、离线训练与在线自适应），不是保持 RBF 输入和更新律不变的近似器替换。

两个分支最终都把补偿量交给同一个 `attitude_bs_step(state, ir, dT, P)`，再组成 `[thrust; moments]` 并走 `allocate_control`（candidate engine 第 2709–2726 行）。`attitude_bs_step.m:39–42` 明确执行 `nominalMoment - estimateTorque`；滤波调用在 candidate engine 第 2376–2381 行。候选要求 1 ms Plant 时钟、100 Hz 双任务时钟且首事件 10 ms（第 709–736 行）；官方审计逐行验证候选事件索引 `11:10:n`（audit 第 246–251 行）。RBF 路径支持 0/1 个事件的可选输出延迟（engine 第 987–990、2504–2512 行），CM18 当前事件直接应用（第 2461–2468 行）；已发布结果没有展示该选项的具体冻结值或 baseline 逐事件时刻，不能从摘要排除两者的有效延迟差。

## 来源缺口与决定

C5 baseline 的运行 marker 为 `2026-10-23T08:06:18.447Z`；其 run status 绑定的 input-lock SHA 与锁文件一致，锁记录了上述 runtime-core SHA。Git 中该 runtime-core 文件是在当日 `16:45:18+08:00` 才首次加入提交；这个提交晚于航次，不能单独作为运行当时的版本证明。更关键的是，当前 C5_COVERAGE33 审计虽核验 snapshot source identity 对应锁（audit 第 191–195、378–405 行），却只比较旧 C5 `runStart` 的配置、选项和场景身份（第 199–207 行），未把旧 runStart 的 `source_paths/source_sha256` 与锁逐项相连。按本审查范围不打开 MAT；因此旧航次的实际 engine hash 仍未由现有逐场审计直接闭合。

**执行决定：** 当前足以认为名义控制/Plant 栈按设计对齐，不能把候选差结果解释成已发现控制器代码错配；同时也不应把它写成严格单因素因果结论。若需要严格证明，应以同一冻结源码与有效延迟配置成对重跑 RBF/CM18，并将两边实际解析的 engine、共有控制函数和选项哈希写入可审核文本身份记录。现有历史结果保留，不解封 TEST。

本审查只读代码、任务书和既有 JSON/标记审计材料；未读取 raw/MAT/TEST，也未运行 Plant、仿真或训练。

