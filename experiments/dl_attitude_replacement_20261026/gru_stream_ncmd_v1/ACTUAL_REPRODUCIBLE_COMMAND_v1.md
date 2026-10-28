# NCMD GRU training command — prepared, not executed

Candidate `GRU32_STREAM72_NCMD_S2026102001`. This launch is pending root review of `GRU_STREAM_NCMD_SOURCE_LOCK_v1.json` and `GRU_STREAM_NCMD_TRAINING_RELEASE0_v1.json`. Do not execute while release0 remains pending.

Run from PowerShell 7 at the project root after root approval and a no-concurrent-GPU-training check. This preserves the already verified process-local environment workaround: preload the trainer dependencies, remove `KMP_DUPLICATE_LIB_OK` only from the Python child process, execute the frozen trainer with `runpy`, retain the Python exit code, and tee stdout to a new attempt log.

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
$attemptLog = 'experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/logs/attempt01'
New-Item -ItemType Directory -Force -Path $attemptLog | Out-Null
$script = 'experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/train_gru_stream_ncmd_v1.py'
$pythonCode = "import os,runpy,sys,numpy,torch,scipy.io; os.environ.pop('KMP_DUPLICATE_LIB_OK',None); sys.argv=[r'$script','--train','--device','cuda:0']; runpy.run_path(sys.argv[0],run_name='__main__')"
python -u -c $pythonCode 2>&1 | Tee-Object -FilePath (Join-Path $attemptLog 'GRU32_STREAM72_NCMD_S2026102001.stdout.log')
$trainingExitCode = $LASTEXITCODE
exit $trainingExitCode
```

The training command is recorded for review only. It has not been run; current release authorizes zero optimizer jobs and zero Plant calls.