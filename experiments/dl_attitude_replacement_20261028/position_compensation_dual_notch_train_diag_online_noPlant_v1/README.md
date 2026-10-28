# W09 dual-notch online helper and no-Plant parity

This is an independent implementation-preparation study for a fixed W09 mechanism diagnosis. The frozen replay that motivated it remains **FAIL**: high-band command-target power fell strongly, but low-band action-change exceeded the unchanged 2% limit on both scenes. The prior result is preserved; this folder does not revise its threshold or filter parameters.

The MATLAB helper applies two causal, unity-DC biquad notch sections (2.2 Hz and 3.2 Hz, Q=4, 100-Hz event rate) to the final stage-1 applied acceleration, after the C5 and residual-GRU actions are combined and before force injection. It holds output between stage-1 events and preserves the first nonzero event sample through steady-state initialization. It retains the ±3 m/s² limit.

`prepare_matlab_parity_inputs.py` binds only the current candidate raw files recorded by the frozen TRAIN replay report and produces `DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat` with expected action sequences from the frozen Python recurrence. The standard `MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat/json` names remain reserved for the fold-model parity inputs used by the full runner no-Plant preflight. `matlab/run_dual_notch_no_plant_parity_v1.m` runs the online MATLAB helper over the dual-notch arrays and records parity plus the measured baseline Q/task values. It does not invoke a runner or Plant. The intervention's closed-loop Q/task remain explicitly unmeasured until a separately authorized closed-loop falsification run.

Integration anchor for a future isolated runner copy: execute the helper inside the stage-1 event block **after** residual-GRU final action/clipping is assigned and **before** `dF=stage1PositionHeldForce` and `position_bs_step(...)`. Existing 3.5-Hz/Q1 code in the current runner is upstream of the residual-GRU block, so it is not reused as-is.

Run from the repository root:

```powershell
python experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_online_noPlant_v1/prepare_matlab_parity_inputs.py
matlab -batch "addpath('experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_diag_online_noPlant_v1/matlab'); run_dual_notch_no_plant_parity_v1"
```

No Plant, TEST, VAL, or inertia reconstruction is part of this preparation.
