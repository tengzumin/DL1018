$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'
$taskDir = Join-Path $taskRoot 'experiments/position_axis_coordinate_c5_20261023'
$bindingPath = Join-Path $taskDir 'C5_TAIL11_SOURCE_BINDING_v1.json'
$tailContractPath = Join-Path $taskDir 'C5_TAIL11_RUN_CONTRACT_v1.json'
$releaseContractPath = Join-Path $taskDir 'C5_TAIL11_PARENT_RELEASE_CONTRACT_v1.json'
$releasePath = Join-Path $taskDir 'C5_TAIL11_RELEASE_v1.json'
$batchPath = Join-Path $taskDir 'C5_TAIL11_BATCH_STATUS_v1.json'
$bodyPath = Join-Path $taskDir 'C5_TAIL11_BODY_COMPLETE_v1.json'
$exitPath = Join-Path $taskDir 'C5_TAIL11_OS_EXIT_v1.json'
$preflightFailurePath = Join-Path $taskDir 'C5_TAIL11_PREFLIGHT_FAILURE_v1.json'
$runnerPath = Join-Path $taskDir 'run_c5_tail11_v1.m'
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior C5 tail exit record; do not rerun.' }
if ((Test-Path -LiteralPath $batchPath) -or (Test-Path -LiteralPath $bodyPath) -or (Test-Path -LiteralPath $preflightFailurePath)) { throw 'C5 tail output exists; preserve it and do not rerun.' }
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
if (-not ((Test-Path -LiteralPath $bindingPath) -and (Test-Path -LiteralPath $tailContractPath) -and (Test-Path -LiteralPath $releaseContractPath) -and (Test-Path -LiteralPath $releasePath))) { throw 'C5 tail source binding, contracts and separate parent release are required.' }
$binding = Get-Content -LiteralPath $bindingPath -Raw | ConvertFrom-Json
$tailContract = Get-Content -LiteralPath $tailContractPath -Raw | ConvertFrom-Json
$releaseContract = Get-Content -LiteralPath $releaseContractPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$runnerSha = (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$bindingSha = (Get-FileHash -LiteralPath $bindingPath -Algorithm SHA256).Hash.ToLowerInvariant()
$launcherSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$tailContractSha = (Get-FileHash -LiteralPath $tailContractPath -Algorithm SHA256).Hash.ToLowerInvariant()
$releaseContractSha = (Get-FileHash -LiteralPath $releaseContractPath -Algorithm SHA256).Hash.ToLowerInvariant()
$inputLockPath = Join-Path $taskDir 'C5_AXIS_COORDINATE_INPUT_LOCK_v1.json'
$runContractPath = Join-Path $taskDir 'C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json'
$prepPath = Join-Path $taskDir 'C5_AXIS_COORDINATE_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat'
$inputLockSha = (Get-FileHash -LiteralPath $inputLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
$runContractSha = (Get-FileHash -LiteralPath $runContractPath -Algorithm SHA256).Hash.ToLowerInvariant()
$prepSha = (Get-FileHash -LiteralPath $prepPath -Algorithm SHA256).Hash.ToLowerInvariant()
$snapshotSha = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($binding.schema -ne 'C5_TAIL11_SOURCE_BINDING_V1' -or $binding.state -ne 'SOURCE_BOUND_C5_TAIL11_WAIT_PARENT_RELEASE_V1' -or $releaseContract.schema -ne 'C5_TAIL11_PARENT_RELEASE_CONTRACT_V1' -or $releaseContract.state -ne 'CONTRACT_ONLY_PARENT_RELEASE_REQUIRED') { throw 'C5 tail binding or release contract schema/state mismatch.' }
if ($release.schema -ne 'C5_TAIL11_PARENT_RELEASE_V1' -or $release.state -ne 'APPROVED_C5_TAIL11_V1' -or -not $release.plant_authorized -or -not $release.subsequent_11_flights_authorized -or [int]$release.max_new_Plant -ne 11) { throw 'Exact parent approval for all eleven remaining scenes is required.' }
if ($release.tail_runner_sha256 -ne $runnerSha -or $release.tail_runner_path -ne $runnerPath -or $release.tail_source_binding_sha256 -ne $bindingSha -or $release.launcher_sha256 -ne $launcherSha -or $release.tail_run_contract_sha256 -ne $tailContractSha -or $release.parent_release_contract_sha256 -ne $releaseContractSha -or $release.c5_input_lock_sha256 -ne $inputLockSha -or $release.c5_run_contract_sha256 -ne $runContractSha -or $release.prepare_result_sha256 -ne $prepSha -or $release.cfg_opts_snapshot_sha256 -ne $snapshotSha) { throw 'Tail release does not bind the exact runner, launcher, contracts and prepared C5 inputs.' }
if ($releaseContract.parent_release_schema -ne $release.schema -or $releaseContract.required_release_state -ne $release.state -or $release.tail_scene_count -ne 11 -or $release.max_total_Plant_including_pilot -ne 12) { throw 'C5 parent release contract scope mismatch.' }
$tailIds = @($release.tail_scene_ids)
if ($tailIds.Count -ne 11 -or @($tailIds | Select-Object -Unique).Count -ne 11 -or (($tailIds -join '|') -ne (@($tailContract.tail_scene_ids) -join '|'))) { throw 'C5 tail release scene IDs/order differ from the frozen contract.' }
$matlabProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(MATLAB|matlab)\.exe$' })
if ($matlabProcesses.Count) { throw 'A MATLAB process is already running; do not interrupt it or start another heavy job.' }
$reserveBytes = [int64]$release.per_scene_output_reserve_bytes * [int64]$tailIds.Count
$minimumFree = [int64]$release.minimum_free_bytes
$freeBytes = [int64](Get-PSDrive -Name C).Free
if (($freeBytes - $reserveBytes) -lt $minimumFree) { throw 'Reserve-adjusted free space is below the frozen 30-GB floor.' }
$deadline = [DateTimeOffset]::Parse([string]$release.deadline_utc).UtcDateTime
$deadlineBuffer = 180 * $tailIds.Count + [int]$release.process_exit_buffer_seconds
if (($deadline - [DateTime]::UtcNow).TotalSeconds -lt $deadlineBuffer) { throw 'The remaining tail cannot meet the frozen per-scene runtime plus exit buffer before deadline.' }
$usedBytes = [int64](Get-ChildItem -LiteralPath $taskDir -File -Recurse -Force | Measure-Object -Property Length -Sum).Sum
if (($usedBytes + $reserveBytes) -gt [int64]$release.max_output_bytes) { throw 'C5 experiment directory cannot reserve 80 MB for each remaining scene under its 1-GiB cap.' }
$lock = Get-Content -LiteralPath $inputLockPath -Raw | ConvertFrom-Json
foreach ($sceneId in $tailIds) {
    $attempt = Join-Path $taskDir (Join-Path 'runs_c5_v1' (Join-Path $sceneId 'C5_AXIS_MASK_M110/attempt_01'))
    if (Test-Path -LiteralPath $attempt) { throw "Prior tail attempt exists for $sceneId; no retry." }
}
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_tail11_v1'
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023'); batch=run_c5_tail11_v1('PARENT_APPROVED_C5_TAIL11_V1'); fprintf('C5_TAIL11_RETURN=%s SCENES=%d PLANT_CALLS=%d\n',batch.status,batch.completed_scenes,batch.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$batchStatus = $null
$completedScenes = 0
$plantCalls = 0
$bodyStatus = 'NOT_WRITTEN'
$sceneExitRecordCount = 0
$launcherExitCode = $matlabOsExitCode
$finalizationError = ''
try {
    if (Test-Path -LiteralPath $batchPath) {
        $batchStatus = Get-Content -LiteralPath $batchPath -Raw | ConvertFrom-Json
        $completedScenes = [int]$batchStatus.completed_scenes
        $plantCalls = [int]$batchStatus.plant_calls
    }
} catch {
    $finalizationError = "Cannot read MATLAB batch status after natural return: $($_.Exception.Message)"
    $launcherExitCode = 1
}
if ($matlabOsExitCode -eq 0 -and -not $finalizationError) {
    try {
        $expectedIds = [string[]]$tailIds
        $actualIds = [string[]]@($batchStatus.records | ForEach-Object { $_.scene_id })
        if ($batchStatus.status -ne 'COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $completedScenes -ne 11 -or $plantCalls -ne 11 -or $actualIds.Count -ne 11 -or (($actualIds -join '|') -ne ($expectedIds -join '|'))) { throw 'MATLAB returned OS 0 without a complete, correctly ordered eleven-scene batch.' }
        $sharedExitRows = @(
            foreach ($record in $batchStatus.records) {
                [ordered]@{ scene_id=$record.scene_id; batch_index=$record.batch_index; batch_id=$batchStatus.batch_id; batch_scope='ONE_SEQUENTIAL_MATLAB_PROCESS'; shared_matlab_os_exit_code=$matlabOsExitCode; shared_matlab_process_count=1; raw_path=$record.raw_path; raw_sha256=$record.raw_sha256; run_status_path=$record.run_status_path; run_status_sha256=$record.run_status_sha256; run_start_path=$record.run_start_path; run_start_sha256=$record.run_start_sha256; attempt_started_marker_path=$record.attempt_started_marker_path; attempt_started_marker_sha256=$record.attempt_started_marker_sha256; first_plant_step_marker_path=$record.first_plant_step_marker_path; first_plant_step_marker_sha256=$record.first_plant_step_marker_sha256; plant_calls=$record.plant_calls }
            }
        )
        $body = [ordered]@{ schema='C5_TAIL11_BODY_COMPLETE_V1'; status='COMPLETE_RAW_PENDING_PARENT_AUDIT'; batch_id=$batchStatus.batch_id; batch_scope='ONE_SEQUENTIAL_MATLAB_PROCESS'; batch_scope_scene_ids=$expectedIds; matlab_process_count=1; shared_matlab_os_exit_code=$matlabOsExitCode; completed_scenes=$completedScenes; plant_calls=$plantCalls; per_scene_exit_record_count=$sharedExitRows.Count; per_scene_exit_records=$sharedExitRows; source_binding_sha256=$bindingSha; tail_release_sha256=(Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant(); created_utc=[DateTime]::UtcNow.ToString('o') }
        [IO.File]::WriteAllText($bodyPath, ($body | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
        $bodyStatus = $body.status
        $sceneExitRecordCount = $sharedExitRows.Count
    } catch {
        $finalizationError = $_.Exception.Message
        $launcherExitCode = 1
    }
}
$exitRecord = [ordered]@{ schema='C5_TAIL11_OS_EXIT_V1'; matlab_os_exit_code=$matlabOsExitCode; launcher_exit_code=$launcherExitCode; completed_utc=[DateTime]::UtcNow.ToString('o'); command_file=$PSCommandPath; command_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant(); source_binding_sha256=$bindingSha; runner_sha256=$runnerSha; parent_release_sha256=(Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant(); batch_status=$batchStatus.status; completed_scenes=$completedScenes; plant_calls=$plantCalls; body_status=$bodyStatus; shared_matlab_process_count=1; per_scene_exit_record_count=$sceneExitRecordCount; tail_scene_ids=$tailIds; plant_authorized=[bool]$release.plant_authorized; matlab_called_once=$true; finalization_error=$finalizationError }
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; LAUNCHER_EXIT_CODE={1}; BATCH={2}; SCENES={3}; PLANT_CALLS={4}" -f $matlabOsExitCode, $launcherExitCode, $batchStatus.status, $completedScenes, $plantCalls)
exit $launcherExitCode
