# Root taskbook v1: MLP15 trained on legal nominal attitude residuals

Date: 2026-10-27
Owner: root (design, source/data review, release decision)
Executor: GPT-6-Luna xhigh (implementation and offline work)
Phase authorized here: isolated implementation, one training run, offline evaluation, and no-Plant validation only.

## Question

Can a frozen MLP15 attitude model trained to predict the past-only fixed-J0 nominal dynamics residual provide a better RBF replacement than imitation of the RBF output, while preserving the WN18 position path?

This is a single-factor model-target study. It is not a claim of a new learning algorithm or a closed-loop result.

## Frozen design and single change

Use the existing MLP15 attitude architecture and the causal-head v1 implementation as the parent reference. Preserve the 13 legal per-event inputs, 15-event history, input normalization procedure, model width/depth/activation, optimizer, training schedule, fixed random seed 2026102001, online causal RLS update, output clipping, beta ramp, and controller integration. Restore the shared command filter to WN18 [18,18,12] rad/s. Preserve C5 DSSM14/M110 and its online head, BS, C0/J0, actuator, Plant, and safety settings.

Change only the supervised attitude output target from the C5 RBF output label to a physically measured, past-only fixed-J0 nominal-model residual. The residual label must be constructed from logged body-rate, timestamps, and the already-issued controller body torque over the preceding event interval:

r_k = mean[ J0^-1 * ( J0 * omega_dot + omega × (J0 * omega) - tau_issued ) ].

Before training, independently verify units, coordinate frame, sign relative to the deployed torque subtraction, sample endpoints, and that every label uses measurements and commands available no later than its feature timestamp. If the existing locked causal-head v1 trainer does not make the training and validation split explicit, inspect its sources and stop for root review before using data.

Output target RMS/normalization may be recomputed from the approved training split only and must be recorded. Do not tune hyperparameters or select among seeds. Run exactly one training configuration, at most 60,000 optimizer steps, seed 2026102001. No teacher-label blend, tracking-drive term, extra feature, architecture change, gain sweep, or filter sweep.

## Data and deployment boundaries

Use only identity-approved TRAIN records for fitting. Existing VAL records may be scored once as validation diagnostics, without hyperparameter or checkpoint selection beyond the fixed schedule. Do not train on VAL or TEST. Do not read TEST. If there are insufficient approved TRAIN records to construct the residual labels, do not substitute VAL/C5 full72/TEST; report the exact data gap and stop for root review.

At runtime, the model receives only the existing legal 13-dimensional feature stream and its past 15-event window. The residual label exists only for offline training and for the already-approved causal update from past measurements. Disable RBF output and RBF weight updates. Prohibit Jhat/Jdot reconstruction, current or true inertia, arm length/shape sensing, true Plant disturbance/force/torque, wind input, future samples, and oracle RBF outputs or hidden states from deployed input or execution.

The trained network output must retain the parent controller's documented sign convention: the prediction represents compensation acceleration and is subtracted through the existing fixed-J0 path. Confirm the sign with a synthetic known-disturbance test independent of the training code.

## Required deliverables before any Plant release

1. A new isolated folder only; do not overwrite or delete old source, raw, MAT, cache, model, or reports. Reuse large source/raw inputs by path and SHA where possible.
2. Frozen data manifest with TRAIN scene IDs, source path/SHA identities, row counts, exact timestamps/endpoints, feature and target definitions, and proof VAL/TEST rows are excluded from fitting.
3. One checkpoint plus training config/log and output-normalizer identity; no additional seeds or parameter search.
4. Independent Python reference for residual labels and model output; compare with MATLAB implementation on fixed fixtures, including sign, units, causality, and zero-head behavior.
5. No-Plant MATLAB validation and Code Analyzer/source-diff review. Only the target builder/training artifacts and the minimum runtime wiring may differ from parent; report every changed file and SHA.
6. Report training/validation error by axis and wind group, but do not claim closed-loop benefit from offline fit.

Luna must stop after these deliverables and make no MATLAB Plant call, closed-loop launch, 12-scene run, or TEST access. Root will independently review actual code, data split, model, hashes, and no-Plant reports. If approved, root will issue a separate frozen release for a fixed 12-scene DEV/VAL screen using reused B and C5 raws and the restored WN18 filter. No user permission is needed for this preparation phase; the Plant screen remains gated on root review.

Use PowerShell 7 for all command execution. Do not terminate or interrupt existing processes. Do not delete anything. Do not git stage, commit, or push.
