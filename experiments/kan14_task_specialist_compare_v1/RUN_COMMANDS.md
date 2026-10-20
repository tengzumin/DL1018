# Run commands

This record describes the completed run on the DL1018 project root. The user narrowed the original two-seed prompt to seed `2026102001` only.

Run from the project root with the Python environment used by the earlier teacher-reuse KAN14 experiment:

```powershell
python experiments/kan14_task_specialist_compare_v1/scripts/prepare_cleanup.py --plan-only
python experiments/kan14_task_specialist_compare_v1/scripts/prepare_cleanup.py
python experiments/kan14_task_specialist_compare_v1/scripts/run_training.py --preflight-only
python experiments/kan14_task_specialist_compare_v1/scripts/run_training.py
python experiments/kan14_task_specialist_compare_v1/scripts/export_models.py
```

The cleanup command without `--plan-only` was run once after reviewing the per-file KEEP/DELETE manifests. Do not rerun it merely to reproduce this report: it is a deleting operation and scans the current repository state.

Four-package PyTorch/MATLAB parity was run with `local_runtime/run_kan14_task_parity.m`. The DEV24 preflight-only call was:

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "addpath('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/kan14_task_specialist_compare_v1/local_runtime'); run_kan14_task_dev24('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018',true)"
```

The 48 Plant comparison used the same command with the final argument `false`. The runner resumes from per-scene `metrics.json` or complete raw MAT evidence and refuses an ambiguous Plant marker without a raw MAT. `scripts/aggregate_results.py` builds the final CSV/JSON/Markdown comparison and marks the state complete after validating 48 runs.

No second seed, extra canary, Student collection, posture training, or TEST evaluation was run.
