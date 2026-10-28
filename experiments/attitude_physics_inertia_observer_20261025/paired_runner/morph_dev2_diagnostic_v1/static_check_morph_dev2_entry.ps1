# PS7 source/identity audit only: hashes and parses entry files; never starts MATLAB or Plant.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$entry = $PSScriptRoot
$pairedRoot = Split-Path -Parent $entry
$parent = Split-Path -Parent $pairedRoot
$preflightCandidatePath = Join-Path $pairedRoot 'preflight_v1/runs/full_input_preflight_20261025T140223_0872c2df/source_lock_paired_runner_v1_candidate.json'
$baseLockPath = Join-Path $pairedRoot 'dev3_v1/source_lock_paired_runner_v1.json'
$wrapper = Join-Path $entry 'run_morph_dev2_diagnostic.m'
$launcher = Join-Path $entry 'launch_morph_dev2_diagnostic.ps1'
$taskbookSource = Join-Path $pairedRoot 'MORPH_DEV2_DIAGNOSTIC_TASKBOOK_v1_ZH.md'
$taskbook = Join-Path $entry 'MORPH_DEV2_DIAGNOSTIC_TASKBOOK_v1_ZH.md'
$state = Join-Path $entry 'STATE_ZH.md'
$candidateLockPath = Join-Path $entry 'source_lock_morph_dev2_diagnostic_v2_candidate.json'
$auditPath = Join-Path $entry 'MORPH_DEV2_DIAGNOSTIC_STATIC_AUDIT_v2.json'

function ShaFile([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function AssertFileSha([string]$path, [string]$sha, [string]$label) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (ShaFile $path) -ne $sha) {
        throw "$label SHA differs: $path"
    }
}
function EntryRecord([string]$path) {
    [ordered]@{ path = $path; sha256 = ShaFile $path }
}
function WriteNewUtf8([string]$path, [string]$content) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($content)
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
if ((Test-Path -LiteralPath $candidateLockPath) -or (Test-Path -LiteralPath $auditPath)) {
    throw 'Static outputs already exist; refusing overwrite.'
}
if ((ShaFile $taskbookSource) -ne (ShaFile $taskbook)) { throw 'Local taskbook copy differs from the approved taskbook.' }
AssertFileSha $preflightCandidatePath 'ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2' 'Preflight candidate'
AssertFileSha $baseLockPath '64041daea543f746ad4067c830d1bdf983fda0ec809843d65ed950147345cb8d' 'Existing frozen DEV3 source lock'
$preflight = Get-Content -Raw -LiteralPath $preflightCandidatePath | ConvertFrom-Json
$baseLock = Get-Content -Raw -LiteralPath $baseLockPath | ConvertFrom-Json
if ($preflight.schema -ne 'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE' -or
    $preflight.status -ne 'NOT_FROZEN' -or $preflight.executed -ne $false -or
    $preflight.preflight_executed -ne $true -or $preflight.exit_code -ne 0 -or
    $preflight.matlab_start_count_this_preflight -ne 1 -or
    $preflight.plant_run_count_this_preflight -ne 0 -or
    $preflight.training_run_count_this_preflight -ne 0 -or
    $baseLock.schema -ne 'SOURCE_LOCK_PAIRED_RUNNER_V1' -or
    $baseLock.status -ne 'FROZEN_INPUTS' -or $baseLock.executed -ne $false -or
    $baseLock.closed_loop_runs_authorized -ne $false) {
    throw 'Preflight or frozen DEV3 source-lock status differs.'
}

$sources = @()
foreach ($property in $preflight.isolated_matlab_source_sha256_before.PSObject.Properties) {
    $relative = [string]$property.Name
    $expectedAfter = $preflight.isolated_matlab_source_sha256_after.PSObject.Properties[$relative].Value
    $path = Join-Path $pairedRoot $relative
    $sha = ShaFile $path
    if ($sha -ne [string]$property.Value -or $sha -ne [string]$expectedAfter) { throw "Frozen MATLAB source differs: $relative" }
    $sources += [ordered]@{ relative_path = $relative; path = $path; sha256 = $sha }
}
if ($sources.Count -ne 39 -or @($baseLock.sources).Count -ne 39) { throw 'Expected exactly 39 frozen deployment sources.' }
for ($i = 0; $i -lt 39; $i++) {
    if ($sources[$i].relative_path -ne $baseLock.sources[$i].relative_path -or
        $sources[$i].path -ne $baseLock.sources[$i].path -or
        $sources[$i].sha256 -ne $baseLock.sources[$i].sha256) { throw 'Frozen source list differs from the reviewed DEV3 lock.' }
}

$inputs = @()
foreach ($property in $preflight.input_sha256_before.PSObject.Properties) {
    $role = [string]$property.Name
    $record = $property.Value
    $after = $preflight.input_sha256_after.PSObject.Properties[$role].Value
    $sha = ShaFile ([string]$record.path)
    if ($sha -ne [string]$record.sha256 -or $sha -ne [string]$after.sha256) { throw "Frozen input differs: $role" }
    $inputs += [ordered]@{ role = $role; path = [string]$record.path; sha256 = $sha }
}
if ($inputs.Count -ne 17 -or @($baseLock.inputs).Count -ne 17) { throw 'Expected exactly 17 frozen preflight inputs.' }
for ($i = 0; $i -lt 17; $i++) {
    if ($inputs[$i].role -ne $baseLock.inputs[$i].role -or
        $inputs[$i].path -ne $baseLock.inputs[$i].path -or
        $inputs[$i].sha256 -ne $baseLock.inputs[$i].sha256) { throw 'Frozen input list differs from the reviewed DEV3 lock.' }
}

$diagnosticScenes = @(foreach ($scene in @($preflight.result.scenes)[1..2]) {
    [ordered]@{
        scene_id = [string]$scene.scene_id; seed = [long]$scene.seed
        spec_sha256 = [string]$scene.spec_sha256; scene_sha256 = [string]$scene.scene_sha256
        metadata_sha256 = [string]$scene.metadata_sha256
    }
})
if ($diagnosticScenes.Count -ne 2 -or
    (@($diagnosticScenes | ForEach-Object { $_.scene_id }) -join ',') -ne 'DL1018_DEV_T2_C02_W15,DL1018_DEV_T3_C10_W11' -or
    (@($diagnosticScenes | ForEach-Object { $_.seed }) -join ',') -ne '2026122847,2026123971') {
    throw 'Preflight diagnostic scene identities differ.'
}

$syntaxTokens = $null
$syntaxErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$syntaxTokens, [ref]$syntaxErrors)
if ($syntaxErrors.Count -ne 0) { throw 'Launcher PowerShell parser errors.' }
$checkerTokens = $null
$checkerSyntaxErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$checkerTokens, [ref]$checkerSyntaxErrors)
if ($checkerSyntaxErrors.Count -ne 0) { throw 'Static checker PowerShell parser errors.' }
$launcherBody = Get-Content -Raw -LiteralPath $launcher
$wrapperBody = Get-Content -Raw -LiteralPath $wrapper
if (-not $launcherBody.Contains("$" + "release.schema -ne 'PAIRED_MORPH_DEV2_DIAGNOSTIC_ROOT_RELEASE_V2'") -or
    -not $launcherBody.Contains("$" + "release.max_runner_calls -ne 4") -or
    -not $launcherBody.Contains("$" + "release.max_new_bytes -ne 2147483648") -or
    -not $launcherBody.Contains("$" + "release.minimum_free_bytes -ne 32212254720") -or
    -not $launcherBody.Contains('batchStatus.artifact_errors') -or
    -not $launcherBody.Contains("@(`$batchStatus.artifact_errors).Count -ne 0") -or
    -not $launcherBody.Contains("`$release.training_authorized -ne `$false") -or
    -not $launcherBody.Contains("`$release.TEST_authorized -ne `$false") -or
    -not $launcherBody.Contains("`$release.retry_authorized -ne `$false") -or
    -not $launcherBody.Contains('CreateNew') -or
    -not $launcherBody.Contains('MORPH_DEV2_DIAGNOSTIC_BATCH_FAILURE_V1') -or
    $launcherBody.Contains('PAIRED_DEV3_ROOT_RELEASE_V1') -or
    $launcherBody.Contains('DEV3_SCREEN_PASS') -or
    $launcherBody.Contains('SIX_FRESH_DEV3_PAIRED_RUNS')) {
    throw 'Launcher release, budget, artifact, or CreateNew gate differs.'
}
$runnerCallCount = [regex]::Matches($wrapperBody, '(?m)^\s*log=run_paired_observer_closed_loop\(').Count
$loadCount = [regex]::Matches($wrapperBody, '(?m)^\s*(?:modelPack|snapshot)=load\(').Count
if ($runnerCallCount -ne 1 -or $loadCount -ne 2 -or
    -not $wrapperBody.Contains("modelPack=load(modelPath,'model');") -or
    -not $wrapperBody.Contains("snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');") -or
    -not $wrapperBody.Contains("save(rawPath,'log','-v7.3');") -or
    -not $wrapperBody.Contains('createNewFile()') -or
    -not $wrapperBody.Contains('MORPH_DEV2_DIAGNOSTIC') -or
    -not $wrapperBody.Contains('DL1018_DEV_T2_C02_W15') -or
    -not $wrapperBody.Contains('DL1018_DEV_T3_C10_W11') -or
    $wrapperBody.Contains('DL1018_DEV_T1_C00_W03') -or
    $wrapperBody.Contains('DEV3_SCREEN_PASS') -or
    -not $wrapperBody.Contains('runnerCalls<4') -or
    -not $wrapperBody.Contains('stateTime<2.2') -or
    -not $wrapperBody.Contains('transitionTime<2.2') -or
    -not $wrapperBody.Contains('q_early_rmse_m') -or
    -not $wrapperBody.Contains('so3_early_rmse_rad') -or
    -not $wrapperBody.Contains('Candidate motor saturation count is nonzero.') -or
    -not $wrapperBody.Contains('Candidate generalized clipping count is nonzero.') -or
    -not $wrapperBody.Contains('tr.prepare.time_s==log.transition_time(k)') -or
    -not $wrapperBody.Contains('tr.commit.time_s==log.transition_time(k)') -or
    -not $wrapperBody.Contains('tr.prepare.estimateTorque_Nm(:)),-double(tr.prepare.tau_comp_Nm(:))') -or
    -not $wrapperBody.Contains('function write_results_csv') -or
    -not $wrapperBody.Contains('function write_diagnostic_report') -or
    -not $wrapperBody.Contains('r.score') -or
    -not $wrapperBody.Contains('traceErrors={};') -or
    -not $wrapperBody.Contains('status.engineering_gate=gate') -or
    $wrapperBody.Contains('r.q_rmse_m') -or $wrapperBody.Contains('r.so3_rmse_rad')) {
    throw 'Diagnostic wrapper call/load/scoring/safety/trace contract differs.'
}
if ($wrapperBody -match 'score\.q_rmse_m\s*<=' -or $wrapperBody -match 'score\.so3_rmse_rad\s*<=' -or
    -not $wrapperBody.Contains('performance_metrics_are_nongating=true') -or
    -not $wrapperBody.Contains('artifact_errors') -or
    -not $wrapperBody.Contains("write_json_new(fullfile(attemptDir,'batch_status.json'),summary);") -or
    -not $wrapperBody.Contains("assert(strcmp(batchStatus,'MORPH_DEV2_DIAGNOSTIC_COMPLETE')") -or
    $wrapperBody.IndexOf("save(rawPath,'log','-v7.3');") -ge $wrapperBody.IndexOf('[score,gate]=score_log(log,scene,a==2);')) {
    throw 'Performance became a stop gate or raw/score/artifact ordering differs.'
}

$entryRecords = [ordered]@{
    wrapper = EntryRecord $wrapper; launcher = EntryRecord $launcher
    checker = EntryRecord $PSCommandPath; taskbook = EntryRecord $taskbook; state = EntryRecord $state
}
$baseLockRecord = [ordered]@{ path = $baseLockPath; sha256 = ShaFile $baseLockPath }
$candidateLock = [ordered]@{
    schema = 'SOURCE_LOCK_MORPH_DEV2_DIAGNOSTIC_V2_CANDIDATE'
    scope = 'MORPH_DEV2_DIAGNOSTIC'
    status = 'NOT_FROZEN'; executed = $false; closed_loop_runs_authorized = $false
    created_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    base_dev3_source_lock = $baseLockRecord
    preflight_candidate_path = $preflightCandidatePath
    preflight_candidate_sha256 = ShaFile $preflightCandidatePath
    taskbook = $entryRecords.taskbook; state = $entryRecords.state
    wrapper = $entryRecords.wrapper; launcher = $entryRecords.launcher; checker = $entryRecords.checker
    sources = $sources; inputs = $inputs; diagnostic_scenes = $diagnosticScenes
    release_contract = [ordered]@{
        schema = 'PAIRED_MORPH_DEV2_DIAGNOSTIC_ROOT_RELEASE_V2'
        approval_required_by_root = $true; root_approval_status = 'PENDING'
        scope = 'MORPH_DEV2_DIAGNOSTIC'; max_runner_calls = 4
        max_new_bytes = 2147483648; minimum_free_bytes = 32212254720
        training_authorized = $false; TEST_authorized = $false; retry_authorized = $false
        scene_ids = @('DL1018_DEV_T2_C02_W15','DL1018_DEV_T3_C10_W11')
        arm_order = @('baseline','candidate')
        required_fields = @('attempt_id','source_lock_path','source_lock_sha256','candidate_input_lock_sha256')
    }
    limits = 'Candidate lock only; root must freeze it and issue a separate approved release. Static checker never starts MATLAB or Plant.'
}
$candidatePayload = ($candidateLock | ConvertTo-Json -Depth 12) + "`n"
$candidateBytes = [Text.UTF8Encoding]::new($false).GetBytes($candidatePayload)
$candidateSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($candidateBytes)).ToLowerInvariant()
$audit = [ordered]@{
    schema = 'MORPH_DEV2_DIAGNOSTIC_STATIC_AUDIT_V2'
    status = 'STATIC_PASS_PENDING_ROOT_REVIEW_NO_MATLAB'
    scope = 'MORPH_DEV2_DIAGNOSTIC'
    matlab_started = $false; runner_invocation_count = 0; plant_run_count = 0; training_run_count = 0
    base_dev3_source_lock = $baseLockRecord
    preflight_candidate = [ordered]@{ path = $preflightCandidatePath; sha256 = ShaFile $preflightCandidatePath }
    candidate_input_lock = [ordered]@{ path = $candidateLockPath; sha256 = $candidateSha }
    entries = $entryRecords
    source_count = $sources.Count; input_count = $inputs.Count
    sources = $sources; inputs = $inputs; diagnostic_scenes = $diagnosticScenes
    powershell_major = $PSVersionTable.PSVersion.Major
    launcher_parser_errors = $syntaxErrors.Count; checker_parser_errors = $checkerSyntaxErrors.Count
    powershell_parser_errors = ($syntaxErrors.Count + $checkerSyntaxErrors.Count)
    runner_call_sites = $runnerCallCount; model_config_mat_load_sites = $loadCount
    max_runner_calls = 4; max_new_bytes = 2147483648; minimum_free_bytes = 32212254720
    early_late_contract = [ordered]@{ cut_seconds = 2.2; early = '[0,2.2)'; late = '[2.2,20]'; q_state_points = 20001; so3_transition_points = 20000 }
    performance_is_nongating = $true; candidate_requires_stable_full_run = $true
    candidate_requires_zero_motor_saturation = $true; candidate_requires_zero_generalized_clipping = $true
    tilt_is_reported_not_compared_as_a_stop_gate = $true
    root_approval_status = 'PENDING'; root_release_issued = $false
    negative_check = [ordered]@{ no_dev3_screen_pass = $true; c00_not_in_scene_scope = $true }
    artifact_errors_block_complete_receipt = $true
    limits = 'PowerShell parser, file identity, and source-text contract checks only; MATLAB syntax/runtime and Plant behavior were not executed.'
}
$auditPayload = ($audit | ConvertTo-Json -Depth 14) + "`n"
WriteNewUtf8 $candidateLockPath $candidatePayload
WriteNewUtf8 $auditPath $auditPayload
Write-Output "MORPH_DEV2_STATIC_PASS candidate_lock=$candidateLockPath sha256=$candidateSha audit=$auditPath sha256=$(ShaFile $auditPath)"
