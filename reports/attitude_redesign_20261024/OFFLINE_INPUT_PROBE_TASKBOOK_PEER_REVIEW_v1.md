# Offline input probe taskbook v1: independent static review

## Scope and verdict

I read taskbook SHA256 `7FF283E153DE88CEBC88D092640300C8305701540B1EE4A0A06DA0E265E3773F`. At review time `reports/attitude_redesign_20261024/offline_input_probe_v1` did not exist, so this is a taskbook/source review only; no fitting, model execution, TEST read, training, runner, integration, or Plant operation occurred.

The five-group design, deterministic TRAIN/VAL plan, common quadratic Ridge specification, TRAIN-only input/target scaling, scene-equal scoring, and VAL-as-development disclosure are coherent for a bounded information diagnostic. The executor must pin exact time indices and command units before fit; those details are necessary for causal interpretation.

## Required input reconstruction

For each scene, reconstruct the fixed nominal inertia by calling the existing source functions on that scene's recorded `cfg`:

```matlab
Pplant0 = simulation_parameters(cfg, cfg.plant.arm_initial(:), zeros(4,1));
P0 = controller_parameters(cfg, Pplant0, 'fixed');
J0 = P0.inertia;
Jdot0 = P0.inertia_dot_for_bs;
```

This follows `controller_parameters.m` fixed branch: use `nominal_arm_lengths`, zero arm rates, and `arm_mass_properties` over the `distributed_v1` component masses, dimensions, arm geometry, and mount contract; then apply `controller_inertia_derivative_mode`. Do not use `cfg.plant.inertia` as a substitute for the computed distributed inertia. Rebuild the event B7 angular-acceleration feature from raw nominal moment and state:

```matlab
alpha_BS = J0 \ (tau_nominal - cross(omega_B, J0*omega_B) - Jdot0*omega_B);
```

This is the inverse of `attitude_bs_step.m`'s `nominalMoment = J0*nominalBodyAngularAcceleration + cross(omega,J0*omega) + Jdot0*omega`. Since the fixed model has zero arm rates, Jdot0 is normally zero, but the implementation should still use and record `P0.inertia_dot_for_bs` rather than silently omit the term. Assert the relevant fixed physical configuration and resulting J0 agree across scenes.

For H5-only numerical cross-checks, `x`/`x29` columns 7:9 (1-based) are `omega_B`, columns 22:24 are nominal body angular acceleration, and column 25 is thrust/mass. These indices follow `attitude_feature_row_v3_6.m`; they are cross-checks only, not input construction. The existing H5 `target_raw` is an event-instant body angular-acceleration residual, but full TRAIN/VAL raw replay and old source identity are not established by this probe. Report it as a prediction-information diagnostic on the stored B labels, not ground-truth validation.

The shape command in DL1018's scenario is the raw `arms.command` normalized sign/rate command in `{−1,0,1}`; `rhoDot_true = 0.05 * command` for the fixed scene morph speed. Define the feature explicitly as raw command `u_k = arms.command(k,:)`, dimensionless, if that is intended. Then `z_k = 0.001 * sum_{i<k} u_i` is signed command-duration in seconds. Do not substitute `rhoDot_true` as a deployable feature. Record that the scene's commanded schedule is available before the prediction; if a source row does not establish a pre-issued command, stop instead of using it.

## Time and event requirements

The raw runtime loop processes state `x(k,:)` and any attitude event at `t(k)`, then computes and logs `requested(k,:)`, integrates into `x(k+1,:)`, and serializes `transition_time=t(q)`, `state=x(qs,:)`, and `attitude_event_flag=attitudeEventLog(q)`. Thus the command/request at row `k` is for the interval starting at the current event and is not a past input to a prediction at that same event. For event index `k`, the previous completed 10×1 ms requested-torque interval is exactly MATLAB rows `k-10:k-1`, columns 2:4 of `requested_generalized`; the `a3` feature is their equal-time-weighted mean. The first event is k=11, so its history rows are 1:10. Assert event-time/flag alignment, 1 ms spacing, and interval completeness. Do not use rows `k-9:k`, which would include the current same-event request and omit a past interval row.

Use raw event row indices for all reconstructed features and `plant_index` to align each H5 `target_raw` row. The H5 feature columns must not be copied into any of G0–G4. Keep `z`'s cumulative update strictly causal (`i<k`) and initialize at zero as specified.

## Fit and reporting gates

Before reading feature/target values, freeze the exact 48 TRAIN scene IDs and H5/raw/run-start hashes from the metadata-only selection. Use exactly event rows 0,5,10,… for the TRAIN fit subset, without replacing failed scenes; fit each group's mean/std and per-axis target RMS on that subset only. Validation values must not affect normalizers, coefficients, or regularization. Report per-scene metrics before any group mean and compute group summaries with equal scene weight. Empty phase/scene cells must stay empty. The recorded VAL results may inform the next input decision only as development evidence, never as independent TEST or as proof of closure performance.

## Pinned source identities

- `matlab/core/arm_mass_properties.m`: `8EC66E107156B5219F7E41ACA2464EEF1EC8043EB7F67DF313C0F23EF4B551F5`
- `matlab/core/distributed_mass_properties.m`: `DB380B506E4BACC37BC398D5726C5EBD25BE8EBC08B6C9E76FF59BC78FD45D3A`
- `matlab/core/simulation_parameters.m`: `962B5434C23D5AC1A9AC568F136635A8EA651A775165D84B7D95250CA88BB9AE`
- `matlab/core/controller_parameters.m`: `4FAD5E78C0BD4177461647AF167E7C86A7DEFA628B43D523B0B7DA2EF5556398`
- `matlab/core/attitude_bs_step.m`: `CF6B20FFC4DF2625D9316A80340D69542E380D14FEAED66EF8498E793FDACCBC`
- `matlab/data/attitude_feature_row_v3_6.m`: `ED65A4FA52321AACE622549BB4F444410264F53FC753F12FD49E6ACD02415616`
- `matlab/runtime/run_dl1018_closed_loop.m`: `9F6B436C8247C49783EC04EF326B20FC5D7DE2870C9AB972212A0B2E4C432BC2`
- `matlab/scenes/make_scenes_dl1018.m`: `7D11B4EBF63105B016C67F4B3C427282B35DAFA53280EF2DAF5578A6A16BB9EC`
- `matlab/core/tcn0916_morphology_scenario.m`: `711A87E01E616EE141F9068A8C4E31758DC328ADE3F692E1A92A5DE723D30438`
