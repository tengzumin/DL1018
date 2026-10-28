param(
    [Parameter(Mandatory = $true)][string]$ReleasePath,
    [Parameter(Mandatory = $true)][string]$ReleaseSha256
)
# A root-approved release path/SHA is required; performance metrics never gate T3 continuation.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$entry = $PSScriptRoot
$root = Split-Path -Parent $entry
$matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$wrapper = Join-Path $entry 'run_morph_dev2_t3_continuation.m'
$candidateLockPath = Join-Path $entry 'source_lock_morph_dev2_t3_continuation_v1_candidate.json'
$attemptDir = $null
$receiptPath = $null
$started = $false
$exitCode = $null
$batchStatusPath = $null
$stdoutPath = $null
$stderrPath = $null
$commandPath = $null
$runTimer = [Diagnostics.Stopwatch]::StartNew()

function ShaFile([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function SaveNewUtf8([string]$path, [string]$content) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($content)
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function TreeBytes([string]$path) {
    [long]$total = 0
    foreach ($file in Get-ChildItem -LiteralPath $path -Recurse -File -Force) { $total += $file.Length }
    return $total
}
function ActiveMatlabProcesses {
    @(Get-CimInstance Win32_Process -Filter "name = 'MATLAB.exe' or name = 'octave.exe' or name = 'octave-cli.exe'" |
        Select-Object ProcessId, Name, ExecutablePath)
}
function QuoteMatlab([string]$value) { $value.Replace("'", "''").Replace('\', '/') }
function AssertFile([string]$path, [string]$sha, [string]$label) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (ShaFile $path) -ne $sha) {
        throw "$label SHA differs: $path"
    }
}
function VerifyInputs($lock, $candidate, $release, $releaseSha, $sourceLockPath, [switch]$VerifyPriorRaw) {
    AssertFile $ReleasePath $releaseSha 'Root release'
    AssertFile $sourceLockPath ([string]$release.source_lock_sha256) 'Frozen source lock'
    AssertFile ([string]$lock.candidate_input_lock_path) ([string]$lock.candidate_input_lock_sha256) 'Candidate input lock'
    AssertFile ([string]$lock.preflight_candidate_path) ([string]$lock.preflight_candidate_sha256) 'Preflight candidate'
    if ((ShaFile ([string]$lock.candidate_input_lock_path)) -ne (ShaFile $candidateLockPath)) { throw 'Candidate lock path differs.' }
    foreach ($item in @($lock.sources) + @($lock.inputs)) { AssertFile ([string]$item.path) ([string]$item.sha256) 'Source/input' }
    foreach ($item in @($lock.prior_a02_root_review_evidence)) { AssertFile ([string]$item.path) ([string]$item.sha256) 'Prior A02 root-review evidence' }
    if ($VerifyPriorRaw) {
        foreach ($item in @($lock.prior_a02_raw_manifest)) {
            AssertFile ([string]$item.path) ([string]$item.sha256) 'Prior A02 raw'
            if ([long](Get-Item -LiteralPath ([string]$item.path)).Length -ne [long]$item.bytes) {
                throw "Prior A02 raw length differs: $($item.path)"
            }
        }
    }
    foreach ($record in @($lock.wrapper,$lock.launcher,$lock.checker,$lock.taskbook,$lock.state)) {
        AssertFile ([string]$record.path) ([string]$record.sha256) 'Entry dependency'
    }
    if ((ShaFile $matlab) -ne '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9') {
        throw 'MATLAB R2025b executable SHA differs.'
    }
}
function SaveReceipt([string]$path, [System.Collections.IDictionary]$receipt, [string]$attemptPath,
    [switch]$RequireWithinBudget) {
    $receipt.new_bytes = TreeBytes $attemptPath
    for ($i = 0; $i -lt 4; $i++) {
        $payload = ($receipt | ConvertTo-Json -Depth 12) + "`n"
        $receipt.new_bytes = (TreeBytes $attemptPath) + [Text.UTF8Encoding]::new($false).GetByteCount($payload)
    }
    if ($RequireWithinBudget -and [long]$receipt.new_bytes -gt 1650000000) {
        throw 'New T3 continuation outputs exceeded 1,650,000,000 bytes.'
    }
    SaveNewUtf8 $path (($receipt | ConvertTo-Json -Depth 12) + "`n")
}
function EnsureFailureArtifacts([string]$attemptPath, [string]$reason) {
    $markerPaths = @(Get-ChildItem -LiteralPath $attemptPath -Recurse -File -Filter 'runner_invocation.json' -ErrorAction SilentlyContinue)
    $records = @()
    $csvRows = @()
    [long]$confirmedTransitions = 0
    $confirmedRuns = 0
    $unknown = 0
    foreach ($arm in @('baseline','candidate')) {
        $runDir = Join-Path $attemptPath ("01_DL1018_DEV_T3_C10_W11_$arm")
        $statusPath = Join-Path $runDir 'run_status.json'
        $status = $null
        if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
            try { $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json } catch { $status = $null }
        }
        $state = if ($null -ne $status) { [string]$status.status } elseif (Test-Path -LiteralPath (Join-Path $runDir 'runner_invocation.json')) { 'UNKNOWN_AFTER_INVOCATION' } else { 'NOT_RUN' }
        $score = if ($null -ne $status -and $null -ne $status.score) { $status.score } else { $null }
        $why = if ($null -ne $status -and $status.reason) { [string]$status.reason } else { '' }
        if ($null -ne $status -and $status.last_transition -is [ValueType]) {
            $count = [long]$status.last_transition
            if ($count -gt 0) { $confirmedRuns++ }
            $confirmedTransitions += $count
        } elseif ($state -ne 'NOT_RUN') { $unknown++ }
        $records += [ordered]@{ scene_id='DL1018_DEV_T3_C10_W11'; arm=$arm; status=$state; reason=$why; score=$score; run_dir=$runDir }
        $csvRows += [pscustomobject]@{
            scene_id='DL1018_DEV_T3_C10_W11'; arm=$arm; status=$state
            wall_seconds=$(if ($null -ne $status) { $status.wall_seconds } else { $null })
            q_rmse_m=$(if ($null -ne $score) { $score.q_rmse_m } else { $null })
            so3_rmse_rad=$(if ($null -ne $score) { $score.so3_rmse_rad } else { $null })
            delta_q_rmse_m=$(if ($null -ne $status -and $null -ne $status.delta_score) { $status.delta_score.q_rmse_m } else { $null })
            delta_so3_rmse_rad=$(if ($null -ne $status -and $null -ne $status.delta_score) { $status.delta_score.so3_rmse_rad } else { $null })
            reason=$why
        }
    }
    $artifactErrors = [Collections.Generic.List[string]]::new()
    $csvPath = Join-Path $attemptPath 'results.csv'
    if (-not (Test-Path -LiteralPath $csvPath)) {
        try { SaveNewUtf8 $csvPath (($csvRows | ConvertTo-Csv -NoTypeInformation | Out-String).TrimEnd() + "`n") }
        catch { $artifactErrors.Add("results.csv: $($_.Exception.Message)") }
    }
    $reportPath = Join-Path $attemptPath 'report.md'
    if (-not (Test-Path -LiteralPath $reportPath)) {
        try { SaveNewUtf8 $reportPath ("# MORPH_DEV2_T3_CONTINUATION: STOPPED_ON_FAILURE`n`nRunner markers: $($markerPaths.Count); confirmed runs: $confirmedRuns; confirmed transitions: $confirmedTransitions; unknown: $unknown.`n`nFailure: $reason`n") }
        catch { $artifactErrors.Add("report.md: $($_.Exception.Message)") }
    }
    $batchPath = Join-Path $attemptPath 'batch_status.json'
    if (-not (Test-Path -LiteralPath $batchPath)) {
        $batch = [ordered]@{
            schema='MORPH_DEV2_T3_CONTINUATION_BATCH_STATUS_V1'; scope='MORPH_DEV2_T3_CONTINUATION'
            status='STOPPED_ON_FAILURE'; runner_invocation_count=$markerPaths.Count
            confirmed_plant_runs=$confirmedRuns; confirmed_transitions=$confirmedTransitions
            unknown_plant_invocations=$unknown; training_run_count=0; performance_is_nongating=$true
            pair_completed=@($false); pair_safety_pass=@($false); results=$records
            failure_reason=$reason; artifact_errors=@($artifactErrors.ToArray())
            new_bytes=(TreeBytes $attemptPath); launcher_failure_artifacts=true
        }
        try { SaveNewUtf8 $batchPath (($batch | ConvertTo-Json -Depth 12) + "`n") }
        catch { $artifactErrors.Add("batch_status.json: $($_.Exception.Message)") }
    } else {
        try {
            $priorBatch = Get-Content -Raw -LiteralPath $batchPath | ConvertFrom-Json
            foreach ($item in @($priorBatch.artifact_errors)) { if ($item) { $artifactErrors.Add([string]$item) } }
        } catch { $artifactErrors.Add("batch_status.json unreadable: $($_.Exception.Message)") }
    }
    return ,$artifactErrors.ToArray()
}

try {
    if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required.' }
    $ReleasePath = (Resolve-Path -LiteralPath $ReleasePath).Path
    $ReleaseSha256 = $ReleaseSha256.ToLowerInvariant()
    if ($ReleaseSha256 -notmatch '^[0-9a-f]{64}$' -or (ShaFile $ReleasePath) -ne $ReleaseSha256) {
        throw 'Root release SHA differs.'
    }
    $release = Get-Content -Raw -LiteralPath $ReleasePath | ConvertFrom-Json
    if ($release.schema -ne 'PAIRED_MORPH_DEV2_T3_CONTINUATION_ROOT_RELEASE_V1' -or
        $release.approved -ne $true -or $release.scope -ne 'MORPH_DEV2_T3_CONTINUATION' -or
        $release.max_runner_calls -ne 2 -or $release.max_new_bytes -ne 1650000000 -or
        $release.prior_runner_calls -ne 2 -or $release.cumulative_runner_call_ceiling -ne 4 -or
        $release.minimum_free_bytes -ne 32212254720 -or
        $release.training_authorized -ne $false -or $release.TEST_authorized -ne $false -or
        $release.retry_authorized -ne $false -or
        $release.attempt_id -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$' -or
        (@($release.scene_ids) -join ',') -ne 'DL1018_DEV_T3_C10_W11' -or
        (@($release.arm_order) -join ',') -ne 'baseline,candidate') {
        throw 'Root release does not authorize exactly the single-scene T3 continuation scope.'
    }
    $sourceLockPath = (Resolve-Path -LiteralPath ([string]$release.source_lock_path)).Path
    $sourceLockSha = ([string]$release.source_lock_sha256).ToLowerInvariant()
    if ($sourceLockSha -notmatch '^[0-9a-f]{64}$' -or (ShaFile $sourceLockPath) -ne $sourceLockSha) {
        throw 'Frozen source-lock SHA differs.'
    }
    $lock = Get-Content -Raw -LiteralPath $sourceLockPath | ConvertFrom-Json
    $candidate = Get-Content -Raw -LiteralPath $candidateLockPath | ConvertFrom-Json
    if ($lock.schema -ne 'SOURCE_LOCK_MORPH_DEV2_T3_CONTINUATION_V1' -or
        $lock.status -ne 'FROZEN_INPUTS' -or $lock.executed -ne $false -or
        $lock.closed_loop_runs_authorized -ne $false -or
        $lock.candidate_input_lock_sha256 -ne $release.candidate_input_lock_sha256 -or
        $lock.candidate_input_lock_path -ne $candidateLockPath -or
        $lock.preflight_candidate_path -ne $candidate.preflight_candidate_path -or
        $candidate.schema -ne 'SOURCE_LOCK_MORPH_DEV2_T3_CONTINUATION_V1_CANDIDATE' -or
        $candidate.status -ne 'NOT_FROZEN' -or $candidate.executed -ne $false -or
        $candidate.closed_loop_runs_authorized -ne $false -or $candidate.scope -ne 'MORPH_DEV2_T3_CONTINUATION' -or
        $lock.preflight_candidate_sha256 -ne $candidate.preflight_candidate_sha256 -or
        $release.source_lock_sha256 -ne $sourceLockSha -or
        $release.candidate_input_lock_sha256 -ne $lock.candidate_input_lock_sha256 -or
        @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 17 -or
        @($candidate.sources).Count -ne 39 -or @($candidate.inputs).Count -ne 17 -or
        @($release.scene_ids).Count -ne 1) {
        throw 'Frozen lock or candidate identity differs from diagnostic scope.'
    }
    if ($lock.wrapper.path -ne $wrapper -or $lock.launcher.path -ne $PSCommandPath -or
        $lock.checker.path -ne (Join-Path $entry 'static_check_morph_dev2_t3_continuation.ps1') -or
        $lock.taskbook.path -ne (Join-Path $entry 'MORPH_DEV2_T3_CONTINUATION_TASKBOOK_v1_ZH.md') -or
        $lock.state.path -ne (Join-Path $entry 'STATE_ZH.md')) {
        throw 'Frozen lock does not bind this exact diagnostic entry.'
    }
    if (@($lock.diagnostic_scenes).Count -ne 1 -or
        (@($lock.diagnostic_scenes | ForEach-Object { $_.scene_id }) -join ',') -ne 'DL1018_DEV_T3_C10_W11' -or
        $lock.diagnostic_scenes[0].seed -ne 2026123971) {
        throw 'Frozen lock T3 continuation scene identity differs.'
    }
    for ($i = 0; $i -lt 39; $i++) {
        if ($lock.sources[$i].path -ne $candidate.sources[$i].path -or
            $lock.sources[$i].sha256 -ne $candidate.sources[$i].sha256 -or
            $lock.sources[$i].relative_path -ne $candidate.sources[$i].relative_path) { throw 'Frozen source list differs from candidate lock.' }
    }
    for ($i = 0; $i -lt 17; $i++) {
        if ($lock.inputs[$i].path -ne $candidate.inputs[$i].path -or
            $lock.inputs[$i].sha256 -ne $candidate.inputs[$i].sha256 -or
            $lock.inputs[$i].role -ne $candidate.inputs[$i].role) { throw 'Frozen input list differs from candidate lock.' }
    }
    for ($i = 0; $i -lt 1; $i++) {
        if ($lock.diagnostic_scenes[$i].scene_id -ne $candidate.diagnostic_scenes[$i].scene_id -or
            $lock.diagnostic_scenes[$i].seed -ne $candidate.diagnostic_scenes[$i].seed -or
            $lock.diagnostic_scenes[$i].scene_sha256 -ne $candidate.diagnostic_scenes[$i].scene_sha256 -or
            $lock.diagnostic_scenes[$i].spec_sha256 -ne $candidate.diagnostic_scenes[$i].spec_sha256 -or
            $lock.diagnostic_scenes[$i].metadata_sha256 -ne $candidate.diagnostic_scenes[$i].metadata_sha256) {
            throw 'Frozen diagnostic scene hashes differ from candidate lock.'
        }
    }
    VerifyInputs $lock $candidate $release $ReleaseSha256 $sourceLockPath
    $attempts = Join-Path $entry 'attempts'
    $attemptDir = Join-Path $attempts ([string]$release.attempt_id)
    if (Test-Path -LiteralPath $attemptDir) { throw 'Attempt directory already exists; no resume or retry.' }
    if ([IO.DriveInfo]::new('C').AvailableFreeSpace -lt [long]$release.minimum_free_bytes) {
        throw 'C drive has less than 30 GiB free.'
    }
    $preexisting = @(ActiveMatlabProcesses)
    while ($preexisting.Count -gt 0) {
        Write-Output "WAITING_FOR_EXISTING_MATLAB_OR_OCTAVE count=$($preexisting.Count)"
        Start-Sleep -Seconds 15
        $preexisting = @(ActiveMatlabProcesses)
    }
    VerifyInputs $lock $candidate $release $ReleaseSha256 $sourceLockPath -VerifyPriorRaw
    if (Test-Path -LiteralPath $attemptDir) { throw 'Attempt appeared while waiting; no duplicate launch.' }
    if (-not (Test-Path -LiteralPath $attempts)) { New-Item -ItemType Directory -Path $attempts | Out-Null }
    New-Item -ItemType Directory -Path $attemptDir -ErrorAction Stop | Out-Null
    $stdoutPath = Join-Path $attemptDir 'stdout.log'
    $stderrPath = Join-Path $attemptDir 'stderr.log'
    $commandPath = Join-Path $attemptDir 'command.json'
    $exitPath = Join-Path $attemptDir 'exit_code.txt'
    $receiptPath = Join-Path $attemptDir 'batch_receipt.json'
    $batchStatusPath = Join-Path $attemptDir 'batch_status.json'
    $batch = "addpath('$(QuoteMatlab $entry)');run_morph_dev2_t3_continuation('$(QuoteMatlab $ReleasePath)','$(QuoteMatlab $ReleaseSha256)','$(QuoteMatlab $attemptDir)')"
    $command = [ordered]@{
        launcher_invocation = @('pwsh','-NoProfile','-File',$PSCommandPath,'-ReleasePath',$ReleasePath,'-ReleaseSha256',$ReleaseSha256)
        executable = $matlab; executable_sha256 = ShaFile $matlab
        arguments = @('-batch',$batch); working_directory = $root
        launcher = $PSCommandPath; launcher_sha256 = ShaFile $PSCommandPath
        wrapper = $wrapper; wrapper_sha256 = ShaFile $wrapper
        release_path = $ReleasePath; release_sha256 = $ReleaseSha256
        source_lock_path = $sourceLockPath; source_lock_sha256 = $sourceLockSha
        candidate_input_lock_path = $candidateLockPath; candidate_input_lock_sha256 = ShaFile $candidateLockPath
    }
    SaveNewUtf8 $commandPath (($command | ConvertTo-Json -Depth 8) + "`n")
    $stdout = [IO.File]::Open($stdoutPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $stderr = [IO.File]::Open($stderrPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $process = $null
    try {
        $start = [Diagnostics.ProcessStartInfo]::new()
        $start.FileName = $matlab; $start.ArgumentList.Add('-batch'); $start.ArgumentList.Add($batch)
        $start.WorkingDirectory = $root; $start.UseShellExecute = $false; $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
        $process = [Diagnostics.Process]::Start($start)
        if ($null -eq $process) { throw 'MATLAB process did not start.' }
        $started = $true
        Write-Output "MORPH_DEV2_T3_CONTINUATION_STARTED pid=$($process.Id) attempt=$attemptDir"
        $stdoutCopy = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrCopy = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutCopy,$stderrCopy))
        $exitCode = $process.ExitCode
    } finally {
        $stdout.Dispose(); $stderr.Dispose()
        if ($null -ne $process) { $process.Dispose() }
        if ($started) { SaveNewUtf8 (Join-Path $attemptDir 'exit_code.txt') ("$exitCode`n") }
    }
    if ($exitCode -ne 0) { throw "MATLAB exited $exitCode; preserved attempt=$attemptDir" }
    if (-not (Test-Path -LiteralPath $batchStatusPath)) { throw 'Missing batch_status.json.' }
    $batchStatus = Get-Content -Raw -LiteralPath $batchStatusPath | ConvertFrom-Json
    if ($batchStatus.schema -ne 'MORPH_DEV2_T3_CONTINUATION_BATCH_STATUS_V1' -or
        $batchStatus.scope -ne 'MORPH_DEV2_T3_CONTINUATION' -or
        $batchStatus.status -ne 'MORPH_DEV2_T3_CONTINUATION_COMPLETE' -or
        $batchStatus.runner_invocation_count -ne 2 -or $batchStatus.confirmed_plant_runs -ne 2 -or
        $batchStatus.confirmed_transitions -ne 40000 -or $batchStatus.unknown_plant_invocations -ne 0 -or
        $batchStatus.training_run_count -ne 0 -or @($batchStatus.results).Count -ne 2 -or
        @($batchStatus.results | Where-Object { $_.status -ne 'COMPLETED_T3_CONTINUATION' }).Count -ne 2 -or
        @($batchStatus.artifact_errors).Count -ne 0 -or
        @($batchStatus.pair_completed | Where-Object { $_ -ne $true }).Count -ne 0 -or
        @($batchStatus.pair_safety_pass | Where-Object { $_ -ne $true }).Count -ne 0 -or
        $batchStatus.performance_is_nongating -ne $true -or
        -not (Test-Path -LiteralPath (Join-Path $attemptDir 'results.csv') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $attemptDir 'report.md') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $attemptDir 'pair_01_audit.json') -PathType Leaf)) {
        throw 'T3 continuation did not complete exactly two safe arms or has artifact errors.'
    }
    foreach ($scene in @('DL1018_DEV_T3_C10_W11')) {
        foreach ($arm in @('baseline','candidate')) {
            $runDir = Join-Path $attemptDir (('{0:D2}_{1}_{2}' -f 1,$scene,$arm))
            foreach ($name in @('run_raw.mat','run_status.json','run_start.json','runner_invocation.json','scene_audit.json')) {
                if (-not (Test-Path -LiteralPath (Join-Path $runDir $name) -PathType Leaf)) {
                    throw "Completed arm artifact missing: $runDir\$name"
                }
            }
            $runStatus = Get-Content -Raw -LiteralPath (Join-Path $runDir 'run_status.json') | ConvertFrom-Json
            $rawPath = Join-Path $runDir 'run_raw.mat'
            if ($runStatus.raw_path -ne $rawPath -or $runStatus.raw_sha256 -ne (ShaFile $rawPath) -or
                [long]$runStatus.raw_bytes -ne (Get-Item -LiteralPath $rawPath).Length -or
                $runStatus.status -ne 'COMPLETED_T3_CONTINUATION' -or $runStatus.runner_status -ne 'STABLE' -or
                $runStatus.last_transition -ne 20000 -or $runStatus.score.transitions -ne 20000 -or
                $runStatus.score.state_points -ne 20001 -or [string]$runStatus.safety_stop_reason -ne '' -or
                $runStatus.safety_gate.passed -ne $true) {
                throw "Raw identity differs from run_status.json: $rawPath"
            }
            if ($arm -eq 'candidate' -and
                ($runStatus.engineering_gate.passed -ne $true -or
                 $runStatus.score.motor_saturation_count -ne 0 -or
                 $runStatus.score.generalized_clip_count -ne 0 -or
                 $runStatus.engineering_gate.candidate_trace_checked -ne $true)) {
                throw "Candidate engineering/safety gate differs: $rawPath"
            }
        }
    }
    $pairAudit = Get-Content -Raw -LiteralPath (Join-Path $attemptDir 'pair_01_audit.json') | ConvertFrom-Json
    if ($pairAudit.schema -ne 'MORPH_DEV2_T3_CONTINUATION_PAIR_AUDIT_V1' -or
        $pairAudit.scope -ne 'MORPH_DEV2_T3_CONTINUATION' -or
        $pairAudit.scene_id -ne 'DL1018_DEV_T3_C10_W11' -or $pairAudit.status -ne 'RECORDED' -or
        $pairAudit.safety_gate.passed -ne $true -or $pairAudit.performance_metrics_are_nongating -ne $true -or
        $null -eq $pairAudit.delta_candidate_minus_baseline.q_rmse_m -or
        $null -eq $pairAudit.delta_candidate_minus_baseline.so3_rmse_rad) {
        throw 'T3 pair audit is absent, incomplete, or not descriptive-only.'
    }
    $actualMarkers = @(Get-ChildItem -LiteralPath $attemptDir -Recurse -File -Filter 'runner_invocation.json')
    if ($actualMarkers.Count -ne 2) { throw 'Expected exactly two T3 runner invocation markers.' }
    VerifyInputs $lock $candidate $release $ReleaseSha256 $sourceLockPath
    $receipt = [ordered]@{
        schema = 'MORPH_DEV2_T3_CONTINUATION_BATCH_RECEIPT_V1'; status = 'MORPH_DEV2_T3_CONTINUATION_COMPLETE'
        scope = 'MORPH_DEV2_T3_CONTINUATION'; release_sha256 = $ReleaseSha256
        source_lock_sha256 = $sourceLockSha; candidate_input_lock_sha256 = $lock.candidate_input_lock_sha256
        command_path = $commandPath; command_sha256 = ShaFile $commandPath
        matlab_start_count = 1; runner_invocation_count = 2; confirmed_plant_runs = 2
        confirmed_transitions = 40000; unknown_plant_invocations = 0; training_run_count = 0
        exit_code = $exitCode; batch_status_path = $batchStatusPath; batch_status_sha256 = ShaFile $batchStatusPath
        results_csv_path = (Join-Path $attemptDir 'results.csv'); results_csv_sha256 = ShaFile (Join-Path $attemptDir 'results.csv')
        report_path = (Join-Path $attemptDir 'report.md'); report_sha256 = ShaFile (Join-Path $attemptDir 'report.md')
        pair_audit_path = (Join-Path $attemptDir 'pair_01_audit.json'); pair_audit_sha256 = ShaFile (Join-Path $attemptDir 'pair_01_audit.json')
        raw_manifest = @(foreach ($arm in @('baseline','candidate')) {
            $runDir = Join-Path $attemptDir ("01_DL1018_DEV_T3_C10_W11_$arm")
            $runStatus = Get-Content -Raw -LiteralPath (Join-Path $runDir 'run_status.json') | ConvertFrom-Json
            [ordered]@{ arm=$arm; path=(Join-Path $runDir 'run_raw.mat'); sha256=$runStatus.raw_sha256; bytes=[long]$runStatus.raw_bytes }
        })
        stdout_path = $stdoutPath; stdout_sha256 = ShaFile $stdoutPath
        stderr_path = $stderrPath; stderr_sha256 = ShaFile $stderrPath
        batch_wall_seconds = [Math]::Round($runTimer.Elapsed.TotalSeconds, 3); new_bytes = 0
    }
    SaveReceipt $receiptPath $receipt $attemptDir -RequireWithinBudget
    Write-Output "MORPH_DEV2_T3_CONTINUATION_DONE receipt=$receiptPath sha256=$(ShaFile $receiptPath)"
} catch {
    $reason = $_.Exception.Message
    if ($null -ne $attemptDir -and (Test-Path -LiteralPath $attemptDir) -and
        $null -ne $receiptPath -and -not (Test-Path -LiteralPath $receiptPath)) {
        $failureArtifactErrors = @()
        try { $failureArtifactErrors = @(EnsureFailureArtifacts $attemptDir $reason) }
        catch { $failureArtifactErrors += "failure artifact persistence: $($_.Exception.Message)" }
        $markers = @(Get-ChildItem -LiteralPath $attemptDir -Recurse -File -Filter 'runner_invocation.json' -ErrorAction SilentlyContinue)
        $failure = [ordered]@{
            schema = 'MORPH_DEV2_T3_CONTINUATION_BATCH_FAILURE_V1'; status = 'STOPPED_ON_FAILURE'
            scope = 'MORPH_DEV2_T3_CONTINUATION'; reason = $reason
            release_sha256 = $(if (Test-Path -LiteralPath $ReleasePath) { ShaFile $ReleasePath } else { $null })
            source_lock_sha256 = $(if ($sourceLockPath) { ShaFile $sourceLockPath } else { $null })
            candidate_input_lock_sha256 = $(if (Test-Path -LiteralPath $candidateLockPath) { ShaFile $candidateLockPath } else { $null })
            command_path = $commandPath; command_sha256 = $(if ($commandPath -and (Test-Path -LiteralPath $commandPath)) { ShaFile $commandPath } else { $null })
            matlab_start_count = [int]$started; runner_invocation_marker_count = $markers.Count
            runner_invocation_count = $markers.Count; exit_code = $exitCode
            artifact_errors = @($failureArtifactErrors)
            batch_status_path = $(if ($batchStatusPath -and (Test-Path -LiteralPath $batchStatusPath)) { $batchStatusPath } else { $null })
            batch_status_sha256 = $(if ($batchStatusPath -and (Test-Path -LiteralPath $batchStatusPath)) { ShaFile $batchStatusPath } else { $null })
            stdout_path = $(if ($stdoutPath -and (Test-Path -LiteralPath $stdoutPath)) { $stdoutPath } else { $null })
            stdout_sha256 = $(if ($stdoutPath -and (Test-Path -LiteralPath $stdoutPath)) { ShaFile $stdoutPath } else { $null })
            stderr_path = $(if ($stderrPath -and (Test-Path -LiteralPath $stderrPath)) { $stderrPath } else { $null })
            stderr_sha256 = $(if ($stderrPath -and (Test-Path -LiteralPath $stderrPath)) { ShaFile $stderrPath } else { $null })
            batch_wall_seconds = [Math]::Round($runTimer.Elapsed.TotalSeconds, 3); new_bytes = 0
        }
        try { SaveReceipt $receiptPath $failure $attemptDir } catch { Write-Error "Could not persist failure receipt: $($_.Exception.Message)" }
    }
    throw "MORPH_DEV2 T3 continuation failed: $reason"
}
