# 首场离线误差分解审核与后续范围

2026-10-25，Root。固定首场 `DL1018_DEV_T1_C01_W15` 的离线任务 attempt04 已以 OS exit 0 完成；session 32848 终态。前三次入口失败分别为任务书 SHA 抄写、JSON 数值列表行列比较、MATLAB 子数组赋值不广播；原源和日志均保留。没有新 Plant、训练或 TEST。

## 核验结果

- 实际记录 20,000 transitions；模型事件 1,999；非事件保持比较 17,991。
- 事件 X18 最大重建差 `2.22e-16`，模型输出差 `1.24e-14`；held/beta/requested/realized 的重建差均为零。
- `E0-G*Cstar` 最大差 `3.55e-15`；Root 独立 Python 逐事件复算矩阵、目标、fit/clip 代数，最大差 `3.77e-15`。
- 全时段事件物理残差向量 RMS `0.268901 rad/s²`；此场 raw 输出无 clip，fit/clip 交叉项为零，完整 allocator 与线性残差差在数值舍入范围。可行投影 oracle 的真实 allocator 残差约 `4.04e-14 rad/s²`。
- 非事件 fresh-minus-held 角加速度差向量 RMS `0.054515 rad/s²`；其完整 allocator 差与 `-G*(fresh-held)` 也闭合。这个量仅表示动作差，不能据此断言刷新将改善闭环或将它与事件残差 RMS 直接相加。

## 决定

首场工程与计算闭合通过。只放行准备剩余十一场的同一离线计算入口，不放行新训练、控制器修改、Plant 或 TEST。保留首场输出，不重复运行。剩余入口须经过 Root 的身份适配 diff 审核，来源与逐场完成状态继续严格绑定。

尚不能从无风改善场推广到高频退化场；不作全十二场主导机制结论。统一聚合须覆盖所有场景，以等场景权重报告 task、HF、W15 和 task/category，保留 MSE 交叉项、可行投影的线性 surrogate 界及 allocator flags。

依据：`a1t_screen12_control_v1/ROOT_FIRST_DECOMPOSITION_EVENT_AUDIT_v1.json`、`ROOT_DECOMPOSITION_FIRST_EXECUTION_RELEASE_v4.json` 与该场 `A1T_SAME_STATE_DECOMPOSITION_*_v1.json`。独立审核只能支持记录内算术与身份闭合，不等价于外部物理标定或闭环因果证明。
