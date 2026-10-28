# Physical TRAIN24: C5 wind-band coverage for fixed 2.2/3.2 Hz notches

只读频谱审计，严格使用 physical manifest 列出的24个 `DL1018_DEV_*` TRAIN_C5_24场景及其现成 `C5_AXIS_MASK_M110` raw；未读取其他 split 的 raw/score、TEST，未运行 Plant、未做惯量重建。频谱来自20 s、1 kHz、Hann窗、去均值单边 PSD；频率分辨率约0.05 Hz。

## 结果

下表中“C5 action”是部署 notch 对应的最终 position compensation 量 `log/stage1_position_applied_acceleration_mps2`；不是 attitude `command_filter_target_euler`。所列风谱主峰和 C5 action 局部峰在各有变化风的 TRAIN 场景中相符。

| W组 | TRAIN场数 | DEV配置频率 f1/f2 (Hz) | raw风峰 (Hz) | C5 action峰 (Hz) | 固定 Q4 双notch在两峰处增益 (dB) |
|---|---:|---:|---:|---:|---:|
| W00–W02 | 3 | 0.25 / 0.45 | 0.25 / 0.45 | 0.25 / 0.45 | -0.01 / -0.02 |
| W03–W05 | 3 | 0.58 / 0.87 | 0.60 / 0.85 | 0.60 / 0.85 | -0.03 / -0.08 |
| W06–W08 | 5 | 1.15 / 1.75 | 1.15 / 1.75 | 1.15 / 1.75 | -0.18 / -1.28 |
| W09–W11 | 4 | 2.20 / 3.20 | 2.20 / 3.20 | 2.20 / 3.20 | 深陷波 / 深陷波 |
| W12–W14 | 6 | 3.70 / 4.80 | 3.70 / 4.80 | 3.70 / 4.80 | -2.61 / -0.46 |
| W15 | 3 | 无双正弦分量 | 无明显AC峰 | 无对应风线 | 不适用 |

21个 W00–W14 的变化风场中，C5最终 position action 的两个局部谱峰都落在对应风频附近。固定2.2/3.2 Hz Q4 notch只与W09–W11（4/24场）对准。它几乎不衰减W00–W08的低频线；对W12–W14只部分衰减3.7 Hz线，基本保留4.8 Hz线。因此把W09的双notch直接推广到全TRAIN24会漏掉多数风频组。W00–W02的0.25/0.45 Hz还与低频位置动作重合，不能仅凭频谱峰就把该能量判定为应消除的扰动。

配置来源是 `matlab/scenes/make_scenes_dl1018.m` 中当前DEV频率行（W码按每3个一组取频率带）；raw风来自 `log/environment_wind_I`。这是离线目录审计，不代表部署时可读取该真值。生成参数与测得谱峰一致；频率 co-occurrence 本身不是风因果干预。

## 部署含义

固定W09双陷波的冻结回放只覆盖两条W09 TRAIN记录：高频C5 action下降约90–95%，但0.05–0.5 Hz action改变量分别为2.23%和3.12%，超过既定2%门限；该回放也不预测闭环位置误差。详见同实验的 `position_compensation_dual_notch_train_replay_v1/TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json`，状态为FAIL。

可在后续研究一个因果、限幅的C5残差整形器：离线用TRAIN24的C5 action、已测位置/速度误差、reference acceleration和过去若干时刻的观测量训练；在线只从这些历史量估计可预测的窄带创新，不输入风场真值、W码或未来量。输出只修正C5 compensation action，低频/与reference相干的分量强约束保留，置信度不足时退回原C5 action；按整组W留出做离线验证，并继续用低频action变化门限和位置分数作为硬约束。由于0.25–0.45 Hz与位置动作重叠，单纯跟踪风频自动移动notch并不适合低频组。

逐场频率、峰值、raw路径/SHA及计算口径见本目录 JSON/CSV。所有 C5 raw 均来自当前 physical TRAIN24 manifest，不含旧 `DL1018_TRAIN_*` cohort。
