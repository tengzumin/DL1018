# DL1018 位置退化诊断：执行与恢复说明

## 结果状态

- 阶段：D0–D5 已完成；D5 候选均未达到位置门槛；D6 未启动。
- 原正式 gate：`G06_P_DEV=STOP_POSITION_NOT_QUALIFIED`；G07–G13 未启动且未由本实验更改。
- 资源：新增 Plant 20、encoder fit 4；D5 的 18 Plant 上限及全任务 80 Plant/6 fit 上限均未超。
- 当前没有本实验的 Python 训练、`run_dl1018.py` 或 MATLAB 仿真进程。

## 实验目录

所有新脚本、临时 MATLAB 隔离副本、模型候选、原始 D3/D5 桥接产物、分析表和报告均保存在 `experiments/position_causal_repair_v1/`。未修改 DL1018 正式模型、配置、日志、gate 报告、原始数据或正式 MATLAB 运行链。`manifests/SOURCE_AND_PROTECTION.json` 记录 D0 基线 SHA-256 和只读边界；最终复核见 `reports/FINAL_PROTECTION_CHECK.json`。

GitHub 上传范围记录在 `manifests/GITHUB_UPLOAD_SCOPE.json`：提交包含代码、文档、CSV、JSON 指标、图和小型候选模型包；不包含原始 Plant `raw_run.mat`、MATLAB 工作区快照、D4 `.npz` 大缓存、Python bytecode 或运行标记。大文件仍保留在执行电脑的实验目录，完整原始轨迹复算依赖该本地目录。

## 环境

- Windows 11
- Python 3.12.7（Anaconda）
- PyTorch 2.6.0+cu124，CUDA 12.4；NVIDIA GeForce RTX 3070 Laptop GPU
- MATLAB R2025b（25.2.0.2978516）
- Git 初始 HEAD：`12bce70c5f69fd5055bc6cf798303cf2c6d80050`，分支 `main`

## 关键入口

离线阶段和训练入口（仅作可复现记录；D4 命令会实际训练）：

```powershell
python experiments/position_causal_repair_v1/scripts/d1_pair_analyze.py
python experiments/position_causal_repair_v1/scripts/d2_signal_analysis.py
python experiments/position_causal_repair_v1/scripts/d3_bridge_analyze.py
python experiments/position_causal_repair_v1/scripts/d4_train_candidates.py --family C1_X20_FIXED_INFORMATION --seed 2026101901
python experiments/position_causal_repair_v1/scripts/d4_train_candidates.py --family C1_X20_FIXED_INFORMATION --seed 2026101902
python experiments/position_causal_repair_v1/scripts/d4_train_candidates.py --family C2_X14_ADAPTATION_AWARE --seed 2026101901
python experiments/position_causal_repair_v1/scripts/d4_train_candidates.py --family C2_X14_ADAPTATION_AWARE --seed 2026101902
```

D2 实际运行链重放的 MATLAB 入口为 `d2_runtime_replay_and_decompose(root)`，只读旧日志，不调用 Plant。D3 六场 Plant 入口为 `d3_run_final_bridge6(root,'run')`；D3 已完成，切勿重复调用。D1/D2/D3 的部分入口会重写实验目录内的派生报告或缓存，复跑前应先检查脚本和当前 state。**不要为了恢复本次工作而重新执行 D5：它已完成，重新调用可能再次运行物理仿真。**也不要运行正式 `run_dl1018.py`、D6 或 G07–G13。

D2/D3 的完整 MATLAB batch 调用形式（供审计，勿重跑 D3）：

```powershell
matlab -batch "root=pwd; addpath(genpath(fullfile(root,'matlab'))); addpath(fullfile(root,'experiments','position_causal_repair_v1','local_runtime')); d2_runtime_replay_and_decompose(root);"
matlab -batch "root=pwd; addpath(genpath(fullfile(root,'matlab'))); addpath(fullfile(root,'experiments','position_causal_repair_v1','local_runtime')); d3_run_final_bridge6(root,'run');"
```

D5 物理评估入口是实验目录内 `local_runtime/d5_run_candidate_bridge6.m`，MATLAB 函数签名为：

```matlab
d5_run_candidate_bridge6(root, 'C2')
d5_run_candidate_bridge6(root, 'C1')
```

任务按冻结顺序先 C2 再 C1 分别调用入口，依赖各自 `D5_PREFLIGHT_*.json` 为 PASS。D5 已执行完；以上只用于审计入口，不是重跑指令。两次 C1 路径初始化失败和最终六场结果都保留在 `runs/`、`RESOURCE_LEDGER.csv`、`reports/D5_CANDIDATE_DECISION.md`，没有覆盖原正式运行文件。

从仓库根目录启动的历史调用形式如下（当前结果已完成，勿再次执行）：

```powershell
matlab -batch "root=pwd; addpath(genpath(fullfile(root,'matlab'))); addpath(genpath(fullfile(root,'experiments','position_causal_repair_v1','local_runtime')),'-begin'); d5_run_candidate_bridge6(root,'C2');"
matlab -batch "root=pwd; addpath(genpath(fullfile(root,'matlab'))); addpath(genpath(fullfile(root,'experiments','position_causal_repair_v1','local_runtime')),'-begin'); d5_run_candidate_bridge6(root,'C1');"
```

## 结果索引

- 最终结论：`reports/FINAL_CAUSAL_REPORT_ZH.md`
- 假设判定：`reports/CAUSE_STATUS_AFTER_BRIDGE.md`
- D2 残差/适应机制：`reports/D2_SIGNAL_MECHANISM.md`
- D5 单条同场候选对比：`reports/D5_CANDIDATE_DECISION.md`
- D3 Initial/Final 六场桥接：`reports/D3_INITIAL_FINAL_BRIDGE.md`
- 资源账本：`RESOURCE_LEDGER.csv`
- 可保护文件指纹复核：`reports/FINAL_PROTECTION_CHECK.json`
- 最终状态机：`state/state.json`
