# Engineering gate launch failure 2 — pre-marker lock parsing

The fresh one-call engineering-gate launcher started MATLAB for `DL1018_DEV_T1_C10_W09`. The candidate wrapper stopped in `verify_release_inputs` while reading `SOURCE_LOCK_v1.json`: MATLAB `jsondecode` represented the heterogeneous `files` array in a form that does not support the wrapper's `lock.files(i).relative_path` struct indexing.

Observed state:
- MATLAB process started; exit code 1.
- Failure occurred before `attempt_started.marker`, `run_start.json`, or `run_mlp15_dev72_closed_loop`.
- No closed-loop transition, raw, safety counter, or Plant call occurred. `Plant_calls_completed=0`.
- TEST was not read and no historical artifacts were modified.

Classification: wrapper/source-lock JSON shape incompatibility. The engineering authorization has been withdrawn. Fix the lock shape or parser, rerun no-Plant validation and MATLAB prepare-only, then require a fresh root review before another launch.
