# Root 独立审核：A02 C02 原始结果与 T3 续跑决定

日期：2026-10-25（Asia/Shanghai）

## A02 实际状态

A02 使用 release SHA `a8e0ba11ede0139609a756d4ea9816d0fc0dd50bd50377fbd9311034f0e26947`，attempt=`MORPH_DEV2_20261025_A02`。批次终态仍为 `STOPPED_ON_FAILURE`，runner markers=2、Plant runs=2、transitions=40,000、unknown=0、training=0；T3 的 baseline/candidate 均 `NOT_RUN`。原 status、raw、pair audit、batch status/receipt、stdout/stderr全部保留；不把批次改标为通过，也不重跑 C02。

C02 baseline与candidate均返回 `STABLE`、20,000 transitions/20,001 states，motor saturation/generalized clipping/tilt计数均为0。candidate 的run_status记作 `FAILED_ENGINEERING`，原因不是Plant停止，而是入口的RBF/trace数组形状校验错误；其后 results CSV writer 又因漏传 `csv_metric` 的第三个 `index` 参数而失败。两项都是新隔离runner的实现缺陷。

## 原始数据独立复算

root从两份A02 raw直接重算位置Q与SO(3)，并对candidate逐样本重放RBF禁用、prepare/commit时序、morph command、omega、clipped torque、estimate符号和event flag。独立指标与runner写入的run_status差异：Q/SO(3)通常小于 `2e-12`，峰值及其余位置量处于浮点舍入误差内。

| C02/W15 | Q RMSE | SO(3) RMSE | 位置峰值 | 姿态峰值 |
|---|---:|---:|---:|---:|
| baseline | 0.005412968909 m | 0.013187128979 rad | 0.015660585982 m | 0.045279229536 rad |
| candidate | 0.004270442964 m | 0.008521352291 rad | 0.010670216565 m | 0.030856030440 rad |
| candidate − baseline | −0.001142525945 m | −0.004665776688 rad | −0.004990369417 m | −0.014423199096 rad |

candidate的早段(0–2.2s)位置Q略增 `4.99e-9 m`、SO(3)略增 `1.53e-8 rad`；晚段明显改善。XYZ位置Q差约 `[-1.14696e-3, -6.20043e-4, +3.17483e-5] m`，即Z轴略差。因而这是一个有价值但仍单场景、存在轴向/早段代价的应用信号，不能据此宣称全面优于RBF或论文结果达标。

trace审核确认：20,000个helper记录、1,999个observer事件；prepare/commit时间、morph command、omega、clipped torque、estimate=-tau_comp、event flag逐项全零失配；trace内RBF flags全false。顶层两个RBF enable/update字段实际为单个运行级false标量；RBF vector histories为3×20,000且全零，权重范数等为1×20,000且全零。错误校验把标量开关误要求为N个样本、把3轴向量历史误要求总元素数=N，故触发“RBF was active or trace shape differed”。

权威独立复算：`c02_independent_v1/review.json` SHA `550d05b9a1111be91852c1c90e39c83545b1084df82676645dadefa1cb978663`；CSV SHA `d925976ced4bf1b4843c107bffc5898585b07c77af3ff802e24939ffb9b4e033`；脚本SHA `d8f5a9cdde6442bbb006e89524a0bbcfcbf8be6ee23a83220db07de3fdcb137e`。A02 batch status SHA `8fb5c7580a7fa2846569a3ccfedd28e30b421fb32210e7b8632d7dc8a31e1e00`；原pair audit SHA `7faa7a44ae3986bfe8f7ff0705e5d5bcd004bdcc1878ef77327a6221cfdd6efe`；receipt SHA `686ba00fc7e0a0723714f68329999d1a90bdb6989f9f454efcf470d5fad4e770`。

## Root 决定

**批准一次隔离的工程修复与T3续跑任务书；当前不批准立即启动Plant。** Luna xhigh只可在新的 `morph_dev2_t3_continuation_v1/` 目录实施，不得修改或重跑A02/C02、39个部署源码、模型、normalizer、C5位置环、参数或滤波器。只修复两项已定位的runner缺陷：RBF标量/向量尺寸校验，以及CSV `index` 调用。v1失败锁、release和raw均保留。

修复入口须只运行预登记的 `DL1018_DEV_T3_C10_W11`（SQUARE、arms3/4、seed 2026123971）baseline→candidate，共最多2次调用；复用同身份B/C5及已预检scene hash。性能正负都记录，只有工程/安全/完整性/资源失败停止；不训练、不跑TEST、不调参、不重复C02。独立审核后root再发新release。剩余stage产物预算最多 `1,650,000,000 bytes`（A02已用487,834,198 bytes；累计上限2 GiB），C盘最低30 GiB，无删除。