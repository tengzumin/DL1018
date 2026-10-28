Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }

$entry = $PSScriptRoot
$project = (Resolve-Path (Join-Path $entry '..\..\..\..')).Path
$screen = Join-Path $project 'experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_screen12_v1'
$refLockPath = Join-Path $screen 'SOURCE_LOCK_MORPH_DEV2_SCREEN12_v1_FROZEN.json'
$refLock = Get-Content -Raw -LiteralPath $refLockPath | ConvertFrom-Json
$manifestPath = Join-Path $entry 'manifest\DEV58_PREPARED_MANIFEST_B72_V2.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

function Get-Sha([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function New-Record([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing locked file: $Path" }
    [ordered]@{ path = (Resolve-Path -LiteralPath $Path).Path; sha256 = Get-Sha $Path }
}
function New-ReuseRecord([string]$SceneId,[string]$RawPath,[string]$StatusPath,[string]$ReviewPath,[string]$ReviewScope) {
    $status = Get-Content -Raw -LiteralPath $StatusPath | ConvertFrom-Json
    if ($status.scene_id -ne $SceneId -or $status.raw_path -ne $RawPath) { throw "Reuse status identity differs: $SceneId" }
    if ((Get-Sha $RawPath) -ne ([string]$status.raw_sha256).ToLowerInvariant()) { throw "Reuse raw SHA mismatch: $SceneId" }
    if ((Get-Sha $StatusPath) -ne ([string](New-Record $StatusPath).sha256)) { throw "Reuse status SHA mismatch: $SceneId" }
    $review = if ($ReviewPath) { New-Record $ReviewPath } else { [ordered]@{ path = ''; sha256 = '' } }
    [ordered]@{
        scene_id = $SceneId
        raw_path = (Resolve-Path -LiteralPath $RawPath).Path
        raw_sha256 = ([string]$status.raw_sha256).ToLowerInvariant()
        status_path = (Resolve-Path -LiteralPath $StatusPath).Path
        status_sha256 = (Get-Sha $StatusPath)
        original_status = [string]$status.status
        effective_options_sha256 = [string]$status.effective_options_sha256
        review_path = [string]$review.path
        review_sha256 = [string]$review.sha256
        review_scope = $ReviewScope
    }
}

if ($manifest.schema -ne 'MORPH_DEV2_DEV58_PREPARED_MANIFEST_V1' -or $manifest.scenes.Count -ne 58 -or
    $manifest.plant_calls -ne 0 -or $manifest.training_runs -ne 0 -or $manifest.TEST_accessed -ne $false) {
    throw 'No-Plant manifest scope is invalid.'
}
$taskbookPath = Join-Path $entry 'ATTITUDE_PHYS_INERTIA_DEV72_TASKBOOK_v1_ZH.md'
$addendumPath = Join-Path $entry 'DEV58_USER_STEERING_ADDENDUM_20261025.md'
$lineageReviewPath = Join-Path $entry 'review\B72_LINEAGE_INDEPENDENT_REVIEW.md'
$t2ReviewPath = Join-Path $entry 'review\PRIOR_T2_RAW_REUSE_REVIEW_V2.json'
$screenReviewPath = Join-Path $entry 'review\SCREEN12_CANDIDATE_VS_B_RAW.json'
$t3ReviewPath = Join-Path $entry 'review\PRIOR_T3_RAW_REUSE_REVIEW.json'

$sources = @()
foreach ($item in $refLock.sources) {
    $path = Join-Path $entry $item.relative_path
    if ((Get-Sha $path) -ne ([string]$item.sha256).ToLowerInvariant()) { throw "Copied runtime source changed: $($item.relative_path)" }
    $sources += [ordered]@{ relative_path = $item.relative_path; path = (Resolve-Path -LiteralPath $path).Path; sha256 = ([string]$item.sha256).ToLowerInvariant() }
}
if ($sources.Count -ne 39) { throw "Expected 39 inherited MATLAB sources, found $($sources.Count)." }

$inputs = @()
foreach ($property in $manifest.c5.inputs.PSObject.Properties) {
    $record = $property.Value
    if ((Get-Sha $record.path) -ne ([string]$record.sha256).ToLowerInvariant()) { throw "Input SHA mismatch: $($property.Name)" }
    $inputs += [ordered]@{ role = $property.Name; path = [string]$record.path; sha256 = ([string]$record.sha256).ToLowerInvariant() }
}
if ($inputs.Count -ne 11) { throw "Expected 11 relevant frozen inputs, found $($inputs.Count)." }

$reuse = @()
$screenAttempt = Join-Path $screen 'attempts\screen12_phys_att_v1_20261025_01'
foreach ($scene in $manifest.lineage.screen12_reuse_ids) {
    $matches = @(Get-ChildItem -LiteralPath $screenAttempt -Directory | Where-Object Name -like "*_${scene}_candidate")
    if ($matches.Count -ne 1) { throw "Expected one frozen screen12 candidate directory: $scene" }
    $dir = $matches[0].FullName
    $statusPath = Join-Path $dir 'run_status.json'
    $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
    if ($status.status -ne 'COMPLETED_SCREEN12' -or -not $status.engineering_gate.passed -or -not $status.safety_gate.passed -or
        $status.effective_options_sha256 -ne $manifest.c5.candidate_options_sha256) { throw "Screen12 candidate is not reusable: $scene" }
    $reuse += New-ReuseRecord $scene $status.raw_path $statusPath $screenReviewPath 'Independent candidate vs locked B72 rescore for all screen12 scenes.'
}

$t2StatusPath = Join-Path $project 'experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_diagnostic_v1\attempts\MORPH_DEV2_20261025_A02\01_DL1018_DEV_T2_C02_W15_candidate\run_status.json'
$t2Status = Get-Content -Raw -LiteralPath $t2StatusPath | ConvertFrom-Json
$t2Review = Get-Content -Raw -LiteralPath $t2ReviewPath | ConvertFrom-Json
if ($t2Review.status -ne 'PASS_REUSE_AFTER_INDEPENDENT_CAUSAL_REVIEW' -or
    $t2Review.candidate_source_raw_sha256 -ne $t2Status.raw_sha256 -or
    -not $t2Review.causal_observer_trace_passed -or -not $t2Review.attitude_rbf_output_enabled_all_false -or
    -not $t2Review.attitude_rbf_update_enabled_all_false) { throw 'T2 prior raw lacks independent reuse approval.' }
$reuse += New-ReuseRecord 'DL1018_DEV_T2_C02_W15' $t2Status.raw_path $t2StatusPath $t2ReviewPath 'Independent 20,000-step trace review; original FAILED_ENGINEERING status retained.'

$t3StatusPath = Join-Path $project 'experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_t3_continuation_v1\attempts\MORPH_DEV2_T3_CONT_20261025_A01\01_DL1018_DEV_T3_C10_W11_candidate\run_status.json'
$t3Status = Get-Content -Raw -LiteralPath $t3StatusPath | ConvertFrom-Json
$t3Review = Get-Content -Raw -LiteralPath $t3ReviewPath | ConvertFrom-Json
if ($t3Status.status -ne 'COMPLETED_T3_CONTINUATION' -or -not $t3Status.engineering_gate.passed -or
    -not $t3Status.safety_gate.passed -or $t3Status.effective_options_sha256 -ne $manifest.c5.candidate_options_sha256 -or
    $t3Review.status -ne 'PASS_REUSE_AFTER_INDEPENDENT_CAUSAL_REVIEW' -or
    $t3Review.candidate_raw_sha256 -ne $t3Status.raw_sha256 -or -not $t3Review.observer_causal_trace_passed) {
    throw 'T3 prior raw is not a completed candidate with the frozen options.'
}
$reuse += New-ReuseRecord 'DL1018_DEV_T3_C10_W11' $t3Status.raw_path $t3StatusPath $t3ReviewPath 'Independent candidate trace audit and locked B72 raw rescore.'
if ($reuse.Count -ne 14 -or @($reuse.scene_id | Select-Object -Unique).Count -ne 14) { throw 'Exactly 14 unique prior candidate raws are required.' }

$diag = @($manifest.scenes | ForEach-Object { [ordered]@{ scene_id = $_.scene_id; seed = [long]$_.seed; spec_sha256 = $_.spec_sha256; scene_sha256 = $_.scene_sha256; metadata_sha256 = $_.metadata_sha256 } })
$sceneCsv = New-Record (Join-Path $entry 'configs\scene_specs_dev58.csv')
$sceneReceipt = New-Record (Join-Path $entry 'configs\scene_specs_dev58_receipt.json')
$candidate = [ordered]@{
    schema = 'SOURCE_LOCK_MORPH_DEV2_DEV58_V1'; scope = 'MORPH_DEV2_DEV58'; status = 'NOT_FROZEN'
    executed = $false; closed_loop_runs_authorized = $false; training_authorized = $false; TEST_authorized = $false
    root_approval_status = 'PENDING'; root_release_issued = $false; created_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    reference_screen12_source_lock = New-Record $refLockPath
    sources = $sources; inputs = $inputs; reused_candidate_raws = $reuse; diagnostic_scenes = $diag
    scene_inputs = @($sceneCsv,$sceneReceipt)
    manifest = New-Record $manifestPath
    taskbook = New-Record $taskbookPath; addendum = New-Record $addendumPath; lineage_review = New-Record $lineageReviewPath
    wrapper = New-Record (Join-Path $entry 'run_morph_dev2_dev58.m')
    launcher = New-Record (Join-Path $entry 'launch_morph_dev2_dev58.ps1')
    checker = New-Record (Join-Path $entry 'static_check_morph_dev2_dev58.ps1')
    state = New-Record (Join-Path $entry 'STATE_ZH.md')
    scene_builder = New-Record (Join-Path $entry 'matlab\scenes\make_paired_dev58_scene.m')
    manifest_generator = New-Record (Join-Path $entry 'prepare_manifest_no_plant.m')
    builder = New-Record (Join-Path $entry 'build_candidate_lock_dev58.ps1')
    release_builder = New-Record (Join-Path $entry 'issue_root_release_dev58.ps1')
    root_review = New-Record (Join-Path $entry 'review\ROOT_REVIEW_DEV58_PRE_RUN.md')
    lineage = $manifest.lineage
    release_contract = [ordered]@{
        schema = 'PAIRED_MORPH_DEV2_DEV58_ROOT_RELEASE_V1'; approval_required_by_root = $true; scope = 'MORPH_DEV2_DEV58'
        max_runner_calls = 58; max_transitions = 1160000; no_fixed_output_cap = $true; minimum_free_bytes = 32212254720
        training_authorized = $false; TEST_authorized = $false; retry_authorized = $false
        scene_ids = @($diag | ForEach-Object scene_id); arm_order = @('candidate'); comparator = 'B_TRACEABLE_C3CORE_V1'
        all_72_B_raw_reused = $true; prior_candidate_raws_reused = 14
    }
    limits = 'Candidate lock only. No Plant calls authorized until root freezes this lock and signs a separate release.'
}
$out = Join-Path $entry 'source_lock_morph_dev2_dev58_candidate.json'
if (Test-Path -LiteralPath $out) { throw 'Candidate lock already exists; refusing overwrite.' }
[IO.File]::WriteAllText($out,(ConvertTo-Json -InputObject $candidate -Depth 15)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "DEV58_CANDIDATE_LOCK_WRITTEN path=$out sha256=$(Get-Sha $out) scenes=$($diag.Count) sources=$($sources.Count) inputs=$($inputs.Count) reuse=$($reuse.Count)"
