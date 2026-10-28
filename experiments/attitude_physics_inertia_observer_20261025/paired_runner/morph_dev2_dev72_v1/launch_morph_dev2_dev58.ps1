param(
    [Parameter(Mandatory=$true)][string]$ReleasePath,
    [Parameter(Mandatory=$true)][string]$ReleaseSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }

$entry = $PSScriptRoot
$matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$ReleasePath = (Resolve-Path -LiteralPath $ReleasePath).Path
$ReleaseSha256 = $ReleaseSha256.ToLowerInvariant()
if ((Get-Sha $ReleasePath) -ne $ReleaseSha256) { throw 'Root release SHA mismatch.' }
$release = Get-Content -Raw -LiteralPath $ReleasePath | ConvertFrom-Json
if ($release.schema -ne 'PAIRED_MORPH_DEV2_DEV58_ROOT_RELEASE_V1' -or $release.approved -ne $true -or
    $release.scope -ne 'MORPH_DEV2_DEV58' -or $release.max_runner_calls -ne 58 -or
    $release.max_transitions -ne 1160000 -or $release.no_fixed_output_cap -ne $true -or
    $release.minimum_free_bytes -ne 32212254720 -or $release.training_authorized -ne $false -or
    $release.TEST_authorized -ne $false -or $release.retry_authorized -ne $false -or
    $release.comparator -ne 'B_TRACEABLE_C3CORE_V1' -or (@($release.arm_order) -join ',') -ne 'candidate' -or
    @($release.scene_ids).Count -ne 58) { throw 'Release does not authorize the frozen candidate-only DEV58 stage.' }

$lockPath = (Resolve-Path -LiteralPath $release.source_lock_path).Path
if ((Get-Sha $lockPath) -ne ([string]$release.source_lock_sha256).ToLowerInvariant()) { throw 'Frozen source-lock SHA mismatch.' }
$lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
if ($lock.schema -ne 'SOURCE_LOCK_MORPH_DEV2_DEV58_V1' -or $lock.status -ne 'FROZEN_INPUTS' -or
    $lock.executed -ne $false -or $lock.closed_loop_runs_authorized -ne $false -or
    $lock.root_release_issued -ne $true -or $lock.manifest.sha256 -ne $release.manifest_sha256 -or
    @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 11 -or
    @($lock.reused_candidate_raws).Count -ne 14) { throw 'Frozen DEV58 source lock mismatch.' }
foreach ($record in @($lock.sources)+@($lock.inputs)+@($lock.scene_inputs)+@(
        $lock.wrapper,$lock.launcher,$lock.checker,$lock.taskbook,$lock.state,$lock.scene_builder,
        $lock.manifest_generator,$lock.builder,$lock.addendum,$lock.lineage_review,$lock.release_builder,
        $lock.manifest,$lock.reference_screen12_source_lock)) {
    if ((Get-Sha ([string]$record.path)) -ne ([string]$record.sha256).ToLowerInvariant()) {
        throw "Locked input SHA mismatch: $($record.path)"
    }
}
foreach ($record in $lock.reused_candidate_raws) {
    if ((Get-Sha $record.raw_path) -ne $record.raw_sha256.ToLowerInvariant() -or
        (Get-Sha $record.status_path) -ne $record.status_sha256.ToLowerInvariant()) {
        throw "Prior candidate raw/status changed: $($record.scene_id)"
    }
    if ($record.review_path -and (Get-Sha $record.review_path) -ne $record.review_sha256.ToLowerInvariant()) {
        throw "Prior candidate review changed: $($record.scene_id)"
    }
}
if ((Get-Sha $matlab) -ne '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9') {
    throw 'MATLAB R2025b executable SHA mismatch.'
}
if ((Get-PSDrive -Name C).Free -lt [long]$release.minimum_free_bytes) { throw 'C: free space is below 30 GiB.' }

$active = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(matlab|octave|octave-cli|octave-gui|wsl|wslhost|vmmemwsl)\.exe$'
})
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
$runningDistros = @()
if ($wsl) {
    $wslOutput = @(& $wsl.Source --list --running --quiet 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Could not verify running WSL distributions; launch refused.' }
    $runningDistros = @($wslOutput | ForEach-Object { ([string]$_).Replace([char]0,'').Trim() } | Where-Object { $_ })
}
if ($active.Count -gt 0 -or $runningDistros.Count -gt 0) {
    $details = $active | ForEach-Object { "$($_.Name) pid=$($_.ProcessId) $($_.CommandLine)" }
    $details += $runningDistros | ForEach-Object { "WSL distro=$_" }
    throw "Existing MATLAB/Octave/WSL process detected; nothing was stopped: $($details -join ' | ')"
}

$attemptId = [string]$release.attempt_id
if ($attemptId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$') { throw 'Invalid attempt_id.' }
$attempt = Join-Path $entry (Join-Path 'attempts' $attemptId)
if (Test-Path -LiteralPath $attempt) { throw 'Attempt directory already exists.' }
New-Item -ItemType Directory -Path $attempt | Out-Null
$preflight = [ordered]@{
    schema = 'MORPH_DEV2_DEV58_LAUNCH_PREFLIGHT_V1'
    release_path = $ReleasePath; release_sha256 = $ReleaseSha256
    source_lock_path = $lockPath; source_lock_sha256 = [string]$release.source_lock_sha256
    attempt_path = $attempt; free_bytes_before_start = (Get-PSDrive -Name C).Free
    active_simulator_processes = 0; running_wsl_distributions = $runningDistros; candidate_calls_authorized = 58
    new_B_runs = 0; new_C5_runs = 0; training = $false; TEST_accessed = $false
    command = "addpath('$($entry.Replace('\','/'))'); run_morph_dev2_dev58('$($ReleasePath.Replace('\','/'))','$ReleaseSha256','$($attempt.Replace('\','/'))');"
    started_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
}
[IO.File]::WriteAllText((Join-Path $attempt 'launcher_preflight.json'),(ConvertTo-Json -InputObject $preflight -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
& $matlab -batch $preflight.command *> (Join-Path $attempt 'matlab_console.log')
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) { throw "MATLAB runner exited $exitCode. Preserve the attempt; review batch_status.json and matlab_console.log." }
Write-Output "DEV58_RUN_COMPLETE attempt=$attempt calls=58 training=0 TEST=false"
