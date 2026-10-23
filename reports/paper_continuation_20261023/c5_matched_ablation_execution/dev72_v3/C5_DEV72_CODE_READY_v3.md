# C5 matched-ablation DEV72 v3 — source handoff

Status: `SOURCE_FROZEN_READY_WAIT_PARENT_REVIEW`. This is an isolated source/lock repair for the v2 field mismatch. No v3 MATLAB or Plant process has started; synthetic MATLAB checks, prepare, and runner preflight remain unexecuted.

## Scope and lineage repair

The v3 tree is `experiments/position_c5_matched_ablations_dev72_v3_20261023`. The only behavioral correction is C3 ancestry lookup: prepare and runner match each scene by `scene_id` against the SHA-locked upstream `C5_DEV72_INPUT_LOCK_v3.json`, then require the new lock's `C3_reference` to equal that upstream row exactly and verify the referenced C3 raw/status/start/marker hashes. The prepared `sceneIdentity` remains the original seven-field structure: `B_raw_path`, `B_raw_sha256`, `alias_normalized_in_memory`, `canonical_scene_id`, `payload_review_sha256`, `raw_scene_id`, `scene_id`. The v2 error's nonexistent `sceneIdentity.C3_raw_path`/`C3_raw_sha256` access is gone; remaining `C3_raw_*` strings only name runner output fields sourced from `row.C3_reference`.

The existing runtime core, episode wrapper, and each variant helper are byte-identical to the reviewed v2 copies. No model, scene, numerical method, budget, or execution rule changed. File/entry names and output paths use v3. Protocol strings intentionally remain as implemented: input/contract/source-binding/release schemas and PREFLIGHT mode use V2 spellings; the formal release state remains `APPROVED_C5_ABLATION_DEV72_REMAINING60_V1`. The runner requires release schema `C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_V2`, state `APPROVED_C5_ABLATION_DEV72_REMAINING60_V1`, and phase `REMAINING60`.

The 72-scene order is exactly the frozen C3 `scene_ids_all_72`; the 12 audited reuse scenes are stable-filtered from that order, leaving 60 in original order. Both locks/contracts agree on `72 = 12 + 60`, with `first_scene_id = DL1018_DEV_T1_C00_W03` (the first remaining scene).

## Frozen artifacts

Manifest SHA-256: `51d1b428c5b7a29a47cb7c8a564a82b8a9529c61dd62e6b79a0c448859a1023f`.

| Variant | Input lock | Run contract | Source binding | Fixture |
|---|---|---|---|---|
| `C5_FREEZE_TRAINED_W0` | `28b2d3b99a20a2390b31db0a07aa1cd76a581fb0134b881e7f4ffc861b8670b3` | `31fd63333e1edfb93b06bf2cdcf11517fb4c42952d97cae67ad0625b6e77f9fa` | `7b24881172848442554327286372dc0e478c909f3ccbf6f7c4465b06d67b70d4` | `bc134495cce41b43560160e4d080f8f2b98507a5cafaf837545dfc5cfa7e70f5` |
| `C5_NO_DELAYED_PREDICTION` | `e0020306b8b7e7fba2948b93cbde30e0ec8f8470ede5dcef5e128d20c8728074` | `91669018d3d5f19a29c7162f4ed307f7f7371850ff0ffe647fe86bc49825bbcc` | `db605d55641ddda3c34d3cb6694a678678b683076951f836b58edc79db6ec06f` | `b57ab0642f2faa01b98e79e0ed06ee172017e01514bdbfa5e97e96190f9d5419` |

Shared v3 prepare SHA-256: `fc42b2b04864a0b1894d0c1fec66692d5d0b555ad6ee8697edafcde6f9901762`. Shared v3 runner SHA-256: `4c848c7ef2ab6c23dbd4e3ac583731042d6509f0e1b0fa067c4b05187e05c5e4`. Shared synthetic checker SHA-256: `9d8f136cfc911af368be930b6c1311ef557b07d6c3cd19af17eed8507c883e4a`. Both fixtures were generated from the pinned Python kernel SHA-256 `6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc`.

The fixture-generator and builder SHA-256 values are `2851da4f9f9e26f7bad5e2ec5cfb9b51e761126f62c84e901fbaaa9cd2056767` and `a9797034f0895d801d562ef1e5eb7966e773daa983d4adefb9df8f383257c509`, respectively.

## Static checks completed

The independent local check confirmed for both variants that all 72 C3 references exactly match the corresponding upstream C5 lock row; all 72 scene IDs and the remaining/reuse order match the frozen C3 order; manifest, lock, contract, binding, and 69 code/JSON/document refs per binding have matching SHA-256; and all 15 v3-local refs per binding match. The core, wrapper, and helper files are byte-identical to v2. All four v3 PowerShell launchers parse with zero errors, both Python entry scripts pass AST parsing, and all expected v3 prepare/snapshot/synthetic-result/preflight/OS/release/batch outputs are absent.

The previous v2 prepare failure and its evidence remain in the v2 tree unchanged. No v3 failure record has been created. The v3 input lock, fixture, contract, source binding, and this handoff report are the only frozen v3 records at this stage.

## Exact no-Plant commands (awaiting parent authorization)

Run in PowerShell 7 from the repository root, sequentially, FREEZE first and NO_PRED only after FREEZE naturally returns OS 0:

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_FREEZE_TRAINED_W0/RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v3.ps1'
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_dev72_v3_20261023/C5_NO_DELAYED_PREDICTION/RUN_C5_ABLATION_DEV72_NOPLANT_EXACT_v3.ps1'
```

These launchers run only the synthetic checker, prepare, and the same runner's `PREFLIGHT_ONLY_C5_MATCHED_ABLATION_DEV72_V2` path, which returns before the shared lock or episode. They are not execution releases.