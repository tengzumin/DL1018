# Composite DEV v3 implementation taskbook

Date: 2026-10-27. Scope: repair only the attempt-marker identity regression in the isolated `mlp15_composite_dev_v3` tree.

## Changes

- Reuse v2's accepted MLP event step, DEV event/tracking wiring, six-scene manifest and passed locked configuration. The sole control-source change from v2 is in `candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m`: copy `opts`, remove only `composite_attempt_marker` from that copy, recompute identity with the existing helper, and keep the full `gate_identity_lock` equality assertion.
- Do not change `gate_holdout_identity_hashes`, numerical step, method parameters, gains, plant model, or common generic gate. Generic gate remains byte-identical to causal-head v1; forward remains unchanged. v3's source diff against causal-head v1 is exactly the accepted step and DEV loop files.
- Reuse v2 `LOCKED_CFG.json` exactly. It captures actual `prepare_mlp15_dev72_no_plant(...).cfg`, including command filter `[Inf, Inf, 6]`, fixed J0 and zero Jdot0. Reuse prior 300-event fixture result (80 residual RLS updates, 81 tracking updates); do not rerun fixture or baseline metrics.
- Reuse v2's driver and raw auditor with only v3 lock/report paths. A new no-Plant audit will reconstruct actual prepared options and verify marker-stripped identity equals the frozen identity.

## Provenance

`V2_FAILURE_LINEAGE.json` records SHA256s for the inherited v2 no-Plant report and locked cfg, prior 300-event report SHA/counts, and the v2 first-attempt `GATE:IdentityLock` failure. v2 is left unchanged; v3 does not copy v2 run raw/logs or preparation fixture.

## Boundaries

Initial v3 release is `PREPARED_ROOT_REVIEW_REQUIRED` with `authorized_Plant_calls=0`, no authorized scenes, no training, no Plant, and no TEST reads. This task performs only static binding and no-Plant identity/budget checks. Root review is required before any flight authorization.
