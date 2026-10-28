# REPAIR01 metadata identity adapter

This adapter only repairs source identity interpretation for the frozen C5_VAL48 set. It does not build features or labels and does not score the model.

## Source mapping

1. Match each of the 48 frozen source rows by canonical `scene_id` to the `VAL` row in `C5_DEV72_INPUT_LOCK_v3.json`.
2. For 12 `C5_reuse.reused=true` rows, require the frozen C5 raw/status/run_start paths and hashes and the same-scene B72 row. Bind the external payload identity from the input lock and the exact 12-scene parent audit. If a raw/status/run_start identity is present, check every present field.
3. For 36 new rows, require an exact row in `C5_DEV72_BATCH_STATUS_v3.json`; raw and run_start `external_identity_sha256` must both equal the input lock. Status candidate, coordinate mask, physical-B source, B72 scoring raw, and all path/hash bindings must match the lock.
4. A scene ID may appear as its canonical form or as the exact `_ACC_FIX_V1` source/raw alias. `canonical_scene_id` must remain the lock's canonical ID.

## Identity schema handling

- `C5_TAIL11_RUN_IDENTITY_V2`: validate nested canonical/raw/scene IDs, `payload_review_sha256`, and the nested physical-B source path/SHA. Check raw, run_start, and status copies where present.
- `C5_AXIS_COORDINATE_DEV72_RUN_IDENTITY_V3`: validate top-level raw external SHA, run_start `scene_identity.external_identity_sha256`, source IDs, candidate/mask, and the status-to-lock B source chain.
- `C5_AXIS_COORDINATE_RUN_IDENTITY_V1`: only the single audited reused row may use this form. It lacks external SHA and nested identity; use the V2 builder's exact parent-audit fallback plus raw `scene_b_raw_sha256`, raw/run_start B72 scoring fields, status hashes, and the C5 input lock. Never infer external identity from `payload_review_sha256`.

`payload_review_sha256` is recorded in its own field and is never copied into an external identity field. No adapter branch reads `/log` or `/scene/arms/command` datasets. It opens only the named identity groups and their whitelisted text fields plus the three-value coordinate-mask metadata. Whole-file SHA checks read source bytes without decoding or loading numerical arrays.

## Current boundary

The REPAIR01 wrapper exposes metadata preflight only. It creates no score-start marker, reads no VAL numeric arrays, and does not run feature/label reconstruction, training, TEST access, Plant, or closed-loop code. Any later numerical scoring requires a separate root review and release.
