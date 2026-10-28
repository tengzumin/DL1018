# 架构历史的长记忆覆盖范围

只读核查训练/筛选代码、数据构建脚本及已有 C5 RBF replay 结果。未运行训练、MATLAB/Plant；未读取 TEST 或真实惯量。结论只限于“历史训练是否覆盖了跨 20 s 持续状态”。

## 结论

**现有 attitude architecture screen 与 full72 训练没有检验跨整段 20 s 持续的 recurrent/SSM hidden state。** 当前 attitude screen 的四种架构都以 15 个事件为一个独立样本窗口（事件约 10 ms 一次）；full72 MLP 与 GRU 同样随机抽取 scene/event 窗口训练。GRU/DSSM 的状态每次窗口前向都重置，未跨窗口携带；梯度至多穿过该 15 事件窗口，没有整段序列或全场 TBPTT。

此前“五家族” MLP/KAN/TCN/GRU/DSSM 是**位置环**筛选，不能当作 attitude RBF 的长记忆验证。该筛选主要用 32 步样本窗口，并含一个 TCN14_L128 的 128 步有限上下文扩展；其中 GRU/DSSM 仍逐窗口零初态，不是 20 s 持续状态。该 TCN128 也属于位置特征/标签，不能回答 attitude 教师标签上的长记忆效果。

因此，已有筛选显示的是短上下文模型的比较，不是“长记忆模型已被充分试过并否定”。这是覆盖范围事实，不说明长记忆是闭环退化的主因。

## 可核查细节

| 范围 | 代码实际做法 | 行号依据 |
|---|---|---|
| 早期五家族筛选 | Amendment 08 明确五家族结果属于 position loop、B-RBF attitude 输出没变。主配置 MLP14/KAN14/TCN14/GRU14/DSSM14 为 32 步；另有 MLP20/TCN20 32 步及 TCN14_L128 128 步。MLP/KAN 取窗口最后时刻特征；GRU 未传入 hidden 并明确注释每个 episode-window 零初态；DSSM 每个窗口设零 state；TCN 为有限输入窗口的因果卷积。 | `experiments/dl_attitude_replacement_20261026/DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT08_ARCHITECTURE_SCREEN.md:5-9`；`experiments/teacher_reuse_model_screen_v1/scripts/fit_models.py:25-33,446-462`；`teacher_models.py:51-64,81-102,105-145,148-159` |
| Attitude 离线架构筛选 | 实际 `FAMILIES` 是四个：MLP15、GRU15、DSSM15、TCN15；`WINDOW=15`、输入 13。GRU forward 只接收本窗口 `x`，无 hidden 输入/保存；DSSM 每次从 `zeros_like` 开始循环 15 步；MLP flatten 当前 15×13，TCN 仅对窗口做因果卷积。训练批次随机抽 scene 与 event，抽取单窗口、单事件标签后各自 `loss.backward()`/optimizer step。 | `experiments/dl_attitude_replacement_20261026/architecture_screen_v1/screen_attitude_architectures_v1.py:29-36,53-120,226-273`；结果只标为 offline screen：`architecture_screen_v1/runs_v1/screen_results.json` |
| DSSM 初态与时间常数 | attitude DSSM 初始 `tau` 在 0.02–1.28 s 对数间隔，训练可调并 clamp 到 0.005–5 s；但每次 `forward` 都把 state 归零，仅按窗口 15 个点递推。不能把可学 tau 等同于训练时保留 20 s state。 | 同上 `screen_attitude_architectures_v1.py:76-92` |
| Full72 MLP/GRU | 两份 full72 trainer 均为 WINDOW=15、batch=512、60,000 steps；每次随机抽 72 场之一和 0–1998 的 event index，再构造一个 15-window、取当前 event target、单次反向传播。MLP 无 recurrent state；full72 GRU 调用同一 GRU15 窗口模型，state 不跨窗口；无 scene 顺序 unroll、hidden carry 或场级 TBPTT。实际 MLP 与 GRU 训练 receipt/progress 均记 60,000 steps PASS，validation disabled。 | `mlp15_c5_teacher_full72_v1/train_mlp15_c5_full72_v1.py:34-45,320-378`；`gru15_c5_teacher_full72_v1/train_gru15_c5_full72_v1.py:34-45,320-378`；实际配置/回执：`mlp15_c5_teacher_full72_v1/runs/C5_MLP15_FULL72_SEED2026102001/{training_config.json,run_receipt.json}` 与 GRU 同名目录的 `training_config.json` |
| 合法特征与教师目标 | Full72 输入顺序为 wrapped attitude error×3、body rates×3、nominal BS body torque×3、morph command×4；显式排除 `Jhat/Jdot_hat`、惯量/质量属性、Plant truth、RBF 权重/hidden state、observer、physical feedforward。标签为 attitude event k 的 `rbf_output_raw`，post-DMAX/pre-beta，rad/s²。 | `train_mlp15_c5_full72_v1.py:37-46`；dataset builder `build_matched_teacher_dataset_v1.py:44-52,289-303,590` |
| 序列数据可行性 | 已抽取数组保留每场 1,999 个按时间递增的 100 Hz 事件：事件索引 `10,20,…,19990`（零基 transition），builder 验证 event flag 与此完全一致，并按该数组顺序提取 feature/label。NPZ 中 C5 TRAIN24 和 C5 VAL48 分别为 `[scene,1999,13]` / `[scene,1999,3]`；全量开发训练将 VAL48 作为 `VAL48_AS_DEV_TRAIN`。所以从既有有序输入/标签做一次 sequence-distillation 在数据排列上可行；当前随机窗口 trainer 没有这样做。此判断只说明数据可用，不是训练授权。 | `mlp15_c5_teacher_redistill_v1/build_matched_teacher_dataset_v1.py:38-41,277-303,528-559,590-595`；`mlp15_c5_teacher_full72_v1/train_mlp15_c5_full72_v1.py:331-339` |
| 原 C5 RBF 的跨事件记忆对照 | 独立 replay 每个 scene 将 RBF `W` 初始化为零，在 1,999 个真实事件上按输出使用 `W_before`、随后更新并令 `W=W_after`，六场共重放 11,994 events，逐事件及已有 weight snapshots 通过。这个在线权重状态确实跨约 20 s 事件序列累积；MLP/GRU/DSSM 的离线窗口训练没有复现这种状态保留。该差异只描述训练覆盖范围，不证明其解释闭环结果。 | `experiments/dl_attitude_replacement_20261026/attitude_rbf_local_reference_20261027_v1/rbf_replay.py:333-345,363-364,431`；`attitude_rbf_local_reference_20261027_v1/REPORT_v1.md`（six scenes × 1,999 events，replay parity PASS）；`STATUS.json`（11,994 replayed events） |

## 判定边界

- 当前架构选择对 attitude 目标只比较了 15-event context，不能称已检验 20 s persistent recurrent/SSM state。
- 老的 5-family position screen 与 attitude C5-RBF 标签不匹配，不可把其排序转移到姿态环。
- C5 full72 有保持事件顺序的开发序列数据，可供未来单次 sequence-distillation 可行性设计；是否实施、如何切分/评估须 root 另行决策。本报告不建议新方法搜索，也不把长记忆解释判为主因。

