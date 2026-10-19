# D2：残差来源、输入敏感度与在线适应探针

## 范围

全阶段读取历史日志，新增 Plant=0、encoder fit=0。分解覆盖 BRIDGE6 的 B/POS_OFF/P_INIT 六场×三角色，并重放两条原 G06 Final 在线记录；共 18 条历史 bridge 分解、8 条逐事件运行链记录、18 份 H5 parity 检查。分解按原 exporter 公式：

`d_effective = d_wind + d_allocation + d_attitude_realization + d_mapping`

`d_applied - d_effective` 是实际补偿误差。已抽查分解的闭合最大误差约 `1.33e-14 m/s²`；标签闭合最大误差 `2.98e-15 m/s²`。每项 RMS 与交叉项都单独保留，**组件 RMS 不能直接相加**。

## 六场历史运行的组件量级

下表为 BRIDGE6 六场内各场逐条 component RMS / 指标的等场均值，单位 m/s²；它是不同闭环轨迹的描述性汇总，不是同一状态下的消融。

| Role | `d_effective` RMS | `d_applied` RMS | 补偿误差 RMS | 误差面余弦均值 | `d_attitude_realization` RMS | `d_wind` RMS |
|---|---:|---:|---:|---:|---:|---:|
| B | 0.70 | 0.52 | 0.76 | 0.45 | 0.43 | 0.39 |
| P_INIT_STUDENT | 0.80 | 0.46 | 0.61 | 0.48 | 0.55 | 0.40 |
| POS_OFF | 0.61 | 0.00 | 0.61 | 0.68 | 0.29 | 0.39 |

这组量级说明 P_INIT 确实施加非零补偿，且在这些轨迹上比 POS_OFF 有较低的补偿误差 RMS；但 P_INIT 的位置 Q 仍显著差于 B。`d_effective`、姿态实现、风、补偿和误差面都会随状态轨迹及控制反馈共同变化，因此不能由这张表断言是哪一项导致闭环位置差距。`d_attitude_realization` 较大只构成关联证据，不是单独因果解释。

## 因果可得信息与局部敏感度

有限差分只在 BRIDGE6 记录轨迹上的有效事件进行，每隔 8 个 ready 事件取样；对位置误差以 `1e-4`、滑模面以 `1e-3` 的物理扰动，保存前向输出 Jacobian 范数的中位数与分位数。它描述附近的输入敏感度，不代表闭环稳定性、全局单调性或远离记录分布后的行为。详见 [`D2_LOCAL_SENSITIVITY.csv`](D2_LOCAL_SENSITIVITY.csv)。

额外合法信息探针为 X20 = X14 + 惯性速度 `v_I` + 零学习补偿预览的名义加速度 `a_nom`。全场景分组四折，只在 G04 TRAIN 选正则化，VAL 48 场一次评价。等场 VAL 线性预测 Q：X14 **0.491362**、X20 **0.475756 m/s²**。这表明两个新增量在此线性记录数据探针中有小幅预测信息；它不等价于非线性 KAN 增益，更不等价于闭环位置收益。C1 的实物闭环结果另见 D5。

## 记录轨迹上的适应探针

支持块固定在 5.5–10 s，查询块固定在 10–20 s，按 TRAIN 场景选择正则化、VAL 只评估。Initial encoder 的 VAL 等场 query Q：固定 W0 **0.576015 m/s²**；从早段记录标签拟合的 ridge **0.378931 m/s²**；真实 Initial online Head **0.437868 m/s²**。Final encoder 对应固定 W0 **0.490428**、早段 ridge **0.349462 m/s²**。

这个结果说明记录状态上存在可被早段监督线性头利用的预测信息，但早段 ridge 不是原在线 PCF 更新律，且查询发生在记录轨迹上；不能把它报告成可部署闭环收益。在线适应现状与理想记录轨迹拟合的差距支持进一步研究训练目标/适应规则，但仍不能单独确认 H5 是主因。逐任务/风组结果见 [`D2_ADAPTATION_PROBE.csv`](D2_ADAPTATION_PROBE.csv) 和 [`D2_ADAPTATION_SELECTION.json`](D2_ADAPTATION_SELECTION.json)。

## 机制判断

- 已检查的 8 条在线记录中，模型身份、X14、输出先于更新、下一事件权重、100 Hz `dt=0.01`、beta、PCF eta、ZOH 与力到加速度闭合均在浮点容差内；18 份 H5 重导出 parity 通过。这些样本不支持生产运行链实现错误，但不能扩展为逐条核验所有历史记录。
- D1/D3 显示位置差距在早期跟踪阶段已出现，Final 相对 Initial 的同场效应是改善。D2 分解可显示实际残差大小和补偿的关联，不能把不同轨迹下的某个残差 RMS 认作唯一根因。
- 输入信息与在线适应都有记录轨迹上的局部信号；D5 C1/C2 实际闭环均未过 C0 Final 的位置门槛。共享容量、任务冲突及各训练机制间的贡献，本阶段没有单变量干预，仍不可识别。

![D2 W08 同场误差与残差诊断](/C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_causal_repair_v1/figures/D2_BRIDGE_W08_ERROR_AND_RESIDUAL.png)

事件级分量和交叉项见 [`D2_LABEL_COMPONENTS.csv`](D2_LABEL_COMPONENTS.csv)，逐场/分时统计见 [`D2_LABEL_COMPONENT_SUMMARY.csv`](D2_LABEL_COMPONENT_SUMMARY.csv)。
