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
$parentContractPath = Join-Path $taskDir 'C6_NOPLANT_PARENT_RELEASE_CONTRACT_v1.json'
$releasePath = Join-Path $taskDir 'C6_NOPLANT_PARENT_RELEASE_v1.json'
$preparePath = Join-Path $taskDir 'prepare_c6_startup_ramp_v1.m'
$syntheticCheckPath = Join-Path $taskDir 'check_c6_startup_ramp_synthetic_v1.m'
$fixtureBuilderPath = Join-Path $taskDir 'build_c6_startup_ramp_fixture_v1.py'
$fixturePath = Join-Path $taskDir 'C6_CROSSLANG_FIXTURE_v1.json'
$launcherPath = $PSCommandPath
$exitPath = Join-Path $reportDir 'C6_NOPLANT_MATLAB_OS_EXIT_v1.json'
$receiptPath = Join-Path $reportDir 'C6_NOPLANT_EXECUTION_RECEIPT_v1.json'
$stdoutPath = Join-Path $reportDir 'C6_NOPLANT_MATLAB_STDOUT_v1.log'
$stderrPath = Join-Path $reportDir 'C6_NOPLANT_MATLAB_STDERR_v1.log'
$prepareResultPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat'
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'A separate parent no-Plant release is required; no release file is created by this launcher.' }
foreach ($path in @($exitPath,$receiptPath,$stdoutPath,$stderrPath,$prepareResultPath,$snapshotPath,(Join-Path $taskDir 'C6_CROSSLANG_SYNTHETIC_RESULT_v1.json'))) {
    if (Test-Path -LiteralPath $path) { throw "Prior no-Plant output exists; preserve it and do not retry: $path" }
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
$deadlineUtc = Get-C6FixedDeadlineUtc -JsonPath $contractPath -Value $contract.limits.deadline_utc -Label 'C6 run contract'
if (($deadlineUtc - [DateTime]::UtcNow).TotalSeconds -lt (180 * 12 + 600)) { throw 'C6 hard deadline cannot preserve the frozen twelve-scene runtime and exit buffer.' }
$binding = Get-Content -LiteralPath $bindingPath -Raw | ConvertFrom-Json
$parentContract = Get-Content -LiteralPath $parentContractPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$lockSha = & $sha $lockPath
$contractSha = & $sha $contractPath
$bindingSha = & $sha $bindingPath
$parentContractSha = & $sha $parentContractPath
$launcherSha = & $sha $launcherPath
$prepareSha = & $sha $preparePath
$syntheticCheckSha = & $sha $syntheticCheckPath
$fixtureBuilderSha = & $sha $fixtureBuilderPath
$fixtureSha = & $sha $fixturePath
if ($lock.schema -ne 'C6_STARTUP_RAMP_INPUT_LOCK_V1' -or $lock.state -ne 'LOCKED_C6_STARTUP_RAMP_NO_PLANT_PARENT_REVIEW_REQUIRED_V1' -or $contract.schema -ne 'C6_STARTUP_RAMP_RUN_CONTRACT_V1' -or $binding.schema -ne 'C6_STARTUP_RAMP_SOURCE_BINDING_V1') { throw 'C6 input lock, run contract or source binding schema/state mismatch.' }
if ($parentContract.schema -ne 'C6_NOPLANT_PARENT_RELEASE_CONTRACT_V1' -or $release.schema -ne 'C6_NOPLANT_PARENT_RELEASE_V1' -or $release.state -ne 'APPROVED_C6_NOPLANT_V1') { throw 'C6 no-Plant contract or parent release schema/state mismatch.' }
if ([bool]$release.plant_authorized -or [int]$release.max_new_Plant -ne 0 -or [int]$release.training_steps -ne 0 -or [int]$release.optimizer_steps -ne 0 -or [bool]$release.TEST_accessed -or [bool]$release.GPU) { throw 'No-Plant release contains a prohibited authorization or activity.' }
$expected = @{
    taskbook_sha256 = $lock.taskbook_sha256
    c6_input_lock_sha256 = $lockSha
    c6_run_contract_sha256 = $contractSha
    c6_source_binding_sha256 = $bindingSha
    c6_noplant_parent_release_contract_sha256 = $parentContractSha
    c6_prepare_entry_sha256 = $prepareSha
    c6_synthetic_check_sha256 = $syntheticCheckSha
    c6_fixture_builder_sha256 = $fixtureBuilderSha
    c6_fixture_sha256 = $fixtureSha
    c6_noplant_launcher_sha256 = $launcherSha
    plant_authorized = $false
    max_new_Plant = 0
    training_steps = 0
    optimizer_steps = 0
    parameter_or_seed_search = $false
    new_B_sorties = 0
    automatic_retry = $false
    TEST_accessed = $false
    GPU = $false
}
foreach ($name in $expected.Keys) { if ($release.$name -ne $expected[$name]) { throw "No-Plant parent release field mismatch: $name" } }
if ($parentContract.required_release_state -ne $release.state -or $parentContract.release_file_name -ne 'C6_NOPLANT_PARENT_RELEASE_v1.json') { throw 'No-Plant parent release contract scope mismatch.' }
foreach ($ref in $binding.file_refs) { if ((& $sha $ref.path) -ne $ref.sha256) { throw "Locked C6 source changed: $($ref.role)" } }
if ((Get-FileHash -LiteralPath $lock.source_files.single_scene_runner.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.source_files.single_scene_runner.sha256) { throw 'C6 first-scene runner hash changed.' }
$matlabProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(MATLAB|matlab)\.exe$' })
if ($matlabProcesses.Count) { throw 'A MATLAB process is already running; no C6 MATLAB process will be started.' }
$reserveBytes = [int64]$contract.limits.per_scene_output_reserve_bytes * [int64]$contract.limits.max_new_Plant
$freeBytes = [int64](Get-PSDrive -Name C).Free
if (($freeBytes - $reserveBytes) -lt [int64]$contract.limits.minimum_free_bytes) { throw 'Reserve-adjusted free space is below the frozen 30-GB floor.' }
$usedBytes = [int64](Get-ChildItem -LiteralPath $taskDir -File -Recurse -Force | Measure-Object -Property Length -Sum).Sum
if (($usedBytes + $reserveBytes) -gt [int64]$contract.limits.max_output_bytes) { throw 'C6 folder cannot preserve the preregistered 12-scene output reserve.' }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_noplant_v1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:BLAS_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'); check_c6_startup_ramp_synthetic_v1; prepare_c6_startup_ramp_v1; quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end" 1> $stdoutPath 2> $stderrPath
$matlabOsExitCode = $LASTEXITCODE
$prepareStatus = $null
$prepareShaOut = $null
$snapshotShaOut = $null
if (Test-Path -LiteralPath $prepareResultPath) {
    $prepared = Get-Content -LiteralPath $prepareResultPath -Raw | ConvertFrom-Json
    $prepareStatus = $prepared.status
    $prepareShaOut = & $sha $prepareResultPath
}
if (Test-Path -LiteralPath $snapshotPath) { $snapshotShaOut = & $sha $snapshotPath }
$naturalPass = ($matlabOsExitCode -eq 0 -and $prepareStatus -eq 'PREPARED_C6_STARTUP_RAMP_NO_PLANT_WAIT_PARENT_RELEASE_V1' -and $prepareShaOut -and $snapshotShaOut)
$receiptStatus = if ($naturalPass) { 'PASS_C6_NOPLANT_NATURAL_OS0' } else { 'FAILED_C6_NOPLANT_NO_RETRY' }
$exitRecord = [ordered]@{
    schema='C6_NOPLANT_MATLAB_OS_EXIT_V1'; status=$receiptStatus; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; completed_utc=[DateTime]::UtcNow.ToString('o')
    launcher_path=$launcherPath; launcher_sha256=$launcherSha; parent_release_sha256=(& $sha $releasePath)
    input_lock_sha256=$lockSha; run_contract_sha256=$contractSha; prepare_entry_sha256=$prepareSha
    prepare_result_path=$prepareResultPath; prepare_result_sha256=$prepareShaOut; prepare_result_status=$prepareStatus
    prepared_snapshot_path=$snapshotPath; prepared_snapshot_sha256=$snapshotShaOut
    stdout_path=$stdoutPath; stdout_sha256=(& $sha $stdoutPath); stderr_path=$stderrPath; stderr_sha256=(& $sha $stderrPath)
    plant_authorized=$false; plant_calls=0; training_steps=0; optimizer_steps=0; TEST_accessed=$false; GPU=$false
}
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
$receipt = [ordered]@{
    schema='C6_NOPLANT_EXECUTION_RECEIPT_V1'; status=$receiptStatus; natural_process_return=$true
    matlab_os_exit_code=$matlabOsExitCode; shell_natural_exit_code=$matlabOsExitCode
    created_utc=[DateTime]::UtcNow.ToString('o'); launcher_path=$launcherPath; launcher_sha256=$launcherSha
    parent_release_sha256=(& $sha $releasePath); input_lock_sha256=$lockSha; run_contract_sha256=$contractSha
    prepare_result_status=$prepareStatus; prepare_result_sha256=$prepareShaOut; prepared_snapshot_sha256=$snapshotShaOut
    stdout_path=$stdoutPath; stdout_sha256=(& $sha $stdoutPath); stderr_path=$stderrPath; stderr_sha256=(& $sha $stderrPath)
    plant_calls=0; plant_authorized=$false; training_steps=0; optimizer_steps=0; parameter_or_seed_search=$false
    TEST_accessed=$false; GPU=$false; MATLAB_invocations=1
}
[IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; PREPARE={1}; RECEIPT={2}" -f $matlabOsExitCode, $prepareStatus, $receiptStatus)
exit $matlabOsExitCode
