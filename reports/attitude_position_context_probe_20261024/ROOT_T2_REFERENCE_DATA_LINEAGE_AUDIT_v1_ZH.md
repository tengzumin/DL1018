# T2 参考加速度来源与 VAL 候选审计

本报告只读核对来源身份与 MAT/HDF5 scene，不运行 Plant、训练、episode、TEST，也不重生成历史数据。机器可读结果见 `ROOT_T2_REFERENCE_DATA_LINEAGE_AUDIT_v1.json` 与 `C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json`。

## T2 参考加速度差异

`DL1018_VAL_T2_C15_W09` 的 A1 B raw SHA 为 `ae0c318a69bc76e0cd64f50a708d8b768f7cc4077fcd2489e972f28e18de4bb2`；C5 `ACC_FIX_V1` physical B source SHA 为 `847b8ec237a37bc97f62b37889622bac71eaf9381a2795f5a8e64ce034fd0627`。只读比较两个 v7.3 MAT 的 `scene` 子树，唯一变化是 `reference.acceleration`。position、velocity、time、wind、arms、初态、yaw/rate/acceleration 及 scene_id 均逐位相同。加速度 shape 3×20001；Y/Z 最大差分别 0.6475885364、0.2428847958 m/s²，RMS 分别 0.2692298524、0.0937572044；X 不变。

ACC_FIX helper 将 FIG8 参数曲线二阶项从 `puu_y=-8π²sin(2θ), puu_z=2.8π²cos(2θ)` 修为 `puu_y=-16π²sin(2θ), puu_z=5.6π²cos(2θ)`。`p_y=sin(2θ)` 且 `θ=2πu`，所以旧的 Y/Z 二阶系数都少一倍。按 `a=puu(du/dt)^2+pu(d²u/dt²)` 独立复算，实际原/fixed scene 的最大残差分别小于 6.9e-15 和 1.4e-14。preflight 明确仅允许 FIG8 的 `reference.acceleration` Y/Z 变化，并分别核对旧/新 helper。

原 TRAIN T2 也有同一缺陷：实际 `DL1018_TRAIN_T2_C00_W00` 原始 B raw 符合旧 helper；对应 corrected TRAIN B raw 符合 fixed helper，scene 字段集合相同，唯一差异仍为 `reference.acceleration`。这来自共享 FIG8 scene generator，不是单个 VAL 场景。修正会改变闭环参考输入，因而可能改变教师轨迹；不能说成仅修离线标签。

## Corrected TRAIN 可复用候选

`G3_D4_CACHE_INDEX_1632.csv` 记录 corrected T2 FIG8 TRAIN 512 条：256 B 与 256 POS_OFF；506 条 `RUN_COMPLETE_STABLE`，6 条 `PILOT6_VALIDATED`。raw、run_start、event H5、cache 路径均 512/512 存在。完整重建表 `TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv` 对 T2 512 条全部 PASS，cache identity、raw hash 前后相同、sidecar 存在也均为 512/512；整体 TRAIN 重建状态为 `PASS_TRAIN_1536`。因此已有完整 corrected T2 数据候选，不应先假设需要重采 B256。

已抽查 corrected TRAIN 的真实 raw H5 标签字段：`attitude_event_flag` (1×20000, 1999 events)、`attitude_bs_nominal_torque_Nm` (3×20000)、`attitude_compensation_applied_torque_Nm` (3×20000)、`requested_generalized`/`realized_generalized` (各4×20000)、`wind_torque_B` (3×20000)、`state` (12×20001)、`time` (1×20001)，全部有限。因此这条 raw 含 X18/物理标签需要的通道；位置 fixed-model sidecar 不代替这些 raw 信号。

MATLAB R2025b `-batch` 只读加载 corrected `T2_C00_W00_B` run_start（SHA `99e686d7eb387d1d97773f5f0e07fa8c8b9623029fc185949322be688b7b6bc8`）与 C5 snapshot（SHA `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a`）。`isequaln(snapshot.cfg,runStart.cfg)` 为 true；formal RBF、attitude 100 Hz、两个 phase start、gamma=19、attitude enable/output/update 与 v1_adaptive 共 9 个 shared opts 逐值相同。这仅是一条 corrected TRAIN run_start，不替代对 C5 VAL 运行 cfg/opts 的逐场核验。

## 48 VAL 候选边界

候选 manifest 逐场列出 A1 B raw、C5 physical B source、C5 teacher raw/run_start、SHA、来源动作和已有审计状态。准确分类为 **32 个 B source SHA 与 A1 相同，16 个 T2 `ACC_FIX_V1` B source SHA 不同**；48 个 C5 teacher 由 36 个 DEV72 新 run 与 12 个 SCREEN12 reuse 组成。C5 父审计 `event_count=1968` 是有效位置推理事件数，不是姿态事件数。

48 场 C5 candidate 的 raw/start cfg/opts 与 `raw.scene` 数值认证仍待完成。16 个不同 SHA 的 T2 alias 中目前只有 C15_W09 做过字段级 HDF5 对照，其余 15 个待核。32 个相同 SHA 只证明 B source bytes 一致，不能自动证明 C5 result raw/start cfg/opts 与当前 snapshot 完全一致。正确参考输入和新训练协议仍由 ROOT 决定；候选 TRAIN 缓存需按选择的 C5 teacher 和标签合同重导/验证，VAL 不得用于训练。这里没有放行采集或训练。
