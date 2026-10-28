# Root engineering-gate review v3 — filter wn12 screen

Date: 2026-10-27 (Asia/Shanghai)
Decision: approve exactly one closed-loop engineering-gate call for `DL1018_DEV_T1_C10_W09`.

## Evidence and fixes reviewed

- Root independently ran the current `validate_filter_wn12_no_plant_v1.py`; it passed all 12 selected inputs, three byte-identical DEV72 metadata copies, nine shared external dependency SHAs, all 59 source files with one documented path-only adaptation, the single `wn` configuration delta, and DRAFT/0-Plant/TEST-false boundary.
- The previous MATLAB engineering launch failed before its marker because `jsondecode` could not index a heterogeneous `SOURCE_LOCK.files` array. The lock was normalized: every `files` record now has the same `relative_path` and `sha256` keys; the changed file's parent SHA is stored in `source_exception.parent_sha256`. Root's MATLAB preflight confirmed `isstruct(sourceLock.files)`, 59 entries, and both fields for every record.
- Root's MATLAB no-Plant prepare preflight loaded the exact engineering scene and frozen model, ran `prepare_mlp15_dev72_no_plant`, applied the locked `[12,12,12]` command-filter override, assembled GRU_STREAM/ACTIVE options, checked position-options identity and fixed J0/Jdot0, and printed `NO_PLANT_SOURCE_LOCK_AND_CANDIDATE_PREPARE_PASS`. It did not call `run_mlp15_dev72_closed_loop` or create a marker.
- The parent-runner release schema mismatch was fixed by using the accepted `DL1018_GRU_STREAM_DEV_RELEASE_V1` schema; the study wrapper still checks this study and candidate IDs. The training evidence path points to the existing frozen 20261026 tree; model/snapshot/checkpoint files are SHA-bound references and were not copied.
- The earlier two engineering launches both failed before marker/Plant and are separately recorded in `ROOT_ATTEMPT_FAILURE_v1.md` and `ROOT_ATTEMPT_FAILURE_v2.md`. The first approval was withdrawn. No closed-loop raw exists, no Plant call completed, and TEST remains unread.

## Scope and limits

The only candidate/controller delta remains `command_filter.wn=[18,18,12]` to `[12,12,12] rad/s`. This is an in-sample DEV/VAL screen because the frozen GRU was trained on all 72 scenes; it cannot be presented as independent validation or final paper evidence. Engineering-gate pass requires a stable 20,000-transition raw with matching identities and zero safety stop, motor saturation, generalized clipping, and tilt limiting. Root must audit that raw before separately releasing the remaining 11. No TEST access is authorized.

Authorized now: `DL1018_DEV_T1_C10_W09`, `ENGINEERING_GATE`, one Plant call only.
