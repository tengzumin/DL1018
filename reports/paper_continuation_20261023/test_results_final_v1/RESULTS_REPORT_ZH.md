# C5 TEST48 原始结果整理

## 结果

对预先登记的 48 个 TEST 场景、6 个方法的 288 条原始记录，审核器状态为 `PASS_RECOVERY288_RAW_IDENTITIES_PHYSICS_WITH_DSSM_HISTORY_DISCLOSED`；统计文件状态为 `COMPUTED_RECOVERY288_STATISTICS_WITH_DSSM_HISTORY_DISCLOSED`。父级独立汇总复算为 `PASS_INDEPENDENT_AGGREGATE_RECOMPUTATION`。C5-M110 的平均全程 Q 为 **12.155996 mm**，B_TRACEABLE 为 **18.619575 mm**；C5-M110 相对 B 为 **46 胜、2 负、0 平**。C5-M110 在高频组（high-frequency，HF W09–W14） 对 B 为 16/18 胜、2 负；W15 为 3/3 胜。分任务胜负为 T1 15/16、T2 15/16、T3 16/16；T2 对应汇报中的 16 场中 C5 胜 15 场。

按父级审核中列出的四项预设表现检查（至少 41 胜、总体均值低于 B、高频组不高于 B、W15 不高于 B），四项均通过：`{'wins_at_least41': True, 'macro_Q_below_B': True, 'HF_Q_no_larger_B': True, 'W15_Q_no_larger_B': True}`。该结果是固定仿真设计下的配对统计；`paper_result_qualified` 为 `False`，不能据此宣称论文证据门已达标。

C5-M110 对 B 的两场输场为：DL1018_TEST_T1_C14_W09（差 0.106685 mm）和 DL1018_TEST_T2_C14_W12（差 1.162507 mm）。完整的全部 comparator 输场见 `C5_M110_losses_all_comparators.csv`。1 µm 与 10 µm ties 敏感性见 `paired_sensitivity_wlt_1_10um.csv`；配对场景 bootstrap 区间直接取自冻结统计 JSON，未在本整理中重采样。

## 配对统计与复算边界

bootstrap 使用 10,000 次有放回的场景配对抽样，seed=2026102301，在每组内抽样并让各 comparator 共用索引；区间为场景等权平均配对 Q 差的 2.5% 与 97.5% quantile（`numpy.quantile of scene-equal mean paired Q differences at 0.025/0.975, method=linear`）。这些区间只描述当前固定仿真设计，不作多重比较校正，也不代表跨训练 seed 的推断。DEV72 汇总单列为上下文对照，不与 TEST48 合并。

完整长表 `paired_complete_48x6_long.csv` 保留 288 条原始审核指标及路径、SHA 和外部身份指纹；`paired_Q_48x6_wide_mm.csv` 提供 48×6 的配对主指标。`task_wind_axis_safety_saturation_timing_summary.csv` 包含任务、各风组及风组分箱上的逐方法均值，距离单位为 mm、计时单位为 ms、占比为 fraction；`axis_early_late_summary.csv` 给出全程/早段 0–5 s/后段 5–20 s 的逐轴 RMSE。图 1 标记了 C5 对 B 的两场输场；图 2 比较整体、高频组和 W15；图 3 展示 ALL48 配对区间。

## 审核限制与历史暴露披露

原始 DSSM 全 48 场进程的自然退出记录为 UNKNOWN；scene32 缺少 `runIdentity`；历史六进程 OS0 gate 为 UNMET。恢复后的 DSSM tail16 有 OS0 退出凭据，B 与 KAN/C5 恢复方法块的自然退出码为 0（B_TRACEABLE=0; CORRECTED_DSSM14_G12_R32=0 (DSSM tail16); CORRECTED_KAN14_G12_R32=0; C5_M110=0; C5_FREEZE_TRAINED_W0=0; C5_NO_DELAYED_PREDICTION=0）。因此不把全 DSSM 原运行改称 OS0，也不把历史 gate 重新分类。

历史 incident 记录称，两条旧 TEST 场景摘要曾被意外展示。该记录同时称 C5 模型与选择在本分支接触该摘要前已冻结，当前 TEST48 性能未被用于本分支选型；与当前 TEST48 的物理场景重叠 **UNKNOWN**。此处仅引用 incident 事实，未读取或复制旧混合报告的任何指标。故不声称历史上从未看到任何 TEST 信息。当前结果是已冻结 C5-M110 对这次 48 场仿真的审核统计；不构成新实机验证或跨 seed 泛化证明。C6 仍为冻结的 DEV 实验，不应依据本次两场 TEST 输场挑场或调参。

## 输入、源码与可复算命令

输入与源码 SHA-256 固定在 `INPUT_MANIFEST_v1.json`。原始审核 JSON：`3ae6d02fb36beb6690696c4b34b63106169bd98acd0fc5191140ef39329ab6a2`；统计 JSON：`d7e3af0215e159a885691c8a4ab755333b90345650afc5370b65814f9498e1a8`；父级独立复核：`5315c7cd1cbef22fff407746837c02344e8e4473602da44b9082a2f1fce95f8d`；DEV72 CSV：`3986e5ed42986c317b64fecfa508d5791709812f5c8443bf04cbce52e04a3a4c`；历史 incident：`42f1c2f672091ce46040222f1878cbf537adb647081f342a6378f353ed616c2b`。审核器源码 SHA-256：`7d81d3274801b6a33e18900c7da938d5db45c26ecd728517a585da2fbaef6495`；统计器源码 SHA-256：`679c36785a4d8cdaea0d63a70f716a123528dc39fd9a95d43912e8521f9e90b8`。

PowerShell 7 中从仓库根目录复算整理产物：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
python reports/paper_continuation_20261023/test_results_final_v1/build_test_results_final_v1.py
```

脚本会校验所有固定输入 SHA；只整理既有 JSON/CSV、做单位换算并生成图表，不调用 MATLAB/Plant、不重算评分或 bootstrap。
