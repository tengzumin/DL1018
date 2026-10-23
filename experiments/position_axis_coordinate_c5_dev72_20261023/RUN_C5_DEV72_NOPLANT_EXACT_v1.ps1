$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'This exact no-Plant command requires PowerShell 7.' }
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_dev72_20261023'
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c5_dev72_execution'
$exitPath = Join-Path $reportDir 'C5_DEV72_NOPLANT_OS_EXIT_v1.json'
$stdoutPath = Join-Path $reportDir 'C5_DEV72_NOPLANT_STDOUT_v1.txt'
$stderrPath = Join-Path $reportDir 'C5_DEV72_NOPLANT_STDERR_v1.txt'
$resultPath = Join-Path $taskDir 'C5_DEV72_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C5_DEV72_PREPARED_CFG_OPTS_v1.mat'
$failurePath = Join-Path $taskDir 'C5_DEV72_PREPARE_FAILURE_v1.json'
if ((Test-Path -LiteralPath $exitPath) -or (Test-Path -LiteralPath $stdoutPath) -or
    (Test-Path -LiteralPath $stderrPath) -or (Test-Path -LiteralPath $resultPath) -or
    (Test-Path -LiteralPath $snapshotPath) -or (Test-Path -LiteralPath $failurePath)) {
    throw 'Preserve prior no-Plant evidence; do not rerun.'
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_dev72_noplant_v1'
New-Item -ItemType Directory -Path $env:MATLAB_PREFDIR -Force | Out-Null
$startedUtc = [DateTime]::UtcNow.ToString('o')
$matlabBatch = "try; cd('$taskDir'); result=prepare_c5_dev72_v1(); fprintf('C5_DEV72_PREPARED=%s; NEW=%d; REUSE=%d; PLANT_CALLS=%d',result.status,numel(result.scene_ids_new_60),numel(result.scene_ids_reuse_12),result.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
& $matlabExe -singleCompThread -wait -batch $matlabBatch 1> $stdoutPath 2> $stderrPath
$matlabOsExitCode = $LASTEXITCODE
$prepareStatus = $null
$snapshotSha = $null
if (Test-Path -LiteralPath $resultPath) {
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json -Depth 40
    $prepareStatus = $result.status
}
if (Test-Path -LiteralPath $snapshotPath) {
    $snapshotSha = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$record = [ordered]@{
    schema = 'C5_AXIS_COORDINATE_DEV72_NOPLANT_OS_EXIT_V1'
    matlab_os_exit_code = $matlabOsExitCode
    started_utc = $startedUtc
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    input_lock_sha256 = if (Test-Path -LiteralPath (Join-Path $taskDir 'C5_DEV72_INPUT_LOCK_v1.json')) {
        (Get-FileHash -LiteralPath (Join-Path $taskDir 'C5_DEV72_INPUT_LOCK_v1.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { $null }
    prepare_entry_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskDir 'prepare_c5_dev72_v1.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    runner_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskDir 'run_c5_dev72_v1.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    source_binding_sha256 = if (Test-Path -LiteralPath (Join-Path $taskDir 'C5_DEV72_SOURCE_BINDING_v1.json')) {
        (Get-FileHash -LiteralPath (Join-Path $taskDir 'C5_DEV72_SOURCE_BINDING_v1.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { $null }
    prepare_result_status = $prepareStatus
    prepare_result_sha256 = if (Test-Path -LiteralPath $resultPath) { (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    snapshot_sha256 = $snapshotSha
    stdout_path = $stdoutPath
    stderr_path = $stderrPath
    matlab_prefdir = $env:MATLAB_PREFDIR
    plant_authorized = $false
    matlab_called_once = $true
}
[IO.File]::WriteAllText($exitPath, ($record | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; PREPARE={1}" -f $matlabOsExitCode, $prepareStatus)
exit $matlabOsExitCode
