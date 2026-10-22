param(
    [ValidateSet('PROBE','CONTINUE')][string] $Mode = 'PROBE',
    [switch] $ParentReviewed
)
$ErrorActionPreference = 'Stop'
if (-not $ParentReviewed) {
    Write-Output 'Both PROBE and CONTINUE require parent model review and the explicit -ParentReviewed switch.'
    exit 2
}
$expDir = $PSScriptRoot
$lock = Get-Content -LiteralPath (Join-Path $expDir 'frozen_inputs.json') -Raw | ConvertFrom-Json -DateKind String
$globalDeadline = [DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
if ($globalDeadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or [DateTimeOffset]::UtcNow -ge $globalDeadline) {
    Write-Error 'The fixed global deadline 2026-10-24T17:01:00Z has passed or changed; refusing to start MATLAB.'
    exit 1
}
$preflightScript = Join-Path $expDir 'preflight_round1.ps1'
$pwshPath = (Get-Command pwsh -ErrorAction Stop).Source
& $pwshPath -NoProfile -File $preflightScript -Mode $Mode -ParentReviewed:$ParentReviewed
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$report = Get-Content -LiteralPath (Join-Path $expDir 'reports\preflight_round1.json') -Raw | ConvertFrom-Json -DateKind String
if ($report.status -ne 'PASS' -or $report.mode -ne $Mode -or
    -not $report.parent_reviewed_switch_present -or $report.matlab_process_count -ne 0) {
    Write-Error 'Mode-specific preflight is not a clean PASS; MATLAB was not started.'
    exit 1
}
$batchPath = $expDir.Replace('\', '/')
$batchCommand = "addpath('$batchPath'); run_frozen_w0_screen('$Mode')"
& $lock.matlab.exe -batch $batchCommand
exit $LASTEXITCODE
