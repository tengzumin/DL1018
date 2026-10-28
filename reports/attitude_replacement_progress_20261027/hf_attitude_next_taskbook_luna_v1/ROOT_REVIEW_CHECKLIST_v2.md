# ROOT 审核清单：HF 同状态 shadow v2

范围：仅审阅任务书和已存在的 W09–W14 DEV/VAL 资料；没有运行 shadow、MATLAB、Plant、训练或 TEST。

## 已核验，可供审阅

- [x] FULL72 score 中 28 个 W09–W14 场景；候选/C5 共 56 份 raw 与 56 份 run_status 全部存在，路径都在 DL1018 仓库根内。
- [x] 56/56 raw SHA、56/56 status SHA 与 paired score 一致；候选 28/28 raw audit SHA 匹配且 `PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY`。
- [x] 候选为 25 个本 study raw + 3 个 parent reuse；C5 为 6 个 input-lock reuse + 22 个新 raw。每场完整绝对路径在 `HF_RAW_INPUT_IDENTITY_v2.csv`。
- [x] C5 的 6 reuse：`VAL_T1_C02_W09`、`VAL_T1_C05_W12`、`VAL_T2_C00_W10`、`VAL_T2_C02_W12`、`VAL_T3_C00_W13`、`VAL_T3_C12_W09`；score audit 标记 `PASS_C5_RAW_ALL_EVENTS`。另 22 条 C5 新 raw 为 `RUN_COMPLETE_RAW_PENDING_AUDIT`。
- [x] C5 28 条 `run_status.json` 的原 status 均保留 `RUN_COMPLETE_RAW_PENDING_AUDIT`；旧 screen audit PASS 不把原 status 晋级。C5 reuse 路径/hash 对 lock，22 条新路径/hash 对 batch status。
- [x] 候选/C5 raw 所需 HDF5 `log` 字段 56/56 存在；字段存在性和所有 raw/status 哈希结果在 CSV/summary。
- [x] C5 runtime/core 源码 SHA 与 C5 input lock inventory 一致。源码显示 C5 W 初始化为零，locked options 路径无 attitude initial-weight override；执行前仍须 fail-closed 重查 override。
- [x] C5 RBF 当前输出由 `W_before` 产生，之后更新/投影 `W_after`；6D 输入交错 `[e1,s1,e2,s2,e3,s3]`，beta 后经 fixed `P.inertia` 到 torque。命令滤波返回更新前参考/速率，然后因果半隐式更新状态。
- [x] 固定 `J0` SHA `8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75`；没有部署端 `Jhat/Jdot_hat` 重建。C5 DSSM14/M110 身份原样保持。
- [x] 任务书 v2 保留 CM18-A1 task SO(3) 缺项及其旧 raw MAT 缺失事实；不将 inner SO(3) 旧数值重新标成 task SO(3)。

## 执行前 STOP 门

- [ ] 逐条确认 raw 数组维度、采样时间、有限值、candidate/C5 event flag 的时间对齐与完整计数；本次只核字段存在，没有读取这些数组值。
- [ ] 因果重建命令滤波，逐样本通过 v2 容差；否则该 scene 不做 cross-model shadow。
- [ ] 确认六个 C5 reuse 的 `parent_screen_event_count=1968` 与 raw per-step event/update 覆盖一致/可解释；不一致则该 scene STOP，不推测为完整 replay。
- [ ] 从锁定配置/opts 确认 `rbf_attitude_initial_weight` 不存在、effective config/J0 与 SHA 对齐；MAT 文件未由 MATLAB 打开，参数值级确认留给执行前静态/只读 identity gate。
- [ ] 每场先过 GRU 与 C5 native self-replay parity；任何字段缺失、事件不完整、memory 链差异或容差失败，只报告 FEASIBILITY_ONLY，不比较模型优劣。
- [ ] 诊断输出总计不超过 5 GiB；不复制 raw。保留 C5 原 run_status 与 audit_status，不因诊断改级。

## 封存约束

仅允许读取列明的 28 对 DEV/VAL raw、paired score、对应 lock/batch/status 与模型/config身份。禁止 MATLAB、Plant、训练/optimizer、闭环重跑、TEST 读取；不修改 production runner/model/config/raw。此清单和任务书均不构成执行授权。
