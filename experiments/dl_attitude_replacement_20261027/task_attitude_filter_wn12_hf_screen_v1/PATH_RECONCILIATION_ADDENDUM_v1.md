# Candidate raw path reconciliation

Date: 2026-10-27

The locked cohort's `candidate_raw_path` for `DL1018_DEV_T1_C10_W09` is `runs/DL1018_DEV_T1_C10_W09/attempt_01/raw_run.mat`. The wrapper that completed the engineering gate wrote the raw to `runs/DL1018_DEV_T1_C10_W09/raw_run.mat`. The B and C5 `attempt_01/raw_run.mat` paths in the same manifest row are separate comparator inputs and are not candidate output paths.

The first raw remains at its original path; it was not moved, copied, or rerun. The produced file SHA-256 is `01f826a970865eaa2596b01866321d2341749133872d30b16d4f408c22410190`; `run_status.json` SHA-256 is `b51b6079613bf68742290fe59a69112b7c3dd6ef489446e52194c099a68163a4`; run identity and status identify the same scene, candidate, model, and produced raw SHA.

For scenes not yet run, the wrapper now reads `record.candidate_raw_path`, canonicalizes and validates that the output filename is `raw_run.mat` under this study's `runs/<same scene>/` tree, and creates the locked parent directory before the run marker. It refuses an outside-study path or a path under another scene. This changes only where future candidate outputs and their run records are placed; it does not authorize a retry or any scene.

Current ledger: MATLAB processes started 5; pre-marker failed launches 2; prepare-only runs 2; closed-loop runs 1; completed Plant calls 1. RELEASE remains DRAFT with 0 authorized calls, and the remaining 11 scenes remain unauthorized pending a separate root decision. No TEST data was read.
