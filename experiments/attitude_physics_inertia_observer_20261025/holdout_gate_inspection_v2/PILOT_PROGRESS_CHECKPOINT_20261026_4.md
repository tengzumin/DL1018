# GHP7 pilot progress checkpoint 2026-10-26 (4)

- Active release revision 7, SHA-256 `7149c50c8f323fe0ee4736f8a433003be9b0e5c7b94542a6a48eaadcad5f5856`.
- The 54/54 pilot slots and full scorer output are complete. Independent CSV recomputation matched JSON means and paired wins. Counts: 54 attempts, 0 missing, 0 duplicate, 0 failed, 0 incomplete, 0 unmatched, 0 invalid; 38/54 application-feasible across all scored arms/configurations.
- Main finding: C5_10 (no RBF, no observer, model-based morphology inertia feedforward) is best in this six-scene pilot and feasible 6/6. C5_11 (feedforward plus observer, no RBF) loses to matched C5_RBF_F on macro Q0–20, Q8–12, and SO(3), so do not expand its old formal batch.
- The F term reconstructs Jhat/Jdot_hat by integrating morph commands under an ideal command-following assumption. Treat its score as a model-based diagnostic reference, not as evidence for a no-inertia DL method.
- Added `GHP7_FULL_PILOT_ROOT_CAUSE_AND_DL_NEXT_STEP_v1.md` with full comparison, provenance caveat, and DL recommendation. No training, TEST read, new Plant calls, or historical raw changes in this step. TEST remains sealed.
- Next: draft a separate small causal-TCN attitude replacement taskbook with reduced deployable inputs, explicit offline label provenance, and unchanged DEV/TEST separation. Reuse only eligible raw TRAIN data after a fresh input/target audit; do not reuse old oversized inputs or RBF functions by default.
- The one legacy C5_RBF/G1/W00 completion-flag mismatch remains disclosed in the scorer and `CANDIDATE_COMPLETION_FLAG_AUDIT_v1.md`; its complete raw was preserved and not rerun.
