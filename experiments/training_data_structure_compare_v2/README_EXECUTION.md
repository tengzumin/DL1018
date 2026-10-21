# DL1018 训练数据与结构对照 v2

本轮的脚本、清单、派生数据、模型、运行记录和结论都保存在本目录。原合同、B、Plant、原始数据、正式输出、原 G06 与 position_causal_repair_v1 均保持只读。

## 环境与入口

- Windows 11；Python 3.12.7、PyTorch 2.6.0+cu124、CUDA 12.4、RTX 3070 Laptop GPU；MATLAB R2025b。
- Python 分析与拟合入口位于 scripts/：d0_initialize.py、d1_pcf_reconstruct.py、d2_zero_plant_audit.py、d3_output_adaptation_scale.py、d4_micro_fit.py、d4_official_fits.py、d4_wide_mlp_fit.py、d5_export_training_candidates.py、d5_analyze_bridge6.py。
- MATLAB 隔离运行入口位于 local_runtime/：d5_run_all_training_candidates 与 d6_run_history_dev。所有候选包和独立运行结果保存在本目录的 models/ 和 runs/，不写回正式模型或原 G06 报告。
- 任务书原件位于用户 Downloads；本轮按该任务书的预算、同场门槛和保护规则执行。

## 恢复与当前终态

开始或恢复任何步骤前，先读 state/state.json、RESOURCE_LEDGER.csv，以及该 identity 对应的模型、checkpoint 或 runs/<gate>/<scene>/<mode>/metrics.json。只有状态明确记录为可恢复时才可恢复同一个 identity；不要用新随机初始化冒充 resume，也不要重跑已有的 Plant。

当前状态为 D6_POSITION_DEV_COMPLETE / STOP_POSITION_NOT_QUALIFIED：48/48 条 DEV 配对均完整、有限且稳定，但 P_F、P_A 都没有通过位置资格；P_STAR 为空。因此本轮已到终态，不存在待恢复命令，不要继续训练或启动新 Plant。最终结论见 reports/FINAL_FINDINGS_ZH.md，唯一优先后续行动见 reports/NEXT_SINGLE_ACTION.md。

本轮资源上限为 80 次新 Plant，实际使用 78 次（BRIDGE6 30 次、DEV 48 次），保留 2 次余量。训练和运行 identity、步数、checkpoint、Plant 账目分别记录在 state/state.json 与 RESOURCE_LEDGER.csv。

## 保护与发布

最终保护文件复核记录在 manifests/SOURCE_AND_PROTECTION.json。推送仓库时，派生 CSV、代码、报告、checkpoint 与模型导出会纳入版本控制；可从原数据重建的大型 .npy 缓存和逐场原始 .mat Plant 快照保留在本机，由本目录 .gitignore 排除。逐场指标、完整配对 CSV、运行 identity 和资源账目会推送。
