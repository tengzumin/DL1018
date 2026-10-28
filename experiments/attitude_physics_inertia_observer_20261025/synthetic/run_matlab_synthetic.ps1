$ErrorActionPreference = 'Stop'
$syntheticDir = $PSScriptRoot
$experimentDir = Split-Path -Parent $syntheticDir
$repoRoot = (Resolve-Path (Join-Path $experimentDir '..\..')).Path
$matlabExe = (Get-Command matlab).Source
$coreDir = Join-Path $repoRoot 'matlab\core'
$helperDir = $experimentDir
$runnerDir = $syntheticDir
$auditPath = Join-Path $syntheticDir 'PHYS_ATT_OBSERVER_SYNTH_AUDIT_v1.json'
$matlabCommand = "restoredefaultpath; addpath('$coreDir'); addpath('$helperDir'); addpath('$runnerDir'); audit=run_phys_attitude_synthetic_audit('$auditPath'); assert(strcmp(audit.status,'PASS'));"
$commandRecord = "$matlabExe -batch $matlabCommand"
Set-Content -LiteralPath (Join-Path $syntheticDir 'matlab_command.txt') -Value $commandRecord -Encoding utf8
Set-Location $repoRoot
& $matlabExe -batch $matlabCommand 1> (Join-Path $syntheticDir 'matlab_stdout.log') 2> (Join-Path $syntheticDir 'matlab_stderr.log')
$exitCode = $LASTEXITCODE
Set-Content -LiteralPath (Join-Path $syntheticDir 'matlab_exit_code.txt') -Value $exitCode -Encoding ascii
if ($exitCode -ne 0) {
    throw "MATLAB synthetic audit failed with exit code $exitCode. See logs in $syntheticDir"
}

