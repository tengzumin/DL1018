Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
$entry = $PSScriptRoot
$candidatePath = Join-Path $entry 'source_lock_morph_dev2_dev58_candidate.json'
$reviewPath = Join-Path $entry 'review\ROOT_REVIEW_DEV58_PRE_RUN.md'
$frozenPath = Join-Path $entry 'SOURCE_LOCK_MORPH_DEV2_DEV58_V1_FROZEN.json'
$releasePath = Join-Path $entry 'ROOT_RELEASE_MORPH_DEV2_DEV58_v1.json'
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf) -or -not (Test-Path -LiteralPath $reviewPath -PathType Leaf)) {
    throw 'Candidate source lock and root review must exist first.'
}
if ((Test-Path -LiteralPath $frozenPath) -or (Test-Path -LiteralPath $releasePath)) { throw 'Frozen lock/release already exists; refusing overwrite.' }
$lock = Get-Content -Raw -LiteralPath $candidatePath | ConvertFrom-Json
$reviewText = Get-Content -Raw -LiteralPath $reviewPath
if ($lock.schema -ne 'SOURCE_LOCK_MORPH_DEV2_DEV58_V1' -or $lock.status -ne 'NOT_FROZEN' -or
    $lock.executed -ne $false -or $lock.closed_loop_runs_authorized -ne $false -or
    $lock.root_approval_status -ne 'PENDING' -or $lock.root_release_issued -ne $false -or
    @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 11 -or
    @($lock.diagnostic_scenes).Count -ne 58 -or @($lock.reused_candidate_raws).Count -ne 14 -or
    $reviewText -notmatch 'ROOT_REVIEW_APPROVED_TO_RUN_DEV58') { throw 'Root review/lock gate failed.' }
foreach ($record in @($lock.sources)+@($lock.inputs)+@($lock.scene_inputs)+@(
        $lock.wrapper,$lock.launcher,$lock.checker,$lock.taskbook,$lock.state,$lock.scene_builder,
        $lock.manifest_generator,$lock.builder,$lock.addendum,$lock.lineage_review,$lock.release_builder,
        $lock.root_review,$lock.manifest,$lock.reference_screen12_source_lock)) {
    if ((Get-Sha ([string]$record.path)) -ne ([string]$record.sha256).ToLowerInvariant()) { throw "Root-reviewed input changed: $($record.path)" }
}
foreach ($record in $lock.reused_candidate_raws) {
    if ((Get-Sha $record.raw_path) -ne $record.raw_sha256.ToLowerInvariant() -or
        (Get-Sha $record.status_path) -ne $record.status_sha256.ToLowerInvariant()) { throw "Reused candidate changed: $($record.scene_id)" }
    if ($record.review_path -and (Get-Sha $record.review_path) -ne $record.review_sha256.ToLowerInvariant()) { throw "Reuse review changed: $($record.scene_id)" }
}

$lock.status = 'FROZEN_INPUTS'
$lock.root_approval_status = 'APPROVED'
$lock.root_release_issued = $true
$lock.closed_loop_runs_authorized = $false
$lock.executed = $false
$frozenText = (ConvertTo-Json -InputObject $lock -Depth 15) + "`n"
[IO.File]::WriteAllText($frozenPath,$frozenText,[Text.UTF8Encoding]::new($false))
$frozenSha = Get-Sha $frozenPath
$attemptId = 'DEV58_PHYATT_B72_20261025_A01'
$release = [ordered]@{
    schema = 'PAIRED_MORPH_DEV2_DEV58_ROOT_RELEASE_V1'; approved = $true; scope = 'MORPH_DEV2_DEV58'
    approver = 'root_codex'; created_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    attempt_id = $attemptId; source_lock_path = (Resolve-Path -LiteralPath $frozenPath).Path
    source_lock_sha256 = $frozenSha; manifest_sha256 = [string]$lock.manifest.sha256
    root_review_path = (Resolve-Path -LiteralPath $reviewPath).Path; root_review_sha256 = Get-Sha $reviewPath
    max_runner_calls = 58; max_transitions = 1160000; no_fixed_output_cap = $true
    minimum_free_bytes = 32212254720; training_authorized = $false; TEST_authorized = $false
    retry_authorized = $false; comparator = 'B_TRACEABLE_C3CORE_V1'
    scene_ids = @($lock.diagnostic_scenes | ForEach-Object scene_id); arm_order = @('candidate')
    reuse_candidate_count = 14; new_B_runs = 0; new_C5_runs = 0; TEST_accessed = $false
    approval_basis = 'User-authorized continuation; root review passed candidate/B72 identity, raw reuse, source, causal trace, and scope gates.'
}
[IO.File]::WriteAllText($releasePath,(ConvertTo-Json -InputObject $release -Depth 12)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "DEV58_ROOT_RELEASE_ISSUED lock_sha256=$frozenSha release_sha256=$(Get-Sha $releasePath) attempt=$attemptId calls=58 output_cap=none"
