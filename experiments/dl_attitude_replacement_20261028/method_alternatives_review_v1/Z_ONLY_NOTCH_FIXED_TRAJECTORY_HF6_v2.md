# Z-only notch fixed-trajectory replay on HF6

Offline event-stream replay only. The Z-only filter uses each completed notch raw's logged Stage1 input events; XY compensation passes straight through and Z uses the fixed 3.5-Hz/Q=1 causal filter. The replay holds each output between existing 100-Hz events on the recorded state trajectory. No Plant, TEST, training, or inertia reconstruction.

## Task to filtered-reference orientation

| Reference condition | Equal-scene mean SO(3) (mrad) |
|---|---:|
| full_notch_logged | 61.961 |
| z_only_notch_replayed | 64.516 |
| parent_no_notch_logged | 63.137 |

Frozen closed-loop task SO(3) context: Parent no-notch GRU 61.199 mrad; full notch 60.033 mrad. These are score_raw closed-loop results; Z-only has no closed-loop score.

## 2–5 Hz signals

| Quantity | Full notch mean | Z-only mean | Signed delta / cross term |
|---|---:|---:|---:|
| Compensation RMS (m/s²) | 0.2015 | 0.4178 | 0.3559 |
| Target RP RMS (mrad) | 28.9543 | 51.5726 | 36.0700 |
| Filtered reference RP RMS (mrad) | 15.4781 | 24.6364 | 16.4221 |
| Target RP power cross term (mrad²) | — | — | +333.644 |
| Filtered-reference RP power cross term (mrad²) | — | — | +30.989 |

Per-scene values, HF-group means, raw hashes, event counts, full-notch parity, and target-power identity checks are in the JSON.

The task→filtered values come from fixed recorded states, so they are diagnostic replays, not closed-loop Z-only performance. A lower 2–5 Hz target RMS alone does not establish task improvement; the signed target delta and cross term are reported.

Reproduce from repository root: `python experiments/dl_attitude_replacement_20261028/method_alternatives_review_v1/z_only_notch_replay_hf6_v1.py`.
