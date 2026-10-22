# W15 源码与早期控制分叉补充审计

日期：2026-10-22。范围仅为 R3 冻结任务书及隔离 runner、`position_only_search_options`、`controller_options_dl1018`、`position_bs_step` 的只读源码核对；没有读取 MAT、CSV、运行日志或 TEST，没有运行 MATLAB、仿真、训练或预检，也没有修改代码。

## 审核结论

**R3 的 Head/mask 不可能直接造成 0.020 s 的首个 B—候选请求差异，因为该差异早于 Head readiness；但源码不能证明两次实际运行满足足以推出控制链相同的全部前提。当前没有证据将该早期分叉归因到某一实现错误。**

## 控制链核对

- R3 的 `run_episode_dl1018` 将执行路径固定到本地隔离 runtime，并以 `B2-RBF-Full-SPLIT` 进入公共闭环。候选选项由 `P_A` 构造：位置 RBF 输出和更新关闭，Stage-1 DSSM Head 开启；姿态 RBF 设置仍继承默认值。源码因此确认位置侧的隔离意图，但不能单靠源码确认历史 B 航次的实际姿态力矩路径与候选完全相同。
- 候选 `stage1PositionHeldForce` 初值为零；只有位置历史事件数达到 `readiness_events` 才调用 Head 预测/更新，否则 held force 仍设为零。该 readiness 默认取模型 context length，缺省为 32。每个控制步再将该力传给 `position_bs_step`。报告中的 0.320 s 首个有效更新坐标差异与 100 Hz × 32 个事件相符，Head 输出差异记录在 0.330 s；源码静态值本身不能证明实际航次传入的 readiness 配置。
- `B2-BS` 不进入 Full/SPLIT 位置 RBF 输出调度分支；在没有额外位置补偿的正式配置下，其位置残差力也为零。因此，当完整状态、参考（含速度、加速度、偏航）、固定 `P`、位置残差力、命令滤波状态与参数、姿态力矩路径及执行器设置逐步相同时，二者经 `position_bs_step` 计算的名义/命令力和后续确定性命令应相同。
- `position_bs_step` 的名义加速度由参考与位置/速度状态构成，命令力为 `nominalForce - residualForce`。因此“位置侧 dF 为零”只证明这一环节的条件等价；姿态 RBF/融合力矩、初始滤波状态、真实 Plant/执行器状态或 runtime 版本不匹配，仍可使最终请求分叉。

## 对 W15 证据的解释

既有 W15 诊断记载 B 与 R3 首个请求差异在 0.020 s、状态差异在 0.021 s，而首个有效更新坐标差异在 0.320 s、Head 输出差异在 0.330 s。由时间先后只能排除 Head/mask 是**首个请求差异的直接原因**，不能排除它影响后续闭环，也不能由这条跨轨迹比较确定别的根因。待核条件包括运行身份与源码版本、全状态和完整参考、有效控制/Plant 参数、滤波器初值，以及实际姿态力矩路径。

下一次获准的诊断应先做离线同状态重放，按“位置名义力与补偿 → 姿态/推力目标 → 命令滤波请求与输出 → 姿态力矩 → 请求广义量与分配/电机”顺序逐级定位首个差异；在这条重放能由既有字段无歧义复建之前，不签发新航次。当前三轮筛查额度已用尽，TEST48 继续封存。

## 审计范围说明

本审计只依赖源码和任务书。另一次 W15 早期命令子审计在尝试路径/身份核对时，对 9 个候选实验 MAT 和 3 个 B MAT 做过 SHA-only 读取，其中包含 R1/R2 的 PCF-off 或身份未确认文件；它未读取变量或信号，未使用这些哈希作科学判断，随后停止。该动作超出了其严格限定的 W15 范围，故不把它作为数据审计或独立验证证据。没有数据被修改或运行被触碰。模型档位与工具未暴露的速度档位无法核验。

## 源码定位

- `experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_episode_dl1018.m`：隔离 runtime 解析与候选方法 dispatch。
- `experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m`：RBF-SPLIT 模式、readiness、held force、Head 和公共位置/姿态控制路径。
- `experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_only_search_options.m` 与 `matlab/runtime/controller_options_dl1018.m`：候选基线选项及禁用位置 RBF 的配置。
- `matlab/core/position_bs_step.m`：位置反步命令力方程。
