# Nominal command-port residual labels — offline preparation v1

**Status:** `PASS_OFFLINE_C5_LABEL_PREPARATION`. The builder completed with exit code 0. This is a labels-only package: 0 optimizer steps, no Plant calls, and no TEST reads.

## Target and scope

For each zero-based start `e = 10, 20, ..., 19990`, the label is

`R_cmd[e] = (ω[e+10] − ω[e]) / (t[e+10] − t[e]) + (1/10) Σ(i=e..e+9) solve(J0, ω[i] × (J0 ω[i]) − τ_req[i])`.

It uses the full locked fixed `J0` and `requested_generalized[1:4]`. This is a finite-difference nominal command-port residual; allocator and actuator mismatch remain lumped in the target. It does not use realized torque to construct labels. Each scene has 1,999 intervals, including the additional final interval `[19990,20000)`. The first 1,998 match the prior next-event residual convention with maximum absolute error `2.1316282072803006e-14` across 72 scenes.

Unclipped labels are stored as float64. The training labels are clipped independently by the exact locked `DMAX = [45.0, 45.0, 4.7124]`, then cast to float32. Existing 13-feature `X` is read from the original C5 NPZ and is not copied or altered; interval-future data is label-only and is not a deployment input.

## Cohort identity

The NPZ split names are experiment aliases. The 24 `c5_train_*` rows have scene IDs `DL1018_DEV_*`; the 48 `c5_val_*` rows have IDs `DL1018_VAL_*`. Together these are DEV24+VAL48 development data, not original TRAIN768 membership and not an independent validation/holdout set. The manifest records this role clarification. Do not treat C5_VAL48 metrics as generalization results.

The NPZ loader read only `c5_train_x`, `c5_train_scene_ids`, `c5_val_x`, and `c5_val_scene_ids`. B24 arrays and the old C5 teacher-Y arrays were not loaded. The builder checked the 72 locked C5 raw/status identities. It read state, time, requested generalized command, and event flags; historical `rbf_output_raw` was used only for the diagnostic comparison columns in the CSV. No realized generalized torque, B/TEST values, wind, mass, or true/estimated inertia fields were used.

## Checks and summary

- Shapes: train `(24,1999,3)`, development `c5_val` `(48,1999,3)`; unclipped float64 and clipped float32.
- Clip counts by axis: DEV24 `[0,0,0]`; VAL48 `[0,0,242]` (242 z-axis labels clipped).
- `TARGET_STATS_v1.csv` has 864 rows: per scene, axis, and `all`, `0–5s`, `5–15s`, `15–20s` phase. The following all-phase summary is computed from per-scene RMS values; scenario-macro is the arithmetic mean of scene RMS, while pooled RMS is `sqrt(mean(scene_RMS²))`.

| Cohort | Axis | Scenario-macro RMS | Pooled RMS | Mean bias |
|---|---:|---:|---:|---:|
| DEV24 | 1 | 6.250961 | 8.020857 | -0.249486 |
| DEV24 | 2 | 6.193899 | 7.122800 | 0.827455 |
| DEV24 | 3 | 0.339521 | 0.482227 | -0.008473 |
| VAL48 (development data) | 1 | 6.929868 | 8.258491 | 0.368226 |
| VAL48 (development data) | 2 | 8.691129 | 10.384243 | -0.392482 |
| VAL48 (development data) | 3 | 0.561575 | 0.740177 | -0.022990 |

The target NPZ plus statistics CSV total 4,536,245 bytes, below the 1 GiB data-output budget. Independent output validation confirmed exact clipping/casting, IDs and X hashes against the source NPZ, event starts, 864 CSV rows, artifact hashes, and the no-training/no-Plant/no-TEST flags.

## Source and artifact identities

| Artifact | SHA-256 |
|---|---|
| Approved C5 source lock | `1b234e231cbc493ffd6e276efc9d4ce60244119d05478dd6f34f8d08158c71dd` |
| Source matched C5 NPZ | `b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f` |
| Source dataset manifest | `98766ddac3125b81d4637eeb2576349b6ce181c94564c1a444d1d4cab734d55c` |
| Locked config JSON | `55a794e875ca95e5846a29997e01065ab9700e26ac17eb9cb57ce02d7e05df99` |
| Bound config snapshot MAT | `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a` |
| Builder source | `1152dcb07f92d4bcc52bd16cbaa96c7c8ec15dd4e34b29653ad7a984f876da64` |
| Target NPZ | `88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7` |
| Statistics CSV | `599af4527376b88c0020b255a758586f333ca72151a70f09db48c8e829765344` |
| Final annotated manifest | `fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab` |

The split-role clarification was appended to the manifest after independent cohort review; target arrays, CSV, locked inputs, and their identities were unchanged. The receipt records exit code 0 and the final manifest hash.

## Reproduction

The successful builder command was run from the project root in PowerShell 7 and exited 0 (recorded in `PREPARATION_RECEIPT_v1.json`):

```powershell
python experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1/build_nominal_command_target_v1.py
```

To reproduce, use a clean workspace with the same locked inputs and an empty target output location. The builder deliberately refuses to overwrite its existing outputs. It performs offline data preparation only; it does not start training or Plant.