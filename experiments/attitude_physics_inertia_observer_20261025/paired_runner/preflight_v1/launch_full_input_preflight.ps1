# Reviewed entry for one no-Plant C5 input and three-scene MATLAB preflight.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$preflight = $PSScriptRoot
$root = Split-Path -Parent $preflight
$repo = (Resolve-Path -LiteralPath (Join-Path $root '../../..')).Path
$matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$probe = Join-Path $preflight 'full_input_preflight_probe.m'
$checker = Join-Path $preflight 'static_check_paired_runner_v2.py'
$audit = Join-Path $preflight 'CODE_ONLY_STATIC_AUDIT_v2.json'
$taskbook = Join-Path $root 'FULL_INPUT_LOCK_TASKBOOK_v1_ZH.md'
$csv = Join-Path $root 'configs/scene_specs_dev3.csv'
$inputReceipt = Join-Path $root 'configs/scene_specs_dev3_receipt.json'
$c5 = Join-Path $repo 'experiments/position_axis_coordinate_c5_dev72_20261023'
$c5LockPath = Join-Path $c5 'C5_DEV72_INPUT_LOCK_v3.json'
$c5ContractPath = Join-Path $c5 'C5_DEV72_RUN_CONTRACT_v3.json'
$c5PreparePath = Join-Path $c5 'C5_DEV72_PREPARE_RESULT_v3.json'
$snapshotPath = Join-Path $c5 'C5_DEV72_PREPARED_CFG_OPTS_v3.mat'
$syntheticLockPath = Join-Path $repo 'experiments/attitude_physics_inertia_observer_20261025/synthetic/source_lock_candidate_v3.json'
$syntheticAuditPath = Join-Path $repo 'experiments/attitude_physics_inertia_observer_20261025/synthetic/PHYS_ATT_OBSERVER_SYNTH_AUDIT_v3.json'
$firstFailurePath = Join-Path $root 'LAUNCH_PRECHECK_FAILURE_v1.json'
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
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }
if ((Test-Path -LiteralPath (Join-Path $root 'runs')) -or
    (Test-Path -LiteralPath (Join-Path $preflight 'runs'))) {
    throw 'Existing scene/preflight runs directory requires root review; no duplicate launch.'
}
$preexisting = @(ActiveMatlabProcesses)
while ($preexisting.Count -gt 0) {
    Write-Output "WAITING_FOR_EXISTING_MATLAB_OR_OCTAVE count=$($preexisting.Count)"
    Start-Sleep -Seconds 15
    $preexisting = @(ActiveMatlabProcesses)
}
$runs = Join-Path $preflight 'runs'
New-Item -ItemType Directory -Path $runs -ErrorAction Stop | Out-Null
$runName = 'full_input_preflight_' + (Get-Date -Format 'yyyyMMddTHHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDir = Join-Path $runs $runName
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
$stdoutPath = Join-Path $runDir 'stdout.log'
$stderrPath = Join-Path $runDir 'stderr.log'
$commandPath = Join-Path $runDir 'command.json'
$exitPath = Join-Path $runDir 'exit_code.txt'
$candidatePath = Join-Path $runDir 'source_lock_paired_runner_v1_candidate.json'
$receiptPath = Join-Path $runDir 'receipt.json'
$batch = "run('" + ($probe.Replace('\','/').Replace("'","''")) + "')"
$command = [ordered]@{
    launcher_invocation = @('pwsh', '-NoProfile', '-File', $PSCommandPath)
    executable = $matlab
    arguments = @('-batch', $batch)
    working_directory = $root
    launcher = $PSCommandPath
    launcher_sha256 = ShaFile $PSCommandPath
    probe = $probe
    probe_sha256 = ShaFile $probe
}
SaveNewUtf8 $commandPath (($command | ConvertTo-Json -Depth 5) + "`n")
$matlabStarted = $false
$exitCode = $null
$before = [ordered]@{}
$after = [ordered]@{}
$sourcesBefore = [ordered]@{}
$sourcesAfter = [ordered]@{}
try {
    $expected = [ordered]@{
        matlab_executable = @($matlab, '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9')
        probe = @($probe, 'd988ebff32f9602f0e1a122ce98939221c96510ba8a3c4cd5919acb7c162f896')
        checker_v2 = @($checker, '1875e9a46a93234ba30dfb3d92d310c6688d2d71a445addaf4ecbf36c90184bc')
        audit_v2 = @($audit, '9f4b9e7c04da2373822e22249b7bbff79dd133c90d9005b17e7a024e628b03e5')
        taskbook = @($taskbook, 'fc4a49236e6d307927b1429cc31efecd21f4fd53c626514f3386da7b52d80e07')
        dev3_csv = @($csv, 'bd68a24a0d87764e8d6fabcf5372d8a36a38104a3a246df6523f514548ac7630')
        dev3_receipt = @($inputReceipt, '3b4443302cddbf67368922c17234f54041d1f3e36db345b5ec71f5ffc0bf7067')
        c5_input_lock = @($c5LockPath, '82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75')
        c5_run_contract = @($c5ContractPath, '6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150')
        c5_prepare_result = @($c5PreparePath, 'ca1fbd9bdf2d7a7b02b15d36ed010fbb1851b4607394c426f6d4d6d408ce3095')
        c5_snapshot_mat = @($snapshotPath, '842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a')
        synthetic_v3_lock = @($syntheticLockPath, '5ac4f0eb9e1fd90a1ffd714da0c78ef86caf2c0258bffe4ca52e691b0346a408')
        synthetic_v3_audit = @($syntheticAuditPath, 'eba73d2ae849c4b7a39c6c88ca9890ef9c9e092ed3b51c590a16002a0eb9fb57')
        first_launcher_failure = @($firstFailurePath, '1d691d6e013f30342d340af9e20581bdea78d70cd5a9d72f6ec06d4d744fa164')
    }
    if ((ShaFile $c5LockPath) -ne $expected.c5_input_lock[1]) { throw 'C5 input lock SHA differs.' }
    $c5Lock = Get-Content -Raw -LiteralPath $c5LockPath | ConvertFrom-Json
    $modelRef = @($c5Lock.shared_input_files | Where-Object { $_.role -eq 'model_mat' })
    $normalizerRef = @($c5Lock.shared_input_files | Where-Object { $_.role -eq 'normalizer_npz' })
    if ($modelRef.Count -ne 1 -or $normalizerRef.Count -ne 1) { throw 'C5 model/normalizer references are not unique.' }
    $expected.model_mat = @($modelRef[0].path, '6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e')
    $expected.normalizer_npz = @($normalizerRef[0].path, '520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404')
    if ($modelRef[0].sha256 -ne $expected.model_mat[1] -or
        $normalizerRef[0].sha256 -ne $expected.normalizer_npz[1]) { throw 'C5 model/normalizer lock SHA differs.' }
    foreach ($key in $expected.Keys) {
        $item = $expected[$key]
        $actual = ShaFile $item[0]
        if ($actual -ne $item[1]) { throw "Input SHA differs: $key" }
        $before[$key] = [ordered]@{ path = $item[0]; sha256 = $actual }
    }
    $before.launcher = [ordered]@{ path = $PSCommandPath; sha256 = ShaFile $PSCommandPath }
    $auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
    if ($auditData.source_count -ne 39 -or
        $auditData.checker_sha256 -ne $before.checker_v2.sha256 -or
        $auditData.full_input_lock_taskbook_sha256 -ne $before.taskbook.sha256) {
        throw 'Static audit identity/count differs.'
    }
    foreach ($property in $auditData.isolated_sha256.PSObject.Properties) {
        $actual = ShaFile (Join-Path $root $property.Name)
        if ($actual -ne $property.Value) { throw "Isolated MATLAB source differs: $($property.Name)" }
        $sourcesBefore[$property.Name] = $actual
    }
    if ($sourcesBefore.Count -ne 39) { throw 'Expected exactly 39 isolated MATLAB sources.' }
    $inputIdentity = Get-Content -Raw -LiteralPath $inputReceipt | ConvertFrom-Json
    if ($inputIdentity.rows.Count -ne 3) { throw 'DEV receipt row count differs.' }
    $preexisting = @(ActiveMatlabProcesses)
    while ($preexisting.Count -gt 0) {
        Write-Output "WAITING_FOR_EXISTING_MATLAB_OR_OCTAVE count=$($preexisting.Count) run_dir=$runDir"
        Start-Sleep -Seconds 15
        $preexisting = @(ActiveMatlabProcesses)
    }
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
        $matlabStarted = $true
        Write-Output "MATLAB_PREFLIGHT_STARTED pid=$($process.Id) run_dir=$runDir"
        $stdoutCopy = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrCopy = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutCopy, $stderrCopy))
        $exitCode = $process.ExitCode
    } finally {
        $stdout.Dispose(); $stderr.Dispose()
        if ($null -ne $process) { $process.Dispose() }
        if ($matlabStarted) { SaveNewUtf8 $exitPath ("$exitCode`n") }
    }
    if ($exitCode -ne 0) { throw "MATLAB exited $exitCode" }
    $lines = @(Get-Content -LiteralPath $stdoutPath | Where-Object { $_.StartsWith('PAIRED_FULL_INPUT_PREFLIGHT_JSON:') })
    if ($lines.Count -ne 1) { throw 'Expected exactly one full-input JSON marker.' }
    $payload = $lines[0].Substring('PAIRED_FULL_INPUT_PREFLIGHT_JSON:'.Length) | ConvertFrom-Json
    $ids = @('DL1018_DEV_T1_C00_W03', 'DL1018_DEV_T2_C02_W15', 'DL1018_DEV_T3_C10_W11')
    $seeds = @(2026121803, 2026122847, 2026123971)
    if ($payload.schema -ne 'PAIRED_FULL_INPUT_PREFLIGHT_V1' -or
        $payload.status -ne 'NOT_FROZEN' -or $payload.closed_loop_runs_authorized -ne $false -or
        $payload.executed -ne $false -or $payload.matlab_release -ne '2025b' -or
        $payload.scenes.Count -ne 3 -or $payload.checkcode_diagnostics.Count -ne 39 -or
        $payload.model_id -ne 'DSSM14' -or $payload.model_architecture -ne 'DSSM' -or
        $payload.model_seed -ne 2026102001 -or $payload.model_selected_step -ne 60000 -or
        $payload.model_input_dim -ne 14 -or $payload.model_window -ne 32 -or
        $payload.W0_sha256 -ne '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53' -or
        $payload.normalizer_arrays_sha256 -ne '533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0' -or
        $payload.synthetic_zero_dssm_smoke_passed -ne $true) { throw 'Full-input status/model/count differs.' }
    foreach ($name in @('cfg_sha256','J0_controller_fixed_sha256','c5_options_sha256',
            'baseline_options_sha256','candidate_options_sha256','common_options_sha256',
            'frozen_model_synthetic_phi_sha256','rbf_position_initial_weight_sha256',
            'rbf_attitude_initial_weight_sha256')) {
        if ($payload.$name -notmatch '^[0-9a-f]{64}$') { throw "Invalid result hash: $name" }
    }
    for ($i = 0; $i -lt 3; $i++) {
        $scene = $payload.scenes[$i]
        if ($scene.scene_id -ne $ids[$i] -or $scene.seed -ne $seeds[$i] -or
            $scene.source_row_sha256 -ne $inputIdentity.rows[$i].source_row_sha256 -or
            $scene.time_size[0] -ne 20001 -or $scene.time_size[1] -ne 1 -or
            $scene.wind_size[0] -ne 20001 -or $scene.arm_command_size[0] -ne 20001 -or
            $scene.scene_sha256 -notmatch '^[0-9a-f]{64}$' -or
            $scene.spec_sha256 -notmatch '^[0-9a-f]{64}$' -or
            $scene.metadata_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw "DEV scene identity/shape/hash differs: $($ids[$i])"
        }
        if ($scene.wind_id -eq 15 -and ($scene.wind_rms_mps -ne 0 -or $scene.wind_peak_mps -ne 0)) {
            throw 'W15 zero-wind identity differs.'
        }
    }
    foreach ($key in $before.Keys) {
        $item = $before[$key]
        $actual = ShaFile $item.path
        if ($actual -ne $item.sha256) { throw "Input changed during preflight: $key" }
        $after[$key] = [ordered]@{ path = $item.path; sha256 = $actual }
    }
    foreach ($key in $sourcesBefore.Keys) {
        $actual = ShaFile (Join-Path $root $key)
        if ($actual -ne $sourcesBefore[$key]) { throw "Source changed during preflight: $key" }
        $sourcesAfter[$key] = $actual
    }
    $candidate = [ordered]@{
        schema = 'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE'
        status = 'NOT_FROZEN'
        closed_loop_runs_authorized = $false
        executed = $false
        preflight_executed = $true
        launcher_invocation_count_this_preflight = 1
        matlab_start_count_this_preflight = 1
        plant_run_count_this_preflight = 0
        training_run_count_this_preflight = 0
        command = $command
        command_sha256 = ShaFile $commandPath
        exit_code = $exitCode
        stdout_sha256 = ShaFile $stdoutPath
        stderr_sha256 = ShaFile $stderrPath
        input_sha256_before = $before
        input_sha256_after = $after
        isolated_matlab_source_sha256_before = $sourcesBefore
        isolated_matlab_source_sha256_after = $sourcesAfter
        source_origins = $auditData.source_origins
        c5_active_inventory_matches = $auditData.c5_v3_active_inventory_matches
        synthetic_v3_source_lock_sha256 = $before.synthetic_v3_lock.sha256
        synthetic_v3_audit_sha256 = $before.synthetic_v3_audit.sha256
        legacy_static_audit_status = 'SUPERSEDED_BEFORE_C5_FORWARD_FIX'
        first_launcher_failure_sha256 = $before.first_launcher_failure.sha256
        result = $payload
    }
    SaveNewUtf8 $candidatePath (($candidate | ConvertTo-Json -Depth 24) + "`n")
    $receipt = [ordered]@{
        schema = 'PAIRED_FULL_INPUT_PREFLIGHT_RECEIPT_V1'
        status = 'NOT_FROZEN'
        closed_loop_runs_authorized = $false
        executed = $false
        preflight_executed = $true
        matlab_start_count = 1
        plant_run_count = 0
        training_run_count = 0
        command = $command
        exit_code = $exitCode
        candidate_path = $candidatePath
        candidate_sha256 = ShaFile $candidatePath
        stdout_path = $stdoutPath
        stdout_sha256 = ShaFile $stdoutPath
        stderr_path = $stderrPath
        stderr_sha256 = ShaFile $stderrPath
        taskbook_sha256 = $before.taskbook.sha256
    }
    SaveNewUtf8 $receiptPath (($receipt | ConvertTo-Json -Depth 8) + "`n")
    Write-Output "FULL_INPUT_PREFLIGHT_NOT_FROZEN receipt=$receiptPath sha256=$(ShaFile $receiptPath)"
} catch {
    $reason = $_.Exception.Message
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        $failure = [ordered]@{
            schema = 'PAIRED_FULL_INPUT_PREFLIGHT_FAILURE_V1'
            status = 'NOT_FROZEN'
            closed_loop_runs_authorized = $false
            executed = $false
            preflight_executed = $matlabStarted
            matlab_start_count = [int]$matlabStarted
            plant_run_count = 0
            training_run_count = 0
            reason = $reason
            command = $command
            exit_code = $exitCode
            stdout_path = $(if (Test-Path -LiteralPath $stdoutPath) { $stdoutPath } else { $null })
            stdout_sha256 = $(if (Test-Path -LiteralPath $stdoutPath) { ShaFile $stdoutPath } else { $null })
            stderr_path = $(if (Test-Path -LiteralPath $stderrPath) { $stderrPath } else { $null })
            stderr_sha256 = $(if (Test-Path -LiteralPath $stderrPath) { ShaFile $stderrPath } else { $null })
            input_sha256_before = $before
            input_sha256_after = $after
            isolated_matlab_source_sha256_before = $sourcesBefore
            isolated_matlab_source_sha256_after = $sourcesAfter
            taskbook_sha256 = ShaFile $taskbook
        }
        SaveNewUtf8 $receiptPath (($failure | ConvertTo-Json -Depth 16) + "`n")
    }
    throw "Full-input preflight failed: $reason; receipt=$receiptPath"
}
