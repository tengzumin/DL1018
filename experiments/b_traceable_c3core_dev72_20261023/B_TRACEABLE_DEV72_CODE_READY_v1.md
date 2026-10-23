# B traceable DEV72 implementation handoff

Superseded by the v3 handoff. Preserve this v1 lock and its bound hashes as an earlier offline draft; do not execute the v1 no-Plant command because its `jsondecode` field-order comparison did not normalize row/column shape.

Status: `CODE_READY_FOR_PARENT_REVIEW`; the lock is not a Plant release. No B71 Plant run or MATLAB process was started by this implementation task.

This batch covers the 71 C3 DEV72 scene IDs left after reusing the independently reviewed B1 scene `DL1018_VAL_T2_C00_W10`. The IDs are fixed in canonical lexical order under the C3 lock SHA `a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730`. The completed B1 reference is bound to raw SHA `5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957`, status SHA `4de20ba0f17cb0cc498220032626f15b621c8d44dbaab2ea24d3457741a30175`, and parent raw-review SHA `01a6b218d8452366084f3af8b5e1382e71aba24591c79eb3a818cdbad1b382f9`. Its previously disclosed historical runtime-tree gap remains open.

The frozen input lock and run contract bind the B1-reviewed 32-source inventory, all 71 B_source inputs and their 14 external identity fields, the batch entry points, and B1 evidence. The no-Plant MATLAB prepare reads each locked scene, checks its complete scene schema and bytes, reconstructs `cfg` and `controller_options_dl1018(cfg,'B')`, and compares the complete trees with the frozen C3 and B1 snapshots. It does not invoke `run_episode_dl1018`, read a model/checkpoint, or authorize Plant. Scene identity rows clone the actual B1 `sceneIdentity(1)` structure before per-scene assignment. The existing Python MAT decoder at `reports/paper14_v2/phase1/audit_w15_position_replay.py` was used to inspect the B1 snapshot: `cfg` has 120 decoded leaves, B options have 13, and `sceneIdentity` has 11 fields, including `B_scored_log_path` and `B_scored_log_sha256`.

The separately locked runner is a sequential, no-retry 71-scene batch. It requires a parent-created release binding the exact lock, contract, prepare result, snapshot, runner, run command, scene-set digest, and B1 raw/status/review. Before each scene it rechecks inputs, available disk, output cap, deadline, and the shared heavy-job lock; each attempt receives fresh B options and unique run-start, marker, status, and raw paths. Failures stop the batch and preserve the attempt. The run command is included for future review only and must not be used without that signed release.

## Frozen and executable source hashes

| Artifact | SHA-256 |
|---|---|
| `freeze_b_traceable_dev72_inputs_v1.ps1` | `c9d2eaad531008ea4d7b1536faa7bb0ae072b7a950772924244a99d7dea17485` |
| `B_TRACEABLE_DEV72_INPUT_LOCK_v1.json` | `2b2c607e85e88cc12586bda9e33fcf2b9c0c9a1df1cc654daa9552688403a186` |
| `B_TRACEABLE_DEV72_RUN_CONTRACT_v1.json` | `fbac98acf6bff929b96ff68e0eaa679b8c5863802cf5f76c622bf328e25d3732` |
| `prepare_b_traceable_dev72_v1.m` | `086d937c5adaeea9011801e0e0c1258a47f5fe4ddebF6ac95ec1b7c197cb3792` |
| `run_b_traceable_dev72_v1.m` | `830f70f6f2c98f8afe7905ea2c715c5adcc8a4ab9ac45f127d65cd5b5e315189` |
| `RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v1.ps1` | `7cbc279dc106e8a4abee545b378d85a2d79b9144a62f0802557e38dc9cff9f2d` |
| `RUN_B_TRACEABLE_DEV72_EXACT_v1.ps1` | `9ebf25cf8a57fbed354601a3340ce3d89b3aa9c7d1587741e6cf2a244b1a55ca` |

The taskbook SHA is `39788bbd5e5fa4258f1db9a038be7f75339f11b6148bf1620770791aa3119a63`. The lock SHA above was checked against all 214 path/hash references; all matched. The lock contains 71 sorted unique non-TEST scenes, 32 active sources (31 `.m` plus one config `.mat`), and one completed B1 reference. No release file or `runs_b` output directory exists.

## Validation performed

- PowerShell 7 AST parsing passed for the input-lock builder, no-Plant command, and future run command.
- The input-lock builder returned `LOCK_BUILT_NO_PLANT_RELEASE` with process exit 0; its self-check confirmed 71 scenes and 32 sources.
- An independent read-only Python check verified every lock reference SHA, the 71-scene order, the B1 reference, and the no-release/no-attempt state.
- MATLAB no-Plant preparation has not yet run. Its exact single-layer PowerShell 7 command, for parent review, is:

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023/RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v1.ps1'
```

Do not issue a 71-scene Plant release until the parent has reviewed the actual no-Plant prepare result and snapshot. The batch run command is `& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023/RUN_B_TRACEABLE_DEV72_EXACT_v1.ps1'`; it is release-gated and is not authorized by this handoff.
