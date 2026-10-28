# 六场 C5 teacher 标签语义诊断

## 结论

这六条原始 C5 teacher 轨迹显示，训练标签与部署 10 ms 固定 `J0` 名义残差之间存在可测差异，但其量级不足以作为当前首要瓶颈或优先重训 representation 的单独理由。这里比较的是完全相同的已记录状态、特征和窗口；没有跨闭环轨迹作因果推断。

在 beta 已成熟、按区间起点对齐的 10,674 个区间中，冻结 MLP 对 teacher 标签的轴向训练集 RMSE 为 **[1.581, 1.868, 0.123] rad/s²**（roll/pitch/yaw）；名义残差减去起点 teacher 标签的 RMSE 为 **[0.667, 0.696, 0.098] rad/s²**，分别为拟合误差的 **42%、37%、80%**。三轴合成向量 RMSE 分别为 **2.450** 与 **0.969 rad/s²**，语义差异约为拟合误差的 **39.5%**。yaw 的相对比例偏高，但其 beta 成熟段 teacher RMS 仅 **0.380 rad/s²**、绝对残差差异为 **0.098 rad/s²**；不应把低 yaw 相关或这一比例放大解读。

每个场景的三个轴上，起点对齐残差差异都小于该场景同状态 MLP 拟合误差；T3 C00 的差异仅为对应拟合误差的约 **0.1%–1.4%**。在最后 5 秒，roll/pitch/yaw 的残差差异仅为拟合误差的 **18%/13%/14%**。因此证据不支持“目标语义或时钟偏差大到足以解释当前失败”；它可能是次要差异，不能由本诊断证明无影响。

## 对齐和量的定义

- 数据集与 builder 明确将 `rbf_output_raw` 定义为 `clip(rbf_output_unclipped, ±[45,45,4.7124])`，即 **post-DMAX、pre-beta** 标签。六条轨迹逐事件重建 beta 并核验 logged beta-applied acceleration；公式为 `beta=min((k+1)*0.001/2.2,1)`。这里 `k` 是零基 Plant transition/sample 索引（事件发生在 `10,20,…,19990`），对应 MATLAB 一基索引 `k+1`；它不是 0–1998 的事件序号。
- 合法观测量按固定 `J0=[0.003257553333333334, 0.0032575533333333334, 0.006360648333333333] kg·m²` 计算：`R=(omega[k]-omega[p])/(t[k]-t[p]) + mean((cross(omega[i],J0*omega[i])-tau_issued[i])/J0, i=p..k-1)`，`p=max(0,k-10)`，`tau_issued` 取 `requested_generalized` 的 MATLAB 第 2–4 列。未重建真实惯量。
- 对结束于事件 `j` 的 10 ms 残差，主要比较使用区间起点 `j-1` 的 MLP 输出、post-DMAX/pre-beta 标签及 beta-applied 标签；`R_j` 与结束点标签 `j` 的比较另列。首区间没有前一个 attitude event，未纳入起点对齐统计。
- beta 成熟时原始与 beta-applied 标签相等。起点到终点标签的成熟段 RMS 变化为 **[0.0436, 0.0466, 0.00351] rad/s²**，远小于 MLP 同状态拟合误差；结束点对齐的残差差异也没有显著大于起点对齐值，故目前没有明显的 10 ms 标签时钟错位信号。

| 场景 | 起点残差差异 / MLP 拟合误差（roll / pitch / yaw） |
|---|---:|
| T1 C08 W15 | 42% / 52% / 67% |
| T1 C05 W12 | 61% / 48% / 92% |
| T2 C02 W12 | 34% / 27% / 65% |
| T2 C05 W15 | 42% / 28% / 22% |
| T3 C00 W13 | 0.4% / 0.1% / 1.4% |
| T3 C02 W15 | 31% / 25% / 24% |

## 核验与限制

冻结 PyTorch MLP 使用现有 SiLU 和 event-major flatten 前向；其六场轴向拟合 RMSE 与 `SAME_STATE_REPLAY` 最大差 **9.6e-9**。重建特征对 NPZ 的最大绝对差为 **3.0e-8**；独立复现既有固定 `J0` 残差审计的最大差为 **2.4e-14**。六条轨迹的实际 compensation torque 与 RBF compensation torque 完全相同。

这些场景属于 `C5_VAL48_AS_DEV_TRAIN`，训练配置显示 C5_FULL72 使用 TRAIN24 与 VAL48_AS_DEV_TRAIN 共 143,928 个事件，验证和 checkpoint selection 均关闭。因此这里的 MLP 误差是同状态训练集拟合误差，不是独立泛化误差。输入及六条 raw SHA、模型/训练文件 SHA、公式和可重跑命令见 [INPUTS.json](INPUTS.json) 与 [METRICS.json](METRICS.json)。

## 下一项最小区分实验

若还需检查补偿对反馈量的局部作用，建议只读检查 beta 成熟区间内 compensation 对 `omega` 与 nominal torque 的局部 Jacobian，固定 `J0` 并复用同一 C5 记录状态。该检查只能提供局部冻结状态的敏感性证据，不能单独确定闭环主要根因或稳定性；不改训练目标、不调 tracking gain，也不启动 Plant。

复跑命令（PowerShell 7，从项目根目录执行）：

```powershell
python 'experiments/dl_attitude_replacement_20261026/attitude_target_semantics_diagnosis_20261027_v1/diagnose_target_semantics.py' --overwrite
```
