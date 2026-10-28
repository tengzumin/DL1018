# Historical experiment inventory — handoff

- MLP15 causal: 6/6 VAL flights completed; failed C5/position gates (13.38% Q degradation vs C5). Base model trained on DEV24+VAL48.
- MLP15 composite: v3 completed 6/6 VAL flights; failed task SO(3) and Q gates (15.79% Q degradation vs C5). v1/v2 prep/failed launch are not results.
- GRU cosine tracking head: 6/6 VAL pilot complete; inner error improved but HF task SO(3) remained worse than B/C5.
- GRU full72: complete, not partial: 66 new raw audits passed + 6 direct-parent reuses = 72 scored rows. All 72 DEV/VAL scenes also trained the model, so this is in-sample. Later C5 audit report supersedes the score JSON's older C5-pending caveat; B runtime-identity limitation remains.
- NCMD: one 60,000-step model fit used DEV24+VAL48; six VAL flights completed and failed C5 task SO(3) gate (all 6 lose C5).
- WN12: 12/12 screen metrics recorded; fails Q<=1.05*C5. All 12 candidate raw paths in the current score JSON are now absent, so the old raw replay cannot be repeated from this workspace.
- Beta025: only the 28-scene offline command/filter shadow has PASS_GATE (0 Plant); the v1/v2 28-call packages were authorized but never executed.
- force09 wind correction: 3 of 12 current candidate raws have exactly zero environment_wind_I despite W15 suffix; scorer now groups exact-zero vs nonzero raw wind. No rescore was run.

Machine-readable details and evidence paths: `HISTORY_INVENTORY_v1.json`.
