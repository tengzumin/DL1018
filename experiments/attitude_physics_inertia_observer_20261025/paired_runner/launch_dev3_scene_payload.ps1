# PowerShell 7 launcher for three isolated DEV scene hashes. CreateNew throughout.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$probe = Join-Path $root 'scene_payload_probe.m'
$csv = Join-Path $root 'configs/scene_specs_dev3.csv'
$inputReceipt = Join-Path $root 'configs/scene_specs_dev3_receipt.json'
$audit = Join-Path $root 'CODE_ONLY_STATIC_AUDIT.json'
$taskbook = Join-Path $root 'SCENE_PAYLOAD_TASKBOOK_v1_ZH.md'
$expectedCsvSha = 'bd68a24a0d87764e8d6fabcf5372d8a36a38104a3a246df6523f514548ac7630'
$expectedReceiptSha = '3b4443302cddbf67368922c17234f54041d1f3e36db345b5ec71f5ffc0bf7067'
$expectedAuditSha = '2c43e1188450d13eccf925d4fec24ece729352c0519bf8c7941e3ecfe22a8adc'
$expectedTaskbookSha = 'ff061386a73391bb5cf3d564e8bb9af87fe71da1da03cdd451f04d4c9ecc7a2b'
$expectedMatlabExeSha = '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9'
function ShaFile([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function SaveNewUtf8([string]$path, [string]$content) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($content)
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function ActiveMatlabProcesses {
    return @(Get-CimInstance Win32_Process -Filter "name = 'MATLAB.exe' or name = 'octave.exe' or name = 'octave-cli.exe'" |
        Select-Object ProcessId, Name, ExecutablePath)
}
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }
if (-not (Test-Path -LiteralPath $matlab -PathType Leaf)) { throw 'MATLAB R2025b executable is absent.' }
if ((ShaFile $matlab) -ne $expectedMatlabExeSha -or
    (ShaFile $audit) -ne $expectedAuditSha -or
    (ShaFile $taskbook) -ne $expectedTaskbookSha) {
    throw 'MATLAB executable, source audit, or scene taskbook SHA differs.'
}
if ((ShaFile $csv) -ne $expectedCsvSha -or (ShaFile $inputReceipt) -ne $expectedReceiptSha) {
    throw 'Isolated DEV CSV or extraction receipt SHA differs.'
}
$inputIdentity = Get-Content -LiteralPath $inputReceipt -Raw | ConvertFrom-Json
if ($inputIdentity.source_sha256 -ne 'd116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3' -or
    $inputIdentity.rows.Count -ne 3) { throw 'DEV input provenance differs.' }
$sourceAudit = Get-Content -LiteralPath $audit -Raw | ConvertFrom-Json
$sourceHashes = [ordered]@{}
foreach ($property in $sourceAudit.isolated_sha256.PSObject.Properties) {
    $path = Join-Path $root $property.Name
    $actual = ShaFile $path
    if ($actual -ne $property.Value) { throw "Isolated MATLAB source changed: $($property.Name)" }
    $sourceHashes[$property.Name] = $actual
}
if ($sourceHashes.Count -ne 39) { throw 'Expected 39 isolated MATLAB sources.' }
$sceneClosure = @(
    'matlab/runtime/activate_paired_runner.m',
    'matlab/runtime/bind_paired_fixed_j0.m',
    'matlab/runtime/paired_sha256_double.m',
    'matlab/scenes/make_paired_dev_scene.m',
    'matlab/core/default_config.m',
    'matlab/core/simulation_parameters.m',
    'matlab/core/controller_parameters.m',
    'matlab/core/arm_mass_properties.m',
    'matlab/core/distributed_mass_properties.m',
    'matlab/core/allocation_matrix.m',
    'matlab/core/arm_directions.m',
    'matlab/core/wind_velocity_profile.m',
    'matlab/core/tcn0916_morphology_scenario.m',
    'matlab/core/tcn0916_topologies.m'
)
$sceneClosureHashes = [ordered]@{}
foreach ($relative in $sceneClosure) {
    if (-not $sourceHashes.Contains($relative)) { throw "Scene dependency absent from source lock: $relative" }
    $sceneClosureHashes[$relative] = $sourceHashes[$relative]
}
$preexisting = @(ActiveMatlabProcesses)
while ($preexisting.Count -gt 0) {
    Write-Output "WAITING_FOR_EXISTING_MATLAB_OR_OCTAVE count=$($preexisting.Count)"
    Start-Sleep -Seconds 15
    $preexisting = @(ActiveMatlabProcesses)
}
$runName = 'scene_payload_' + (Get-Date -Format 'yyyyMMddTHHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8)
$runDir = Join-Path $root (Join-Path 'runs' $runName)
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
$stdoutPath = Join-Path $runDir 'stdout.log'
$stderrPath = Join-Path $runDir 'stderr.log'
$commandPath = Join-Path $runDir 'command.json'
$receiptPath = Join-Path $runDir 'receipt.json'
$exitPath = Join-Path $runDir 'exit_code.txt'
$batch = "run('" + ($probe.Replace('\','/').Replace("'","''")) + "')"
$command = [ordered]@{
    launcher_invocation = @('pwsh','-NoProfile','-File',$PSCommandPath)
    executable = $matlab
    executable_sha256 = $expectedMatlabExeSha
    arguments = @('-batch', $batch)
    working_directory = $root
    launcher = $PSCommandPath
    launcher_sha256 = ShaFile $PSCommandPath
    probe = $probe
    probe_sha256 = ShaFile $probe
    source_audit_sha256 = $expectedAuditSha
    taskbook_sha256 = $expectedTaskbookSha
}
SaveNewUtf8 $commandPath (($command | ConvertTo-Json -Depth 5) + "`n")
$exitCode = -1
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
    $stdoutCopy = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
    $stderrCopy = $process.StandardError.BaseStream.CopyToAsync($stderr)
    $process.WaitForExit()
    [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutCopy,$stderrCopy))
    $exitCode = $process.ExitCode
} finally {
    $stdout.Dispose(); $stderr.Dispose()
    if ($null -ne $process) { $process.Dispose() }
    SaveNewUtf8 $exitPath ("$exitCode`n")
}
if ($exitCode -ne 0) { throw "MATLAB exited $exitCode; logs preserved in $runDir" }
$lines = @(Get-Content -LiteralPath $stdoutPath | Where-Object { $_.StartsWith('PAIRED_DEV3_PAYLOAD_JSON:') })
if ($lines.Count -ne 1) { throw "Expected one payload JSON marker; logs preserved in $runDir" }
$payload = $lines[0].Substring('PAIRED_DEV3_PAYLOAD_JSON:'.Length) | ConvertFrom-Json
$ids = @('DL1018_DEV_T1_C00_W03','DL1018_DEV_T2_C02_W15','DL1018_DEV_T3_C10_W11')
$seeds = @(2026121803,2026122847,2026123971)
if ($payload.status -ne 'NOT_FROZEN' -or $payload.closed_loop_runs_authorized -ne $false -or
    $payload.executed -ne $false -or $payload.matlab_release -ne '2025b' -or
    $payload.scenes.Count -ne 3) { throw "Payload status/release/count differs; logs preserved in $runDir" }
for ($i=0; $i -lt 3; $i++) {
    $scene = $payload.scenes[$i]
    if ($scene.scene_id -ne $ids[$i] -or $scene.seed -ne $seeds[$i] -or
        $scene.source_row_sha256 -ne $inputIdentity.rows[$i].source_row_sha256 -or
        $scene.time_size[0] -ne 20001 -or $scene.time_size[1] -ne 1 -or
        $scene.wind_size[0] -ne 20001 -or $scene.arm_command_size[0] -ne 20001 -or
        $scene.scene_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $scene.spec_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $scene.metadata_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Payload identity/shape/hash differs for $($ids[$i]); logs preserved in $runDir"
    }
    if ($scene.wind_id -eq 15 -and ($scene.wind_rms_mps -ne 0 -or $scene.wind_peak_mps -ne 0)) {
        throw "W15 wind differs; logs preserved in $runDir"
    }
}
foreach ($property in $sourceAudit.isolated_sha256.PSObject.Properties) {
    if ((ShaFile (Join-Path $root $property.Name)) -ne $sourceHashes[$property.Name]) {
        throw "Source changed during MATLAB run: $($property.Name); logs preserved in $runDir"
    }
}
if ((ShaFile $csv) -ne $expectedCsvSha -or (ShaFile $inputReceipt) -ne $expectedReceiptSha) {
    throw "Input changed during MATLAB run; logs preserved in $runDir"
}
if ((ShaFile $audit) -ne $expectedAuditSha -or
    (ShaFile $taskbook) -ne $expectedTaskbookSha -or
    (ShaFile $matlab) -ne $expectedMatlabExeSha -or
    (ShaFile $probe) -ne $command.probe_sha256) {
    throw "Taskbook, audit, MATLAB executable, or probe changed during run; logs preserved in $runDir"
}
$receipt = [ordered]@{
    schema = 'PAIRED_DEV3_SCENE_PAYLOAD_RECEIPT_V1'
    status = 'NOT_FROZEN'
    closed_loop_runs_authorized = $false
    executed = $false
    command = $command
    exit_code = $exitCode
    input_csv_sha256 = $expectedCsvSha
    input_receipt_sha256 = $expectedReceiptSha
    source_csv_sha256_from_input_receipt = $inputIdentity.source_sha256
    source_row_sha256 = @($inputIdentity.rows | ForEach-Object { $_.source_row_sha256 })
    source_audit_sha256 = ShaFile $audit
    isolated_matlab_source_sha256 = $sourceHashes
    scene_dependency_closure_sha256 = $sceneClosureHashes
    taskbook_sha256 = $expectedTaskbookSha
    matlab_executable_sha256 = $expectedMatlabExeSha
    stdout_sha256 = ShaFile $stdoutPath
    stderr_sha256 = ShaFile $stderrPath
    result = $payload
}
SaveNewUtf8 $receiptPath (($receipt | ConvertTo-Json -Depth 16) + "`n")
Write-Output "DEV3_SCENE_PAYLOAD_NOT_FROZEN receipt=$receiptPath sha256=$(ShaFile $receiptPath)"
} catch {
    $reason = $_.Exception.Message
    $stdoutHash = if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) { ShaFile $stdoutPath } else { $null }
    $stderrHash = if (Test-Path -LiteralPath $stderrPath -PathType Leaf) { ShaFile $stderrPath } else { $null }
    $failure = [ordered]@{
        schema = 'PAIRED_DEV3_SCENE_PAYLOAD_FAILURE_V1'
        status = 'NOT_FROZEN'
        payload_generation_status = 'FAILED'
        closed_loop_runs_authorized = $false
        executed = $false
        reason = $reason
        command = $command
        exit_code = $exitCode
        stdout_path = $stdoutPath
        stdout_sha256 = $stdoutHash
        stderr_path = $stderrPath
        stderr_sha256 = $stderrHash
        input_csv_sha256 = $expectedCsvSha
        input_receipt_sha256 = $expectedReceiptSha
        source_csv_sha256_from_input_receipt = $inputIdentity.source_sha256
        source_row_sha256 = @($inputIdentity.rows | ForEach-Object { $_.source_row_sha256 })
        source_audit_sha256 = $expectedAuditSha
        scene_dependency_closure_sha256 = $sceneClosureHashes
        taskbook_sha256 = $expectedTaskbookSha
        matlab_executable_sha256 = $expectedMatlabExeSha
    }
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        SaveNewUtf8 $receiptPath (($failure | ConvertTo-Json -Depth 16) + "`n")
    }
    throw "Scene payload generation failed: $reason; receipt=$receiptPath"
}
