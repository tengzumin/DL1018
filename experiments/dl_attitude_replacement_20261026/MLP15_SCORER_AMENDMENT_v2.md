# MLP15 scorer amendment v2

The v2r scoring output is preserved at pilot_score_mlp15_v2r/pilot_score.json. It reports SCORER_ERROR for all six rows and is not a metric result. Root cause: score_log assigned the MLP event cell array to a local variable named trace, then attempted trace(D) for SO(3), shadowing MATLAB's matrix-trace function. The failure occurred after raw files were read but before a score row was completed. No Plant call or raw modification occurred.

The v2s scorer renames the event variable to mlpTrace, leaving trace(D) to call MATLAB's built-in function. It retains the v2 candidate release, v2 taskbook, six original raw files, identity checks, metrics, tolerances, and acceptance criteria. No candidate run is repeated.