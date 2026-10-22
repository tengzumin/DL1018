param([ValidateSet('PROBE','CONTINUE')][string]$Mode='PROBE',[switch]$ParentReviewed)
$ErrorActionPreference='Stop'
if(-not $ParentReviewed){Write-Error 'Both modes require a fresh parent review and -ParentReviewed.';exit 2}
$expDir=$PSScriptRoot
$lock=Get-Content (Join-Path $expDir 'frozen_inputs.json') -Raw|ConvertFrom-Json -DateKind String
$deadline=[DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
if($deadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or [DateTimeOffset]::UtcNow -ge $deadline){Write-Error 'Fixed global deadline 2026-10-24T17:01:00Z has passed or changed.';exit 1}
$pwsh=(Get-Command pwsh -ErrorAction Stop).Source
& $pwsh -NoProfile -File (Join-Path $expDir 'preflight_round2.ps1') -Mode $Mode -ParentReviewed:$ParentReviewed
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$report=Get-Content (Join-Path $expDir 'reports\preflight_round2.json') -Raw|ConvertFrom-Json
if($report.status -ne 'PASS' -or $report.mode -ne $Mode -or -not $report.parent_reviewed_switch_present -or $report.matlab_process_count -ne 0){Write-Error 'Fresh mode-specific preflight is not a clean PASS; MATLAB not started.';exit 1}
$batchPath=$expDir.Replace('\','/')
& $lock.matlab.exe -batch "addpath('$batchPath'); run_round2_pcf_screen('$Mode')"
exit $LASTEXITCODE
