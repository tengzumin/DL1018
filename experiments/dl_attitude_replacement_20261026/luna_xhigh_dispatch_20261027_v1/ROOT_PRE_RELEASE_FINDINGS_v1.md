# root 实际入口与设计边界预审

2026-10-27。这是实现代理尚在运行时的源码快照预审，不把未交付的中间状态当最终失败；也不据此放行 Plant。待最终产物完成后按最终源码和SHA复核。

## 首要入口核对项

当前 `mlp15_composite_head_v1` 快照的无Plant报告列出改动为 `mlp15_attitude_step_v1.m` 与 `run_gate_holdout_closed_loop.m`。但前一实际DEV study 的执行入口 `causal_head_study.m` 调用 `run_mlp15_dev72_closed_loop`；当前新树中的这个DEV函数仍与v1逐字节相同，没有 `tracking_surface`、`tracking_euler_rate_map`、`actual_event_dt` 三项输入。

新step会强制要求这三项。故若最终driver继续调用DEV函数，将发生集成接口错误；300事件直接step数值检查不能证明实际runner已接通。若改用generic gate函数，则必须证明它接受同一DEV场景合同且物理数组/评分目标/基线完全匹配，不能悄悄切成GHP7。

首场真实Plant前必须明确：最终driver实际调用哪个函数、which解析路径、该函数如何传递合法当前T/s和真实事件间隔，以及与v1的完整输入身份。优先保持原DEV入口并在其事件处接通新字段；不因同目录存在两个相似函数就推定路径正确。此项若最终未解决，root不得放行。

## beta 与饱和边界

当前合成报告是80次残差更新、81次跟踪更新。实际源码对应：RLS仍要求上一和当前beta均为1；跟踪项只要求当前beta为1且存在前一事件间隔。因此跟踪项比RLS早一事件启动。

这可作为单一新增跟踪通道的明确实现选择：使用当前已知surface/T，不利用未成熟的过去残差标签，当前输出仍先于更新。若最终保持此选择，root在首航release里明确记录，不把两路描述成同一启动时刻。实际dt必须与相邻事件time_s之差一致，不能用1ms Plant dt冒充10ms事件间隔。

未屏蔽dmax饱和轴的tracking项只能作为受限离散系统中的实验更新律；不宣称该轴仍精确抵消Lyapunov交叉项。首航记录所有输出裁剪和权重投影，并按既有稳定/执行器/实际角度检查停发后续航次。对此只作理论边界披露，不在本项加入第二个anti-windup机制或参数搜索。

## 固定惯量来源核对

实际DEV源码要求formalRbfBaseline，并在循环前用初始名义臂长和零臂长速度构造fixedController；控制循环在此模式下使用该固定对象。`controller_parameters(...,'fixed')` 使用nominal_arm_lengths和零armRates计算名义常数，未从当前真实变形读取J或Jdot。

最终还需从锁定cfg/控制器对象数值验证 `P.inertia == J0`、`P.inertia_dot_for_bs == 0`，并确认实际BS使用此对象。固定初始名义模型不是时变惯量重建；Plant自身计算真实动力学所需的J/Jdot与部署控制输入应明确隔离。

## 当前决定

实现代理继续完成本来的无Plant准备；root仅审核和监督。还没有新的真实复合头航次获准，TEST保持未读。最终验收保持双环优于B、姿态优于C5、位置相对C5保留主要收益，不能用改善旧冻结MLP代替。
