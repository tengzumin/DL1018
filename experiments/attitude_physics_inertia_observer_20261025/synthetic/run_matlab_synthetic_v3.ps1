$ErrorActionPreference = 'Stop'
$syntheticDir = $PSScriptRoot
$experimentDir = Split-Path -Parent $syntheticDir
$repoRoot = (Resolve-Path (Join-Path $experimentDir '..\..')).Path
$matlabExe = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$auditPath = Join-Path $syntheticDir 'PHYS_ATT_OBSERVER_SYNTH_AUDIT_v3.json'
$commandPath = Join-Path $syntheticDir 'matlab_command_v3.txt'
$stdoutPath = Join-Path $syntheticDir 'matlab_stdout_v3.log'
$stderrPath = Join-Path $syntheticDir 'matlab_stderr_v3.log'
$exitPath = Join-Path $syntheticDir 'matlab_exit_code_v3.txt'
foreach ($path in @($auditPath, $commandPath, $stdoutPath, $stderrPath, $exitPath)) {
    if (Test-Path -LiteralPath $path) { throw "Refusing to overwrite existing evidence: $path" }
}
if (-not (Test-Path -LiteralPath $matlabExe -PathType Leaf)) { throw "MATLAB R2025b not found: $matlabExe" }
$coreDir = Join-Path $repoRoot 'matlab\core'
$matlabCommand = "restoredefaultpath; addpath('$coreDir'); addpath('$experimentDir'); addpath('$syntheticDir'); audit=run_phys_attitude_synthetic_audit_v3('$auditPath'); assert(strcmp(audit.status,'PASS'));"
Set-Content -LiteralPath $commandPath -Value "$matlabExe -batch $matlabCommand" -Encoding utf8
Set-Location $repoRoot
& $matlabExe -batch $matlabCommand 1> $stdoutPath 2> $stderrPath
$exitCode = $LASTEXITCODE
Set-Content -LiteralPath $exitPath -Value $exitCode -Encoding ascii
if ($exitCode -ne 0) { throw "MATLAB synthetic v3 audit failed with exit code $exitCode" }
