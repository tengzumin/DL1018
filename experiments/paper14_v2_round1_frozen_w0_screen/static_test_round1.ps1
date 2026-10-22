param([switch] $AllowCompletedProbe)
$ErrorActionPreference = 'Stop'
$expDir = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $expDir)
$lock = Get-Content -LiteralPath (Join-Path $expDir 'frozen_inputs.json') -Raw | ConvertFrom-Json -DateKind String
$sceneRows = @(Import-Csv -LiteralPath $lock.scene_list.path)
$rawRows = @(Import-Csv -LiteralPath $lock.reuse_manifest.path)
$expectedIds = @(
    'DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00',
    'DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T1_C00_W07',
    'DL1018_VAL_T3_C12_W09','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00'
)
$sceneHeader = Get-Content -LiteralPath $lock.scene_list.path -TotalCount 1
$sceneIdOrder = @($sceneRows | ForEach-Object { $_.scene_id })
if ($sceneHeader -cne 'task,band,scene_id' -or $sceneRows.Count -ne 12 -or
    ($sceneIdOrder -join "`n") -cne ($expectedIds -join "`n") -or
    (@($sceneRows | Where-Object { $_.scene_id -notlike 'DL1018_VAL_*' })).Count -ne 0) {
    throw 'Exact scene CSV schema/order/VAL ID check failed.'
}
if ($rawRows.Count -ne 24 -or (@($rawRows | Where-Object split -ne 'VAL')).Count -ne 0) { throw 'Raw manifest is not 24 VAL pairs.' }
foreach ($id in $expectedIds) {
    foreach ($role in @('ON_CANDIDATE','B_BASELINE')) {
        if (@($rawRows | Where-Object { $_.scene_id -eq $id -and $_.role -eq $role }).Count -ne 1) { throw "Missing $role identity for $id." }
    }
}
$lineageRows = @(Import-Csv -LiteralPath $lock.lineage.path | Where-Object { $_.scene_id -in $expectedIds })
$baselineScoreRows = @(Import-Csv -LiteralPath $lock.rescores[1].path | Where-Object { $_.scene_id -in $expectedIds })
$payloadRows = @(Import-Csv -LiteralPath $lock.scene_payload_identity.path)
if ($payloadRows.Count -ne 12 -or (@($payloadRows | Where-Object {
    $_.scene_id -notin $expectedIds -or $_.status -ne 'IDENTICAL' -or
    [int]$_.physical_field_count -ne 14 -or [int]$_.time_samples -ne 20001 -or
    [double]$_.max_abs_physical_scene_diff -ne 0
})).Count -ne 0) { throw 'Scene payload identity must prove all twelve VAL pairs identical over 14 fields and 20,001 samples.' }
if ($lineageRows.Count -ne 12) { throw 'Existing ON run_start lineage lacks the exact twelve VAL scenes.' }
foreach ($id in $expectedIds) {
    $onRun = @($lineageRows | Where-Object scene_id -eq $id)
    $candidateRaw = @($rawRows | Where-Object { $_.scene_id -eq $id -and $_.role -eq 'ON_CANDIDATE' })
    $bRaw = @($rawRows | Where-Object { $_.scene_id -eq $id -and $_.role -eq 'B_BASELINE' })
    $bScore = @($baselineScoreRows | Where-Object scene_id -eq $id)
    if ($onRun.Count -ne 1 -or $candidateRaw.Count -ne 1 -or $bRaw.Count -ne 1 -or $bScore.Count -ne 1 -or
        $onRun[0].raw_sha256 -ne $candidateRaw[0].raw_sha256 -or
        $onRun[0].run_start_model_id -ne $lock.model.canonical_id -or
        $onRun[0].run_start_method_id -ne $lock.run.method -or
        $onRun[0].run_start_architecture -ne 'DSSM' -or $onRun[0].run_start_seed -ne '2026102001' -or
        $onRun[0].run_start_selected_step -ne '60000' -or $onRun[0].run_start_input_dim -ne '14' -or
        $onRun[0].run_start_window -ne '32' -or $onRun[0].run_start_context_length -ne '32' -or
        $onRun[0].run_start_head_type -ne 'FEATURE' -or $onRun[0].run_start_head_enabled -ne '1' -or
        $onRun[0].run_start_update_enabled -ne '1' -or $onRun[0].run_start_gamma -ne '12.0' -or
        $onRun[0].run_start_kappa -ne '1.0' -or $onRun[0].run_start_beta_scale -ne '1.0' -or
        $onRun[0].run_start_pcf_enabled -ne '1' -or $onRun[0].run_start_position_update_hz -ne '100.0' -or
        $onRun[0].run_start_plant_dt_s -ne '0.001') { throw "Actual ON run_start contract mismatch for $id." }
    if ($bRaw[0].raw_scan_helper_sha256 -ne $lock.scoring_helper.sha256 -or
        $bRaw[0].rescore_csv_sha256 -ne $lock.rescores[1].sha256 -or
        $bScore[0].resolved_raw_path -ne $bRaw[0].raw_path -or
        $bScore[0].resolved_raw_sha256_expected -ne $bRaw[0].raw_sha256 -or
        $bScore[0].manifest_source_raw_path -ne $bRaw[0].paired_source_raw_path -or
        $bScore[0].'rescore_matches_pair_with_1e-12_m_tolerance' -ne 'True') { throw "B raw resolved-path/hash/scorer/rescore provenance mismatch for $id." }
}
$binding = Get-Content -LiteralPath $lock.model_binding.path -Raw | ConvertFrom-Json
if ($binding.status -ne 'PASS_NEW_MODEL_BINDING_FORWARD' -or $binding.science_rows -ne 0 -or
    $binding.plant_calls_started -ne 0 -or $binding.test_files_read -ne 0) { throw 'Model binding report is not a no-Plant/no-TEST PASS.' }
if ($lock.scenes.Count -ne 12 -or $lock.run.seed -ne 2026102001 -or $lock.run.optimizer_steps -ne 0 -or
    $lock.run.duration_s -ne 20 -or $lock.run.plant_dt_s -ne 0.001 -or $lock.run.position_event_hz -ne 100 -or
    $lock.safety.minimum_free_bytes -ne 30000000000 -or $lock.safety.max_cycle_output_bytes -ne 80000000000 -or
    $lock.safety.estimated_cycle_output_bytes -ne 805306368) { throw 'Frozen run contract/budget check failed.' }
if ($lock.plantFiles.Count -ne 22 -or $lock.safety.global_deadline_utc -ne '2026-10-24T17:01:00Z' -or
    $lock.safety.selected_pair_raw_count -ne 24 -or $lock.safety.selected_pair_raw_max_bytes -ne 49600404 -or
    $lock.safety.estimated_bytes_per_attempt -ne 67108864) { throw 'Plant source, global deadline, or empirical output estimate lock failed.' }
if ($lock.scene_payload_identity.sha256 -ne (Get-FileHash -LiteralPath $lock.scene_payload_identity.path -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Scene payload identity file SHA check failed.'
}
if ($lock.model.PSObject.Properties.Name -contains 'model_arrays_identity_sha256') {
    throw 'Unverified aggregate model-array identity must not be used as a runtime lock.'
}

$builder = Get-Content -LiteralPath (Join-Path $expDir 'build_frozen_w0_options.m') -Raw
if ($builder -notmatch "opts\.stage1_position_runtime\.update_enabled\s*=\s*false" -or
    $builder -notmatch "position_only_search_options\(cfg, model, 'FEATURE', 12, 1\)" -or
    $builder -notmatch 'position_only_search_head' -or $builder -notmatch 'command_filter_coordination_v3_5\.enabled' -or
    $builder -match 'online_updates_enabled\s*=\s*false') { throw 'Single-factor option builder/static PCF contract check failed.' }
$offMutationCount = [regex]::Matches($builder, 'opts\.stage1_position_runtime\.update_enabled\s*=\s*false').Count
if ($offMutationCount -ne 1) { throw 'OFF builder must contain exactly one experimental option mutation.' }

$runnerPath = $lock.runtimeFiles[0].path
$runner = Get-Content -LiteralPath $runnerPath -Raw
foreach ($token in @(
    'elseif stage1SearchEnabled'
    'headClipped=max(min(raw,cfg.rbf.position.dmax(:))'
    'applied=beta*headClipped'
    'weightNext=stage1PositionWeight'
    'stage1PositionWeight=weightNext'
    'position_head_update_executed'
    'stage1_position_event_weight_before_33x3'
    'stage1_position_event_weight_after_33x3'
    'stage1_position_update_enabled'
    'stage1_position_search_head_enabled'
)) {
    if ($runner -notlike "*$token*") { throw "Frozen-W0 runner behavior evidence missing token: $token" }
}
$runEntry = Get-Content -LiteralPath (Join-Path $expDir 'run_frozen_w0_screen.m') -Raw
if ($runEntry -match 'sceneTable\.split' -or
    -not $runEntry.Contains("sceneTable.Properties.VariableNames, {'task','band','scene_id'}") -or
    -not $runEntry.Contains('isequal(sceneTable.scene_id(:), expectedIds(:))') -or
    -not $runEntry.Contains('startsWith(sceneTable.scene_id, "DL1018_VAL_")')) {
    throw 'Runner must validate the frozen scene CSV schema, exact order, and VAL prefix without a missing column.'
}
if ($runEntry -match 'make_scenes_dl1018|scene_specs\.csv|TEST_' -or
    $runEntry -notmatch "load\(char\(bRow\.raw_path\), 'scene'\)" -or
    $runEntry -notmatch 'stage1_position_event_weight_before_33x3' -or
    $runEntry -notmatch 'stage1_position_event_weight_after_33x3' -or
    $runEntry -notmatch 'position_head_update_executed' -or
    $runEntry -notmatch "fullfile\(here, 'runs'\)" -or
    $runEntry -notmatch "fullfile\(runsRoot, sceneId, 'attempt_01'\)" -or
    $runEntry -notmatch 'verify_source_chain\(lock\.plantFiles\)' -or
    $runEntry -notmatch 'scene_payload_identity' -or $runEntry -notmatch 'attempt_output_bytes' -or
    $runEntry -notmatch 'inputIdentity' -or $runEntry -notmatch 'modelIdentity' -or
    $runEntry -notmatch 'globalDeadline' -or $runEntry -notmatch 'parent_reviewed_switch_present' -or
    $runEntry -notmatch 'minutes\(5\)' -or
    $runEntry -notmatch 'frozen_inputs_sha256') { throw 'Future runner source/isolation check failed.' }
$lockedInputsPosition = $runEntry.IndexOf('verify_locked_inputs(lock);')
$restoreDefaultPosition = $runEntry.IndexOf('restoredefaultpath;')
$initRuntimeSearchPosition = $runEntry.IndexOf('initRuntimeIndex = find(endsWith(string({lock.runtimeFiles.path}), ...')
$initRuntimeDirPosition = $runEntry.IndexOf('initRuntimeDir = fileparts(lock.runtimeFiles(initRuntimeIndex).path);')
$initFileCheckPosition = $runEntry.IndexOf("assert(isfile(fullfile(initRuntimeDir, 'init_dl1018.m'))")
$initRuntimeAddPathPosition = $runEntry.IndexOf("addpath(initRuntimeDir, '-begin');")
$initPosition = $runEntry.IndexOf('[cfg, ~, resolvedRoot] = init_dl1018();')
$lockedRuntimeDirPosition = $runEntry.IndexOf('lockedRuntimeDir = fileparts(lock.runtimeFiles(1).path);')
$lockedRuntimeAddPathPosition = $runEntry.IndexOf("addpath(lockedRuntimeDir, '-begin');")
$clearPosition = $runEntry.IndexOf('clear run_dl1018_closed_loop')
$rehashPosition = $runEntry.IndexOf('rehash;')
$runtimeVerifyPosition = $runEntry.IndexOf('runtimeSourceIdentity = verify_runtime_chain(lock.runtimeFiles);')
$runtimePathAssertPosition = $runEntry.IndexOf("assert(strcmpi(which('run_dl1018_closed_loop'), fullfile(lockedRuntimeDir, 'run_dl1018_closed_loop.m'))")
$initRuntimeAddPathCount = [regex]::Matches($runEntry, [regex]::Escape("addpath(initRuntimeDir, '-begin');")).Count
$lockedRuntimeAddPathCount = [regex]::Matches($runEntry, [regex]::Escape("addpath(lockedRuntimeDir, '-begin');")).Count
$bBeforePosition = $runEntry.IndexOf('bIdentityBeforeLoad = file_identity(char(bRow.raw_path));')
$bLoadPosition = $runEntry.IndexOf("b = load(char(bRow.raw_path), 'scene');")
$bAfterPosition = $runEntry.IndexOf('bIdentityAfterLoad = file_identity(char(bRow.raw_path));')
if ($lockedInputsPosition -lt 0 -or $initPosition -lt 0 -or $lockedInputsPosition -ge $initPosition -or
    $restoreDefaultPosition -lt 0 -or $initRuntimeSearchPosition -lt 0 -or $initRuntimeDirPosition -lt 0 -or
    $initFileCheckPosition -lt 0 -or $initRuntimeAddPathPosition -lt 0 -or $initRuntimeAddPathCount -ne 1 -or
    $restoreDefaultPosition -ge $initRuntimeSearchPosition -or $initRuntimeSearchPosition -ge $initRuntimeDirPosition -or
    $initRuntimeDirPosition -ge $initFileCheckPosition -or $initFileCheckPosition -ge $initRuntimeAddPathPosition -or
    $initRuntimeAddPathPosition -ge $initPosition -or
    $runEntry -notmatch 'string\(\{lock\.runtimeFiles\.path\}\)' -or
    $runEntry -notmatch 'string\(filesep\) \+ "init_dl1018\.m"' -or
    $runEntry -notmatch 'lock\.runtimeFiles\(initRuntimeIndex\)\.path' -or
    $lockedRuntimeDirPosition -le $initPosition -or $lockedRuntimeAddPathPosition -le $lockedRuntimeDirPosition -or
    $lockedRuntimeAddPathPosition -ge $clearPosition -or $clearPosition -ge $rehashPosition -or
    $rehashPosition -ge $runtimeVerifyPosition -or $runtimeVerifyPosition -ge $runtimePathAssertPosition -or
    $lockedRuntimeAddPathCount -ne 1 -or
    $runEntry -notmatch 'lock\.runtimeFiles\(1\)\.path' -or
    $runEntry -notmatch 'pf\.frozen_inputs_sha256' -or $runEntry -notmatch 'lock\.setupFiles' -or
    $runEntry -notmatch 'lock\.plantFiles' -or $runEntry -notmatch 'lock\.runtimeFiles' -or
    $runEntry -notmatch 'lock\.model\.mat_sha256' -or $runEntry -notmatch 'lock\.normalizer\.npz_file_sha256' -or
    $runEntry -notmatch 'lock\.rescores\(k\)\.sha256' -or $runEntry -notmatch 'lock\.mechanism_evidence\(k\)\.sha256' -or
    $runEntry -notmatch 'lock\.setupFiles\(k\)\.sha256' -or $runEntry -notmatch 'lock\.taskbook\.sha256' -or
    $bBeforePosition -lt 0 -or $bLoadPosition -le $bBeforePosition -or $bAfterPosition -le $bLoadPosition -or
    $runEntry -notmatch 'bIdentityAfterLoad\.bytes == bIdentityBeforeLoad\.bytes' -or
    $runEntry -notmatch 'bIdentityAfterLoad\.mtime == bIdentityBeforeLoad\.mtime' -or
    $runEntry -notmatch 'strcmpi\(bIdentityAfterLoad\.sha256, char\(bRow\.raw_sha256\)\)') {
    throw 'MATLAB runner must rehash the frozen input lock before initialization and verify B raw before/after scene load.'
}
$resultConstructPosition = $runEntry.IndexOf("result = struct('scene_id")
$resultConstructEndMarker = "'probe_started_utc', char(startedAt));"
$resultConstructEnd = $runEntry.IndexOf($resultConstructEndMarker, $resultConstructPosition)
$resultPlantShaPosition = $runEntry.IndexOf('result.plant_source_sha256 = {plantSourceIdentity.sha256};')
$resultRuntimeShaPosition = $runEntry.IndexOf('result.runtime_source_sha256 = {runtimeSourceIdentity.sha256};')
$resultStatusWritePosition = $runEntry.IndexOf("write_text(fullfile(attemptDir, 'run_status.json'), jsonencode(result));")
if ($resultConstructPosition -lt 0 -or $resultConstructEnd -le $resultConstructPosition -or
    $resultPlantShaPosition -le $resultConstructEnd -or $resultRuntimeShaPosition -le $resultPlantShaPosition -or
    $resultStatusWritePosition -le $resultRuntimeShaPosition) {
    throw 'Run result serialization must construct a scalar before assigning source SHA arrays.'
}
$resultConstructText = $runEntry.Substring($resultConstructPosition, $resultConstructEnd + $resultConstructEndMarker.Length - $resultConstructPosition)
if ($resultConstructText -match 'plant_source_sha256|runtime_source_sha256') {
    throw 'Plant/runtime source SHA arrays must not be struct constructor arguments.'
}
$episodeSource = Get-Content -LiteralPath $lock.runtimeFiles[1].path -Raw
if ($episodeSource -notmatch "save\(rawPath,'log','scene','method','-v7\.3'\)") {
    throw 'Existing runner source does not save the complete scene variable into the reusable MAT raw.'
}

$preflight = Get-Content -LiteralPath (Join-Path $expDir 'preflight_round1.ps1') -Raw
if ($preflight -notmatch 'SOLIDWORKS_MCP_CAD' -or $preflight -notmatch 'OTHER_PYTHON' -or
    $preflight -notmatch '\[switch\] \$ParentReviewed' -or
    $preflight -notmatch 'parent_reviewed_switch_present' -or
    $preflight -notmatch 'frozen_inputs_sha256' -or
    $preflight -notmatch 'verify_scene_payload_identity\.py' -or
    $preflight -notmatch 'scene_payload_verifier_exit_code' -or
    $preflight -match 'Stop-Process|taskkill|Remove-Item|Copy-Item|Start-Process') { throw 'Preflight process safety/category check failed.' }
$sceneVerifier = Get-Content -LiteralPath (Join-Path $expDir 'verify_scene_payload_identity.py') -Raw
if ($sceneVerifier -notmatch 'PHYSICAL_FIELDS' -or $sceneVerifier -notmatch 'np\.array_equal' -or
    $sceneVerifier -notmatch 'stable_file_identity' -or $sceneVerifier -match 'write_text|to_csv|save\(') {
    throw 'Read-only 14-field scene payload verifier source check failed.'
}
$launcher = Get-Content -LiteralPath (Join-Path $expDir 'launch_round1.ps1') -Raw
if ($launcher -notmatch 'preflight_round1\.ps1' -or $launcher -notmatch '\-batch' -or
    $launcher -notmatch 'ParentReviewed' -or $launcher -notmatch 'ParentReviewed:\$ParentReviewed' -or
    $launcher -notmatch 'parent_reviewed_switch_present' -or $launcher -notmatch 'globalDeadline' -or
    $launcher -match 'Copy-Item|Stop-Process|taskkill') { throw 'Future launcher gate check failed.' }

$taskbook = Get-Content -LiteralPath (Join-Path $expDir 'TASKBOOK_ZH.md') -Raw
if ($taskbook -match '\$\(' -or $taskbook -notmatch '2026-10-24T17:01:00Z' -or
    $taskbook -notmatch 'OFF−ON' -or $taskbook -notmatch '20,000' -or
    $taskbook -notmatch 'run_start\.mat/raw_run\.mat' -or
    $taskbook -notmatch 'scene_payload_identity\.csv' -or
    $taskbook -notmatch 'preflight 绑定的 frozen_inputs SHA' -or
    $taskbook -notmatch '文件大小、mtime 和 SHA' -or
    $taskbook -notmatch '8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26' -or
    $taskbook -notmatch 'C-order 连续数组字节' -or
    $taskbook -notmatch '不代表父审批准') { throw 'Taskbook unresolved placeholder or required contract missing.' }
if ($taskbook -notmatch 'ad0810c2fc25f93b34e61432631d26d876712c4717946e6770f6fce58cbcda28' -or
    $taskbook -notmatch '0\.00851665899477647' -or $taskbook -notmatch '0\.008693982397142386' -or
    $taskbook -notmatch '0\.02999291272652684' -or $taskbook -notmatch 'recovered_after_serialization_error' -or
    $taskbook -notmatch '只写不存在文件' -or $taskbook -notmatch '保守上界而非实测') {
    throw 'Completed-probe serialization-failure audit and no-overwrite recovery boundary missing.'
}
foreach ($source in $lock.plantFiles) {
    if ($taskbook -notmatch [regex]::Escape($source.name) -or $taskbook -notmatch [regex]::Escape($source.sha256)) {
        throw "Taskbook lacks locked Plant source identity $($source.name)."
    }
}
foreach ($source in $lock.setupFiles) {
    $actual = (Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $source.sha256 -or $taskbook -notmatch [regex]::Escape($source.name) -or
        $taskbook -notmatch [regex]::Escape($source.sha256)) {
        throw "Taskbook/setup SHA identity mismatch for $($source.name)."
    }
}
foreach ($id in $expectedIds) { if ($taskbook -notmatch [regex]::Escape($id)) { throw "Taskbook lacks frozen scene $id." } }

$runsDir = Join-Path $expDir 'runs'
$probeId = $expectedIds[0]
if (Test-Path -LiteralPath $runsDir) {
    if (-not $AllowCompletedProbe) { throw 'Static test found run output; fresh-package mode requires no runs. Use -AllowCompletedProbe only for the exact reviewed probe artifact.' }
    $runChildren = @(Get-ChildItem -LiteralPath $runsDir -Force)
    if ($runChildren.Count -ne 1 -or -not $runChildren[0].PSIsContainer -or $runChildren[0].Name -cne $probeId) {
        throw 'Completed-probe static mode accepts only the first frozen scene directory.'
    }
    $sceneDir = $runChildren[0].FullName
    $sceneChildren = @(Get-ChildItem -LiteralPath $sceneDir -Force)
    if ($sceneChildren.Count -ne 1 -or -not $sceneChildren[0].PSIsContainer -or $sceneChildren[0].Name -cne 'attempt_01') {
        throw 'Completed-probe static mode accepts exactly one attempt_01 directory.'
    }
    $attemptDir = $sceneChildren[0].FullName
    $attemptItems = @(Get-ChildItem -LiteralPath $attemptDir -Force)
    $expectedProbeFiles = @('attempt_started.marker','raw_run.mat','run_start.mat')
    if ($attemptItems.Count -ne $expectedProbeFiles.Count -or
        (@($attemptItems | Where-Object { $_.PSIsContainer -or $_.Name -notin $expectedProbeFiles })).Count -ne 0 -or
        (@($expectedProbeFiles | Where-Object { $_ -notin @($attemptItems.Name) })).Count -ne 0) {
        throw 'Completed-probe static mode requires exactly marker, run_start.mat, and raw_run.mat.'
    }
    $completedRawSha = (Get-FileHash -LiteralPath (Join-Path $attemptDir 'raw_run.mat') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($completedRawSha -ne 'ad0810c2fc25f93b34e61432631d26d876712c4717946e6770f6fce58cbcda28') {
        throw 'Completed-probe raw SHA differs from the reviewed artifact.'
    }
} elseif ($AllowCompletedProbe) {
    throw '-AllowCompletedProbe requires the exact reviewed single-probe artifact.'
}
Write-Output 'STATIC_PREFLIGHT PASS: 12 VAL IDs, one option difference, scalar result serialization, guarded output state, no simulator invocation.'
exit 0
