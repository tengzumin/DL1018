# PCF 目标变换的解释边界（主审）

2026-10-22。以下是用于解释离线诊断的恒等式，不是稳定性验收证明，也不放行新训练。

令 e=r−p，s=de+K1 e，名义加速度 a0=rAcc+K1 de+e+K2 s。实际应用补偿 u 后 a_req=a0−u；定义 Y=a_actual−a_req。因此在连续理想模型下：

```text
dot e = s−K1 e
dot s = −e−K2 s+u−Y
dot eta = −K2 eta+r_f
sc = s−M eta
dot sc = −e−K2 sc+u−(Y+M r_f)
```

最后一式要求固定 M 与 K2 可交换；本诊断采用两者均对角的情形，M=diag(1,1,0)。这说明 Y+M r_f 是 sc 坐标的自然匹配项，但不能据此认定旧 Y 标签是实现错误。

仍有两个关键限制：

1. 实际位置误差满足 dot e=sc+M eta−K1 e。即使在理想条件下 u 完全匹配新目标，eta 仍进入位置误差动力学；不能把 sc 的残差变小直接等同于位置 RMSE 变小。
2. r_f=a_req−a_f，其中 a_req 和 a_f 都依赖策略与滤波历史。Teacher B/POS_OFF 上精确重建的影子目标，不是候选 PCF-on 闭环中的同分布外扰。X14 未显式包含滤波状态，代数上存在的目标也未必能由现有输入唯一辨识。

部署 helper 对每个 1 ms Plant 步使用

```text
eta_next = exp(−K2 h) eta + integral_0^h exp(−K2 tau) d tau * r_f(k)
```

它对分段恒定 r_f 的辅助系统是精确更新；实际 r_f 在步内变化、物理积分误差、100 Hz 权重更新、输出保持、beta、输出限幅、surface 限幅、泄漏与投影仍需分别处理。不能把这个 eta 更新式扩写成整个闭环的精确离散稳定性证明。R3 源码在事件上使用当前 eta 的 M 掩码构造 sc，再输出补偿并更新权重；同一步后段才推进 eta。

因此本轮使用相同状态、相同固定 W0 对两目标做 prior/zero 比较。必须同时报告目标本身 RMS、先验误差、偏置、低频及分组，不能只凭新目标绝对误差较小支持目标变换，更不能由零预测离线优于先验推出零补偿闭环优于 B。

源码依据：matlab/core/position_bs_step.m；experiments/paper14_v2_round3_xy_pcf_screen/runtime/position_filter_realization_pcf_step_v3_5.m；同目录 run_dl1018_closed_loop.m 的事件 sc 构造及后段 eta 推进。这些文件本轮均只读。
