# GRU32 continuous-state preparation commands

Run these from PowerShell 7 in the repository root. The first command writes a pending source lock and release0 only. The second verifies C5-only data identity, reuses the existing GRU15 full72 normalizer, and runs CPU toy checks; it does not call `optimizer.step`, Plant, TEST, or MATLAB.

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
python .\experiments\dl_attitude_replacement_20261026\gru_stream_c5_teacher_v1\train_gru_stream_c5_teacher_v1.py --prepare-release0
python .\experiments\dl_attitude_replacement_20261026\gru_stream_c5_teacher_v1\train_gru_stream_c5_teacher_v1.py --self-check
```

The single formal GPU command, for execution only after root updates both release artifacts to `APPROVED_FOR_TRAINING` with one authorized job, is:

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
python .\experiments\dl_attitude_replacement_20261026\gru_stream_c5_teacher_v1\train_gru_stream_c5_teacher_v1.py --train --device cuda:0
```

The formal command is recorded here for review; it has not been run. Do not set `KMP_DUPLICATE_LIB_OK`. A failed or interrupted run leaves its output directory in place and cannot silently restart as the same job.
