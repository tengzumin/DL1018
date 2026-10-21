# 运行与恢复

使用 MATLAB R2025b 的独立 `-batch` 进程，不启动重复任务。所有格子的 `run_status.json` 与 `RESOURCE_LEDGER.csv` 写在本实验目录。

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "addpath('experiments/old_kan_fig8_transfer_compare_v1/scripts'); run_zero_plant_preflight(pwd);"
```

只有 `reports/ZERO_PLANT_PREFLIGHT.json` 为 PASS 才可执行：

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "addpath('experiments/old_kan_fig8_transfer_compare_v1/scripts'); run_old_kan_transfer_experiment(pwd);"
```

恢复前先检查 `state/state.json`、每格 `run_status.json`、raw 与账本。如果 Plant 已标记开始而无完整原始结果，记作待人工核查且禁止自动重跑该格。当前没有设置定时自动化；由当前 Codex 对话检查并汇报。
