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
$auditPath = Join-Path $entry 'DEV3_ENTRY_STATIC_AUDIT_v1.json'
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
    -not $body.Contains('n=20000;') -or
    -not $body.Contains('q=sqrt(mean(sum(e.^2,2)))') -or
    -not $body.Contains('theta(k)=acos(max(min(x,1),-1))')) {
    throw 'Wrapper call/load/raw/scoring contract differs.'
}
$audit = [ordered]@{
    schema = 'PAIRED_DEV3_ENTRY_STATIC_AUDIT_V1'
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
