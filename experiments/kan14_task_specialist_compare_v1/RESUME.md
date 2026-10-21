# Resume and status guide

The authorized experiment is complete for the single seed `2026102001`. Do not launch another seed unless the user changes this instruction.

## Status files

- `state/state.json`: overall phase and completed-run/Plant counters.
- `reports/DEV24_PROGRESS.json`: paired DEV progress and latest scene result.
- `reports/DEV24_PAIRED_RESULTS.csv`: one row for each completed policy/scene run.
- `runs/<policy>/<scene>/metrics.json`: accepted result for a scene.
- `runs/<policy>/<scene>/run_start.mat`, `plant_started.marker`, and `raw_run.mat`: run identity and raw evidence.

The final state is 48/48: 24 shared-model runs and 24 task-routed expert runs. All 48 are stable, finite, complete, and have 20,000 transitions. The same-scene B raw data are reused; no TEST data are read.

## If an interruption occurs before completion

1. Check the MATLAB process list before doing anything. If `run_kan14_task_dev24` is active, do not start another instance.
2. Read `state/state.json`, `reports/DEV24_PROGRESS.json`, and the relevant scene directory. Preserve all existing raw files.
3. The runner skips a scene with a complete `metrics.json`, and it can recover a complete `raw_run.mat` plus `run_start.mat` without starting another Plant run.
4. If a `plant_started.marker` exists without `raw_run.mat`, or an `error.json` exists without raw evidence, stop and inspect the specific scene before resuming. The runner intentionally refuses to repeat that Plant scene automatically.
5. After reviewing the scene evidence and confirming no matching MATLAB process is active, run the same one-seed command recorded in `RUN_COMMANDS.md` with the final argument `false`.
6. When the run reaches 48/48, run `python experiments/kan14_task_specialist_compare_v1/scripts/aggregate_results.py` to regenerate the paired summaries and final report.

Do not remove failed or weak DEV scenes from the paired analysis. Keep TEST sealed and do not initiate Student acquisition, another model screen, fusion, or distillation as part of this task.
