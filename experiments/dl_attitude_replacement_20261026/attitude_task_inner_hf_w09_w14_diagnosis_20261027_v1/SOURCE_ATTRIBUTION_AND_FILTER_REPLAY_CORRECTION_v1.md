# HF command-path source and filter replay correction

Date: 2026-10-27 (Asia/Shanghai)

This addendum corrects the B-runner source attribution in `HF_W09_W14_attitude_path_diagnosis.md` and adds an independent replay of the recorded command filter.

## Source attribution correction

The path-diagnosis script selected Candidate, B, and C5 raw paths from the locked `FULL72_PAIRED_SCORE_v1.json` rows and checked each raw SHA. The B row points to `experiments/b_traceable_c3core_dev72_20261023/runs_b/.../raw_run.mat`. However, its `RUNNER_SOURCES` tuple cited `experiments/attitude_physics_inertia_observer_20261025/.../run_paired_observer_closed_loop.m`; that file is not the runner bound to the B raw in this score.

For the scored B batch, the traceable wrapper is `experiments/b_traceable_c3core_dev72_20261023/run_b_traceable_dev72_v3.m` (SHA-256 `85378c7ee2ef93681c30fae3e756a57487f0da6aae8ca3d98940404d12192b12`). The active controller source it binds is the project `matlab/runtime/run_dl1018_closed_loop.m`, included in `B_TRACEABLE_DEV72_INPUT_LOCK_v3.json`'s active source inventory. The path-diagnosis report's numeric trace metrics remain tied to the correct locked B raw files; its stated B runner path/line reference should not be used as provenance for this batch.

## Filter code and configuration check

Candidate, B, and C5 use the same `command_filter_step.m` SHA-256 `15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b` and `command_filter_init.m` SHA-256 `64fbd68ef652f419066e0546569ba4029bdc00da3eabb0f8019bdc12f66d14a5`. Their recorded run configurations agree on `wn=[18,18,12] rad/s`, damping `[1,1,1]`, acceleration limit `[Inf,Inf,6] rad/s²`, `dt=0.001 s`, and initialization from the actual starting Euler angle with zero filter rate. Each raw logs the filter output before the step advances its state.

I replayed the locked per-scene `command_filter_target_euler` using that recurrence against the logged `filtered_attitude_reference` for all 28 HF scenes and all three methods. Maximum absolute wrapped Euler mismatch was `6.4e-16 rad` for Candidate, `7.5e-16 rad` for B, and `5.0e-16 rad` for C5. This rules out a filter implementation or parameter mismatch as the source of the observed Candidate–B gap.

The equal-scene RMS geodesic rate of the recorded target was `2.799 rad/s` for Candidate, `0.247 rad/s` for B, and `2.794 rad/s` for C5. Candidate and C5 target-to-filtered SO(3) gaps are nearly equal; B's target stream is much slower. The large `target→filtered` gap therefore occurs at the filter input: the C5 DSSM position loop supplies a much faster command trajectory than B's position controller. This association does not alone prove what a different closed-loop filter bandwidth would do to Q.

## Follow-up hypothesis, not a result

On the recorded Candidate target streams held fixed, an offline replay changing only roll/pitch `wn` from 18 to 12 rad/s reduced macro task-to-filtered-reference SO(3) RMSE from `60.537` to `57.595 mrad`. This is conditional signal replay, not a closed-loop counterfactual; the position trajectory and command targets would change after a Plant run. It motivates one isolated low-bandwidth screen, with position-Q gates unchanged. It does not authorize or predict success of that screen.
