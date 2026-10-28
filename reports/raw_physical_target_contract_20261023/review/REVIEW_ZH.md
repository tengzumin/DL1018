# 原始物理目标契约：独立审阅

**结论：数据表支持“raw 与 applied 只在旧 β<1（或饱和）时有同状态差异”，不支持 raw-only 是晚段高频问题的直接修复。** 预训练目标又是第三个独立问题：真实缓存训练用 `clip(Y,±3)`，不是 R3 XY-mask 的 `Y+M r_f`（M=diag(1,1,0)），也不是全轴 PCF 的 `Y+r_f`；真实缓存未施加 XY mask。

## 预训练目标契约

冻结导出器 `matlab/data/export_position_events_dl1018.m`（SHA-256 `4506849cc2c888e078129772e6bb1927cb479f02b75c072472778ed32d4cf094`）第44行定义 `Y`，第65–66行分别写入 `target_raw=Y` 与 `target_clip=clip(Y,±3)`。D4 cache builder（`experiments/position_causal_repair_v1/scripts/d4_sequence_data.py`，SHA-256 `7f67e51d7502290182f39a27871577a9400faa2badd5b250c28fa71f3165d43f`）第55–56、95–96行把 `target_clip` 作为 `y`、`target_raw` 作为 `raw` 保存。冻结 corrected-pair workflow（`REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1/corrected_pair_training/scripts/pair_workflow.py`，SHA-256 `a82f92465587f64f60b3c3109875a480a8ae164bf8562670808347820dbc233b`）钉住的 canonical `teacher_data.py` / `fit_models.py` SHA 分别为 `3d6ec20f544cda2ec99c3bddf17e595a75683c90fbd6b542475d006b6d2badad` / `31a08407f5b3fe66b42a7e930925e5ae4cdabfa0a764c218356eedb82ca4e9ff`；前者第41–43、87–90行直接用 cache `y` 生成窗口目标，后者第327–332行对 `pred/3` 与 `yb/3` 做全轴 SmoothL1。

因此，真实预训练标签契约是裁剪后的物理 `Y`，其 `raw` 副本没有进入该 loss；这条链中没有 `Y+M r_f` 或 `M=diag(1,1,0)` 的 XY 标签变换。已有离线重建中的 `Y+M r_f` 是 R3 XY-mask（M=diag(1,1,0)）坐标目标；全轴 PCF 的对应式为 `Y+r_f`（M=I）。被引用的旧 TRAIN 重建属于 XY-mask 方案，不是当前全轴 PCF 标签契约（见 `reports/train_pcf_contract_reconstruction_20261022/TARGET_CONTRACT_REPORT_ZH.md`）；两者与本表的延迟区间标签 `y= d̂⁻` 均不同。若研究目标要求模型监督全轴 PCF 坐标，应独立评估 `Y` 与 `Y+r_f` 的目标契约；这本身不是已证训练错误，也不能由改 raw/applied 延迟预测项解决。

## 固定 12 条同状态表

审阅输入为脚本 `raw_physical_target_contract.py` SHA `8411371afda8cffaace6efdf7584801c73bb8af0838704fd76cec80b14c6b5a6`、CSV SHA `6bedf4dfd0de290fbc930c79eccbae86367e8a2735c81f9b0606f8d0687eddda`、摘要 JSON SHA `a52d9690ff758ffe38e20435cd6d54f60442903a15357ef3dab67d815b46f501`。我未重读 raw；摘要记录 12/12 输入 SHA/stat 读前后相同，且主审另有实际 raw 独立复算。本次只读核了固定 CSV 的行键、维度、公式代码和静态来源。

CSV 恰为 504 行：21 个唯一 scope/group × 6 个 phase × X/Y/Z/ALL，无重复键。对每个窗口固定同一 `W_k`、旧 `φ_j` 与区间目标 `y=d̂⁻`，令 `z=φ_jᵀW_k`：

- `raw`: 预测 `z`、误差 `z−y`，梯度 `φ_j(z−y)ᵀ`；
- `applied`: 预测 `β_j clip(z,±3)`、误差 `β_j clip(z,±3)−y`，梯度 `φ_j[β_j m⊙(β_j clip(z)−y)]ᵀ`，其中 `m=1{|z|<3}`。

独立表级核对确认：旧 `β_j=1` 有 21,828 对、65,484 个坐标；对应 84 个 scope-axis 行的预测差、误差差、梯度差均精确为零。`CURRENT_5_20` 的 18,000 对也全为 `β_j=1` 且差异为零。全表饱和轴和精确 clip 边界均为 0。这里必须区分事件时钟：`CURRENT_18_5` 有 12 对位于当前时刻 1.80 s、但使用前一事件 `β_j<1`；表同时保留 current-time 与旧 β 分组，没有把它们误算为 β 已完成 ramp。

在旧 `β_j<1` 的 1,776 对中，ALL12 XYZ 合并 RMSE 为 raw `0.1108945`、applied `0.1040263 m/s²`；HF W09–W14 为 `0.1276539`、`0.1265259`；W15 为 `0.0639411`、`0.0290366`。这些是对固定区间物理目标的同状态描述统计，不是训练 loss、参数更新后误差或闭环因果结果。组表里的 `per_scalar_half_squared_error_mean` 明确是逐标量的 `0.5 e²` 描述均值，不是事件级向量 loss。全程没有观察到 clip 饱和，所以本批数据只实证了 ramp 语义差异，没有实证饱和语义差异。

## 对 raw-only 改法的判断

逐坐标地，若 `β_j=1` 且 `|z|<3`，则两种预测、误差和该预测项梯度完全相同。因而把新增预测项从 `β clip(z)` 改成 `z`，在此集合内不会直接改变该项的同状态梯度；固定表显示整个 `5–20 s` 高频窗口也属于此情形。ramp 期间两者确实不同，但表内应用输出对固定 `d̂⁻` 的误差在 ALL12、HF、W15 汇总都更低，raw 定义更直接表达未 ramp 的物理残差语义，但语义直接不等于控制性能更优；本表没有证据表明仅换 raw 定义便能提升控制性能。

这不能否定“新增延迟预测项”相对原控制器 tracking 更新的作用：原 Head 没有 prediction 项，本审计只比较这个拟议新项的两种输出语义，不比较有/无新项。它也不证明早段更新改变后晚段 rollout 相同；`W`、特征和闭环状态可能分叉。故建议不把 raw-only 作为晚段 HF 的首选修复；只有在明确要拟合未 ramp 的底层残差时，才把它保留为 β<1 的目标语义对照，并另行验证其更新收益。预训练 `Y` 与 R3 XY-mask `Y+M r_f`（M=diag(1,1,0)）、全轴 PCF `Y+r_f`（M=I）的目标问题应独立处置。

## 完成状态

数值 CSV/报告已写出，BOOKKEEPING_RECOVERY SHA `b86cd14a9408cf8c2aca35db4f625d529c59d8f43d5c58884c224ebdbc2c2dc8` 记载全部 504 行完成且输入未变；但正式 `--full` 进程 **exit code 1**，不是成功退出。失败只发生在写完输出后的精确字节账本断言：预估 222,387 B，实际 222,844 B，差 457 B，原因是 Windows CRLF 扩展。恢复记录未重跑、未覆盖结果。故可称数据计算完整、表可审；不可把 `SUMMARY.json` 的 `status=PASS` 单独表述为程序正常退出。