# C4 cross-language Python precheck

Created 2026-10-23. All commands ran from `C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018` in PowerShell 7 (`login=false`). Each command returned process exit code `0`.

| Command | Result |
|---|---|
| `python -B 'reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py'` | `PASS_SYNTHETIC_SINGLE_STEP_ONLY`; max gradient finite-difference error `1.8828050230013105e-11` |
| `python -B 'experiments/position_coordinate_c4_20261023/c4_coordinate_synthetic_check.py'` | `PASS_SYNTHETIC_NO_PLANT`; m=0 target `[0.6675499999999898, -0.2649000000000003, 0.5324500000000005]` |
| `python -B 'experiments/position_coordinate_c4_20261023/c4_coordinate_fixture_v1.py'` | `FIXTURE_GENERATED`; 4 events over 11 transition rows |

The generated fixture SHA-256 is `1306fa797179380d86df4a93deb0594f2f2e99a920d8eeb68aef0957044181a0`. The untouched MATLAB helper SHA-256 is `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`.

New source SHA-256 values: fixture generator `69330e2d325cc28866d51f018d49bb7f953c0fe68c948d9cf91eab65743af011`; MATLAB synthetic checker `ab2b772e53046aa32b3c60395ef3b247d96aca5c9e45ff988acc28be8838eca3`.

The C4 core (`run_dl1018_closed_loop.m`), wrapper (`run_episode_dl1018.m`), preparation and runner files, frozen input lock, and prediction helper retained their recorded SHA-256 values. MATLAB has not been started; this report covers Python checks only. The cross-language synthetic result is pending source/command review.
