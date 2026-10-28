# GRU tracking-head full72 paired score

Read-only scoring of the frozen 72-scene DEV/VAL cohort; no baseline reruns, training, or TEST access.

**Scope: in-sample closed-loop development screen only.** The frozen model was trained on the same 72 DEV/VAL scenes scored here, so these results are not independent validation or generalization evidence. TEST48 remains sealed.

Training model SHA-256: `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`; training-config SHA-256: `b85b9b545eba1939582b4e8909667338bfbff1e81dc4cfb295ec750c0a57739d`.

**B baseline qualification:** 72/72 run-status labels remain `RUN_COMPLETE_RAW_PENDING_AUDIT` (all stable; raw/status SHAs locked). The bound parent review passes exact new-vs-historical equality for 33 numeric arrays on all 72 scenes and the lineage review validates 71+1 sources. Historical runtime identity remains unclosed and no fresh equation derivation is claimed. C5 still has 60 raw-pending parent audits; the numeric B gate is not complete paper evidence.

## Macro means

| Group | N | Method | Q (mm) | Task SO(3) (mrad) | Inner SO(3) (mrad) |
|---|---:|---|---:|---:|---:|
| ALL72 | 72 | Candidate | 11.128768 | 58.479739 | 14.459743 |
| ALL72 | 72 | B | 17.057913 | 62.368719 | 16.338108 |
| ALL72 | 72 | C5 | 11.558718 | 58.494287 | 16.387735 |
| DEV | 24 | Candidate | 10.338109 | 54.878860 | 12.552126 |
| DEV | 24 | B | 15.188406 | 56.740544 | 13.938690 |
| DEV | 24 | C5 | 10.725305 | 54.852777 | 14.050570 |
| VAL | 48 | Candidate | 11.524098 | 60.280179 | 15.413551 |
| VAL | 48 | B | 17.992667 | 65.182807 | 17.537817 |
| VAL | 48 | C5 | 11.975425 | 60.315041 | 17.556317 |
| HF_W09_W14 | 28 | Candidate | 9.715192 | 58.853581 | 13.816660 |
| HF_W09_W14 | 28 | B | 10.718777 | 54.815925 | 15.506096 |
| HF_W09_W14 | 28 | C5 | 10.179060 | 58.795380 | 15.688301 |
| W15 | 6 | Candidate | 5.637240 | 2.960117 | 15.268241 |
| W15 | 6 | B | 7.647124 | 6.021852 | 17.214007 |
| W15 | 6 | C5 | 6.333930 | 2.886175 | 17.212710 |
| W00_W08 | 38 | Candidate | 13.037434 | 66.970532 | 14.805935 |
| W00_W08 | 38 | B | 23.214770 | 76.830810 | 16.812869 |
| W00_W08 | 38 | C5 | 13.400275 | 67.052657 | 16.772847 |

## Frozen DEV72 gates

- at_least_62_of_72_wins_vs_B_Q: **PASS**
- at_least_62_of_72_wins_vs_B_task_SO3: **FAIL**
- ALL72_macro_Q_strictly_better_than_B: **PASS**
- ALL72_macro_task_SO3_strictly_better_than_B: **PASS**
- HF_macro_Q_no_worse_than_B: **PASS**
- HF_macro_task_SO3_no_worse_than_B: **FAIL**
- W15_macro_Q_no_worse_than_B: **PASS**
- W15_macro_task_SO3_no_worse_than_B: **PASS**
- all_candidate_raws_complete_finite_and_audited: **PASS**
- no_candidate_stop_motor_saturation_generalized_clip_or_tilt_limit: **PASS**
- overall_frozen_DEV72_gate: **FAIL**

C5 comparison is provisional: 60/72 locked C5 sources remain pending parent raw audit; no C5 gate is claimed.
SO(3) is the primary attitude metric. Wrapped Euler axes are diagnostics only.

Scorer SHA-256: `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`.
Paired rows: `FULL72_PAIRED_SCORE_v1.csv`; phase/axis details: `FULL72_AXES_PHASE_v1.csv`.
