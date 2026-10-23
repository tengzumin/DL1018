$ErrorActionPreference = 'Stop'
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c4_coordinate_execution'
$exitPath = Join-Path $reportDir 'C4_PREPARE_MATLAB_OS_EXIT_v3.json'
$resultPath = Join-Path $taskDir 'C4_PREPARE_RESULT_v3.json'
$snapshotPath = Join-Path $taskDir 'C4_PREPARED_CFG_OPTS_v3.mat'
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior prepare exit record; do not rerun.' }
if ((Test-Path -LiteralPath $resultPath) -or (Test-Path -LiteralPath $snapshotPath)) {
    throw 'A v3 prepare result already exists; preserve it and do not rerun.'
}
$parseTokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'); prepare_c4_coordinate_v3; quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$prepareStatus = $null
if (Test-Path -LiteralPath $resultPath) { $prepareStatus = (Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json).status }
$exitRecord = [ordered]@{
    schema = 'C4_PREPARE_NOPLANT_OS_EXIT_V3'
    matlab_os_exit_code = $matlabOsExitCode
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    input_lock_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskDir 'C4_INPUT_LOCK_v3.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    prepare_entry_sha256 = (Get-FileHash -LiteralPath (Join-Path $taskDir 'prepare_c4_coordinate_v3.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    prepare_result_status = $prepareStatus
    plant_authorized = $false
    matlab_called_once = $true
    crosslanguage_synthetic_rerun = $false
}
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; PREPARE={1}" -f $matlabOsExitCode, $prepareStatus)
exit $matlabOsExitCode
