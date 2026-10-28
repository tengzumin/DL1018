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
& $matlab.Source -batch $command
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

