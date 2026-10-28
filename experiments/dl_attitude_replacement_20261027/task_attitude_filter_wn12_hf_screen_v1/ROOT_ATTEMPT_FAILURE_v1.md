# Engineering gate launch failure — pre-Plant

At 2026-10-27 local time, the authorized PS7 launcher started one MATLAB process for `DL1018_DEV_T1_C10_W09`. MATLAB stopped before the attempt wrapper created an attempt directory or invoked the closed-loop runner. Error: `prepare_mlp15_dev72_no_plant` could not read the study-root file `MLP15_DEV72_PAYLOAD_MANIFEST_v2.json`.

Observed state afterward:
- MATLAB exit code: 1.
- No `runs/` directory, attempt marker, `run_start.json`, `raw_run.mat`, or scene status was created.
- `Plant_calls_completed` remains 0; no 20,000-transition Plant simulation ran.
- TEST was not accessed. No previous experiment or raw was changed.

Classification: isolated-runner packaging/dependency-lock defect, not a controller outcome. Authorization has been withdrawn. Do not retry until the missing preparation dependencies and hashes are included in this study, the no-Plant validator passes, and root issues a fresh one-call engineering-gate release.
