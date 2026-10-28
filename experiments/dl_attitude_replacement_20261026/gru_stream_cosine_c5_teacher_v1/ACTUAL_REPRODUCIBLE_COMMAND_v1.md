# Actual reproducible command — cosine GRU stream

Candidate: `GRU32_STREAM72_COSINE_S2026102001`.

Status: prepared only. Do not run until root approves the cosine source lock/release. The command preserves the previously proven Windows process-environment workaround: PowerShell sets the locked math-library variables; Python imports the trainer's existing NumPy, Torch, and SciPy dependencies first, then removes `KMP_DUPLICATE_LIB_OK` only from its own child environment before executing the unchanged frozen trainer with `runpy`. No user/system environment mutation is used.

Run from PowerShell 7 at the repository root after root approval and a no-concurrent-GPU-training check:

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
$attemptLog = 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_c5_teacher_v1/logs/attempt01'
New-Item -ItemType Directory -Force -Path $attemptLog | Out-Null
$script = 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_c5_teacher_v1/train_gru_stream_cosine_c5_teacher_v1.py'
$pythonCode = "import os,runpy,sys,numpy,torch,scipy.io; os.environ.pop('KMP_DUPLICATE_LIB_OK',None); sys.argv=[r'$script','--train','--device','cuda:0']; runpy.run_path(sys.argv[0],run_name='__main__')"
python -u -c $pythonCode 2>&1 | Tee-Object -FilePath (Join-Path $attemptLog 'GRU32_STREAM72_COSINE_S2026102001.stdout.log')
$trainingExitCode = $LASTEXITCODE
exit $trainingExitCode
```

The trainer's `training_config.json` and final `run_receipt.json` will embed this command template. The per-update applied learning rate is recorded on every JSONL history row as `learning_rate_step` and `learning_rate`.
