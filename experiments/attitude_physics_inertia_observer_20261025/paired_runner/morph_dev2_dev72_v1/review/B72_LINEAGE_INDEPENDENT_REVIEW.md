# Locked B72 lineage review

## Result

The C5 DEV72 input lock contains 72 unique scene records and a per-scene `B72_scoring` raw/status reference for every record. All 144 referenced files exist and their SHA-256 values match the lock. The 58-scene candidate manifest preserves the same per-scene paths, hashes, scene IDs, and external identities.

The B traceable lock's 71 `scenes` entries are 71 new runs. Its `completed_reference` binds the remaining `DL1018_VAL_T2_C00_W10` scene. Together they account for all 72 C5-locked scenes; the missing row is not a missing baseline. C5's B lock hash points to this exact B lock.

## Identity and status checks

- C5 lock: `C5_DEV72_INPUT_LOCK_v3.json`, SHA-256 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`.
- B lock: `B_TRACEABLE_DEV72_INPUT_LOCK_v3.json`, SHA-256 `8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452`.
- Candidate no-Plant manifest: `manifest/DEV58_PREPARED_MANIFEST_B72_V2.json`, SHA-256 `4ce70de0d846a9c26a46b545b610a246eac1141499de926ada5014b3f4257904`.
- Every B run status is complete for 20,000 transitions and 20,001 samples, stable, one Plant call, zero training, and `TEST_accessed=false`. Scene IDs, raw path/hash, and external identity match the C5 lock.
- The B cohort is 71 new runs plus 1 completed reference. Do not describe it as 72 new runs.

## Limits to the claim

The B lock retains `historical_72_runtime_tree_gap_closed=false`. The per-scene B raw/status lineage is nevertheless closed by the C5 lock and the completed-reference chain. The run-status text remains `RUN_COMPLETE_RAW_PENDING_AUDIT`; this is distinct from the independent C5 DEV72 parent raw audit, which records a PASS. Preserve both labels and their different scopes.
