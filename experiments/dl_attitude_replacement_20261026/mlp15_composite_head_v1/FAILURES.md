## 2026-10-27 — synthetic fixture first run

- Command: `python experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits/make_composite_fixture.py`
- Result: failed before any MATLAB or Plant work.
- Error: `ValueError: too many values to unpack (expected 2)` in `euler_map`; the independent fixture passed a 3-element Euler state to a helper that only needs roll and pitch.
- Repair: read `eta[0]` and `eta[1]` explicitly, then rerun the full fixture.

## 2026-10-27 — synthetic fixture projection coverage

- Command: `python experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits/make_composite_fixture.py`
- Result: failed its required dmax coverage assertion; the first synthetic disturbance did not produce a clipped current residual.
- Scope: no MATLAB or Plant work occurred.
- Repair: move the synthetic disturbance later, after the 15-event feature window stabilizes, preserving the frozen dmax and weight limit.

## 2026-10-27 — delayed synthetic disturbance retry

- Command: `python experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/audits/make_composite_fixture.py`
- Result: weight projection was exercised (30 events), but no `dmax` clip occurred; maximum raw magnitudes were `[12.30, 17.48, 3.63]` against `[45, 45, 4.7124]`.
- Scope: synthetic reference only; no MATLAB or Plant work occurred.
- Repair: make the late synthetic impulse z-axis dominant so the fixed z-axis dmax branch is exercised under the unchanged Frobenius-20 projection.

## 2026-10-27 — first MATLAB cross-language check

- Command: explicit `C:/Program Files/MATLAB/R2025b/bin/matlab.exe -batch "... check_composite_head_no_plant"`.
- Result: failed before producing `NO_PLANT_CHECK.json`; no Plant or training was started.
- Error: MATLAB `sizeDimensionsMustMatch` at the `clipped_residual_rad_s2` comparison.
- Repair: expose and validate both vector shapes before elementwise comparison; fix the fixture/import contract if they differ.

## 2026-10-27 — MATLAB fixture shape diagnosis

- Command: explicit R2025b no-Plant check with a clip-vector shape assertion.
- Result: failed before producing a check report; no Plant or training was started.
- Root cause: `savemat` received duplicate `expected_clipped` keys; the 300-event Boolean vector replaced the 3x300 clipped-output array, yielding `300x1` in MATLAB.
- Repair: rename the Boolean event field to `expected_clip_active`, regenerate the fixture, and rerun the cross-language check.

## 2026-10-27 — MATLAB source-diff path calculation

- Command: explicit R2025b no-Plant check after fixture repair.
- Result: all 300 event computations completed; the check failed at source-tree diff validation.
- Investigation: PowerShell SHA comparison confirmed exactly the two expected copied files differ. MATLAB had received the audits folder through a relative `addpath`, so `mfilename('fullpath')` remained relative and the prefix removal built invalid comparison paths.
- Repair: canonicalize the audit directory to an absolute path before constructing source paths; rerun the check.

## 2026-10-27 — MATLAB source-diff assertion retry

- Command: explicit R2025b no-Plant check after canonical path repair.
- Result: failed at the exact-path assertion; the reported differing paths were the expected MLP step and event-entry files. PowerShell independently confirmed both file hashes and no other changed MATLAB source.
- Root cause: the MATLAB comparison used `isequal` on string arrays whose shape/type differed despite identical displayed paths.
- Repair: compare normalized column string arrays element by element, then rerun.

## 2026-10-27 — prepared-release hard-block check

- Command: explicit R2025b no-Plant check, including a direct call to the closed-loop entry with a dummy scene.
- Result: did not reach the Plant loop; the negative test saw the wrong guard identifier because the runner looked one directory too deep for `RELEASE.json`.
- Repair: resolve the copied runner root first, then read the release from its parent study directory and rerun.

## 2026-10-27 — release preparation record assembly

- Command: explicit R2025b batch running `check_composite_head_no_plant` followed by `prepare_composite_release_no_plant`.
- Result: the no-Plant check passed and wrote its report; release preparation failed while assembling the first prediction-only metric record. No Plant or training was started.
- Error: MATLAB `heterogeneousStrucAssignment` because an empty no-field struct array was assigned a populated record.
- Repair: stage per-scene metric records in a cell array and concatenate them after all six records are built; rerun preparation only.

## 2026-10-27 — report JSON struct shape

- Command: explicit R2025b batch running the updated no-Plant check and release preparation.
- Result: the no-Plant numeric/analyzer checks passed; preparation stopped while reading the check report. No Plant or training was started.
- Root cause: a three-element cell field passed directly to MATLAB `struct` expanded the report into a 1x3 struct array, so JSON encoded a top-level array instead of one report object.
- Repair: wrap the support-analyzer cell array as one struct field, emit a fresh v4 report, and rerun.

## 2026-10-27 — release lock path review

- Review found the prepared release named `NO_PLANT_CHECK_v4.json` as if it were at the study root, although the report is under `audits/`.
- No Plant work occurred; the raw auditor would have rejected the bad path before reading candidate metrics.
- Repair: bind `audits/NO_PLANT_CHECK_v6.json` in the final release and make the guarded runner log the local release SHA for future raw replay.
- The v5 check also found one unused local in `audit_composite_raw.m`; it was removed before v6.
