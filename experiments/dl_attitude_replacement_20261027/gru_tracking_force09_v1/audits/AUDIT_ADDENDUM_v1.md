# GRU force09 raw audit addendum

This addendum supplements the formal `GRU_TRACKING_FORCE09_SCORE_final12.json`; it does not modify that score, frozen sources, release, or run outputs. The audit reads the 12 completed candidate MAT files only. No Plant run was started.

## Raw wind grouping

Wind was classified directly from each raw `scene/environment_wind_I` array, with zero meaning every stored component equals exactly zero. All 12 raw/status/start hashes match the formal score, and all 12 statuses are `COMPLETED`.

- Zero wind: 3 scenes — `DL1018_DEV_T1_C01_W15`, `DL1018_VAL_T2_C05_W15`, `DL1018_VAL_T3_C02_W15`.
- Nonzero wind: 9 scenes — `DL1018_DEV_T1_C10_W09`, `DL1018_DEV_T2_C00_W04`, `DL1018_DEV_T2_C09_W10`, `DL1018_DEV_T3_C00_W05`, `DL1018_DEV_T3_C09_W09`, `DL1018_VAL_T1_C00_W07`, `DL1018_VAL_T1_C07_W14`, `DL1018_VAL_T2_C04_W14`, `DL1018_VAL_T3_C01_W14`.
- Maximum absolute stored wind component: `14.722010947957433`.

## GRU-specific trace

Audited `log/gru_stream_attitude_trace`, not legacy `log/trace`: 23,988 events, 1,999 per scene. Every event records a 13-element model input in this order: Euler attitude error (1:3, rad), body angular rate (4:6, rad/s), nominal body moment (7:9, N·m), and normalized arm morphology command (10:13, dimensionless). The trace marks the base GRU weights fixed and output-before-tracking-update at all events.

The 13-feature inference vector contains no inertia input. No `J`, `J0`, `Jdot`, `Jhat`, or inertia-estimate fields occur in the GRU event trace; `time_varying_inertia_reconstruction_used` is false at all 23,988 events. The step receives the locked fixed `J0` separately for the torque map. Plant physical dynamics are separate from the GRU/controller path.

Across every event, the recorded residual clipping, beta scaling, fixed-`J0` torque mapping, and `DeltaW` update/projection match their equations. Maximum absolute identity errors are at most `7.11e-15`; torque and clipping errors are zero, and the tracking update/projection errors are at most `1.74e-18`. No residual element was clipped; no `DeltaW` projection activated, and the projection flag matched the recomputed condition at every event.

## Decision

On HF W09–W14, candidate Q is `0.01171651485` versus B `0.01126576966` (**+4.00%**, worse). Candidate task SO(3) RMSE is `0.06030275611 rad` versus B `0.05761862420 rad` (**+4.66%**, worse), with **0/6** task wins. **FAIL; do not expand this candidate study.**

The parent model used DEV24+VAL48 for development training; VAL is not independent validation, and this study adds no training. A future winner requires a fresh holdout.

Machine-readable bindings and full identity-check values are in [`AUDIT_ADDENDUM_v1.json`](AUDIT_ADDENDUM_v1.json).
