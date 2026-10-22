param()
$ErrorActionPreference='Stop'
$expDir=$PSScriptRoot
$lockPath=Join-Path $expDir 'frozen_inputs.json'
$lock=Get-Content $lockPath -Raw|ConvertFrom-Json -DateKind String
function Require([bool]$ok,[string]$message){if(-not $ok){throw $message}}
function Sha([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$taskbook=Get-Content (Join-Path $expDir 'TASKBOOK_ZH.md') -Raw
Require ((Sha (Join-Path $expDir 'TASKBOOK_ZH.md')) -eq '0de23a43f1e9c512e79a6cf3ac53d3aa95a7b24ce3aa18c60b60a718add3ff5e') 'Frozen taskbook SHA changed.'
Require ($lock.schema -eq 'ROUND2_PCF_SCREEN_INPUTS_V1') 'Unexpected lock schema.'
Require ($lock.single_difference.path -eq 'opts.stage1_position_runtime.command_filter_coordination_v3_5.enabled' -and $lock.single_difference.ON -eq $true -and $lock.single_difference.OFF -eq $false) 'Single-factor lock changed.'
Require ($lock.run.pcf_enabled -eq $false -and $lock.run.update_enabled -eq $true -and $lock.run.optimizer_steps -eq 0) 'Run flags or optimizer step count changed.'
Require ($lock.run.weight_delta_threshold_unitless -eq 1e-12 -and $lock.run.signal_tolerance_mps -eq 1e-12) 'Weight and signal tolerances must be independently unit-typed.'
Require ($lock.safety.minimum_free_bytes -eq 30000000000 -and $lock.safety.max_cycle_output_bytes -eq 80000000000 -and $lock.safety.global_deadline_utc -eq '2026-10-24T17:01:00Z') 'Frozen resource limit changed.'
Require ($lock.safety.gpu_compute_jobs_must_be_zero -eq $true -and $lock.safety.gpu_unknown_pid_blocks -eq $true -and $lock.safety.gpu_engine_compute_counters_required -eq $true -and $lock.safety.gpu_wddm_pids_query_required -eq $true -and $lock.safety.gpu_compute_query_pid_pids_fallback_required -eq $true -and $lock.safety.gpu_per_pid_engine_counters_required -eq $true) 'Frozen safety lock must require PIDS fallback and per-PID/global Compute counters while failing closed on unknown identities.'
Require ((@($lock.safety.gpu_wddm_allowed_graphics_types) -join '|') -eq 'C+G|G' -and @($lock.safety.gpu_suspected_compute_image_patterns).Count -ge 3) 'WDDM graphics allowlist or suspected-compute image policy changed.'
Require ($lock.analysis.else -eq '筛查未通过，不进入72场，保留全部数据且不调参。' -and $lock.analysis.propose_72_only_if -match '不得据此声称证伪H2') 'Lock failure language must not claim that the 12-scene screen falsifies H2.'
$expected=@('DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00','DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T1_C00_W07','DL1018_VAL_T3_C12_W09','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00')
Require ((@($lock.scenes|ForEach-Object {$_.scene_id}) -join '|') -eq ($expected -join '|')) 'Lock scene order differs from the taskbook.'
$headFiles=@($lock.runtimeFiles|Where-Object {$_.path -like '*position_only_search_head_step.m'})
$pcfFiles=@($lock.runtimeFiles|Where-Object {$_.path -like '*position_filter_realization_pcf_step_v3_5.m'})
Require ($headFiles.Count -eq 1 -and $headFiles[0].sha256 -eq '3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc') 'Actual FEATURE Head helper identity is not locked.'
Require ($pcfFiles.Count -eq 1 -and $pcfFiles[0].sha256 -eq 'b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0') 'PCF eta step identity is not locked.'
$builder=Get-Content (Join-Path $expDir 'build_round2_pcf_off_options.m') -Raw
Require ($builder -match 'optsPcfOn = position_only_search_options\(cfg, model, ''FEATURE'', 12, 1\)') 'Builder does not use the frozen baseline options helper.'
Require ($builder -match 'command_filter_coordination_v3_5\.enabled = false') 'Builder does not set the sole PCF field.'
Require ($builder -match 'isequaln\(optsPcfOff, expected\)') 'Builder lacks exact single-difference equality assertion.'
Require ($builder -match 'logical\(p\.update_enabled\)' -and $builder -match 'head_type.*FEATURE' -and $builder -match 'gamma\)==12' -and $builder -match 'kappa\)==1') 'Builder does not retain online FEATURE Head contract.'
Require ($builder -match 'assert\(~fusionEnabled' -and $builder -match 'attitude_fusion_enabled.*, false') 'Builder does not prove attitude-fusion contract is inactive.'
$runtimeMain=Get-Content $lock.runtimeFiles[0].path -Raw
Require ($runtimeMain -match 'if attitudeFusionActive' -and $runtimeMain -match '~stage1PositionActive\|\|pcfCoordinationEnabled') 'Locked runtime fusion/PCF contract changed.'
$controllerOptions=Get-Content $lock.runtimeFiles[5].path -Raw
Require ($controllerOptions -match 'P_A' -and $controllerOptions -match 'command_filter_coordination_v3_5') 'Locked effective-options baseline changed.'
$controllerOptions=Get-Content $lock.runtimeFiles[5].path -Raw
Require ($controllerOptions -match 'P_A' -and $controllerOptions -match 'command_filter_coordination_v3_5') 'Locked effective-options baseline changed.'
$runner=Get-Content (Join-Path $expDir 'run_round2_pcf_screen.m') -Raw
Require ($runner -match 'probeSummary\.attempt_execution_and_raw_persistence_seconds' -and $runner -match 'verify_locked_inputs\(lock\)' -and $runner -match 'lock\.taskbook\.sha256' -and $runner -match 'lock\.runtimeFiles' -and $runner -match 'ROUND2_PCF_SCREEN_INPUTS_V1') 'Runner lacks source/input SHA verification.'
Require ($runner -match 'position_only_search_head_step' -and $runner -match 'run_episode_dl1018\(scene' -and $runner -match 'optsPcfOff, optionAudit') 'Runner lacks locked helper path or passes altered options.'
Require ($runner -match 'probeStatus\.update_enabled' -and $runner -match '~probeStatus\.pcf_enabled') 'CONTINUE gate does not require update=true/PCF=false.'
Require ($runner -match 'any\(updateExecuted\)' -and $runner -match 'eventDelta > weightDeltaThreshold' -and $runner -match 'etaMax <= signalToleranceMps' -and $runner -match 'surfaceClipError <= signalToleranceMps') 'Runner lacks independent dimensionless-weight and m/s signal checks.'
Require ($runner -match "save\(runStartPath, 'sceneId', 'inputIdentity', '-v7\.3'\)" -and $runner -notmatch "save\(runStartPath, 'scene'") 'run_start must save only scene ID and identity, never the frozen scene payload.'
Require ($runner -match 'run_episode_dl1018\(scene, method, cfg, optsPcfOff\)' -and $runner -notmatch 'run_episode_dl1018\(scene, method, cfg, optsPcfOff, rawPath\)' -and $runner -match "save\(rawPath, 'log', 'method', 'runIdentity', '-v7\.3'\)") 'Raw output must save only returned log, method, and run identity without passing rawPath to the locked wrapper.'
Require ($runner -match "catch ME" -and $runner -match "'status', 'FAILED'" -and $runner -match 'rethrow\(ME\)' -and $runner -match 'attempt_started_marker_present') 'Runner must preserve marker/partial outputs, write failure status, and rethrow without retry.'
Require ($runner -match 'model_mat_sha256' -and $runner -match 'model_binding_sha256' -and $runner -match 'normalizer_npz_sha256' -and $runner -match 'normalizer_arrays_identity_sha256' -and $runner -match 'W0_output_W_sha256' -and $runner -match 'scene_payload_identity_csv_sha256' -and $runner -match 'plant_source_identity' -and $runner -match 'runtime_source_identity' -and $runner -match 'max_abs_event_weight_delta_unitless') 'Run status is missing direct model, input, W0, or source identity fields.'
Require ($runner -match 'head_type.*optionAudit\.head_type' -and $runner -match 'position_only_search_head_enabled' -and $runner -match "'update_enabled', logical\(optsPcfOff" -and $runner -match "'pcf_enabled', logical\(optsPcfOff") 'Input identity does not bind the effective Head/update/PCF contract.'
$episode=Get-Content $lock.runtimeFiles[1].path -Raw
Require ($episode -match "runtimeHandle\(scene,'B2-RBF-Full-SPLIT',cfg,opts\)" -and $episode -match 'log=runtimeHandle') 'Locked episode wrapper overlays or replaces effective options.'
$preflight=Get-Content (Join-Path $expDir 'preflight_round2.ps1') -Raw
Require ($preflight -match 'observedAttemptSeconds' -and $preflight -match 'per_pid_gpu_compute_counter_rows' -and $preflight -match 'NO_ACTIVE_COMPUTE' -and $preflight -match '\[switch\]\s*\$ParentReviewed' -and $preflight -match 'A fresh parent-review marker is required') 'Preflight lacks parent-review blocker.'
Require ($preflight -match 'SOLIDWORKS_MCP_CAD' -and $preflight -match 'OTHER_PYTHON' -and $preflight -match 'verify_scene_payload_identity\.py') 'Preflight lacks process categories or read-only scene verifier.'
Require ($preflight -match 'checked_sha256_failure_count' -and $preflight -match 'minimum_free_bytes' -and $preflight -match 'fixed global deadline') 'Preflight lacks source/disk/deadline checks.'
Require ($preflight -match 'nvidia-smi' -and $preflight -match 'query-compute-apps' -and $preflight -match ' -q -d PIDS' -and $preflight -match 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine' -and $preflight -match 'raw_nvidia_process_rows' -and $preflight -match 'raw_nvidia_pids_query' -and $preflight -match 'parsed_nvidia_pids_rows' -and $preflight -match 'raw_compute_query_rows' -and $preflight -match 'WDDM_PIDS_FALLBACK' -and $preflight -match 'gpu_engine_counters_by_pid' -and $preflight -match 'gpu_engine_compute_counters_by_pid' -and $preflight -match 'per_pid_gpu_engine_counter_status' -and $preflight -match 'PIDS table' -and $preflight -match 'PIDS query PID' -and $preflight -match '\[double\]::IsNaN' -and $preflight -match '\[double\]::IsInfinity' -and $preflight -match '\$util -lt 0' -and $preflight -match '\$util -gt 100' -and $preflight -match 'active GPU compute engine counters detected' -and $preflight -match 'gpu_resource_audit') 'Preflight lacks read-only PIDS fallback, PID/type cross-check, bounded finite engine counters, or fail-closed Compute activity accounting.'
Require ($preflight -match '\[string\]\s*\$ReportPathOverride' -and $preflight -match 'Refusing to overwrite an existing versioned preflight report' -and $preflight -match 'resource_preflight_only=\$true' -and $preflight -match 'run_authorization_granted=\$false') 'Versioned resource report must stay isolated and explicitly grant no run authorization.'
Require ($preflight -notmatch 'Stop-Process|taskkill|Copy-Item|Remove-Item|Start-Process') 'Preflight contains forbidden process or file mutation.'
$gpuReportFiles=@(Get-ChildItem (Join-Path $expDir 'reports') -Filter 'preflight_round2_wddm_resource_audit_20261022_v*.json' -File|Sort-Object LastWriteTimeUtc -Descending)
Require ($gpuReportFiles.Count -gt 0) 'Versioned WDDM resource audit report is missing.'
$gpuReportPath=$gpuReportFiles[0].FullName
$gpuReport=Get-Content -LiteralPath $gpuReportPath -Raw|ConvertFrom-Json
Require ($gpuReport.schema -eq 'ROUND2_PCF_SCREEN_PREFLIGHT_V1' -and $gpuReport.resource_preflight_only -eq $true -and $gpuReport.run_authorization_granted -eq $false -and $gpuReport.parent_reviewed_switch_present -eq $false) 'Preflight audit JSON scope/authorization schema is invalid.'
Require ($gpuReport.frozen_inputs_sha256 -eq (Sha $lockPath)) 'Latest resource audit is not bound to the current frozen input lock.'
Require ($gpuReport.gpu_resource_audit.schema -eq 'ROUND2_WDDM_GPU_RESOURCE_AUDIT_V2' -and $null -ne $gpuReport.gpu_resource_audit.raw_nvidia_process_rows -and $null -ne $gpuReport.gpu_resource_audit.raw_nvidia_pids_query -and $null -ne $gpuReport.gpu_resource_audit.parsed_nvidia_pids_rows -and $null -ne $gpuReport.gpu_resource_audit.raw_compute_query_rows -and $null -ne $gpuReport.gpu_resource_audit.process_entries -and $null -ne $gpuReport.gpu_resource_audit.gpu_engine_counters_by_pid -and $null -ne $gpuReport.gpu_resource_audit.gpu_engine_compute_counters -and $null -ne $gpuReport.gpu_resource_audit.gpu_engine_compute_counters_by_pid -and $null -ne $gpuReport.gpu_resource_audit.errors) 'WDDM GPU resource audit JSON is missing raw PIDS/process rows, mappings, or engine counters.'
Require ($gpuReport.checked_sha256_failure_count -eq 0 -and $gpuReport.scene_payload_verifier_exit_code -eq 0 -and $gpuReport.parent_reviewed_switch_present -eq $false -and $gpuReport.errors -match 'parent-review marker') 'No-marker preflight must preserve successful identity checks while recording no authorization.'
Require ($gpuReport.status -in @('PASS','BLOCKED') -and $gpuReport.gpu_resource_audit.status -in @('PASS','BLOCKED')) 'Preflight report contains an unknown status.'
if($gpuReport.gpu_resource_audit.status -eq 'PASS'){
    Require (@($gpuReport.gpu_resource_audit.errors).Count -eq 0 -and @($gpuReport.gpu_resource_audit.active_compute_engine_rows).Count -eq 0 -and $gpuReport.gpu_resource_audit.gpu_engine_counter_status -eq 'PASS') 'GPU PASS status is inconsistent with errors, active Compute counters, or counter query status.'
    Require ($gpuReport.gpu_resource_audit.driver_model -eq 'WDDM' -and @($gpuReport.gpu_resource_audit.process_entries|Where-Object {$_.classification -ne 'WDDM_GRAPHICS_CONTEXT' -or $_.blocked -ne $false -or $_.type -notin @('C+G','G') -or [string]::IsNullOrWhiteSpace($_.image_name)}).Count -eq 0) 'GPU PASS must contain only mapped, approved, non-suspicious WDDM contexts.'
    Require (@($gpuReport.gpu_resource_audit.wddm_pids_fallback_entries|Where-Object {$_.source -ne 'WDDM_PIDS_FALLBACK' -or $_.per_pid_gpu_engine_counter_status -ne 'NO_ACTIVE_COMPUTE'}).Count -eq 0) 'Every accepted PIDS fallback must have per-PID GPU engine rows and no active per-PID Compute counter; non-Compute graphics counters may be nonzero.'
} else { Require (@($gpuReport.gpu_resource_audit.errors).Count -gt 0 -or $gpuReport.gpu_resource_audit.gpu_engine_counter_status -eq 'BLOCKED') 'GPU BLOCKED status must explain a failure-closed condition.' }
Require ($null -ne $gpuReport.gpu_resource_audit.active_compute_engine_rows -and $gpuReport.resource_preflight_only -eq $true -and $gpuReport.run_authorization_granted -eq $false) 'GPU counter evidence or no-authorization scope is missing.'
$launcher=Get-Content (Join-Path $expDir 'launch_round2.ps1') -Raw
Require ($launcher -match '\[switch\]\s*\$ParentReviewed' -and $launcher -match 'preflight_round2\.ps1' -and $launcher -match 'ParentReviewed:\$ParentReviewed' -and $launcher -match 'run_round2_pcf_screen') 'Launcher review/preflight gate is incomplete.'
Require ($launcher -notmatch 'Copy-Item|Stop-Process|taskkill') 'Launcher contains forbidden file/process mutation.'
$verifier=Get-Content (Join-Path $expDir 'verify_scene_payload_identity.py') -Raw
Require ($verifier -match 'EXPECTED_IDS' -and $verifier -match 'PHYSICAL_FIELDS' -and $verifier -match 'np\.array_equal' -and $verifier -match 'stable_file_identity') 'Scene verifier lacks the frozen 14-field VAL identity audit.'
Require ($verifier -notmatch 'read_text\([^\)]*TEST|to_csv|write_text|save\(') 'Scene verifier must remain read-only and VAL-only.'
$scorer=Get-Content (Join-Path $expDir 'rescore_round2.py') -Raw
Require ($scorer -match 'round2_screen_results\.csv' -and $scorer -match 'round2_screen_summary\.json') 'Scorer output paths are not isolated in R2.'
Require ($scorer -match 'WEIGHT_DELTA_TOL' -and $scorer -match 'SIGNAL_TOL_MPS' -and $scorer -match 'max_abs_event_weight_delta_unitless' -and $scorer -notmatch 'max_abs_event_weight_delta[^\r\n]*TOL_M') 'Scorer must use a unitless W threshold and separate m/s signal tolerance.'
Require ($scorer -match 'f\["log/reference/position"\]' -and $scorer -match 'raw_scan\.score\(path\)' -and $scorer -match 'stable_file_identity' -and $scorer -match 'rescore_identities') 'Scorer must rescan all raw logs and retain read-only identity checks.'
Require ($scorer -match 'controller_call_time_s' -and $scorer -match 'controller_call_time_mean_s' -and $scorer -match 'controller_call_time_p95_s' -and $scorer -match 'controller_call_time_max_s' -and $scorer -match 'candidate_episode_runtime_s' -and $scorer -match 'candidate_attempt_execution_and_raw_persistence_s') 'Scorer must report controller-call time separately from precisely bounded episode and persistence timing.'
Require ($scorer -match 'motor_saturated_fraction' -and $scorer -match 'generalized_clipped_fraction' -and $scorer -match 'safety_stop_reason' -and $scorer -match 'last_transition' -and $scorer -match 'identity_status') 'Scorer must report each method safety marker and saturation/clipping proportions.'
Require ($scorer -match 'q_outcome_off_vs_on' -and $scorer -match 'q_outcome_off_vs_b' -and $scorer -match '"W09_W11"' -and $scorer -match '"W12_W14"' -and $scorer -match '"W15"' -and $scorer -match '"W00_W08"' -and $scorer -match 'hf_w09_w14_gate') 'Scorer must report per-scene win/tie/loss and four groups plus the merged high-frequency gate.'
Require ($scorer -match 'mean_rmse_z_off_minus_on_0_20_m' -and $scorer -match 'mean_rmse_z_off_minus_b_0_20_m' -and $scorer -match 'z_outcomes_off_vs_on' -and $scorer -match 'z_outcomes_off_vs_b') 'Every band group must report OFF-minus-ON/B Z deltas and win/tie/loss counts.'
Require ($scorer -match 'after_array_read = stable_file_identity\(path\)' -and $scorer -match 'raw changed during direct HDF5 array read') 'Scorer must recheck file identity after direct HDF5 metric reads.'
Require ($scorer -match 'np\.array_equal\(ref, ref_arrays\[0\]\)' -and $scorer -notmatch 'ref_max|TOL_M\s*\).*reference') 'Reference input identity must use exact element equality, never state-trajectory comparison or metric tolerance.'
Require ($scorer -match 'hf_q_improvement_vs_on > TOL_M' -and $scorer -match 'hf_q_off_minus_b <= TOL_M' -and $scorer -match 'hf_z_wins >= 4' -and $scorer -match 'macro_q_improvement_vs_b > TOL_M') 'Scorer does not implement registered Round 2 gate.'
Require ($scorer -match 'SCREEN_NOT_PASSED_NO_72_NO_TUNING' -and $scorer -notmatch 'FALSIFY_CURRENT_HYPOTHESIS' -and $scorer -match 'does not independently prove or falsify H2') 'Failed screen must not be described as falsifying H2.'
Require ($scorer -match 'delta_q_off_minus_on_m' -and $scorer -match 'delta_rmse_z_off_minus_on_' -and $scorer -match 'micro_sensitivity' -and $scorer -match 'q_outcomes_off_vs_on') 'Scorer does not report paired deltas and micro sensitivity.'
$smoke=Get-Content (Join-Path $expDir 'offline_options_smoke_round2.m') -Raw
Require ($smoke -match 'build_round2_pcf_off_options' -and $smoke -match 'run_episode_called'',false' -and $smoke -match 'plant_called'',false' -and $smoke -match 'attitude_fusion_enabled' -and $smoke -match 'frozen_inputs_path' -and $smoke -match 'options_builder_sha256' -and $smoke -match 'position_only_search_head_step_sha256' -and $smoke -match 'offline_options_smoke_20261022_v8\.json' -and $smoke -match 'Refusing to overwrite an existing offline smoke report') 'Offline smoke must be options-only, uniquely versioned, and report locked helper/lock identities.'
Require ($smoke -notmatch 'run_episode_dl1018\s*\(' -and $smoke -notmatch 'run_dl1018_closed_loop\s*\(') 'Offline smoke must never call a simulator.'
$smokeReportPath=Join-Path $expDir 'reports\offline_options_smoke_20261022_v8.json'
Require (Test-Path -LiteralPath $smokeReportPath -PathType Leaf) 'Fresh current-lock offline options smoke report is missing.'
$smokeReport=Get-Content -LiteralPath $smokeReportPath -Raw|ConvertFrom-Json
$lockedHead=@($lock.runtimeFiles|Where-Object {$_.path -like '*position_only_search_head_step.m'})
$lockedBuilder=@($lock.setupFiles|Where-Object {$_.name -eq 'build_round2_pcf_off_options.m'})
Require ($smokeReport.status -eq 'OFFLINE_OPTIONS_SMOKE_PASS' -and $smokeReport.closed_loop_called -eq $false -and $smokeReport.run_episode_called -eq $false -and $smokeReport.plant_called -eq $false -and $smokeReport.optimizer_steps -eq 0) 'Offline options smoke report has invalid scope/status.'
Require ($smokeReport.frozen_inputs_sha256 -eq (Sha $lockPath) -and [IO.Path]::GetFullPath($smokeReport.frozen_inputs_path) -eq [IO.Path]::GetFullPath($lockPath)) 'Offline options smoke report is stale or not bound to current frozen_inputs.json.'
Require ($lockedHead.Count -eq 1 -and [IO.Path]::GetFullPath($smokeReport.position_only_search_head_step_path) -eq [IO.Path]::GetFullPath($lockedHead[0].path) -and $smokeReport.position_only_search_head_step_sha256 -eq $lockedHead[0].sha256 -and (Sha $lockedHead[0].path) -eq $lockedHead[0].sha256) 'Offline options smoke helper identity does not match the frozen runtime lock.'
Require ($lockedBuilder.Count -eq 1 -and [IO.Path]::GetFullPath($smokeReport.options_builder_path) -eq [IO.Path]::GetFullPath($lockedBuilder[0].path) -and $smokeReport.options_builder_sha256 -eq $lockedBuilder[0].sha256 -and (Sha $lockedBuilder[0].path) -eq $lockedBuilder[0].sha256) 'Offline options smoke builder identity does not match frozen setup lock.'
Require (Test-Path -LiteralPath (Join-Path $expDir 'reports\offline_options_smoke_stale_20261021_v1.json') -PathType Leaf) 'Prior offline smoke report was not preserved under an explicit stale/versioned name.'
$staleSmoke=Get-Content -LiteralPath (Join-Path $expDir 'reports\offline_options_smoke_stale_20261021_v1.json') -Raw|ConvertFrom-Json
Require ($staleSmoke.frozen_inputs_sha256 -eq '95c7503840ff7fb455a98c24701481ce7dc3936e847255ec2214a01b54a67870') 'Archived smoke report is not the known stale snapshot.'
$lockStaleSmoke=Get-Content -LiteralPath (Join-Path $expDir 'reports\offline_options_smoke_stale_20261022_v2.json') -Raw|ConvertFrom-Json
Require ($lockStaleSmoke.frozen_inputs_sha256 -eq '75e54b948ee41b989fe7fa16a8c91dec4c6a56993b6df2e6ed262e5472116ccf') 'Prior pre-final-lock smoke report must be preserved as stale.'
$secondStaleSmoke=Get-Content -LiteralPath (Join-Path $expDir 'reports\offline_options_smoke_stale_20261022_v3.json') -Raw|ConvertFrom-Json
Require ($secondStaleSmoke.frozen_inputs_sha256 -eq '0a8f7100da83e2209ac80dfed45e32a57798b4f5795a3fe777299cff117577cf') 'Intermediate smoke report must be preserved as stale.'
Require ($runner -match 'max\(double\(lock\.safety\.estimated_runtime_per_attempt_seconds\),\s*\.\.\.\s*double\(probeSummary\.attempt_execution_and_raw_persistence_seconds\)\)\s*\*\s*11\s*\*\s*1\.25' -and $preflight -match '\[Math\]::Max\(\[double\]\$lock\.safety\.estimated_runtime_per_attempt_seconds,\$observedAttemptSeconds\)\*11\*1\.25') 'CONTINUE time budget must use the lock upper bound or observed attempt persistence duration, whichever is larger, plus margin.'
Require ($runner -match 'episode_runtime_seconds' -and $runner -match 'attempt_execution_and_raw_persistence_seconds' -and $runner -match 'attemptExecutionTimer' -and $scorer -match 'candidate_episode_runtime_s' -and $scorer -match 'candidate_attempt_execution_and_raw_persistence_s' -and $scorer -notmatch '(^|[^A-Za-z_])runtime_seconds([^A-Za-z_]|$)') 'Runner/scorer must distinguish episode-only and bounded attempt persistence timing.'
foreach($f in $lock.setupFiles){Require ((Sha $f.path) -eq $f.sha256) "Setup SHA mismatch: $($f.name)"}
foreach($f in $lock.plantFiles){Require ((Sha $f.path) -eq $f.sha256) "Plant source SHA mismatch: $($f.name)"}
foreach($f in $lock.runtimeFiles){Require ((Sha $f.path) -eq $f.sha256) "Runtime SHA mismatch: $($f.path)"}
Require ((Sha $lock.scene_list.path) -eq $lock.scene_list.sha256 -and (Sha $lock.reuse_manifest.path) -eq $lock.reuse_manifest.sha256 -and (Sha $lock.scene_payload_identity.path) -eq $lock.scene_payload_identity.sha256) 'Frozen VAL identity input SHA mismatch.'
Require ((Sha $lock.upstream_round1.lock_path) -eq $lock.upstream_round1.lock_sha256 -and (Sha $lock.upstream_round1.results_path) -eq $lock.upstream_round1.results_sha256 -and (Sha $lock.upstream_round1.summary_path) -eq $lock.upstream_round1.summary_sha256) 'Round 1 upstream evidence SHA mismatch.'
Require (-not (Test-Path -LiteralPath (Join-Path $expDir 'runs'))) 'R2 runs directory exists; fresh static package requires no runs.'
Require (@(Get-Process -Name matlab -ErrorAction SilentlyContinue).Count -eq 0) 'MATLAB is active; static package test expects idle environment.'
Write-Output 'ROUND2_STATIC PASS: exact PCF-only option diff; locked source identities; WDDM graphics classification/compute gate; 12 VAL scenes/24 reused ON-B raws; no runs; no MATLAB process.'
exit 0










