$ErrorActionPreference = 'Stop'
$studyRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $studyRoot '..\..\..')).Path
$parentRoot = Join-Path $repoRoot 'experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_dev_v1'
$payloadPath = Join-Path $studyRoot 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'
$parentPayloadPath = Join-Path $studyRoot 'MLP15_DEV72_PAYLOAD_MANIFEST_PARENT_v1.json'
$payload = Get-Content -Raw $payloadPath | ConvertFrom-Json
$parentPayload = Get-Content -Raw $parentPayloadPath | ConvertFrom-Json
$c5LockPath = Join-Path $repoRoot 'experiments\position_axis_coordinate_c5_dev72_20261023\C5_DEV72_INPUT_LOCK_v3.json'
$c5BatchPath = Join-Path $repoRoot 'experiments\position_axis_coordinate_c5_dev72_20261023\C5_DEV72_BATCH_STATUS_v3.json'
$c5Lock = Get-Content -Raw $c5LockPath | ConvertFrom-Json
$c5Batch = Get-Content -Raw $c5BatchPath | ConvertFrom-Json
$parentManifestPath = Join-Path $parentRoot 'MANIFEST.json'
$parentManifest = Get-Content -Raw $parentManifestPath | ConvertFrom-Json

function File-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing input file: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Require-Sha([string]$Path, [string]$Expected, [string]$Label) {
    $actual = File-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "$Label SHA mismatch: $Path (expected $Expected, actual $actual)" }
    return $actual
}

$payloadRecords = @($payload.records)
$parentPayloadRecords = @($parentPayload.records)
$c5Scenes = @($c5Lock.scenes)
$c5BatchRows = @($c5Batch.records)
$parentRows = @($parentManifest.records)
if ($payloadRecords.Count -ne 72 -or $parentPayloadRecords.Count -ne 72 -or $c5Scenes.Count -ne 72) { throw 'Expected exactly 72 payload/C5 rows.' }
if ($payload.test_data_read -ne $false -or $payload.plant_calls -ne 0 -or $payload.training_runs -ne 0 -or $parentPayload.status -ne 'PASS_NO_PLANT' -or $parentPayload.test_data_read -ne $false) { throw 'Payload provenance does not prove no TEST/no Plant/no training.' }
if (@($payloadRecords | Where-Object source_split -eq 'DEV').Count -ne 24 -or @($payloadRecords | Where-Object source_split -eq 'VAL').Count -ne 48) { throw 'DEV24/VAL48 split mismatch.' }
if (@($payloadRecords | Where-Object scene_id -match 'TEST').Count -ne 0) { throw 'TEST scene in payload cohort.' }

$c5Ids = @($c5Lock.scene_ids_all_72 | ForEach-Object { [string]$_ })
$payloadIds = @($payloadRecords | ForEach-Object { [string]$_.scene_id })
if (($c5Ids -join "`n") -cne ($payloadIds -join "`n")) { throw 'C5 lock scene order differs from payload manifest.' }
$parentById = @{}
foreach ($r in $parentRows) { $parentById[[string]$r.scene_id] = $r }
$c5ById = @{}
foreach ($r in $c5Scenes) { $c5ById[[string]$r.scene_id] = $r }
$batchById = @{}
foreach ($r in $c5BatchRows) { $batchById[[string]$r.scene_id] = $r }
if ($parentRows.Count -ne 6 -or $batchById.Count -ne 60) { throw 'Expected six existing parent candidate rows and 60 new C5 source rows.' }

$identityRows = [System.Collections.Generic.List[object]]::new()
$manifestRows = [System.Collections.Generic.List[object]]::new()
foreach ($r in $payloadRecords) {
    $id = [string]$r.scene_id
    $c5Scene = $c5ById[$id]
    if ($null -eq $c5Scene -or $c5Scene.external_identity_sha256 -ne $r.external_identity_sha256) { throw "C5 external identity mismatch for $id" }
    Require-Sha ([string]$r.payload_path) ([string]$r.payload_sha256) "$id payload" | Out-Null
    Require-Sha ([string]$r.b_raw_path) ([string]$r.b_raw_sha256) "$id B raw" | Out-Null
    Require-Sha ([string]$r.b_status_path) ([string]$r.b_status_sha256) "$id B status" | Out-Null
    $bStatus = Get-Content -Raw ([string]$r.b_status_path) | ConvertFrom-Json
    if ([string]$bStatus.scene_id -ne $id -or [bool]$bStatus.TEST_accessed -or [int]$bStatus.transitions -ne 20000) { throw "B status identity/scope mismatch for $id" }
    if ($c5Scene.C5_reuse.reused) {
        $c5RawPath = [string]$c5Scene.C5_reuse.raw_path
        $c5RawSha = [string]$c5Scene.C5_reuse.raw_sha256
        $c5StatusPath = [string]$c5Scene.C5_reuse.run_status_path
        $c5StatusSha = [string]$c5Scene.C5_reuse.run_status_sha256
        $c5RunStartPath = [string]$c5Scene.C5_reuse.run_start_path
        $c5RunStartSha = [string]$c5Scene.C5_reuse.run_start_sha256
        $c5AuditState = [string]$c5Scene.C5_reuse.parent_screen_status
        $c5AuditScope = 'PARENT_SCREEN_REUSE'
    } else {
        $c5Row = $batchById[$id]
        if ($null -eq $c5Row -or $c5Row.status -ne 'RUN_COMPLETE_RAW_PENDING_AUDIT') { throw "Missing/pending-state mismatch for C5 source $id" }
        $c5RawPath = [string]$c5Row.raw_path
        $c5RawSha = [string]$c5Row.raw_sha256
        $c5StatusPath = [string]$c5Row.run_status_path
        $c5StatusSha = [string]$c5Row.run_status_sha256
        $c5RunStartPath = [string]$c5Row.run_start_path
        $c5RunStartSha = [string]$c5Row.run_start_sha256
        $c5AuditState = [string]$c5Row.status
        $c5AuditScope = 'RAW_PENDING_PARENT_AUDIT'
    }
    Require-Sha $c5RawPath $c5RawSha "$id C5 raw" | Out-Null
    Require-Sha $c5StatusPath $c5StatusSha "$id C5 status" | Out-Null
    Require-Sha $c5RunStartPath $c5RunStartSha "$id C5 run_start" | Out-Null
    $c5Status = Get-Content -Raw $c5StatusPath | ConvertFrom-Json
    $c5TestRead = if ($null -ne $c5Status.TEST_accessed) { [bool]$c5Status.TEST_accessed } elseif ($null -ne $c5Status.TEST_read) { [bool]$c5Status.TEST_read } else { $true }
    if ([string]$c5Status.scene_id -ne $id -or $c5TestRead -or [int]$c5Status.transitions -ne 20000) { throw "C5 status identity/scope mismatch for $id" }

    $reuse = $parentById.ContainsKey($id)
    if ($reuse) {
        $p = $parentById[$id]
        $candRaw = Join-Path $parentRoot ("runs\{0}\raw_run.mat" -f $id)
        $candStatus = Join-Path $parentRoot ("runs\{0}\run_status.json" -f $id)
        $candAudit = Join-Path $parentRoot ("audits\{0}_GRU_STREAM_TRACKING_HEAD_RAW_AUDIT.json" -f $id)
        $rawSha = File-Sha256 $candRaw
        $statusSha = File-Sha256 $candStatus
        $auditSha = File-Sha256 $candAudit
        $runStatus = Get-Content -Raw $candStatus | ConvertFrom-Json
        $auditResult = Get-Content -Raw $candAudit | ConvertFrom-Json
        if ($runStatus.state -ne 'COMPLETED' -or $auditResult.status -ne 'PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY') { throw "Parent candidate raw/audit not PASS for $id" }
        $candStatusText = [string]$runStatus.state
        $candAuditText = [string]$auditResult.status
    } else {
        $candRaw = Join-Path $studyRoot ("runs\{0}\raw_run.mat" -f $id)
        $candStatus = Join-Path $studyRoot ("runs\{0}\run_status.json" -f $id)
        $candAudit = Join-Path $studyRoot ("audits\{0}_GRU_STREAM_TRACKING_HEAD_FULL72_RAW_AUDIT.json" -f $id)
        $rawSha = ''
        $statusSha = ''
        $auditSha = ''
        $candStatusText = 'NOT_STARTED_RELEASE0'
        $candAuditText = 'NOT_STARTED_RELEASE0'
    }
    $parentArraySha = if ($reuse) { [string]$parentById[$id].scene_arrays_sha256 } else { '' }
    $manifestRows.Add([pscustomobject]@{
        scene_id=$id; source_split=[string]$r.source_split; external_identity_sha256=[string]$r.external_identity_sha256
        b_raw_path=[string]$r.b_raw_path; b_raw_sha256=[string]$r.b_raw_sha256; b_status_path=[string]$r.b_status_path; b_status_sha256=[string]$r.b_status_sha256
        c5_raw_path=$c5RawPath; c5_raw_sha256=$c5RawSha; c5_status_path=$c5StatusPath; c5_status_sha256=$c5StatusSha
        c5_run_start_path=$c5RunStartPath; c5_run_start_sha256=$c5RunStartSha; c5_audit_status=$c5AuditState; c5_audit_scope=$c5AuditScope
        payload_path=[string]$r.payload_path; payload_sha256=[string]$r.payload_sha256; transitions=[int]$r.transitions; state_samples=[int]$r.state_samples
        scene_arrays_sha256=$parentArraySha
        candidate_reuse=[bool]$reuse; candidate_raw_path=$candRaw; candidate_raw_sha256=$rawSha; candidate_status_path=$candStatus; candidate_status_sha256=$statusSha; candidate_audit_path=$candAudit; candidate_audit_sha256=$auditSha
        candidate_parent_status=$candStatusText; candidate_parent_audit_status=$candAuditText
    })
    $identityRows.Add([pscustomobject]@{scene_id=$id;split=[string]$r.source_split;external_identity_sha256=[string]$r.external_identity_sha256;payload_path=[string]$r.payload_path;payload_sha256=[string]$r.payload_sha256;b_raw_sha256=[string]$r.b_raw_sha256;b_status_sha256=[string]$r.b_status_sha256;c5_raw_sha256=$c5RawSha;c5_status_sha256=$c5StatusSha;c5_run_start_sha256=$c5RunStartSha;c5_audit_scope=$c5AuditScope;c5_audit_status=$c5AuditState;candidate_reuse=[bool]$reuse;candidate_raw_sha256=$rawSha;candidate_status_sha256=$statusSha;candidate_audit_sha256=$auditSha})
}

if (@($manifestRows | Where-Object candidate_reuse).Count -ne 6 -or @($manifestRows | Where-Object { -not $_.candidate_reuse }).Count -ne 66) { throw 'Expected exactly six reused candidate rows and 66 new rows.' }
$payloadParentSha = File-Sha256 $parentPayloadPath
$manifest = [pscustomobject]@{
    schema='GRU_STREAM_COSINE_TRACKING_HEAD_FULL72_MANIFEST_V1'
    status='PASS_READ_ONLY_VALIDATION_BINDINGS'
    study_id='gru_stream_cosine_tracking_head_full72_v1'
    candidate='GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001'
    base_candidate='GRU32_STREAM72_COSINE_S2026102001'
    direct_parent_study='gru_stream_cosine_tracking_head_dev_v1'
    scene_count=72; dev_scene_count=24; val_scene_count=48; reused_candidate_count=6; new_candidate_scene_count=66
    payload_manifest_path=$payloadPath; payload_manifest_sha256=(File-Sha256 $payloadPath)
    payload_parent_manifest_path=$parentPayloadPath; payload_parent_manifest_sha256=$payloadParentSha
    c5_input_lock_path=$c5LockPath; c5_input_lock_sha256=(File-Sha256 $c5LockPath)
    c5_batch_status_path=$c5BatchPath; c5_batch_status_sha256=(File-Sha256 $c5BatchPath)
    parent_manifest_path=$parentManifestPath; parent_manifest_sha256=(File-Sha256 $parentManifestPath)
    candidate_model_path=[string](Join-Path $repoRoot 'experiments\dl_attitude_replacement_20261026\gru_stream_cosine_c5_teacher_v1\runs\GRU32_STREAM72_COSINE_S2026102001\gru_stream_c5_teacher_weights_v1.mat')
    candidate_model_sha256='b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567'
    TEST_read=$false; Plant_calls=0; training_runs=0
    records=@($manifestRows)
}
$manifestPath = Join-Path $studyRoot 'MANIFEST.json'
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
$report = [pscustomobject]@{
    schema='GRU_STREAM_COSINE_TRACKING_HEAD_FULL72_INPUT_IDENTITY_POWERSHELL_V1'
    created_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    status='PASS_FILE_SHA_AND_SCENE_MAPPING_CHECKS'
    repo_root=$repoRoot
    payload_source_status=[string]$parentPayload.status
    payload_scene_count=72; dev_scene_count=24; val_scene_count=48
    c5_lock_status=[string]$c5Lock.state; c5_reused_count=12; c5_new_count=60; c5_new_pending_parent_audit=60
    candidate_parent_reuse_count=6; candidate_new_scene_count=66
    candidate_parent_raw_all_completed=(@($manifestRows | Where-Object { $_.candidate_reuse -and $_.candidate_parent_status -eq 'COMPLETED' }).Count -eq 6)
    candidate_parent_audits_all_pass=(@($manifestRows | Where-Object { $_.candidate_reuse -and $_.candidate_parent_audit_status -eq 'PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY' }).Count -eq 6)
    test_read=$false; plant_calls=0; training_runs=0
    payload_manifest_sha256=(File-Sha256 $payloadPath); payload_parent_manifest_sha256=$payloadParentSha
    c5_input_lock_sha256=(File-Sha256 $c5LockPath); c5_batch_status_sha256=(File-Sha256 $c5BatchPath)
    parent_candidate_manifest_sha256=(File-Sha256 $parentManifestPath)
    records=@($identityRows)
}
$reportPath = Join-Path $studyRoot 'audits\FULL72_INPUT_IDENTITY_POWERSHELL_v1.json'
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding utf8NoBOM
[pscustomobject]@{manifest_path=$manifestPath;manifest_sha256=(File-Sha256 $manifestPath);identity_report_path=$reportPath;identity_report_sha256=(File-Sha256 $reportPath);scene_count=72;new_candidate_count=66;reused_candidate_count=6;raw_or_checkpoint_copied=0} | ConvertTo-Json -Compress


