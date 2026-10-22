param([ValidateSet('PROBE','CONTINUE')][string]$Mode='PROBE',[switch]$ParentReviewed)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){Write-Error 'PowerShell 7 is required.';exit 2}
if(-not $ParentReviewed){Write-Error 'PROBE/CONTINUE require -ParentReviewed.';exit 2}
$expDir=$PSScriptRoot;$lockPath=Join-Path $expDir 'frozen_inputs.json'
$lock=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json -Depth 100 -DateKind String
$sha=(Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($lock.schema -ne 'ROUND3_XY_PCF_SCREEN_INPUTS_V1'){Write-Error 'Unexpected R3 input-lock schema.';exit 1}
$deadline=[DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
if($deadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or [DateTimeOffset]::UtcNow -ge $deadline){Write-Error 'Frozen deadline changed or passed.';exit 1}
$pwsh=(Get-Command pwsh -ErrorAction Stop).Source
& $pwsh -NoProfile -File (Join-Path $expDir 'preflight_round3.ps1') -Mode $Mode -ParentReviewed
if($LASTEXITCODE -ne 0){Write-Error 'Fresh reviewed preflight failed; MATLAB was not started.';exit $LASTEXITCODE}
$reportPath=Join-Path $expDir 'reports\preflight_round3.json'
$report=Get-Content -LiteralPath $reportPath -Raw|ConvertFrom-Json -DateKind String
$age=[DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse([string]$report.created_utc).ToUniversalTime()
if($report.status -ne 'PASS' -or $report.mode -ne $Mode -or -not $report.parent_reviewed_switch_present -or
   $report.matlab_process_count -ne 0 -or $report.frozen_inputs_sha256 -ne $sha -or $age.TotalMinutes -lt 0 -or $age.TotalMinutes -gt 5){
    Write-Error 'Preflight is not a fresh mode-specific PASS for this frozen input lock; MATLAB was not started.';exit 1
}
$batchDir=$expDir.Replace('\','/')
& $lock.matlab.exe -batch "addpath('$batchDir'); run_round3_xy_pcf_screen('$Mode',true)"
exit $LASTEXITCODE
