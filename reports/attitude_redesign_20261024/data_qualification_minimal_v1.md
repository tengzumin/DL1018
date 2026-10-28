# Attitude data qualification: two-scene read-only check

**Scope.** This check reads only the first TRAIN scene `DL1018_TRAIN_T1_C00_W00/B` and lexicographically first VAL scene `DL1018_VAL_T1_C00_W07/B`, their event H5 files, and the corresponding `attempt_01` raw/run-start/marker files. No TEST data, MATLAB execution, training, or closed-loop run was used. The wider H5 metadata inventory is recorded separately in `EVENT_METADATA_INVENTORY_v1.json`; this note does not repeat that scan.

## Finding

For both selected scenes, event rows align exactly with the raw event flags and event times. The exported `target_raw` can also be independently reconstructed from the raw state, realized generalized torque, wind torque, arm geometry, and the configuration in `run_start.mat` using the exporter’s rigid-body equation. The reconstruction agrees with H5 to floating-point precision.

However, these two selected labels are effectively zero-residual controls: all four arms stay at 0.15 m, arm command/rate are zero, the requested torque equals the exporter’s virtual torque, realized torque differs only at round-off, and logged wind torque is at most `1.4e-17 N·m`. The H5 targets peak at only `9.31e-14` and `8.43e-14 rad/s²`. This establishes traceability for these two records, but they provide almost no nonzero attitude-residual supervision. It does not establish label reconstruction or informative excitation for the remaining TRAIN/VAL records.

## Event and identity checks

Each H5 has 1,999 event rows, `x`/`x29` shape `(1999, 29)`, and `target_raw` shape `(1999, 3)`. In both raw files, `attitude_event_flag` and `transition_time` have 20,000 entries while `state` has 20,001 state columns. The 1-based event positions are exactly `11, 21, ..., 19991`; H5 `plant_index` equals those positions, H5 `event_index` is `1..1999`, and H5 `event_time_s` equals `transition_time[plant_index-1]` exactly (`max absolute difference = 0`). The first and last H5 times are 0.01 s and 19.99 s. The exporter indexes the event flag and state with the same MATLAB 1-based `k`; in NumPy terms, raw state column `k-1` is the state used for event `k`.

The H5 attributes identify split, scene, contract, collector/model `B`, and role `attitude_teacher_reused_from_B`. Each `run_start.mat` has matching scene-specific `run_id`, `collector_id=B`, `model_id=B`, contract, `raw_path`, and recorded `cfg`/`opts`; the raw `method` scalar is 66 (ASCII `B`). Both markers contain `first_plant_transition=1`. These artifacts link the event file to the B run/configuration and confirm a Plant transition occurred.

They do **not** pin the exact runtime source revision. The raw MAT root has no `runIdentity`; neither `run_start.mat`’s fields nor the H5 attributes contain a source commit/hash or raw-file hash. The marker records a transition, not source provenance. Thus the B/config identity is supported, but exact producing-source identity and a cryptographic H5-to-raw binding remain unverified for these records. Do not equate a recorded config/opts match with full provenance verification.

## Independent label reconstruction

The exporter defines `tauVirtual = ai0.nominal_moment - tauBehavior`, computes true angular acceleration from `vehicle_derivative` using `realized_generalized`, `wind_torque_B`, and `Ptrue(rho_true,rhoDot_true)`, and stores `target_raw = omegaDotTrue - omegaDotVirtual` ([exporter lines 31–45](../../matlab/data/export_attitude_events_dl1018.m:31)). The raw runtime logs `attitudeInfo.nominal_moment` as `attitude_bs_nominal_torque_Nm` and the applied `dT` as `attitude_compensation_applied_torque_Nm` ([runtime lines 2326, 2516–2527](../../matlab/runtime/run_dl1018_closed_loop.m:2326)); the exporter’s zero-estimate call has the same nominal moment because that term is independent of the estimate-torque argument. The rotational dynamics are

\[
\dot\omega=J^{-1}\{\tau_{real}+\tau_{wind}-\omega\times(J\omega)-\dot J\omega\}.
\]

I independently rebuilt the fixed-shape inertia from each recorded `cfg.plant` geometry/mass data using the repository’s `distributed_v1` equations, then evaluated the reduced difference for these static-shape scenes:

\[
\widehat y=J^{-1}\left[\tau_{real}+\tau_{wind}-(\tau_{nominal}-\tau_{behavior})\right].
\]

This reduction is valid here because raw `rho_true` is constantly 0.15 m, `rhoDot_true` and arm command are zero, so true and fixed-controller `J` and `Jdot` agree; the shared gyroscopic term cancels. The implementation uses the source model in [simulation_parameters.m](../../matlab/core/simulation_parameters.m:1), [distributed_mass_properties.m](../../matlab/core/distributed_mass_properties.m:1), and [vehicle_derivative.m](../../matlab/core/vehicle_derivative.m:1). The reconstructed diagonal inertia is approximately `diag(0.00325755333, 0.00325755333, 0.00636064833) kg m^2` for both scenes.

| Scene | max \(|\tau_{requested}-(\tau_{nominal}-\tau_{behavior})|\) | max \(|\tau_{real}-\tau_{requested}|\) | max \(|\tau_{wind}|\) | max H5 \(|target_raw|\) | max reconstruction error |
|---|---:|---:|---:|---:|---:|
| TRAIN T1_C00_W00 | 0 | 3.03e-16 N·m | 6.07e-18 N·m | 9.31e-14 rad/s² | 8.15e-17 rad/s² |
| VAL T1_C00_W07 | 0 | 2.97e-16 N·m | 1.39e-17 N·m | 8.43e-14 rad/s² | 7.37e-16 rad/s² |

`target_clip` equals `target_raw` in these records. The reconstruction is independently calculated from raw/config physical quantities; it does not rely on a “recorded versus verified” manifest flag. It uses the repository’s stated dynamics/equations, so it verifies internal data/equation consistency, not physical-model fidelity to hardware.

## Qualification boundary and minimum follow-up

These two files pass **sample-level event alignment and target replay**. They do not qualify all 768 TRAIN and 48 VAL H5 files as raw-linked, source-pinned, or physically replayed. Both selected scenes are `C00` (no arm motion); their near-zero target cannot validate learning a nonzero morphology-induced attitude residual. The nonzero wind field in the raw scenes does not change this point: the logged body wind torque is essentially zero, and the target compares two matched nominal rigid-body calculations.

Before using the attitude dataset as evidence for a morphology-residual learner, the minimum further data-only check is to replay at least one nonzero arm-motion record and one record with non-negligible body wind torque, then perform a stratified raw/config/source-link audit across all TRAIN/VAL H5s. Report the unpinned-source subset explicitly. Do not use the current TEST split for data qualification or model selection.

## Artifact identities

SHA256 hashes below identify the exact files inspected in this check.

| Artifact | SHA256 |
|---|---|
| TRAIN `B.h5` | `0205E02BCE7193FD00190DFC8503B109A6545F8FAC9BFE9A4AA0B9B73284138E` |
| TRAIN `run_start.mat` | `A6C2F6A421DADFA8A1FD49F03ADB62EC6CE377886AC424C8DEBCDA85BE1EDAD7` |
| TRAIN `raw_run.mat` | `5F1221277F91B664958BC50C5B627F1EF1DF40EBCB2EB32F310EA683D7A46236` |
| TRAIN `plant_started.marker` | `4BE70A7D8354EC28A1906E1883FFE4CD84B134986A6B28729838902D87C72EFB` |
| VAL `B.h5` | `B26A1B46FFB1AEFB9946C1730443763E39039883C46DF4FE633951C3863CC664` |
| VAL `run_start.mat` | `9CAF9E59EABCDBDCEBDC0E2D704902A5ACC5E15B35A71E22C173FAAA347374AB` |
| VAL `raw_run.mat` | `E3EC711F1108C2C9A0C78D9D1CE07211A12313C6C00C22D112EB515A16DDF927` |
| VAL `plant_started.marker` | `4BE70A7D8354EC28A1906E1883FFE4CD84B134986A6B28729838902D87C72EFB` |

