# Root review: HF28 scene-pair preflight

Date: 2026-10-27 (Asia/Shanghai)  
Scope: read-only scene identity and input-hash preflight for the 28 W09-W14 DEV/VAL scenes. No Plant call, candidate flight, baseline score recomputation, or TEST access occurred.

## Finding and correction

The first bounded preflight stopped at `DL1018_VAL_T1_C02_W09`. Its B raw contained the expected `runIdentity.scene_id`, `runIdentity.external_identity_sha256`, and `runIdentity.TEST_accessed=false`. The corresponding legacy C5 raw contained the matching scene ID and `TEST_accessed=false`, but did not contain `runIdentity.external_identity_sha256`. No other C5 fields were inspected to diagnose this mismatch.

The taskbook and scene-only auditor were amended. B raws must attest all three allowed `runIdentity` fields. C5 raws must attest the scene ID and `TEST_accessed=false`; if the external identity hash exists, it must match the locked payload identity. If absent, that gap is recorded and is never inferred. For both methods, the auditor compares only `scene.time`, `scene.initial_state`, `scene.reference`, `scene.arms`, and `scene.environment_wind_I` with the locked payload.

## Successful preflight

The amended MATLAB preflight returned `PASS_SCENE_ONLY` with these counts:

- 28/28 B raw SHA values and B identity attestations matched the execution manifest.
- 28/28 C5 raw SHA values, scene IDs, TEST flags, and allowed scene fields matched their locked scene payloads.
- 22/28 C5 raws carried a matching external identity hash. Six did not: `DL1018_VAL_T1_C02_W09`, `DL1018_VAL_T1_C05_W12`, `DL1018_VAL_T2_C00_W10`, `DL1018_VAL_T2_C02_W12`, `DL1018_VAL_T3_C00_W13`, and `DL1018_VAL_T3_C12_W09`.
- No B/C5 `log` variable or controller/actuator trace was loaded. Baseline metrics were not recomputed; TEST was not read.

This establishes scenario-level pairing for the screen. It does not repair the missing C5 identity attestations or complete the separate C5 provenance audit; C5 comparisons remain marked provisional as required by the taskbook.
