# Local feedback sensitivity diagnosis

Scope: fixed 200 uniformly spaced mature attitude events per each of the six frozen v3 composite logs. Recompute exact body-scale BS nominal moment and network compensation at each selected point; compare parity to recorded nominal moment/net torque before finite differences. Freeze reference, position/attitude derivatives, arm command, prior 14-event network history, beta, model, and logged `weight_before`. Perturb only current body-rate feature and the resulting nominal torque feature.

Read only the fixed prepared cfg snapshot for K1/K2/J0 and the frozen full72 MLP model. Never read or reconstruct variable Plant inertia. Use the exact `attitude_bs_step` equations, including `Tdot`, fixed Jdot0, gyro term, and output clipping. Compute BS-alone, frozen MLP, and composite with fixed logged weights; do not replay/update the head during perturbations.

Finite difference epsilon is 1e-5 rad/s; 5e-6 is a numerical consistency check only. Summaries report local `Sym(-dτ/dω)` eigenvalues, neural increment relative to BS derivative, W15/HF, axes and time windows, and outliers. This is a local frozen-memory sensitivity diagnostic, not a stability proof or Plant counterfactual.

No MATLAB, Plant execution, training, TEST read, code/config changes, or changes under v3.
