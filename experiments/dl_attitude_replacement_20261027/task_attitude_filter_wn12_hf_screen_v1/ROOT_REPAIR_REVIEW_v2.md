# Root repair review — filter wn12 engineering gate

Date: 2026-10-27 (Asia/Shanghai)
Decision: approve exactly one closed-loop engineering-gate call for `DL1018_DEV_T1_C10_W09`.

## Evidence reviewed

- Root ran `validate_filter_wn12_no_plant_v1.py`; result: `PASS_NO_PLANT_VALIDATION` for the 12 locked DEV/VAL scenes, three byte-identical DEV72 metadata files, nine shared external dependency hashes, and the 59-file runner source tree with one declared path-only adaptation. TEST remained unread and no MAT/raw/checkpoint was copied into this study.
- Root independently ran MATLAB prepare-only on the exact engineering scene. It printed `NO_PLANT_PREPARE_PASS`; it called `prepare_mlp15_dev72_no_plant` only, did not call `run_mlp15_dev72_closed_loop`, and created no attempt marker or run output.
- I reviewed the one copied runtime helper delta: `prepare_mlp15_dev72_no_plant.m` now resolves the frozen MLP15 training evidence from the existing 20261026 tree. It does not alter the trained weights, controller, filter, or Plant. The GRU checkpoint, MLP15 checkpoint, DSSM14 model, and C5 snapshot are referenced by absolute path and SHA only.
- RELEASE schema now matches the parent closed-loop runner's accepted `DL1018_GRU_STREAM_DEV_RELEASE_V1`; the candidate wrapper still binds its study ID, candidate ID, source/config/scene hashes, and explicit scene authorization.
- The earlier MATLAB launch failed before the marker due to a missing payload manifest. It is recorded in `ROOT_ATTEMPT_FAILURE_v1.md`; that authorization was withdrawn. No closed-loop transition, Plant call, raw file, or TEST read resulted.

## Limits and next gate

This is an in-sample DEV/VAL screen because the frozen GRU was trained on all 72 scenes. It cannot support independent validation or final paper claims. The engineering gate checks execution, safety counters, and raw identity; after it passes, root must independently audit its raw and metrics before releasing the remaining 11. No TEST access is authorized.

Authorized now: one scene, `DL1018_DEV_T1_C10_W09`, `ENGINEERING_GATE`, one Plant call. Remaining11, training, TEST, and other parameter changes are not authorized by this record.
