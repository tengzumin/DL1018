$ErrorActionPreference = 'Stop'
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c4_coordinate_execution'
$exitPath = Join-Path $reportDir 'C4_CROSSLANG_MATLAB_OS_EXIT_v1.json'
$syntheticResultPath = Join-Path $taskDir 'C4_CROSSLANG_SYNTHETIC_RESULT_v1.json'
$prepareResultPath = Join-Path $taskDir 'C4_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C4_PREPARED_CFG_OPTS_v1.mat'
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior MATLAB exit record; do not rerun.' }
if ((Test-Path -LiteralPath $syntheticResultPath) -or (Test-Path -LiteralPath $prepareResultPath) -or (Test-Path -LiteralPath $snapshotPath)) {
    throw 'A noPlant result already exists; preserve it and do not rerun.'
}
$parseTokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'); check_c4_coordinate_synthetic_v1; prepare_c4_coordinate_v1; quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$syntheticStatus = $null
$prepareStatus = $null
if (Test-Path -LiteralPath $syntheticResultPath) { $syntheticStatus = (Get-Content -Raw -LiteralPath $syntheticResultPath | ConvertFrom-Json).status }
if (Test-Path -LiteralPath $prepareResultPath) { $prepareStatus = (Get-Content -Raw -LiteralPath $prepareResultPath | ConvertFrom-Json).status }
$exitRecord = [ordered]@{
    schema = 'C4_CROSSLANG_NOPLANT_OS_EXIT_V1'
    matlab_os_exit_code = $matlabOsExitCode
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    synthetic_result_status = $syntheticStatus
    prepare_result_status = $prepareStatus
    plant_authorized = $false
    matlab_called_once = $true
}
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; SYNTHETIC={1}; PREPARE={2}" -f $matlabOsExitCode, $syntheticStatus, $prepareStatus)
exit $matlabOsExitCode
