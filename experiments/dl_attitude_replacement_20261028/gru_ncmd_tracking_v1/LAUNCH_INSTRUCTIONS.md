# NCMD tracking trial launch

Run MATLAB from the new study root and add both the study root and isolated runtime directory. The runtime path is required to resolve `prepare_gru_ncmd_tracking_no_plant`.

```matlab
studyRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/dl_attitude_replacement_20261028/gru_ncmd_tracking_v1';
cd(studyRoot);
addpath(fullfile(studyRoot, 'candidate_runner_work', 'matlab', 'runtime'), '-begin');
addpath(studyRoot, '-begin');
run_gru_ncmd_tracking_attempt('DL1018_DEV_T1_C10_W09');
```

To resume the fixed screen, call `run_gru_ncmd_tracking_screen()` from the same MATLAB session after those `cd`/`addpath` lines. It skips matching completed scenes and stops on an incomplete or mismatched attempt.

After a scene completes, score the current partial results with:

```powershell
python experiments/dl_attitude_replacement_20261028/gru_ncmd_tracking_v1/audits/score_ncmd_tracking_v1.py --tag partial01
```

Use a new `--tag` for each score; existing score files are never overwritten. The scorer compares the NCMD candidate with the parent cosine-GRU tracking run, B, and C5 using the frozen FULL72 metric scorer. It reports both ID-based wind strata and zero/nonzero wind groups read from each candidate raw MAT. The source GRU was trained on DEV24+VAL48 development data, so this screen does not provide independent validation.
