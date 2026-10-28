# Offline C5 RBF local-reference diagnosis

Reconstruct the frozen C5 attitude RBF from zero weights by replaying existing raw events in original output-before-update order with the locked `rbf_mimo_basis` and `rbf_mimo_update` equations. First validate one scene against all event `output_unclipped`, clipped raw output, basis norms, weight norms/derivative norms, and the first eight stored weight snapshots. Expand to six scenes only after parity passes.

Then use 200 uniformly spaced mature events per scene for same-state local torque Jacobians: actual RBF with replayed `W_before`, fixed BS, and hypothetical frozen full72 MLP on the same C5 states/history. MLP-on-C5 is an offline hypothetical, not a logged flight. Freeze state/reference/history/weights; use eps=1e-5 and 5e-6 only as derivative consistency checks.

Read only fixed J0/K1/K2 and RBF attitude settings. Never read/reconstruct Plant inertia or variable morphology. No MATLAB, Plant, training, TEST, source/config writes, or modifications under C5/v3.
