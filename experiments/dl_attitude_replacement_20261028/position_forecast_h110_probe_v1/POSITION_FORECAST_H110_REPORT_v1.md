# C5 位置 H110 离线因果预测探针

这是开发诊断，不是独立验证或闭环结果。冻结 C5 backbone 已使用开发集；本探针只在 TRAIN_C5_24 拟合两组 ridge head，在 C5_VAL48 做离线诊断。

## 方法与索引

- 特征只取 C5 raw 中 `stage1_position_event_phi_33[:, j]`；逐场与同一时刻 runtime `stage1_position_phi_33` 精确相等，确认使用 DSSM 前向后的归一化特征。不把未来状态、未来输入、TEST 或惯量重建加入特征。
- 标签字段为 `stage1_position_delayed_prediction_target_mps2` 的 XY 分量。原始 1ms 索引验证显示 H0 使用 `k=j+10`，该行的 `prev_index_zero_based=j`；H110 使用 `k=j+120`，其标签区间为 `[j+110,j+120]`，记录的前序索引为 `j+110`。过去标签基线取 `Y[j]`（区间 `[j-10,j]`），在预测时已可用。
- 两个 head 均最小化 `mean(sum((Phi W-Y)^2, XY)) + 0.001||W-W0||_F^2`，只拟合 XY；所有比较统一裁剪到 ±3 m/s²。Z 固定为 W0 原值，不拟合。
- 110ms 是由指令滤波器低频群延迟（2/18）设定的预测间隔；它不代表内环带宽。

## 数据与身份

- TRAIN raw：24 场，24 场清单 hash `18761c159e003388e7a728132913eaf0b290c0d109d797618986ef87d8fd3bbb`；拟合事件数 46920。
- VAL raw：48 场，48 场 freeze hash `7f15ef2570251e21a67149d8e133069c1b0d3ffa643675135031aba364d02634`；有效事件每场 1955–1955。全部 72 个 raw 均与各自 manifest SHA-256 相符。
- W0 SHA-256 `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`；归一化器数组 SHA-256 `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`。旧版 VAL raw 不总保存这两个 model_identity 字段，按 raw 的 input_lock SHA 绑定 C5 input lock，并逐场重算 W0 数组 hash；phi33 直接使用 runtime 已归一化的冻结 DSSM 输出。训练/验证 scene ID 不重叠。

## TRAIN 拟合记录

| Head | Target | N | 未裁剪训练 XY RMSE (m/s²) | Objective |
|---|---|---:|---:|---:|
| H0_ridge | y_h0 | 46920 | 0.356602 | 0.130511 |
| H110_ridge | y_h110 | 46920 | 0.46957 | 0.236349 |

## VAL48：全部对同一 H110 标签评分

XY RMSE (m/s²)，候选使用相同有效事件与 ±3 m/s² 输出裁剪。

| Group | Scenes | Predictor | Macro scene RMSE | Pooled XY RMSE | X RMSE pooled | Y RMSE pooled |
|---|---:|---|---:|---:|---:|---:|
| ALL48 | 48 | H110_ridge | 0.483027 | 0.502946 | 0.349508 | 0.361661 |
| ALL48 | 48 | H0_ridge | 0.483082 | 0.520449 | 0.370854 | 0.365151 |
| ALL48 | 48 | W0_prior | 0.493223 | 0.545609 | 0.389374 | 0.3822 |
| ALL48 | 48 | past_label_persistence | 0.302651 | 0.386474 | 0.288699 | 0.256934 |
| ALL48 | 48 | C5_online_raw_prebeta_preclip | 0.357734 | 0.447172 | 0.325554 | 0.306557 |
| HF_W09_W14 | 18 | H110_ridge | 0.55939 | 0.578425 | 0.402419 | 0.415493 |
| HF_W09_W14 | 18 | H0_ridge | 0.645014 | 0.674864 | 0.48682 | 0.467384 |
| HF_W09_W14 | 18 | W0_prior | 0.710172 | 0.746655 | 0.528841 | 0.527087 |
| HF_W09_W14 | 18 | past_label_persistence | 0.518674 | 0.563412 | 0.416427 | 0.379501 |
| HF_W09_W14 | 18 | C5_online_raw_prebeta_preclip | 0.618843 | 0.66389 | 0.478491 | 0.460214 |
| W15 | 3 | H110_ridge | 0.27754 | 0.281658 | 0.219121 | 0.176967 |
| W15 | 3 | H0_ridge | 0.24964 | 0.253386 | 0.190473 | 0.167106 |
| W15 | 3 | W0_prior | 0.25605 | 0.258475 | 0.192312 | 0.1727 |
| W15 | 3 | past_label_persistence | 0.0277075 | 0.0279643 | 0.020661 | 0.0188447 |
| W15 | 3 | C5_online_raw_prebeta_preclip | 0.0791485 | 0.0791519 | 0.0604354 | 0.0511134 |
| W00_W08 | 27 | H110_ridge | 0.45495 | 0.466725 | 0.322289 | 0.337583 |
| W00_W08 | 27 | H0_ridge | 0.401066 | 0.413257 | 0.287186 | 0.297163 |
| W00_W08 | 27 | W0_prior | 0.374943 | 0.387478 | 0.281026 | 0.266766 |
| W00_W08 | 27 | past_label_persistence | 0.189186 | 0.231999 | 0.180325 | 0.145966 |
| W00_W08 | 27 | C5_online_raw_prebeta_preclip | 0.214615 | 0.2469 | 0.188089 | 0.159945 |

逐场结果见 `POSITION_FORECAST_H110_SCENE_METRICS_v1.csv`；拟合权重见 `POSITION_FORECAST_H110_WEIGHTS_v1.npz`；完整来源与 hash 见 `POSITION_FORECAST_H110_RESULTS_v1.json`。

**限制：** C5_VAL48 只作为开发诊断；不能据此声称独立验证、真实部署收益或闭环成功。探针没有启动 Plant、训练大网、读取 TEST 或重建惯量。
