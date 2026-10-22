# Round 3 execution ledger

## Frozen scope and status

- Frozen taskbook: `PAPER14_V2_R3_PCF_XY_ONLY_SCREEN_20261022_REVISION_2_FROZEN`.
- Freeze time: 2026-10-21 22:49 UTC. Frozen taskbook SHA256: `a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a`.
- Candidate: `DSSM14_PCF_XY`, only FEATURE Head update eta mask `[1,1,0]`; R1/R2 and external inputs remain read-only.
- Current phase: isolated source package and offline checks. No PROBE/CONTINUE was started. No MATLAB Plant, flight, training, GPU job or TEST access was run.
- Only the twelve taskbook VAL scenes are referenced. R2 B/ON/OFF raws are bound by their original paths and SHA values; none are copied.
- The first candidate flight remains blocked pending independent main-model review, a matching `main_review_round3.json` approval, and a fresh mode-specific PASS preflight. CONTINUE additionally requires a separately reviewed PASS PROBE record.

## Model and speed record

派出的审计/实现 worker 均指定 GPT-6-Luna xhigh。协作工具没有 Fast/normal 速度选择器；没有请求 Fast，因此实际服务速度不可独立测量。主对话模型也不能由工具切换或核验模型/xhigh 设置，主模型身份无法按任务书要求更改；主模型审核仍由当前 Codex 会话执行。以上是工具限制记录，不是性能测量或模型身份声明。

## Theory gate, separate from empirical screening

The parallel theory review is **not passed; additional proof is required**. Conditional eta/filter/weight/output bounds support the exact algebraic mask identities, but there is no auditable full closed-loop ISS/UUB proof without a defined invariant domain and a uniform residual bound. The mask identity does not guarantee H3 improvement. This theoretical gap is recorded independently from the empirical 12-scene screen and does not change the frozen taskbook or candidate.

## Package artifacts

- `frozen_inputs.json` inherits the R2 model, normalizer, W0, Plant/runtime source lock, scene list, rescore manifests, and 12 R2 OFF raw/status/run_start identities; it adds the taskbook lock, seven local runtime source identities, and ten R3 package source hashes.
- `runtime/run_dl1018_closed_loop.m` contains the only runtime behavior change: require `[1,1,0]`, use masked eta only when building the FEATURE update surface, and log mask/effective eta for each event. The eta recursion, PCF helper, FEATURE Head helper, output-before-update order, and projection rule remain from the frozen source.
- `build_round3_xy_pcf_options.m` removes only `eta_mask` to prove exact recovery of frozen PCF-on options; it also asserts disabled V3.6 fusion and enabled formal B/RBF attitude/output/update flags.
- `verify_round3_identity.py` and `rescore_round3.py` read only locked VAL artifacts and R3 attempt outputs. They fail closed on TEST paths; the scorer reports all preregistered gates and limits conclusions to requesting a separate review.
- `offline_smoke_round3.m` and `offline_smoke_round3.py` use a synthetic same-record event to compare MATLAB/Python eta, mask, clipping, output, and weight update equations without calling an episode, Plant, actuator, training, or TEST.
- `preflight_round3.ps1` is read-only apart from its R3-local report. `launch_round3.ps1` requires `-ParentReviewed`, a fresh PASS preflight, an exact-lock main review, and (for CONTINUE) a separate PASS PROBE review.

## Commands and current evidence

All commands below must be invoked with PowerShell 7. The only authorized validation commands are the static audit, pure offline equation smoke, and read-only preflight. Do not run the launcher while the approval records remain absent/PENDING.

```powershell
$exp = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen'
$lock = Get-Content -LiteralPath (Join-Path $exp 'frozen_inputs.json') -Raw | ConvertFrom-Json
& $lock.matlab.exe -batch "addpath('$($exp.Replace('\','/'))'); offline_smoke_round3"
$matlabSmokeExit = $LASTEXITCODE
$python = (Get-Command python -ErrorAction Stop).Source
& $python (Join-Path $exp 'offline_smoke_round3.py')
$pythonSmokeExit = $LASTEXITCODE
pwsh -NoProfile -File (Join-Path $exp 'static_test_round3.ps1')
$staticExit = $LASTEXITCODE
python (Join-Path $exp 'verify_round3_identity.py') --inputs-only
$identityExit = $LASTEXITCODE
pwsh -NoProfile -File (Join-Path $exp 'preflight_round3.ps1') -Mode PROBE
$preflightExit = $LASTEXITCODE
```

Expected no-marker preflight status is `BLOCKED`; it can document resource/input state but it does not grant authorization. A successful offline smoke is not flight approval.

## Start and resource log

| UTC time | Mode | Action | Result |
|---|---|---|---|
| 2026-10-22 | package | Copy seven locked `.m` sources into R3 `runtime/`; patch only local `run_dl1018_closed_loop.m` | No MATLAB/Plant/flight/training/GPU job; no TEST access |
| 2026-10-22 | static/offline | Pending final validation evidence | No PROBE or CONTINUE authorization |

## Final lock and test results

To be filled after the final source lock and allowed offline checks. Do not edit `TASKBOOK_ZH.md` or `frozen_taskbook_manifest.json`.

Main review records must bind `frozen_inputs_sha256`, `taskbook_sha256`, mode, `setup_manifest_sha256`, `runner_sha256`, and SHA256 values for `static_test_round3.json`, `offline_math_smoke_matlab_final.json`, and `offline_math_smoke_python_final.json`. CONTINUE's separate PROBE review must bind the exact `raw_sha256`, `run_start_sha256`, and `run_status_sha256` currently present on disk; preflight and MATLAB runner both recheck them.

The earlier `offline_math_smoke_matlab.json` and `offline_math_smoke_python.json` are retained as preliminary PASS reports bound to earlier locks; the `*_final.json` reports supersede them and are the only valid review evidence.

理论门槛状态：未通过，完整闭环 ISS/UUB 证明仍需补证。该结论与经验筛选分开记录。

## Final validation record — 2026-10-22 (authoritative)

The planned command block above is superseded by this executed-command record. All changes in this section are R3-local; the frozen taskbook, its manifest, R2 lock, and external sources remain unchanged. `round3_ledger.md` is not listed in `frozen_inputs.json` `setupFiles`, so these ledger records do not alter the source/setup lock.

| Check | Exact command / executable | Result |
|---|---|---|
| MATLAB offline equation smoke | `C:\Program Files\MATLAB\R2025b\bin\matlab.exe -batch "addpath('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/paper14_v2_round3_xy_pcf_screen'); offline_smoke_round3"` (executable path came from the frozen lock) | PASS, exit 0; helper-only, no episode/Plant/TEST calls. Eta uses `plantDt=0.001 s`; FEATURE Head update uses `eventDt=0.01 s`. Every MATLAB parity/identity error recorded as 0. |
| Python offline parity | `C:\ProgramData\anaconda3\python.exe C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen\offline_smoke_round3.py` | PASS, exit 0; max error `4.440892098500626e-16`; no Plant/episode/TEST access. |
| Frozen input identity | `C:\ProgramData\anaconda3\python.exe C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen\verify_round3_identity.py --inputs-only` | PASS, exit 0; 12 scenes, 24 reused ON/B raws, 12 R2 OFF raws, 7 runtime files, 10 setup files; `test_access=false`, no candidate runs. |
| Static audit, first attempt | `C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen\static_test_round3.ps1` | FAIL, exit 1, static-test false positive: the ledger recorded the theory gap in English but lacked the required Chinese status token `未通过/不足`. Added the explicit ledger line `理论门槛状态：未通过`; no candidate/runtime/lock change. |
| Static audit, final | Same exact PowerShell 7 command as above | PASS, exit 0; report generated and hash-checked against the current lock and both final smoke reports. |
| No-marker resource preflight | `C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round3_xy_pcf_screen\preflight_round3.ps1 -Mode PROBE` (deliberately no `-ParentReviewed`) | Expected BLOCKED, preflight exit 1; sole error: `A manual -ParentReviewed marker is required; this preflight grants no run authorization.` No run authorization was granted. |

### Final SHA256 index

- `TASKBOOK_ZH.md`: `a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a`
- `frozen_taskbook_manifest.json`: `fe73d468b5a958622a61d36118e339743bec28773bbe4168e67a0714808bb349`
- `frozen_inputs.json`: `9e464f044e3b99b323d45bdfbc5997df60602e24bb9e469cd3e6426f519c979c`
- R2 upstream lock: `92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58`
- R3 setup manifest (computed from locked setup filenames and hashes): `949ffa1a4c20773a1b5b0a2b93219ddbf1380fe87c0bf78f9ba93a1e7fccee15`
- `build_round3_xy_pcf_options.m`: `3e16a3bf07fcf8957defb8a42adb62cb4ec3c7fa35fddff2a30a278cf974c7c8`
- `round3_xy_math.m`: `ab780a7efe746d7fc7029a87d5bf751be622609c0b5c8e8a4fc6a9fb48ca6a8b`
- `run_round3_xy_pcf_screen.m`: `a10765729ce97611c8d0c2d076ce5311a683fde0cd81b87c66fd200839f49a14`
- `offline_smoke_round3.m`: `a2151f135ceb9b279b43a842b96fd867bc7314cd4b0fb6b78663642748eab096`
- `offline_smoke_round3.py`: `70c95875e6a25864b1c9833419ea2a46cbfeddd44f44ff6e8463e3f0f0599659`
- `verify_round3_identity.py`: `77964149155552ea8f7fdd9e2813756a42131f15fcf0605c0e86e9570f6b6d0f`
- `rescore_round3.py`: `7012829ece392267362c64460ff39f9e21019c725ae51166890fd5c773812552`
- `preflight_round3.ps1`: `6dbd0d04f77b279c9c73da217c9c6f8dfb95c99a123a91e1e22fff5b5e85741a`
- `launch_round3.ps1`: `b763ec2af6fe384709644d738aec500af6d09aeb71f226e81e23c39edfd1fbe9`
- `static_test_round3.ps1`: `49a96f6b9f5d87ae69772dd6753abfebc3f8cf4f84a4bb517f7e021d2cd49fc0`
- `reports/offline_math_smoke_matlab_final.json`: `cac26408fccb094fbd2359cc7e28ab58207716e5ff04fc8e7dcca9b7d0c25dfc`
- `reports/offline_math_smoke_python_final.json`: `11e83d831d29f71b0c141cf662383b8b9631a8006a1c3067f7e00fc7e5e49de6`
- `reports/static_test_round3.json`: `3179062e0f2584f0a15110277d4db144842a2e68e14450866ec1cc64f75c5131`
- `reports/preflight_round3.json`: `893e4200c848cd230dd833e95f58acc3cf776b18ac6e3c32ee5940ec6610bff6`

The three earlier smoke diagnostics remain preserved: `offline_smoke_failure_01.json` SHA `56beae2ba00ae448817ea16e549bb346f65b9f8d1f759371fc387fd83b984ca6`; `offline_smoke_failure_02.json` SHA `8c2256fab5f22f5452b8a7f681295b60204e66c9d50eef732f59895ae6890df2`; `offline_smoke_failure_03.json` SHA `5862099b6167bb9397f8e3fd64536fb0b3e48ec650397b82613e659b32520aed`. Failure 03 isolated only the smoke's incorrect shared time step (`W_next` error `0.02764274701385977`); the fix split `plantDt` and `eventDt` in the offline helper, without changing the deployment runtime.

### Final process and access snapshot

At the final read-only snapshot, MATLAB process count was 0; no process matched MATLAB/Simulink, Plant/flight, or training command patterns; GPU audit reported 0 active compute rows. The system did have Python workers for the unrelated `mcp_cad.exe` service; they were not training jobs and were not touched. MATLAB/Python smoke and identity reports each state `test_accessed=false`; the offline MATLAB report also states `scene_or_raw_read=false`. No PROBE, CONTINUE, launcher, episode, Plant, flight, training, GPU job, full72, or TEST access was executed.

## Main-model audit repair and final pre-PROBE decision — 2026-10-22

The independent Luna source review found two scorer gaps before any candidate flight:

1. The taskbook prohibits new actuator saturation, while the raw runtime log already records `tilt_limited`; the scorer only checked motor saturation and generalized clipping. The R3 scorer now reads the flag from every B/PCF-on/PCF-off/XY raw, requires exactly 20,000 finite binary values, reports counts/fractions, and defines a new event as `XY[t] != 0` while all three matched controls are zero at that tick. The gate requires zero such new events. This is an executable interpretation of the frozen “no new saturation” condition; it does not require absolute zero when matched controls already had an event.
2. The scorer previously accepted a common nonuniform time axis. It now rejects nonfinite axes and requires each of the 20,000 transition samples to match `k * plant_dt_s` (0.001 s) within absolute tolerance `1e-12 s`, `rtol=0`; synthetic tests cover nonuniform interior samples with unchanged endpoints, nonfinite values, wrong length, and wrong step.

No candidate runtime, head, Plant, taskbook, model, training, input data, launcher, or experiment setting was changed for these audit repairs. The original frozen taskbook and its manifest are unchanged. The updated R3 input/source lock is SHA256 `f6a45b2ef9aac6f4ff365b14466868b68fbd3111b0fe8ee2a12a5ef76c852fa4`; it binds the updated scorer and synthetic tests as 11 setup files. The prior lock and prior smoke/preflight evidence were retained under `reports/archive_pre_tilt_gate_fix` and `reports/archive_before_time_grid_fix`; final smoke reports were version-preserved before regeneration.

Final offline evidence on the updated lock:

- `test_rescore_round3_tilt.py -v`: 8 synthetic-only tests passed, exit 0; no raw/MAT reads.
- `verify_round3_identity.py --inputs-only`: PASS, 12 VAL scenes, 24 reused B/ON raws, 12 OFF raws, 7 runtime files and 11 setup files; `test_access=false`, candidate runs empty.
- MATLAB offline equation smoke: PASS, exit 0; no episode, Plant, actuator, training, raw/scene, or TEST access; all same-record identities are exact.
- Python offline parity: PASS; maximum error `4.440892098500626e-16`; no Plant/episode/TEST access.
- Static test: PASS, including PowerShell/Python parsing and all 8 scorer tests.
- No-marker resource preflight: expected BLOCKED solely because the main-model review marker was absent; MATLAB count 0, GPU audit PASS, disk free 167,039,791,104 bytes, `run_authorization_granted=false`.

The independent Luna follow-up found no P1 blocker in the repaired scorer or hash chain. Root review approves only a single PROBE on fixed scene `DL1018_VAL_T2_C00_W10`, contingent on a fresh mode-specific PASS preflight and launcher checks. CONTINUE is not approved; it needs a separate PROBE raw/status/run_start audit and a new mode-specific approval. The full closed-loop theory gate remains NOT PASSED, so independent TEST remains sealed. No Plant/flight/training/GPU job has been run in R3.


## Launcher UTC parse guard — 2026-10-22

The first authorized R3 PROBE launch attempt exited before MATLAB started and before any flight was produced. PowerShell 7 `ConvertFrom-Json` had parsed the frozen ISO-8601 `...Z` deadline as local DateTime, shifting the effective deadline by eight hours. The Luna xhigh implementer changed only `launch_round3.ps1` and its preflight-report JSON parse to `-DateKind String`; independent PS7 parsing and exact UTC-string assertions passed. No process was stopped, no experiment was interrupted, and no candidate run, Plant, training, score, or TEST access occurred in that attempt. The launcher source is now re-bound in the R3 setup lock. One retry is permitted only after the fresh static/offline/main-review/preflight chain passes; no further retry for the same issue.

## Round 3 scene payload dimension regression and isolated repair — 2026-10-22

After the PowerShell 7 UTC-date fix, the authorized launcher passed fresh PROBE preflight and MATLAB started. It exited at the B-scene payload assertion before creating the attempt directory or calling `run_episode_dl1018`; `runs` remains empty, with no candidate raw, run_start, status, probe summary, new MAT output, Plant call, or flight. The runner had incorrectly required `reference.position` to be exactly 3x20001. Read-only inspection of the locked B raw for `DL1018_VAL_T2_C00_W10` confirmed a 20001-point [0,20] time axis and a 20001x3 reference-position matrix. The file SHA remains the locked `05ad0e79…3e059b7`; the scene payload identity record reports identical ON/B physical data. R1/R2 already accept either matrix orientation and accept the `_ACC_FIX_V1` scene metadata alias; both completed this scene STABLE at 20000 transitions. The defect was R3's new assertion, not a changed experiment input.

The R3 repair restores orientation-agnostic dimension validation, verifies the frozen scene ID or its `_ACC_FIX_V1` alias, then normalizes only `scene_id` metadata; it does not transpose or modify physical arrays. The lock was refreshed only for the R3 runner/static test setup hashes. Taskbook, model, scenario, training settings, scorer and source data are unchanged. One offline MATLAB smoke call initially exited because the prior canonical report path was protected from overwrite; existing reports were archived with SHA preserved, then the final offline chain passed. This path/overwrite failure did not invoke Plant or an episode.

New lock SHA256 `65e5a515b18e7874b28d8388562afd690baf8392f097d4e1ee714161d417e98c`; setup manifest `c6d72933759f1f46030243216dd5173ddf9b7661caedc0f518525c28e8717c95`; runner `9405d5509b6159c6e8f702116faeaa38182d09bbd33a6a2c3981632055227019`; static source `a23f93acda739d96e087a055fa2016aa46706aa683cf676845dab5175cb0f416`. MATLAB smoke, Python parity, eight scorer synthetic tests, PS7 static test and input identity audit pass. Identity audit sees 12 VAL scenes, 24 reused ON/B raws and 12 R2 OFF raws; no candidate runs and no TEST access. The previous main review and preflight bound the old lock and are preserved as `main_review_round3_pre_scene_payload_fix.*` and `preflight_round3_pre_scene_payload_fix.json`; they are not current authorization.

This is one corrected engineering retry for a newly identified R3 assertion regression. No retry is approved yet. Root review and a new fresh PROBE preflight are required; if either fails, do not launch. CONTINUE and TEST remain unauthorized; the closed-loop theory gate remains NOT PASSED.

## Static identity-alias guard tightened — 2026-10-22

Independent review found the scene loader itself used the exact frozen ID or `_ACC_FIX_V1` alias, but the previous static test did not require the exact alias equality expression. The static test now explicitly requires both `strcmp(sceneId,id)` and `strcmp(sceneId,[id '_ACC_FIX_V1'])`, while the runner remains unchanged. The lock was refreshed only for `static_test_round3.ps1`; current lock SHA256 is `2557c553578fc7616ce79f7fb62505bb69b2ba6fac7ab83e60e283d0c1e92404`, setup manifest `a5784da7613e3ac55e968bdc36996be4ae9b6f7f239b3d0991c04e9d1d0e557e`. New MATLAB/Python/static reports bind this lock and all pass. Root independently reran the 8 scorer tests and inputs-only identity check; all passed. Candidate runs remain empty, TEST remains sealed. New main review and fresh preflight are pending; no PROBE retry is authorized yet.

## 固定 12 场完成与主模型收束决定 — 2026-10-22T01:00:55.693Z

CONTINUE 专属 PS7 预检 PASS：PowerShell 7.6.6、MATLAB 进程数 0、冻结 VAL identity verifier exit 0、磁盘可用 166,734,626,816 bytes；本批投影输出 756,250,000 bytes、预计 299 s。唯一授权批次按顺序启动并正常结束；12/12 场均 STABLE、20,000 transitions、1,968 Head events。所有 raw/run_start/run_status SHA 和文件尺寸见 `reports/round3_attempt_hashes.csv`。

隔离兼容 scorer 完成 12 行输出；locked scorer 因其 raw_scan 使用小写 `RMSE_x/y/z_*`、而旧 scorer 取大写键的兼容缺陷，不运行修改历史 scorer，而使用兼容副本加精确键别名。root 另从 48 份配对 raw 独立复算每场 Q 与 X/Y/Z 0–20 s RMSE，最大绝对差 0；Luna xhigh 对评分口径、分组、场景安全/身份与哈希独立复核无 blocker。

门槛结果：G1 PASS；G2 PASS；G3 PASS（高频 Z 4/6）；G4 FAIL（W15 XY−B mean Q `+0.348385206963766 mm`，W00–W08 mean `−2.7660031 mm`）；G5 PASS（ALL_12 mean `−0.635549 mm`，8胜/0平/4负）。唯一失败项为 W15。按冻结 taskbook 第三轮规则停止，不扩大 72、不调 mask/训练、不解封 TEST。理论 ISS/UUB gate 仍 NOT_PASSED。完整根审核：`reports/round3_main_review_20261022.md`；机器决定：`reports/round3_main_review_20261022.json`。

原 CONTINUE 授权和 launch preflight 已复制留档；活动 `main_review_round3.json` 已关闭为 `CLOSED`，防止过期批准被复用。未删除文件，MAT、模型、缓存和所有历史产物保留。
