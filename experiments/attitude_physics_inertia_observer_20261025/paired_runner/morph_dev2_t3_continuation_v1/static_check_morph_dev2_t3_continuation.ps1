# PS7 source/identity audit only: hashes and parses entry files; never starts MATLAB or Plant.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$entry = $PSScriptRoot
$pairedRoot = Split-Path -Parent $entry
$preflightCandidatePath = Join-Path $pairedRoot 'preflight_v1/runs/full_input_preflight_20261025T140223_0872c2df/source_lock_paired_runner_v1_candidate.json'
$baseLockPath = Join-Path $pairedRoot 'dev3_v1/source_lock_paired_runner_v1.json'
$wrapper = Join-Path $entry 'run_morph_dev2_t3_continuation.m'
$launcher = Join-Path $entry 'launch_morph_dev2_t3_continuation.ps1'
$taskbook = Join-Path $entry 'MORPH_DEV2_T3_CONTINUATION_TASKBOOK_v1_ZH.md'
$state = Join-Path $entry 'STATE_ZH.md'
$candidateLockPath = Join-Path $entry 'source_lock_morph_dev2_t3_continuation_v1_candidate.json'
$auditPath = Join-Path $entry 'MORPH_DEV2_T3_CONTINUATION_STATIC_AUDIT_v1.json'
$a02Attempt = Join-Path $pairedRoot 'morph_dev2_diagnostic_v1/attempts/MORPH_DEV2_20261025_A02'
$rootReview = Join-Path $pairedRoot 'root_review_v1/ROOT_A02_C02_REVIEW_AND_T3_DECISION_v1_ZH.md'
$independentReview = Join-Path $pairedRoot 'root_review_v1/c02_independent_v1/review.json'
$independentScores = Join-Path $pairedRoot 'root_review_v1/c02_independent_v1/scores.csv'
$independentScorer = Join-Path $pairedRoot 'root_review_v1/score_morph_dev2_c02_raw_v1.py'

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

$t3Scene = @($preflight.result.scenes)[2]
$diagnosticScenes = @([ordered]@{
    scene_id = [string]$t3Scene.scene_id; seed = [long]$t3Scene.seed
    spec_sha256 = [string]$t3Scene.spec_sha256; scene_sha256 = [string]$t3Scene.scene_sha256
    metadata_sha256 = [string]$t3Scene.metadata_sha256
})
if ($diagnosticScenes.Count -ne 1 -or
    $diagnosticScenes[0].scene_id -ne 'DL1018_DEV_T3_C10_W11' -or
    $diagnosticScenes[0].seed -ne 2026123971 -or
    $diagnosticScenes[0].spec_sha256 -ne '56c29ea53ac1e8b1d261b5c88667b68a766ca77a128b32880be9d74c0c9fefba' -or
    $diagnosticScenes[0].scene_sha256 -ne 'e06aa4dde902603f390554f4d8b022760b44a450b2c9868d68344d44ea5a809f' -or
    $diagnosticScenes[0].metadata_sha256 -ne '2bc2cafcd45c4ce2db4069b9f7477090f9c0851c30bdd304bde32e16a7073614') {
    throw 'Preflight T3 scene ID, seed, or hashes differ from the taskbook.'
}

$a02Evidence = @()
foreach ($item in @(
    [ordered]@{ role='root_review'; path=$rootReview },
    [ordered]@{ role='independent_review_json'; path=$independentReview },
    [ordered]@{ role='independent_scores_csv'; path=$independentScores },
    [ordered]@{ role='independent_scorer'; path=$independentScorer },
    [ordered]@{ role='batch_status'; path=(Join-Path $a02Attempt 'batch_status.json') },
    [ordered]@{ role='pair_audit'; path=(Join-Path $a02Attempt 'pair_01_audit.json') },
    [ordered]@{ role='batch_receipt'; path=(Join-Path $a02Attempt 'batch_receipt.json') }
)) {
    if (-not (Test-Path -LiteralPath $item.path -PathType Leaf)) { throw "Missing A02 evidence: $($item.path)" }
    $a02Evidence += [ordered]@{ role=$item.role; path=$item.path; sha256=(ShaFile $item.path) }
}
$a02BatchPath = Join-Path $a02Attempt 'batch_status.json'
$a02PairPath = Join-Path $a02Attempt 'pair_01_audit.json'
$a02ReceiptPath = Join-Path $a02Attempt 'batch_receipt.json'
AssertFileSha $a02BatchPath '8fb5c7580a7fa2846569a3ccfedd28e30b421fb32210e7b8632d7dc8a31e1e00' 'A02 batch status'
AssertFileSha $a02PairPath '7faa7a44ae3986bfe8f7ff0705e5d5bcd004bdcc1878ef77327a6221cfdd6efe' 'A02 pair audit'
AssertFileSha $a02ReceiptPath '686ba00fc7e0a0723714f68329999d1a90bdb6989f9f454efcf470d5fad4e770' 'A02 batch receipt'
$a02Batch = Get-Content -Raw -LiteralPath $a02BatchPath | ConvertFrom-Json
$a02Independent = Get-Content -Raw -LiteralPath $independentReview | ConvertFrom-Json
if ($a02Batch.status -ne 'STOPPED_ON_FAILURE' -or $a02Batch.runner_invocation_count -ne 2 -or
    $a02Batch.confirmed_plant_runs -ne 2 -or $a02Batch.confirmed_transitions -ne 40000 -or
    $a02Batch.unknown_plant_invocations -ne 0 -or
    $a02Independent.schema -ne 'ROOT_MORPH_DEV2_C02_RAW_REVIEW_V1' -or
    $a02Independent.scene_id -ne 'DL1018_DEV_T2_C02_W15' -or
    $a02Independent.runs.Count -ne 2 -or
    $a02Independent.runs[0].raw_sha256 -ne '6e5866127b76631bbc860c38ff09898d79a8227984310d570945a0d121c881c4' -or
    $a02Independent.runs[1].raw_sha256 -ne '99523fa5c1dc69a3daeed2f7f23ecc24d04e37e0ede2c0c49e7058156eead0ff' -or
    $a02Independent.runs[0].run_status_sha256 -ne '27114714c1b0f58e8b3862667ce112c08e6502ec8d63f40bdfacdb7c6f8f8059' -or
    $a02Independent.runs[1].run_status_sha256 -ne '36d26c1b471ec3d76c9f0cfcb4b2b995b736f69de7f0b24722100db40fa5a11f' -or
    $a02Independent.runs[1].trace_audit.trace_count -ne 20000 -or
    $a02Independent.runs[1].trace_audit.event_count -ne 1999 -or
    (@($a02Independent.runs[1].trace_audit.top_level_rbf_flags.attitude_fusion_rbf_output_enabled.shape) -join ',') -ne '1,1' -or
    (@($a02Independent.runs[1].trace_audit.top_level_rbf_flags.attitude_fusion_rbf_update_enabled.shape) -join ',') -ne '1,1' -or
    $a02Independent.runs[1].trace_audit.top_level_rbf_flags.attitude_fusion_rbf_output_enabled.values[0] -ne 0 -or
    $a02Independent.runs[1].trace_audit.top_level_rbf_flags.attitude_fusion_rbf_update_enabled.values[0] -ne 0 -or
    $a02Independent.runs[1].trace_audit.all_trace_checks_pass -ne $true -or
    $a02Independent.runs[1].trace_audit.all_rbf_off -ne $true -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.rbf_output_held.shape) -join ',') -ne '3,20000' -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.attitude_rbf_estimate_acceleration_rads2.shape) -join ',') -ne '3,20000' -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.attitude_rbf_compensation_torque_Nm.shape) -join ',') -ne '3,20000' -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_norm.shape) -join ',') -ne '1,20000' -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_max.shape) -join ',') -ne '1,20000' -or
    (@($a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_derivative_norm.shape) -join ',') -ne '1,20000' -or
    $a02Independent.runs[1].trace_audit.rbf_series.rbf_output_held.nonzero_count -ne 0 -or
    $a02Independent.runs[1].trace_audit.rbf_series.attitude_rbf_estimate_acceleration_rads2.nonzero_count -ne 0 -or
    $a02Independent.runs[1].trace_audit.rbf_series.attitude_rbf_compensation_torque_Nm.nonzero_count -ne 0 -or
    $a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_norm.nonzero_count -ne 0 -or
    $a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_max.nonzero_count -ne 0 -or
    $a02Independent.runs[1].trace_audit.rbf_series.rbf_weight_derivative_norm.nonzero_count -ne 0 -or
    @($a02Independent.runs[1].trace_audit.mismatch_counts.PSObject.Properties | Where-Object { $_.Value -ne 0 }).Count -ne 0) {
    throw 'A02 root-reviewed status or independent raw/trace evidence differs.'
}
$a02RawManifest = @()
foreach ($armIndex in 0..1) {
    $arm = [string]$a02Independent.runs[$armIndex].arm
    $runStatusPath = Join-Path $a02Attempt ("01_DL1018_DEV_T2_C02_W15_$arm/run_status.json")
    AssertFileSha $runStatusPath ([string]$a02Independent.runs[$armIndex].run_status_sha256) "A02 $arm run status"
    $runStatus = Get-Content -Raw -LiteralPath $runStatusPath | ConvertFrom-Json
    if ($runStatus.status -ne [string]$a02Independent.runs[$armIndex].stored_status -or
        $runStatus.runner_status -ne 'STABLE' -or $runStatus.last_transition -ne 20000 -or
        $runStatus.raw_sha256 -ne [string]$a02Independent.runs[$armIndex].raw_sha256 -or
        [long]$runStatus.raw_bytes -ne [long]$a02Independent.runs[$armIndex].raw_bytes) {
        throw "A02 $arm status/raw manifest differs from independent root review."
    }
    $rawPath = Join-Path $a02Attempt ("01_DL1018_DEV_T2_C02_W15_$arm/run_raw.mat")
    if ([IO.Path]::GetFullPath([string]$runStatus.raw_path) -ne [IO.Path]::GetFullPath($rawPath) -or
        (ShaFile $rawPath) -ne [string]$a02Independent.runs[$armIndex].raw_sha256 -or
        (Get-Item -LiteralPath $rawPath).Length -ne [long]$a02Independent.runs[$armIndex].raw_bytes) {
        throw "A02 $arm raw file SHA/path/length differs from root-reviewed evidence."
    }
    $a02Evidence += [ordered]@{ role="run_status_$arm"; path=$runStatusPath; sha256=(ShaFile $runStatusPath) }
    $a02RawManifest += [ordered]@{ arm=$arm; path=[string]$runStatus.raw_path; sha256=[string]$runStatus.raw_sha256; bytes=[long]$runStatus.raw_bytes }
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
if (-not $launcherBody.Contains('PAIRED_MORPH_DEV2_T3_CONTINUATION_ROOT_RELEASE_V1') -or
    -not $launcherBody.Contains('MORPH_DEV2_T3_CONTINUATION') -or
    -not $launcherBody.Contains('max_runner_calls -ne 2') -or
    -not $launcherBody.Contains('max_new_bytes -ne 1650000000') -or
    -not $launcherBody.Contains('prior_runner_calls -ne 2') -or
    -not $launcherBody.Contains('cumulative_runner_call_ceiling -ne 4') -or
    -not $launcherBody.Contains('minimum_free_bytes -ne 32212254720') -or
    -not $launcherBody.Contains('@($batchStatus.artifact_errors).Count -ne 0') -or
    -not $launcherBody.Contains('$release.training_authorized -ne $false') -or
    -not $launcherBody.Contains('$release.TEST_authorized -ne $false') -or
    -not $launcherBody.Contains('$release.retry_authorized -ne $false') -or
    -not $launcherBody.Contains('CreateNew') -or
    -not $launcherBody.Contains('EnsureFailureArtifacts') -or
    -not $launcherBody.Contains('Raw identity differs from run_status.json') -or
    -not $launcherBody.Contains('failure_reason=$reason; artifact_errors=@($artifactErrors.ToArray())') -or
    -not $launcherBody.Contains('results.csv') -or -not $launcherBody.Contains('report.md') -or
    -not $launcherBody.Contains('MORPH_DEV2_T3_CONTINUATION_BATCH_FAILURE_V1') -or
    -not $launcherBody.Contains('run_morph_dev2_t3_continuation(') -or
    -not $launcherBody.Contains('01_DL1018_DEV_T3_C10_W11_') -or
    $launcherBody.Contains('DEV_T2_C02') -or $launcherBody.Contains('C02') -or
    $launcherBody.Contains('DEV3_SCREEN_PASS')) {
    throw 'Launcher T3 release, call budget, artifact, or CreateNew gate differs.'
}
$runnerCallCount = [regex]::Matches($wrapperBody, '(?m)^\s*log=run_paired_observer_closed_loop\(').Count
$loadCount = [regex]::Matches($wrapperBody, '(?m)^\s*(?:modelPack|snapshot)=load\(').Count
if ($runnerCallCount -ne 1 -or $loadCount -ne 2 -or
    -not $wrapperBody.Contains('function run_morph_dev2_t3_continuation(') -or
    -not $wrapperBody.Contains("modelPack=load(modelPath,'model');") -or
    -not $wrapperBody.Contains("snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');") -or
    -not $wrapperBody.Contains("save(rawPath,'log','-v7.3');") -or
    -not $wrapperBody.Contains('createNewFile()') -or
    -not $wrapperBody.Contains('MORPH_DEV2_T3_CONTINUATION') -or
    -not $wrapperBody.Contains('DL1018_DEV_T3_C10_W11') -or
    $wrapperBody.Contains('DL1018_DEV_T1_C00_W03') -or
    $wrapperBody.Contains('DL1018_DEV_T2_C02_W15') -or
    $wrapperBody.Contains('DEV3_SCREEN_PASS') -or
    -not $wrapperBody.Contains('runnerCalls<2') -or
    -not $wrapperBody.Contains('max_runner_calls)==2') -or
    -not $wrapperBody.Contains('max_new_bytes)==1650000000') -or
    -not $wrapperBody.Contains('prior_runner_calls)==2') -or
    -not $wrapperBody.Contains('cumulative_runner_call_ceiling)==4') -or
    -not $wrapperBody.Contains('isequal(size(value),[n,3])') -or
    -not $wrapperBody.Contains('isequal(size(value),[n,1])') -or
    -not $wrapperBody.Contains('is_scalar_false(log.attitude_fusion_rbf_output_enabled)') -or
    -not $wrapperBody.Contains('is_scalar_false(log.attitude_fusion_rbf_update_enabled)') -or
    -not $wrapperBody.Contains('numel(log.phys_attitude_trace)~=n') -or
    -not $wrapperBody.Contains('for k=1:n') -or
    -not $wrapperBody.Contains('stateTime<2.2') -or
    -not $wrapperBody.Contains('transitionTime<2.2') -or
    -not $wrapperBody.Contains('q_early_rmse_m') -or
    -not $wrapperBody.Contains('so3_early_rmse_rad') -or
    -not $wrapperBody.Contains('Candidate motor saturation count is nonzero.') -or
    -not $wrapperBody.Contains('Candidate generalized clipping count is nonzero.') -or
    -not $wrapperBody.Contains('tr.prepare.time_s==log.transition_time(k)') -or
    -not $wrapperBody.Contains('tr.commit.time_s==log.transition_time(k)') -or
    -not $wrapperBody.Contains('tr.prepare.estimateTorque_Nm(:)),-double(tr.prepare.tau_comp_Nm(:))') -or
    -not $wrapperBody.Contains('logical(tr.prepare.observer.updated)==logical(tr.is_attitude_event)') -or
    -not $wrapperBody.Contains('function write_results_csv') -or
    -not $wrapperBody.Contains('function write_diagnostic_report') -or
    -not $wrapperBody.Contains('csv_metric(r,''wall_seconds'',0)') -or
    -not $wrapperBody.Contains('function value=csv_metric(record,name,index)') -or
    -not $wrapperBody.Contains('r.score') -or
    -not $wrapperBody.Contains('traceErrors={};') -or
    -not $wrapperBody.Contains('status.engineering_gate=gate') -or
    $wrapperBody.Contains('r.q_rmse_m') -or $wrapperBody.Contains('r.so3_rmse_rad')) {
    throw 'T3 wrapper call/load/scoring/safety/trace contract differs.'
}
 $csvCalls = [regex]::Matches($wrapperBody, '(?<!function )csv_metric\(([^)]*)\)')
if (@($csvCalls).Count -lt 3 -or @($csvCalls | Where-Object { $_.Groups[1].Value.Split(',').Count -ne 3 }).Count -ne 0) {
    throw 'Every csv_metric call must explicitly pass record, field, and index.'
}
if ($wrapperBody -match 'score\.q_rmse_m\s*<=' -or $wrapperBody -match 'score\.so3_rmse_rad\s*<=' -or
    -not $wrapperBody.Contains('performance_metrics_are_nongating=true') -or
    -not $wrapperBody.Contains('artifact_errors') -or
    -not $wrapperBody.Contains("write_json_new(fullfile(attemptDir,'batch_status.json'),summary);") -or
    -not $wrapperBody.Contains("assert(strcmp(batchStatus,'MORPH_DEV2_T3_CONTINUATION_COMPLETE')") -or
    $wrapperBody.IndexOf("save(rawPath,'log','-v7.3');") -ge $wrapperBody.IndexOf('[score,gate]=score_log(log,scene,a==2);')) {
    throw 'Performance became a stop gate or raw/score/artifact ordering differs.'
}

$entryRecords = [ordered]@{
    wrapper = EntryRecord $wrapper; launcher = EntryRecord $launcher
    checker = EntryRecord $PSCommandPath; taskbook = EntryRecord $taskbook; state = EntryRecord $state
}
$baseLockRecord = [ordered]@{ path = $baseLockPath; sha256 = ShaFile $baseLockPath }
$candidateLock = [ordered]@{
    schema = 'SOURCE_LOCK_MORPH_DEV2_T3_CONTINUATION_V1_CANDIDATE'
    scope = 'MORPH_DEV2_T3_CONTINUATION'
    status = 'NOT_FROZEN'; executed = $false; closed_loop_runs_authorized = $false
    training_authorized = $false; TEST_authorized = $false; retry_authorized = $false
    root_approval_status = 'PENDING'; root_release_issued = $false
    created_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    base_dev3_source_lock = $baseLockRecord
    preflight_candidate_path = $preflightCandidatePath
    preflight_candidate_sha256 = ShaFile $preflightCandidatePath
    taskbook = $entryRecords.taskbook; state = $entryRecords.state
    wrapper = $entryRecords.wrapper; launcher = $entryRecords.launcher; checker = $entryRecords.checker
    sources = $sources; inputs = $inputs; diagnostic_scenes = $diagnosticScenes
    prior_a02_root_review_evidence = $a02Evidence; prior_a02_raw_manifest = $a02RawManifest
    release_contract = [ordered]@{
        schema = 'PAIRED_MORPH_DEV2_T3_CONTINUATION_ROOT_RELEASE_V1'
        approval_required_by_root = $true; root_approval_status = 'PENDING'
        scope = 'MORPH_DEV2_T3_CONTINUATION'; max_runner_calls = 2
        prior_runner_calls = 2; cumulative_runner_call_ceiling = 4
        max_new_bytes = 1650000000; minimum_free_bytes = 32212254720
        training_authorized = $false; TEST_authorized = $false; retry_authorized = $false
        scene_ids = @('DL1018_DEV_T3_C10_W11')
        arm_order = @('baseline','candidate')
        required_fields = @('attempt_id','source_lock_path','source_lock_sha256','candidate_input_lock_sha256')
    }
    limits = 'Candidate lock only; root must freeze it and issue a separate approved release. Static checker never starts MATLAB or Plant.'
}
$candidatePayload = ($candidateLock | ConvertTo-Json -Depth 12) + "`n"
$candidateBytes = [Text.UTF8Encoding]::new($false).GetBytes($candidatePayload)
$candidateSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($candidateBytes)).ToLowerInvariant()
$audit = [ordered]@{
    schema = 'MORPH_DEV2_T3_CONTINUATION_STATIC_AUDIT_V1'
    status = 'STATIC_PASS_PENDING_ROOT_REVIEW_NO_MATLAB'
    scope = 'MORPH_DEV2_T3_CONTINUATION'
    matlab_started = $false; runner_invocation_count = 0; plant_run_count = 0; training_run_count = 0
    base_dev3_source_lock = $baseLockRecord
    preflight_candidate = [ordered]@{ path = $preflightCandidatePath; sha256 = ShaFile $preflightCandidatePath }
    candidate_input_lock = [ordered]@{ path = $candidateLockPath; sha256 = $candidateSha }
    entries = $entryRecords
    source_count = $sources.Count; input_count = $inputs.Count
    sources = $sources; inputs = $inputs; diagnostic_scenes = $diagnosticScenes
    prior_a02_root_review_evidence = $a02Evidence; prior_a02_raw_manifest = $a02RawManifest
    powershell_major = $PSVersionTable.PSVersion.Major
    launcher_parser_errors = $syntaxErrors.Count; checker_parser_errors = $checkerSyntaxErrors.Count
    powershell_parser_errors = ($syntaxErrors.Count + $checkerSyntaxErrors.Count)
    runner_call_sites = $runnerCallCount; csv_metric_call_sites = @($csvCalls).Count; model_config_mat_load_sites = $loadCount
    max_runner_calls = 2; prior_runner_calls = 2; cumulative_runner_call_ceiling = 4
    max_new_bytes = 1650000000; minimum_free_bytes = 32212254720
    early_late_contract = [ordered]@{ cut_seconds = 2.2; early = '[0,2.2)'; late = '[2.2,20]'; q_state_points = 20001; so3_transition_points = 20000 }
    performance_is_nongating = $true; candidate_requires_stable_full_run = $true
    candidate_requires_zero_motor_saturation = $true; candidate_requires_zero_generalized_clipping = $true
    tilt_is_reported_not_compared_as_a_stop_gate = $true
    root_approval_status = 'PENDING'; root_release_issued = $false
    negative_check = [ordered]@{ no_dev3_screen_pass = $true; no_t2_c02_in_scene_scope = $true; no_old_diagnostic_scope = $true }
    artifact_errors_block_complete_receipt = $true
    limits = 'PowerShell parser, file identity, and source-text contract checks only; MATLAB syntax/runtime and Plant behavior were not executed.'
}
$auditPayload = ($audit | ConvertTo-Json -Depth 14) + "`n"
WriteNewUtf8 $candidateLockPath $candidatePayload
WriteNewUtf8 $auditPath $auditPayload
Write-Output "MORPH_DEV2_STATIC_PASS candidate_lock=$candidateLockPath sha256=$candidateSha audit=$auditPath sha256=$(ShaFile $auditPath)"
