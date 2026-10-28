# Amendment 07 — strengthen batch parity identity checks

Date: 2026-10-26 (Asia/Shanghai).

## Finding

Static review found that the MATLAB batch verifier checked the reported sample and scene counts, but did not independently assert the frozen event indices, TRAIN/VAL-only manifest flags, continuous-replay scene membership, or the Python exporter identity. The Python exporter already checks these inputs when it creates the vectors; the MATLAB-side omissions could let a malformed or stale selection report pass the count checks.

## Change

`matlab/verify_tcn_teacher_parity_batch_v3.m` now also verifies:

- parity report schema, TRAIN-only/no-TEST/no-Plant flags, fixed event indices `[0, 1, 100, 999, 1998]`, and the 1,999-event replay length;
- current dataset-manifest SHA, the manifest's TRAIN=768/VAL=48 and no-TEST/no-Plant/no-inertia-read flags, and its recorded NPZ SHA;
- membership of the continuous-replay scene in the manifest's 48 VAL scenes;
- the current Python exporter SHA, in addition to the model and parity-vector SHA values.

The verifier changed from SHA-256 `D1F31183389D8ABFC99F5BEEFC714648003D9C67410D77AA622615BB4B00EB06` to `7EA02E54BFDC946D944BE78C794ABA21AE8BA24E6D50ED13CC22E74251EED4EB`.

This is a validation-only hardening. It does not change training, model weights, candidate runtime, dataset, controller, acceptance criteria, Plant-call authorization, or the TEST seal. The frozen parity gate remains blocked until the formal 60,000-step training reports PASS; no parity vectors or Plant calls were run for this amendment.

## Verification

MATLAB R2025b `checkcode` completed on the updated verifier with exit code 0 and no diagnostics. No MATLAB/Plant experiment was running when this static check was launched. The full Python/MATLAB parity comparison remains pending the frozen training gate.

A second read-only MATLAB batch check decoded the actual frozen dataset manifest and exercised the new VAL-row selection expression: it found 768 TRAIN and 48 VAL rows, selected `DL1018_VAL_T1_C00_W07` from VAL, and confirmed the manifest marks TEST, Plant truth, and nominal inertia as unread. No Plant or TEST records were opened.
