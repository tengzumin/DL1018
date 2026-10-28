[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CampaignReleasePath,
    [Parameter(Mandatory)][string]$ExpectedCampaignReleaseSha256,
    [Parameter(Mandatory)][string]$FirstAuditPath,
    [Parameter(Mandatory)][string]$ExpectedFirstAuditSha256,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$ReportDir = Join-Path $RepoRoot 'reports/attitude_position_context_probe_20261024/c5_matched_train24_v1'
$ExperimentDir = Join-Path $RepoRoot 'experiments/attitude_position_context_probe_20261024/c5_matched_train24_v1'
$TaskbookPath = Join-Path $RepoRoot 'reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json'
$SourceManifestPath = Join-Path $RepoRoot 'reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json'
$PreparePath = Join-Path $ReportDir 'PREPARED_C5_MATCHED_TRAIN24_v1.json'
$RunnerPath = Join-Path $ExperimentDir 'run_c5_matched_train24_v1.m'
$PrepareSourcePath = Join-Path $ExperimentDir 'prepare_c5_matched_train24_v1.m'
$ExporterPath = Join-Path $ExperimentDir 'export_c5_matched_train24_scene_v1.m'
$FirstReleasePath = Join-Path $ReportDir 'releases/ROOT_C5_MATCHED_TRAIN24_RELEASE_DL1018_TRAIN_T1_C00_W00_v1.json'
$MatlabPath = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
$RunnerFunction = 'run_c5_matched_train24_v1'
$ExporterFunction = 'export_c5_matched_train24_scene_v1'
$CampaignSchema = 'C5_MATCHED_TRAIN24_REMAINING23_RELEASE_V1'
$FirstAuditSchema = 'ROOT_FIRST_CSTAR_EXPORT_INDEPENDENT_AUDIT_V1'
$ExpectedTaskbookSha256 = '88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b'
$ExpectedSourceManifestSha256 = '0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5'
$ExpectedPrepareSha256 = 'F520ECC31753DE0FE08B746CAFC5F61C449CCECD997139046458A5EFB655E723'
$ExpectedRunnerSha256 = 'B8047D648AB6CD0C7B922042633AC794229B3297C689E1BF8A76FC926484DCB4'
$ExpectedExporterSha256 = '8b77f32b80e82291c3d1ab4ce0bc60f5719c2b97801094a52dc275049fb54861'
$FirstAuditorPath = Join-Path $RepoRoot 'reports/attitude_cm18_datarepair_20261024/root_first_train24_cstar_audit_v1.py'
$ExpectedFirstAuditorSha256 = 'dcf750d7cb7e075d7f196fb79dac200707d6a6556b6d876bef14b9263b67b3f4'
$MinimumFreeBytes = [int64](30GB)
$OutputBudgetBytes = [int64](2GB)
$FirstSceneId = 'DL1018_TRAIN_T1_C00_W00'

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label file is missing: $Path" }
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "$Label SHA mismatch: expected $Expected, got $actual" }
    return $actual
}
function Get-FileBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [int64]0 }
    if ((Get-Item -LiteralPath $Path).PSIsContainer) {
        $sum = [int64]0
        Get-ChildItem -LiteralPath $Path -Recurse -File | ForEach-Object { $sum += $_.Length }
        return $sum
    }
    return [int64](Get-Item -LiteralPath $Path).Length
}
function Assert-Resources {
    $driveRoot = [IO.Path]::GetPathRoot($RepoRoot)
    $drive = [IO.DriveInfo]::new($driveRoot)
    if ($drive.AvailableFreeSpace -lt $MinimumFreeBytes) { throw "Free-space floor violated: $($drive.AvailableFreeSpace) bytes available." }
    $used = Get-FileBytes $ReportDir
    if ($used -ge $OutputBudgetBytes) { throw "C5 output budget exhausted: $used bytes used." }
}
function Write-NewUtf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) { [void](New-Item -ItemType Directory -Path $parent) }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Text)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function Add-Ledger([string]$Path, [hashtable]$Record) {
    $line = ConvertTo-Json -InputObject $Record -Depth 20 -Compress
    [IO.File]::AppendAllText($Path, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}
function Resolve-InputPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}
function Matlab-Quote([string]$Value) {
    "'" + $Value.Replace("'", "''") + "'"
}
function Invoke-Matlab([string]$Batch, [string]$LogPath) {
    if (Test-Path -LiteralPath $LogPath) { throw "Refusing to overwrite MATLAB log: $LogPath" }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    & $MatlabPath -batch $Batch *> $LogPath
    $exit = $LASTEXITCODE
    $timer.Stop()
    return @{ exit_code = [int]$exit; elapsed_seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 3); log_path = $LogPath }
}
function Assert-Json([string]$Path, [string]$ExpectedSha, [string]$Label) {
    [void](Assert-Sha256 $Path $ExpectedSha $Label)
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
}
function Assert-SceneRows($Campaign, $Prepared) {
    if (-not ($Campaign.scene_rows -is [System.Collections.IEnumerable]) -or $Campaign.scene_rows.Count -ne 23) {
        throw 'Campaign scene_rows must contain exactly the remaining 23 approved scenes.'
    }
    $preparedRows = @($Prepared.scene_rows)
    for ($seq = 2; $seq -le 24; $seq++) {
        $row = $Campaign.scene_rows[$seq - 2]
        $source = $preparedRows[$seq - 1]
        if ([int]$row.sequence_index -ne $seq -or $row.canonical_scene_id -ne $source.canonical_scene_id -or
            $row.source_runtime_scene_id -ne $source.source_runtime_scene_id -or
            $row.snapshot_sha256.ToLowerInvariant() -ne $Prepared.snapshot_rows[$seq - 1].sha256.ToLowerInvariant() -or
            $row.raw_sha256.ToLowerInvariant() -ne $source.raw_sha256.ToLowerInvariant() -or
            $row.run_start_sha256.ToLowerInvariant() -ne $source.run_start_sha256.ToLowerInvariant()) {
            throw "Campaign row $seq does not exactly bind the prepared scene/source/snapshot identity."
        }
    }
}

if (-not $Execute) {
    Write-Output 'Source loaded; no validation, release creation, MATLAB, or filesystem mutation was performed. Pass -Execute only after Root review and an approved campaign release.'
    return
}

if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 or newer is required.' }
if (-not (Test-Path -LiteralPath $MatlabPath -PathType Leaf)) { throw "Pinned MATLAB executable is missing: $MatlabPath" }
$campaignPath = Resolve-InputPath $CampaignReleasePath
$auditPath = Resolve-InputPath $FirstAuditPath
$CampaignSha = $ExpectedCampaignReleaseSha256.ToLowerInvariant()
$FirstAuditSha = $ExpectedFirstAuditSha256.ToLowerInvariant()
if ($CampaignSha -notmatch '^[0-9a-f]{64}$' -or $FirstAuditSha -notmatch '^[0-9a-f]{64}$') { throw 'Expected release/audit SHA must be 64 hexadecimal characters.' }
$Campaign = Assert-Json $campaignPath $CampaignSha 'Remaining-23 campaign release'
if ($Campaign.schema -ne $CampaignSchema -or $Campaign.decision -ne 'APPROVE_REMAINING_23') { throw 'Campaign schema/decision does not authorize exactly the remaining 23 flights.' }
if ([int]$Campaign.training_steps -ne 0 -or [int]$Campaign.optimizer_steps -ne 0 -or [bool]$Campaign.TEST_accessed) { throw 'Campaign scope must be Plant-only, with zero training/optimizer steps and no TEST access.' }

$Taskbook = Get-Content -LiteralPath $TaskbookPath -Raw | ConvertFrom-Json -AsHashtable
$Prepared = Get-Content -LiteralPath $PreparePath -Raw | ConvertFrom-Json -AsHashtable
$SourceManifestSha = Assert-Sha256 $SourceManifestPath $ExpectedSourceManifestSha256 'Source manifest'
$TaskbookSha = Assert-Sha256 $TaskbookPath $ExpectedTaskbookSha256 'Taskbook'
$PrepareSha = Get-Sha256 $PreparePath
$PrepareSourceSha = Assert-Sha256 $PrepareSourcePath $ExpectedPrepareSha256 'Prepare source'
$RunnerSha = Assert-Sha256 $RunnerPath $ExpectedRunnerSha256 'Runner source'
$ExporterSha = Assert-Sha256 $ExporterPath $ExpectedExporterSha256 'Exporter source'
if ($Prepared.schema -ne 'C5_MATCHED_TRAIN24_PREPARATION_V1' -or $Prepared.status -ne 'PREPARED_NO_PLANT' -or
    $Prepared.scene_rows.Count -ne 24 -or $Prepared.snapshot_rows.Count -ne 24 -or
    $Prepared.source_hashes.prepare_matlab_sha256.ToLowerInvariant() -ne $PrepareSourceSha.ToLowerInvariant() -or
    $Prepared.source_hashes.runner_matlab_sha256.ToLowerInvariant() -ne $RunnerSha.ToLowerInvariant()) {
    throw 'The frozen preparation result or source pins changed.'
}
if ($Campaign.pins.taskbook_sha256.ToLowerInvariant() -ne $TaskbookSha -or
    $Campaign.pins.source_manifest_sha256.ToLowerInvariant() -ne $SourceManifestSha -or
    $Campaign.pins.prepare_result_sha256.ToLowerInvariant() -ne $PrepareSha -or
    $Campaign.pins.prepare_matlab_sha256.ToLowerInvariant() -ne $PrepareSourceSha -or
    $Campaign.pins.runner_matlab_sha256.ToLowerInvariant() -ne $RunnerSha -or
    $Campaign.pins.exporter_matlab_sha256.ToLowerInvariant() -ne $ExporterSha) {
    throw 'Campaign source/data pins do not match the current frozen inputs.'
}
Assert-SceneRows $Campaign $Prepared

$firstAttemptDir = Join-Path $ReportDir "runs/$FirstSceneId/attempt_01"
$firstStatusPath = Join-Path $firstAttemptDir 'run_status.json'
$firstRawPath = Join-Path $firstAttemptDir 'raw_run.mat'
$firstTerminalPath = Join-Path $firstAttemptDir 'terminal.marker'
$firstStatus = Get-Content -LiteralPath $firstStatusPath -Raw | ConvertFrom-Json -AsHashtable
$FirstAuditorSha = Assert-Sha256 $FirstAuditorPath $ExpectedFirstAuditorSha256 'Independent auditor source'
$firstAudit = Assert-Json $auditPath $FirstAuditSha 'Independent first-flight audit'
if ($firstAudit.schema -ne $FirstAuditSchema -or $firstAudit.status -ne 'PASS' -or
    $firstAudit.canonical_scene_id -ne $FirstSceneId -or
    $firstAudit.raw_sha256.ToLowerInvariant() -ne $firstStatus.raw_sha256.ToLowerInvariant() -or
    $firstAudit.exporter_sha256.ToLowerInvariant() -ne $ExporterSha -or
    $firstAudit.source_sha256.ToLowerInvariant() -ne $FirstAuditorSha -or
    [int]$firstAudit.event_count -ne 1999 -or $firstAudit.Plant_calls -ne 0 -or
    $firstAudit.optimizer_steps -ne 0 -or $firstAudit.TEST_accessed -or
    (Resolve-InputPath $Campaign.first_independent_audit.path) -ne $auditPath -or
    $Campaign.first_independent_audit.sha256.ToLowerInvariant() -ne $FirstAuditSha -or
    (Resolve-InputPath $Campaign.first_independent_audit.source_path) -ne [IO.Path]::GetFullPath($FirstAuditorPath) -or
    $Campaign.first_independent_audit.source_sha256.ToLowerInvariant() -ne $FirstAuditorSha) {
    throw 'The independently audited first flight is not PASS or is not bound by this campaign release.'
}
if ($firstStatus.status -ne 'RUN_COMPLETE_STABLE' -or $firstStatus.canonical_scene_id -ne $FirstSceneId -or
    [int]$firstStatus.sequence_index -ne 1 -or [int]$firstStatus.transitions -ne 20000 -or
    [int]$firstStatus.state_samples -ne 20001 -or $firstStatus.plant_calls -ne 1 -or
    $firstStatus.optimizer_steps -ne 0 -or $firstStatus.TEST_accessed -or (Get-Sha256 $firstRawPath) -ne $firstStatus.raw_sha256.ToLowerInvariant() -or
    (Get-Content -LiteralPath $firstTerminalPath -Raw).Trim() -ne 'RUN_COMPLETE_STABLE') {
    throw 'The first flight is not a terminal stable single-flight baseline.'
}
$firstRelease = Get-Content -LiteralPath $FirstReleasePath -Raw | ConvertFrom-Json -AsHashtable
$firstAuditFile = Join-Path $ReportDir "event_exports_v1/$FirstSceneId/${FirstSceneId}_CSTAR_AUDIT_v1.json"
$firstCacheFile = Join-Path $ReportDir "event_exports_v1/$FirstSceneId/${FirstSceneId}_CSTAR_EVENTS_v1.mat"
$firstExportAudit = Get-Content -LiteralPath $firstAuditFile -Raw | ConvertFrom-Json -AsHashtable
if ($firstExportAudit.status -ne 'PASS' -or $firstExportAudit.canonical_scene_id -ne $FirstSceneId -or
    $firstExportAudit.identity.flight_raw_sha256.ToLowerInvariant() -ne $firstStatus.raw_sha256.ToLowerInvariant() -or
    $firstExportAudit.identity.exporter_matlab_sha256.ToLowerInvariant() -ne $ExporterSha -or
    (Get-Sha256 $firstCacheFile) -ne $firstAudit.event_cache_sha256.ToLowerInvariant() -or
    (Get-Sha256 $firstAuditFile) -ne $firstAudit.export_audit_sha256.ToLowerInvariant() -or
    $firstExportAudit.cache_sha256.ToLowerInvariant() -ne (Get-Sha256 $firstCacheFile) -or
    [int64]$firstExportAudit.cache_bytes -ne (Get-Item -LiteralPath $firstCacheFile).Length) {
    throw 'First flight exporter products do not match the independent audit pins.'
}
Assert-Resources

$campaignRunDir = Join-Path $ReportDir ("remaining23_campaign_" + $CampaignSha.Substring(0, 12))
if (Test-Path -LiteralPath $campaignRunDir) { throw "Campaign execution record already exists; refusing to resume or overwrite: $campaignRunDir" }
[void](New-Item -ItemType Directory -Path $campaignRunDir)
$ledgerPath = Join-Path $campaignRunDir 'execution_ledger.jsonl'
Write-NewUtf8 $ledgerPath ''
Add-Ledger $ledgerPath @{ stage = 'CAMPAIGN_START'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); campaign_sha256 = $CampaignSha; first_audit_sha256 = $FirstAuditSha; scope = 'sequence_index_2_to_24'; training_steps = 0; optimizer_steps = 0; TEST_accessed = $false }

$campaignTimer = [Diagnostics.Stopwatch]::StartNew()
$allPreparedRows = @($Prepared.scene_rows)
$allSnapshotRows = @($Prepared.snapshot_rows)
$firstReleasePins = $firstRelease.pins
$sceneTimer = $null
$runner = $null
$export = $null
try {
for ($seq = 2; $seq -le 24; $seq++) {
    $currentSequence = $seq
    $currentSceneId = [string]$allPreparedRows[$seq - 1].canonical_scene_id
    $stage = 'SCENE_PREFLIGHT'
    $releaseSha = ''
    $runner = $null
    $export = $null
    $sceneTimer = [Diagnostics.Stopwatch]::StartNew()
    Assert-Resources
    $sourceRow = $allPreparedRows[$seq - 1]
    $snapshotRow = $allSnapshotRows[$seq - 1]
    $sceneId = [string]$sourceRow.canonical_scene_id
    $runtimeId = [string]$sourceRow.source_runtime_scene_id
    $attemptDir = Join-Path $ReportDir "runs/$sceneId/attempt_01"
    $releasePath = Join-Path $ReportDir "releases/ROOT_C5_MATCHED_TRAIN24_RELEASE_${sceneId}_v1.json"
    $exportDir = Join-Path $ReportDir "event_exports_v1/$sceneId"
    if ((Test-Path -LiteralPath $attemptDir) -or (Test-Path -LiteralPath $releasePath) -or (Test-Path -LiteralPath $exportDir)) {
        throw "Scene $sceneId already has a record/release/export; no retry or overwrite is allowed."
    }
    $stage = 'RELEASE_CREATE'
    Add-Ledger $ledgerPath @{ stage = 'SCENE_START'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); sequence_index = $seq; canonical_scene_id = $sceneId; source_runtime_scene_id = $runtimeId; snapshot_sha256 = $snapshotRow.sha256; raw_input_sha256 = $sourceRow.raw_sha256; run_start_input_sha256 = $sourceRow.run_start_sha256 }
    $release = [ordered]@{
        schema = 'C5_MATCHED_TRAIN24_RELEASE_V1'
        decision = 'APPROVE_ONE_FLIGHT'
        canonical_scene_id = $sceneId
        source_runtime_scene_id = $runtimeId
        sequence_index = $seq
        attempt_id = 1
        pins = [ordered]@{}
        reason = "Scene $seq of the Root-approved remaining-23 campaign; prior scenes passed terminal and export audit gates."
        training_steps = 0
        TEST_access = $false
        created_at = [DateTimeOffset]::Now.ToString('o')
        campaign_binding = [ordered]@{ schema = $CampaignSchema; release_path = $campaignPath; release_sha256 = $CampaignSha; first_independent_audit_sha256 = $FirstAuditSha; first_independent_auditor_sha256 = $FirstAuditorSha; exporter_matlab_sha256 = $ExporterSha }
    }
    foreach ($key in $firstReleasePins.Keys) { $release.pins[$key] = $firstReleasePins[$key] }
    $release.pins.taskbook_sha256 = $TaskbookSha
    $release.pins.source_manifest_sha256 = $SourceManifestSha
    $release.pins.prepare_result_sha256 = $PrepareSha
    $release.pins.snapshot_sha256 = [string]$snapshotRow.sha256
    $release.pins.raw_sha256 = [string]$sourceRow.raw_sha256
    $release.pins.run_start_sha256 = [string]$sourceRow.run_start_sha256
    $release.pins.prepare_matlab_sha256 = $PrepareSourceSha
    $release.pins.runner_matlab_sha256 = $RunnerSha
    $release.pins.exporter_matlab_sha256 = $ExporterSha
    $release.pins.first_auditor_sha256 = $FirstAuditorSha
    $releaseJson = ConvertTo-Json -InputObject $release -Depth 20
    Write-NewUtf8 $releasePath $releaseJson
    $releaseSha = Get-Sha256 $releasePath
    $matlabFolder = Matlab-Quote $ExperimentDir
    $releaseArg = Matlab-Quote $releasePath
    $sceneArg = Matlab-Quote $sceneId
    $runnerBatch = "addpath($matlabFolder); $RunnerFunction($releaseArg,'$releaseSha',$sceneArg);"
    $runnerLog = Join-Path $campaignRunDir ("{0:D2}_{1}_runner.log" -f $seq, $sceneId)
    $stage = 'RUNNER'
    if ((Get-Sha256 $RunnerPath) -ne $RunnerSha -or (Get-Sha256 $ExporterPath) -ne $ExporterSha) { throw 'Frozen runner/exporter source changed before flight.' }
    $runner = Invoke-Matlab $runnerBatch $runnerLog
    if ($runner.exit_code -ne 0) {
        throw "Runner failed for $sceneId with exit $($runner.exit_code); stopping the series without retry."
    }
    $stage = 'RUNNER_VERIFY'
    $statusPath = Join-Path $attemptDir 'run_status.json'
    $terminalPath = Join-Path $attemptDir 'terminal.marker'
    $rawPath = Join-Path $attemptDir 'raw_run.mat'
    if (-not (Test-Path -LiteralPath $statusPath) -or -not (Test-Path -LiteralPath $terminalPath) -or -not (Test-Path -LiteralPath $rawPath)) { throw "Runner returned OS0 but terminal status/raw is incomplete for $sceneId." }
    $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json -AsHashtable
    $actualRawSha = Get-Sha256 $rawPath
    if ($status.status -ne 'RUN_COMPLETE_STABLE' -or $status.canonical_scene_id -ne $sceneId -or
        $status.source_runtime_scene_id -ne $runtimeId -or [int]$status.sequence_index -ne $seq -or
        [int]$status.attempt_id -ne 1 -or [int]$status.transitions -ne 20000 -or
        [int]$status.state_samples -ne 20001 -or $status.plant_calls -ne 1 -or
        $status.training_steps -ne 0 -or $status.optimizer_steps -ne 0 -or $status.TEST_accessed -or
        $status.raw_sha256.ToLowerInvariant() -ne $actualRawSha -or
        (Get-Content -LiteralPath $terminalPath -Raw).Trim() -ne 'RUN_COMPLETE_STABLE') {
        throw "Runner OS0 did not produce the exact terminal stable status/raw identity for $sceneId."
    }
    Add-Ledger $ledgerPath @{ stage = 'SCENE_RUN_COMPLETE'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); sequence_index = $seq; canonical_scene_id = $sceneId; release_sha256 = $releaseSha; raw_sha256 = $actualRawSha; runner_elapsed_seconds = $runner.elapsed_seconds }
    Assert-Resources

    $exportBatch = "addpath($matlabFolder); $ExporterFunction($sceneArg);"
    $exportLog = Join-Path $campaignRunDir ("{0:D2}_{1}_export.log" -f $seq, $sceneId)
    $stage = 'EXPORT'
    if ((Get-Sha256 $RunnerPath) -ne $RunnerSha -or (Get-Sha256 $ExporterPath) -ne $ExporterSha) { throw 'Frozen runner/exporter source changed before export.' }
    $export = Invoke-Matlab $exportBatch $exportLog
    if ($export.exit_code -ne 0) {
        throw "Audit/export failed for $sceneId with exit $($export.exit_code); stopping before the next scene."
    }
    $stage = 'EXPORT_VERIFY'
    $auditJsonPath = Join-Path $ReportDir "event_exports_v1/$sceneId/${sceneId}_CSTAR_AUDIT_v1.json"
    $cachePath = Join-Path $ReportDir "event_exports_v1/$sceneId/${sceneId}_CSTAR_EVENTS_v1.mat"
    if (-not (Test-Path -LiteralPath $auditJsonPath) -or -not (Test-Path -LiteralPath $cachePath)) { throw "Exporter returned OS0 but did not publish both expected artifacts for $sceneId." }
    $audit = Get-Content -LiteralPath $auditJsonPath -Raw | ConvertFrom-Json -AsHashtable
    $actualAuditSha = Get-Sha256 $auditJsonPath
    $actualCacheSha = Get-Sha256 $cachePath
    $cacheBytes = [int64](Get-Item -LiteralPath $cachePath).Length
    if ($audit.schema -ne 'C5_MATCHED_TRAIN24_EVENT_EXPORT_AUDIT_V1' -or $audit.status -ne 'PASS' -or
        $audit.canonical_scene_id -ne $sceneId -or $audit.identity.runtime_scene_id -ne $runtimeId -or
        [int]$audit.event_count -ne 1999 -or [int]$audit.transition_count -ne 20000 -or
        [int]$audit.state_sample_count -ne 20001 -or $audit.exporter_plant_calls -ne 0 -or
        $audit.exporter_engine_calls -ne 0 -or $audit.optimizer_steps -ne 0 -or $audit.TEST_accessed -or
        $audit.identity.flight_raw_sha256.ToLowerInvariant() -ne $actualRawSha -or
        $audit.identity.release_sha256.ToLowerInvariant() -ne $releaseSha -or
        $audit.identity.run_status_sha256.ToLowerInvariant() -ne (Get-Sha256 $statusPath) -or
        $audit.identity.taskbook_sha256.ToLowerInvariant() -ne $TaskbookSha -or
        $audit.identity.source_manifest_sha256.ToLowerInvariant() -ne $SourceManifestSha -or
        $audit.identity.preparation_result_sha256.ToLowerInvariant() -ne $PrepareSha -or
        $audit.identity.snapshot_sha256.ToLowerInvariant() -ne $snapshotRow.sha256.ToLowerInvariant() -or
        $audit.identity.exporter_matlab_sha256.ToLowerInvariant() -ne $ExporterSha -or
        $audit.cache_sha256.ToLowerInvariant() -ne $actualCacheSha -or [int64]$audit.cache_bytes -ne $cacheBytes) {
        throw "Exporter OS0 result did not pass audit/identity/cache gates for $sceneId."
    }
    $sceneTimer.Stop()
    Add-Ledger $ledgerPath @{ stage = 'SCENE_AUDIT_EXPORT_PASS'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); sequence_index = $seq; canonical_scene_id = $sceneId; raw_sha256 = $actualRawSha; audit_path = $auditJsonPath; audit_sha256 = $actualAuditSha; cache_path = $cachePath; cache_sha256 = $actualCacheSha; cache_bytes = $cacheBytes; runner_elapsed_seconds = $runner.elapsed_seconds; export_elapsed_seconds = $export.elapsed_seconds; scene_elapsed_seconds = [Math]::Round($sceneTimer.Elapsed.TotalSeconds,3) }
    Assert-Resources
}
} catch {
    if ($null -ne $sceneTimer -and $sceneTimer.IsRunning) { $sceneTimer.Stop() }
    $failure = @{ stage = 'SCENE_FAILED'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); sequence_index = $currentSequence; canonical_scene_id = $currentSceneId; stage_name = $stage; release_sha256 = $releaseSha; elapsed_seconds = if ($null -ne $sceneTimer) { [Math]::Round($sceneTimer.Elapsed.TotalSeconds,3) } else { $null }; error_type = $_.Exception.GetType().FullName; error_message = $_.Exception.Message }
    if ($null -ne $runner) { $failure.runner_exit_code = $runner.exit_code; $failure.runner_elapsed_seconds = $runner.elapsed_seconds; $failure.runner_log_path = $runner.log_path }
    if ($null -ne $export) { $failure.export_exit_code = $export.exit_code; $failure.export_elapsed_seconds = $export.elapsed_seconds; $failure.export_log_path = $export.log_path }
    Add-Ledger $ledgerPath $failure
    if ($campaignTimer.IsRunning) { $campaignTimer.Stop() }
    Add-Ledger $ledgerPath @{ stage = 'CAMPAIGN_FAILED'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); campaign_sha256 = $CampaignSha; failed_sequence_index = $currentSequence; failed_scene_id = $currentSceneId; elapsed_seconds = [Math]::Round($campaignTimer.Elapsed.TotalSeconds,3); training_steps = 0; optimizer_steps = 0; TEST_accessed = $false }
    throw
}
$campaignTimer.Stop()
Add-Ledger $ledgerPath @{ stage = 'CAMPAIGN_COMPLETE'; at_utc = [DateTimeOffset]::UtcNow.ToString('o'); campaign_sha256 = $CampaignSha; completed_scenes = 23; elapsed_seconds = [Math]::Round($campaignTimer.Elapsed.TotalSeconds,3); decision = 'PASS'; training_steps = 0; optimizer_steps = 0; TEST_accessed = $false }
Write-Output "Remaining-23 campaign completed; ledger: $ledgerPath"





