# DL1018 仅位置闭环搜索

## 结果

- 状态：`PASS_POSITION_DEV_BEATS_B`
- 位置候选：`FEATURE`，`gamma=12`、`kappa=1`，候选 ID `POSITION_FEATURE_G12_K1`
- 编码器：复用 `DL1018_POSITION_SELECTED` 的 Final 编码器并冻结；未重新拟合编码器
- DEV：24/24 场完整、有限且稳定；新 Plant 72 次（预算 78 次）
- 等权宏位置 Q：候选 0.01517148131 m，同场 B 0.01695891840 m，改善 0.00178743709 m（10.5398%）
- 单场胜 B：11/24。整体通过不代表每一场都优于 B
- 选择只看位置 Q；姿态量仅记录。24 场是既定开发集，不是盲测

## 交付文件

- `reports/FINAL_REPORT_ZH.md`：结论、分任务汇总、24 场逐场配对及搜索组结果
- `reports/FINAL_RESULT.json`：机器可读的最终状态和锁定候选参数
- `reports/DEV_PAIRED_24.csv`：24 场候选与同场 B 配对指标
- `reports/SEARCH_ALL_RUNS.csv`、`reports/SEARCH_GROUP_SCORES.json`：搜索阶段逐场和组级结果
- `reports/PREFLIGHT_ZERO_PLANT.json`：零 Plant 预检
- `models/position_only_candidate_package.mat`、`models/candidate_manifest.json`：候选包和复现信息
- `local_runtime/`：实验运行入口及位置头实现
- `TASK_PROMPT.md`：本轮原始任务书

## 原始轨迹

72 个 `runs/**/raw_run.mat` 总计约 3.2 GB，保留在本机实验目录，未加入 Git，避免把主仓库扩成数 GB。逐场 CSV、JSON 指标、起始配置快照和资源账本已提交；报告中的 `raw_path` 指向本机原始轨迹。若需要完整原始轨迹归档，应单独使用对象存储或 Git LFS。

## 复现与重建报告

从仓库根目录运行 MATLAB：

```matlab
addpath(genpath(pwd));
run_position_only_closed_loop_search(pwd);
```

本机已有原始轨迹。该入口具备缓存续跑能力；报告和 CSV 也已作为本次交付文件提交。
