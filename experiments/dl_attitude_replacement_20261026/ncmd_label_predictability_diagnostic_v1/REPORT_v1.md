# NCMD 标签可预测性与闭环误差诊断

## 结论

NCMD 在原 C5 的 72 组输入上，比 cosine 模型更贴近新的 NCMD 标签；但 6 条 NCMD 自闭环轨迹上，同一模型对自身 10 ms 命令端口标签的误差明显增大。T2 三轴八字无风场 T2_C05_W15 的 roll RMSE 从 C5 历史记录的 0.4865 升至自闭环记录的 0.9522 rad/s²，标签 RMS 几乎不变，且输出和标签均未触发限幅。

这组数据支持优先检查闭环状态/特征分布和模型输出误差的交互，不支持把回归误差变小直接等同于闭环性能改善。C5 与 NCMD 运行产生了不同轨迹，因此这些 on/off-policy 差异是描述性比较，不能单独证明分布偏移或反馈是因果主因。

## 范围与身份

- C5 输入和旧 teacher 标签：`matched_teacher_data_v1.npz`，SHA-256 `b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f`。只读取 C5 的 X、ID、旧 Y；没有读 B24 或 TEST。
- NCMD 标签：`nominal_command_target_v1.npz`，SHA-256 `88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7`；manifest SHA-256 `fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab`；统计表 SHA-256 `599af4527376b88c0020b255a758586f333ca72151a70f09db48c8e829765344`。
- Cosine 权重 SHA-256 `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`；NCMD 权重 SHA-256 `cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6`。两个模型的 `input_mean/input_std/target_rms` 完全一致；锁定 normalizer 身份为 `612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693`。
- 72 组是 DEV24 + VAL48_AS_DEV_TRAIN，全部属于开发材料；48 组不能称作独立验证集。
- 旧 C5 记录上的推理按场景重置 hidden，使用部署合法的 13 维 X 和双精度 GRU reset/update/new 前向方程。NCMD 自闭环部分只读取 6 个已存在 raw 中的角速度状态行、`requested_generalized` 力矩行、时间、事件标志和 GRU trace 的 `feature_raw/raw_residual/clipped_residual` 字段。命令标签使用固定 LOCKED_CFG 的 J0 和请求力矩，不读取 realized torque、风、质量或真实惯量数据，也没有新 Plant 调用。
- 新训练 0、optimizer 更新 0、新 Plant 调用 0、TEST 读取 0。

## 原 C5 输入上的标签变化和拟合

下面是全 72 组、1999 事件/组、逐轴 pooled RMSE；偏差见组级 CSV。`Δ标签` 是同一 C5 记录上 `NCMD clipped target − old C5 teacher Y` 的 RMSE，`Cosine` 与 `NCMD` 两模型都在同一 C5 输入上评估新 NCMD 标签。

| 分组 | Roll NCMD / Cosine / Δ标签 | Pitch NCMD / Cosine / Δ标签 | Yaw NCMD / Cosine / Δ标签 |
|---|---:|---:|---:|
| 全72 | 0.607 / 1.040 / 0.974 | 0.665 / 1.032 / 0.934 | 0.0670 / 0.321 / 0.320 |
| W15 无风 | 0.485 / 0.727 / 0.535 | 0.486 / 0.731 / 0.584 | 0.0319 / 0.0361 / 0.0266 |
| HF W09–W14 | 0.688 / 1.195 / 1.170 | 0.769 / 1.157 / 1.114 | 0.0810 / 0.316 / 0.315 |
| T1 | 0.624 / 0.992 / 0.931 | 0.639 / 1.044 / 0.972 | 0.0672 / 0.340 / 0.338 |
| T2 | 0.606 / 1.043 / 0.955 | 0.701 / 1.032 / 0.927 | 0.0691 / 0.319 / 0.318 |
| T3 | 0.591 / 1.083 / 1.033 | 0.652 / 1.019 / 0.901 | 0.0646 / 0.302 / 0.302 |

全72 的 NCMD 新标签 RMS 为 roll/pitch/yaw `8.180 / 9.423 / 0.660` rad/s²。NCMD 对新标签的 bias 为 `−0.0075 / +0.0259 / +0.00091` rad/s²；cosine 对同一新标签的 RMSE 为 `1.040 / 1.032 / 0.321`。反过来，相对旧 C5 teacher 标签，cosine RMSE 为 `0.430 / 0.455 / 0.0342`，NCMD 模型为 `1.031 / 1.013 / 0.314`。因此权重确实转向了新标签；这只说明离线标签拟合变化，不说明闭环一定变好。

标签差异主要在后段出现。全72的早段（0–5 s）NCMD / cosine / Δ标签 RMSE 为：roll `0.171 / 0.094 / 0.00110`，pitch `0.236 / 0.095 / 0.00114`，yaw `0.0160 / 0.0104 / 0.000364`。晚段（15–20 s）为：roll `0.547 / 0.566 / 0.336`，pitch `0.558 / 0.636 / 0.346`，yaw `0.0365 / 0.0663 / 0.0596`。早段标签几乎相同而 NCMD 预测误差更大；晚段标签发生明显变化，NCMD 对 roll/pitch/yaw 均比 cosine 更贴近新标签。

NCMD 标签按精确 DMAX 的全72裁剪率为 roll 0、pitch 0、yaw `0.168%`；NCMD 预测值超过 DMAX 的比例为 roll 0、pitch 0、yaw `0.086%`。其余主要组别的标签裁剪率也接近零。限幅不是这里的主要解释。

### T2_C05_W15 的同记录比较

在同一原始 C5 输入上，NCMD 对新标签的 roll/pitch/yaw RMSE 是 `0.4865 / 0.4285 / 0.04174`；cosine 是 `1.103 / 0.6070 / 0.03626`。NCMD 新标签相对旧 teacher 标签的差异 RMSE 是 `0.8520 / 0.4567 / 0.02262`。标签 RMS 为 `15.3393 / 7.3180 / 0.01266`，clip rate 为 0。

此场早段标签差异 RMSE 只有 `1.69e−5 / 1.11e−5 / 2.25e−7`；15–20 s 则升至 `0.470 / 0.432 / 0.0132`。NCMD 模型晚段 roll/pitch 对新标签的误差是 `0.703 / 0.442`，cosine 是 `0.741 / 0.857`；yaw 上 cosine 略好（`0.0203` 对 `0.0300`）。

## 自闭环标签和 C5 历史误差

自闭环标签按每场固定 J0 的方程逐区间复算：

`Rcmd[e] = (ω[e+10]−ω[e])/(t[e+10]−t[e]) + mean_i solve(J0, cross(ω[i], J0 ω[i])−τ_req[i])`, `i=e..e+9`。

区间起点 `e=10,20,…,19990` 与 1999 个 trace 事件逐项绑定；trace 的 MATLAB `sample_index=e+1`、事件时刻和 raw 时间网格通过断言。raw trace 中保存的模型输出由相同冻结权重和该事件的合法 13D `feature_raw` 重放，最大差异小于 `1e−8`。root 的独立 1 ms 重新聚合检查也通过，六场目标最大绝对误差不超过 `5.98e−13`。

| 组别 | 指标 | Roll | Pitch | Yaw |
|---|---|---:|---:|---:|
| 六场 pooled | 自闭环输出 vs 自身 forward10ms Rcmd RMSE | 0.6982 | 0.6871 | 0.05841 |
| 六场 pooled | 同一 NCMD 模型在 C5 历史 X vs C5 NCMD 标签 RMSE | 0.4442 | 0.4929 | 0.05223 |
| W15 无风 pooled | 自闭环 / C5 历史 RMSE | 0.6580 / 0.4010 | 0.7502 / 0.5241 | 0.03049 / 0.03506 |
| HF W09–W14 pooled | 自闭环 / C5 历史 RMSE | 0.7363 / 0.4836 | 0.6175 / 0.4597 | 0.07677 / 0.06502 |
| T1 pooled | 自闭环 / C5 历史 RMSE | 0.7901 / 0.5313 | 0.9399 / 0.6481 | 0.08995 / 0.06300 |
| T2 pooled | 自闭环 / C5 历史 RMSE | 0.8102 / 0.4757 | 0.6176 / 0.4585 | 0.04430 / 0.06012 |
| T3 pooled | 自闭环 / C5 历史 RMSE | 0.4266 / 0.2889 | 0.3890 / 0.3140 | 0.01349 / 0.02451 |

六场自闭环对比的 pooled bias roll/pitch/yaw 是 `−0.0794 / −0.0392 / +0.00523` rad/s²；C5 历史对比是 `+0.0260 / −0.0318 / +0.00430`。按场景等权的 macro RMSE：自闭环 `0.629 / 0.633 / 0.0455`，C5 历史 `0.426 / 0.471 / 0.0468`。六场自闭环的输出限幅和重建标签限幅率均为 0。

T2_C05_W15 roll 的自闭环 RMSE `0.95215` 对比 C5 历史 `0.48649`（1.96 倍）；pitch `0.56415` 对比 `0.42852`（1.32 倍）；yaw 自闭环误差反而更小（`0.02404` 对比 `0.04174`）。两条轨迹的标签 RMS 几乎相同：roll `15.33956` 对 `15.33931`，pitch `7.31799` 对 `7.31800`。这排除了该场景的简单标签量纲、幅值和限幅解释，但由于轨迹不同，仍不能把误差变化因果归于某一反馈环节。

## 10 ms 时序检查

原 C5 序列上，72 场 ±2 事件 offset 扫描没有一致的单步修正：全72 roll 在 −1 事件 RMSE `0.60659`，只比 offset 0 的 `0.60701` 略低；pitch 和 yaw 在 offset 0 最低（`0.66452`、`0.06699`）。HF 三轴 offset 0 最低。W15 pitch/yaw 的 +1/+2 事件变化也只有约 `0.4%` 或更小；T2_C05_W15 三轴 offset 0 与最优相邻 offset 的差均小于 `0.5%`。

六条自闭环 raw 上，offset −2 的 roll/pitch RMSE 比 offset 0 低（`0.64092` 对 `0.69823`；`0.64994` 对 `0.68707`），yaw 仍在 offset 0 最低（`0.05841`）。这反映标签和输出的时间相关性，不推翻 trace 与 forward 区间起点的精确索引绑定，不能据此认定标签错移 10 ms。

## 优先假设和最小下一步

首要假设：NCMD 闭环下的特征/hidden 序列与 C5 记录不同，使模型在某些姿态通道的逐事件命令误差放大；相较继续降低 C5 上的离线标签误差，这更值得优先验证。六场里 T2_C05_W15 的 roll/pitch 标签 RMS、限幅率都基本不变而输出误差上升，是支持该假设的最直接描述性证据；它仍不是因果证明。

最小区分实验建议：只选 T2_C05_W15，做一对相同初态、环境、参考与确定性设置的 frozen-policy replay（C5 基线与 NCMD 激活），随后对两条日志用同一合法公式重建 10 ms Rcmd，并按时间逐段比较 feature/hidden-before 与输出误差。预先锁定场景、初始化和比较项，不训练、不改标签或限幅；仅在下一阶段获得 Plant replay 授权后执行。此配对能检验误差放大是否随闭环策略切换出现。

## 产物

- 主程序：`diagnose_ncmd_fit_v1.py`，SHA-256 `bfe0fa0861a4803705b58d08b8c94ea668260c99e13dda180bb098d966791249`。
- 自闭环程序：`diagnose_ncmd_on_policy_v1.py`，SHA-256 `3c03664fc0d058d22a61f681fefc5e59caa8b3d44a30ddeca8629f50b43e5e91`。
- 机器可读摘要：`OPEN_LOOP_FIT_DIAGNOSTIC_v1.json`、`ON_POLICY_LABEL_FIT_DIAGNOSTIC_v1.json`。
- 详细逐场 pooled/macro 指标：`open_loop_group_metrics_v1.csv`、`onpolicy_group_metrics_v1.csv`；逐事件标签/输出：`onpolicy_event_values_v1.csv`；时移扫描：`ncmd_event_lag_group_metrics_v1.csv` 和 `onpolicy_event_lag_scan_v1.csv`。
- 每个输出的 SHA-256 与逐 raw SHA-256 在相邻 JSON 回执中记录。执行命令和退出码见 `EXECUTION_RECEIPT_v1.md`。
