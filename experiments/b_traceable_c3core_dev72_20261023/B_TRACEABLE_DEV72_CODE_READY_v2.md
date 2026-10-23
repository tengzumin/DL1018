# B traceable DEV72 implementation handoff v2

Superseded by the v3 handoff. Preserve the v2 lock and its bound hashes, plus the failed single no-Plant attempt recorded in `B_TRACEABLE_DEV72_PREPARE_EXECUTION_LEDGER_v2.json`; do not rerun the v2 command. Its MATLAB process returned exit 1 during upstream SHA verification, before scene checks or any Plant call.

The batch covers the 71 remaining C3 DEV72 scenes in canonical ID order and reuses the independently reviewed B1 scene `DL1018_VAL_T2_C00_W10` exactly once. C3 input lock SHA: `a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730`. B1 raw SHA: `5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957`; B1 status SHA: `4de20ba0f17cb0cc498220032626f15b621c8d44dbaab2ea24d3457741a30175`; parent raw review SHA: `01a6b218d8452366084f3af8b5e1382e71aba24591c79eb3a818cdbad1b382f9`. The B1 review's disclosed historical runtime-tree gap remains open.

The lock binds the same 32-source C3/B1 inventory and the 14 external scene-input fields for each B_source. The no-Plant prepare validates each scene's bytes and schema, reconstructs `cfg` and fresh `controller_options_dl1018(cfg,'B')`, and compares the full trees with the C3 and B1 snapshots. It does not invoke `run_episode_dl1018`, load a model/checkpoint, train, or authorize Plant. Its scene identities clone the complete B1 `sceneIdentity(1)` structure before per-scene assignment.

The actual B1 snapshot was inspected with the existing Python MAT decoder, `reports/paper14_v2/phase1/audit_w15_position_replay.py`: the decoded `cfg` has 120 leaves, B opts have 13 leaves, and `sceneIdentity` has 11 fields, including `B_scored_log_path` and `B_scored_log_sha256`. MATLAB comparisons of JSON field arrays and the hand-written field list normalize to columns with `(:)` before checking order.

The separately locked runner is sequential and refuses retries or overwrites. It reconstructs B options for each scene, rechecks the source inventory, scene hash/schema, resource floor, deadline, and shared heavy-job lock before each call. Every attempt records run-start, attempt marker, first-Plant marker, raw, status, and failure evidence. The PS7 batch command writes OS exit evidence only after the MATLAB batch process returns; per-scene exit records explicitly state `SHARED_BATCH_PROCESS_NOT_INDIVIDUAL_SCENE_PROCESS` so the shared process exit is not represented as independent scene exits.

## V2 frozen artifact hashes

| Artifact | SHA-256 |
|---|---|
| `freeze_b_traceable_dev72_inputs_v2.ps1` | `a24784906fe011e250de1c8be3ab1a0dbf9120e927f1e299e9061c9520bed062` |
| `B_TRACEABLE_DEV72_INPUT_LOCK_v2.json` | `8a3d5ec06e86d7c647ed03a97765b9a6bd7fbc60de242efa1dde4c120bd76c2a` |
| `B_TRACEABLE_DEV72_RUN_CONTRACT_v2.json` | `59c3e48385a705060618066eb5fb3cf7da5cbcce05ae3191fedb4aa800c402c7` |
| `prepare_b_traceable_dev72_v2.m` | `acb3c7994103b967fc0424e27519741f6f21455899dba033ba0397c8eb2163b8` |
| `run_b_traceable_dev72_v2.m` | `3c36de3098b43a255298604f694d39b90857f46c404f4f96e1e8fb77b98599c5` |
| `RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v2.ps1` | `f3e631dfe3b2ad9182ccfce80cd9bd2bbeb9d607c765eef8ab2c31ea1e08074f0` |
| `RUN_B_TRACEABLE_DEV72_EXACT_v2.ps1` | `ddf89b0e56e99b2ce5edac3fe98e961aeeacddccb4cdc51b8685d4b9000ddef6` |

The input-lock builder completed with process exit 0 and reported `LOCK_BUILT_NO_PLANT_RELEASE`, 71 new scenes, 32 active sources, and `plant_authorized=false`. Independent Python validation matched all 214 lock path/SHA references; it also confirmed the sorted scene set, B1 reference, and absence of a release, prepare result/snapshot, or `runs_b` directory. PowerShell 7 AST parsing passed for the v2 builder and both exact commands. The single v2 no-Plant invocation returned MATLAB/PowerShell exit 1 in the SHA helper during upstream-reference verification; stdout and OS exit JSON are preserved. No scene validation, prepare snapshot, release, `runs_b`, or Plant attempt was produced. The v3 fix is to use B1's chunked SHA helper with a clean empty-read break and signed Java bytes.

## Exact no-Plant command for review

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023/RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v2.ps1'
```

The parent should inspect the actual preparation result and snapshot after running this command before considering a separate Plant release. The future Plant-batch command is release-gated and is not authorized by this handoff:

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023/RUN_B_TRACEABLE_DEV72_EXACT_v2.ps1'
```
