param(
    [ValidateSet('PROBE','CONTINUE')][string] $Mode = 'PROBE',
    [switch] $ParentReviewed
)
$ErrorActionPreference = 'Stop'
$expDir = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $expDir)
$lockPath = Join-Path $expDir 'frozen_inputs.json'
$reportPath = Join-Path $expDir 'reports\preflight_round1.json'
$errors = [System.Collections.Generic.List[string]]::new()
$checked = [System.Collections.Generic.List[object]]::new()
$sceneEvidence = @()
$expectedIds = @()
$scenePayloadVerifierExitCode = $null
$scenePayloadVerifierOutput = ''

function Get-Sha256([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Check-Hash([string] $Label, [string] $Path, [string] $Expected) {
    try {
        $actual = Get-Sha256 $Path
        $ok = $actual -eq $Expected.ToLowerInvariant()
        $checked.Add([pscustomobject]@{ label=$Label; path=$Path; expected=$Expected; actual=$actual; pass=$ok })
        if (-not $ok) { $errors.Add("SHA256 mismatch: $Label ($Path)") }
    } catch { $errors.Add($_.Exception.Message) }
}

try {
    if (-not $ParentReviewed) { $errors.Add('A fresh parent-review marker is required for every preflight mode.') }
    $lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json -DateKind String
    if ($lock.schema -ne 'FROZEN_W0_SCREEN_INPUTS_V1') { $errors.Add('Unexpected frozen input schema.') }
    if ($lock.repo_root -ne $repoRoot) { $errors.Add('Repository root differs from frozen input lock.') }
    $globalDeadline = [DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
    if ($globalDeadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or
        [DateTimeOffset]::UtcNow -ge $globalDeadline) { $errors.Add('Global hard deadline 2026-10-24T17:01:00Z has passed or changed.') }
    Check-Hash 'scene_list' $lock.scene_list.path $lock.scene_list.sha256
    Check-Hash 'reuse_manifest' $lock.reuse_manifest.path $lock.reuse_manifest.sha256
    Check-Hash 'candidate_rescore' $lock.rescores[0].path $lock.rescores[0].sha256
    Check-Hash 'baseline_B_rescore' $lock.rescores[1].path $lock.rescores[1].sha256
    Check-Hash 'candidate_RAW_INDEX' $lock.raw_index.path $lock.raw_index.sha256
    Check-Hash 'model_binding' $lock.model_binding.path $lock.model_binding.sha256
    Check-Hash 'model_mat_weights' $lock.model.mat_path $lock.model.mat_sha256
    Check-Hash 'normalizer_npz_file' $lock.normalizer.npz_path $lock.normalizer.npz_file_sha256
    Check-Hash 'normalizer_train_only_report' $lock.normalizer.train_only_report_path $lock.normalizer.train_only_report_sha256
    Check-Hash 'run_start_lineage' $lock.lineage.path $lock.lineage.sha256
    Check-Hash 'reviewed_scoring_helper' $lock.scoring_helper.path $lock.scoring_helper.sha256
    foreach ($evidence in $lock.mechanism_evidence) { Check-Hash 'mechanism_audit_evidence' $evidence.path $evidence.sha256 }
    Check-Hash 'scene_payload_identity' $lock.scene_payload_identity.path $lock.scene_payload_identity.sha256
    foreach ($source in $lock.runtimeFiles) { Check-Hash 'runtime_or_config_source' $source.path $source.sha256 }
    foreach ($source in $lock.plantFiles) { Check-Hash "plant_source_$($source.name)" $source.path $source.sha256 }
    Check-Hash 'taskbook' $lock.taskbook.path $lock.taskbook.sha256
    foreach ($source in $lock.setupFiles) { Check-Hash "isolated_setup_source_$($source.name)" $source.path $source.sha256 }

    $expectedIds = @(
        'DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00',
        'DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T1_C00_W07',
        'DL1018_VAL_T3_C12_W09','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00'
    )
    $scenes = @(Import-Csv -LiteralPath $lock.scene_list.path)
    if ($scenes.Count -ne 12 -or (@($scenes | Where-Object { $_.scene_id -notin $expectedIds -or $_.scene_id -notlike 'DL1018_VAL_*' })).Count -ne 0 -or
        (@($scenes.scene_id | Sort-Object -Unique)).Count -ne 12 -or
        (Compare-Object $expectedIds @($scenes.scene_id)).Count -ne 0) {
        $errors.Add('Frozen scene index is not the exact twelve VAL IDs.')
    }
    $sceneEvidence = @(Import-Csv -LiteralPath $lock.scene_payload_identity.path)
    if ($sceneEvidence.Count -ne 12 -or (@($sceneEvidence | Where-Object {
        $_.scene_id -notin $expectedIds -or $_.status -ne 'IDENTICAL' -or
        [int]$_.physical_field_count -ne 14 -or [int]$_.time_samples -ne 20001 -or
        [double]$_.max_abs_physical_scene_diff -gt 1e-12
    })).Count -ne 0 -or (@($sceneEvidence.scene_id | Sort-Object -Unique)).Count -ne 12) {
        $errors.Add('ON/B scene payload identity is not 12/12 identical across 14 physical fields.')
    }
    $rawRows = @(Import-Csv -LiteralPath $lock.reuse_manifest.path)
    $candidateScoreRows = @(Import-Csv -LiteralPath $lock.rescores[0].path)
    $baselineScoreRows = @(Import-Csv -LiteralPath $lock.rescores[1].path)
    if ($rawRows.Count -ne 24 -or (@($rawRows | Where-Object { $_.split -ne 'VAL' })).Count -ne 0) {
        $errors.Add('Reuse manifest must contain only 24 VAL raw rows.')
    }
    foreach ($id in $expectedIds) {
        foreach ($role in @('ON_CANDIDATE','B_BASELINE')) {
            $rows = @($rawRows | Where-Object { $_.scene_id -eq $id -and $_.role -eq $role })
            if ($rows.Count -ne 1) { $errors.Add("Expected exactly one $role raw for $id."); continue }
            $row = $rows[0]
            Check-Hash "$role raw $id" $row.raw_path $row.raw_sha256
            if ($role -eq 'ON_CANDIDATE') {
                if ($row.source_index_path -ne $lock.raw_index.path -or $row.source_index_sha256 -ne $lock.raw_index.sha256) {
                    $errors.Add("Candidate raw is not bound to the frozen candidate RAW_INDEX: $id")
                }
                $score = @($candidateScoreRows | Where-Object scene_id -eq $id)
                if ($score.Count -ne 1 -or $score[0].raw_path -ne $row.raw_path -or
                    $score[0].raw_sha256_expected -ne $row.raw_sha256 -or
                    $score[0].'rescore_matches_pair_with_1e-12_m_tolerance' -ne 'True') {
                    $errors.Add("Candidate raw/path/hash/rescore identity mismatch: $id")
                }
            } else {
                $score = @($baselineScoreRows | Where-Object scene_id -eq $id)
                $baselineRelativePath = ([string]$row.source_index_path).Replace('/','\')
                if ($baselineRelativePath -ne 'reports\paper14_v2\phase1\baseline_b_raw_rescore.csv' -or
                    $row.source_index_sha256 -ne $lock.rescores[1].sha256 -or
                    $row.rescore_csv_sha256 -ne $lock.rescores[1].sha256 -or
                    $row.raw_scan_helper_sha256 -ne $lock.scoring_helper.sha256 -or
                    $score.Count -ne 1 -or $score[0].resolved_raw_path -ne $row.raw_path -or
                    $score[0].resolved_raw_sha256_expected -ne $row.raw_sha256 -or
                    $score[0].manifest_source_raw_path -ne $row.paired_source_raw_path -or
                    $score[0].'rescore_matches_pair_with_1e-12_m_tolerance' -ne 'True') {
                    $errors.Add("B raw resolved path/hash/scorer/rescore identity mismatch: $id")
                }
            }
        }
    }

    $verifierPath = Join-Path $expDir 'verify_scene_payload_identity.py'
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    $verifierOutput = @(& $pythonExe $verifierPath 2>&1)
    $scenePayloadVerifierExitCode = $LASTEXITCODE
    $scenePayloadVerifierOutput = [string]::Join([Environment]::NewLine, @($verifierOutput))
    if ($scenePayloadVerifierExitCode -ne 0) {
        $errors.Add("Read-only scene payload verifier failed with exit code $scenePayloadVerifierExitCode.")
    }

    $matlabPath = $lock.matlab.exe
    if (-not (Test-Path -LiteralPath $matlabPath -PathType Leaf)) { $errors.Add("MATLAB executable not found: $matlabPath") }
    else {
        $productVersion = (Get-Item -LiteralPath $matlabPath).VersionInfo.ProductVersion
        if ($productVersion -ne $lock.matlab.product_version) { $errors.Add("MATLAB product version changed: $productVersion") }
    }
    $matlabProcesses = @(Get-Process -Name matlab -ErrorAction SilentlyContinue)
    $pythonProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' } | ForEach-Object {
        $cmd = [string]$_.CommandLine
        $category = if ($cmd -match 'solidworks-mcp|mcp_cad') { 'SOLIDWORKS_MCP_CAD' } else { 'OTHER_PYTHON' }
        [pscustomobject]@{ pid=$_.ProcessId; name=$_.Name; category=$category; command_line=$cmd }
    })
    if ($matlabProcesses.Count -gt 0) { $errors.Add("MATLAB is already running ($($matlabProcesses.Count) process(es)); refusing to start another runner.") }
    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if ([long]$disk.FreeSpace -lt [long]$lock.safety.minimum_free_bytes) { $errors.Add('C: free space is below the frozen minimum.') }
    $runsRoot = Join-Path $expDir 'runs'
    $existingOutputBytes = [long]0
    $estimatedRemainingSeconds = $null
    $estimatedRemainingBytes = [long]$lock.safety.estimated_cycle_output_bytes
    $probeStartedUtc = $null
    $deadlineUtc = $null
    if (Test-Path -LiteralPath $runsRoot) {
        $existing = @(Get-ChildItem -LiteralPath $runsRoot -Force -Recurse -ErrorAction Stop)
        $existingOutputBytes = [long](($existing | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum)
        if ($Mode -eq 'PROBE' -and $existing.Count -gt 0) { $errors.Add('PROBE refuses any existing output; automatic retry is forbidden.') }
        if ($Mode -eq 'CONTINUE') {
            $probeId = [string]$expectedIds[0]
            $probeDir = Join-Path $runsRoot "$probeId\attempt_01"
            $probeStatusPath = Join-Path $probeDir 'run_status.json'
            $probeSummaryPath = Join-Path $expDir 'reports\probe_round1.json'
            $expectedRelative = @(
                "runs\$probeId", "runs\$probeId\attempt_01",
                "runs\$probeId\attempt_01\attempt_started.marker",
                "runs\$probeId\attempt_01\run_start.mat",
                "runs\$probeId\attempt_01\raw_run.mat",
                "runs\$probeId\attempt_01\run_status.json"
            ) | Sort-Object
            $actualRelative = @($existing | ForEach-Object { $_.FullName.Substring($expDir.Length + 1) } | Sort-Object)
            if (-not (Test-Path -LiteralPath $probeStatusPath -PathType Leaf) -or
                -not (Test-Path -LiteralPath $probeSummaryPath -PathType Leaf) -or
                (Compare-Object $expectedRelative $actualRelative).Count -ne 0) {
                $errors.Add('CONTINUE requires exactly one complete first-scene probe and no other attempts/partial output.')
            } else {
                $probeStatus = Get-Content -LiteralPath $probeStatusPath -Raw | ConvertFrom-Json -DateKind String
                $probeSummary = Get-Content -LiteralPath $probeSummaryPath -Raw | ConvertFrom-Json -DateKind String
                $probeStartedUtc = [DateTimeOffset]::Parse([string]$probeSummary.probe_started_utc).ToUniversalTime()
                $deadlineUtc = [DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
                $estimatedRemainingSeconds = [long][Math]::Ceiling([double]$probeSummary.runtime_seconds * 11 * 1.25)
                $perAttemptEstimate = [long][Math]::Ceiling([Math]::Max([long]$lock.safety.estimated_bytes_per_attempt,[long]$probeSummary.attempt_output_bytes) * 1.25)
                $estimatedRemainingBytes = [long]($perAttemptEstimate * 11)
                if ($probeStatus.scene_id -ne $probeId -or $probeStatus.status -ne 'STABLE' -or
                    $probeStatus.last_transition -ne 20000 -or $probeStatus.update_enabled -ne $false -or
                    $probeStatus.head_enabled -ne $true -or $probeStatus.pcf_enabled -ne $true -or
                    [double]$probeStatus.max_abs_W_before_delta -gt 1e-12 -or
                    [double]$probeStatus.max_abs_W_after_delta -gt 1e-12 -or
                    $probeSummary.status -ne 'PROBE_COMPLETE' -or $probeSummary.scene_id -ne $probeId -or
                    [double]$probeSummary.runtime_seconds -le 0 -or [long]$probeSummary.attempt_output_bytes -le 0) {
                    $errors.Add('First-scene probe status/W0/timing evidence is invalid.')
                }
                $probeRaw = Join-Path $probeDir 'raw_run.mat'
                if ((Get-Sha256 $probeRaw) -ne [string]$probeStatus.raw_sha256) { $errors.Add('Probe raw hash differs from run_status.json.') }
                if ([DateTimeOffset]::UtcNow.AddSeconds($estimatedRemainingSeconds) -gt $deadlineUtc) {
                    $errors.Add('Estimated remaining 11-scene runtime exceeds the fixed global deadline.')
                }
            }
        }
    } elseif ($Mode -eq 'CONTINUE') {
        $errors.Add('CONTINUE cannot run before the first-scene PROBE.')
    }
    if ([long]$lock.safety.estimated_cycle_output_bytes -gt [long]$lock.safety.max_cycle_output_bytes) {
        $errors.Add('Estimated output for this 12-scene cycle exceeds the frozen 80 GB cycle cap.')
    }
    if ($lock.safety.minimum_free_bytes -ne 30000000000 -or
        $lock.safety.max_cycle_output_bytes -ne 80000000000 -or
        $lock.safety.estimated_bytes_per_attempt -le 0 -or
                    $lock.safety.max_cycle_duration_hours -ne 72 -or
        $lock.plantFiles.Count -lt 10) {
        $errors.Add('Frozen disk/time budget or complete Plant source lock is invalid.')
    }
    if ([long]$existingOutputBytes + [long]$estimatedRemainingBytes -gt [long]$lock.safety.max_cycle_output_bytes) {
        $errors.Add('Existing plus projected cycle output exceeds the frozen 80 GB cap.')
    }
    if ([long]$disk.FreeSpace - [long]$estimatedRemainingBytes -lt [long]$lock.safety.minimum_free_bytes) {
        $errors.Add('Projected C: free space after the estimated cycle would be below the 30 GB refusal threshold.')
    }
} catch {
    $errors.Add($_.Exception.Message)
    $matlabProcesses = @()
    $pythonProcesses = @()
    $disk = $null
}

$status = if ($errors.Count -eq 0) { 'PASS' } else { 'BLOCKED' }
$report = [ordered]@{
    schema='FROZEN_W0_SCREEN_PREFLIGHT_V1'; status=$status; mode=$Mode
    parent_reviewed_switch_present=[bool]$ParentReviewed
    created_utc=[DateTime]::UtcNow.ToString('o'); repo_root=$repoRoot
    frozen_inputs_sha256=Get-Sha256 $lockPath
    matlab_executable=$lock.matlab.exe; matlab_product_version=$lock.matlab.product_version
    matlab_process_count=@($matlabProcesses).Count
    python_processes=@($pythonProcesses)
    python_process_categories=@($pythonProcesses | Group-Object category | ForEach-Object { [ordered]@{ category=$_.Name; count=$_.Count } })
    b_source_path_resolution_divergences=@($baselineScoreRows | Where-Object { $_.scene_id -in $expectedIds -and $_.resolved_path_differs_from_manifest_source -eq 'True' } | Select-Object scene_id,manifest_source_raw_path,resolved_raw_path,manifest_source_raw_sha256,resolved_raw_sha256_expected)
    c_free_bytes=if ($disk) { [long]$disk.FreeSpace } else { $null }
    projected_c_free_bytes=if ($disk) { [long]$disk.FreeSpace - [long]$estimatedRemainingBytes } else { $null }
    minimum_postrun_free_bytes=[long]$lock.safety.minimum_free_bytes
    estimated_bytes_per_attempt=[long]$lock.safety.estimated_bytes_per_attempt
    estimated_cycle_output_bytes=[long]$lock.safety.estimated_cycle_output_bytes
    max_cycle_output_bytes=[long]$lock.safety.max_cycle_output_bytes
    existing_output_bytes=if ($existingOutputBytes) { $existingOutputBytes } else { 0 }
    estimated_remaining_seconds=$estimatedRemainingSeconds
    estimated_remaining_bytes=$estimatedRemainingBytes
    probe_started_utc=if ($probeStartedUtc) { $probeStartedUtc.ToString('o') } else { $null }
    deadline_utc=if ($deadlineUtc) { $deadlineUtc.ToString('o') } else { $null }
    global_deadline_utc=if ($lock) { [string]$lock.safety.global_deadline_utc } else { $null }
    checked_sha256=@($checked); errors=@($errors)
    scene_payload_identity_rows=@($sceneEvidence).Count
    scene_payload_identical_rows=@($sceneEvidence | Where-Object status -eq 'IDENTICAL').Count
    scene_payload_physical_field_counts=@($sceneEvidence | Select-Object -ExpandProperty physical_field_count -Unique)
    scene_payload_verifier_exit_code=$scenePayloadVerifierExitCode
    scene_payload_verifier_output=$scenePayloadVerifierOutput
    scene_payload_time_sample_counts=@($sceneEvidence | Select-Object -ExpandProperty time_samples -Unique)
    scene_payload_max_abs_diff_m=@($sceneEvidence | Select-Object -ExpandProperty max_abs_physical_scene_diff -Unique)
    plant_source_count=@($lock.plantFiles).Count
    isolated_setup_source_count=@($lock.setupFiles).Count
    simulator_started=$false; plant_calls_started=0; transitions_started=0; test_files_read=0
    output_runs_created=$false
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding utf8NoBOM
Write-Output "PRECHECK mode=$Mode status=$status MATLAB=$(@($matlabProcesses).Count) SolidWorks_MCP_CAD=$(@($pythonProcesses | Where-Object category -eq 'SOLIDWORKS_MCP_CAD').Count) Other_Python=$(@($pythonProcesses | Where-Object category -eq 'OTHER_PYTHON').Count) C_free_bytes=$(if($disk){[long]$disk.FreeSpace}else{'unknown'}) estimated_remaining_seconds=$estimatedRemainingSeconds estimated_remaining_bytes=$estimatedRemainingBytes"
foreach ($errorText in $errors) { Write-Error $errorText -ErrorAction Continue }
if ($errors.Count -gt 0) { exit 1 }
exit 0
