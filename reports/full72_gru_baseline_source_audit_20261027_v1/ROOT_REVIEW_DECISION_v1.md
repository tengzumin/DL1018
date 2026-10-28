# Root review: FULL72 B/C5 baseline source audit

Date: 2026-10-27 (Asia/Shanghai)
Decision: **Accept the 72-scene B/C5 source audit for conditional DEV/VAL comparison; keep all claims development-only.**

## Independent checks

Root checked `SCENE_SOURCE_AUDIT.csv`: 72 unique scene rows; 0 non-PASS scene results; 0 B or C5 raw/status SHA mismatches; 0 B source-chain failures; 0 B 33-array parent-equivalence failures; 0 C5 source-chain failures; 0 C5 event-audit failures. C5 has 60 `PASS_C5_RAW_ALL_EVENTS` and 12 `PASS_REUSED_C5_SCREEN_AUDIT` rows. One B row is the reused B1 reference.

The score-referenced C5 rows bind to the same C5 input lock and raw/status files that the parent review audited. The parent audit used a different scorer from `FULL72_PAIRED_SCORE_v1`; it verifies source and raw integrity, not a replacement for the score's fixed metric implementation. Preserve the GRU paired scorer outputs for all numeric Candidate/B/C5 comparisons.

## Claim boundary

- The old FULL72 report's statement that 60 C5 audits are pending is stale. Its raw/status files and numeric results do not need a rerun; this root review supplies the missing audit reference without changing the frozen score or any raw.
- B's 72 raw/status source alignment and 33-array reproduction pass, but B1 reuses one historic run and its historic runtime identity remains unclosed. Keep that qualification on B-based claims.
- The GRU was trained on these same 72 scored scenes. This is an in-sample development result, not independent validation or generalization evidence.
- The locked numeric DEV72 gate remains **FAIL**: Q beats B in 68/72 scenes, task SO(3) beats B in 41/72 (below the 62 requirement), and the W09–W14 task SO(3) macro remains worse than B. Passing baseline provenance does not alter these performance results or unlock TEST.

## Next use

New candidate taskbooks may cite this audit report and root review for the existing DEV/VAL B/C5 source chain. They must retain the baseline scorer from the locked GRU score, the B1 historic-identity qualification, the in-sample training limitation, and the current performance-gate failure. No B/C5 rerun is required for this baseline audit.

## Reproducibility script verification

Root independently ran `python .\verify_baseline_source_audit.py` from this audit directory. Result: `PASS`, 72/72 scenes, 144 raw and 144 status files rehashed, zero errors, TEST not accessed. Script SHA-256: `504b526e68617470edc9f5fba322d3dba9fcc1a88d8e38b522935e74d5b03a93`; command instructions: `REPRODUCE.md`.
