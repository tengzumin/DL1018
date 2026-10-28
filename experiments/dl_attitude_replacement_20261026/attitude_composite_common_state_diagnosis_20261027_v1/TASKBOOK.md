# Common-state composite-head diagnosis v1

Objective: replay the six frozen v3 raw logs on their recorded state/feature/torque histories, compare prediction-only and composite-head one-step residual predictions, and attribute the head update to RLS versus tracking. This is a fixed-record shadow analysis, not a closed-loop counterfactual.

## Inputs and scope

- Read only the six `mlp15_composite_dev_v3/runs/*/raw_run.mat` files, their locked audit reports, the released full72 MLP model, `LOCKED_CFG.json`, and `ROOT_SIX_PYTHON_METRICS_v1.json`.
- Reuse the independent raw-auditor observation, feature, T/surface, forward model, Joseph RLS, tracking, projection, and replay semantics. Verify composite replay against the real trace before aggregating.
- Generate paired metrics CSV and all candidate-loss rows from root's six-scene Python metrics JSON.
- Report by W15/HF family, roll/pitch/yaw output axis, beta ramp/mature phase, and first/middle/last five seconds. Include P trace/diagonal extrema and tracking-to-RLS weight-increment norm ratio.

## Boundaries

No MATLAB, Plant, training, TEST, parameter sweep, controller runner, inertia reconstruction, or modifications under v3. The state/action sequence remains the observed composite flight trajectory; prediction-only shadow results do not represent a simulated prediction-only closed-loop flight.
