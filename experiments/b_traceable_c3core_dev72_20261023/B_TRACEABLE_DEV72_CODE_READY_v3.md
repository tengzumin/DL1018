# B traceable DEV72 preparation record v3

Status: `PREPARED_NO_PLANT_WAIT_PARENT_RELEASE_V3`. This record covers implementation and no-Plant preparation only. It does not authorize any of the 71 Plant runs; the v3 release file is absent.

The frozen input lock covers the 71 C3 DEV72 scenes remaining after the independently reviewed B1 scene `DL1018_VAL_T2_C00_W10`. Its scene IDs, B-source and scored-log paths and SHA-256 values, external identities, and 14-field contracts were checked against C3. The 32-source inventory matches B1 and every source hash was recomputed. All `source_files` references were rehashed. The C1 heavy-job-lock reference is bound to B71 v2's frozen reference and its live zero-byte file was checked after C4 completed; both SHA-256 values were `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

The one exact PS7 no-Plant prepare command below returned MATLAB/PowerShell exit 0. The prepare result reports 71 verified scenes, 32 active sources, 31 `which` checks, cfg equality with C3/B1, fresh B-option construction through `controller_options_dl1018(cfg,'B')`, and complete B1-tree equality. It reports `plant_calls=0`, `run_episode_called=false`, no training/optimizer steps, no TEST access, and `release_required=true`. No Plant batch was started.

## Frozen and prepared artifact SHA-256

| Artifact | SHA-256 |
|---|---|
| `freeze_b_traceable_dev72_inputs_v3.ps1` | `6c2765615e6df65fba4a3f0c67398adacd410fa5836f8cfc68b568ca6c426fd5` |
| `B_TRACEABLE_DEV72_INPUT_LOCK_v3.json` | `8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452` |
| `B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json` | `03cb8c04c70974db9b13e4da20a5f65860a2a604f4888a8a94e4dcfb9ac52de8` |
| `prepare_b_traceable_dev72_v3.m` | `fb8773fa0cb3dcebe5b0622d8064fa7ff29f1391dc3095375dc40f1e0f3b4e60` |
| `run_b_traceable_dev72_v3.m` | `85378c7ee2ef93681c30fae3e756a57487f0da6aae8ca3d98940404d12192b12` |
| `RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v3.ps1` | `c2c7d85156b3664f8bddede766f0b4506c76ec42a224b1bf8042320e8abe1699` |
| `RUN_B_TRACEABLE_DEV72_EXACT_v3.ps1` | `0dab63188af439a594d8e8cb1f86d236be9671390b1e4459510346de9745f0a7` |
| `B_TRACEABLE_DEV72_PREPARE_RESULT_v3.json` | `3ee8867ef084471db6bba4d45d996cb9d5b8984143cd5abff6e30b849851aec8` |
| `B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v3.mat` | `1736946bf085a4badb3c13662f47c2af25ed88f7cffbe65f0412a9fc3cb8003d` |
| `B_TRACEABLE_DEV72_PREPARE_STDOUT_v3.txt` | `48ee37e750c18eb5c578c3a176bc8024ff3db7ec7f1fcd795ccf4367e65945e1` |
| `B_TRACEABLE_DEV72_PREPARE_OS_EXIT_v3.json` | `a02aa3177cede9084443581fa562c6ea5ac067b8b2ff4618d8d11d972396a1b7` |

The locked scene-ID SHA-256 is `6b41340cf6f2c6a36601c83498f32617911e8f232e19d814e3b06afa29e85487`. The reused B1 raw and run-status SHA-256 values are `5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957` and `4de20ba0f17cb0cc498220032626f15b621c8d44dbaab2ea24d3457741a30175`; its independently reviewed historical runtime-tree identity gap remains open.

PowerShell 7 AST parsing passed for the v3 builder and both exact commands. The v3 SHA helper uses 8 MiB reads, exits on an empty block, and passes signed bytes to Java `MessageDigest.update`. The initial freeze attempt returned exit 1 because the B1 input lock has no nested shared-lock ref; it wrote no input lock. The successful freeze then read the exact shared-lock ref from the preserved B71 v2 lock and checked it against the live file before binding it.

## Exact no-Plant command executed once

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023/RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v3.ps1'
```

The prepare OS-exit record captures MATLAB exit 0 and binds the command, input-lock, prepare-entry, and snapshot hashes. Review of the actual result and snapshot remains with the parent reviewer. The separate release-gated Plant command was not run.
