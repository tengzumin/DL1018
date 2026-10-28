Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
$entry = $PSScriptRoot
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

$required = @(
    'ATTITUDE_PHYS_INERTIA_DEV72_TASKBOOK_v1_ZH.md',
    'DEV58_USER_STEERING_ADDENDUM_20261025.md',
    'prepare_manifest_no_plant.m',
    'run_morph_dev2_dev58.m',
    'build_candidate_lock_dev58.ps1',
    'build_candidate_lock_dev58_v2.ps1',
    'issue_root_release_dev58.ps1',
    'issue_root_release_dev58_v2.ps1',
    'launch_morph_dev2_dev58.ps1',
    'matlab\scenes\make_paired_dev58_scene.m',
    'configs\scene_specs_dev58.csv',
    'configs\scene_specs_dev58_receipt.json',
    'manifest\DEV58_PREPARED_MANIFEST_B72_V2.json',
    'review\B72_LINEAGE_INDEPENDENT_REVIEW.md',
    'review\PRIOR_T2_RAW_REUSE_REVIEW_V2.json',
    'review\PRIOR_T3_RAW_REUSE_REVIEW.json',
    'STATE_ZH.md'
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $entry $relative) -PathType Leaf)) { throw "Required file missing: $relative" }
}

$manifest = Get-Content -Raw -LiteralPath (Join-Path $entry 'manifest\DEV58_PREPARED_MANIFEST_B72_V2.json') | ConvertFrom-Json
$csv = @(Import-Csv -LiteralPath (Join-Path $entry 'configs\scene_specs_dev58.csv'))
if ($manifest.schema -ne 'MORPH_DEV2_DEV58_PREPARED_MANIFEST_V1' -or $manifest.scenes.Count -ne 58 -or
    $csv.Count -ne 58 -or @($csv.scene_id | Select-Object -Unique).Count -ne 58 -or
    $manifest.plant_calls -ne 0 -or $manifest.training_runs -ne 0 -or $manifest.TEST_accessed -ne $false -or
    @($csv | Where-Object { $_.scene_id -match 'TEST' -or $_.split -notin @('DEV','VAL') }).Count -ne 0) {
    throw 'No-Plant manifest or fixed 58-scene CSV scope failed.'
}
if ((@($csv.scene_id) -join ',') -ne (@($manifest.scenes.scene_id) -join ',')) { throw 'Manifest/CSV scene ordering differs.' }

$runner = Get-Content -Raw -LiteralPath (Join-Path $entry 'run_morph_dev2_dev58.m')
$scene = Get-Content -Raw -LiteralPath (Join-Path $entry 'matlab\scenes\make_paired_dev58_scene.m')
$prep = Get-Content -Raw -LiteralPath (Join-Path $entry 'prepare_manifest_no_plant.m')
$writerCount = ([regex]::Matches($runner,'run_paired_observer_closed_loop\(')).Count
if ($writerCount -ne 1 -or -not $runner.Contains("run_paired_observer_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,candidateOpts)")) {
    throw 'Runner must contain exactly one candidate closed-loop call.'
}
if (-not $runner.Contains("load(bRawPath,'log')") -or -not $runner.Contains("'B_TRACEABLE_C3CORE_V1'") -or
    -not $runner.Contains("strcmp(bs.status,'RUN_COMPLETE_RAW_PENDING_AUDIT')") -or
    -not $runner.Contains('numel(lock.inputs)==11') -or -not $runner.Contains('runnerCalls==58') -or
    -not $runner.Contains('1160000') -or -not $runner.Contains('no_fixed_output_cap') -or
    -not $runner.Contains('if nargin<3,index=0;end') -or
    -not $runner.Contains("'runner_sha256',char(lock.wrapper.sha256)")) { throw 'Candidate/B reuse identity, wrapper SHA, budget, no-cap, or CSV writer checks are missing.' }
if ($runner.Contains("controller_options_dl1018(cfg,'B')") -or $runner.Contains('run_b_traceable_dev72') -or
    $runner.Contains('run_morph_dev2_screen12(') -or $runner.Contains('DL1018_TEST_')) {
    throw 'Runner contains a B/C5/screen12 rerun or TEST path.'
}
if ($scene.Contains('run_paired_observer_closed_loop') -or $scene.Contains('rk4_vehicle_step') -or
    $prep.Contains('run_paired_observer_closed_loop') -or $prep.Contains('DL1018_TEST_')) {
    throw 'No-Plant builder contains a closed-loop or TEST path.'
}
foreach ($file in @('build_candidate_lock_dev58.ps1','issue_root_release_dev58.ps1','build_candidate_lock_dev58_v2.ps1','issue_root_release_dev58_v2.ps1','launch_morph_dev2_dev58.ps1')) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $entry $file),[ref]$tokens,[ref]$errors)
    if ($errors.Count -ne 0) { throw "PowerShell parse failed: $file" }
}

$candidateLockPath = Join-Path $entry 'source_lock_morph_dev2_dev58_candidate.json'
if (Test-Path -LiteralPath $candidateLockPath) {
    $lock = Get-Content -Raw -LiteralPath $candidateLockPath | ConvertFrom-Json
    if ($lock.status -ne 'NOT_FROZEN' -or $lock.executed -ne $false -or $lock.closed_loop_runs_authorized -ne $false -or
        @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 11 -or
        @($lock.reused_candidate_raws).Count -ne 14 -or $lock.release_contract.no_fixed_output_cap -ne $true) {
        throw 'Candidate lock is not the expected frozen-inputs-only lock.'
    }
}
$candidateLockV2Path = Join-Path $entry 'source_lock_morph_dev2_dev58_candidate_v2.json'
if (Test-Path -LiteralPath $candidateLockV2Path) {
    $lockV2 = Get-Content -Raw -LiteralPath $candidateLockV2Path | ConvertFrom-Json
    if ($lockV2.status -ne 'NOT_FROZEN' -or $lockV2.executed -ne $false -or $lockV2.closed_loop_runs_authorized -ne $false -or
        @($lockV2.sources).Count -ne 39 -or @($lockV2.inputs).Count -ne 11 -or
        @($lockV2.reused_candidate_raws).Count -ne 14 -or $lockV2.release_contract.no_fixed_output_cap -ne $true) {
        throw 'V2 candidate lock is not the expected frozen-inputs-only lock.'
    }
}
Write-Output "DEV58_STATIC_PASS scenes=58 candidate_closed_loop_calls=1 new_B_runs=0 new_C5_runs=0 output_cap=none TEST=false"
