[CmdletBinding()]
param([switch]$Once)

# Read-only training watcher. It waits for the formal run to finish, then archives
# and CPU-audits the selected best checkpoint before the frozen no-Plant parity gate.
# It never starts/stops training, releases Plant, or reads TEST data.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskRoot = (Resolve-Path $PSScriptRoot).Path
$TrainingDir = Join-Path $TaskRoot 'training_v2_teacher_distill'
$AuditDir = Join-Path $TrainingDir 'checkpoint_audits'
$ProgressPath = Join-Path $TrainingDir 'training_progress.json'
$CheckpointPath = Join-Path $TrainingDir 'best.pt'
$HistoryPath = Join-Path $TrainingDir 'training_progress_history.jsonl'
$ManifestPath = Join-Path $TaskRoot 'dataset_v4_teacher_distill\DATASET_MANIFEST_v2.json'
$TrainerPath = Join-Path $TaskRoot 'train_tcn_teacher_v2.py'
$AuditScript = Join-Path $TaskRoot 'audit_tcn_teacher_checkpoint_val.py'
$Exporter = Join-Path $TaskRoot 'export_tcn_teacher_parity_batch_v3.py'
$ParityReport = Join-Path $TrainingDir 'MATLAB_PYTHON_PARITY_BATCH_V3.json'
$MonitorStatusPath = Join-Path $TaskRoot 'training_gate_monitor_status_v1.json'
$MonitorLogPath = Join-Path $AuditDir 'training_gate_monitor_v1.jsonl'
$Python = 'C:\ProgramData\anaconda3\python.exe'
$Matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$ExpectedPid = 20056
$PollSeconds = 30

function Get-Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Read-Progress {
    Get-Content -LiteralPath $ProgressPath -Raw | ConvertFrom-Json
}

function Write-Status([string]$Status, [object]$Progress, [int]$LastAudited, [object]$Extra = $null) {
    $value = [ordered]@{
        schema = 'DL1018_TCN_TRAINING_GATE_MONITOR_V1'
        status = $Status
        updated_local = Get-Date -Format 'yyyy/MM/dd HH:mm:ss'
        formal_training_status = $Progress.status
        completed_steps = [int]$Progress.completed_steps
        target_steps = [int]$Progress.target_steps
        best_step = [int]$Progress.best_step
        last_audited_best_step = $LastAudited
        progress_sha256 = Get-Sha256 $ProgressPath
        plant_calls = 0
        test_data_read = $false
    }
    if ($null -ne $Extra) { $value['result'] = $Extra }
    $tmp = $MonitorStatusPath + '.tmp'
    $json = ConvertTo-Json -InputObject $value -Depth 12
    [System.IO.File]::WriteAllText($tmp, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $MonitorStatusPath -Force
}

function Write-Log([object]$Value) {
    $line = ConvertTo-Json -InputObject $Value -Compress -Depth 12
    Add-Content -LiteralPath $MonitorLogPath -Value $line -Encoding utf8NoBOM
}

function Assert-FrozenInputs {
    foreach ($path in @($ProgressPath, $CheckpointPath, $ManifestPath, $TrainerPath, $AuditScript, $Exporter)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required frozen input is missing: $path" }
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.status -ne 'PASS' -or $manifest.test_data_read -ne $false -or
        $manifest.plant_truth_read -ne $false -or $manifest.nominal_inertia_read -ne $false -or
        $manifest.split_counts.TRAIN -ne 768 -or $manifest.split_counts.VAL -ne 48) {
        throw 'Frozen dataset manifest is not the expected TRAIN/VAL-only, no-Plant PASS.'
    }
}

function Assert-TrainingProcess([object]$Progress) {
    if ($Progress.status -ne 'RUNNING') { return }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ExpectedPid" -ErrorAction SilentlyContinue
    if ($null -eq $proc) { throw 'Formal training progress says RUNNING but PID 20056 is missing; do not restart automatically.' }
    if ($proc.Name -ne 'python.exe' -or $proc.CommandLine -notlike '*train_tcn_teacher_v2.py*') {
        throw 'PID 20056 no longer identifies the frozen formal teacher-training command.'
    }
}

function Get-LastAuditedBestStep {
    $steps = [System.Collections.Generic.List[int]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $AuditDir -Filter 'best_step_*.pt' -File) {
        if ($file.BaseName -notmatch '^best_step_(\d+)$') { continue }
        $step = [int]$Matches[1]
        $reportPath = Join-Path $AuditDir "audit_step_$step.json"
        if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) { throw "Archived checkpoint $step has no CPU audit report." }
        $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        if ($report.status -ne 'PASS_READ_ONLY_VAL48' -or $report.checkpoint_step -ne $step -or
            $report.checkpoint_sha256 -ne (Get-Sha256 $file.FullName)) {
            throw "Archived checkpoint/audit identity failed for step $step."
        }
        $steps.Add($step)
    }
    if ($steps.Count -eq 0) { return 0 }
    ($steps | Measure-Object -Maximum).Maximum
}

function Assert-ExistingBest([int]$Step) {
    $archive = Join-Path $AuditDir "best_step_$Step.pt"
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Current best checkpoint $Step is not archived." }
    if ((Get-Sha256 $archive) -ne (Get-Sha256 $CheckpointPath)) { throw "Current best.pt differs from archived step $Step." }
}

function Invoke-BestAudit([int]$Step) {
    $checkpointHash = Get-Sha256 $CheckpointPath
    $archive = Join-Path $AuditDir "best_step_$Step.pt"
    $reportPath = Join-Path $AuditDir "audit_step_$Step.json"
    if ((Test-Path -LiteralPath $archive) -or (Test-Path -LiteralPath $reportPath)) {
        throw "Refusing to overwrite partial or existing audit artifacts for step $Step."
    }
    Copy-Item -LiteralPath $CheckpointPath -Destination $archive
    if ((Get-Sha256 $archive) -ne $checkpointHash) { throw "Checkpoint copy SHA mismatch at step $Step." }
    Start-Sleep -Seconds 2
    $progressBefore = Read-Progress
    if ([int]$progressBefore.best_step -ne $Step -or (Get-Sha256 $CheckpointPath) -ne $checkpointHash) {
        throw "Best checkpoint changed during archive at step $Step; audit withheld."
    }
    $lines = & $Python $AuditScript
    if ($LASTEXITCODE -ne 0) { throw "Read-only checkpoint auditor exited $LASTEXITCODE at step $Step." }
    $text = $lines -join "`n"
    $report = $text | ConvertFrom-Json
    if ($report.status -ne 'PASS_READ_ONLY_VAL48' -or $report.checkpoint_step -ne $Step -or
        $report.checkpoint_sha256 -ne $checkpointHash -or $report.test_data_read -ne $false -or
        $report.plant_data_read -ne $false -or $report.writes_to_model_or_dataset -ne $false) {
        throw "Read-only VAL48 audit failed or does not match step $Step."
    }
    if ((Get-Sha256 $CheckpointPath) -ne $checkpointHash) { throw "best.pt changed during audit at step $Step." }
    [System.IO.File]::WriteAllText($reportPath, $text + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Write-Log ([ordered]@{time=(Get-Date -Format 'o');event='BEST_CHECKPOINT_AUDITED';step=$Step;checkpoint_sha256=$checkpointHash;report_sha256=(Get-Sha256 $reportPath);status=$report.status})
    Write-Output "AUDITED_BEST_STEP=$Step SHA256=$checkpointHash"
}

function Invoke-BatchParity {
    $progress = Read-Progress
    $configPath = Join-Path $TrainingDir 'training_config.json'
    if ($progress.status -ne 'PASS' -or [int]$progress.completed_steps -ne 60000 -or
        -not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw 'Batch parity is held until the formal 60,000-step run reports PASS.'
    }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($config.status -ne 'PASS' -or $config.test_data_read -ne $false) { throw 'Training config is not a clean PASS.' }
    $vectors = Join-Path $TrainingDir 'parity_vectors_batch_v3.mat'
    $selectionPath = Join-Path $TrainingDir 'parity_vectors_batch_v3.json'
    if ((Test-Path -LiteralPath $vectors) -or (Test-Path -LiteralPath $selectionPath) -or
        (Test-Path -LiteralPath $ParityReport)) { throw 'Refusing to overwrite existing batch-parity artifacts.' }

    $exportLines = & $Python $Exporter
    if ($LASTEXITCODE -ne 0) { throw "Batch parity exporter exited $LASTEXITCODE." }
    $selection = (($exportLines -join "`n") | ConvertFrom-Json)
    if ($selection.status -ne 'PASS' -or $selection.sample_count -ne 240 -or
        $selection.scene_count -ne 48 -or $selection.sequence_step_count -ne 1999 -or
        $selection.training_split_only -ne $true -or $selection.test_data_read -ne $false -or
        $selection.plant_called -ne $false) { throw 'Python exporter did not produce the frozen 240-window VAL selection.' }

    $env:MATLAB_PREFDIR = Join-Path $TaskRoot 'matlab_prefdir_parity_monitor'
    $matlabCommand = "addpath('matlab'); report=verify_tcn_teacher_parity_batch_v3; assert(strcmp(report.status,'PASS'));"
    & $Matlab -batch $matlabCommand
    if ($LASTEXITCODE -ne 0) { throw "MATLAB batch-parity verifier exited $LASTEXITCODE." }
    $report = Get-Content -LiteralPath $ParityReport -Raw | ConvertFrom-Json
    if ($report.status -ne 'PASS' -or $report.sample_count -ne 240 -or $report.scene_count -ne 48 -or
        $report.sequence_step_count -ne 1999 -or $report.max_abs_error -gt 1e-5 -or
        $report.test_data_read -ne $false -or $report.plant_called -ne $false) {
        throw 'MATLAB batch parity report does not satisfy the frozen no-Plant gate.'
    }
    [ordered]@{status=$report.status;max_abs_error=$report.max_abs_error;sample_count=$report.sample_count;scene_count=$report.scene_count;sequence_step_count=$report.sequence_step_count;report_sha256=(Get-Sha256 $ParityReport);plant_called=$false;test_data_read=$false}
}

try {
    Assert-FrozenInputs
    $progress = Read-Progress
    $lastAudited = Get-LastAuditedBestStep
    Assert-TrainingProcess $progress
    if ([int]$progress.best_step -lt $lastAudited) { throw 'Progress best_step is older than the latest archived audit.' }
    if ([int]$progress.best_step -eq $lastAudited) { Assert-ExistingBest $lastAudited }

    if ($Once) {
        [pscustomobject]@{status='PASS_MONITOR_PREFLIGHT';formal_status=$progress.status;completed_steps=$progress.completed_steps;best_step=$progress.best_step;last_audited_best_step=$lastAudited;next_step=if($progress.status -eq 'PASS'){'run_batch_parity'}else{'watch_without_restarting'};plant_calls=0;test_data_read=$false} | ConvertTo-Json -Compress
        return
    }
    if (Test-Path -LiteralPath $MonitorStatusPath) { throw 'Monitor status already exists; inspect it before starting another watcher.' }
    Write-Status 'MONITORING' $progress $lastAudited
    Write-Log ([ordered]@{time=(Get-Date -Format 'o');event='MONITOR_STARTED';pid=$PID;formal_pid=$ExpectedPid;progress_step=$progress.completed_steps;best_step=$progress.best_step;plant_calls=0;test_data_read=$false})
    Write-Output "MONITOR_READY: formal=$($progress.completed_steps)/$($progress.target_steps), audited_best=$lastAudited; no training or Plant calls will be started."

    while ($true) {
        $progress = Read-Progress
        Assert-TrainingProcess $progress
        if ($progress.status -eq 'FAILED') { throw 'Formal training reported FAILED; no automatic restart.' }
        Write-Status 'MONITORING' $progress $lastAudited

        if ($progress.status -eq 'PASS' -and [int]$progress.completed_steps -eq 60000) {
            if ([int]$progress.best_step -gt $lastAudited) {
                Invoke-BestAudit ([int]$progress.best_step)
                $lastAudited = [int]$progress.best_step
            }
            elseif ([int]$progress.best_step -eq $lastAudited -and $lastAudited -gt 0) {
                Assert-ExistingBest $lastAudited
            }
            else { throw 'Final selected best checkpoint has no auditable step.' }
            $result = Invoke-BatchParity
            Write-Status 'PARITY_PASS_NO_PLANT_STOPPED' $progress $lastAudited $result
            Write-Log ([ordered]@{time=(Get-Date -Format 'o');event='BATCH_PARITY_PASS';result=$result;plant_calls=0;test_data_read=$false;next='main-model-review-before-no-Plant-release-or-Plant-call'})
            Write-Output "PARITY_PASS_NO_PLANT: max_abs_error=$($result.max_abs_error); stopped before any Plant release/call."
            return
        }
        Start-Sleep -Seconds $PollSeconds
    }
}
catch {
    try {
        $progress = Read-Progress
        $lastAudited = Get-LastAuditedBestStep
        Write-Status 'FAILED_NO_RESTART_NO_PLANT' $progress $lastAudited ([ordered]@{error=$_.Exception.Message})
        Write-Log ([ordered]@{time=(Get-Date -Format 'o');event='MONITOR_FAILURE';error=$_.Exception.Message;plant_calls=0;test_data_read=$false})
    } catch { }
    Write-Error $_
    exit 1
}
