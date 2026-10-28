param(
    [Parameter(Mandatory = $true)][string]$ReleasePath,
    [Parameter(Mandatory = $true)][string]$ReleaseSha256
)
# One hidden MATLAB batch, serial six-call ceiling. A root release is mandatory.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$entry = $PSScriptRoot
$root = Split-Path -Parent $entry
$matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$wrapper = Join-Path $entry 'run_dev3_paired.m'
function ShaFile([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function SaveNewUtf8([string]$path, [string]$content) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($content)
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function ActiveMatlabProcesses {
    @(Get-CimInstance Win32_Process -Filter "name = 'MATLAB.exe' or name = 'octave.exe' or name = 'octave-cli.exe'" |
        Select-Object ProcessId, Name, ExecutablePath)
}
function QuoteMatlab([string]$value) { $value.Replace("'", "''").Replace('\', '/') }
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
$ReleasePath = (Resolve-Path -LiteralPath $ReleasePath).Path
$ReleaseSha256 = $ReleaseSha256.ToLowerInvariant()
if ($ReleaseSha256 -notmatch '^[0-9a-f]{64}$' -or (ShaFile $ReleasePath) -ne $ReleaseSha256) {
    throw 'Root release SHA differs.'
}
$release = Get-Content -Raw -LiteralPath $ReleasePath | ConvertFrom-Json
if ($release.schema -ne 'PAIRED_DEV3_ROOT_RELEASE_V1' -or
    $release.approved -ne $true -or
    $release.scope -ne 'SIX_FRESH_DEV3_PAIRED_RUNS' -or
    $release.max_runner_calls -ne 6 -or
    $release.max_new_bytes -ne 1073741824 -or
    $release.minimum_free_bytes -ne 32212254720 -or
    $release.attempt_id -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$' -or
    @($release.scene_ids).Count -ne 3 -or
    @($release.arm_order).Count -ne 2 -or
    (@($release.scene_ids) -join ',') -ne 'DL1018_DEV_T1_C00_W03,DL1018_DEV_T2_C02_W15,DL1018_DEV_T3_C10_W11' -or
    (@($release.arm_order) -join ',') -ne 'baseline,candidate') {
    throw 'Root release scope, order, or budget differs.'
}
$sourceLockPath = (Resolve-Path -LiteralPath $release.source_lock_path).Path
$sourceLockSha = [string]$release.source_lock_sha256
if ($sourceLockSha -notmatch '^[0-9a-f]{64}$' -or (ShaFile $sourceLockPath) -ne $sourceLockSha) {
    throw 'Final source-lock SHA differs.'
}
$lock = Get-Content -Raw -LiteralPath $sourceLockPath | ConvertFrom-Json
if ($lock.schema -ne 'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE' -or
    $lock.status -ne 'NOT_FROZEN' -or $lock.executed -ne $false -or
    $lock.closed_loop_runs_authorized -ne $false -or
    $lock.preflight_candidate_sha256 -ne 'ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2' -or
    $release.candidate_input_lock_sha256 -ne $lock.preflight_candidate_sha256 -or
    (ShaFile $lock.preflight_candidate_path) -ne $lock.preflight_candidate_sha256 -or
    (ShaFile $lock.wrapper.path) -ne $lock.wrapper.sha256 -or
    (ShaFile $lock.launcher.path) -ne $lock.launcher.sha256 -or
    (ShaFile $lock.checker.path) -ne $lock.checker.sha256 -or
    (ShaFile $lock.audit.path) -ne $lock.audit.sha256 -or
    (ShaFile $lock.taskbook.path) -ne $lock.taskbook.sha256 -or
    (ShaFile $lock.state.path) -ne $lock.state.sha256 -or
    $lock.wrapper.path -ne $wrapper -or $lock.launcher.path -ne $PSCommandPath -or
    @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 17) {
    throw 'Final source lock, entry, or candidate identity differs.'
}
if ((ShaFile $matlab) -ne '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9') {
    throw 'MATLAB R2025b executable SHA differs.'
}
foreach ($item in @($lock.sources) + @($lock.inputs)) {
    if ((ShaFile $item.path) -ne $item.sha256) { throw "Source/input differs: $($item.path)" }
}
$attempts = Join-Path $entry 'attempts'
$attemptDir = Join-Path $attempts $release.attempt_id
if (Test-Path -LiteralPath $attemptDir) { throw 'Attempt directory already exists; no resume or retry.' }
if ([IO.DriveInfo]::new('C').AvailableFreeSpace -lt $release.minimum_free_bytes) {
    throw 'C drive has less than 30 GiB free.'
}
$preexisting = @(ActiveMatlabProcesses)
while ($preexisting.Count -gt 0) {
    Write-Output "WAITING_FOR_EXISTING_MATLAB_OR_OCTAVE count=$($preexisting.Count)"
    Start-Sleep -Seconds 15
    $preexisting = @(ActiveMatlabProcesses)
}
if (Test-Path -LiteralPath $attemptDir) { throw 'Attempt appeared while waiting; no duplicate launch.' }
if (-not (Test-Path -LiteralPath $attempts)) {
    New-Item -ItemType Directory -Path $attempts -ErrorAction Stop | Out-Null
}
New-Item -ItemType Directory -Path $attemptDir -ErrorAction Stop | Out-Null
$stdoutPath = Join-Path $attemptDir 'stdout.log'
$stderrPath = Join-Path $attemptDir 'stderr.log'
$commandPath = Join-Path $attemptDir 'command.json'
$exitPath = Join-Path $attemptDir 'exit_code.txt'
$receiptPath = Join-Path $attemptDir 'batch_receipt.json'
$batch = "addpath('$(QuoteMatlab $entry)');run_dev3_paired('$(QuoteMatlab $ReleasePath)','$(QuoteMatlab $ReleaseSha256)','$(QuoteMatlab $attemptDir)')"
$command = [ordered]@{
    launcher_invocation = @('pwsh','-NoProfile','-File',$PSCommandPath,'-ReleasePath',$ReleasePath,'-ReleaseSha256',$ReleaseSha256)
    executable = $matlab
    executable_sha256 = ShaFile $matlab
    arguments = @('-batch',$batch)
    working_directory = $root
    launcher = $PSCommandPath
    launcher_sha256 = ShaFile $PSCommandPath
    wrapper = $wrapper
    wrapper_sha256 = ShaFile $wrapper
    release_path = $ReleasePath
    release_sha256 = $ReleaseSha256
    source_lock_path = $sourceLockPath
    source_lock_sha256 = $sourceLockSha
}
SaveNewUtf8 $commandPath (($command | ConvertTo-Json -Depth 5) + "`n")
$started = $false
$exitCode = $null
try {
    $stdout = [IO.File]::Open($stdoutPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $stderr = [IO.File]::Open($stderrPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $process = $null
    try {
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $matlab
        $start.ArgumentList.Add('-batch')
        $start.ArgumentList.Add($batch)
        $start.WorkingDirectory = $root
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $process = [Diagnostics.Process]::Start($start)
        if ($null -eq $process) { throw 'MATLAB process did not start.' }
        $started = $true
        Write-Output "DEV3_BATCH_STARTED pid=$($process.Id) attempt=$attemptDir"
        $stdoutCopy = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrCopy = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutCopy,$stderrCopy))
        $exitCode = $process.ExitCode
    } finally {
        $stdout.Dispose(); $stderr.Dispose()
        if ($null -ne $process) { $process.Dispose() }
        if ($started) { SaveNewUtf8 $exitPath ("$exitCode`n") }
    }
    if ($exitCode -ne 0) { throw "MATLAB exited $exitCode; preserved attempt=$attemptDir" }
    $batchStatusPath = Join-Path $attemptDir 'batch_status.json'
    if (-not (Test-Path -LiteralPath $batchStatusPath)) { throw 'Missing batch_status.json.' }
    $batchStatus = Get-Content -Raw -LiteralPath $batchStatusPath | ConvertFrom-Json
    if ($batchStatus.status -ne 'DEV3_SCREEN_PASS' -or $batchStatus.runner_invocation_count -ne 6) {
        throw 'Batch did not report six-call DEV3 screen pass.'
    }
    if ((ShaFile $ReleasePath) -ne $ReleaseSha256 -or (ShaFile $sourceLockPath) -ne $sourceLockSha) {
        throw 'Release or source lock changed during batch.'
    }
    foreach ($item in @($lock.sources) + @($lock.inputs)) {
        if ((ShaFile $item.path) -ne $item.sha256) { throw "Source/input changed during batch: $($item.path)" }
    }
    $receipt = [ordered]@{
        schema = 'PAIRED_DEV3_BATCH_RECEIPT_V1'
        status = 'DEV3_SCREEN_PASS'
        release_sha256 = $ReleaseSha256
        source_lock_sha256 = $sourceLockSha
        candidate_input_lock_sha256 = $lock.preflight_candidate_sha256
        command_path = $commandPath
        command_sha256 = ShaFile $commandPath
        matlab_start_count = 1
        runner_invocation_count = 6
        exit_code = $exitCode
        batch_status_path = $batchStatusPath
        batch_status_sha256 = ShaFile $batchStatusPath
        stdout_path = $stdoutPath
        stdout_sha256 = ShaFile $stdoutPath
        stderr_path = $stderrPath
        stderr_sha256 = ShaFile $stderrPath
    }
    SaveNewUtf8 $receiptPath (($receipt | ConvertTo-Json -Depth 8) + "`n")
    Write-Output "DEV3_BATCH_DONE receipt=$receiptPath sha256=$(ShaFile $receiptPath)"
} catch {
    $reason = $_.Exception.Message
    $markers = @(Get-ChildItem -LiteralPath $attemptDir -Recurse -File -Filter 'runner_invocation.json')
    $batchStatusPath = Join-Path $attemptDir 'batch_status.json'
    $failure = [ordered]@{
        schema = 'PAIRED_DEV3_BATCH_FAILURE_V1'
        status = 'STOPPED_ON_FAILURE'
        reason = $reason
        release_sha256 = $ReleaseSha256
        source_lock_sha256 = $sourceLockSha
        candidate_input_lock_sha256 = $lock.preflight_candidate_sha256
        command_path = $commandPath
        command_sha256 = ShaFile $commandPath
        matlab_start_count = [int]$started
        runner_invocation_marker_count = $markers.Count
        exit_code = $exitCode
        batch_status_path = $(if (Test-Path -LiteralPath $batchStatusPath) { $batchStatusPath } else { $null })
        batch_status_sha256 = $(if (Test-Path -LiteralPath $batchStatusPath) { ShaFile $batchStatusPath } else { $null })
        stdout_path = $(if (Test-Path -LiteralPath $stdoutPath) { $stdoutPath } else { $null })
        stdout_sha256 = $(if (Test-Path -LiteralPath $stdoutPath) { ShaFile $stdoutPath } else { $null })
        stderr_path = $(if (Test-Path -LiteralPath $stderrPath) { $stderrPath } else { $null })
        stderr_sha256 = $(if (Test-Path -LiteralPath $stderrPath) { ShaFile $stderrPath } else { $null })
    }
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        SaveNewUtf8 $receiptPath (($failure | ConvertTo-Json -Depth 8) + "`n")
    }
    throw "DEV3 batch failed: $reason; receipt=$receiptPath"
}
