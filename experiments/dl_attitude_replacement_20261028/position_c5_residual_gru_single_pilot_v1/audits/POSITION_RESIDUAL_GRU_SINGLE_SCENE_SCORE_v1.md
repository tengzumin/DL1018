# Position residual-GRU single-scene pilot audit

Scene: `DL1018_VAL_T3_C01_W14`. Candidate raw SHA256: `62972f54e5204202d8c6933f2c22ad3bc435009be102dd542db629b2db4953e1`. Candidate release/source-lock: `5d2d48b8a671380df92d3b55bb1c94db4fbe56c8fa1223c0b8fde52d03d99dca` / `24a3c270fd83e6b7cc1a874c13bfd8f71f87dc05cf299716445560cad2a27314`.

## Frozen score_raw comparison

| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) | motor/gen/tilt/head events |
|---|---:|---:|---:|---|
| B | 11.405 | 61.792 | 17.915 | 0/0/0/0 |
| C5 | 9.990 | 65.383 | 17.965 | 0/0/0/0 |
| Parent_Cosine_GRU | 9.621 | 65.417 | 15.910 | 0/0/0/0 |
| Applied_Notch_3p5Hz_Q1 | 10.100 | 61.548 | 16.555 | 0/0/0/0 |
| Residual_GRU_Pilot | 8.733 | 74.522 | 15.723 | 0/0/0/0 |

Candidate Q is lower than B/C5/parent GRU/single notch, while task attitude error is higher than every comparator. All five score traces report zero listed safety events.

## Runtime recurrence and applied-force path

The raw contains 1999 100 Hz events at 0.01–19.99s. Logged X14 is finite for all events and matches model input exactly. The first 31 events update hidden state with zero emitted delta; event ordinal 31 at 0.32s is first ready. Independent recurrence replay max errors: raw head 8.88e-16, hidden norm 8.88e-16, delta 6.11e-16, beta 0.

Ready base action equals the post-PCF C5 event action (max error 0 m/s²). Total action follows `clip(base + beta*clip(delta,±0.5),±3)` (max error 6.66e-16); no total-action clip occurred. The residual action is held into the logged applied acceleration; held force equals injected force exactly, and applied force equals held force exactly. PCF is enabled and applied notch is disabled.

Raw head components reached the ±0.5 delta bound in 25.54% of ready axis outputs on this one VAL scene. This warrants caution: the residual is frequently saturated at its own bound here, despite zero total ±3 action clips.

## Source and scope

Verified all 72 candidate source-lock files, current release/raw/status/run-start binding, MAT weight hash, same-scene B/C5/parent/notch raw hashes, and prior frozen scorer SHA `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`. The lock's `root` field names `candidate_runner_work`, but its `files` are study-relative as shown by the hash-lock writer; verification used the writer's actual `relative_to(STUDY)` rule. Candidate status is STABLE, with no safety stop; `TEST_read=false`, no inertia reconstruction, and this audit made no Plant call.

The single VAL result is a diagnostic point, not an independent validation cohort or a general closed-loop claim.
