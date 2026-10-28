# 名义力矩特征路径的局部导数分解

## 范围与定义

复用已核验 `local_feedback_sensitivity.py` 的同一 1200 个 v3 成熟事件、SiLU/窗口前向和 BS 模型。past 14 event history、参考/导数、姿态、arms、beta、模型与 composite 的 `W_before` 固定；只扰动当前 omega。

`full` 同时重算当前 omega 与其派生 nominal torque 特征；`omega_only` 固定神经当前 nominal-torque 特征在原点，但控制 BS torque 仍随 omega 正确变化；`nominal_tau_only` 固定神经当前 omega 特征在原点，仅让 nominal-torque 特征变化。三种模式原点输出必须一致。

每轴网络补偿导数 `Jcomp=d(tau_comp)/domega` 检查 `Jcomp_full ≈ Jcomp_omega_only + Jcomp_nominal_tau_only`。`Jnet=JBS-Jcomp`，对 `Sym(-Jnet)` 只报告冻结状态下的局部负特征值比例，不作闭环稳定性推断。

## 核验

- 1200 events / 2400 variant rows；原点输出最大差 `0` torque units；原点 clipping：frozen `0`、composite `0`。
- 双 epsilon `1e-05` / `5e-06`；BS 解析式对差分最大绝对差 `1.47e-12`。
- 补偿导数可加性最大绝对误差：frozen eps1 `3.41e-08`，composite eps1 `8.19e-08`；eps2 `8.52e-09` / `2.05e-08`。

## 总体与分组

负特征值比例：

| 组 | 模型 | full | omega_only（tau特征冻结） | nominal_tau_only | omega_only/full 跨轴补偿 Jacobian 中位数 |
|---|---|---:|---:|---:|---:|
| overall | frozen | 60.0% | 54.5% | 13.5% | 0.881 |
| overall | composite | 54.9% | 48.2% | 11.4% | 0.872 |
| family:W15 | frozen | 70.8% | 67.3% | 14.5% | 0.882 |
| family:W15 | composite | 69.7% | 61.3% | 15.0% | 0.877 |
| family:HF | frozen | 49.2% | 41.7% | 12.5% | 0.880 |
| family:HF | composite | 40.2% | 35.2% | 7.8% | 0.842 |
| time_band:first5 | frozen | 72.9% | 68.2% | 2.6% | 0.878 |
| time_band:first5 | composite | 70.3% | 62.5% | 1.6% | 0.877 |
| time_band:middle | frozen | 54.6% | 48.4% | 12.2% | 0.908 |
| time_band:middle | composite | 46.3% | 40.3% | 8.3% | 0.867 |
| time_band:last5 | frozen | 63.4% | 58.9% | 22.3% | 0.936 |
| time_band:last5 | composite | 63.4% | 56.0% | 23.2% | 0.876 |

`omega_only_cross_over_full` 是逐事件 off-diagonal `Jcomp` Frobenius 比值的中位数；同组跨轴补偿增量幅度仍存在于 omega 输入路径。具体逐事件结果见 [EVENTS.csv](EVENTS.csv)，完整分位数、输入 SHA 和核验数值见 [RESULT.json](RESULT.json)。

## 解释边界

固定神经 nominal-torque 特征会改变部分 composite 跨轴导数，但 omega-only 模式下负特征值并未普遍消失；方向和幅度按场景/时间窗混合。该特征固定只是局部假设性评估，不是可部署修改，也不能说明删去 nominal torque 特征会改善真实闭环。RBF 参照及其他闭环因果判断仍需独立证据。未启动 Plant/MATLAB/训练，未重建真实惯量。
