# Candidate completion flag audit v1

Date: 2026-10-26 (Asia/Shanghai)

## Finding

The first C5_RBF candidate raw run contains 20,001 state samples and 20,000 transitions. Its time and transition-time arrays match the frozen 20 s scene; all states, reference values, and transition traces are finite. The stored `last_transition` is 20,000. The runner incorrectly recorded completion with `last == n-1` even though `n` already denotes the number of transitions. The condition is now `last == n`.

This is a completion-metadata bug. It does not change controller commands, Plant integration, or the preserved raw MAT.

## Preserved run and rescore

- Candidate: `C5_RBF`, `DL1018_GHP7_G1_W00`, `ACTIVE`.
- Attempt: `C5_RBF_GHP7_G1_W00_ACTIVE_2418192f4d45457eaf4b3c3105e78f9f`.
- Raw SHA-256: `35046519a6485abd2d9370f363cf3f1ecd3c65e1958199ea2071f6282f617e02`.
- Historical runner/status completion flags remain false; the independent scorer reports structural completion true and `completion_flag_mismatch=true`.
- Recomputed metrics: Q0–20 = 0.00997520463252 m; Q8–12 = 0.0116848254522 m; SO(3) RMSE = 0.0626458295377 rad; stable, valid, no safety stop.
- Paired B: Q0–20 = 0.0125101568570 m; Q8–12 = 0.0176535721743 m; SO(3) RMSE = 0.0633611272051 rad; stable and valid.

The initial score snapshots are retained. `pilot_score_after_first_pair_v2` documents the temporary source-lock rejection; `pilot_score_after_first_pair_v3` is the valid rescore under release revision 7. Neither raw run was altered or repeated.

## Provenance and guard checks

- Source lock v4 remains immutable and is pinned to this one historical attempt by attempt ID, scene, arms, payload SHA, taskbook SHA, source-lock SHA, and raw SHA in release revision 7.
- Source lock v5 governs every new candidate run. v4 and v5 differ in exactly two files: the wrapper's lock filename and the runner's completion metadata condition. No controller or Plant source differs.
- The scorer verifies the v4 lock hash, exact file coverage, and that only those two documented files differ from v5. The legacy compatibility record permits only the named raw run.
- MATLAB no-Plant dry run reached the expected `GATE:OutputPath` rejection and created no attempt directory. MATLAB `checkcode` parsed the modified runner/scorer; it also reported style diagnostics, which were not silently suppressed.
- No Plant call was used for this correction or rescore.
