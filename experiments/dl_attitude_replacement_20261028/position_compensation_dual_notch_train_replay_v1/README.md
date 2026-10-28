# W09 stage-1 compensation dual-notch frozen replay

This is an offline mechanism screen for only the physical TRAIN scenes `DL1018_DEV_T1_C10_W09` and `DL1018_DEV_T3_C09_W09`. The raw paths come from each W09 attempt binding; each parent raw path is cross-checked against the exact scene row in its parent manifest. No other scene is used.

## Fixed intervention

Cascade two causal, unity-DC biquad notches on the final stage-1 position-compensation acceleration, after the C5 action and residual-GRU correction are combined and before that action becomes injected force. The fixed event-rate configuration is 100 Hz, with centers at 2.2 Hz and 3.2 Hz and Q=4 for each section. Update the filter only on the 100-Hz stage-1 event and hold its output between events. Initialize the filter history at the first nonzero action sample so startup does not inject a step. Keep the existing ±3 m/s² total-action bound and record any clipping.

This leaves the nominal backstepping acceleration, yaw target, and shared attitude command filter unchanged. It is intentionally different from filtering the complete position command or using the earlier broad 3.5-Hz/Q1 notch.

## Frozen replay and falsifiers

`replay_dual_notch_train24.py` reads the completed W09 candidate raws and their bound source records, filters the logged stage-1 action offline, and reconstructs the same-sample roll/pitch command target from the logged commanded force and yaw. It first requires the unmodified reconstruction to match the logged command target within 1e-8 rad.

The fixed replay passes only if, on both scenes:

- Command-target vector RMS falls at least 30% in each of the 1.5–2.5 Hz and 2.5–3.5 Hz bands.
- The band RMS change of the command-target difference stays within 2% of the original target RMS in 0.05–0.5 Hz.
- The corresponding low-band action-difference RMS stays within 2%, and no action-limit clipping occurs.

These are frozen-trajectory command checks, not closed-loop results. A later closed-loop falsifier must also reduce task-minus-actual RMS by at least 25% in each high-frequency band while worsening the position-error Q score by no more than 5% against the current candidate on both scenes. Passing the frozen replay does not establish cross-wind generalization.

The script does not call MATLAB or Plant. It does not read TEST data or perform inertia reconstruction.
