# DL1018

DL1018 is the isolated formal experiment project for the V3.11/R2E contract. Its MATLAB runtime uses only files under this project; DL1009 is read only and supplies the migration reference. The contract id is `DL1018_V311_R2E_PAPER_FINAL`.

The corrected scene-reference identity, cache guards, and zero-Plant regression are documented in [the engineering note](reports/integration_next14_v1/engineering/A_CORRECTED_REFERENCE_CACHE_GUARD_ZH.md).

## Runtime

- MATLAB R2025b (`25.2.0.2998904`)
- Python 3.12.7
- PyTorch 2.6.0+cu124; CUDA available
- NumPy 1.26.4, SciPy 1.13.1, pandas 2.2.2, h5py 3.11.0

Set `MATLAB_EXE` if MATLAB is not available at the default R2025b path.

## Run and resume

```powershell
$SRC = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009'
$DST = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
Set-Location $DST

python .\run_dl1018.py --source-root "$SRC" --root "$DST" --stage G00_MIGRATION
python .\run_dl1018.py --source-root "$SRC" --root "$DST" --through G13_FINAL_REPORT --resume
python .\run_dl1018.py --root "$DST" --status
```

`--stage` enforces all earlier Gate reports. `--through` runs in the fixed order and stops on the first failure. `--resume` skips reports already marked PASS. `--status` reads reports and does not start MATLAB, Plant episodes, or training.

Each Gate report is written under `reports/`; the resumable state is `logs/gate_status.json`. The scene assignment is fixed in `configs/scene_specs.csv`, role quotas are in `configs/dataset_plan.json`, and `logs/attempt_index.csv` plus `logs/episode_index.csv` record actual runs. TEST stays sealed until its Gate.

G00 through G05 passed in this workspace. G06 stopped with `STOP_POSITION_NOT_QUALIFIED`; G07 through G13 have not started. The current detailed state is recorded in `logs/gate_status.json` and `reports/G06_P_DEV.json`. No file hash scan or manifest audit is part of this project.

## Repository contents

This repository tracks source code, configuration, tests, model exports, Gate reports, and CSV run indexes/results. The generated simulation data under `data/` (about 90.6 GB) and console/progress logs are kept local and excluded from Git. The execution task document is archived under `docs/`.
