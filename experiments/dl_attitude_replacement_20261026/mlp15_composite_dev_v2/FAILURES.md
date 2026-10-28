# Implementation failure log

- MATLAB no-Plant capture PID 25900 exited before prepare because `prepare_mlp15_dev72_no_plant` was not on the MATLAB path. The runtime path was then added and `activate_paired_runner` was called before the successful capture attempt. No Plant call or attempt marker was created.
- MATLAB no-Plant capture PID 35468 passed all checks and wrote `audits/NO_PLANT_CHECK_v2.json` plus `LOCKED_CFG.json`, then exited with code 1 during `RELEASE.json` assembly because the MATLAB struct supplied `TEST_read` twice. The duplicate field was removed from the saved audit source; the executed script is preserved as `audits/audit_composite_dev_no_plant_capture_v1.m`. No Plant call or attempt marker was created.
- PowerShell 7 release finalization assembled a zero-budget `PREPARED_ROOT_REVIEW_REQUIRED` release from the passing report and captured cfg. Several optional status/report annotations used property assignment on JSON properties that did not exist and emitted `SetValueInvocationException`; the `RELEASE.json`/`RELEASE_RECORD.json` assembly completed, but the implementation status may lack those optional annotations. Root will set final release fields after review.

All recorded attempts kept `authorized_Plant_calls=0`; training and TEST were not started/read.
