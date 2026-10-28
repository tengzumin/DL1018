# MLP15 姿态替代候选：闭环筛查任务书 v2

日期：2026-10-26。v2 保留 MLP15 的训练权重、输入、场景集合、配对基线、评分规则和六次闭环预算；只修复 v1 runner 的场景白名单匹配实现。

## v1 启动故障记录

v1 在 DL1018_GHP7_G1_W00 上执行到场景白名单绑定时，用 MATLAB 短路运算符 && 组合六项逻辑数组，触发非标量逻辑错误。该错误发生在 attempt marker、run_start、Plant 和 raw 写入之前。失败记录保存在 pilot_runs_mlp15_v1/MLP15_RELEASE_V1_PREFLIGHT_FAILURE_01.json；Plant 航次消耗为 0。v1 release 与源码锁保留原样，v2 使用独立 runner、任务书、源码锁和 release。

## 候选与配对筛选

- 候选仍为冻结 59,000 步权重的 DL_MLP15；位置环沿用锁定的 C5 DSSM14，BS 姿态名义环、Plant、allocator 和执行器不变。
- 姿态 RBF 输出/更新、惯量重建、observer 和物理前馈均关闭。DL_MLP15 是冻结监督网络，无在线权重更新。
- 只运行原 GHP7 六场 ACTIVE 场景：G1/G2/G3 × W00/W12。复用同 payload、同 R_task 的 B 与 C5_RBF raw；C5_10 仅作诊断参照。
- 最多新增 6 个 Plant 航次。六场必须完整结束、STABLE、无安全停止、饱和、通用裁剪或倾角限制；候选相对 B 的六场宏平均位置 Q 与 SO(3) RMSE 均须严格改善，才晋升 DEV72。逐场、W00/W12 分组、安全与应用可行性都报告。六场只是方向/安全筛查，不作为论文统计结论。
- TEST48 保持封存，不读取、不运行。

## v2 实现与释放门

- 唯一源代码改动：v2 runner 的 allowlist 采用逐元素 & 组合四个字段的比较结果，再用 find 取唯一命中；其余 runner 源码复制自 MLP15 v1。
- 候选源位于 pilot_runner_mlp15_v2/candidate_runner_work；新运行与评分输出分别位于 pilot_runs_mlp15_v2 和 pilot_score_mlp15_v2。
- 启动前完成 MATLAB Code Analyzer、无 Plant 的场景准备/白名单匹配、候选单步检查、C5/B 输入身份及完整源码哈希核对。
- 每场启动前检查没有其他 MATLAB/Plant 实验进程；失败航次若已写 attempt marker 仍计入六次预算并保留。v1 的无 marker 前置失败不计入 v2 Plant 航次。
- 不覆盖或删除 v1 release、源码锁、训练、模型、基线、缓存或历史 raw。