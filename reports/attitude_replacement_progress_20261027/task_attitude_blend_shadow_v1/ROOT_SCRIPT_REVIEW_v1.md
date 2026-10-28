# Root script review: task-attitude blend shadow

Date: 2026-10-27 (Asia/Shanghai)

## Decision

**Script approved for one execution under the fixed taskbook.** Approved script SHA-256:

`04119b15e4b0608ac2c2377373b529edc4de6521adb77ed040d9bd3e0f1a2544`

## Static review

- Uses only the seven whitelisted HDF5 datasets; it does not read `log/state`, arms, motors, wind, Plant parameters, or disturbance labels.
- Verifies the identity CSV, prior diagnostic result, input recheck, reviewed runner/filter/adapter/config/path-table hashes before opening any raw. Then verifies the selected 56 Candidate/C5 raw paths are contained in the project and match their locked SHA-256 values.
- Selects only W09-W14, requires the same 28 scenes for Candidate and C5, checks the full 0-20 s / 1 ms grid and exact transition alignment.
- Replays the original second-order filter from the first logged filter state and rate. It aborts unless all logged filter states/rates reproduce within 1e-8 before evaluating the counterfactual.
- Implements only beta=0.25 SO(3) shortest-geodesic interpolation, the frozen task-attitude equation, and the frozen filter parameters. It records command shift, task-to-command and task-to-filtered errors, per-scene values, tilt cap violations, and the pre-registered Candidate threshold of 58.949 mrad.
- Writes outputs only in the isolated taskbook directory, enforces the 100 MiB cap, and records abort status on failure. No Plant, MATLAB, training, B raw, or TEST path is present.

## Execution boundary

This approval authorizes exactly one offline shadow execution of the reviewed script. It does not authorize a closed-loop flight or any source/model/config change. A threshold pass only permits preparation of a separate closed-loop taskbook; it is not evidence of closed-loop improvement.
