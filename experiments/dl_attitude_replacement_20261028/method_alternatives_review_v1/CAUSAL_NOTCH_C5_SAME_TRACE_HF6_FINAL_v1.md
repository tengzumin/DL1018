# Causal notch replay on C5 HF6 traces

Offline same-trace replay only; no Plant, TEST, training, wind-field read, or inertia reconstruction. VAL is a development diagnostic, not independent validation.

Fixed scheme: second-order causal `iirnotch` at 3.5 Hz, Q=1, fs=100 Hz, zero initial state, updated only when `stage1_position_event` is true; hold output between events. No Q/frequency sweep was performed.

The C5 raw log has 20,000 1-ms transitions and 1,999 Stage1 events per scene at zero-based indices 10, 20, …, 19,990 (event time 10 ms onward). The filtered input is the logged held applied Stage1 acceleration at the current event. Its output replaces the compensation only for reconstructing command/target on the unchanged raw state trajectory.

## Filter response

Poles: `[[0.8788867602711026, 0.1694376970420597], [0.8788867602711026, -0.1694376970420597]]`; stable=True; dense-grid −3 dB edges 2.158–5.656 Hz.

| Frequency (Hz) | Gain (dB) | Phase (deg) |
|---:|---:|---:|
| 0.5 | -0.093 | -8.36 |
| 1 | -0.407 | -17.41 |
| 1.5 | -1.071 | -27.87 |
| 2 | -2.380 | -40.51 |
| 2.5 | -4.987 | -55.72 |
| 3 | -10.624 | -72.88 |
| 3.5 | notch zero | undefined |
| 4 | -11.766 | +75.05 |
| 4.5 | -6.890 | +63.10 |
| 5 | -4.599 | +53.92 |
| 6 | -2.494 | +41.37 |
| 8 | -1.089 | +28.10 |
| 10 | -0.611 | +21.25 |

At 1 Hz the response is −0.407 dB/−17.41°; at 5 Hz it is −4.599 dB/+53.92°. This does **not** leave all sub-1-Hz content untouched, and its phase is material around the band edges. The response is computed for the 100-Hz event-rate filter; the 1-ms output hold adds a further frequency-dependent response not included in this table.

Historical-source check: the repository search found no completed prior notch implementation. The only older mention is `experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/CONTINUATION_STATE_v2.json`, marked `OFFLINE_PREPARING` (SHA-256 recorded in the JSON); it contains no prior completed result.

## Equal-scene results

| Signal | Compensation RMS (m/s²) | Task→command target SO(3) (mrad) | Task→filtered reference SO(3) (mrad) | Δ command force RMS (N) | Comp 0–1 Hz | Comp 1–2 Hz | Comp 2–5 Hz | Target RP 2–5 Hz | Signed target RP Δ 2–5 Hz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw_C5 | 0.7408 | 81.213 | 63.969 | 0.0000 | 0.5847 | 0.0473 | 0.4370 | 53.917 | 0.000 |
| tau0p1_event100hz | 0.6166 | 66.997 | 60.865 | 0.2611 | 0.5830 | 0.0394 | 0.1903 | 30.748 | 37.693 |
| notch_3p5Hz_Q1_event100hz | 0.6110 | 64.551 | 60.771 | 0.2791 | 0.5839 | 0.0443 | 0.1645 | 23.556 | 40.469 |

The signed target RP delta is candidate minus raw C5. The reported 2–5 Hz cross term is retained separately in the JSON because the candidate target spectrum is not the sum of the raw target and compensation spectra; force-to-attitude mapping is nonlinear. Per-scene values and HF-group means are in the JSON.

Different-trajectory B comparator: mean task→logged-filtered-reference 60.550 mrad. This is contextual only; it is not a same-state counterfactual.

## Limits

Filtering `dF` on a fixed trajectory does not recompute position closure Q or the next state. A lower compensation-band RMS or conditional attitude-reference error cannot establish closed-loop success. The filter's phase may improve one trace and worsen another; the six DEV/VAL signals only support or falsify this offline mechanism hypothesis.

## Reproduction

From the repository root: `python experiments/dl_attitude_replacement_20261028/method_alternatives_review_v1/causal_notch_replay_hf6_v1.py`.

Script SHA-256: `65322a70c64836a43e070d2e4e767f4f9edceabb00793aa896983752860702fc`.
