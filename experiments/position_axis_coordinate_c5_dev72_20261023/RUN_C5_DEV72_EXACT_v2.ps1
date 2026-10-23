$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'This exact C5 DEV72 command requires PowerShell 7.' }
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_dev72_20261023'
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c5_dev72_execution'
$releasePath = Join-Path $taskDir 'C5_DEV72_RELEASE_v2.json'
$batchPath = Join-Path $taskDir 'C5_DEV72_BATCH_STATUS_v2.json'
$bodyPath = Join-Path $taskDir 'C5_DEV72_BODY_COMPLETE_v2.json'
$osPath = Join-Path $reportDir 'C5_DEV72_MATLAB_OS_EXIT_v2.json'
$stdoutPath = Join-Path $reportDir 'C5_DEV72_STDOUT_v2.txt'
$stderrPath = Join-Path $reportDir 'C5_DEV72_STDERR_v2.txt'
$commandPath = Join-Path $reportDir 'C5_DEV72_COMMAND_v2.txt'
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'Separate parent release is required; this launcher does not grant it.' }
$activeMatlab = @(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'matlab.exe'" -ErrorAction Stop)
if ($activeMatlab.Count -ne 0) { throw 'An existing MATLAB process is active; do not start or interrupt it.' }
$driveRoot = [IO.Path]::GetPathRoot($taskDir)
$availableBytes = [IO.DriveInfo]::new($driveRoot).AvailableFreeSpace
$reserveBytes = 60L * 80000000L
$minimumFreeBytes = 30000000000L
if (($availableBytes - $reserveBytes) -lt $minimumFreeBytes) {
    throw 'Available space after the 60-scene reserve would be below 30 GB.'
}
$deadlineUtc = [DateTime]::Parse('2026-10-24T17:01:00Z').ToUniversalTime()
$requiredSeconds = (60 * 180) + 600
if ([DateTime]::UtcNow.AddSeconds($requiredSeconds) -ge $deadlineUtc) {
    throw 'The remaining-scene time guard would cross the locked deadline.'
}
if ((Test-Path -LiteralPath $osPath) -or (Test-Path -LiteralPath $stdoutPath) -or
    (Test-Path -LiteralPath $stderrPath) -or (Test-Path -LiteralPath $commandPath) -or
    (Test-Path -LiteralPath $batchPath) -or (Test-Path -LiteralPath $bodyPath)) {
    throw 'Preserve prior execution evidence; do not overwrite or retry.'
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_dev72_run_v2'
New-Item -ItemType Directory -Path $env:MATLAB_PREFDIR -Force | Out-Null
$invocation = "& '$PSCommandPath'"
[IO.File]::WriteAllText($commandPath, $invocation + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$startedUtc = [DateTime]::UtcNow.ToString('o')
$matlabBatch = "try; cd('$taskDir'); run_c5_dev72_v2('PARENT_APPROVED_C5_M110_DEV72_V2'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
& $matlabExe -singleCompThread -wait -batch $matlabBatch 1> $stdoutPath 2> $stderrPath
$matlabOsExitCode = $LASTEXITCODE
$bodyStatus = $null
$batchStatus = $null
$bodySha = $null
if (Test-Path -LiteralPath $batchPath) {
    $batch = Get-Content -LiteralPath $batchPath -Raw | ConvertFrom-Json -Depth 50
    $batchStatus = $batch.status
}
if (Test-Path -LiteralPath $bodyPath) {
    $body = Get-Content -LiteralPath $bodyPath -Raw | ConvertFrom-Json -Depth 50
    $body.shared_matlab_os_exit_code = $matlabOsExitCode
    $bodyStatus = $body.status
    $body | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $bodyPath -Encoding utf8NoBOM
    $bodySha = (Get-FileHash -LiteralPath $bodyPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record = [ordered]@{
    schema = 'C5_AXIS_COORDINATE_DEV72_MATLAB_OS_EXIT_V2'
    matlab_os_exit_code = $matlabOsExitCode
    started_utc = $startedUtc
    completed_utc = [DateTime]::UtcNow.ToString('o')
    outer_invocation = $invocation
    command_path = $commandPath
    command_sha256 = (Get-FileHash -LiteralPath $commandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    launcher_path = $PSCommandPath
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    release_sha256 = (Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    batch_status = $batchStatus
    body_status = $bodyStatus
    body_sha256_after_os_return = $bodySha
    stdout_path = $stdoutPath
    stdout_sha256 = if (Test-Path -LiteralPath $stdoutPath) { (Get-FileHash -LiteralPath $stdoutPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    stderr_path = $stderrPath
    stderr_sha256 = if (Test-Path -LiteralPath $stderrPath) { (Get-FileHash -LiteralPath $stderrPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    matlab_prefdir = $env:MATLAB_PREFDIR
    plant_authorized_by_release = $true
    matlab_process_count = 1
    plant_calls = if (Test-Path -LiteralPath $batchPath) { [int]$batch.plant_calls } else { $null }
    preflight_matlab_process_count = $activeMatlab.Count
    preflight_available_bytes = $availableBytes
    preflight_reserve_bytes = $reserveBytes
    preflight_minimum_free_bytes = $minimumFreeBytes
    preflight_deadline_utc = $deadlineUtc.ToString('o')
}
[IO.File]::WriteAllText($osPath, ($record | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; BATCH={1}; BODY={2}" -f $matlabOsExitCode, $batchStatus, $bodyStatus)
exit $matlabOsExitCode
