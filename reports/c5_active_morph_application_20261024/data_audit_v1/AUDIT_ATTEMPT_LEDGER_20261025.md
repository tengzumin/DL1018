# C5 active morphology audit — attempt ledger

- Attempt: 1 (single authorized run; no retry)
- State at creation: PREPARED, immediately before execution
- Prepared UTC: 2026-10-25T03:57:53Z
- Script: `reports/c5_active_morph_application_20261024/data_audit_v1/audit_active_morph_subgroups_v1.py`
- Script SHA256: `10c2401f7ee4b0f29be7ea095068bbf3bbd0e41d43c200b04b6adac35f0f7417`
- Runtime: PowerShell 7.6.8; Python 3.12.7
- Command: `python reports/c5_active_morph_application_20261024/data_audit_v1/audit_active_morph_subgroups_v1.py`
- Output boundary: the script sets `OUT` to its own `data_audit_v1` directory; no overwrite targets or `.tmp` files existed at preflight.
- Preflight: five audit target outputs absent; directory had only the audit script, so no prior failed attempt or prior output was present in the scoped directory.
- Disk free at preflight: 207575531520 bytes on C:.
- Input handling: MATLAB/HDF5 and CSV/JSON inputs are opened read-only by the script; input file attributes were `Archive`, and no input permissions or bytes were changed by preflight.

## Frozen inputs (all preflight hashes matched the script pins)

| Name | Path | SHA256 |
|---|---|---|
| scene_specs | `configs/scene_specs.csv` | `d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3` |
| dev_input_lock | `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json` | `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75` |
| dev_parent_review | `reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json` | `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab` |
| test_long_metrics | `reports/paper_continuation_20261023/test_results_final_v1/paired_complete_48x6_long.csv` | `178f29fb3732a5eda5cb4f0d4a9ba17f72b2f470ad7418f7a829fe525be64db2` |
| test_wide_crosscheck | `reports/paper_continuation_20261023/test_results_final_v1/paired_Q_48x6_wide_mm.csv` | `8da2901ede8034388b6e512ef04fa53bd9dc7fdae0a1e41657047c8930641ce3` |
| test_input_index | `experiments/c5_test48_v3/input/TEST_INPUT_INDEX_v1.json` | `90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68` |
| test48_producer | `experiments/c5_test48_v3/test48_entry_v1.m` | `0490da98749b114ed9e9553fc7cb44349e0c5c9d182551d8a05c844a009b9bf2` |
| test_shared_scenes | `experiments/c5_test48_v3/input/TEST_SCENES_SHARED_v1.mat` | `da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c` |
| pinned_hdf5_reader | `reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py` | `d82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e` |

## Frozen TEST IDs

- Count: 48 sorted IDs
- Newline-joined ID SHA256: `90e59e5461650cf718a2eeb48b68a4f3c38e3e5b4046ca721116d143b731769e`
- `DL1018_TEST_T1_C00_W11`
- `DL1018_TEST_T1_C01_W12`
- `DL1018_TEST_T1_C02_W13`
- `DL1018_TEST_T1_C03_W14`
- `DL1018_TEST_T1_C04_W15`
- `DL1018_TEST_T1_C05_W00`
- `DL1018_TEST_T1_C06_W01`
- `DL1018_TEST_T1_C07_W02`
- `DL1018_TEST_T1_C08_W03`
- `DL1018_TEST_T1_C09_W04`
- `DL1018_TEST_T1_C10_W05`
- `DL1018_TEST_T1_C11_W06`
- `DL1018_TEST_T1_C12_W07`
- `DL1018_TEST_T1_C13_W08`
- `DL1018_TEST_T1_C14_W09`
- `DL1018_TEST_T1_C15_W10`
- `DL1018_TEST_T2_C00_W14`
- `DL1018_TEST_T2_C01_W15`
- `DL1018_TEST_T2_C02_W00`
- `DL1018_TEST_T2_C03_W01`
- `DL1018_TEST_T2_C04_W02`
- `DL1018_TEST_T2_C05_W03`
- `DL1018_TEST_T2_C06_W04`
- `DL1018_TEST_T2_C07_W05`
- `DL1018_TEST_T2_C08_W06`
- `DL1018_TEST_T2_C09_W07`
- `DL1018_TEST_T2_C10_W08`
- `DL1018_TEST_T2_C11_W09`
- `DL1018_TEST_T2_C12_W10`
- `DL1018_TEST_T2_C13_W11`
- `DL1018_TEST_T2_C14_W12`
- `DL1018_TEST_T2_C15_W13`
- `DL1018_TEST_T3_C00_W01`
- `DL1018_TEST_T3_C01_W02`
- `DL1018_TEST_T3_C02_W03`
- `DL1018_TEST_T3_C03_W04`
- `DL1018_TEST_T3_C04_W05`
- `DL1018_TEST_T3_C05_W06`
- `DL1018_TEST_T3_C06_W07`
- `DL1018_TEST_T3_C07_W08`
- `DL1018_TEST_T3_C08_W09`
- `DL1018_TEST_T3_C09_W10`
- `DL1018_TEST_T3_C10_W11`
- `DL1018_TEST_T3_C11_W12`
- `DL1018_TEST_T3_C12_W13`
- `DL1018_TEST_T3_C13_W14`
- `DL1018_TEST_T3_C14_W15`
- `DL1018_TEST_T3_C15_W00`

## Execution result

Pending; append exactly one outcome after the single run. Do not retry.

### Single-run outcome

- Completed once with exit code 0; no retry.
- Summary: 72 parent-review batch rows (64 wins, 8 losses, 0 ties); 48 TEST rows (46 wins, 2 losses, 0 ties).
- All nine frozen input SHA256 values matched again after execution; the shared MAT remained at its pinned SHA.
- Five main outputs and their SHA256 values are listed in `AUDIT_EXECUTION_ADDENDUM_20261025.md`.
- Addendum: created in this directory after successful output verification.

- Ledger note: the earlier Pending line records the pre-run state at file creation; the successful single-run outcome immediately below is final.
