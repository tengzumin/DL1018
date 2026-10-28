# W09 TRAIN baseline frequency audit

只读审计：读取两个指定 TRAIN/B `raw_run.mat`，未运行 Plant/MATLAB、未读 TEST、未重建惯量。

## 高频定义追溯

冻结 scorer 的 `classify()` 直接解析 scene ID 末尾 `_Wnn`，把编号 09–14 归入 `HF_W09_W14`；这是预先按风场编号分组，不是从轨迹频谱自动检测出的高频任务组。WN12 screen 的冻结选样规则进一步把每种拓扑的最低风 DEV 与最高风 VAL 各取一场，因此 HF6 是三个拓扑 × (低端 W09, 高端 W14) 的 6 场配对。
两条指定 TRAIN 场的 scene spec 均为 W09、wind_band=3、双正弦风 f1=2 Hz 与 f2=3 Hz（A1=1.5、A2=1.0 m/s，V0=9 m/s）。场景生成代码把该 wind profile 单独写入 `environment_wind_I`；任务参考由独立的 HELIX/SQUARE `make_reference()` 生成。W09 的高频在风输入上，轨迹频率不由 W09 决定。
计分 task attitude 只用 `scene/reference/acceleration`、reference yaw、重力 9.8 m/s² 与 30° 倾角上限重建，不把 `environment_wind_I` 直接送入任务姿态公式。风可经 Plant、位置误差/控制命令影响后续姿态链，但不直接成为 task reference 项。
## 频谱与姿态偏置

频谱用全 20 s、1 kHz 记录，Hann 单边 periodogram；每 0.05 Hz 左右一个频点。表内带通 RMS 对各轴单独积分 PSD。姿态路径误差同时报告各轴平均偏置、AC RMS 与精确 SO(3) RMSE。
| TRAIN 场景 | 参考加速度 RMS x/y/z (m/s²) | 风速度均值向量 (m/s) | 风速度 RMS / 峰值 (m/s) | task roll/pitch RMS (mrad) | B task-SO(3) RMSE (mrad) | task−actual Euler 均值 (mrad) |
|---|---:|---:|---:|---:|---:|---:|
| DL1018_TRAIN_T1_C10_W09 | 0.371/0.373/0.021 | -6.030/-6.030/2.285 | 8.982/11.070 | 37.955/37.786 | 46.724 | 30.852/-31.515/1.241 |
| DL1018_TRAIN_T3_C09_W09 | 0.234/0.234/0.000 | -8.521/0.000/2.283 | 8.976/11.168 | 23.886/23.886 | 62.243 | 1.502/-60.076/-0.194 |

误差均值的主要路径来源如下（stage 定义为左信号−右信号；角度均按 wrap 处理）：

| TRAIN 场景 | task→command 均值 roll/pitch (mrad) | command→filtered 均值 roll/pitch (mrad) | filtered→actual 均值 roll/pitch (mrad) | task→actual 均值 roll/pitch (mrad) | task→actual bias 向量范数 / SO(3) RMSE (mrad) |
|---|---:|---:|---:|---:|---:|
| DL1018_TRAIN_T1_C10_W09 | 25.365/-31.802 | -0.164/0.172 | 5.651/0.115 | 30.852/-31.516 | 44.121/46.724 |
| DL1018_TRAIN_T3_C09_W09 | 2.818/-59.012 | 0.014/0.291 | -1.330/-1.355 | 1.502/-60.077 | 60.096/62.243 |

### 2–3 Hz 带的实际量级

W09 的 2–3 Hz 风峰在两个 raw 中都可见；reference acceleration 与 task attitude 基本集中在 0.05–0.5 Hz。B 的实际姿态在 2–3 Hz 有小幅周期成分，但在这两例中 task→actual 的主要误差是稳态 Euler 偏置：T1 bias 向量范数约 44.1 mrad / SO(3) RMSE 46.7 mrad；T3 约 60.1 / 62.2 mrad。小角度近似下 bias² 占两例 SO(3) RMSE² 约 89% 与 93%；此比例只作偏置主导诊断，不是 SO(3) 的严格可加误差分解。
T1 的 command target 平均姿态约 (−25.4,+31.8) mrad，而 task−command 偏差约 (+25.4,−31.8) mrad；actual 平均姿态约 (−30.8,+31.5) mrad，filtered−actual 均值约 (+5.7,+0.1) mrad。T3 command target 平均姿态约 (−2.8,+59.0) mrad，task−command 约 (+2.8,−59.0) mrad；actual 平均姿态约 (−1.5,+60.1) mrad，filtered−actual 约 (−1.3,−1.4) mrad。故这两条 B raw 的 task 误差主量级出现在 task→command 外环链及其低频/偏置，而不是内环对 task 的纯 2–3 Hz 滞后。
这并不能直接解释 Candidate 为什么输/赢 B：指定 TRAIN raw 里没有匹配 Candidate flight，本审计只刻画 B 与共同场景输入。比较候选的因果归因需要相同场景下 Candidate/B 的 command、filtered reference 与 actual 的并行谱及偏置。
## TRAIN24 与证据边界

POSITION_TRAIN24 manifest 明确对应 24 个 C5-M110/PCF TRAIN 场景；其 scene list 不包含 `T1_C10_W09` 和 `T3_C09_W09`。因此本次两条 W09 raw 是完整 TRAIN split 的 B 基线，但不属于已锁定的 C5 POSITION_TRAIN24 子集；不能用它们推断该 24 场的位置收益训练分布。
检查来源：冻结 scorer、WN12 taskbook、`make_scenes_dl1018.m`、`wind_velocity_profile.m`、上述 B raw 与 POSITION_TRAIN24 manifest。输入 SHA256 写在 JSON；CSV 是逐轴频谱与路径差异。
