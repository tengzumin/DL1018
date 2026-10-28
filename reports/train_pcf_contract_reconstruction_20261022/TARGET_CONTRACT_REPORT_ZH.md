# DL1018 PCF 目标契约离线补证

更新：2026-10-22（Asia/Shanghai）  
状态：18 条冻结分层样本、TRAIN1536 和原训练 VAL96 固定模型离线推理/目标重建均通过；父审对 1632 条 Teacher 运行的全量 sidecar 摘要也通过。证据确认目标坐标契约真实存在，但固定先验表现不支持“只换 PCF 标签即可解决失配”的结论。

## 结论与边界

现有训练/验证 raw、同运行 run_start、事件 H5 与 cache 足以精确重建 Y、请求加速度 a_req、滤波姿态对应的 a_f、残差 r_f 和固定混合目标。M 固定为 diag(1,1,0)；没有搜索替代权重。重建恒等式确认 PCF 坐标目标契约真实存在，但不能说明该标签更可辨识、可泛化或改善闭环性能。父审已完成 1632 条 Teacher 运行的全量摘要；关键 late 统计见 [KEY_LATE_RESULTS.csv](../train_pcf_contract_parent_review_20261022/KEY_LATE_RESULTS.csv)，整体结论、低频与 VAL 边界见 [FINAL_REVIEW_ZH.md](../train_pcf_contract_parent_review_20261022/FINAL_REVIEW_ZH.md)。固定 W0 在 W15 仍弱，因此没有“只改标签即可解决失配”的证据；本轮未训练新目标模型，不能据此断言重训一定无效。

18 条分层 Teacher 样本均未启用 PCF coordination。日志中的 stage1_position_pcf_* 是 NaN/占位，未用于重建；eta=0 也不代表 r_f=0。实际 a_req、a_f、r_f 均由同运行命令量、滤波状态和物理方程计算。新增的 TRAIN1536/VAL96 worker 对每条数据都重做同样的输入守卫和闭合核验。

## 数据契约与公式

冻结的 18 样本来自 task × role × wind band 共 18 组，每组在冻结 TRAIN 索引内取 run_id 字典序第一条。W00–W08、W09–W14、W15 三带候选数分别为 144、96、16。raw 索引不含独立 wind_cell 字段，按 runtime_scene_id 的 _Wdd 与训练索引交叉核对。事件映射为 raw 0 基索引 10–19990、H5 event_index 1–1999、时间 0.01–19.99 s；H5 的 Plant index 是 1 基，cache 为 0 基。raw log 的 component-major 数组与事件 H5 的 event-major 数组已显式适配，H5→cache float32、phase code、beta、索引和时间均逐元素闭合。

runtime 调用顺序是位置控制先给出 a0，a_req=a0-u。请求推力取当前 requested_generalized[:,0]，滤波姿态取当前 filtered_attitude_reference；没有用 realized 或 clipped 推力替代请求量。

    a_f = (T_req / m) R(filtered_euler) e3 - g e3
    r_f = a_req - a_f
    Y   = a_actual - a_req
    M   = diag(1, 1, 0)
    Y_M = Y + M r_f
        = a_actual - ((I-M) a_req + M a_f)

因此 XY 目标为 Y+r_f，Z 目标仍是 Y。Teacher 的 position_event_beta 与事件 H5/cache 一致；固定 W0 候选使用 clip(event_time_s/1.8,0,1)。两种时钟在首事件相差 1 ms（beta 差约 0.0005556），属于 Teacher 与候选的时钟约定差异，不作为标签 bug。没有用 100 Hz eta 差分代替 1 kHz 的精确 r_f。

对已重建目标，即使 u 匹配 Y+M r_f，位置误差动力学仍包含 M eta（dot e = s_c + M eta - K1 e）。因此坐标目标匹配不保证位置代价 Q 下降；r_f 是 Teacher 策略和滤波状态条件化的影子残差，也不自动等同于可泛化外扰。

## 阶段结果与执行账本

冻结 TRAIN 输入 SHA：PAIR_TRAINING_INPUT_INDEX.csv 257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca；G3_D4_CACHE_INDEX_1632.csv 3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e；TRAIN raw 可用性表 ab1c18ae1894a927e0c71ecd02788bc216a2a9ae1887c46d90197753cdcdb0b6；18 条冻结名单 4019aac3a23f1aef4a70f5d37b364d1ca09bfd1bcfe9ce39e486b3772af18b49。归档 runtime SHA 为 01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b。

| 阶段 | 运行结果 | 时间 / 资源 | 产物 |
|---|---|---|---|
| 18 条分层重建 | 18/18 PASS；最大闭合误差见下文 | wall 5.8976 s | stratified_reconstruction_checks.csv、PHASE_STATE.json |
| VAL96 run_start schema audit | 96/96；MATLAB_5 64、MATLAB_7.3_ROOT_CFG_OPTS 16、MATLAB_7.3_RUNSTART_CFG_OPTS 16；0 raw 读取 | 20:41:50+08:00；96 份 run_start SHA/stat 未变 | peer VAL96_RUNSTART_SCHEMA_AUDIT.csv/.json |
| TRAIN 固定模型推理 | 1536/1536 PASS；24,576 指标行；1536 sidecar | 20:17:25 启动，PID 75380；20:17:31 状态开始，20:30:15 完成；wall 764.5163 s；sidecar 769,172,595 B | TRAIN_FIXED_MODEL_5ca776c5f476_PHASE_STATE.json、..._RUNS.csv、..._METRICS.csv |
| 首次 VAL96（原 worker） | 32/96 完成后在第 33 条停止；16,001,016 B 已写 sidecar，保留 | 20:32:02.548+08:00 启动，PID 74736；wall 9.6826 s | 原目录 VAL_FIXED_MODEL_5ca776c5f476_PHASE_STATE.json（FAILED）及前 32 条原样保留 |
| 修复版 VAL96 | 96/96 PASS；1536 指标行；96 sidecar | 20:51:36.088+08:00 启动，PID 74516；20:51:37 状态开始，20:52:07 完成；wall 29.6784 s；sidecar 48,039,049 B | peer VAL_FIXED_MODEL_e445610c306d_PHASE_STATE.json、..._RUNS.csv、..._METRICS.csv |

首次 VAL 失败是 run_start 格式分支：第 33 条 G02_P_TEACHER_DL1018_VAL_T2_C00_W10_ACC_FIX_V1_B 的 MATLAB v7.3 文件使用顶层 /cfg 与 /opts，原 worker 硬编码 /runStart/cfg，触发 KeyError: component not found。没有从当前默认配置补数据。只读审计确认 VAL96 中存在三种显式配对 schema；MATLAB v5 未发现游离顶层 cfg，HDF5 的 cfg/opts 交叉 schema 或非 Group opts 会 fail closed。v2 peer 仅增加该格式分支与来源/配对守卫；原 TRAIN core/worker 及首次 VAL 32 条产物未改。

修复版在执行前固定引用并验证既有 TRAIN 父审 gate、TRAIN state/RUNS/METRICS 三个 SHA 和原固定模型身份。VAL 父审 gate VAL_COMPLETED_PHASE_PARENT_GATE.json SHA-256 为 0b0ba0084130a7d4bfd4ed59fcc821bef639692cec66ac21c0abf1b681effc39，状态 PASS，96 episodes、1536 metric rows、全部 sidecar SHA 和源 SHA/stat 通过。

## 数值闭合与固定模型身份

18 条最大误差（除注明外 m/s²）：a0 重放 5.56e-16；a_req 与 a0-u 5.56e-16；物理 Y 与事件 H5 2.66e-15；混合恒等式 2.23e-16；Y clip 与 H5 clip 2.66e-15；Teacher beta、事件时刻与 transition 各 0；X14 与 H5 3.56e-15（原特征单位）。全部 18 条 raw、run_start、H5、cache 读前读后 SHA/stat 不变。r_f 全轴 RMS 均值 0.04312，Y RMS 均值 0.21629，Y+M r_f RMS 均值 0.20310；目标能量变化不能单独说明拟合改善。

固定模型为 CORRECTED_DSSM14_SEED2026102001_FINAL60000，模型 raw SHA f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5，数组身份 8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26，normalizer 身份 533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0。所有新增推理都只使用这份冻结模型；没有训练或优化器步骤。

VAL 的 MAT5 smoke G02_P_TEACHER_DL1018_VAL_T1_C00_W07_B 有 1999 事件、1968 有效推理事件。新旧 core 的 16 个共享物理/特征/时间/索引/cache 数组逐元素完全相同；固定 W0 raw/applied 输出逐元素相同；数值指标最大差 0。结果在 VAL_V2_SMOKE_RESULTS.json 和 VAL_V2_SMOKE_METRICS.csv。另一次 root-CFG VAL33 smoke 曾在后续 MAT5 来源标签比较退出前打印 PASS；该记录不单独作为最终数值结论，VAL96 的正式 96/96 PASS 已包含并覆盖此样本。候选模型 prior-vs-zero、阶段、beta 和低频统计以后处理输出为准。

父审已给出的 W15 TRAIN all-valid 旧目标旁证：旧 Y 的 zero/prior overall RMSE 为 0.103561/0.133569，75/96 条 prior 较 zero 差；新混合目标为 0.091878/0.137985，84/96 条 prior 较 zero 差。这里 TRAIN1536 与原训练 VAL96 是 Teacher 运行条数，包含 B/POS_OFF；W15 的 TRAIN96/VAL6 也都是运行条数，不代表独立场景或 seed。原训练 VAL96 不等于封存评估 VAL48 或 TEST48。W15 零预测 SmoothL1 loss 审计中各风组权重质量仍为 6.25%，但 W15 占总零预测 loss 0.5842%；这是绝对误差能量旁证，不是训练后 loss/gradient，也不是加权 bug。

## 精确命令、冻结身份与资源预算

18 条阶段命令：

    python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_stratified.py

TRAIN1536：

    python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_full_worker.py --execute-after-audit --split TRAIN

原 worker/core SHA 分别为 5ca776c5f476c8e7ad824c11ab1381d48b6fdf0b385f9471522a8f5826a8021a / d2e2c807b8119b32eddba8f765c6c566bee40d5e37c0590363f9091d30a47f70。父审 TRAIN gate SHA 为 b0be7a622dd3ea0cfa402e3fb3eddc0d3eaed37df4ed1760abd1c1370477c501。

原 VAL 失败命令（只用于失败留档，不要重跑）：

    python -B reports/train_pcf_contract_reconstruction_20261022/reconstruct_full_worker.py --execute-after-audit --split VAL

v2 VAL96 schema-only 审计和 smoke：

    python -B reports/train_pcf_contract_reconstruction_val_v2_20261022/audit_val_runstart_schema.py
    python -B reports/train_pcf_contract_reconstruction_val_v2_20261022/smoke_val_v2.py

经审核的 v2 core SHA 8cc54696cc2d05e11d4e55e263b5eb9c9250f11851deb1c0b1f8719c9810f711，VAL-only worker SHA e445610c306d33c014cc7ec59fdb9168cefca0713c3019e6fd61e31d800bc962；peer manifest 与冻结 18 样本 SHA 一致。正式 VAL96 命令为：

    python -B reports/train_pcf_contract_reconstruction_val_v2_20261022/reconstruct_val_worker.py --execute-after-audit

启动时 OPENBLAS/OMP/MKL 线程数均为 1，未使用 resume。v2 worker 只接受 VAL，不能执行 TRAIN，拒绝覆写已有输出并无 resume 入口。后续任何续跑均未授权，不能从失败行继续。

正式 VAL 前预算按侧车真实 payload layout 计算；96 条数组裸尺寸 58,588,224 B，含 NPZ 头与表格/状态裕量为 127,269,952 B。旧阶段与失败尝试已有 sidecar 共 786,168,029 B；预估合并上界 913,437,981 B，低于 2 GiB。正式 VAL 实际新增 48,039,049 B；所有报告目录中的 sidecar 合计 834,207,078 B，未复制 58.6 GiB raw。

## 失败与限制

原目录 FAILURES.csv 保留全部探索/开发记录；其中正式原 VAL 在第 33 条因 HDF5 schema 路径失败，状态文件与前 32 条侧车均保留。v2 peer FAILURES.csv 保留两次 smoke 比较器仅比较 cfg/opts 来源字符串导致的中止；物理数组已相同，来源标签不属于数值契约。最终 MAT5 smoke 明确只比较物理数据和数值指标并通过。早期 smoke 脚本一度落在未带日期后缀的临时目录，第一次按正式 peer 路径调用时报“文件不存在”，没有打开数据；脚本随后移入已批准的带日期 v2 peer。smoke 结果 JSON 中遗漏日期后缀的 command 字段已更正。首次全量汇总脚本还因派生 SSE 的绝对误差 2.56e-12 停止，而对应 RMS 差仅约 1e-17；父审批准在摘要器副本中对 ratio/SSE 使用 atol=2e-12、rtol=1e-12，对计分值使用 1e-12 m 容差。这是统计复算数值守门调整，不涉及模型或阈值调优；原 c50 脚本与失败记录保留。首次 VAL 错误和所有失败记录均未通过覆盖或删除处理。

任务只做离线源数据核验、重建和固定模型 CPU 推理：0 训练、0 optimizer、0 Plant、0 GPU、0 TEST；DEV labels 未使用。MAT/H5/cache 只读，没有移动/删除原数据，没有更改控制器，也没有打断其他进程。Luna max 为用户请求，但当前工具接口没有速度档位的设置/核验能力，因此不声称实际速度档位已核验。
