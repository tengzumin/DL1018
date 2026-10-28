# Closed-loop force09 actual-wind group erratum

Date: 2026-10-27

The force09 scorer previously classified `NO_WIND_W00` and `LOW_WIND_W01_W08` from the scene-ID `wind_index` (`audits/score_closed_loop_v1.py`, former lines 279–280) and described those suffixes as measured wind groups (former line 381). That is not supported by the raw inputs.

The independent raw-field audit at `experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/closed_loop_force09_v1/audits/FORCE09_ACTUAL_WIND_CLASSIFICATION_AUDIT_v1.json` reads only each authorized DEV/VAL raw's `scene/environment_wind_I`, and verifies each raw SHA against its `run_status.json`. It finds 3 exact-zero wind scenes and 9 nonzero-wind scenes. All three scenes labeled W15 have an exactly zero wind field; the nine nonzero scenes have peak vector speeds from 11.4889 to 17.0000 m/s. Scene suffixes therefore do not classify actual wind for this cohort.

The current scorer now emits `ACTUAL_NO_WIND_RAW` for exact-zero raw wind and `ACTUAL_NONZERO_WIND_RAW` otherwise. It no longer calls W01–W08 “low wind” based on scene ID; it makes no separate low-wind claim. `scene_index_group` remains available for the existing HF/W15/W00–W08 scene cohort summaries. The metric functions, per-scene metrics, and paired score calculations are unchanged. Existing score files and raw data remain untouched; this note corrects only the interpretation of wind subgroup labels. The scorer has not been run as part of this correction.
