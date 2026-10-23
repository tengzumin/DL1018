$ErrorActionPreference = 'Stop'
$taskDir = [IO.Path]::GetDirectoryName($PSCommandPath)
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c5_matched_ablation_execution/dev72_v2'
[IO.Directory]::CreateDirectory($reportDir) | Out-Null
$exitPath = Join-Path $reportDir 'C5_NO_DELAYED_PREDICTION_DEV72_NOPLANT_OS_EXIT_v2.json'
$resultPath = Join-Path $taskDir 'C5_ABLATION_DEV72_PREPARE_RESULT_v2.json'
$snapshotPath = Join-Path $taskDir 'C5_ABLATION_DEV72_PREPARED_CFG_OPTS_v2.mat'
$syntheticPath = Join-Path $taskDir 'C5_ABLATION_CROSSLANG_RESULT_DEV72_v2.json'
$preflightPath = Join-Path $taskDir 'C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v2.json'
$failurePath = Join-Path $taskDir 'C5_ABLATION_DEV72_RUNNER_PREFLIGHT_FAILURE_v2.json'
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior no-Plant exit record; do not rerun.' }
if ((Test-Path -LiteralPath $resultPath) -or (Test-Path -LiteralPath $snapshotPath) -or
    (Test-Path -LiteralPath $syntheticPath) -or (Test-Path -LiteralPath $preflightPath) -or
    (Test-Path -LiteralPath $failurePath)) { throw 'No-Plant output already exists; preserve it and do not rerun.' }
$parseTokens = $null; $parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$activeMatlab = Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'"
if ($activeMatlab) { throw 'A MATLAB process is already active; do not overlap the no-Plant check.' }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
$prefDir = Join-Path $taskDir 'matlab_prefdir_noplant_v2'
if (-not (Test-Path -LiteralPath $prefDir)) { New-Item -ItemType Directory -Path $prefDir | Out-Null }
$env:MATLAB_PREFDIR = $prefDir
& $matlabExe -singleCompThread -wait -batch "try; cd('$($taskDir.Replace('\','/'))'); check_c5_matched_ablation_dev72_synthetic_v2; prepare_c5_matched_ablation_dev72_v2; run_c5_matched_ablation_dev72_v2('PREFLIGHT_ONLY_C5_MATCHED_ABLATION_DEV72_V2'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$prepareStatus = $null; if (Test-Path -LiteralPath $resultPath) { $prepareStatus = (Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json).status }
$preflightStatus = $null; if (Test-Path -LiteralPath $preflightPath) { $preflightStatus = (Get-Content -Raw -LiteralPath $preflightPath | ConvertFrom-Json).status }
$exitRecord = [ordered]@{
    schema='C5_MATCHED_ABLATION_DEV72_NOPLANT_OS_EXIT_V2'; variant_id='C5_NO_DELAYED_PREDICTION'
    matlab_os_exit_code=$matlabOsExitCode; completed_utc=[DateTime]::UtcNow.ToString('o')
    command_file=$PSCommandPath; command_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    input_lock_sha256=(Get-FileHash -LiteralPath (Join-Path $taskDir 'C5_ABLATION_DEV72_INPUT_LOCK_v2.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    runner_sha256=(Get-FileHash -LiteralPath (Join-Path $taskDir 'run_c5_matched_ablation_dev72_v2.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    prepare_status=$prepareStatus; runner_preflight_status=$preflightStatus
    plant_authorized=$false; matlab_called_once=$true; matlab_prefdir=$prefDir
}
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; PREPARE={1}; PREFLIGHT={2}" -f $matlabOsExitCode, $prepareStatus, $preflightStatus)
exit $matlabOsExitCode
