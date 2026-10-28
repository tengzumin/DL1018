# TEST48 descriptive statistics

This folder contains a small future-use summarizer for a separately audited TEST48 raw-score JSON. It does not create scenes, execute Plant, read MAT files, or produce a paper/gate decision. The CLI has not been run on any TEST data.

`test48_statistics.py` accepts only an input whose top-level status is `PASS_TEST48_RAW_IDENTITIES_PHYSICS_ALL_METHODS`, whose `TEST_accessed` value is `true`, and whose `rows` contain exactly 288 unique `(scene_id, method)` pairs with the same 48 scene IDs across all six methods. The upstream audited status attests the frozen identity check. Each row must expose the original score fields from `parent_raw_metrics.score` directly, including the scene/method identity, Q values, XYZ phase RMSEs, peak/p95, saturation/clipping, and required scalar timing summaries. Path and SHA fields are retained as identities and excluded from averages. Numeric metrics must be finite and have a consistent field set across all rows; per-call arrays are never pooled.

The script gives each scene equal weight for ALL48, T1/T2/T3, W00–W15, the five fixed nonzero-wind bands W00_W02/W03_W05/W06_W08/W09_W11/W12_W14, HF_W09_W14, and W15. It reports all six methods, C5_M110 paired differences against the other five methods, W/L/T at `1e-12 m` and sensitivity at `1e-6 m`/`1e-5 m`, every scene-level Q difference and every C5 loss. It also reports means for all numeric scalar score/timing fields present in the rows, without pooling time windows or timed calls.

The only intervals are the six contract groups, in the frozen order ALL48, HF_W09_W14, W15, T1, T2, T3. Each group draws 10,000 paired-scene bootstrap index rows using NumPy PCG64 seed `2026102301`; each generated index matrix is shared by all five method contrasts in that group. The output records a SHA-256 of each matrix's canonical little-endian int64 bytes; the matrices themselves are not saved. Intervals are descriptive for this fixed simulation design and do not support multiplicity-adjusted or cross-training-seed claims.

The script reports four numeric performance checks from the contract: at least 41 C5 wins versus B, strictly lower ALL48 Q mean, and no larger HF and W15 Q means. It explicitly leaves paper-gate and goal decisions to the root reviewer. Each row must include `controller_mean_s`, `controller_p50_s`, `controller_p95_s`, `controller_p99_s`, `controller_max_s`, `controller_over_1ms_fraction`, `controller_ready_calls`, `controller_nonready_calls`, plus `controller_ready_{mean,p50,p95,p99,max}_s` and `controller_ready_over_1ms_fraction`, and corresponding `controller_nonready_{mean,p50,p95,p99,max}_s` and `controller_nonready_over_1ms_fraction`. JIT effects remain included upstream.

Before future use, the script verifies these frozen source identities:

- Statistics contract: `TEST48_SCORE_STATISTICS_CONTRACT_v1.json`, SHA-256 `c7d2983a031b56b16950ede637cce598f6c169b1fea6dc3a092f4337489d992c`.
- Scientific freeze: `TEST48_SCIENTIFIC_FREEZE_v1_ZH.md`, SHA-256 `bbcf14230f3bc7585f68ce4baf33227e85d1f20899b9fd11d7ec95af221068f6`.
- Scoring source: `reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py`, SHA-256 `c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1`.

The hashes for the previously reviewed script and README are retained in `PRE_REQUIRED_TIMING_SCHEMA_SHA256_v1.json`.

The only execution performed for this deliverable is the import-level synthetic self-check recorded in `DEV_OR_SYNTHETIC_SELF_CHECK.json`; its `TEST_accessed` value is `false`. It exercises equal-scene averaging, the three W/L/T tolerances, and deterministic bootstrap-index generation with five synthetic observations.
