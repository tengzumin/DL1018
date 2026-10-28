# Offline diagnostic execution receipt

All runs used PowerShell 7 (`pwsh`) in the repository root and the Anaconda Python interpreter. Threading variables were set only in the invoking PowerShell process. No training/optimizer job, new Plant run, TEST access, or persistent environment change occurred.

## Final open-loop run

Command:

```powershell
$env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_THREADING_LAYER='SEQUENTIAL'; & 'C:\ProgramData\anaconda3\python.exe' -u 'experiments/dl_attitude_replacement_20261026/ncmd_label_predictability_diagnostic_v1/diagnose_ncmd_fit_v1.py'; $code=$LASTEXITCODE; Write-Output "PYTHON_EXIT=$code"; exit $code
```

- Successful final tool session: `69754`; Python exit code `0`.
- Printed status: `PASS_HISTORICAL_C5_OFFLINE_DIAGNOSTIC`.
- 13,005 per-scene metric rows, 4,335 per-scene lag rows; group summary has pooled and scenario-macro metrics.
- Python source SHA-256: `bfe0fa0861a4803705b58d08b8c94ea668260c99e13dda180bb098d966791249`.

## Final self-closed-loop run

Command:

```powershell
$env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:MKL_THREADING_LAYER='SEQUENTIAL'; & 'C:\ProgramData\anaconda3\python.exe' -u 'experiments/dl_attitude_replacement_20261026/ncmd_label_predictability_diagnostic_v1/diagnose_ncmd_on_policy_v1.py'; $code=$LASTEXITCODE; Write-Output "PYTHON_EXIT=$code"; exit $code
```

- Successful final tool session: `49595`; Python exit code `0`.
- Printed status: `PASS_OFFLINE_SIX_RAW_DIAGNOSTIC`.
- 225 scene/group/axis metric rows and 35,982 event/axis rows; all six existing raw/status/audit identities and per-event model replay checks passed.
- Python source SHA-256: `3c03664fc0d058d22a61f681fefc5e59caa8b3d44a30ddeca8629f50b43e5e91`.
- Root independently rebuilt all six 1 ms residual sequences and 10 ms targets with maximum absolute error `5.98e-13`; review file: `ROOT_ON_POLICY_TARGET_REVIEW_v1.json`.

## Attempt note

An earlier open-loop attempt exited `1` at the root-path assertion before any array was opened; the traceback was `FileNotFoundError` for an incorrectly resolved feature NPZ path. The script's repository-root calculation was corrected, then the successful commands above ran. No source outside this new diagnostic directory was changed.
