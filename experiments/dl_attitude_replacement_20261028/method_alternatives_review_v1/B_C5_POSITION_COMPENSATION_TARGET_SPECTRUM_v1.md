# B/C5 位置补偿与姿态命令频谱核验

日期：2026-10-28。只读检查锁定的 HF6 DEV/VAL raw 与控制源码。未修改任何运行源码或 raw；未运行 Plant、未读取 TEST、未读取风力字段、未进行惯量重建。

## 结论

B 的任务姿态更好不能解释为“B 没有位置补偿”。B 使用 `B2-RBF-Full-SPLIT`，有传统在线位置 RBF 残差补偿；HF6 raw 中该 RBF 力除以质量后，与实际施加的总位置补偿逐点完全相等。C5/Parent 则关闭该 RBF 输出，使用 Stage1 delayed M110 在线位置头及 PCF；Stage1 held applied acceleration 与总补偿逐点相等。二者用了不同补偿机制。

锁定 HF6 同场宏均值中，B 的任务姿态 SO(3) 为 57.619 mrad，C5 为 61.204 mrad，Parent 为 61.199 mrad。冻结评分路径诊断将 B 与 Parent/C5 的差异定位在外环命令：task→command RMSE 为 B 61.485、Parent 80.563、C5 81.213 mrad；command→filtered 为 B 14.738、Parent 61.267、C5 61.262 mrad；filtered→actual 为 B 16.193、Parent 14.410、C5 16.425 mrad。三段是不同参考曲线间的 SO(3) RMSE，**不可相加成总差或因果份额**。

## 控制路径与语义

两类方法均经共享 `position_bs_step` 和 `baseline_force_to_attitude`：

```text
e = r.position - p
de = r.velocity - v
alpha = r.velocity + k1 .* e
z2 = alpha - v
a_nom = r.acceleration + k1 .* de + e + k2 .* z2
F_cmd = mass * a_nom - dF
a_cmd = F_cmd / mass
```

适配器将 `a_cmd + g*e3` 与当前 yaw 映射为推力、roll、pitch，倾角上限为 30°；运行时再把该 RP 与轨迹 yaw 拼成 `command_filter_target_euler`。因此这里的 target 是位置环补偿后的力方向命令，不是评分器从外部轨迹重建的 task 姿态，也不是滤波后的内环参考。

- B 的冻结 active runner 为 `experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m`，SHA-256 `e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f`。B 的 `dF=heldRbfForce` 在该文件第 1879 行；raw method 为 `B2-RBF-Full-SPLIT`。HF6 上 `position_compensation_applied_acceleration_mps2` 与 `position_rbf_compensation_force_N / 0.695` 最大差为 0；Stage1 replacement/delayed/PCF 标志均为 0。
- C5 的冻结 active runner 为 `experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m`，SHA-256 `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`。该文件第 1980 行以 `stage1PositionHeldForce` 替换 `dF`。HF6 raw 的 Stage1 replacement、delayed prediction、PCF 标志均为 1，coordinate mask 为 M110；Stage1 held applied acceleration 与总位置补偿最大差为 0，RBF 补偿力为 0。Parent 使用相同 Stage1 位置路径，HF6 目标谱和补偿量与 C5 很接近。
- B/C5 共用 `command_filter_step.m` SHA-256 `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b` 和 `command_filter_init.m` SHA-256 `64fbd68ef652f419066e0546569ba4029bdc00da3eabb0f8019bdc12f66d14a5`。已锁定配置相同：`wn=[18,18,12] rad/s`、阻尼 `[1,1,1]`、加速度限幅 `[Inf,Inf,6] rad/s²`、`dt=0.001 s`、初值为实际 Euler 和零滤波速率。已有 28 场 replay 对 B/C5 的滤波目标复现误差在机器精度量级；滤波实现不一致不是这里的解释。

## 补偿与 2–5 Hz target 频带

重放脚本从 `GRU_PREDICTION_TAU01_SCORE_final12.json` 读取锁定路径，并逐个核验 18 份 raw SHA。对每种方法自己的轨迹，使用 raw `position_nominal_acceleration_mps2` 和当时 state yaw，通过冻结力方向适配器重建“去掉位置补偿”的 RP target；用 `position_nominal_acceleration_mps2 - position_compensation_applied_acceleration_mps2` 重建实际 target。实际 target 对 raw `command_filter_target_euler` 的最大误差不超过 `1.11e-16 rad`。频带数值为每个场景 20,000 个 1 ms transition 的不去均值矩形窗 FFT，`2 <= f < 5 Hz`，先算每场双轴 RP 合成 RMS，再对 6 场等权平均。

| 方法 | 总位置补偿 RMS (m/s²) | 实际 target RP 2–5 Hz (mrad) | 同轨迹无补偿 RP target (mrad) | 补偿引起的 target 差分信号 (mrad) |
|---|---:|---:|---:|---:|
| B | 0.601489 | 8.955 | 8.986 | 2.179 |
| C5 | 0.740798 | 53.917 | 12.051 | 44.287 |
| Parent_Cosine_GRU | 0.735190 | 53.917 | 12.035 | 44.302 |

C5 的补偿总 RMS 只比 B 高约 23%，但在这个 target 差分频带，C5/Parent 分别约为 B 的 20.3/20.3 倍。六场中，C5 每场差分带 RMS 为 18.532–58.485 mrad；B 为 1.481–3.407 mrad。该证据支持一个具体、可证伪的耦合假设：Stage1 的位置补偿在这些 HF raw 上带入较强的 2–5 Hz 力方向命令变化，随后同一命令滤波器产生较大的 target→filtered gap。

“补偿引起的 target 差分”是同轨迹、同瞬时状态下的重建差，并非重新闭环仿真。由于适配器非线性，实际 target PSD 也含名义命令与补偿变化的交叉项；表中差分 RMS 不能当作可加的 PSD 贡献，也不能单独证明该补偿导致闭环任务分数差异。不同方法的状态/位置轨迹本身也不同。

## 可检验的最小候选

优先测试**仅对 C5 Stage1 applied `dF` 做因果输出低通**，再送入共享 `position_bs_step`；保留名义位置 BS、低频 Stage1 补偿、M110、在线 head、PCF、GRU 姿态路径、WN18 和 J0。低通截止只能由 TRAIN 数据预先确定，不能按这 6 场回调。PCF 每步继续使用修改后实际的 `a_cmd` 更新。单场预注册 task 和 Q 门槛后证伪：若 task 改善不足或 Q/PCF 残差越界就拒绝。此想法与全频补偿乘 0.9、改 head 学习常数 tau、改 yaw、替换 PCF 状态、或统一降低姿态命令滤波带宽不同；它仍只是开发数据支持的假设，不代表预测能保住 C5 位置效果。

## 复现与身份锁

从仓库根目录运行：

```powershell
python experiments/dl_attitude_replacement_20261028/method_alternatives_review_v1/b_c5_compensation_target_spectrum_v1.py
```

脚本对 score JSON、两份输入锁、冻结 B/C5 runner、位置 BS/力姿态适配器、命令滤波器及默认质量配置做 SHA 检查；然后核验各 raw 的 score-bound SHA、力/加速度恒等式、target 重建和补偿来源。脚本 SHA-256：`A18AD993D952DF46C7CD254AAC1A033E64B78A7EB60D1C5485ABBD924EC13CA9`。

| 文件 | SHA-256 |
|---|---|
| `experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json` | `132ac1ccf86f3c2b51a4c89eaebdb23170f62598205e7ce7072a6a7e47759fcb` |
| `experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json` | `8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452` |
| `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json` | `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75` |
| `experiments/position_delayed_prediction_c3_dev72_20261023/run_dl1018_closed_loop.m` | `e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f` |
| `experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m` | `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c` |
| `matlab/core/position_bs_step.m` | `ea533c3ae97cbc552208287e7f8d9b0a0f5a018f36fb5c8bd45520e19e73c681` |
| `matlab/core/baseline_force_to_attitude.m` | `ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039` |
| `matlab/core/default_config.m` | `685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51` |
| `experiments/dl_attitude_replacement_20261026/attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/HF_W09_W14_attitude_path_by_scene_phase.csv` | `87e5780879b5c5ae9ff8be8eb8cae3f99700b939938239dc15c4827ee412daaa` |
| `experiments/dl_attitude_replacement_20261026/attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/SOURCE_ATTRIBUTION_AND_FILTER_REPLAY_CORRECTION_v1.md` | `9623696c73d99306c631a36d5c21adce7bce7dec4f99301c9bf95418b3d820e7` |

### Raw SHA-256

| Scene | B | C5 | Parent_Cosine_GRU |
|---|---|---|---|
| DEV T1 C10 W09 | `d1048a81954f856f3d4dac15d510f1cc7130775878bc4677ef76fd088c712a5f` | `1e684df2174bc6b754e7798c67acb5c0b4ead218bcc1bd7b1d5cfc1a2fcf4991` | `c40239f9c9a6cea0f233eabdea3294b20ff4d3384e22a59055dc4e5358f5b541` |
| DEV T2 C09 W10 | `61bb549a6afc78326bb6d577cd52c14f0edd52c046f69681f97a2e88adb5751e` | `9810e02aa6bede12197eda25dbb0c18335252b1965f055931ea28b2f2dbb505d` | `518567b25d19d8e8acd6a74c33eb7c5ed6b78c507d6f022a0cd12ba6bf126e98` |
| DEV T3 C09 W09 | `a8cec3af85c0988622a3582385a44a201aa2d5e796fa73a933277cde0cf85f49` | `fa11a41b18ce9d4c3b7558d3bbb0d230aaef3e7071fc15419df0c6d1fca2f3a4` | `14176658aac8e8b69817f71aff748add1b591cee744cd05954184e52e34c2cb2` |
| VAL T1 C07 W14 | `d1b472b85cb95736eab9f9c05bb74ec24fa1ba52908b19c7897226153793cd26` | `df07c18cd061aa78e8e1152b73bccc2ae11026a5d54630065c877a5e4ec42dd1` | `fe85f45de5cb16135840a1cb0a6c9bb8e7ac1c1e7e1bcda274c7b7eb1f1b2c27` |
| VAL T2 C04 W14 | `2648d58e27b3d9a00c27ed181a074bf1d5b893768ff74ec18e341508c648689e` | `b3cbe42c3835600cef5b4a5adbafe619cb83c56da94f37fe87669e027e91c6bf` | `9b009512da9f08e917f5484d6292066dcbcb731353df72828dc702d76b6a3479` |
| VAL T3 C01 W14 | `396496784a14c217d90bcb4566dad275c8602503d6debce6dce63ec50497ae5e` | `556be0c5cc9ae61c077597fdf474c2fde74f443a848bcd7dcfe0f7f49768db83` | `76afcf331ca14b169977810c74c8a8680f57d9747a9a3b9a46285804a98a0503` |
