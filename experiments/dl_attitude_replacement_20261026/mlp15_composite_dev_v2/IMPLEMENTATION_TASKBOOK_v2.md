# Composite DEV v2 implementation taskbook

Date: 2026-10-27
Status: implementation started; release authorization remains zero.

## Scope

Build the isolated `mlp15_composite_dev_v2` source and review package from the approved v1 repair taskbook. Retain the already accepted composite-head update law from the v1 implementation and connect its tracking inputs and trace to the proven six-scene `run_mlp15_dev72_closed_loop` engine from `mlp15_causal_head_v1`. Restore `run_gate_holdout_closed_loop.m` byte-for-byte from the parent source. Bind the candidate to the configuration returned by the real `prepare_mlp15_dev72_no_plant(record.payload_path)` path, including the locked C5 full72 model and identity rebuild.

## Hard boundaries

- Do not modify, rename, or stop any file or process in `mlp15_composite_head_v1`; its CLI worker is finishing there.
- Do not train, launch Plant, run TEST scenes, or authorize any Plant call. `authorized_Plant_calls` remains 0 and `authorized_scenes` remains empty pending root review.
- No inertia reconstruction or inertia/Jhat/Jdot estimation. The candidate uses fixed J0, with `inertia_dot_for_bs=zeros(3)`.
- Do not add Plant truth to deployment inputs, change method parameters, alter physics arrays, or change scoring targets.
- Only the six manifest-bound DEV/VAL scenes and frozen prediction-only raw bindings may appear in release inputs.
- Use actual scene `p.cfg`, not `default_config()`, to bind the fixed controller. The command-filter angular-acceleration cap must be asserted as `[Inf Inf 6]` with the first two entries explicitly labeled unbounded.
- Both the unique root driver and actual DEV closed-loop entry must reject a zero Plant budget before creating output markers or entering Plant.

## Implementation sequence

1. Preserve the prior preparation artifacts and prior NO_PLANT_CHECK v1/v2 evidence under `preparation_attempt01/` as read-only provenance.
2. Copy only the source tree and small manifest/taskbook dependencies needed for an isolated candidate. Do not copy payload raw data, models, or generated run outputs.
3. Keep the accepted `mlp15_attitude_step_v1` math unchanged; connect tracking surface, Euler-rate map, actual event-dt input, and trace in the causal v1 DEV engine. Keep generic-gate source identical to parent.
4. Implement actual p.cfg / p.model binding; verify fixed J0, zero inertia derivative, and fixed morphology. Preserve the 6-scene manifest and exact scene identity contract.
5. Add a root driver and audit entry point with budget checks, lock/identity assertions, and unique outputs. Keep initial release at `PREPARED_ROOT_REVIEW_REQUIRED`, zero authorized Plant calls, and no authorized scenes.
6. Record source hashes, byte diffs, accurate review commands, and the final implementation state. Static checks are allowed; MATLAB runtime is optional and must not be started if a MATLAB process is already active.

## Release boundary

Only root may approve the first T1/W15 attempt after reviewing this package. This implementation does not authorize that attempt.

## Completion log (2026-10-27)

- Actual no-Plant check: `audits/NO_PLANT_CHECK_v2.json` (`PASS_REAL_PREPARED_CFG_AND_ZERO_BUDGET_ENTRY`). It captured the `prepare_mlp15_dev72_no_plant(record.payload_path).cfg` snapshot SHA `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a`, confirmed `[Inf (unbounded), Inf (unbounded), 6]`, fixed morphology, `Pfixed.inertia == J0`, and `Pfixed.inertia_dot_for_bs == zeros(3)`. It rebound model SHA `67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b` through `make_gate_holdout_options(p.cfg,p.model,...)` and rebuilt the C5 identity (`common_position_options_sha256=0218d3dc3c591b07ed6f7328de2c36276c4f51c2a0d56966bdff62d68d6a6b21`). Both actual `run_mlp15_dev72_closed_loop` and `run_composite_dev_attempt` rejected the zero budget before Plant or attempt creation.
- The already accepted synthetic fixture was reused: 300 events, 80 RLS updates, 81 tracking updates. No baseline metrics were recomputed.
- MATLAB R2025b no-Plant command was `cd('C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261026\mlp15_composite_dev_v2'); addpath(fullfile(pwd,'audits')); audit_composite_dev_no_plant;` (PID 35468). The audit wrote its PASS report and locked cfg, then MATLAB exited 1 while building the release struct because `TEST_read` was supplied twice. This metadata error was recorded in `RELEASE_FINALIZATION_v1.json`; the release metadata was finalized from the captured outputs with PowerShell 7, without rerunning prepare or baseline checks.
- `SOURCE_DIFF_v2.json` confirms the only two control source changes are `mlp15_attitude_step_v1.m` and `run_mlp15_dev72_closed_loop.m`. `run_gate_holdout_closed_loop.m` is byte-identical to causal v1; `mlp15_attitude_forward_v1.m` is unchanged.
- Source lock SHA-256: `'$sourceLockSha'`; diff SHA-256: `'$sourceDiffSha'`; patch SHA-256: `'$patchSha'`. Initial release stays `PREPARED_ROOT_REVIEW_REQUIRED`, with zero authorized calls and no authorized scenes.
- Root first-flight command after root authorization only: `run_composite_dev_attempt('DL1018_VAL_T1_C08_W15')`. It has not been run.
