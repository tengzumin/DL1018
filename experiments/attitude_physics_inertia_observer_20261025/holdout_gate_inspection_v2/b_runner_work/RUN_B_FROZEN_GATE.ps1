[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ScenePayloadPath,
    [string]$MatlabExe = 'matlab.exe'
)
$ErrorActionPreference = 'Stop'
$workRoot = $PSScriptRoot
$resolvedPayload = (Resolve-Path -LiteralPath $ScenePayloadPath).Path
$payloadFile = Get-Item -LiteralPath $resolvedPayload
if ($payloadFile.Extension -ne '.mat' -or $payloadFile.BaseName -notmatch '(?i)scene[_-]payload') {
    throw 'Input must be a new .mat scene payload whose filename contains scene_payload.'
}
$normalizedPayload = $resolvedPayload -replace '/', '\'
if ($normalizedPayload -match '(?i)(?:test|raw|status|score)' -or
    $normalizedPayload -match '(?i)[\\/]runs_b[\\/]' -or
    $normalizedPayload -match '(?i)[\\/]data[\\/]raw[\\/]') {
    throw 'Historical raw, TEST, status, and score paths are rejected before MATLAB opens the file.'
}
& (Join-Path $workRoot 'verify_no_plant_identity.ps1') -Quiet
$matlab = Get-Command -Name $MatlabExe -CommandType Application -ErrorAction Stop
function ConvertTo-MatlabString([string]$value) { return $value.Replace("'", "''") }
$workEscaped = ConvertTo-MatlabString $workRoot
$payloadEscaped = ConvertTo-MatlabString $resolvedPayload
$command = "cd('$workEscaped'); run_b_frozen_gate('$payloadEscaped');"
$prefRoot = Join-Path (Split-Path -Parent $workRoot) 'pilot_prefdirs'
$logRoot = Join-Path (Split-Path -Parent $workRoot) 'pilot_logs'
New-Item -ItemType Directory -Force -Path $prefRoot,$logRoot | Out-Null
$runId = [guid]::NewGuid().ToString('N')
$prefDir = Join-Path $prefRoot ('B_' + $runId)
New-Item -ItemType Directory -Path $prefDir | Out-Null
$logPath = Join-Path $logRoot ('B_' + $payloadFile.BaseName + '_' + $runId + '.log')
$oldPrefDir = $env:MATLAB_PREFDIR
$runExitCode = 0
try {
    $env:MATLAB_PREFDIR = $prefDir
    & $matlab.Source -batch $command *>&1 | Tee-Object -FilePath $logPath
    $runExitCode = $LASTEXITCODE
} finally {
    if ($null -eq $oldPrefDir) { Remove-Item Env:MATLAB_PREFDIR -ErrorAction SilentlyContinue }
    else { $env:MATLAB_PREFDIR = $oldPrefDir }
}
if ($runExitCode -ne 0) { exit $runExitCode }

