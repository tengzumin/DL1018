# 姿态替代研究阶段状态

更新时间：2026-10-25（本机时间）。

## 当前阶段

- DEV72 candidate 对同场锁定 B72 的完整独立复算已完成，开发门通过。详见 `review/ROOT_DEV72_REVIEW_AND_NEXT_STEP_20261025_ZH.md` 和 `review/DEV72_INDEPENDENT_RESCORE_v3.json/.csv`。
- A02 完成 58 个 candidate-only Plant 航次、1,160,000 transitions；0 未知调用、0 训练、`TEST_accessed=false`，58 场均完整并通过安全门。B72 与另外 14 个 candidate raw 均复用。没有重跑 B/C5。
- 72 场宏平均：位置 Q 10.553 mm vs B 17.058 mm，改善 38.13%；姿态 SO(3) 9.804 mrad vs B 16.338 mrad，改善 39.99%。位置与姿态各 69 胜/0 平/3 负；高频 W09–W14 与无风 W15 两组位置、姿态均值都优于 B。候选 raw 全部稳定，无 safety stop、饱和、clip 或 tilt limit。
- Candidate 为 C5 DSSM14/M110 位置栈（冻结 encoder/normalizer/W0、位置 head 按原算法在线更新）加解析惯量前馈/有界姿态 disturbance observer；姿态 RBF 输出与更新关闭。此处对 B 的结果是系统级比较，不应单独归因姿态环。
- V3 报告补齐 XYZ 宏平均、早晚段、P95、W00–W15 全风组、控制调用耗时和逐场原始数据。对 72 个 candidate raw 的 `rho_true` 核验显示，66/66 命令变形场确有臂长变化，6/6 固定场无变化（0 个标签不匹配）。实际主动变形组的姿态 SO(3) 均值低于 B 7.131 mrad；固定几何组 `n=6`，均值略高于 B 0.033 mrad。分组仅为描述性系统级结果，不识别形态变化的因果效果。P95 为描述性补充，没有新增验收门。

## 历史记录与风险

- A01 保留原样；因 runner 自身 SHA 从错误位置读取，在首场 invocation marker 前失败，0 Plant/0 transitions。修复后使用独立 V2 frozen source lock 与 A02 release。
- T2 既有复用 candidate 的 `run_status` 仍为 `FAILED_ENGINEERING`。保持标签不改；raw 为 STABLE，既有独立 trace review 将标签归因旧 shape checker 误报。DEV72 汇总保留历史 gate-failed 计数。
- 4 个不同场景有至少一项误差轻微退化；位置最大 +0.841 mm，姿态最大 +0.186 mrad，全部无安全异常。定位结果见根审查报告，不针对 DEV 输场调参。
- 旧 `experiments/c5_test48_v9` 已有多方法 TEST 实际航次 marker，旧方法清单不含当前 physics/inertia attitude candidate；旧 release/manifest 的状态标志还有矛盾。未读取其 raw 或性能指标，不将其作为当前 candidate 的独立 TEST。

## 下一步

- 当前已完成只读源码与机制审查，没有发现当前冻结 v2 candidate 的符号接线、因果输入或共同 Plant 源码 blocker；此审查不构成闭环稳定性证明或新航次放行。当前没有可见 MATLAB/Octave 实验进程；DEV72 后没有新增 Plant 航次。
- 论文还缺两类识别：B 对比是位置/姿态一起改变的系统级结果；标准三条轨迹没有障碍/碰撞模型，不能证明主动形变有任务净空收益。下一阶段改为独立 gate-inspection 应用任务，并增加同 C5 位置栈+原姿态 RBF 对照、candidate 的 feedforward×observer 消融、固定安全短形态配对与固定宽形态几何核验。
- 先完成 no-Plant 轨迹、scene 身份和完整机体扫掠包络审核；Plant 本身没有接触响应，所以 gate clearance 只能按模型几何后处理报告。之后再写新 scene/source lock、评分统计门和一次性任务书。所有这些通过 root 审核前不启动新航次，不访问旧 TEST raw/成绩，也不训练或调参。
- 当前详细草案在 `../../holdout_gate_inspection_v1/GATE_INSPECTION_HOLDOUT_TASKBOOK_v1_DRAFT_ZH.md`：3 种往返检视 profile × W00–W15；B、C5+RBF、feedforward×observer 2×2，以及两种固定臂长比较，共拟 384 个正式航次，另 48 个 pilot 航次。任务书仍为草案，未放行。
- 只用 PowerShell 7 启动实验；不打断已有作业；不删除历史 raw、模型、cache 或 ledger；保留 A01/A02 与旧 TEST 原位。
