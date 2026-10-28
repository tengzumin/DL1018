# C5 position head: HF6 input spectrum and causal replay screen

Status: read-only diagnostic; no source, model, controller, PCF, or raw run changed. No Plant, TEST, or inertia reconstruction was used.

## Evidence and binding

- HF6 scenes and B/C5 raw bindings: `ROOT_POSITION_APPLIED_LOWPASS_HF6_SCORE_v1.json` (SHA-256 `4cc2c61f4b4179f6f502250850b1dbfdcfb0c8bcd312792f66886c26715bb669`). The six scenes are the fixed HF6 cohort. The scorer binds each raw path and SHA.
- C5 source lock: `C5_DEV72_INPUT_LOCK_v3.json` (SHA-256 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`); it identifies DSSM14, input dimension 14, 32-event window, selected step 60000, W0 SHA `88f8c4f2…a0c2f53`, and training-only normalizer arrays SHA `533aad9a…013de5f0`.
- C5 predictor/update source: `position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m`, SHA-256 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`; fixed `rho=0.01`.
- Model and normalizer files match the locked hashes: `matlab_model_and_parity.mat` SHA `6f3628b1…ead9c9b6e`; `normalizer_x14_train_only.npz` SHA `520983e0…ace198404`. The NPZ contains only `mu` and `sigma`; no validation or TEST statistics were read.

The C5 runtime assembles each event input as `[position error(1:3), position surface(4:6), measured Euler(7:9), preview thrust/mass(10), RL-GAP u_rho(11:14)]`. Thus dimensions 11–14 are internal `u_rho` values, not motor commands. The model normalizes every column with the locked training-only `mu/sigma`, then recomputes a 32-sample DSSM history from zero state at each 100 Hz event. The 32 learned time constants span 5.30 ms–0.959 s; at 10 ms their state-retention factors `exp(-0.01/tau)` span 0.152–0.990. The window spans 320 ms, but this is not a persistent hidden state across inference calls.

## B versus C5 on the saved HF6 trajectories

Position error is `reference.position - state(1:3)` over 0.5–19.5 s. Compensation is the logged applied position compensation force. These are trajectory comparisons, not counterfactual closed-loop results.

| Scene | Position error RMS B → C5 (mm) | Applied compensation force RMS B → C5 (N) | C5 2–5 Hz force RMS (N) |
|---|---:|---:|---:|
| VAL T3 C01 W14 | 11.674 → 10.234 | 0.449 → 0.596 | 0.395 |
| DEV T1 C10 W09 | 11.268 → 10.734 | 0.327 → 0.338 | 0.110 |
| DEV T2 C09 W10 | 10.866 → 11.637 | 0.447 → 0.582 | 0.300 |
| DEV T3 C09 W09 | 11.286 → 9.876 | 0.425 → 0.446 | 0.140 |
| VAL T1 C07 W14 | 14.152 → 12.456 | 0.505 → 0.640 | 0.404 |
| VAL T2 C04 W14 | 10.011 → 10.155 | 0.393 → 0.528 | 0.364 |

C5 lowers position error in four scenes and raises it in two. Its applied force RMS is higher in all six (macro mean 0.522 N vs 0.424 N, +22.9%). In the 2–5 Hz band, B force RMS is 0.00–0.02 N while C5 is 0.110–0.404 N. The C5 position head is enabled; B's replacement head is disabled. This supports a real HF compensation difference, but does not identify its cause.

## Online update versus fixed W0: signed 2–5 Hz diagnostic

On each saved C5 feature sequence `phi`, I evaluated the logged online output and the initial W0 output with the same `phi`. A zero-phase 2–5 Hz filter was used only for this offline signed comparison; it is not a proposed runtime operation.

| Scene | Signed projection gain (online onto W0) | Relative band difference norm | X/Y band correlation |
|---|---:|---:|---:|
| VAL T3 C01 W14 | 0.962 | 0.087 | 0.999 / 0.997 |
| DEV T1 C10 W09 | 1.012 | 0.038 | 0.999 / 1.000 |
| DEV T2 C09 W10 | 0.945 | 0.100 | 0.997 / 0.999 |
| DEV T3 C09 W09 | 0.998 | 0.038 | 1.000 / 0.998 |
| VAL T1 C07 W14 | 0.969 | 0.055 | 0.999 / 0.999 |
| VAL T2 C04 W14 | 0.972 | 0.057 | 0.999 / 0.999 |

The logged C5 online weight sequence changes the signed X/Y 2–5 Hz component little on the same recorded `phi`; this is evidence against the online update being the main source of that component. It is not a causal claim about the backbone: `phi` itself came from the closed-loop C5 trajectory, and the fixed-W0 comparison does not intervene on inputs or plant state.

The original C5 update was reconstructed event by event with `rho=0.01`; maximum differences versus logged output and W-after were below `9e-16`. Median prediction/tracking update-gradient norm ratios across the six scenes were 0.68–1.66. Negative per-event inner products occurred, but the conflict-gated and PCGrad replays did not reduce 2–5 Hz output. Antagonistic gradients alone are therefore not treated as a defect.

## Input dimensions and the frozen-model causal screen

Median normalized 2–5 Hz band RMS across the six logged C5 inputs was:

| Dimensions | Meaning | Median 2–5 Hz RMS after locked normalization |
|---|---|---:|
| 1–3 | Position error | 0.006–0.017 |
| 4–6 | Position sliding surface | 0.103–0.242 |
| 7–9 | Measured Euler angles | 0.131–0.320 |
| 10 | Preview thrust / mass | 0.115 |
| 11–13 | RL-GAP `u_rho` | 0 in these six scenes |
| 14 | RL-GAP `u_rho` | 0.055 |

As one fixed sensitivity screen (not a sweep), I replayed the locked DSSM14 forward pass after applying a causal 1 Hz one-pole filter to dimensions 7–10 at the 100 Hz input-event rate only. The state was initialized from the first observed value; `alpha=exp(-2*pi*1*0.01)=0.939101`. Dimensions 1–6 and 11–14, the C5 W-before sequence, beta, and PCF/force path were held fixed. The unfiltered forward pass reproduced logged `phi` within `2.2e-16` and applied head output within `1.6e-15`.

Using the old, raw-input normalizer, normalized standard deviation of filtered dimensions 7–10 relative to unfiltered was, by scene: roll 0.859–0.978 (median 0.950), pitch 0.747–0.984 (median 0.862), yaw 0.677–0.948 (median 0.907), thrust/mass 0.509–0.977 (median 0.901). This is a train/runtime distribution mismatch; the frozen-weight replay is only a sensitivity check.

| Scene | 0–0.5 Hz change | 0.5–2 Hz change | 2–5 Hz change | 5–20 Hz change |
|---|---:|---:|---:|---:|
| VAL T3 C01 W14 | 0.0% | −2.0% | +14.9% | +3.1% |
| DEV T1 C10 W09 | +0.7% | +4.2% | +16.0% | +2.7% |
| DEV T2 C09 W10 | +1.9% | +5.9% | −23.4% | −17.8% |
| DEV T3 C09 W09 | +1.0% | −5.2% | +7.3% | +16.3% |
| VAL T1 C07 W14 | −0.1% | −17.2% | +9.6% | −0.2% |
| VAL T2 C04 W14 | +1.1% | −11.6% | +14.3% | +14.5% |

This input-only screen lowers 2–5 Hz output in only one of six scenes. It does not support proceeding with this exact filter. The unchanged normalizer also means it is not a valid trained candidate. No conclusion that Euler/thrust inputs cause the C5 oscillation is warranted.

## Decision and boundary

- Do not change the C5 online head update based on this evidence. Its contribution to the signed 2–5 Hz output is small on the fixed recorded feature sequence; gradient conflict does not translate to a useful reduction in the frozen-trace replay.
- Do not promote the screened 1 Hz input filter. Its frozen-model result is inconsistent and its normalizer is mismatched.
- A future input treatment, if reconsidered after the separate notch result, must apply the same causal event-rate preprocessing during training and runtime, reset per scene/run from the first current sample, and fit the normalizer from transformed training data only. It must keep full scenes grouped for validation and reserve fresh holdout scenes before any winner claim. Zero-phase filtering is limited to offline spectral diagnostics, never deployment.
- A future target treatment must define its label at event `k` only after the completed interval `k-10 → k` is observed (the logged `stage1_position_delayed_prediction_target_mps2`), apply any causal target transform to training and the runtime prediction-gradient target identically, reset it at each scene, and split by whole scenes/wind groups before fitting. It must not use parent-future pointwise errors or an external wind oracle. This is a design constraint, not a tested candidate or a claim of improvement.

No independent winner evaluation is claimed. The HF6 cohort is a development screen; a fresh grouped holdout is required before selecting a new winner.
