# C1 v9 首场 raw-event 独立复核

**结论：PASS。** 只读 h5py 选取两条新 raw 的小型事件/PCF数组；没有运行 Plant，也没有读取或改写运行源码。复核脚本为 [verify_probe_event_contract.py](verify_probe_event_contract.py)，数值结果保存在 [probe_event_contract_review.json](probe_event_contract_review.json)。

核验对象是 `DL1018_VAL_T2_C00_W10` 的 ON1 和 ONC。两条 raw 的 SHA-256 分别为 `2377ee61ec67f15012256502e28f008c26b61af78d0964995ec2f2d8678e854e` 与 `311a4292f97198c387bd1548cece83ba616ddff52e09200935e44cbea5deca42`；读取前后 SHA、大小和修改时间均一致。v9 release、source lock、runner 以及锁定的 Head/runtime/PCF源码哈希也逐一匹配。

两条运行各有 1,968 个有效 Head 事件。MATLAB 一基 `event_step_index` 映射到 HDF5 第 `k−1` 列；这些索引与 readiness=32 后的 scheduler event 逐项一致，覆盖 step 321–19991、`transition_time` 0.32–19.99 s。Plant 步长约 1 ms，Head 事件及其有效更新步长约 10 ms。记录的 β 与 `clip(t/1.8,0,1)` 完全一致，范围 0.1777778–1；γ=12，β 与更新步长缩放均为 1。

原始 `W0` 的 MATLAB F-order double SHA 与冻结模型身份一致；ON1 初值等于 `W0`，ONC 初值等于 `0.2802979648061464·W0`，最大元素差均为 0。φ 范数为 1（浮点误差内）。逐事件重算 `raw=W_beforeᵀφ`、`applied=β·clip(raw,±3)` 与完整离散更新

`W_after = clip_[−60,60](W_before + dt_eff·(−12β φ s_effᵀ − 0.002W_before))`

均与 raw 记录相符：raw/output 最大误差分别不超过 `4.45e−16`，更新最大误差为 0；投影事件和输出限幅命中均为 0，事件权重链、首末矩阵也精确衔接。

PCF 事件逐元素满足 `s_coord=s_original−η_before`、`s_eff=clip(s_coord,±[7,8,10])`。当前事件使用本步的 `η_before`，且所有 1,968 个事件的 Z 轴 `s_eff` 非零，Z 权重均有非零更新。全 20,000 个 Plant 步上 `r_f=a_req−a_f` 精确，重算 η 的完整离散递推最大误差分别为 `3.01e−15`（ON1）和 `1.24e−15`（ONC）。

时序边界：每步先用当前 φ 和 `W_before` 生成 Head 输出/更新，使用本步开始时已有的 PCF `η_before`；位置请求与当前滤波姿态随后产生，PCF 再推进 η，供下一步使用。该核验确认实现、索引和日志在各自闭环轨迹上相符；它没有把同一闭环轨迹上的相关性解释为 Head 的独立因果贡献，也不证明闭环性能改善。
