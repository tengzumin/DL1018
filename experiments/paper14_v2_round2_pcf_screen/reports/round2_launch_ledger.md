
## PROBE launch attempt

- Start: 2026-10-21 22:07:57 UTC
- Scope: one scene, DL1018_VAL_T2_C00_W10; no automatic continuation.
- Command: pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode PROBE -ParentReviewed`n- Parent review: main_review_round2_20261022.md.
- Pre-run state: no uns/, MATLAB=0; fresh launcher preflight required.
- Result: running.

## CONTINUE completion and root decision

- Completion: all 12 fixed scenes completed `STABLE`, 20,000 transitions; no retry, no training, no TEST, no process was interrupted.
- Score: independent raw rescore completed 12 paired rows. All B/ON/OFF arms are safe, finite, complete and identity verified. Registered screen gate failed: HF OFF Q is +1.134 mm vs ON and +1.214 mm vs B; W15 OFF−B is +1.508 mm; all-12 OFF−B is +0.640 mm. HF Z wins ON in 4/6; W00–W08 is noninferior to B. Decision: `SCREEN_NOT_PASSED_NO_72_NO_TUNING`.
- Scorer failure: frozen original scorer threw `KeyError: name` before writes and also had an RMSE axis-key case mismatch. The locked original/lock were preserved; an isolated audited copy and independent raw recalculation agree exactly.
- Same-state replay: 12 PCF-on VAL raws, 23,616 events, no Plant. PCF residual, eta recursion/event timing, surface/feature identity, coordination/clipping, output-before-update and weight update replay all match; maximum output discrepancy `4.44e-16`, weight discrepancy `0`, common W0 discrepancy `0`.
- Root review: `reports/round2_root_review_20261022.md`. Keep TEST sealed and stop the PCF-off direction. Proposed single remaining candidate is XY-only eta correction (`mask=[1,1,0]`), pending a separate frozen taskbook and main review.
- MATLAB process snapshot at root review: none active. Inputs remain read-only; no MAT/checkpoint/cache deletion or upload.

- PROBE completed: 2026-10-21 22:12:57 UTC; scene=DL1018_VAL_T2_C00_W10; STABLE/20,000 transitions; episode=17.309 s; attempt+raw persistence=21.190 s; 45,285,950 bytes; raw/status/run_start identity and update/eta/clipping checks passed.
- Independent Q: OFF 9.832278 mm, ON 8.693982 mm, B 8.516659 mm; single-scene mixed evidence, not a registered stopping gate.
- Reviewer decision: CONTINUE fixed remaining 11 scenes after fresh reviewed preflight; no retry or auto-expansion.

## CONTINUE launch attempt

- Start: 2026-10-21 22:13:12 UTC
- Scope: fixed scenes 2–12 only; no retries or automatic expansion.
- Command: pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode CONTINUE -ParentReviewed`n- Parent review: probe_review_round2_20261022.md.
- Pre-run state: PROBE COMPLETE; reviewed CONTINUE preflight required.
- Result: running.
