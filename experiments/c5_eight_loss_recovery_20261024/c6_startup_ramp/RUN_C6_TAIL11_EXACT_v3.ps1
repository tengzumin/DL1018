$ErrorActionPreference = 'Stop'
function Get-C6FixedDeadlineUtc {
    param([string]$JsonPath, [object]$Value, [string]$Label)
    $expectedText = '2026-10-24T17:01:00Z'
    $rawJson = [IO.File]::ReadAllText($JsonPath)
    $deadlineMatches = [regex]::Matches($rawJson, '"deadline_utc"\s*:\s*"([^"]+)"')
    if ($deadlineMatches.Count -ne 1 -or $deadlineMatches[0].Groups[1].Value -cne $expectedText) {
        throw "$Label raw JSON deadline must be exactly $expectedText."
    }
    if ($Value -is [DateTimeOffset]) {
        $parsedUtc = $Value.ToUniversalTime()
    } elseif ($Value -is [DateTime]) {
        if ($Value.Kind -eq [DateTimeKind]::Unspecified) {
            $parsedUtc = [DateTimeOffset]::new([DateTime]$Value, [TimeSpan]::Zero).ToUniversalTime()
        } else {
            $parsedUtc = ([DateTimeOffset]$Value).ToUniversalTime()
        }
    } elseif ($Value -is [string]) {
        $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
        $parsedUtc = [DateTimeOffset]::ParseExact($Value, "yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture, $styles)
    } else {
        throw "$Label deadline has unsupported parsed type: $($Value.GetType().FullName)"
    }
    $fixedUtc = [DateTimeOffset]::new(2026, 10, 24, 17, 1, 0, [TimeSpan]::Zero)
    if ($parsedUtc.UtcDateTime.Ticks -ne $fixedUtc.UtcDateTime.Ticks) {
        throw "$Label typed deadline differs from the fixed UTC deadline."
    }
    return $parsedUtc.UtcDateTime
}
$taskRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'
$taskDir = Join-Path $taskRoot 'experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'
$reportDir = Join-Path $taskRoot 'reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp'
$bindingPath = Join-Path $taskDir 'C6_TAIL11_SOURCE_BINDING_v3.json'
$tailContractPath = Join-Path $taskDir 'C6_TAIL11_RUN_CONTRACT_v1.json'
$releaseContractPath = Join-Path $taskDir 'C6_TAIL11_PARENT_RELEASE_CONTRACT_v3.json'
$releasePath = Join-Path $taskDir 'C6_TAIL11_PARENT_RELEASE_v3.json'
$inputLockPath = Join-Path $taskDir 'C6_STARTUP_RAMP_INPUT_LOCK_v1.json'
$runContractPath = Join-Path $taskDir 'C6_STARTUP_RAMP_RUN_CONTRACT_v1.json'
$prepPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat'
$firstReleasePath = Join-Path $taskDir 'C6_FIRST_PARENT_RELEASE_v1.json'
$runnerPath = Join-Path $taskDir 'run_c6_startup_ramp_tail11_v3.m'
$batchPath = Join-Path $taskDir 'C6_TAIL11_BATCH_STATUS_v3.json'
$bodyPath = Join-Path $taskDir 'C6_TAIL11_BODY_COMPLETE_v3.json'
$preflightFailurePath = Join-Path $taskDir 'C6_TAIL11_PREFLIGHT_FAILURE_v3.json'
$osExitPath = Join-Path $reportDir 'C6_TAIL11_MATLAB_OS_EXIT_v3.json'
$receiptPath = Join-Path $reportDir 'C6_TAIL11_EXECUTION_RECEIPT_v3.json'
$stdoutPath = Join-Path $reportDir 'C6_TAIL11_MATLAB_STDOUT_v3.log'
$stderrPath = Join-Path $reportDir 'C6_TAIL11_MATLAB_STDERR_v3.log'
foreach ($path in @($osExitPath,$receiptPath,$stdoutPath,$stderrPath,$batchPath,$bodyPath,$preflightFailurePath)) {
    if (Test-Path -LiteralPath $path) { throw "Prior C6 tail output exists; preserve it and do not retry: $path" }
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
foreach ($path in @($bindingPath,$tailContractPath,$releaseContractPath,$releasePath,$inputLockPath,$runContractPath,$prepPath,$snapshotPath,$firstReleasePath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Post-first reviewed binding, contracts and exact release are required: $path" }
}
$binding = Get-Content -LiteralPath $bindingPath -Raw | ConvertFrom-Json
$tailContract = Get-Content -LiteralPath $tailContractPath -Raw | ConvertFrom-Json
$releaseContract = Get-Content -LiteralPath $releaseContractPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$contract = Get-Content -LiteralPath $runContractPath -Raw | ConvertFrom-Json
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$runnerSha = & $sha $runnerPath
$bindingSha = & $sha $bindingPath
$launcherSha = & $sha $PSCommandPath
$tailContractSha = & $sha $tailContractPath
$releaseContractSha = & $sha $releaseContractPath
$inputLockSha = & $sha $inputLockPath
$runContractSha = & $sha $runContractPath
$prepSha = & $sha $prepPath
$snapshotSha = & $sha $snapshotPath
$firstReleaseSha = & $sha $firstReleasePath
if ($binding.schema -ne 'C6_TAIL11_SOURCE_BINDING_V3' -or $binding.state -ne 'SOURCE_BOUND_C6_TAIL11_WAIT_PARENT_RELEASE_V3' -or $releaseContract.schema -ne 'C6_TAIL11_PARENT_RELEASE_CONTRACT_V1' -or $tailContract.schema -ne 'C6_TAIL11_RUN_CONTRACT_V1') { throw 'C6 tail binding or contract schema/state mismatch.' }
if ($release.schema -ne 'C6_TAIL11_PARENT_RELEASE_V1' -or $release.state -ne 'APPROVED_C6_TAIL11_V1' -or -not [bool]$release.plant_authorized -or -not [bool]$release.subsequent_11_flights_authorized -or [int]$release.max_new_Plant -ne 11 -or [bool]$release.first_scene_review_is_tail_authorization) { throw 'An independent parent release for exactly the remaining eleven scenes is required.' }
$expected = @{
    tail_source_binding_sha256=$bindingSha
    tail_runner_path=$runnerPath
    tail_runner_sha256=$runnerSha
    launcher_sha256=$launcherSha
    tail_run_contract_sha256=$tailContractSha
    parent_release_contract_sha256=$releaseContractSha
    c6_input_lock_sha256=$inputLockSha
    c6_run_contract_sha256=$runContractSha
    prepare_result_sha256=$prepSha
    cfg_opts_snapshot_sha256=$snapshotSha
    first_scene_parent_release_sha256=$firstReleaseSha
    first_scene_review_is_tail_authorization=$false
    plant_authorized=$true
    subsequent_11_flights_authorized=$true
    max_new_Plant=11
    max_total_Plant_including_pilot=12
    tail_scene_count=11
    b72_complete_scene_count=72
    per_scene_output_reserve_bytes=89478486
    max_output_bytes=80000000000
    minimum_free_bytes=30000000000
    seconds_per_remaining_scene_for_deadline_guard=180
    process_exit_buffer_seconds=600
    training_steps=0
    optimizer_steps=0
    parameter_or_seed_search=$false
    new_B_sorties=0
    TEST_accessed=$false
    automatic_retry=$false
    separate_MATLAB_process_per_scene=$false
}
foreach ($name in $expected.Keys) { if ($release.$name -ne $expected[$name]) { throw "C6 tail release field mismatch: $name" } }
if ($releaseContract.release_file_name -ne 'C6_TAIL11_PARENT_RELEASE_v3.json' -or $releaseContract.required_release_state -ne $release.state -or $releaseContract.required_release_schema -ne $release.schema -or -not ($releaseContract.required_fields -contains 'tail_scene_count') -or [int]$releaseContract.required_values.tail_scene_count -ne 11 -or [int]$release.tail_scene_count -ne 11 -or [int]$release.max_total_Plant_including_pilot -ne 12) { throw 'C6 tail release contract scope mismatch.' }
$tailIds = [string[]]@($release.tail_scene_ids)
$expectedTailIds = [string[]]@($tailContract.tail_scene_ids)
if ($tailIds.Count -ne 11 -or @($tailIds | Select-Object -Unique).Count -ne 11 -or (($tailIds -join '|') -ne ($expectedTailIds -join '|'))) { throw 'C6 tail scene IDs/order differ from the frozen 12-scene list with the first scene removed.' }
if ($release.tail_runner_sha256 -ne $runnerSha -or $release.launcher_sha256 -ne $launcherSha -or $release.tail_source_binding_sha256 -ne $bindingSha -or $release.tail_run_contract_sha256 -ne $tailContractSha -or $release.parent_release_contract_sha256 -ne $releaseContractSha -or $release.c6_input_lock_sha256 -ne $inputLockSha -or $release.c6_run_contract_sha256 -ne $runContractSha -or $release.prepare_result_sha256 -ne $prepSha -or $release.cfg_opts_snapshot_sha256 -ne $snapshotSha -or $release.first_scene_parent_release_sha256 -ne $firstReleaseSha) { throw 'C6 tail release does not bind the exact C6 sources and prepared/first-scene inputs.' }
$matlabProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(MATLAB|matlab)\.exe$' })
if ($matlabProcesses.Count) { throw 'A MATLAB process is already running; do not start or interrupt another heavy job.' }
$reserveBytes = [int64]$release.per_scene_output_reserve_bytes * [int64]$tailIds.Count
$minimumFree = [int64]$release.minimum_free_bytes
$freeBytes = [int64](Get-PSDrive -Name C).Free
if (($freeBytes - $reserveBytes) -lt $minimumFree) { throw 'Reserve-adjusted free space is below the frozen 30-GB floor.' }
$runContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $runContractPath -Value $contract.limits.deadline_utc -Label 'C6 run contract'
$tailContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $tailContractPath -Value $tailContract.limits.deadline_utc -Label 'C6 tail run contract'
$releaseContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $releaseContractPath -Value $releaseContract.required_values.deadline_utc -Label 'C6 tail release contract'
$releaseDeadline = Get-C6FixedDeadlineUtc -JsonPath $releasePath -Value $release.deadline_utc -Label 'C6 tail parent release'
if ($runContractDeadline.Ticks -ne $tailContractDeadline.Ticks -or $runContractDeadline.Ticks -ne $releaseContractDeadline.Ticks -or $runContractDeadline.Ticks -ne $releaseDeadline.Ticks) { throw 'C6 tail deadlines differ across run contract, tail contract, release, and release contract.' }
$deadline = $releaseDeadline
if (($deadline - [DateTime]::UtcNow).TotalSeconds -lt (180 * $tailIds.Count + [int]$release.process_exit_buffer_seconds)) { throw 'The fixed eleven-scene tail lacks the preregistered runtime and exit buffer before deadline.' }
$usedBytes = [int64](Get-ChildItem -LiteralPath $taskDir -File -Recurse -Force | Measure-Object -Property Length -Sum).Sum
if (($usedBytes + $reserveBytes) -gt [int64]$release.max_output_bytes) { throw 'C6 folder cannot reserve the preregistered bytes for all eleven remaining scenes.' }
$lock = Get-Content -LiteralPath $inputLockPath -Raw | ConvertFrom-Json
foreach ($sceneId in $tailIds) {
    $attempt = Join-Path $taskDir (Join-Path 'runs_c6_startup_ramp_tail11_v3' (Join-Path $sceneId 'C6_STARTUP_PREDICTION_RAMP/attempt_01'))
    if (Test-Path -LiteralPath $attempt) { throw "Prior C6 tail attempt exists for $sceneId; no retry." }
}
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_tail11_v3'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:BLAS_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'); batch=run_c6_startup_ramp_tail11_v3('PARENT_APPROVED_C6_TAIL11_V1'); fprintf('C6_TAIL11_RETURN=%s SCENES=%d PLANT_CALLS=%d\n',batch.status,batch.completed_scenes,batch.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end" 1> $stdoutPath 2> $stderrPath
$matlabOsExitCode = $LASTEXITCODE
$batchStatus = $null
$completedScenes = 0
$plantCalls = 0
$bodyStatus = 'NOT_WRITTEN'
$finalizationError = ''
if (Test-Path -LiteralPath $batchPath) {
    try {
        $batchStatus = Get-Content -LiteralPath $batchPath -Raw | ConvertFrom-Json
        $completedScenes = [int]$batchStatus.completed_scenes
        $plantCalls = [int]$batchStatus.plant_calls
    } catch { $finalizationError = "Cannot read batch status after natural MATLAB return: $($_.Exception.Message)" }
}
if ($matlabOsExitCode -eq 0 -and -not $finalizationError -and $batchStatus) {
    try {
        $actualIds = [string[]]@($batchStatus.records | ForEach-Object { $_.scene_id })
        if ($batchStatus.status -ne 'COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $completedScenes -ne 11 -or $plantCalls -ne 11 -or (($actualIds -join '|') -ne ($tailIds -join '|'))) { throw 'MATLAB returned OS 0 without the complete, correctly ordered eleven-scene batch.' }
        $body = [ordered]@{
            schema='C6_TAIL11_BODY_COMPLETE_V1'; status='COMPLETE_RAW_PENDING_PARENT_AUDIT'
            batch_id=$batchStatus.batch_id; batch_scope='ONE_SEQUENTIAL_MATLAB_PROCESS'; batch_scope_scene_ids=$tailIds
            matlab_process_count=1; shared_matlab_os_exit_code=$matlabOsExitCode; completed_scenes=$completedScenes; plant_calls=$plantCalls
            per_scene_exit_record_count=$batchStatus.records.Count; per_scene_exit_records=$batchStatus.records
            source_binding_sha256=$bindingSha; tail_release_sha256=(& $sha $releasePath)
            created_utc=[DateTime]::UtcNow.ToString('o')
        }
        [IO.File]::WriteAllText($bodyPath, ($body | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
        $bodyStatus = $body.status
    } catch { $finalizationError = $_.Exception.Message }
}
$status = if ($matlabOsExitCode -eq 0 -and $bodyStatus -eq 'COMPLETE_RAW_PENDING_PARENT_AUDIT' -and -not $finalizationError) { 'COMPLETE_RAW_PENDING_PARENT_AUDIT' } else { 'FAILED_NO_RETRY' }
$exitRecord = [ordered]@{
    schema='C6_TAIL11_MATLAB_OS_EXIT_V1'; status=$status; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; completed_utc=[DateTime]::UtcNow.ToString('o')
    command_file=$PSCommandPath; command_sha256=$launcherSha; source_binding_sha256=$bindingSha
    runner_sha256=$runnerSha; parent_release_sha256=(& $sha $releasePath)
    batch_status=$batchStatus.status; completed_scenes=$completedScenes; plant_calls=$plantCalls
    body_status=$bodyStatus; shared_matlab_process_count=1; tail_scene_ids=$tailIds
    plant_authorized=[bool]$release.plant_authorized; finalization_error=$finalizationError
    stdout_path=$stdoutPath; stdout_sha256=(& $sha $stdoutPath); stderr_path=$stderrPath; stderr_sha256=(& $sha $stderrPath)
}
[IO.File]::WriteAllText($osExitPath, ($exitRecord | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
$receipt = [ordered]@{
    schema='C6_TAIL11_EXECUTION_RECEIPT_V1'; status=$status; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; shell_natural_exit_code=$matlabOsExitCode
    completed_scenes=$completedScenes; plant_calls=$plantCalls; batch_status_path=$batchPath
    batch_status_sha256=$(if(Test-Path -LiteralPath $batchPath){ & $sha $batchPath }else{$null})
    body_path=$bodyPath; body_sha256=$(if(Test-Path -LiteralPath $bodyPath){ & $sha $bodyPath }else{$null})
    source_binding_sha256=$bindingSha; tail_release_sha256=(& $sha $releasePath)
    stdout_path=$stdoutPath; stdout_sha256=(& $sha $stdoutPath); stderr_path=$stderrPath; stderr_sha256=(& $sha $stderrPath)
    finalization_error=$finalizationError; TEST_accessed=$false; training_steps=0; optimizer_steps=0; GPU=$false
}
[IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; TAIL={1}; SCENES={2}; PLANT_CALLS={3}" -f $matlabOsExitCode, $status, $completedScenes, $plantCalls)
exit $matlabOsExitCode
