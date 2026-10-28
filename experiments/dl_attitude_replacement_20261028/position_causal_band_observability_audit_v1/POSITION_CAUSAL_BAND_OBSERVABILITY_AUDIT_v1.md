# TRAIN24 因果频带可观测性审计 v1

## 结论

现有数据不足以训练一个可靠的、能同时保住 C5 位置表现并把高频任务姿态压到 B 水平的频带门控网络。本次只做了 TRAIN-only 信号审计，没有训练模型、没有运行 Plant、没有读取 VAL/TEST、没有惯量重建。

把现成 10 ms 位置残差 target 作为高频 band 的监督会有方向冲突：在同一条闭环轨迹中，C5 action 与 target 在主要风频附近高度同频；target 可能奖励保留/增强这部分位置补偿，而姿态目标可能希望抑制其进入姿态回路。它不是改动作后位置 Q 的标签。

参考频率回归也有严重窗口边界泄漏：未加窗的有限记录 tone fit 会把慢任务轨迹泄漏到 2.2–4.8 Hz。参考位置/速度/加速度本身 1 kHz 数值微分保持一致，因此不能把全窗未加窗拟合幅值当作真实高频命令线。Hann、Welch 和去慢趋势 residual-fit 显著减小这些线。

## 数据与口径

- 数据：物理 `TRAIN_C5_24` 的 24 个 `DL1018_DEV_*` 场景；每场 1,999 个 position event、1,968 个 ready event，100 Hz。输入是现成 X14、C5 applied action、10 ms raw target；从同一批 C5 raw 只读取 scene reference 的 position/velocity/acceleration。
- 风组/频率只用于离线分层和指定 tone 查询，不进入任何部署输入。未解析 wind truth 字段。
- PSD/coherence：Hann Welch，1024 样本窗（0.0977 Hz bin），50% overlap。相干度在参考加速度频带 RMS 小于 action 的 5% 时标为低功率，不解释为可部署分离信号。
- Tone 检查：全窗未加权拟合、Hann 加权拟合、Welch `f±0.12 Hz` 局部功率、减去 0.5 Hz 零相位低通参考趋势后的残差拟合。后两者仅作离线诊断，不是在线滤波器。

## 全 TRAIN24 频带摘要

以下为按场先算频带、再对 24 场取中位；RMS 单位均按对应信号单位。Msc² 是原始描述值，参考能量不足的频带不应作为门控判据。

| 频带 Hz | action RMS m/s² | target RMS m/s² | reference accel RMS m/s² | ref/action | action-target Msc² | action-reference Msc² |
|---|---:|---:|---:|---:|---:|---:|
| 0.10-0.50 | 0.071 | 0.091 | 0.34508 | 4.876 | 0.949 | 0.492 |
| 0.50-1.00 | 0.034 | 0.046 | 0.00170 | 0.057 | 0.845 | 0.512 |
| 1.00-2.00 | 0.032 | 0.058 | 0.00021 | 0.013 | 0.936 | 0.571 |
| 2.00-3.00 | 0.020 | 0.027 | 0.00003 | 0.004 | 0.981 | 0.499 |
| 3.00-4.00 | 0.048 | 0.084 | 0.00001 | 0.003 | 0.988 | 0.487 |
| 4.00-5.00 | 0.009 | 0.013 | 0.00001 | 0.002 | 0.984 | 0.547 |

参考线相干在参考能量很小的高频段数值不稳；表中的 action-target 相干也来自同一闭环 raw，不是 action 干预的因果估计。
0.5 Hz 低通趋势剥离会按定义去掉 W00–02 的 .25/.45 Hz 成分；该 residual-fit 只用于检查高于转折频段的边界泄漏，不用于评估这两条低频参考线。

## 参考 tone 边界泄漏检查

取 W09 2.2 Hz 的同场参考位置为例：未加窗全记录 fit 约 1e-2 m，Hann fit 约 1e-5 m，低频趋势剥离后的 Hann residual fit 约 1e-6 m；明显的量级差说明全窗拟合受慢轨迹/端点污染。raw 1 kHz 参考信号的差分一致性如下：

- finite-difference(position) 对 logged velocity：relative RMS 中位 `1.49e-07`，P95 `1.66e-07`。
- finite-difference(velocity) 对 logged acceleration：relative RMS 中位 `2.21e-07`，P95 `1.25e-05`。
- 对 W09 residual-fit 的小参考 tone，位置/速度/加速度的导数关系大体恢复一致；绝对参考加速度线仍比 C5 action 小很多。W12–14 更高频的参考线接近数值/谱估计底噪，应标不可辨。

| 离线频组 | lines | position full / Hann / residual median (m) | velocity full / Hann / residual median (m/s) | acceleration full / Hann / residual median (m/s²) |
|---|---:|---:|---:|---:|
| W00-W02 | 6 | 0.070109 / 0.048794 / 0.000277 | 0.051824 / 0.082248 / 0.000444 | 0.069352 / 0.129011 / 0.000732 |
| W03-W05 | 6 | 0.018025 / 0.000263 / 0.000008 | 0.006037 / 0.000065 / 0.000031 | 0.000922 / 0.000027 / 0.000045 |
| W06-W08 | 10 | 0.014874 / 0.000053 / 0.000000 | 0.001971 / 0.000006 / 0.000001 | 0.000864 / 0.000009 / 0.000002 |
| W09-W11 | 8 | 0.010627 / 0.000007 / 0.000001 | 0.002764 / 0.000018 / 0.000017 | 0.000032 / 0.000336 / 0.000335 |
| W12-W14 | 12 | 0.006200 / 0.000002 / 0.000000 | 0.000700 / 0.000000 / 0.000000 | 0.000046 / 0.000000 / 0.000000 |

The full-window tone fit is not a safe estimate of high-frequency command content. The deployment model must not use future/window-wide spectral estimates; any causal feature needs a measured transfer function and startup behavior.

## 有限阶滤波的低频泄漏

以 100 Hz、0.5 Hz 四阶 Butterworth 因果高通残差支路为响应示例：DC 数学上为零，但 0–0.5 Hz 并非零；.25 Hz 幅值仍为 0.062，.40 为 0.379，.45 为 0.549，.50 为 0.707，.58 为 0.875。相位在转折区也显著变化。不能声称“0–.5 Hz machine-zero/identity”；要以实际最终 SOS 系数报告整条幅相曲线，并让 paired scene 测到其位置代价。

| f Hz | gain dB | magnitude | phase deg |
|---:|---:|---:|---:|
| 0.00 | -300.00 | 0.00000 | 0.0 |
| 0.25 | -24.10 | 0.06236 | -78.0 |
| 0.40 | -8.43 | 0.37900 | -135.9 |
| 0.45 | -5.22 | 0.54854 | -158.1 |
| 0.50 | -3.01 | 0.70711 | -180.0 |
| 0.58 | -1.16 | 0.87539 | 149.6 |
| 0.85 | -0.06 | 0.99292 | 93.5 |
| 1.15 | -0.01 | 0.99936 | 67.0 |
| 2.20 | -0.00 | 1.00000 | 34.2 |
| 3.20 | -0.00 | 1.00000 | 23.4 |
| 3.70 | -0.00 | 1.00000 | 20.2 |
| 4.80 | -0.00 | 1.00000 | 15.5 |

## 最小 paired closed-loop 数据方案（仅设计，未执行）

先用低维干预识别位置–姿态响应，不训练大网络。对照必须是完全相同 scene/initial state/reference/arm schedule 的 C5 DSSM14 + cosineGRU 基线；B raw 只在方法身份和场景身份匹配后作姿态门槛。旧 C5 raw 若不是这一精确 dual-loop stack，不可当成配对基线。

- 每个频组取 T1/T2/T3 各一条，12 条 active-band anchors：
  - W03–05：T1_C00_W03、T2_C00_W04、T3_C00_W05（0.58/0.87 Hz，转折边缘）；
  - W06–08：T1_C05_W06、T2_C06_W07、T3_C06_W08（1.15/1.75 Hz）；
  - W09–11：T1_C10_W09、T2_C09_W10、T3_C10_W11（2.2/3.2 Hz）；
  - W12–14：T1_C11_W12、T2_C12_W13、T3_C15_W14（3.7/4.8 Hz）。
- 再加入 3 条 W00–02 低频/reference-confound 控制（T1_C04_W00、T2_C03_W01、T3_C05_W02），检查 .45 Hz 附近泄漏；3 条 W15 no-tone 控制只作 identity/parity。W分组只用于选测试场，不提供给在线模块。
- 每个 active band 单独做两档轻到中等扰动：band gain 0.90 与 0.75；其余 bands=1，基线 gain=1。低组只作低频保护检查；不再做 gain=0 硬陷波。最小筛查为 12×2 + 3×2 = 30 条候选闭环运行，另需 15 个 exact C5 baseline 与对应 B score（可复用已存在且身份锁定的 raw，否则补齐）。
- 若最小筛查的 paired ΔQ_m/Δtask_SO3 方向稳定，再把该 TRAIN_C5_24 的其余 6 条 active scenes 纳入同样两档，检查 amplitude/task 异质性。看 paired Q_m、task/inner SO(3)、逐 phase XYZ 误差和安全字段。
- 只从成对结果拟合最多 4–6 个共享 band gain/低维响应曲线；按整组频带留出，scene 是有效样本单位，不能把 100 Hz event 数伪装成大数据。若不同 task/幅度组响应符号相反，拒绝全局门控，不扩充网络容量。
- 当前同轨迹 target、PSD/coherence、零相位 replay 均不能识别改动作后的闭环 Q。任何通过只够支持进一步验证，不等于部署证据。

## 文件与范围锁

- 数据 NPZ SHA-256：`15d689f08fd6d8a53a64c59dbdf62b33f9b8e8a12ce083fb12834cd106df2eeb`
- TRAIN24 physical manifest SHA-256：`18761c159e003388e7a728132913eaf0b290c0d109d797618986ef87d8fd3bbb`
- Windband profile SHA-256：`ce0c225dc39a207a9908df6a70c932149d6190c8ef0bc3a213b9f0895e143d7e`
- Scene source SHA-256：`7d11b4ebf63105b016c67f4b3c427282b35dafa53280ef2daf5578a6a16bb9ec`
- 本审计脚本 SHA-256：`9c0767d0fa0ddb2912445d0af567e03ce740081d643e722ead8c35638d9827f9`
- 已绑定并核验 C5 raw 文件数：24。具体逐场路径和 SHA 在 JSON 中。
- 本报告与 JSON 均由同目录脚本生成；本次无模型训练、无 Plant、无 VAL/TEST、无惯量重建。
