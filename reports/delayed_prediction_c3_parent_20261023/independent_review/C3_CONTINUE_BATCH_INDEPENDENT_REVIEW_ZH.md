# C3 continuation batch independent audit

Audit scope: read-only verification after the frozen v2 continuation reached terminal `ALL_11_COMPLETE_RAW_PENDING_AUDIT`. The audit script required both progress and summary to be terminal-success before it opened candidate raws. It audited 11 continuation raws and reused the already-passing probe audit; it did not start MATLAB/Plant, training, optimizer steps, or TEST access.

The audit runner uses the reviewed `verify_c3_raw.py` and pinned recovered C2 scorer. This is an independent batch execution/check run, not a separately reimplemented scoring algorithm. For each continuation row it checked candidate SHA before/after, run-status/run-start/first-Plant-marker identity, frozen C2 raw identity, external physical-input identity, exact event indices/clock, delayed interval target, output-before-update, applied beta/clip, full discrete update, weight continuity, and prediction-term norm. The verifier’s recurrence/error checks are below `1e-10` for every row.

Frozen inputs used:

- Batch audit script: `417dbfddce0e892fce797310f939c2caaea563e14bab4fee908daffe7650dad1`

- C3 continuation release: `816baa148451c74b59cbb2f100cbdc5c1a122610ca2b6d582eb4635612cd600e`
- v2 runner: `efb132bee970ab627a917d47c2918a50f04976f65facb55c049a90bbc9e150ef`
- source lock: `863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2`
- run contract: `fc2fd5998915a3074f3d43706baea53cceb7d49176115fead94e47db2c33fbe2`
- prepare result: `b844c86de21d321d9cc03d1ef6dd69dfeecb9aa45e71f5589bf6eb7ec7602fb3`; prepared snapshot: `71c95e5cb9cc537fcc1fc2ea82f86c78c0f3f624de4de7a00951127950d4a64e`
- raw verifier: `275de5a3e56fd3c1e41f62f6a2a5f5ad95d44416dc022a4f6daace1e46f77b96`
- frozen recovered C2 scorer: `320755d6e570abb14c66a2abf2c3350a007f9c2cc4db750b0246de48837eddba`
- prior probe audit: `6dd08d101bc52cc0716e1157d4166aa086cf891358d5e01f8d1eeed1cb8218ed`
- terminal progress/summary: `fc1aa532e12b91d8131085d545038972dd391ed5eda7b7bd302467bbd3fb64cc`

Results: all 11 new candidate raws passed; together with the pre-audited probe this gives 12/12 scenes, each with 1,968 valid events. The 12 external-input identity hashes are distinct across the 12 fixed scenes. All task-by-wind rows in the 3-task × 4-band design passed raw audit. Across the 11 new raws, maxima were: beta-clock error 0; event-dt error `1.99e-15 s`; interval-target error `5.31e-13 m/s²`; output-before-update and applied-beta/clip errors `4.44e-16 m/s²`; full joint-update error `5.25e-15`; weight-continuity error 0; prediction-term norm error `4.33e-15`. Motor-saturated and generalized-clipped fractions were zero for all 12 scenes. Timing remains explicitly non-isolated and not formally qualified.

One C2 comparator exception remains visible: `DL1018_VAL_T2_C02_W12` retains original collection status `FAILED_NO_RETRY`. Its separately pinned recovery review (`2105f1eb4b6ce0ee29dab04066e06c3fde47f3ec8e298293f6b945f3495a4ec4`) authorizes use of the exact raw SHA `f01d4d5463e78b7fd2e448ba93c07eb37a92d337c2228736baf6f74959610167` for scoring only after stable-runtime, 20,000-transition, 1,968-event and run-start identity checks. The batch output records it as `RECOVERED_STABLE_RAW`; it does not rewrite collection history. The other 11 C2 comparator rows are `STABLE`.

A first audit attempt stopped before opening any candidate raw because the C2 recovery exception had not yet been encoded; its no-raw-open failure is preserved in `C3_CONTINUE_BATCH_PREFLIGHT_FAILURE_01.json` (SHA-256 `bb4138d5996d01e8037c4f3e2cfcd2249064a21045e5319f8c5188e9ae895e44`). The successful audit used the corrected script and left the original run records untouched.

The final machine-readable result is `C3_CONTINUE_BATCH_REVIEW.json` (SHA-256 `10fa402f2a9aca1cd000f31bdbccf3f03e29d5840e4dd09051c22374413c9044`). It contains each scene’s raw/status/start/marker/C2 hashes, per-scene metrics and checks, recovery labeling, and task-by-wind grouping. The per-scene verifier JSON files are under `c3_continue_scene_audits/`. This verifies implementation/record consistency; it does not establish causal performance improvement or formal timing qualification.
