# Root post-screen review: beta=0.25 HF28

Date: 2026-10-27 (Asia/Shanghai)
Decision: **REJECT beta=0.25; do not expand or tune this target-blend branch. Keep the pre-existing no-blend GRU candidate as the active attitude-replacement reference.**

## What ran

The released V2 batch completed 28/28 frozen W09–W14 development scenes. Each raw has 20,000 transitions and 20,001 states; all are finite and stable. Every recorded safety counter is zero, and no TEST data were read. The frozen scorer and scene identities were used; B/C5 raw results were reused rather than rerun. Raw files total about 2.41 GiB.

The V2 runner repair only moved the existing `isNetwork` assignment before its first read. The earlier V1 failures were startup-order failures before any transition and are separately recorded in `HF28_V1_ABORT_AUDIT_v1.md`.

## Paired result

All means below give each scene equal weight. No-blend and beta=.25 are the same GRU weights, online tracking head, C5 DSSM14 position stack, geometry, Plant, filter, scenes, and references; beta=.25 changes only the active attitude target.

| HF W09–W14, 28 scenes | No-blend GRU | beta=.25 | Frozen B | Frozen C5 |
|---|---:|---:|---:|---:|
| Position Q (mm) | 9.7152 | 42.8624 | 10.7188 | 10.1791 |
| Trajectory-task SO(3) RMSE (mrad) | 58.8536 | 56.0873 | 54.8159 | 58.7954 |
| Inner command-tracking SO(3) RMSE (mrad) | 13.8167 | 13.6873 | 15.5061 | 15.6883 |
| Q wins vs B / C5 | 24/28 / 26/28 | 0/28 / 0/28 | — | — |
| Task SO(3) wins vs B / C5 | 2/28 / 7/28 | 5/28 / 28/28 | — | — |
| Inner SO(3) wins vs B / C5 | 25/28 / 26/28 | not independently rescored here | — | — |

The beta=.25 candidate still loses the task-attitude macro to B (56.087 vs 54.816 mrad), and its position Q is 4.41 times the no-blend value. It therefore fails the joint objective despite its improvement over C5 on the task-attitude metric.

An independent axis-level replay of the frozen score function found:

| Equal-scene axis RMSE | No-blend | beta=.25 | Change |
|---|---:|---:|---:|
| Position X (mm) | 6.295 | 27.878 | +21.583 |
| Position Y (mm) | 6.443 | 27.721 | +21.278 |
| Position Z (mm) | 1.957 | 2.044 | +0.087 |
| Task roll (mrad) | 37.906 | 35.768 | -2.139 |
| Task pitch (mrad) | 37.662 | 36.256 | -1.405 |
| Inner roll tracking (mrad) | 9.140 | 9.026 | -0.113 |
| Inner pitch tracking (mrad) | 9.645 | 9.560 | -0.085 |

Thus the position penalty is almost entirely horizontal. The beta blend slightly improves inner tracking, but most of the task-attitude score change comes from shifting the desired orientation, not from making the learned inner controller materially more accurate.

## Root cause

At the active callsite in `candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m`, the unblended target is built from `positionInfo.commanded_acceleration` (around line 2391). That acceleration contains position-feedback correction. The blend's trajectory task target is computed from `r.acceleration` and reference yaw (around lines 2395–2396), without that correction. The mean geodesic separation between these targets in the 28 raws was 74.142 mrad; beta=.25 deliberately moves one quarter of that separation into the active command.

This explains the observed tradeoff: tracking the trajectory-only orientation more closely reduces the trajectory-task attitude error a little, while removing some tilt needed by the position loop, so horizontal position error grows sharply. It is not evidence of an inertia-reconstruction leak, a baseline score mismatch, a different model, a B/C5 rerun, or an identified beta-helper sign/frame error. The numerical SO(3) interpolation and raw/manifest identities were verified. The comparison is valid as a closed-loop system comparison; it does not isolate the attitude module from the feedback-aware target that the position controller supplies.

The no-blend candidate's inner command-tracking error is already lower than B/C5 in the HF group (13.817 vs 15.506/15.688 mrad), with 25/28 and 26/28 paired wins. The remaining HF weakness is specifically the plant attitude relative to the trajectory-only task reference. That metric also reflects how much position feedback changes the demanded tilt; it should not be called a pure inner-loop tracking metric.

## Decision and next action

1. Keep V2 complete and immutable; do not rerun it, sweep beta, or open TEST.
2. Reject beta=.25 as a method candidate. Do not use this result as evidence that the GRU replacement itself damaged position; the old no-blend candidate is the relevant same-stack control.
3. Keep the no-blend GRU candidate as the reference for the next review. It already has strong paired HF position and inner command tracking, while its HF trajectory-task SO(3) remains worse than B and marginally worse than C5.
4. Before changing more controller code, review whether the paper's attitude claim should be evaluated with (a) inner tracking against the filtered, feedback-aware attitude command and (b) total attitude against the trajectory task reference, reported separately. If the latter must beat B under the current fixed position controller, the next intervention must preserve the position-feedback tilt while improving attitude tracking; another convex blend toward the trajectory-only target is not justified by these results.

Independent yaw-convention review found only about 0.16–0.18 mrad RMS thrust-axis mismatch, too small to explain the HF task-attitude gap; see the Luna review thread for details. The existing v2 result remains development evidence only, not independent TEST or a paper-level final claim.

The earlier HF command-path note had a B-runner source-path attribution error; its locked B raw paths and numeric trace calculations remain unchanged. The corrected source attribution and a 28-scene filter recurrence replay are recorded in `experiments/dl_attitude_replacement_20261026/attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/SOURCE_ATTRIBUTION_AND_FILTER_REPLAY_CORRECTION_v1.md`. The replay confirms the filter implementation, timing, and effective parameters match; the high target-to-filtered gap is associated with the much faster target stream from the C5 DSSM position loop.
