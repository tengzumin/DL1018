# Actual GRU32 stream training command

This records the successful attempt03 command used on this Windows host. It differs from the generic `--train` template in `TRAINING_COMMANDS_v1.md`: SciPy's `threadpoolctl` sets `KMP_DUPLICATE_LIB_OK=True` during import, so the Python child imports the trainer's existing NumPy, Torch, and SciPy dependencies first, then removes that variable from its own environment before loading the frozen trainer. No system or user environment setting is changed, and the training source, parameters, and release lock remain unchanged.

Run from PowerShell 7 in the repository root:

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
$attemptLog = 'experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/logs/attempt03'
$script = 'experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/train_gru_stream_c5_teacher_v1.py'
$pythonCode = "import os,runpy,sys,numpy,torch,scipy.io; os.environ.pop('KMP_DUPLICATE_LIB_OK',None); sys.argv=[r'$script','--train','--device','cuda:0']; runpy.run_path(sys.argv[0],run_name='__main__')"
python -u -c $pythonCode 2>&1 | Tee-Object -FilePath (Join-Path $attemptLog 'GRU32_STREAM72_S2026102001.stdout.log')
$trainingExitCode = $LASTEXITCODE
```

The real attempt03 session is recorded in `logs/attempt03/TRAINING_SESSION_v1.json` (PowerShell tool session 74639, Python PID 30448). Attempts01 and 02 each exited before any optimizer step; the two tool-policy-rejected launch calls created no process. These are recorded as startup failures, not optimizer jobs. The only formal optimizer job is attempt03.

`training_config.json` and the trainer-generated `run_receipt.json` embed the original generic command template; that template was not the successful host command. Use this file and the attempt03 launch/session receipts as the execution record.
