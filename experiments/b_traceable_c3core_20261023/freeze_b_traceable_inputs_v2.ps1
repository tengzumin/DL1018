$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false)
$here = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $here)
$c3Dir = Join-Path $repoRoot 'experiments/position_delayed_prediction_c3_dev72_20261023'
$reportDir = Join-Path $repoRoot 'reports/paper_continuation_20261023'
$lockPath = Join-Path $here 'B_TRACEABLE_INPUT_LOCK_v2.json'
if (Test-Path -LiteralPath $lockPath) { throw "Refusing to overwrite $lockPath" }
function Get-Sha([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function New-Ref([string]$Path) { [ordered]@{ path = [IO.Path]::GetFullPath($Path); sha256 = (Get-Sha $Path) } }
function Assert-Ref($Ref) {
    if ((Get-Sha ([string]$Ref.path)) -ne ([string]$Ref.sha256).ToLowerInvariant()) { throw "SHA mismatch: $($Ref.path)" }
}
$c3LockPath = Join-Path $c3Dir 'C3_DEV72_INPUT_LOCK_v2.json'
$c3LockSha = 'a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730'
if ((Get-Sha $c3LockPath) -ne $c3LockSha) { throw 'C3 DEV72 input lock SHA changed.' }
$c3 = Get-Content -LiteralPath $c3LockPath -Raw | ConvertFrom-Json -Depth 100
$targetId = 'DL1018_VAL_T2_C00_W10'
$row = @($c3.scenes | Where-Object { $_.scene_id -ceq $targetId })
if ($row.Count -ne 1 -or $row[0].candidate_action -ne 'REUSE_C3_SCREEN') { throw 'Fixed B scene row is absent or ambiguous.' }
$row = $row[0]
if ($row.B_source.path -cne $row.b_scene_to_scored_log.path -or $row.B_source.sha256 -cne $row.b_scene_to_scored_log.sha256 -or $row.b_scene_to_scored_log.matching_fields.Count -ne 14) { throw 'B source does not match the frozen scored-log physical binding.' }
if ((Get-Sha $row.B_source.path) -ne $row.B_source.sha256.ToLowerInvariant()) { throw 'B raw SHA differs from the frozen DEV72 lock.' }
$c3Refs = [ordered]@{}
foreach ($name in @('c3_source_lock','c3_run_contract','c3_prepare_result','c3_snapshot','c3_probe_release','c3_continue_release_v2','c3_continue_progress','c3_probe_raw_audit')) {
    $ref = $c3.c3_reference_refs.$name
    Assert-Ref $ref
    $c3Refs[$name] = [ordered]@{ path=$ref.path; sha256=([string]$ref.sha256).ToLowerInvariant() }
}
$c3SourceLock = Get-Content -LiteralPath $c3.c3_reference_refs.c3_source_lock.path -Raw | ConvertFrom-Json -Depth 100
$dev72PreparePath = Join-Path $c3Dir 'C3_DEV72_PREPARE_RESULT_v2.json'
$dev72SnapshotPath = Join-Path $c3Dir 'C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat'
$dev72RunnerPath = Join-Path $c3Dir 'run_c3_dev72_v2.m'
$dev72ContractPath = Join-Path $c3Dir 'C3_DEV72_RUN_CONTRACT_v2.json'
$dev72Prepare = Get-Content -LiteralPath $dev72PreparePath -Raw | ConvertFrom-Json -Depth 30
if ($dev72Prepare.status -ne 'PREPARED_NO_PLANT_WAIT_PARENT_RELEASE' -or $dev72Prepare.plant_calls -ne 0 -or $dev72Prepare.run_episode_called -ne $false -or $dev72Prepare.TEST_accessed -ne $false) { throw 'C3 DEV72 no-Plant prepare evidence is not valid.' }
if ((Get-Sha $dev72SnapshotPath) -ne $dev72Prepare.snapshot_sha256.ToLowerInvariant()) { throw 'C3 DEV72 prepared snapshot SHA mismatch.' }
$active = [Collections.Generic.List[object]]::new()
foreach ($item in $c3SourceLock.frozen_runtime_files) {
    $leaf = [IO.Path]::GetFileName([string]$item.path)
    $role = switch -CaseSensitive ($leaf) {
        'run_dl1018_closed_loop.m' { 'runtime_core'; break }
        'run_episode_dl1018.m' { 'episode_wrapper'; break }
        default { $null }
    }
    if ($null -ne $role) {
        $isolated = @($c3.source_files.isolated_c3_sources | Where-Object role -eq $role)
        if ($isolated.Count -ne 1) { throw "Expected exactly one isolated source for $role" }
        $active.Add([ordered]@{ role=$role; path=$isolated[0].path; sha256=$isolated[0].sha256.ToLowerInvariant() })
    } else {
        $active.Add([ordered]@{ role='frozen_runtime'; path=$item.path; sha256=([string]$item.sha256).ToLowerInvariant() })
    }
}
$helper = @($c3.source_files.isolated_c3_sources | Where-Object role -eq 'prediction_helper')
if ($helper.Count -ne 1) { throw 'Expected exactly one frozen C3 helper.' }
$active.Add([ordered]@{ role='prediction_helper'; path=$helper[0].path; sha256=$helper[0].sha256.ToLowerInvariant() })
foreach ($item in $c3SourceLock.frozen_plant_files) { $active.Add([ordered]@{ role='frozen_plant'; path=$item.path; sha256=([string]$item.sha256).ToLowerInvariant() }) }
if ($active.Count -ne 32) { throw "Expected 32 active C3 sources; got $($active.Count)." }
$matCount = @($active | Where-Object { [IO.Path]::GetExtension($_.path) -ieq '.mat' }).Count
$mCount = @($active | Where-Object { [IO.Path]::GetExtension($_.path) -ieq '.m' }).Count
if ($matCount -ne 1 -or $mCount -ne 31) { throw "Expected 31 .m and 1 MAT; got $mCount/$matCount." }
$baseNames = @($active | ForEach-Object { [IO.Path]::GetFileName($_.path) })
if (($baseNames | Sort-Object -Unique).Count -ne 32) { throw 'Active source basenames are not unique.' }
foreach ($item in $active) { if ((Get-Sha $item.path) -ne ([string]$item.sha256).ToLowerInvariant()) { throw "Active source SHA mismatch: $($item.path)" } }
$authPath = Join-Path $reportDir 'USER_CONTINUATION_AUTHORIZATION.json'
$taskbookPath = Join-Path $reportDir 'B_TRACEABLE_PROBE_TASKBOOK_ZH.md'
$auth = Get-Content -LiteralPath $authPath -Raw | ConvertFrom-Json -Depth 20
if ($auth.status -ne 'USER_AUTHORIZED_NECESSARY_ADDITIONAL_SORTIES_AND_NEW_ARCHITECTURES_WITHOUT_REPEATED_CONFIRMATION' -or $auth.new_training -eq $true -or $auth.original_deadline_utc.ToString('yyyy-MM-ddTHH:mm:ssZ') -ne '2026-10-24T17:01:00Z' -or $auth.minimum_free_bytes -ne 30000000000) { throw 'Continuation authorization does not preserve one-scene/no-training/deadline constraints.' }
$c1ReleasePath = $c3SourceLock.c1_release.path
if ((Get-Sha $c1ReleasePath) -ne ([string]$c3SourceLock.c1_release.sha256).ToLowerInvariant()) { throw 'C1 release SHA mismatch.' }
$c1Release = Get-Content -LiteralPath $c1ReleasePath -Raw | ConvertFrom-Json -Depth 20
$sharedLockPath = [IO.Path]::GetFullPath([string]$c1Release.shared_heavy_job_lock_path)
if (-not (Test-Path -LiteralPath $sharedLockPath -PathType Leaf)) { throw 'Shared heavy-job lock file missing.' }
$contractPath = Join-Path $here 'B_TRACEABLE_RUN_CONTRACT_v2.json'
$preparePath = Join-Path $here 'prepare_b_traceable_probe_v2.m'
$runnerPath = Join-Path $here 'run_b_traceable_probe_v2.m'
$builderPath = Join-Path $here 'freeze_b_traceable_inputs_v2.ps1'
foreach ($path in @($contractPath,$preparePath,$runnerPath,$builderPath)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required entry missing: $path" } }
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json -Depth 20
if ($contract.scene_id -ne $targetId -or $contract.limits.max_new_Plant -ne 1 -or $contract.limits.max_output_bytes -ne 134217728 -or $contract.limits.minimum_free_bytes -ne 30000000000 -or $contract.limits.hard_deadline_utc -ne $auth.original_deadline_utc) { throw 'B contract differs from fixed task scope.' }
$sourceFiles = [ordered]@{
    runner = New-Ref $runnerPath
    prepare_entry = New-Ref $preparePath
    contract = New-Ref $contractPath
    input_lock_builder = New-Ref $builderPath
}
$failurePath = Join-Path $here 'B_TRACEABLE_PREPARE_FAILURE_01.json'
$refs = [ordered]@{
    authorization = New-Ref $authPath
    taskbook = New-Ref $taskbookPath
    c3_dev72_input_lock = New-Ref $c3LockPath
    c3_dev72_prepare_result = New-Ref $dev72PreparePath
    c3_dev72_prepared_snapshot = New-Ref $dev72SnapshotPath
    c3_dev72_runner = New-Ref $dev72RunnerPath
    c3_dev72_contract = New-Ref $dev72ContractPath
    c3_source_lock = New-Ref $c3.c3_reference_refs.c3_source_lock.path
    c3_source_lock_contract = New-Ref $c3.c3_reference_refs.c3_run_contract.path
    c1_release = New-Ref $c1ReleasePath
    b_scene_payload_review = New-Ref $c3.historical_review_refs.b_scene_payload_review.path
    effective_config = New-Ref (($c3.shared_input_files | Where-Object role -eq 'effective_config_mat').path)
    b_source = New-Ref $row.B_source.path
    previous_prepare_failure = New-Ref $failurePath
}
foreach ($name in @('authorization','taskbook','c3_dev72_input_lock','c3_dev72_prepare_result','c3_dev72_prepared_snapshot','c3_dev72_runner','c3_dev72_contract','c3_source_lock','c3_source_lock_contract','c1_release','b_scene_payload_review','effective_config','b_source','previous_prepare_failure')) { Assert-Ref $refs[$name] }
$lock = [ordered]@{
    schema='B_TRACEABLE_C3CORE_INPUT_LOCK_V2'; state='LOCKED_SINGLE_SCENE_NO_PLANT_PARENT_REVIEW_REQUIRED_V2'; plant_authorized_by_this_lock=$false
    created_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); repo_root=$repoRoot
    scene_id=$targetId; scene_raw_path=[IO.Path]::GetFullPath([string]$row.B_source.path); scene_raw_sha256=([string]$row.B_source.sha256).ToLowerInvariant()
    scene_external_identity_sha256=([string]$row.external_identity_sha256).ToLowerInvariant(); scene_scored_log_path=$row.b_scene_to_scored_log.path
    scene_scored_log_sha256=([string]$row.b_scene_to_scored_log.sha256).ToLowerInvariant(); scene_matching_fields=@($row.b_scene_to_scored_log.matching_fields)
    runtime_method='B2-RBF-Full-SPLIT'; collector_tag='B_TRACEABLE_C3CORE_V1'; expected_transitions=20000; expected_time_samples=20001
    no_training=$true; no_optimizer=$true; no_search=$true; TEST_accessed=$false
    c3_source_lock=$c3Refs.c3_source_lock; shared_heavy_job_lock_path=$sharedLockPath; source_files=$sourceFiles; upstream_refs=$refs
    active_source_inventory=@($active); source_counts=[ordered]@{total=$active.Count; matlab=$mCount; mat=$matCount}
    resource_limits=[ordered]@{max_output_bytes=134217728;minimum_free_bytes=30000000000;hard_deadline_utc=$auth.original_deadline_utc}
    no_plant_entry=[IO.Path]::GetFullPath($preparePath); plant_entry=[IO.Path]::GetFullPath($runnerPath); expected_outputs=@('B_TRACEABLE_PREPARE_RESULT_v2.json','B_TRACEABLE_PREPARED_CFG_OPTS_v2.mat','runs_b/DL1018_VAL_T2_C00_W10/B_TRACEABLE_C3CORE_V1/attempt_01')
}
$json = $lock | ConvertTo-Json -Depth 60 -Compress
[IO.File]::WriteAllText($lockPath,$json,$utf8)
$actual = Get-Sha $lockPath
Write-Output "B_TRACEABLE_INPUT_LOCK=$lockPath"
Write-Output "B_TRACEABLE_INPUT_LOCK_SHA256=$actual"
Write-Output "SOURCES=$($active.Count) (.m=$mCount, MAT=$matCount); B_raw=$($lock.scene_raw_sha256)"