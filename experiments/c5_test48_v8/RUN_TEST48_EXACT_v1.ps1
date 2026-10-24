param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('PREPARE_NO_PLANT','ENGINEERING_DEV2','RUN_UNSTARTED_TEST_PARENT_APPROVED')]
    [string]$Mode
)
$ErrorActionPreference = 'Stop'
$taskDir = [IO.Path]::GetDirectoryName($PSCommandPath)
$repoRoot = [IO.Path]::GetFullPath((Join-Path $taskDir '..\..'))
$reportDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v8'
$contractPath = Join-Path $taskDir 'TEST48_RUN_CONTRACT_v4.json'
$manifestPath = Join-Path $reportDir 'TEST_METHOD_SOURCE_MANIFEST_v4.json'
$taskbookPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_TASKBOOK_v1_ZH.md'
$codeReleasePath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_CODE_ONLY_RELEASE_v1.json'
$dependencyReviewPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_dependency_review_v1/DEPENDENCY_REVIEW_v1.json'
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
$methodIds = @('B_TRACEABLE','CORRECTED_DSSM14_G12_R32','CORRECTED_KAN14_G12_R32','C5_M110','C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION')
$runMethodIds = @('CORRECTED_DSSM14_G12_R32','CORRECTED_KAN14_G12_R32','C5_M110','C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION')

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing frozen file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Resolve-ManifestPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return $Path }
    Join-Path $repoRoot $Path
}
function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required evidence/release is absent: $Path" }
    Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}
function Require-Value($Object,[string]$Name,$Expected) {
    if (-not ($Object.PSObject.Properties.Name -contains $Name)) { throw "Required field '$Name' is absent." }
    if ($Object.$Name -is [bool] -or $Expected -is [bool]) {
        if ([bool]$Object.$Name -ne [bool]$Expected) { throw "Authorization field '$Name' does not match required value." }
    } elseif ($Object.$Name -is [System.Array] -or $Expected -is [System.Array]) {
        $actual = [string]::Join('|',[string[]]@($Object.$Name))
        $wanted = [string]::Join('|',[string[]]@($Expected))
        if ($actual -cne $wanted) { throw "Authorization array '$Name' does not match required order." }
    } elseif ([string]$Object.$Name -cne [string]$Expected) { throw "Authorization field '$Name' does not match required value." }
}
function Convert-DeadlineUtc($Value) {
    if ($Value -is [DateTime]) { return $Value.ToUniversalTime() }
    if ($Value -is [DateTimeOffset]) { return $Value.UtcDateTime }
    [DateTimeOffset]::Parse([string]$Value).UtcDateTime
}
function Assert-DeadlineParser {
    $raw = Get-Content -Raw -LiteralPath $contractPath
    $typed = $raw | ConvertFrom-Json
    $typedUtc = Convert-DeadlineUtc $typed.limits.hard_deadline_utc
    $match = [regex]::Match($raw,'"hard_deadline_utc"\s*:\s*"([^"]+)"')
    if (-not $match.Success) { throw 'The contract JSON has no hard_deadline_utc string.' }
    $stringUtc = Convert-DeadlineUtc $match.Groups[1].Value
    $expected = [DateTimeOffset]::Parse('2026-10-24T17:01:00Z').UtcDateTime
    if ($typedUtc -ne $expected -or $stringUtc -ne $expected -or $typedUtc -ne $stringUtc) { throw 'PS7 UTC deadline parsing failed exact roundtrip.' }
}
function Assert-ShortPath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute.Length -ge 240) { throw "Planned output path is too long ($($absolute.Length)): $absolute" }
}
function Assert-NoMatlab {
    $active = Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'"
    if ($active) { throw 'A MATLAB process is active; do not overlap this stage.' }
}
function Assert-FileSha([string]$Path,[string]$Expected) {
    if ((Get-Sha256 $Path) -ne ([string]$Expected).ToLowerInvariant()) { throw "Frozen SHA mismatch: $Path" }
}
function Assert-StaticInputs($Contract,$Manifest) {
    if ($Contract.schema -ne 'TEST48_RUN_CONTRACT_V4' -or $Contract.state -ne 'CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES') { throw 'v4 contract is not code-only.' }
    if ($Manifest.schema -ne 'TEST48_METHOD_SOURCE_MANIFEST_V4' -or $Manifest.status -ne 'CODE_ONLY_CANDIDATE_WAITING_FOR_ROOT_REVIEW' -or $Manifest.test_accessed -or $Manifest.plant_started -or $Manifest.training_steps -ne 0) { throw 'v4 source manifest is not in the required code-only state.' }
    Assert-FileSha $manifestPath $Contract.method_source_manifest_sha256
    Assert-FileSha (Resolve-ManifestPath $Contract.entry_path) $Contract.entry_sha256
    Assert-FileSha (Resolve-ManifestPath $Contract.launcher_path) $Contract.launcher_sha256
    Assert-FileSha $taskbookPath $Contract.taskbook_sha256
    Assert-FileSha $codeReleasePath $Contract.code_only_release_sha256
    Assert-FileSha $dependencyReviewPath $Contract.dependency_review_sha256
    Assert-FileSha (Resolve-ManifestPath $Contract.v3_source_manifest_path) $Contract.v3_source_manifest_sha256
    $codeRelease = Read-Json $codeReleasePath
    if ($codeRelease.status -ne 'APPROVED_CODE_ONLY' -or $codeRelease.MATLAB_authorized -or $codeRelease.Plant_authorized -or $codeRelease.TEST_generation_authorized -or $codeRelease.training_authorized) { throw 'v4 authorization is not code-only.' }
    if ($Contract.method_order.Count -ne 6 -or $Manifest.methods.Count -ne 6 -or $Contract.execution.unstarted_method_ids.Count -ne 5 -or $Contract.execution.max_unique_plant_calls -ne 240 -or -not $Contract.execution.B48_reused) { throw 'Frozen six-method/240-call scope changed.' }
    for ($i=0; $i -lt 6; $i++) {
        $m = $Manifest.methods[$i]
        if ($m.method_id -cne $methodIds[$i] -or $Contract.method_order[$i].id -cne $methodIds[$i] -or $m.order -ne ($i+1)) { throw "Fixed method order changed at index $i." }
        foreach ($ref in $m.source_refs) { Assert-FileSha $ref.path $ref.sha256 }
        foreach ($ref in $m.model_refs) { Assert-FileSha $ref.path $ref.sha256 }
        foreach ($item in @(@{path=$m.input_lock_path;sha=$m.input_lock_sha256},@{path=$m.run_contract_path;sha=$m.run_contract_sha256},@{path=$m.cfg_opts_snapshot_path;sha=$m.cfg_opts_snapshot_sha256})) {
            if ([string]$item.path) { Assert-FileSha (Resolve-ManifestPath ([string]$item.path)) $item.sha }
        }
        if ($m.global_platform_lock_sha256 -cne $Manifest.global_platform_lock_sha256) { throw "Global platform lock differs on $($m.method_id)." }
    }
    foreach ($ref in $Manifest.shared_source_refs) { Assert-FileSha $ref.path $ref.sha256 }
    foreach ($ref in $Manifest.global_platform_refs) { Assert-FileSha (Resolve-ManifestPath $ref.path) $ref.sha256 }
    $canonical = [Text.StringBuilder]::new()
    foreach ($ref in $Manifest.global_platform_refs) { [void]$canonical.Append([string]$ref.path).Append(':').Append([string]$ref.sha256).Append("`n") }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($canonical.ToString())
    $platformHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    if ($platformHash -cne $Manifest.global_platform_lock_sha256 -or $platformHash -cne $Contract.global_platform_lock_sha256) { throw 'Canonical v3 B global platform reference lock changed.' }
    if ($Manifest.v4_execution.max_unique_plant_calls -ne 240 -or $Manifest.v4_execution.scene_count -ne 48 -or -not $Manifest.v4_execution.B48_reused -or $Manifest.v4_execution.v4_retries -ne 0) { throw 'v4 execution scope differs from fixed contract.' }
    foreach ($field in @('shared_scenes','cfg_opts','index')) {
        $name = @{shared_scenes='shared_scenes';cfg_opts='cfg_opts';index='index'}[$field]
        $pathName = "${name}_path"; $shaName = "${name}_sha256"
        Assert-FileSha (Resolve-ManifestPath $Manifest.v3_frozen_inputs.$pathName) $Manifest.v3_frozen_inputs.$shaName
    }
    Assert-FileSha (Resolve-ManifestPath $Manifest.v3_frozen_inputs.freeze_result_path) $Manifest.v3_frozen_inputs.freeze_result_sha256
    Assert-FileSha (Resolve-ManifestPath $Manifest.v3_frozen_inputs.freeze_os_path) $Manifest.v3_frozen_inputs.freeze_os_sha256
    Assert-DeadlineParser
}
function Assert-V3UnstartedGuard {
    $g = $manifest.v3_unstarted_guard
    if ($g.schema -cne 'TEST48V3_UNSTARTED_COMBINATION_GUARD_V1') { throw 'v3 no-prior-Plant guard schema changed.' }
    foreach ($item in @(
        @{path=$g.input_index_path;sha=$g.input_index_sha256},
        @{path=$g.b_method_batch_path;sha=$g.b_method_batch_sha256},
        @{path=$g.b_method_body_path;sha=$g.b_method_body_sha256},
        @{path=$g.b_os_exit_path;sha=$g.b_os_exit_sha256},
        @{path=$g.dssm_os_exit_path;sha=$g.dssm_os_exit_sha256},
        @{path=$g.dssm_batch_path;sha=$g.dssm_batch_sha256},
        @{path=$g.dssm_failure_path;sha=$g.dssm_failure_sha256},
        @{path=$g.dssm_status_path;sha=$g.dssm_status_sha256}
    )) { Assert-FileSha (Resolve-ManifestPath $item.path) $item.sha }
    $bOs = Read-Json (Resolve-ManifestPath $g.b_os_exit_path)
    $bBatch = Read-Json (Resolve-ManifestPath $g.b_method_batch_path)
    $bBody = Read-Json (Resolve-ManifestPath $g.b_method_body_path)
    if ($bOs.matlab_os_exit_code -ne $g.expected_v3_b_os_exit -or $bOs.method_id -cne 'B_TRACEABLE' -or
        $bBatch.status -cne 'COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $bBatch.completed_scenes -ne 48 -or $bBatch.plant_calls -ne 48 -or
        $bBody.status -cne 'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $bBody.completed_scenes -ne 48 -or $bBody.plant_calls -ne 48) {
        throw 'Pinned v3 B48 natural-OS0 receipt and complete batch/body do not match.'
    }
    $dOs = Read-Json (Resolve-ManifestPath $g.dssm_os_exit_path)
    $dBatch = Read-Json (Resolve-ManifestPath $g.dssm_batch_path)
    $dFailurePath = Resolve-ManifestPath $g.dssm_failure_path
    $dFailure = Read-Json $dFailurePath
    $dStatus = Read-Json (Resolve-ManifestPath $g.dssm_status_path)
    if ($dOs.matlab_os_exit_code -ne $g.expected_v3_dssm_os_exit -or $dOs.method_id -cne 'CORRECTED_DSSM14_G12_R32' -or
        $dBatch.status -cne 'FAILED_STOP_NO_RETRY' -or $dBatch.completed_scenes -ne 0 -or $dBatch.plant_calls -ne $g.expected_v3_dssm_plant_calls -or
        $dFailure.status -cne 'FAILED_NO_RETRY' -or $dFailure.plant_start_confirmed -ne $g.expected_v3_dssm_first_plant -or
        $dFailure.partial_raw_preserved -ne $g.expected_v3_dssm_raw -or $dFailure.scene_id -cne $g.failed_scene_id -or
        $dStatus.status -cne 'FAILED_NO_RETRY' -or $dStatus.plant_calls -ne 0 -or (Test-Path -LiteralPath $dStatus.raw_path)) {
        throw 'Pinned v3 DSSM evidence is not the exact OS1/zero-Plant/no-raw failure.'
    }
    $index = Read-Json (Resolve-ManifestPath $g.input_index_path)
    if ($index.scene_count -ne 48 -or $index.TEST_accessed -ne $true -or $index.scene_ids.Count -ne 48) { throw 'Frozen v3 index is not the original 48-scene set.' }
    $aliases = @{CORRECTED_DSSM14_G12_R32='DSSM';CORRECTED_KAN14_G12_R32='KAN';C5_M110='C5M110';C5_FREEZE_TRAINED_W0='C5FREEZE';C5_NO_DELAYED_PREDICTION='C5NOPRED'}
    foreach ($method in $g.unstarted_method_ids) {
        $alias = [string]$aliases[[string]$method]
        if (-not $alias) { throw "Unknown unstarted v3 method in guard: $method" }
        foreach ($sceneId in $index.scene_ids) {
            $marker = Join-Path (Join-Path (Join-Path (Join-Path (Join-Path $repoRoot 'experiments/c5_test48_v3/runs') $alias) $sceneId) 'attempt_01') $g.marker_name
            if (Test-Path -LiteralPath $marker -PathType Leaf) { throw "v3 combination already entered Plant; stop before v4: $marker" }
        }
    }
}
function Assert-ParentRelease($Release,[string]$Schema,[string]$Status,[bool]$Plant,[bool]$TestAccess) {
    Require-Value $Release 'schema' $Schema
    Require-Value $Release 'status' $Status
    Require-Value $Release 'taskbook_sha256' (Get-Sha256 $taskbookPath)
    Require-Value $Release 'contract_sha256' (Get-Sha256 $contractPath)
    Require-Value $Release 'method_source_manifest_sha256' (Get-Sha256 $manifestPath)
    Require-Value $Release 'entry_sha256' (Get-Sha256 (Join-Path $taskDir 'test48_entry_v4.m'))
    Require-Value $Release 'launcher_sha256' (Get-Sha256 $PSCommandPath)
    Require-Value $Release 'plant_authorized' $Plant
    Require-Value $Release 'scene_generation_authorized' $false
    Require-Value $Release 'TEST_accessed' $TestAccess
    Require-Value $Release 'training_authorized' $false
    Require-Value $Release 'no_retry' $true
}
function Get-DirectoryBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return [int64]0 }
    $sum = [int64]0
    Get-ChildItem -LiteralPath $Path -Recurse -File | ForEach-Object { $sum += [int64]$_.Length }
    $sum
}
function Assert-Budget([int]$SceneCalls,[int]$Processes) {
    $limits = $contract.limits
    $reserve = [int64]$SceneCalls * [int64]$limits.per_scene_output_reserve_bytes
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskDir))
    if ($drive.AvailableFreeSpace - $reserve -lt [int64]$limits.minimum_free_bytes_after_reserve) { throw 'Reserve-adjusted free-space floor failed; preserve historical data.' }
    $v3out = Join-Path $repoRoot 'experiments/c5_test48_v3'
    $v3report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v3'
    $v4out = Join-Path $repoRoot 'experiments/c5_test48_v4'
    $v4report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v4'
    $v5out = Join-Path $repoRoot 'experiments/c5_test48_v5'
    $v5report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v5'
    $v6out = Join-Path $repoRoot 'experiments/c5_test48_v6'
    $v6report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v6'
    $v7out = Join-Path $repoRoot 'experiments/c5_test48_v7'
    $v7report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v7'
    $used = [int64]$limits.prior_created_bytes + (Get-DirectoryBytes $v3out) + (Get-DirectoryBytes $v3report) + (Get-DirectoryBytes $v4out) + (Get-DirectoryBytes $v4report) + (Get-DirectoryBytes $v5out) + (Get-DirectoryBytes $v5report) + (Get-DirectoryBytes $v6out) + (Get-DirectoryBytes $v6report) + (Get-DirectoryBytes $v7out) + (Get-DirectoryBytes $v7report) + (Get-DirectoryBytes $taskDir) + (Get-DirectoryBytes $reportDir) + $reserve
    if ($used -gt [int64]$limits.max_output_bytes) { throw 'Cycle-wide v3/v4/v5/v6/v7/v8 outputs plus remaining reserve exceed the 80e9-byte cap.' }
    $deadline = Convert-DeadlineUtc $limits.hard_deadline_utc
    $required = ([int64]$SceneCalls * [int64]$limits.per_scene_seconds_guard) + ([int64]$Processes * [int64]$limits.process_exit_buffer_seconds)
    if (($deadline - [DateTime]::UtcNow).TotalSeconds -lt $required) { throw 'Conservative remaining deadline guard failed.' }
}
function Assert-NoOutputs([string[]]$Paths) {
    foreach ($path in $Paths) { Assert-ShortPath $path; if (Test-Path -LiteralPath $path) { throw "No-retry guard: output exists: $path" } }
}
function Write-ExitReceipt([string]$Path,[string]$Stage,[string]$Method,[int]$ExitCode,[string]$Stdout,[string]$Stderr,[string]$Started,$Snapshot) {
    if (Test-Path -LiteralPath $Path) { throw "No-retry guard: receipt exists: $Path" }
    $receipt = [ordered]@{
        schema='TEST48V4_MATLAB_OS_EXIT_V1'; mode=$Mode; stage=$Stage; method_id=$Method
        process_scope=$(if ($Method) { 'ONE_SEQUENTIAL_METHOD_MATLAB_PROCESS' } else { 'ONE_STAGE_MATLAB_PROCESS' })
        matlab_os_exit_code=$ExitCode; natural_wait_used=$true
        started_utc=$Started; completed_utc=[DateTime]::UtcNow.ToString('o')
        command_file=$PSCommandPath; command_sha256=(Get-Sha256 $PSCommandPath)
        contract_sha256=(Get-Sha256 $contractPath); source_manifest_sha256=(Get-Sha256 $manifestPath)
        stdout_path=$Stdout; stdout_sha256=$(if (Test-Path -LiteralPath $Stdout) { Get-Sha256 $Stdout } else { '' })
        stderr_path=$Stderr; stderr_sha256=$(if (Test-Path -LiteralPath $Stderr) { Get-Sha256 $Stderr } else { '' })
        TEST_accessed=($Mode -in @('PREPARE_NO_PLANT','RUN_UNSTARTED_TEST_PARENT_APPROVED')); plant_authorized=($Mode -ne 'PREPARE_NO_PLANT')
        matlab_executable=$matlabExe; thread_argument='-singleCompThread'; process_snapshot=$Snapshot
    }
    [IO.File]::WriteAllText($Path,($receipt | ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
}
function Invoke-Matlab([string]$Stage,[string]$Method,[string]$ReceiptPath,[string]$StdoutPath,[string]$StderrPath) {
    Assert-NoOutputs @($ReceiptPath,$StdoutPath,$StderrPath)
    if (-not (Test-Path -LiteralPath $matlabExe -PathType Leaf)) { throw 'Locked MATLAB R2025b executable is missing.' }
    Assert-NoMatlab
    $logDir = Split-Path -Parent $StdoutPath
    if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $prefName = 'matlab_prefdir_'+$Stage.ToLowerInvariant()+$(if ($Method) {'_'+$Method.ToLowerInvariant()} else {''})
    $pref = Join-Path $taskDir $prefName
    Assert-NoOutputs @($pref)
    New-Item -ItemType Directory -Path $pref | Out-Null
    $oldPref = $env:MATLAB_PREFDIR
    $env:MATLAB_PREFDIR = $pref
    $rootForMatlab = $repoRoot.Replace('\','/').Replace("'","''")
    $stageArg = $Stage.Replace("'","''"); $methodArg = $Method.Replace("'","''")
    $expr = "try; cd('$rootForMatlab'); addpath('experiments/c5_test48_v8'); test48_entry_v4('$stageArg','$methodArg'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
    $argLine = '-singleCompThread -wait -batch "' + $expr + '"'
    $started = [DateTime]::UtcNow.ToString('o')
    $proc = $null
    try {
        $cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
        $computer = Get-CimInstance Win32_ComputerSystem
        $proc = Start-Process -FilePath $matlabExe -ArgumentList $argLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
        $matlabPid = [int]$proc.Id
        $snapshot = Get-CimInstance Win32_Process -Filter "ProcessId=$matlabPid"
        $peak = [int64]0; $cpuSeconds = 0.0
        while (-not $proc.HasExited) {
            $proc.Refresh(); $peak = [Math]::Max($peak,[int64]$proc.PeakWorkingSet64); $cpuSeconds = $proc.TotalProcessorTime.TotalSeconds
            if ($proc.WaitForExit(5000)) { break }
        }
        $proc.Refresh(); $peak = [Math]::Max($peak,[int64]$proc.PeakWorkingSet64); $cpuSeconds = $proc.TotalProcessorTime.TotalSeconds
        $code = [int]$proc.ExitCode
        $procSnapshot = [ordered]@{pid=$matlabPid;command_line=$(if($snapshot){$snapshot.CommandLine}else{''});creation_date=$(if($snapshot){$snapshot.CreationDate}else{''});cpu_processors=$cpu;logical_cpu_count=$computer.NumberOfLogicalProcessors;physical_memory_bytes=$computer.TotalPhysicalMemory;matlab_cpu_time_s=$cpuSeconds;peak_working_set_bytes=$peak;monitor_poll_ms=5000}
        Write-ExitReceipt $ReceiptPath $Stage $Method $code $StdoutPath $StderrPath $started $procSnapshot
        if ($code -ne 0) { throw "MATLAB naturally exited OS $code; preserve evidence and stop without retry." }
    } finally {
        if ($null -ne $oldPref) { $env:MATLAB_PREFDIR = $oldPref } else { Remove-Item Env:MATLAB_PREFDIR -ErrorAction SilentlyContinue }
    }
}
function Assert-ResultSha($Release,[string]$Field,[string]$Path) { Require-Value $Release $Field (Get-Sha256 $Path) }
function Assert-PreparePass($Release) {
    $resultPath=Join-Path $reportDir 'PREPARE_NO_PLANT_RESULT_v1.json'; $osPath=Join-Path $reportDir 'PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json'
    $r=Read-Json $resultPath; $o=Read-Json $osPath
    if ($r.status -cne 'PASS_PREPARE_NO_PLANT' -or -not $r.TEST_accessed -or $r.plant_calls -ne 0 -or $r.training_steps -ne 0 -or $o.matlab_os_exit_code -ne 0) { throw 'No-Plant preparation must naturally exit OS0 with TEST input accessed and zero Plant/training.' }
    Assert-ResultSha $Release 'prepare_result_sha256' $resultPath; Assert-ResultSha $Release 'prepare_os_exit_sha256' $osPath
}
function Assert-EngineeringPass($Release) {
    Assert-PreparePass $Release
    foreach ($alias in @('DSSM','KAN')) {
        $resultPath=Join-Path $reportDir "ENGINEERING_${alias}_RESULT_v1.json"; $osPath=Join-Path $reportDir "ENGINEERING_${alias}_MATLAB_OS_EXIT_v1.json"
        $r=Read-Json $resultPath; $o=Read-Json $osPath
        if ($r.status -cne 'PASS_ENGINEERING_DEV2_FULL_RAW' -or -not $r.full_raw_numeric_comparison_pass -or $r.max_abs_numeric_difference -gt 1e-12 -or $r.plant_calls -ne 1 -or $r.TEST_accessed -or $r.training_steps -ne 0 -or $o.matlab_os_exit_code -ne 0) { throw "$alias DEV2 must pass full raw comparison and naturally exit OS0." }
        Assert-ResultSha $Release "engineering_${alias}_result_sha256" $resultPath; Assert-ResultSha $Release "engineering_${alias}_os_exit_sha256" $osPath
    }
}

$contract = Read-Json $contractPath
$manifest = Read-Json $manifestPath
Assert-StaticInputs $contract $manifest
Assert-V3UnstartedGuard

switch ($Mode) {
    'PREPARE_NO_PLANT' {
        Assert-Budget 0 1
        $releasePath=Join-Path $reportDir 'PREPARE_NO_PLANT_PARENT_RELEASE_v1.json'
        $release=Read-Json $releasePath
        Assert-ParentRelease $release 'TEST48_V4_PREPARE_NO_PLANT_RELEASE_V1' 'APPROVED_PREPARE_NO_PLANT_V1' $false $true
        Require-Value $release 'max_plant_calls' 0
        $receipt=Join-Path $reportDir 'PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json'
        $result=Join-Path $reportDir 'PREPARE_NO_PLANT_RESULT_v1.json'; $failure=Join-Path $reportDir 'PREPARE_NO_PLANT_FAILURE_v1.json'
        $stdout=Join-Path $reportDir 'logs/PREPARE_NO_PLANT.stdout.log'; $stderr=Join-Path $reportDir 'logs/PREPARE_NO_PLANT.stderr.log'
        Assert-NoOutputs @($receipt,$result,$failure,$stdout,$stderr,(Join-Path $taskDir 'matlab_prefdir_prepare_no_plant'))
        Invoke-Matlab $Mode '' $receipt $stdout $stderr
        $r=Read-Json $result
        if ($r.status -cne 'PASS_PREPARE_NO_PLANT' -or -not $r.TEST_accessed -or $r.plant_calls -ne 0 -or $r.training_steps -ne 0) { throw 'PREPARE result is incomplete or has a nonzero Plant/training count.' }
    }
    'ENGINEERING_DEV2' {
        Assert-Budget 2 2
        $releasePath=Join-Path $reportDir 'ENGINEERING_DEV2_PARENT_RELEASE_v1.json'
        $release=Read-Json $releasePath
        Assert-ParentRelease $release 'TEST48_V4_ENGINEERING_DEV2_RELEASE_V1' 'APPROVED_ENGINEERING_DEV2_V1' $true $false
        Require-Value $release 'max_plant_calls' 2; Require-Value $release 'scene_id' 'DL1018_VAL_T1_C00_W07'
        Require-Value $release 'method_ids' $runMethodIds[0..1]
        Assert-PreparePass $release
        foreach ($method in $runMethodIds[0..1]) {
            $alias=if($method -eq 'CORRECTED_DSSM14_G12_R32'){'DSSM'}else{'KAN'}
            $receipt=Join-Path $reportDir "ENGINEERING_${alias}_MATLAB_OS_EXIT_v1.json"
            $result=Join-Path $reportDir "ENGINEERING_${alias}_RESULT_v1.json"; $failure=Join-Path $reportDir "ENGINEERING_${alias}_FAILURE_v1.json"
            $stdout=Join-Path $reportDir "logs/ENGINEERING_${alias}.stdout.log"; $stderr=Join-Path $reportDir "logs/ENGINEERING_${alias}.stderr.log"
            $pref=Join-Path $taskDir ('matlab_prefdir_engineering_dev2_'+$method.ToLowerInvariant())
            Assert-NoOutputs @($receipt,$result,$failure,$stdout,$stderr,$pref,(Join-Path $taskDir ('engineering_dev2/'+$alias)))
        }
        foreach ($method in $runMethodIds[0..1]) {
            $alias=if($method -eq 'CORRECTED_DSSM14_G12_R32'){'DSSM'}else{'KAN'}
            $receipt=Join-Path $reportDir "ENGINEERING_${alias}_MATLAB_OS_EXIT_v1.json"
            $stdout=Join-Path $reportDir "logs/ENGINEERING_${alias}.stdout.log"; $stderr=Join-Path $reportDir "logs/ENGINEERING_${alias}.stderr.log"
            Invoke-Matlab $Mode $method $receipt $stdout $stderr
            $r=Read-Json (Join-Path $reportDir "ENGINEERING_${alias}_RESULT_v1.json")
            if ($r.status -cne 'PASS_ENGINEERING_DEV2_FULL_RAW' -or -not $r.full_raw_numeric_comparison_pass -or $r.plant_calls -ne 1 -or $r.TEST_accessed -or $r.training_steps -ne 0) { throw "$alias DEV2 result failed; preserve outputs and stop before next method." }
        }
    }
    'RUN_UNSTARTED_TEST_PARENT_APPROVED' {
        Assert-Budget 240 5
        $releasePath=Join-Path $reportDir 'RUN_UNSTARTED_TEST_PARENT_RELEASE_v1.json'
        $release=Read-Json $releasePath
        Assert-ParentRelease $release 'TEST48_V4_UNSTARTED_TEST_RELEASE_V1' 'APPROVED_RUN_UNSTARTED_TEST_V4' $true $true
        Require-Value $release 'max_plant_calls' 240; Require-Value $release 'scene_count' 48
        Require-Value $release 'method_ids' $runMethodIds
        $index = Read-Json (Resolve-ManifestPath $manifest.v3_frozen_inputs.index_path)
        Require-Value $release 'input_index_sha256' $manifest.v3_frozen_inputs.index_sha256
        Require-Value $release 'shared_scenes_mat_sha256' $manifest.v3_frozen_inputs.shared_scenes_sha256
        Require-Value $release 'method_cfg_opts_sha256' $manifest.v3_frozen_inputs.cfg_opts_sha256
        Require-Value $release 'scene_set_sha256' $manifest.v3_frozen_inputs.scene_set_sha256
        Require-Value $release 'freeze_result_sha256' $manifest.v3_frozen_inputs.freeze_result_sha256
        Require-Value $release 'freeze_os_exit_sha256' $manifest.v3_frozen_inputs.freeze_os_sha256
        Assert-EngineeringPass $release
        foreach ($method in $runMethodIds) {
            $m=$manifest.methods | Where-Object method_id -ceq $method
            $alias=[string]$m.alias
            $runRoot=Join-Path $taskDir "runs/$alias"
            $receipt=Join-Path $reportDir "RUN_${alias}_MATLAB_OS_EXIT_v1.json"
            $stdout=Join-Path $reportDir "logs/RUN_${alias}.stdout.log"; $stderr=Join-Path $reportDir "logs/RUN_${alias}.stderr.log"
            $pref=Join-Path $taskDir ('matlab_prefdir_run_unstarted_test_parent_approved_'+$method.ToLowerInvariant())
            Assert-NoOutputs @($runRoot,$receipt,$stdout,$stderr,$pref)
        }
        $remainingMethods=$runMethodIds.Count
        foreach ($method in $runMethodIds) {
            $m=$manifest.methods | Where-Object method_id -ceq $method; $alias=[string]$m.alias
            $receipt=Join-Path $reportDir "RUN_${alias}_MATLAB_OS_EXIT_v1.json"
            $stdout=Join-Path $reportDir "logs/RUN_${alias}.stdout.log"; $stderr=Join-Path $reportDir "logs/RUN_${alias}.stderr.log"
            $remainingScenes=$remainingMethods*48
            Assert-Budget $remainingScenes $remainingMethods
            Invoke-Matlab $Mode $method $receipt $stdout $stderr
            $body=Read-Json (Join-Path $taskDir "runs/$alias/METHOD_BODY_COMPLETE_v4.json")
            if ($body.status -cne 'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $body.scene_count -ne 48 -or $body.completed_scenes -ne 48 -or $body.plant_calls -ne 48 -or $body.training_steps -ne 0 -or $body.method_id -cne $method) { throw "$alias batch did not close naturally at 48 raw records; stop without retry." }
            $remainingMethods--
        }
    }
}
