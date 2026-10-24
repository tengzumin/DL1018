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
$lockPath = Join-Path $taskDir 'C6_STARTUP_RAMP_INPUT_LOCK_v1.json'
$contractPath = Join-Path $taskDir 'C6_STARTUP_RAMP_RUN_CONTRACT_v1.json'
$bindingPath = Join-Path $taskDir 'C6_SOURCE_BINDING_v1.json'
$releaseContractPath = Join-Path $taskDir 'C6_FIRST_PARENT_RELEASE_CONTRACT_v1.json'
$releasePath = Join-Path $taskDir 'C6_FIRST_PARENT_RELEASE_v1.json'
$preparePath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat'
$noPlantExitPath = Join-Path $reportDir 'C6_NOPLANT_MATLAB_OS_EXIT_v1.json'
$noPlantReceiptPath = Join-Path $reportDir 'C6_NOPLANT_EXECUTION_RECEIPT_v1.json'
$noPlantReviewPath = Join-Path $reportDir 'C6_NOPLANT_PARENT_REVIEW_v1.json'
$runnerPath = Join-Path $taskDir 'run_c6_startup_ramp_first_v1.m'
$launcherPath = $PSCommandPath
$osExitPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_OS_EXIT_v1.json'
$receiptPath = Join-Path $reportDir 'C6_FIRST_SCENE_EXECUTION_RECEIPT_v1.json'
$historyPath = Join-Path $reportDir 'C6_FIRST_SCENE_OUTER_INVOCATION_HISTORY_v1.json'
$stdoutPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_STDOUT_v1.log'
$stderrPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_STDERR_v1.log'
$firstId = 'DL1018_VAL_T1_C00_W07'
$attemptDir = Join-Path $taskDir (Join-Path 'runs_c6_startup_ramp_v1' (Join-Path $firstId 'C6_STARTUP_PREDICTION_RAMP/attempt_01'))
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'An independent parent first-scene release is required; this launcher creates no release.' }
foreach ($path in @($osExitPath,$receiptPath,$historyPath,$stdoutPath,$stderrPath,$attemptDir)) {
    if (Test-Path -LiteralPath $path) { throw "Prior first-scene output or attempt exists; preserve it and do not retry: $path" }
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
$binding = Get-Content -LiteralPath $bindingPath -Raw | ConvertFrom-Json
$releaseContract = Get-Content -LiteralPath $releaseContractPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$noPlantExit = Get-Content -LiteralPath $noPlantExitPath -Raw | ConvertFrom-Json
$noPlantReceipt = Get-Content -LiteralPath $noPlantReceiptPath -Raw | ConvertFrom-Json
$noPlantReview = Get-Content -LiteralPath $noPlantReviewPath -Raw | ConvertFrom-Json
$runContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $contractPath -Value $contract.limits.deadline_utc -Label 'C6 run contract'
$releaseDeadline = Get-C6FixedDeadlineUtc -JsonPath $releasePath -Value $release.deadline_utc -Label 'C6 first-scene parent release'
$releaseContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $releaseContractPath -Value $releaseContract.required_values.deadline_utc -Label 'C6 first-scene release contract'
if ($runContractDeadline.Ticks -ne $releaseDeadline.Ticks -or $runContractDeadline.Ticks -ne $releaseContractDeadline.Ticks) { throw 'C6 first-scene deadlines differ across contract, release, and release contract.' }
if (($runContractDeadline - [DateTime]::UtcNow).TotalSeconds -lt (180 + 600)) { throw 'The fixed first scene lacks the preregistered runtime and exit buffer before deadline.' }
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$lockSha = & $sha $lockPath
$contractSha = & $sha $contractPath
$bindingSha = & $sha $bindingPath
$releaseContractSha = & $sha $releaseContractPath
$launcherSha = & $sha $launcherPath
$runnerSha = & $sha $runnerPath
$prepareSha = & $sha $preparePath
$snapshotSha = & $sha $snapshotPath
$noPlantExitSha = & $sha $noPlantExitPath
$noPlantReceiptSha = & $sha $noPlantReceiptPath
$noPlantReviewSha = & $sha $noPlantReviewPath
if ($lock.schema -ne 'C6_STARTUP_RAMP_INPUT_LOCK_V1' -or $lock.state -ne 'LOCKED_C6_STARTUP_RAMP_NO_PLANT_PARENT_REVIEW_REQUIRED_V1' -or $contract.schema -ne 'C6_STARTUP_RAMP_RUN_CONTRACT_V1' -or $binding.schema -ne 'C6_STARTUP_RAMP_SOURCE_BINDING_V1') { throw 'C6 lock, contract or source-binding schema/state mismatch.' }
if ($releaseContract.schema -ne 'C6_FIRST_PARENT_RELEASE_CONTRACT_V1' -or $release.schema -ne 'C6_FIRST_PARENT_RELEASE_V1' -or $release.state -ne 'APPROVED_C6_FIRST_SCENE_V1') { throw 'C6 first-scene parent release contract/schema/state mismatch.' }
if (-not [bool]$release.plant_authorized -or [int]$release.max_new_Plant -ne 1 -or $release.scene_id -ne $firstId -or (($release.coordinate_mask -join ',') -ne '1,1,0')) { throw 'Release must authorize exactly the preregistered first scene and mask.' }
$expected = @{
    taskbook_sha256=$lock.taskbook_sha256
    c6_input_lock_sha256=$lockSha
    c6_run_contract_sha256=$contractSha
    c6_source_binding_sha256=$bindingSha
    c6_parent_release_contract_sha256=$releaseContractSha
    c6_runner_path=$runnerPath
    c6_runner_sha256=$runnerSha
    first_launcher_sha256=$launcherSha
    c6_prepare_result_sha256=$prepareSha
    c6_snapshot_sha256=$snapshotSha
    c6_noplant_os_exit_path=$noPlantExitPath
    c6_noplant_os_exit_sha256=$noPlantExitSha
    c6_noplant_execution_receipt_path=$noPlantReceiptPath
    c6_noplant_execution_receipt_sha256=$noPlantReceiptSha
    c6_noplant_parent_review_path=$noPlantReviewPath
    c6_noplant_parent_review_sha256=$noPlantReviewSha
    scene_id=$firstId
    b72_parent_review_status='PASS_C5_B72_ALL72_PARENT_AUDIT'
    b72_raw_manifest_schema='C5_B72_SCORING_MANIFEST_V1'
    b72_raw_manifest_state='PASS_C5_B72_ALL72_PARENT_AUDIT'
    b72_complete_scene_count=72
    c6_noplant_parent_review_status='PASS_C6_NOPLANT_PARENT_REVIEW'
    plant_calls_before_first_scene=0
    per_scene_output_reserve_bytes=89478486
    max_output_bytes=80000000000
    minimum_free_bytes=30000000000
    plant_authorized=$true
    max_new_Plant=1
    training_steps=0
    optimizer_steps=0
    parameter_or_seed_search=$false
    new_B_sorties=0
    TEST_accessed=$false
    automatic_retry=$false
}
foreach ($name in $expected.Keys) { if ($release.$name -ne $expected[$name]) { throw "First-scene parent release field mismatch: $name" } }
if ($releaseContract.release_file_name -ne 'C6_FIRST_PARENT_RELEASE_v1.json' -or $releaseContract.required_release_state -ne $release.state -or $releaseContract.required_release_schema -ne $release.schema) { throw 'First-scene release contract does not describe the C6 release.' }
if ($noPlantExit.schema -ne 'C6_NOPLANT_MATLAB_OS_EXIT_V1' -or $noPlantExit.status -ne 'PASS_C6_NOPLANT_NATURAL_OS0' -or [int]$noPlantExit.matlab_os_exit_code -ne 0 -or -not [bool]$noPlantExit.natural_process_return -or [int]$noPlantExit.plant_calls -ne 0) { throw 'A natural zero-exit C6 no-Plant preparation is required.' }
if ($noPlantReceipt.schema -ne 'C6_NOPLANT_EXECUTION_RECEIPT_V1' -or $noPlantReceipt.status -ne 'PASS_C6_NOPLANT_NATURAL_OS0' -or [int]$noPlantReceipt.plant_calls -ne 0 -or [bool]$noPlantReceipt.plant_authorized) { throw 'The C6 no-Plant receipt is incomplete or claims Plant activity.' }
if ($noPlantReview.status -ne 'PASS_C6_NOPLANT_PARENT_REVIEW' -or [int]$noPlantReview.plant_calls -ne 0 -or [bool]$noPlantReview.TEST_accessed) { throw 'Independent parent review of no-Plant preparation is required.' }
if ((& $sha $release.c6_noplant_os_exit_path) -ne $release.c6_noplant_os_exit_sha256) { throw 'No-Plant OS receipt hash mismatch.' }
foreach ($ref in $binding.file_refs) { if ((& $sha $ref.path) -ne $ref.sha256) { throw "Locked C6 source changed: $($ref.role)" } }
$prepared = Get-Content -LiteralPath $preparePath -Raw | ConvertFrom-Json
if ($prepared.status -ne 'PREPARED_C6_STARTUP_RAMP_NO_PLANT_WAIT_PARENT_RELEASE_V1' -or [int]$prepared.plant_calls -ne 0 -or [bool]$prepared.TEST_accessed -or $prepared.first_scene_id -ne $firstId) { throw 'C6 no-Plant prepare result is not the frozen 12-scene result.' }
if ([int64]$prepared.plant_calls -ne [int64]$release.plant_calls_before_first_scene -or [bool]$release.automatic_retry) { throw 'C6 release does not preserve the no-retry one-scene scope.' }
$matlabProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(MATLAB|matlab)\.exe$' })
if ($matlabProcesses.Count) { throw 'A MATLAB process is already running; C6 will not start a second process.' }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_first_v1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:BLAS_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'); run_c6_startup_ramp_first_v1('PARENT_APPROVED_C6_FIRST_V1'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end" 1> $stdoutPath 2> $stderrPath
$matlabOsExitCode = $LASTEXITCODE
$runStatusPath = Join-Path $attemptDir 'run_status.json'
$rawPath = Join-Path $attemptDir 'raw_run.mat'
$runStartPath = Join-Path $attemptDir 'run_start.mat'
$markerPath = Join-Path $attemptDir 'first_plant_step.marker'
$runStatus = $null
if (Test-Path -LiteralPath $runStatusPath) { $runStatus = Get-Content -LiteralPath $runStatusPath -Raw | ConvertFrom-Json }
$rawSha = if (Test-Path -LiteralPath $rawPath) { & $sha $rawPath } else { $null }
$runStatusSha = if (Test-Path -LiteralPath $runStatusPath) { & $sha $runStatusPath } else { $null }
$runStartSha = if (Test-Path -LiteralPath $runStartPath) { & $sha $runStartPath } else { $null }
$markerSha = if (Test-Path -LiteralPath $markerPath) { & $sha $markerPath } else { $null }
$complete = ($matlabOsExitCode -eq 0 -and $runStatus -and $runStatus.status -eq 'RUN_COMPLETE_RAW_PENDING_AUDIT' -and [int]$runStatus.plant_calls -eq 1 -and $runStatus.scene_id -eq $firstId)
$status = if ($complete) { 'RUN_COMPLETE_RAW_PENDING_AUDIT' } else { 'FAILED_NO_RETRY' }
$osExit = [ordered]@{
    schema='C6_FIRST_SCENE_OS_EXIT_V1'; status=$status; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; completed_utc=[DateTime]::UtcNow.ToString('o')
    command_file=$launcherPath; command_sha256=$launcherSha; release_sha256=(& $sha $releasePath)
    input_lock_sha256=$lockSha; runner_sha256=$runnerSha; one_scene_only=$true; plant_authorized=$true
    plant_calls=$(if($runStatus){[int]$runStatus.plant_calls}else{0})
    run_status_path=$runStatusPath; run_status_sha256=$runStatusSha; raw_path=$rawPath; raw_sha256=$rawSha
    stdout_path=$stdoutPath; stdout_sha256=(& $sha $stdoutPath); stderr_path=$stderrPath; stderr_sha256=(& $sha $stderrPath)
}
[IO.File]::WriteAllText($osExitPath, ($osExit | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
$receipt = [ordered]@{
    schema='C6_FIRST_SCENE_EXECUTION_RECEIPT_V1'; status=$status; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; shell_natural_exit_code=$matlabOsExitCode; run_status=$status
    created_utc=[DateTime]::UtcNow.ToString('o'); release_sha256=(& $sha $releasePath)
    plant_calls=$(if($runStatus){[int]$runStatus.plant_calls}else{0})
    artifacts=[ordered]@{
        raw=[ordered]@{path=$rawPath;sha256=$rawSha}
        run_status=[ordered]@{path=$runStatusPath;sha256=$runStatusSha}
        run_start=[ordered]@{path=$runStartPath;sha256=$runStartSha}
        first_plant_step_marker=[ordered]@{path=$markerPath;sha256=$markerSha}
    }
    stdout=[ordered]@{path=$stdoutPath;sha256=(& $sha $stdoutPath)}
    stderr=[ordered]@{path=$stderrPath;sha256=(& $sha $stderrPath)}
}
[IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
$history = [ordered]@{
    schema='C6_FIRST_SCENE_OUTER_INVOCATION_HISTORY_V1'; status=$status; created_utc=[DateTime]::UtcNow.ToString('o')
    release_sha256=(& $sha $releasePath); launcher_sha256=$launcherSha; runner_sha256=$runnerSha
    preflight_path_error=[ordered]@{MATLAB_launches=0;Plant_calls=0;outputs_created=0;status='PASS'}
    actual_execution=[ordered]@{
        MATLAB_launches=1; MATLAB_OS_exit_code=$matlabOsExitCode; natural_shell_process_exit_code=$matlabOsExitCode
        MATLAB_stdout_path=$stdoutPath; MATLAB_stderr_path=$stderrPath; run_status_path=$runStatusPath
        run_status_sha256=$runStatusSha; raw_path=$rawPath; raw_sha256=$rawSha
        plant_calls=$(if($runStatus){[int]$runStatus.plant_calls}else{0})
    }
}
[IO.File]::WriteAllText($historyPath, ($history | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; FIRST_STATUS={1}; PLANT_CALLS={2}" -f $matlabOsExitCode, $status, $(if($runStatus){$runStatus.plant_calls}else{0}))
exit $matlabOsExitCode
