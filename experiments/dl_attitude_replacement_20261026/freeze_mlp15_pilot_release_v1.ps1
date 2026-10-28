$ErrorActionPreference = 'Stop'
$researchRoot = Join-Path (Get-Location).Path 'experiments/dl_attitude_replacement_20261026'
$runnerRoot = Join-Path $researchRoot 'pilot_runner_mlp15_v1/candidate_runner_work'
$runRoot = Join-Path $researchRoot 'mlp15_formal_v1/run_v1'
$releasePath = Join-Path $researchRoot 'MLP15_PILOT_RELEASE_v1.json'
$lockPath = Join-Path $researchRoot 'MLP15_CANDIDATE_SOURCE_LOCK_v1.json'
if (Test-Path -LiteralPath $releasePath) { throw "Refusing to overwrite $releasePath" }
if (Test-Path -LiteralPath $lockPath) { throw "Refusing to overwrite $lockPath" }

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-JsonFile([string]$Path, $Value) {
    $json = ConvertTo-Json -InputObject $Value -Depth 30
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

$sourceRoot = (Resolve-Path -LiteralPath $runnerRoot).Path
$matlabRoot = Join-Path $sourceRoot 'matlab'
$files = @(Get-ChildItem -LiteralPath $matlabRoot -Filter '*.m' -File -Recurse | Sort-Object FullName)
$lockedFiles = foreach ($file in $files) {
$relative = $file.FullName.Substring($sourceRoot.Length + 1).Replace([char]92, '/')
    [ordered]@{ relative_path = $relative; sha256 = Get-Sha256 $file.FullName }
}
$lock = [ordered]@{
    schema = 'DL1018_MLP15_CANDIDATE_SOURCE_LOCK_V1'
    root = $sourceRoot
    file_count = $files.Count
    files = @($lockedFiles)
}

$payloadPath = Join-Path $researchRoot 'GHP7_PILOT_PAYLOAD_MANIFEST_v1.json'
$physicsPath = Join-Path $researchRoot 'GHP7_C5_10_PHYSICS_REFERENCE_REUSE_MANIFEST_v1.json'
$payloadManifest = Get-Content -LiteralPath $payloadPath -Raw | ConvertFrom-Json
$trainingProgress = Get-Content -LiteralPath (Join-Path $runRoot 'training_progress.json') -Raw | ConvertFrom-Json
$trainingConfig = Get-Content -LiteralPath (Join-Path $runRoot 'training_config.json') -Raw | ConvertFrom-Json
$datasetManifest = Get-Content -LiteralPath (Join-Path $researchRoot 'dataset_v4_teacher_distill/DATASET_MANIFEST_v2.json') -Raw | ConvertFrom-Json
$screenAudit = Get-Content -LiteralPath (Join-Path $researchRoot 'architecture_screen_v1/SCREEN_AUDIT_v1.json') -Raw | ConvertFrom-Json
$checkpointAudit = Get-Content -LiteralPath (Join-Path $runRoot 'MLP15_CHECKPOINT_AUDIT_v1.json') -Raw | ConvertFrom-Json
$parityAudit = Get-Content -LiteralPath (Join-Path $runRoot 'MATLAB_PARITY_AUDIT_v1.json') -Raw | ConvertFrom-Json
$noPlantAudit = Get-Content -LiteralPath (Join-Path $researchRoot 'MATLAB_NO_PLANT_AUDIT_MLP15_v1.json') -Raw | ConvertFrom-Json
$codeAudit = Get-Content -LiteralPath (Join-Path $researchRoot 'MLP15_RUNNER_CODE_ANALYZER_COMPARISON_v1.json') -Raw | ConvertFrom-Json
$baseline = Get-Content -LiteralPath (Join-Path $researchRoot 'GHP7_BASELINE_REUSE_MANIFEST_v1.json') -Raw | ConvertFrom-Json
$physics = Get-Content -LiteralPath $physicsPath -Raw | ConvertFrom-Json
$physicsComparison = Get-Content -LiteralPath (Join-Path $researchRoot 'C5_10_PHYSICS_PAIRED_COMPARISON_v1.json') -Raw | ConvertFrom-Json
$completionAudit = Get-Content -LiteralPath (Join-Path $researchRoot 'C5_RBF_COMPLETION_FLAG_ROOT_CAUSE_v1.json') -Raw | ConvertFrom-Json
$c5ReceiptPath = Join-Path (Get-Location).Path 'experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json'
$c5Receipt = Get-Content -LiteralPath $c5ReceiptPath -Raw | ConvertFrom-Json
if ($trainingProgress.status -ne 'PASS' -or $trainingProgress.completed_steps -ne 60000 -or
    $trainingProgress.plant_called -or $trainingProgress.test_data_read -or
    $trainingConfig.status -ne 'PASS' -or $trainingConfig.best_step -ne 59000 -or
    $trainingConfig.test_data_read -or $trainingConfig.plant_truth_read -or
    $datasetManifest.status -ne 'PASS' -or $datasetManifest.test_data_read -or
    $datasetManifest.plant_truth_read -or $datasetManifest.nominal_inertia_read -or
    $screenAudit.status -ne 'PASS_INDEPENDENT_VAL48_RECOMPUTE' -or $screenAudit.test_data_read -or
    $checkpointAudit.status -ne 'PASS_READ_ONLY_VAL48_AND_EXPORT' -or
    $checkpointAudit.plant_called -or $checkpointAudit.test_data_read -or
    $parityAudit.status -ne 'PASS' -or $parityAudit.plant_called -or $parityAudit.test_data_read -or
    $parityAudit.max_abs_error_rad_s2 -gt $parityAudit.tolerance_rad_s2 -or
    $parityAudit.tolerance_rad_s2 -gt 1e-5 -or
    $noPlantAudit.status -ne 'PASS' -or $noPlantAudit.plant_invoked -or
    $noPlantAudit.test_data_read -or $noPlantAudit.runner_matlab_file_count -ne 52 -or
    $codeAudit.status -ne 'PASS_NO_NEW_DIAGNOSTIC_IDS_OR_COUNTS' -or
    -not $codeAudit.no_new_diagnostics -or $codeAudit.plant_invoked -or $codeAudit.test_data_read -or
    $baseline.status -ne 'PASS' -or $baseline.test_data_read -or
    $physics.status -ne 'PASS' -or $physics.test_data_read -or
    $physicsComparison.status -ne 'PASS' -or $physicsComparison.test_data_read -or
    $completionAudit.status -ne 'PASS' -or $completionAudit.plant_invoked -or
    $c5Receipt.status -ne 'PASS_NO_PLANT_PILOT_PAYLOADS_ONLY' -or
    $c5Receipt.plant_calls -ne 0 -or $c5Receipt.tests_data_read) {
    throw 'An MLP15 training, data, audit, parity, baseline, or no-Plant release prerequisite failed.'
}
$payloads = @($payloadManifest.records | Where-Object geometry_arm -eq 'ACTIVE' | ForEach-Object {
    [ordered]@{
        scene_id = $_.scene_id
        geometry_arm = $_.geometry_arm
        payload_path = $_.payload_path
        payload_sha256 = $_.payload_file_sha256
        r_task_sha256 = $_.r_task_sha256
    }
})
if ($payloads.Count -ne 6 -or $lock.file_count -ne 52) {
    throw "Unexpected pilot payload/source counts: payloads=$($payloads.Count), MATLAB files=$($lock.file_count)"
}
Write-JsonFile $lockPath $lock
$release = [ordered]@{
    schema = 'DL1018_MLP15_GHP7_PILOT_RELEASE_V1'
    status = 'RELEASED'
    created_utc = [DateTime]::UtcNow.ToString('o')
    plant_calls_authorized = 6
    candidate_arm_id = 'DL_MLP15'
    geometry_arm = 'ACTIVE'
    test_data_read = $false
    variable_inertia_reconstruction_enabled = $false
    observer_enabled = $false
    feedforward_enabled = $false
    taskbook_sha256 = Get-Sha256 (Join-Path $researchRoot 'DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_FROZEN_ZH.md')
    amendment02_sha256 = Get-Sha256 (Join-Path $researchRoot 'DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT02_SUPERVISION_FIX.md')
    amendment03_sha256 = Get-Sha256 (Join-Path $researchRoot 'DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT03_RUNTIME_FEATURE_FIX.md')
    amendment04_sha256 = Get-Sha256 (Join-Path $researchRoot 'DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT04_PILOT_BINDING_FIX.md')
    amendment09_sha256 = Get-Sha256 (Join-Path $researchRoot 'DL_ATTITUDE_REPLACEMENT_TASKBOOK_v1_AMENDMENT09_MLP15_FORMAL_TRAINING.md')
    pilot_taskbook_sha256 = Get-Sha256 (Join-Path $researchRoot 'MLP15_CLOSED_LOOP_PILOT_TASKBOOK_v1.md')
    freeze_script_sha256 = Get-Sha256 $PSCommandPath
    candidate_source_lock_sha256 = Get-Sha256 $lockPath
    no_plant_audit_sha256 = Get-Sha256 (Join-Path $researchRoot 'MATLAB_NO_PLANT_AUDIT_MLP15_v1.json')
    code_analyzer_comparison_sha256 = Get-Sha256 (Join-Path $researchRoot 'MLP15_RUNNER_CODE_ANALYZER_COMPARISON_v1.json')
    dataset_manifest_sha256 = Get-Sha256 (Join-Path $researchRoot 'dataset_v4_teacher_distill/DATASET_MANIFEST_v2.json')
    screen_audit_sha256 = Get-Sha256 (Join-Path $researchRoot 'architecture_screen_v1/SCREEN_AUDIT_v1.json')
    parity_report_sha256 = Get-Sha256 (Join-Path $runRoot 'MATLAB_PARITY_AUDIT_v1.json')
    checkpoint_audit_sha256 = Get-Sha256 (Join-Path $runRoot 'MLP15_CHECKPOINT_AUDIT_v1.json')
    training_release_sha256 = Get-Sha256 (Join-Path $researchRoot 'mlp15_formal_v1/TRAINING_RELEASE_v1.json')
    training_config_sha256 = Get-Sha256 (Join-Path $runRoot 'training_config.json')
    model_sha256 = Get-Sha256 (Join-Path $runRoot 'mlp15_attitude_weights_v1.mat')
    best_step = [int]$trainingConfig.best_step
    payload_manifest_sha256 = Get-Sha256 $payloadPath
    baseline_reuse_manifest_sha256 = Get-Sha256 (Join-Path $researchRoot 'GHP7_BASELINE_REUSE_MANIFEST_v1.json')
    physics_reference_manifest_sha256 = Get-Sha256 $physicsPath
    physics_comparison_sha256 = Get-Sha256 (Join-Path $researchRoot 'C5_10_PHYSICS_PAIRED_COMPARISON_v1.json')
    completion_marker_audit_sha256 = Get-Sha256 (Join-Path $researchRoot 'C5_RBF_COMPLETION_FLAG_ROOT_CAUSE_v1.json')
    c5_receipt_sha256 = Get-Sha256 (Join-Path (Get-Location).Path 'experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json')
    score_script_sha256 = Get-Sha256 (Join-Path $researchRoot 'matlab/score_mlp15_ghp7_pilot_v1.m')
    pilot_payloads = $payloads
}
Write-JsonFile $releasePath $release
[pscustomobject]@{
    Status = 'RELEASED'
    Candidate = $release.candidate_arm_id
    AuthorizedCalls = $release.plant_calls_authorized
    LockedFiles = $lock.file_count
    ReleaseSha256 = Get-Sha256 $releasePath
    SourceLockSha256 = $release.candidate_source_lock_sha256
} | Format-List
