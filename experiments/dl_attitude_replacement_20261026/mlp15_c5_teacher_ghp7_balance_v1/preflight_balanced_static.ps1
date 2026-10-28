$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $taskRoot '..\..\..')).Path
$researchRoot = (Resolve-Path (Join-Path $taskRoot '..')).Path
$lockPath = Join-Path $taskRoot 'MLP15_C5_GHP7_BALANCE_PILOT_SOURCE_LOCK_v1.json'
$releasePath = Join-Path $taskRoot 'MLP15_C5_GHP7_BALANCE_PILOT_RELEASE_v1.json'
$reportPath = Join-Path $taskRoot 'STATIC_PREFLIGHT_GHP7_BALANCE_v1.json'
function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-Hash([string]$Path,[string]$Expected) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing locked file: $Path" }
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "SHA mismatch: $Path" }
    return $actual
}
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
if ($lock.schema -ne 'DL1018_MLP15_C5_GHP7_BALANCE_PILOT_SOURCE_LOCK_V1' -or $lock.status -ne 'APPROVED_FOR_CLOSED_LOOP_SCREEN') { throw 'Candidate source lock is not root-approved.' }
if ($release.status -ne 'PREPARED_PENDING_ROOT_APPROVAL' -or $release.plant_calls_authorized -ne 0 -or $release.TEST48_read -ne $false -or $release.max_plant_calls -ne 6) { throw 'Pilot release must be pending with zero Plant calls.' }
if ((Get-Sha256 $lockPath) -ne $release.candidate_source_lock_sha256) { throw 'Release/source-lock SHA mismatch.' }
$sourceChecks = foreach ($file in $lock.source_file_sha256) {
    $path = Join-Path $projectRoot $file.path
    [void](Assert-Hash $path $file.sha256)
    [pscustomobject]@{path=$file.path;sha256=$file.sha256}
}
$sharedTask = Join-Path $researchRoot 'pilot_runner_mlp15_c5_full72_v1'
$sharedLockPath = Join-Path $sharedTask 'MLP15_C5_FULL72_PILOT_SOURCE_LOCK_v1.json'
if ((Get-Sha256 $sharedLockPath) -ne $lock.shared_runner_source_lock_sha256) { throw 'Shared C5 runner lock SHA mismatch.' }
$sharedLock = Get-Content -LiteralPath $sharedLockPath -Raw | ConvertFrom-Json
$sharedChecks = foreach ($file in $sharedLock.candidate_runner.files) {
    $path = Join-Path (Join-Path $sharedTask 'candidate_runner_work') $file.relative_path
    [void](Assert-Hash $path $file.sha256)
    [pscustomobject]@{path=$file.relative_path;sha256=$file.sha256}
}
$payloadManifestPath = Join-Path $researchRoot 'GHP7_PILOT_PAYLOAD_MANIFEST_v1.json'
$baselineManifestPath = Join-Path $researchRoot 'GHP7_BASELINE_REUSE_MANIFEST_v1.json'
if ((Get-Sha256 $payloadManifestPath) -ne $release.payload_manifest_sha256 -or (Get-Sha256 $baselineManifestPath) -ne $release.baseline_reuse_manifest_sha256) { throw 'Frozen payload/baseline manifest SHA mismatch.' }
$payloadManifest = Get-Content -LiteralPath $payloadManifestPath -Raw | ConvertFrom-Json
$baselineManifest = Get-Content -LiteralPath $baselineManifestPath -Raw | ConvertFrom-Json
if ($payloadManifest.status -ne 'PASS' -or $payloadManifest.scene_count -ne 6 -or $payloadManifest.tests_data_read -ne $false -or $payloadManifest.payloads_copied -ne $false) { throw 'Payload manifest failed its frozen read-only gate.' }
if ($baselineManifest.status -ne 'PASS' -or $baselineManifest.record_count -ne 12 -or $baselineManifest.test_data_read -ne $false -or $baselineManifest.raw_files_copied -ne $false -or $baselineManifest.baselines_reexecuted -ne $false) { throw 'Baseline reuse manifest failed its frozen read-only gate.' }
$payloadChecks = foreach ($record in $payloadManifest.records) {
    [void](Assert-Hash $record.payload_path $record.payload_file_sha256)
    [pscustomobject]@{scene_id=$record.scene_id;sha256=$record.payload_file_sha256}
}
$baselineChecks = foreach ($record in $baselineManifest.records) {
    [void](Assert-Hash $record.raw_path $record.raw_sha256)
    [pscustomobject]@{scene_id=$record.scene_id;method=$record.attitude_arm;application_feasible=$record.application_feasible;sha256=$record.raw_sha256}
}
$noPlantPath = Join-Path $taskRoot 'audits\NO_PLANT_PREFLIGHT_GHP7_BALANCE_v1.json'
$codeAuditPath = Join-Path $taskRoot 'audits\MLP15_GHP7_BALANCE_CODE_ANALYZER_v1.json'
$noPlant = Get-Content -LiteralPath $noPlantPath -Raw | ConvertFrom-Json
$codeAudit = Get-Content -LiteralPath $codeAuditPath -Raw | ConvertFrom-Json
if ($noPlant.status -ne 'PASS_NO_PLANT' -or $noPlant.plant_calls -ne 0 -or $noPlant.TEST48_read -ne $false -or $noPlant.scene_count -ne 6) { throw 'MATLAB no-Plant preflight did not pass.' }
if ($codeAudit.status -ne 'PASS_NO_NEW_DIAGNOSTICS' -or $codeAudit.diagnostic_count -ne 0 -or $codeAudit.plant_called -ne $false -or $codeAudit.TEST48_read -ne $false) { throw 'MATLAB Code Analyzer did not pass.' }
$runsRoot = Join-Path $researchRoot 'pilot_runs_mlp15_c5_ghp7_balance_v1'
if (Test-Path -LiteralPath $runsRoot) { throw 'Candidate output directory already exists before first Plant release.' }
$report = [ordered]@{
    schema='DL1018_MLP15_C5_GHP7_BALANCE_STATIC_PREFLIGHT_V1'
    status='PASS_STATIC_NO_PLANT'
    method='PowerShell 7; hashes and identity checks only'
    plant_invoked=$false;closed_loop_started=$false;training_started=$false;TEST48_read=$false
    baselines_reexecuted=$false;baseline_raws_copied=$false;plant_calls_authorized=0
    source_lock_sha256=(Get-Sha256 $lockPath)
    taskbook_sha256=(Get-Sha256 (Join-Path $taskRoot 'MLP15_C5_GHP7_BALANCED_CLOSED_LOOP_TASKBOOK_v1.md'))
    new_source_file_count=$sourceChecks.Count;shared_runner_file_count=$sharedChecks.Count
    payload_count=$payloadChecks.Count;baseline_raw_count=$baselineChecks.Count
    max_tilt_deg=30;dmax_rad_s2=@(45,45,4.7124)
    no_plant_report_sha256=(Get-Sha256 $noPlantPath);code_analyzer_sha256=(Get-Sha256 $codeAuditPath)
    candidate_output_directory_absent=$true
    reused_baseline_raws=$baselineChecks;payloads=$payloadChecks
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
$report | ConvertTo-Json -Depth 2
