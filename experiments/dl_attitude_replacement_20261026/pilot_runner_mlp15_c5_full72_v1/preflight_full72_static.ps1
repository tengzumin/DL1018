$ErrorActionPreference = 'Stop'
$runnerRoot = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $runnerRoot '..\..\..')).Path
$researchRoot = (Resolve-Path (Join-Path $runnerRoot '..')).Path
$lockPath = Join-Path $runnerRoot 'MLP15_C5_FULL72_PILOT_SOURCE_LOCK_v1.json'
$reportPath = Join-Path $runnerRoot 'STATIC_PREFLIGHT_MLP15_C5_FULL72_v1.json'
function Get-Sha256([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-FileHash([string]$RelativePath,[string]$Expected) {
    $path = Join-Path $projectRoot $RelativePath
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing locked file: $RelativePath" }
    $actual = Get-Sha256 $path
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "SHA mismatch: $RelativePath" }
    return $actual
}
$lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
if ($lock.schema -ne 'DL1018_MLP15_C5_FULL72_PILOT_SOURCE_LOCK_V1' -or $lock.status -ne 'PREPARED_PENDING_ROOT_REVIEW') { throw 'Unexpected runner source lock state.' }
if (([IO.Path]::GetFullPath($lock.candidate_runner.root)) -ne ([IO.Path]::GetFullPath((Join-Path $runnerRoot 'candidate_runner_work')))) { throw 'Runner source root mismatch.' }
$trainingLockPath = Join-Path $projectRoot $lock.training_source_lock.path
$trainingLock = Get-Content -Raw -LiteralPath $trainingLockPath | ConvertFrom-Json
$datasetArtifact = $lock.training_artifacts | Where-Object { $_.path -match 'DATASET_MANIFEST_v1\.json$' } | Select-Object -First 1
$datasetManifest = Get-Content -Raw -LiteralPath (Join-Path $projectRoot $datasetArtifact.path) | ConvertFrom-Json
if ($datasetManifest.inertia_config_read -ne $false -or $trainingLock.dataset.manifest_inertia_config_read -ne $false) { throw 'Training source or manifest records inertia-configuration access.' }
$sourceChecks = foreach ($file in $lock.candidate_runner.files) {
    $path = Join-Path $runnerRoot (Join-Path 'candidate_runner_work' $file.relative_path)
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Sha256 $path) -ne $file.sha256) { throw "Runner source mismatch: $($file.relative_path)" }
    [pscustomobject]@{ path=$file.relative_path; sha256=$file.sha256 }
}
foreach ($artifact in $lock.training_artifacts) { [void](Assert-FileHash $artifact.path $artifact.sha256) }
foreach ($artifact in $lock.shared_stack_artifacts) { [void](Assert-FileHash $artifact.path $artifact.sha256) }
$payloadManifest = Get-Content -Raw (Join-Path $researchRoot 'GHP7_PILOT_PAYLOAD_MANIFEST_v1.json') | ConvertFrom-Json
$baselineManifest = Get-Content -Raw (Join-Path $researchRoot 'GHP7_BASELINE_REUSE_MANIFEST_v1.json') | ConvertFrom-Json
if ($payloadManifest.status -ne 'PASS' -or $payloadManifest.scene_count -ne 6 -or $baselineManifest.status -ne 'PASS' -or $baselineManifest.record_count -ne 12 -or $baselineManifest.baselines_reexecuted -or $baselineManifest.raw_files_copied -or $baselineManifest.test_data_read) { throw 'GHP7 payload/baseline reuse manifest is invalid.' }
$baselineChecks = foreach ($record in $baselineManifest.records) {
    if (!(Test-Path -LiteralPath $record.raw_path -PathType Leaf) -or (Get-Sha256 $record.raw_path) -ne $record.raw_sha256) { throw "Historical baseline raw mismatch: $($record.scene_id) / $($record.runner)" }
    [pscustomobject]@{ scene_id=$record.scene_id; method=$record.attitude_arm; application_feasible=$record.application_feasible; raw_sha256=$record.raw_sha256 }
}
$payloadChecks = foreach ($record in $payloadManifest.records) {
    if (!(Test-Path -LiteralPath $record.payload_path -PathType Leaf) -or (Get-Sha256 $record.payload_path) -ne $record.payload_file_sha256) { throw "Frozen payload mismatch: $($record.scene_id)" }
    [pscustomobject]@{ scene_id=$record.scene_id; sha256=$record.payload_file_sha256 }
}
$history = $baselineManifest.historical_note
$feasibleExceptions = @($baselineChecks | Where-Object { !$_.application_feasible } | ForEach-Object { "$($_.scene_id):$($_.method)" } | Sort-Object -Unique)
$expectedExceptions = @('DL1018_GHP7_G2_W00:B','DL1018_GHP7_G2_W00:C5_RBF','DL1018_GHP7_G2_W12:B')
if (!(Compare-Object $expectedExceptions $feasibleExceptions -SyncWindow 0 | Measure-Object).Count -eq 0) { throw 'Historical feasible-flag exceptions differ from the reviewed manifest.' }
if ($history -notmatch 'G1 / W00.*completion-flag mismatch') { throw 'Historical G1/W00 completion mismatch note is missing.' }
$runsRoot = Join-Path $researchRoot 'pilot_runs_mlp15_c5_full72_v1'
if (Test-Path -LiteralPath $runsRoot) { throw 'Candidate output directory already exists before root authorization.' }
$release = Get-Content -Raw (Join-Path $runnerRoot 'MLP15_C5_FULL72_PILOT_RELEASE_v1.json') | ConvertFrom-Json
if ($release.status -ne 'PREPARED_PENDING_ROOT_APPROVAL' -or $release.plant_calls_authorized -ne 0 -or $release.test_data_read -or $release.max_plant_calls -ne 6) { throw 'Pilot release is not safely pending with zero Plant calls.' }
$report = [ordered]@{
    schema='DL1018_MLP15_C5_FULL72_STATIC_PREFLIGHT_V1'
    status='PASS_STATIC_NO_PLANT'
    method='PowerShell 7; static identities, hashes, and source inspection only'
    plant_invoked=$false
    closed_loop_started=$false
    training_started=$false
    test_data_read=$false
    baseline_runs_reexecuted=$false
    baseline_raw_files_copied=$false
    plant_calls_authorized=0
    matlab_code_analyzer_executed=$false
    matlab_no_plant_scene_preparation_executed=$false
    source_lock_sha256=(Get-Sha256 $lockPath)
    taskbook_sha256=(Get-Sha256 (Join-Path $runnerRoot 'MLP15_C5_FULL72_CLOSED_LOOP_TASKBOOK_v1.md'))
    runner_source_file_count=$sourceChecks.Count
    training_artifact_count=$lock.training_artifacts.Count
    manifest_inertia_config_read=$datasetManifest.inertia_config_read
    training_lock_manifest_inertia_config_read=$trainingLock.dataset.manifest_inertia_config_read
    runtime_feature_contract='PASS_13D_LOCKED_ORDER'
    shared_stack_artifact_count=$lock.shared_stack_artifacts.Count
    payload_count=$payloadChecks.Count
    reused_baseline_count=$baselineChecks.Count
    reused_baseline_raws=$baselineChecks
    payloads=$payloadChecks
    baseline_historical_note=$history
    application_feasible_exceptions=$feasibleExceptions
    candidate_output_directory_absent=$true
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
$report | ConvertTo-Json -Depth 2





