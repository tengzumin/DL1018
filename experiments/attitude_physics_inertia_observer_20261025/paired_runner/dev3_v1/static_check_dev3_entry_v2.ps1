# PowerShell 7 code/input identity check only; never calls MATLAB or reads MAT variables.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$entry = $PSScriptRoot
$root = Split-Path -Parent $entry
$preflightCandidate = Join-Path $root 'preflight_v1/runs/full_input_preflight_20261025T140223_0872c2df/source_lock_paired_runner_v1_candidate.json'
$wrapper = Join-Path $entry 'run_dev3_paired.m'
$launcher = Join-Path $entry 'launch_dev3_paired.ps1'
$taskbook = Join-Path $root 'DEV3_EXECUTION_ENTRY_TASKBOOK_v1_ZH.md'
$state = Join-Path $entry 'STATE_ZH.md'
$auditPath = Join-Path $entry 'DEV3_ENTRY_STATIC_AUDIT_v2.json'
function ShaFile([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
if (Test-Path -LiteralPath $auditPath) { throw 'Static audit already exists; no overwrite.' }
if ((ShaFile $preflightCandidate) -ne 'ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2') {
    throw 'Approved preflight candidate SHA differs.'
}
$candidate = Get-Content -Raw -LiteralPath $preflightCandidate | ConvertFrom-Json
if ($candidate.schema -ne 'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE' -or
    $candidate.status -ne 'NOT_FROZEN' -or
    $candidate.exit_code -ne 0 -or
    $candidate.preflight_executed -ne $true -or
    $candidate.matlab_start_count_this_preflight -ne 1 -or
    $candidate.plant_run_count_this_preflight -ne 0) {
    throw 'Preflight candidate status differs.'
}
$sources = @()
foreach ($property in $candidate.isolated_matlab_source_sha256_before.PSObject.Properties) {
    $relative = [string]$property.Name
    $path = Join-Path $root $relative
    $sha = ShaFile $path
    if ($sha -ne $property.Value -or
        $sha -ne $candidate.isolated_matlab_source_sha256_after.$relative) {
        throw "Isolated source differs: $relative"
    }
    $sources += [ordered]@{ relative_path = $relative; path = $path; sha256 = $sha }
}
if ($sources.Count -ne 39) { throw 'Expected 39 isolated MATLAB sources.' }
$forward = @($sources | Where-Object { $_.relative_path -eq 'matlab/models/position_stage1_model_forward_v2.m' })
if ($forward.Count -ne 1 -or
    $forward[0].sha256 -ne 'dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676') {
    throw 'C5 DSSM forward identity differs.'
}
$inputs = @()
foreach ($property in $candidate.input_sha256_before.PSObject.Properties) {
    $role = [string]$property.Name
    $record = $property.Value
    $sha = ShaFile $record.path
    if ($sha -ne $record.sha256 -or
        $sha -ne $candidate.input_sha256_after.$role.sha256) {
        throw "Preflight input differs: $role"
    }
    $inputs += [ordered]@{ role = $role; path = [string]$record.path; sha256 = $sha }
}
if ($inputs.Count -ne 17) { throw 'Expected 17 preflight inputs.' }
$syntaxTokens = $null
$syntaxErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($launcher,[ref]$syntaxTokens,[ref]$syntaxErrors)
if ($syntaxErrors.Count -ne 0) { throw 'DEV3 launcher PowerShell Parser errors.' }
$launcherBody = Get-Content -Raw -LiteralPath $launcher
if (-not $launcherBody.Contains("$" + "lock.schema -ne 'SOURCE_LOCK_PAIRED_RUNNER_V1'") -or
    -not $launcherBody.Contains("$" + "lock.status -ne 'FROZEN_INPUTS'") -or
    -not $launcherBody.Contains('confirmed_transitions') -or
    -not $launcherBody.Contains('unknown_plant_invocations')) {
    throw 'Launcher frozen-lock or Plant-accounting gate differs.'
}
$body = Get-Content -Raw -LiteralPath $wrapper
$runnerCalls = [regex]::Matches($body,'(?m)^\s*log=run_paired_observer_closed_loop\(')
$loads = [regex]::Matches($body,'(?m)^\s*(?:modelPack|snapshot)=load\(')
if ($runnerCalls.Count -ne 1 -or $loads.Count -ne 2 -or
    -not $body.Contains("modelPack=load(modelPath,'model');") -or
    -not $body.Contains("snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');") -or
    -not $body.Contains("save(rawPath,'log','-v7.3');") -or
    -not $body.Contains('runner_invocation.json') -or
    -not $body.Contains('source_lock_sha256') -or
    -not $body.Contains('releaseSha') -or
    -not $body.Contains("strcmp(lock.schema,'SOURCE_LOCK_PAIRED_RUNNER_V1')") -or
    -not $body.Contains("strcmp(lock.status,'FROZEN_INPUTS')") -or
    -not $body.Contains('same_path(attemptDir,expectedAttempt)') -or
    -not $body.Contains('confirmed_plant_runs') -or
    -not $body.Contains('confirmed_transitions') -or
    -not $body.Contains('unknown_plant_invocations') -or
    -not $body.Contains('pairGate.delta_q_rmse_m') -or
    -not $body.Contains('n=20000;') -or
    -not $body.Contains('q=sqrt(mean(sum(e.^2,2)))') -or
    -not $body.Contains('theta(k)=acos(max(min(x,1),-1))')) {
    throw 'Wrapper call/load/raw/scoring contract differs.'
}
if ($body.IndexOf("save(rawPath,'log','-v7.3');") -ge
        $body.IndexOf("write_json_new(fullfile(armDir,'scene_audit.json'),audit);") -or
    $body.IndexOf("write_json_new(fullfile(armDir,'scene_audit.json'),audit);") -ge
        $body.IndexOf('[score,gate]=score_log(log,scene,a==2);')) {
    throw 'Raw, scene audit, and score/gate order differs.'
}
$archived = @()
$old = [ordered]@{
    'run_dev3_paired.m' = '167d49b3c3d802888857c80d8196bb69c70550017a9bf08c9c4d638fccfc7441'
    'launch_dev3_paired.ps1' = '53daf4e068b2dc5a0a58e975f7c76548297e92f55d7058883e3bbd3aee95453b'
    'DEV3_ENTRY_STATIC_AUDIT_v1.json' = '912c3f9ed7f7317ebc8ee351ecd00dbda5a302ae2a6b6d11fb90ee83786b634e'
    'source_lock_paired_runner_v1_candidate.json' = '025089a45f3e272a39b2c7fc09f61c9421fcb460a9d1233dae64217b3edadfa4'
}
foreach ($name in $old.Keys) {
    $path = Join-Path (Join-Path $entry 'provenance_before_entry_fix') $name
    $sha = ShaFile $path
    if ($sha -ne $old[$name]) { throw "Archived first entry differs: $name" }
    $archived += [ordered]@{ path = $path; sha256 = $sha }
}
$audit = [ordered]@{
    schema = 'PAIRED_DEV3_ENTRY_STATIC_AUDIT_V2'
    status = 'STATIC_PASS_PENDING_ROOT_RELEASE_NO_MATLAB'
    matlab_started = $false
    runner_invocation_count = 0
    plant_run_count = 0
    preflight_candidate = [ordered]@{ path = $preflightCandidate; sha256 = ShaFile $preflightCandidate }
    taskbook = [ordered]@{ path = $taskbook; sha256 = ShaFile $taskbook }
    state = [ordered]@{ path = $state; sha256 = ShaFile $state }
    wrapper = [ordered]@{ path = $wrapper; sha256 = ShaFile $wrapper }
    launcher = [ordered]@{ path = $launcher; sha256 = ShaFile $launcher }
    checker = [ordered]@{ path = $PSCommandPath; sha256 = ShaFile $PSCommandPath }
    source_count = $sources.Count
    sources = $sources
    input_count = $inputs.Count
    inputs = $inputs
    parser_errors = $syntaxErrors.Count
    runner_call_sites = $runnerCalls.Count
    model_config_mat_load_sites = $loads.Count
    archived_unexecuted_entry_v1 = $archived
    required_frozen_lock = [ordered]@{ schema = 'SOURCE_LOCK_PAIRED_RUNNER_V1'; status = 'FROZEN_INPUTS' }
    release_contract = [ordered]@{
        schema = 'PAIRED_DEV3_ROOT_RELEASE_V1'
        approved = $true
        scope = 'SIX_FRESH_DEV3_PAIRED_RUNS'
        max_runner_calls = 6
        max_new_bytes = 1073741824
        minimum_free_bytes = 32212254720
        scene_ids = @('DL1018_DEV_T1_C00_W03','DL1018_DEV_T2_C02_W15','DL1018_DEV_T3_C10_W11')
        arm_order = @('baseline','candidate')
        required_fields = @('attempt_id','source_lock_path','source_lock_sha256','candidate_input_lock_sha256')
    }
    limits = 'Static text/identity check only; MATLAB wrapper not executed.'
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($audit | ConvertTo-Json -Depth 12) + "`n")
$stream = [IO.File]::Open($auditPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
Write-Output "DEV3_STATIC_PASS audit=$auditPath sha256=$(ShaFile $auditPath)"
