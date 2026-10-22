$ErrorActionPreference='Stop'
$expDir=$PSScriptRoot;$lockPath=Join-Path $expDir 'frozen_inputs.json'
function Require([bool]$ok,[string]$message){if(-not $ok){throw $message}}
function Sha([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function SetupManifestSha($value){$parts=@($value.setupFiles|ForEach-Object {"$($_.name)|$(([string]$_.sha256).ToLowerInvariant())"});$b=[Text.Encoding]::UTF8.GetBytes([string]::Join(';',$parts));[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b)).ToLowerInvariant()}
Require ($PSVersionTable.PSVersion.Major -ge 7) 'Static check requires PowerShell 7.'
$lock=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json -Depth 100 -DateKind String
Require ($lock.schema -eq 'ROUND3_XY_PCF_SCREEN_INPUTS_V1') 'Unexpected R3 lock schema.'
Require ((Sha (Join-Path $expDir 'TASKBOOK_ZH.md')) -eq 'a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a') 'Frozen taskbook changed.'
Require ($lock.taskbook.sha256 -eq 'a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a') 'R3 lock does not bind the frozen taskbook.'
Require ((Sha $lock.frozen_taskbook_manifest.path) -eq $lock.frozen_taskbook_manifest.sha256) 'Frozen manifest hash mismatch.'
Require ($lock.upstream_round2.lock_sha256 -eq '92bf5bb355e473360f4ea6023dc508ed7c5369733eb083dfe38b26e53bf6bd58') 'Upstream R2 lock SHA changed.'
Require ((Sha $lock.upstream_round2.lock_path) -eq $lock.upstream_round2.lock_sha256) 'Upstream R2 lock file hash mismatch.'
Require ($lock.run.pcf_enabled -eq $true -and $lock.run.update_enabled -eq $true -and $lock.run.optimizer_steps -eq 0 -and (@($lock.run.eta_mask) -join ',') -eq '1,1,0') 'R3 run flags/mask/optimizer changed.'
Require ($lock.single_difference.path -eq 'opts.stage1_position_runtime.position_only_search_head.eta_mask' -and (@($lock.single_difference.ON) -join ',') -eq '1,1,1' -and (@($lock.single_difference.R3) -join ',') -eq '1,1,0') 'Single-factor lock changed.'
Require ($lock.run.seed -eq 2026102001 -and $lock.run.plant_dt_s -eq 0.001 -and $lock.run.position_event_hz -eq 100 -and $lock.run.duration_s -eq 20 -and $lock.run.gamma -eq 12 -and $lock.run.beta -eq 1 -and $lock.run.kappa -eq 1) 'Frozen run/timing/head parameters changed.'
Require ($lock.safety.read_test -eq $false -and $lock.analysis.test_access -eq $false -and $lock.safety.minimum_free_bytes -eq 30000000000 -and $lock.safety.max_cycle_output_bytes -eq 80000000000 -and $lock.safety.global_deadline_utc -eq '2026-10-24T17:01:00Z') 'R3 safety/deadline limits changed.'
Require ($lock.analysis.claim_limit -match '不证明|only decides' -and $lock.analysis.reference_position_input_rule -match 'never compare closed-loop state trajectories') 'Analysis interpretation limits are missing.'
$expected=@('DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00','DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T1_C00_W07','DL1018_VAL_T3_C12_W09','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00')
Require ((@($lock.scenes|ForEach-Object {$_.scene_id}) -join '|') -eq ($expected -join '|') -and @($lock.scenes).Count -eq 12) 'R3 scene IDs/order differ from taskbook.'
Require ((@($lock.scenes|Where-Object {$_.split -ne 'VAL'}).Count) -eq 0 -and (@($lock.round2_off_raws).Count -eq 12)) 'R3 candidate/off references must be twelve VAL scenes.'
Require (@($lock.localRuntimeFiles).Count -eq 7) 'Expected seven local runtime source files.'
foreach($entry in $lock.localRuntimeFiles){Require ((Sha $entry.path) -eq $entry.sha256) "Local runtime SHA mismatch: $($entry.name)";if($entry.name -ne 'run_dl1018_closed_loop.m'){Require ($entry.sha256 -eq $entry.upstream_sha256) "Unexpected upstream runtime difference: $($entry.name)"}}
foreach($entry in $lock.setupFiles){Require ((Sha $entry.path) -eq $entry.sha256) "R3 source SHA mismatch: $($entry.name)"}
$builder=Get-Content (Join-Path $expDir 'build_round3_xy_pcf_options.m') -Raw
Require ($builder -match "position_only_search_options\(cfg,model,'FEATURE',12,1\)" -and $builder -match 'eta_mask=\[1;1;0\]') 'Builder does not create the exact candidate.'
Require ($builder -match 'rmfield\(optsXYWithoutMask.*eta_mask' -and $builder -match 'isequaln\(optsXYWithoutMask,optsOn\)') 'Builder single-factor check must remove eta_mask and recover PCF-on exactly.'
Require ($builder -match 'assert\(~fusionEnabled' -and $builder -match 'formal_rbf_baseline' -and $builder -match 'rbf_attitude_output_enabled' -and $builder -match 'rbf_attitude_update_enabled') 'Builder lacks the frozen B/RBF attitude and V3.6 fusion checks.'
$runner=Get-Content (Join-Path $expDir 'run_round3_xy_pcf_screen.m') -Raw
Require ($runner -match 'parentReviewed' -and $runner -match 'preflight_round3\.json' -and $runner -match 'minutes\(5\)' -and $runner -match 'main_review_round3\.json') 'Runner lacks ParentReviewed/fresh-preflight/main-review gates.'
Require ($runner -match 'probe_review_round3\.json' -and $runner -match 'sceneIndices|ix=2:12' -and $runner -match 'DSSM14_PCF_XY') 'Runner lacks PROBE review/CONTINUE fixed-list candidate behavior.'
Require ($runner -match 'numel\(scene\.time\)==20001' -and $runner -match 'numel\(scene\.reference\.position\)==3\*20001' -and $runner -match 'numel\(posSize\)==2' -and $runner -match 'any\(posSize==3\)' -and $runner -match 'any\(posSize==20001\)' -and $runner -notmatch 'isequal\(size\(scene\.reference\.position\)') 'B scene payload check must accept either 3x20001 orientation without transposing.'
Require ($runner -match 'sceneId=char\(string\(scene\.scene_id\)\)' -and $runner -match 'strcmp\(sceneId,id\)' -and $runner -match 'strcmp\(sceneId,\[id ''_ACC_FIX_V1''\]\)' -and $runner -match 'scene\.scene_id=id') 'B scene identity must accept the frozen ID or ACC_FIX_V1 alias, then normalize metadata.'
Require (($runner -match 'eta_effective') -and ($runner -match 'maskErr') -and ($runner -match 'max\(min\(c,lim\),-lim\)') -and ($runner -match 'weight_before_33x3') -and $runner.Contains("raw0=(b.'*v).';")) 'Runner must verify logged event mask/equations and output-before-update.'
Require ($runner -match 'setup_manifest_sha256' -and $runner -match 'matlab_smoke_report_sha256' -and $runner -match 'round_status_sha256|run_status_sha256' -and $runner -match 'rawSha' -and $runner -match 'startSha') 'Runner must bind offline/main review evidence and reviewed PROBE raw/run_start/status hashes.'
$identity=Get-Content (Join-Path $expDir 'verify_round3_identity.py') -Raw
Require ($identity -match 'round2_off_raws' -and $identity -match 'raw_sha256' -and $identity -match 'TEST' -and $identity -match 'expected_mask' -and $identity -match 'err_mask' -and $identity -match 'W-before/W-after') 'Identity verifier lacks VAL/status/raw/event-mask identity checks.'
$scorer=Get-Content (Join-Path $expDir 'rescore_round3.py') -Raw
Require ($scorer -match 'round3_xy_screen_results\.csv' -and $scorer -match 'round3_xy_screen_summary\.json' -and $scorer -match 'high_frequency_xy_q_below_on_and_off_and_not_worse_than_b' -and $scorer -match 'at_least_4_of_6' -and $scorer -match 'W15' -and $scorer -match 'W00_W08') 'Scorer lacks the five preregistered R3 gates.'
Require ($scorer -match 'stable_identity' -and $scorer -match 'np\.array_equal' -and $scorer -match 'controller_call_time' -and $scorer -match 'motor_saturated_fraction' -and $scorer -match 'generalized_clipped_fraction' -and $scorer -match 'claim_limit') 'Scorer missing identity/paired input/safety/metric interpretation checks.'
$pre=Get-Content (Join-Path $expDir 'preflight_round3.ps1') -Raw
Require ($pre -match 'PSVersionTable\.PSVersion\.Major' -and $pre -match 'Get-GpuAudit' -and $pre -match 'GPUPerformanceCounters_GPUEngine' -and $pre -match 'minimum_free_bytes' -and $pre -match 'global_deadline_utc' -and $pre -match 'MATLAB' -and $pre -match 'verify_round3_identity\.py') 'Preflight lacks PS7/MATLAB/GPU/disk/deadline/input identity checks.'
Require ($pre -match 'setup_manifest_sha256' -and $pre -match 'static_report_sha256' -and $pre -match 'run_status_sha256' -and $pre -match 'probe_artifact_sha256') 'Preflight must bind reviewed static/offline evidence and exact PROBE artifact hashes.'
Require ($pre -notmatch 'Stop-Process|taskkill|Remove-Item|Copy-Item|Move-Item|Start-Process') 'Preflight must stay read-only and must not start/stop processes or move/delete inputs.'
$launcher=Get-Content (Join-Path $expDir 'launch_round3.ps1') -Raw
Require ($launcher -match '\[switch\]\s*\$ParentReviewed' -and $launcher -match 'preflight_round3\.ps1' -and $launcher -match 'status -ne ''PASS''' -and $launcher -match 'frozen_inputs_sha256') 'Launcher lacks reviewed fresh PASS preflight/lock gate.'
$mSmoke=Get-Content (Join-Path $expDir 'offline_smoke_round3.m') -Raw
$math=Get-Content (Join-Path $expDir 'round3_xy_math.m') -Raw
Require ($math -match 'plantDt,eventDt' -and $math -match 'exp\(-k2\*plantDt\)' -and $math -match 'W\+eventDt\*') 'Offline math must use the 1-kHz plant step for eta and 100-Hz Head event step for W.'
Require ($mSmoke -match 'round3_xy_math' -and $mSmoke -match 'position_filter_realization_pcf_step_v3_5' -and $mSmoke -match 'position_only_search_head_step' -and $mSmoke -match 'attitude_fusion_enabled' -and $mSmoke -match 'test_accessed'',false') 'MATLAB smoke lacks equation/output/options contract coverage.'
Require ($mSmoke -match 'setup_manifest_sha256' -and $mSmoke -match 'round3_runner_sha256' -and $mSmoke -match 'offline_smoke_source_sha256') 'MATLAB smoke report must lock its source/setup/runner identity.'
Require ($mSmoke -match 'checkcode\(fullfile\(here,\x27run_round3_xy_pcf_screen\.m\x27\)' -and $runner -match 'round3_runner_parse_check_complete') 'MATLAB offline smoke must parse-check the R3 runner without invoking it.'
Require ($mSmoke -notmatch 'run_episode_dl1018\s*\(' -and $mSmoke -notmatch 'run_dl1018_closed_loop\s*\(' -and $mSmoke -notmatch 'run_episode\s*\(') 'MATLAB smoke must not invoke Plant/episode code.'
Require ((Get-Content (Join-Path $expDir 'offline_smoke_round3.py') -Raw) -match 'np\.outer\(phi, s_eff\)' -and (Get-Content (Join-Path $expDir 'offline_smoke_round3.py') -Raw) -match 'same_record_z_vs_off') 'Python smoke lacks independent 33x3 recurrence/mask checks.'
$ledger=Get-Content (Join-Path $expDir 'round3_ledger.md') -Raw
Require ($ledger -match 'GPT-6-Luna xhigh' -and $ledger -match '速度' -and $ledger -match 'ISS/UUB' -and $ledger -match '未通过|不足') 'Ledger must record assigned model/speed limitation and theory-gate status.'
$psFiles=@('preflight_round3.ps1','launch_round3.ps1','static_test_round3.ps1')|ForEach-Object {Join-Path $expDir $_}
foreach($path in $psFiles){$tokens=$null;$parseErrors=$null;[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$parseErrors)|Out-Null;Require ($parseErrors.Count -eq 0) "PowerShell AST parse errors in $path"}
$python=Get-Command python -ErrorAction Stop
$pyFiles=@('verify_round3_identity.py','rescore_round3.py','offline_smoke_round3.py','test_rescore_round3_tilt.py')|ForEach-Object {Join-Path $expDir $_}
& $python.Source -c 'import ast,pathlib,sys; [ast.parse(pathlib.Path(p).read_text(encoding="utf-8"), filename=p) for p in sys.argv[1:]]' @pyFiles
Require ($LASTEXITCODE -eq 0) 'Python AST parse failed.'
& $python.Source (Join-Path $expDir 'test_rescore_round3_tilt.py') -v
Require ($LASTEXITCODE -eq 0) 'R3 tilt-limited scorer synthetic tests failed.'
$lockSha=Sha $lockPath;$setupSha=SetupManifestSha $lock;$runnerSha=Sha (Join-Path $expDir 'run_round3_xy_pcf_screen.m')
$matPath=Join-Path $expDir 'reports\offline_math_smoke_matlab_final.json';$pyPath=Join-Path $expDir 'reports\offline_math_smoke_python_final.json'
Require (Test-Path -LiteralPath $matPath -PathType Leaf) 'MATLAB offline smoke report must exist before final static evidence.'
Require (Test-Path -LiteralPath $pyPath -PathType Leaf) 'Python offline smoke report must exist before final static evidence.'
$mat=Get-Content -LiteralPath $matPath -Raw|ConvertFrom-Json;$py=Get-Content -LiteralPath $pyPath -Raw|ConvertFrom-Json
$matSha=Sha $matPath;$pySha=Sha $pyPath
Require ($lock.analysis.theory_gate -match 'No full closed-loop ISS/UUB proof') 'Theory gate status is missing from the lock.'
Require ($mat.status -eq 'PASS' -and $mat.frozen_inputs_sha256 -eq $lockSha -and $mat.setup_manifest_sha256 -eq $setupSha -and $mat.round3_runner_sha256 -eq $runnerSha -and $mat.round3_runner_parse_check_complete -eq $true -and $mat.test_accessed -eq $false -and $mat.run_episode_called -eq $false -and $mat.plant_called -eq $false -and $mat.actuator_called -eq $false -and $mat.training_called -eq $false) 'MATLAB offline smoke report is stale or violates the offline/TEST gate.'
Require ($py.status -eq 'PASS' -and $py.frozen_inputs_sha256 -eq $lockSha -and $py.setup_manifest_sha256 -eq $setupSha -and $py.round3_runner_sha256 -eq $runnerSha -and $py.matlab_report_sha256 -eq $matSha -and $py.test_accessed -eq $false -and $py.plant_or_episode_called -eq $false) 'Python parity report is stale or violates the offline/TEST gate.'
$staticReport=[ordered]@{schema='ROUND3_STATIC_TEST_V1';status='PASS';created_utc=[DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ');frozen_inputs_sha256=$lockSha;taskbook_sha256=$lock.taskbook.sha256;setup_manifest_sha256=$setupSha;runner_sha256=$runnerSha;static_test_source_sha256=(Sha $PSCommandPath);matlab_smoke_report_path='reports/offline_math_smoke_matlab_final.json';matlab_smoke_report_sha256=$matSha;python_smoke_report_path='reports/offline_math_smoke_python_final.json';python_smoke_report_sha256=$pySha;test_accessed=$false;python_ast_exit_code=0;tilt_scorer_test_exit_code=0;checks=@('taskbook/R2 lock identity','single [1,1,0] factor and B/RBF options','fixed 12 VAL IDs','local source lock','PowerShell/Python AST','synthetic tilt-limited union-gate tests','offline MATLAB/Python parity','review/preflight/launcher gates','theory/speed ledger')}
$staticPath=Join-Path $expDir 'reports\static_test_round3.json';$staticReport|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $staticPath -Encoding utf8
Write-Output 'ROUND3_STATIC PASS: frozen taskbook/R2 inheritance; exact [1,1,0] single factor; 12 VAL identities; local source lock; offline-only smokes; five gates; review/preflight/launcher gates; no destructive preflight operations.'
Write-Output "STATIC_REPORT $staticPath SHA256=$(Sha $staticPath)"
exit 0
