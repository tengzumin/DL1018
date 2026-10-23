$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here '../..')).Path
$taskbookPath = Join-Path $root 'reports/paper_continuation_20261023/B_TRACEABLE_DEV72_COMPLETION_TASKBOOK_ZH.md'
$c3LockPath = Join-Path $root 'experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_INPUT_LOCK_v2.json'
$bDir = Join-Path $root 'experiments/b_traceable_c3core_20261023'
$reviewDir = Join-Path $root 'reports/paper_continuation_20261023/baseline_b_probe_review'
$attemptDir = Join-Path $bDir 'runs_b/DL1018_VAL_T2_C00_W10/B_TRACEABLE_C3CORE_V1/attempt_01'
$outContract = Join-Path $here 'B_TRACEABLE_DEV72_RUN_CONTRACT_v2.json'
$outLock = Join-Path $here 'B_TRACEABLE_DEV72_INPUT_LOCK_v2.json'
$preparePath = Join-Path $here 'prepare_b_traceable_dev72_v2.m'
$runnerPath = Join-Path $here 'run_b_traceable_dev72_v2.m'
$prepareCommandPath = Join-Path $here 'RUN_B_DEV72_PREPARE_NOPLANT_EXACT_v2.ps1'
$runCommandPath = Join-Path $here 'RUN_B_TRACEABLE_DEV72_EXACT_v2.ps1'
if ((Test-Path -LiteralPath $outContract) -or (Test-Path -LiteralPath $outLock)) {
    throw 'Refusing to overwrite a frozen contract or input lock.'
}
function Get-FileSha([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-TextSha([string]$Text) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}
function Get-Ref([string]$Path) {
    [ordered]@{ path = $Path; sha256 = (Get-FileSha $Path) }
}
function Read-Json([string]$Path) {
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 100
}
function Assert-Sha([string]$Path, [string]$Expected) {
    if ((Get-FileSha $Path) -ne $Expected.ToLowerInvariant()) { throw "SHA mismatch: $Path" }
}
$expectedC3Lock = 'a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730'
$expectedTaskbook = '39788bbd5e5fa4258f1db9a038be7f75339f11b6148bf1620770791aa3119a63'
$expectedB1Lock = '7c5e1c2979c147b220139a5dfd764394334b61d88b55b2d8abd6ef48edf129d8'
$expectedB1Release = 'ce06cd0d79646b12462ee4887af1af9853f1120a320373a4704ad5ce1c57206e'
$expectedB1Raw = '5a1fffedd408c070a77e3083643a33d9b422a55330ffecc1b6d1ab61b5d48957'
$expectedB1Status = '4de20ba0f17cb0cc498220032626f15b621c8d44dbaab2ea24d3457741a30175'
$expectedB1Review = '01a6b218d8452366084f3af8b5e1382e71aba24591c79eb3a818cdbad1b382f9'
Assert-Sha $taskbookPath $expectedTaskbook
Assert-Sha $c3LockPath $expectedC3Lock
$b1LockPath = Join-Path $bDir 'B_TRACEABLE_INPUT_LOCK_v2.json'
$b1ReleasePath = Join-Path $bDir 'B_TRACEABLE_RELEASE_v2.json'
$b1ContractPath = Join-Path $bDir 'B_TRACEABLE_RUN_CONTRACT_v2.json'
$b1PreparePath = Join-Path $bDir 'B_TRACEABLE_PREPARE_RESULT_v2.json'
$b1SnapshotPath = Join-Path $bDir 'B_TRACEABLE_PREPARED_CFG_OPTS_v2.mat'
$b1BodyPath = Join-Path $bDir 'B_TRACEABLE_BODY_COMPLETE_v2.json'
$b1ExitPath = Join-Path $bDir 'B_TRACEABLE_RUN_EXIT_v2.json'
$b1LedgerPath = Join-Path $bDir 'B_TRACEABLE_EXECUTION_LEDGER_v2.json'
$b1RawReviewPath = Join-Path $reviewDir 'PARENT_B_PROBE_RAW_REVIEW.json'
$b1PrepareReviewPath = Join-Path $reviewDir 'PARENT_B_PROBE_V2_PREPARE_REVIEW.json'
$b1CommandPath = Join-Path $reviewDir 'RUN_B_PROBE_EXACT.ps1'
$b1AttemptRaw = Join-Path $attemptDir 'raw_run.mat'
$b1AttemptStatus = Join-Path $attemptDir 'run_status.json'
$b1RunStart = Join-Path $attemptDir 'run_start.mat'
$b1AttemptMarker = Join-Path $attemptDir 'attempt_started.marker'
$b1PlantMarker = Join-Path $attemptDir 'first_plant_step.marker'
Assert-Sha $b1LockPath $expectedB1Lock
Assert-Sha $b1ReleasePath $expectedB1Release
Assert-Sha $b1AttemptRaw $expectedB1Raw
Assert-Sha $b1AttemptStatus $expectedB1Status
Assert-Sha $b1RawReviewPath $expectedB1Review
Assert-Sha $b1CommandPath '105bdff169cb0ffedee47ee75db76d53eff0dd2f0cbf7efd755125a704d911bd'
$b1Lock = Read-Json $b1LockPath
$b1Release = Read-Json $b1ReleasePath
$b1Prepare = Read-Json $b1PreparePath
$b1Status = Read-Json $b1AttemptStatus
$b1Body = Read-Json $b1BodyPath
$b1Exit = Read-Json $b1ExitPath
$b1Ledger = Read-Json $b1LedgerPath
$b1RawReview = Read-Json $b1RawReviewPath
$b1PrepareReview = Read-Json $b1PrepareReviewPath
if ($b1Status.status -ne 'RUN_COMPLETE_RAW_PENDING_AUDIT' -or $b1Status.log_status -ne 'STABLE' -or
    [int]$b1Status.plant_calls -ne 1 -or [int]$b1Status.last_transition -ne 20000 -or
    [int]$b1Status.state_samples -ne 20001 -or $b1Status.TEST_accessed -ne $false -or
    [int]$b1Status.training_steps -ne 0 -or [int]$b1Status.optimizer_steps -ne 0 -or
    $b1Status.raw_sha256 -ne $expectedB1Raw) { throw 'B1 status does not prove the frozen completed single run.' }
if ($b1Body.status -ne 'RUN_COMPLETE_RAW_PENDING_AUDIT' -or [int]$b1Body.plant_calls -ne 1 -or
    $b1Body.raw_sha256 -ne $expectedB1Raw -or $b1Exit.exit_code -ne 0 -or
    $b1RawReview.status -ne 'PASS_TRACEABLE_B_REPRODUCES_ONE_HISTORICAL_SCENE_EXACTLY' -or
    $b1RawReview.natural_matlab_OS_exit_code -ne 0 -or
    $b1RawReview.historical_72_runtime_tree_gap_closed -ne $false -or
    $b1PrepareReview.active_source_count -ne 32) { throw 'B1 evidence/review binding failed.' }
if (!(Test-Path -LiteralPath $b1AttemptRaw) -or !(Test-Path -LiteralPath $b1RunStart) -or
    !(Test-Path -LiteralPath $b1AttemptMarker) -or !(Test-Path -LiteralPath $b1PlantMarker)) {
    throw 'B1 raw/run_start/markers are incomplete.'
}
$fullArrayGroups = @($b1RawReview.full_numeric_arrays_equal.PSObject.Properties)
if ($fullArrayGroups.Count -ne 33) { throw 'B1 raw review must bind all 33 complete-array groups.' }
foreach ($group in $fullArrayGroups) {
    if ([double]$group.Value.max_abs_difference -ne 0) { throw "B1 full-array mismatch: $($group.Name)" }
}
$c3 = Read-Json $c3LockPath
if ($c3.schema -ne 'C3_DELAYED_PREDICTION_DEV72_INPUT_LOCK_V1' -or @($c3.scenes).Count -ne 72) {
    throw 'Frozen C3 DEV72 lock schema/count changed.'
}
$sceneIdsAll = @($c3.scenes | ForEach-Object { [string]$_.scene_id } | Sort-Object -Unique)
if ($sceneIdsAll.Count -ne 72) { throw 'C3 DEV72 scene IDs are not unique.' }
$completedSceneId = 'DL1018_VAL_T2_C00_W10'
$completedIx = @($c3.scenes | Where-Object { $_.scene_id -eq $completedSceneId })
if ($completedIx.Count -ne 1) { throw 'B1 reference scene must occur once in C3 DEV72.' }
$expectedFields = @(
    'initial_state','time','environment_wind_I','arms/command','arms/rho_true','arms/rhoDot_true',
    'arms/rho_hat','arms/rhoDot_hat','reference/acceleration','reference/position',
    'reference/velocity','reference/yaw','reference/yaw_acceleration','reference/yaw_rate'
)
$newSceneRows = @()
foreach ($row in @($c3.scenes | Sort-Object -Property scene_id)) {
    if ($row.scene_id -eq $completedSceneId) { continue }
    $fields = @($row.b_scene_to_scored_log.matching_fields | ForEach-Object { [string]$_ })
    if ($fields.Count -ne 14 -or ($fields -join '|') -ne ($expectedFields -join '|')) {
        throw "External-input field contract changed for $($row.scene_id)."
    }
    if ($row.B_source.path -ne $row.b_scene_to_scored_log.path -or
        $row.B_source.sha256 -ne $row.b_scene_to_scored_log.sha256 -or
        $row.external_identity_sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "B_source/scored-log identity is inconsistent for $($row.scene_id)."
    }
    if (!(Test-Path -LiteralPath $row.B_source.path -PathType Leaf)) {
        throw "Locked scene source is missing for $($row.scene_id)."
    }
    $newSceneRows += [ordered]@{
        scene_id = [string]$row.scene_id
        source_split = [string]$row.source_split
        task = [string]$row.task
        candidate_action = [string]$row.candidate_action
        B_source = [ordered]@{ path = [string]$row.B_source.path; sha256 = [string]$row.B_source.sha256 }
        scored_log = [ordered]@{
            path = [string]$row.b_scene_to_scored_log.path
            sha256 = [string]$row.b_scene_to_scored_log.sha256
            matching_fields = $fields
        }
        external_identity_sha256 = [string]$row.external_identity_sha256
    }
}
if ($newSceneRows.Count -ne 71) { throw "Expected exactly 71 remaining B scenes, found $($newSceneRows.Count)." }
$sceneIds = @($newSceneRows | ForEach-Object { [string]$_.scene_id })
if (($sceneIds -join '|') -ne ((@($sceneIds | Sort-Object)) -join '|')) { throw 'Remaining B scene IDs are not canonical sorted order.' }
if ($sceneIds -contains $completedSceneId -or $sceneIds -contains 'DL1018_TEST_T1_C00_W00') {
    throw 'The completed B1 scene or a TEST scene entered the 71-scene batch.'
}
$sceneIdsSha = Get-TextSha ($sceneIds -join '|')
$activeSources = @($b1Lock.active_source_inventory)
if ($activeSources.Count -ne 32) { throw 'The reviewed B1 active runtime inventory is not 32 items.' }
$matCount = @($activeSources | Where-Object { ([IO.Path]::GetExtension($_.path)).Equals('.m',[StringComparison]::OrdinalIgnoreCase) }).Count
$matDataCount = @($activeSources | Where-Object { ([IO.Path]::GetExtension($_.path)).Equals('.mat',[StringComparison]::OrdinalIgnoreCase) }).Count
if ($matCount -ne 31 -or $matDataCount -ne 1) { throw 'Expected the exact 31 MATLAB + 1 MAT B1 inventory.' }
foreach ($source in $activeSources) { Assert-Sha $source.path $source.sha256 }
$sourceFiles = [ordered]@{
    prepare_entry = Get-Ref $preparePath
    runner = Get-Ref $runnerPath
    contract = [ordered]@{ path = $outContract; sha256 = '' }
    input_lock_builder = Get-Ref $PSCommandPath
    prepare_command = Get-Ref $prepareCommandPath
    run_command = Get-Ref $runCommandPath
}
$limits = [ordered]@{
    max_new_Plant = 71
    max_output_bytes = 6442450944
    reserve_per_scene_bytes = 80000000
    minimum_free_bytes_after_reserve = 30000000000
    minimum_seconds_per_remaining_scene = 180
    batch_exit_reserve_seconds = 1800
    hard_deadline_utc = '2026-10-24T17:01:00Z'
    transitions = 20000
    state_samples = 20001
    score_horizon_s = 20
    win_tolerance_m = 1e-12
}
$contract = [ordered]@{
    schema = 'B_TRACEABLE_C3CORE_DEV72_CONTRACT_V2'
    state = 'FIXED_71_REMAINING_SCENES_PARENT_RELEASE_REQUIRED_V2'
    completed_reference_scene_id = $completedSceneId
    method = 'B2-RBF-Full-SPLIT'
    collector_tag = 'B_TRACEABLE_C3CORE_V1'
    new_scene_count = 71
    new_scene_ids = $sceneIds
    new_scene_ids_sha256 = $sceneIdsSha
    source_count = 32
    source_matlab_count = 31
    source_mat_count = 1
    training_steps = 0
    optimizer_steps = 0
    TEST_accessed = $false
    parameter_or_seed_search = $false
    controller_options_reconstructed_per_scene = $true
    release_required_before_run = $true
    limits = $limits
}
$contractJson = ConvertTo-Json -InputObject $contract -Depth 100
[IO.File]::WriteAllText($outContract,$contractJson,[Text.UTF8Encoding]::new($false))
$sourceFiles.contract = Get-Ref $outContract
$b1ReviewRef = Get-Ref $b1RawReviewPath
$b1Attempt = [ordered]@{
    scene_id = $completedSceneId
    method = 'B2-RBF-Full-SPLIT'
    collector_tag = 'B_TRACEABLE_C3CORE_V1'
    input_lock = Get-Ref $b1LockPath
    contract = Get-Ref $b1ContractPath
    prepare_result = Get-Ref $b1PreparePath
    cfg_opts_snapshot = Get-Ref $b1SnapshotPath
    release = Get-Ref $b1ReleasePath
    runner_path = $b1Lock.source_files.runner.path
    runner_sha256 = $b1Lock.source_files.runner.sha256
    exact_command = Get-Ref $b1CommandPath
    body_complete = Get-Ref $b1BodyPath
    os_exit = Get-Ref $b1ExitPath
    raw = Get-Ref $b1AttemptRaw
    run_status = Get-Ref $b1AttemptStatus
    run_start = Get-Ref $b1RunStart
    attempt_started_marker = Get-Ref $b1AttemptMarker
    first_plant_step_marker = Get-Ref $b1PlantMarker
    execution_ledger = Get-Ref $b1LedgerPath
    parent_prepare_review = Get-Ref $b1PrepareReviewPath
    parent_raw_root_review = $b1ReviewRef
    raw_sha256 = $expectedB1Raw
    run_status_sha256 = $expectedB1Status
    parent_raw_review_status = [string]$b1RawReview.status
    parent_raw_review_sha256 = $b1ReviewRef.sha256
    full_numeric_array_groups = 33
    full_numeric_arrays_max_abs_difference = 0
    natural_matlab_os_exit_code = 0
    historical_72_runtime_tree_gap_closed = $false
}
$upstream = [ordered]@{
    taskbook = Get-Ref $taskbookPath
    c3_dev72_input_lock = Get-Ref $c3LockPath
    b1_input_lock = Get-Ref $b1LockPath
    b1_release = Get-Ref $b1ReleasePath
    b1_prepare_result = Get-Ref $b1PreparePath
    b1_snapshot = Get-Ref $b1SnapshotPath
    b1_raw = Get-Ref $b1AttemptRaw
    b1_run_status = Get-Ref $b1AttemptStatus
    b1_run_start = Get-Ref $b1RunStart
    b1_first_plant_marker = Get-Ref $b1PlantMarker
    b1_run_exit = Get-Ref $b1ExitPath
    b1_execution_ledger = Get-Ref $b1LedgerPath
    b1_parent_prepare_review = Get-Ref $b1PrepareReviewPath
    b1_parent_raw_root_review = $b1ReviewRef
    authorization = $b1Lock.upstream_refs.authorization
    shared_heavy_job_lock = [ordered]@{ path = $b1Lock.shared_heavy_job_lock_path; sha256 = (Get-FileSha $b1Lock.shared_heavy_job_lock_path) }
    c3_prepared_snapshot = $b1Lock.upstream_refs.c3_dev72_prepared_snapshot
    c3_prepare_result = $b1Lock.upstream_refs.c3_dev72_prepare_result
}
$lock = [ordered]@{
    schema = 'B_TRACEABLE_C3CORE_DEV72_INPUT_LOCK_V2'
    state = 'LOCKED_DEV72_WITH_B1_REUSED_NO_PLANT_PARENT_REVIEW_REQUIRED_V2'
    created_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    repo_root = $root
    plant_authorized_by_this_lock = $false
    completed_reference = $b1Attempt
    completed_reference_scene_id = $completedSceneId
    total_scene_count = 72
    new_scene_count = 71
    new_scene_ids = $sceneIds
    new_scene_ids_sha256 = $sceneIdsSha
    source_counts = [ordered]@{ total = 32; matlab = 31; mat = 1 }
    active_source_inventory = $activeSources
    source_files = $sourceFiles
    upstream_refs = $upstream
    shared_heavy_job_lock_path = $b1Lock.shared_heavy_job_lock_path
    resource_limits = $limits
    historical_72_runtime_tree_gap_closed = $false
    scenes = $newSceneRows
}
$lockJson = ConvertTo-Json -InputObject $lock -Depth 100
[IO.File]::WriteAllText($outLock,$lockJson,[Text.UTF8Encoding]::new($false))
$built = Read-Json $outLock
if ($built.scenes.Count -ne 71 -or $built.new_scene_ids_sha256 -ne $sceneIdsSha -or
    $built.active_source_inventory.Count -ne 32 -or $built.plant_authorized_by_this_lock -ne $false) {
    throw 'New B DEV72 lock self-check failed.'
}
[pscustomobject]@{
    status = 'LOCK_BUILT_NO_PLANT_RELEASE'
    lock_path = $outLock
    lock_sha256 = Get-FileSha $outLock
    contract_path = $outContract
    contract_sha256 = Get-FileSha $outContract
    scene_count = $built.scenes.Count
    first_new_scene_id = $built.new_scene_ids[0]
    last_new_scene_id = $built.new_scene_ids[-1]
    scene_ids_sha256 = $sceneIdsSha
    active_source_count = $built.active_source_inventory.Count
    B1_raw_sha256 = $built.completed_reference.raw_sha256
    B1_parent_raw_review_status = $built.completed_reference.parent_raw_review_status
    plant_authorized = $false
} | ConvertTo-Json -Depth 5

