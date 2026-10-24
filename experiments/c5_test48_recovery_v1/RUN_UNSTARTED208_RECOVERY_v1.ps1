param(
    [ValidateSet('CODE_ONLY','RUN_AFTER_PARENT_RELEASE')]
    [string]$Mode = 'CODE_ONLY'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repoRoot=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSCommandPath) '..\..'))
$recoveryDir=Split-Path -Parent $PSCommandPath
$reportDir=Join-Path $repoRoot 'reports\paper_continuation_20261023\test_handoff_incident_v1\recovery_v1'
$scopePath=Join-Path $reportDir 'RECOVERY208_SCOPE_v1.json'
$releasePath=Join-Path $reportDir 'PARENT_RECOVERY208_RUN_RELEASE_v1.json'
$tailEntryPath=Join-Path $recoveryDir 'run_dssm_tail16_v1.m'
$v9Dir=Join-Path $repoRoot 'experiments\c5_test48_v9'
$v9EntryPath=Join-Path $v9Dir 'test48_entry_v4.m'
$v9LauncherPath=Join-Path $v9Dir 'RUN_TEST48_EXACT_v1.ps1'
$v9ContractPath=Join-Path $v9Dir 'TEST48_RUN_CONTRACT_v4.json'
$v9ManifestPath=Join-Path $repoRoot 'reports\paper_continuation_20261023\test_entry_v9\TEST_METHOD_SOURCE_MANIFEST_v4.json'
$v9ReleasePath=Join-Path $repoRoot 'reports\paper_continuation_20261023\test_entry_v9\RUN_UNSTARTED_TEST_PARENT_RELEASE_v1.json'
$taskbookPath=Join-Path $repoRoot 'reports\paper_continuation_20261023\test_handoff_incident_v1\UNSTARTED208_RECOVERY_CODE_ONLY_TASKBOOK_v1_ZH.md'
$incidentDir=Join-Path $repoRoot 'reports\paper_continuation_20261023\test_handoff_incident_v1'
$indexPath=Join-Path $repoRoot 'experiments\c5_test48_v3\input\TEST_INPUT_INDEX_v1.json'
$runRoot=Join-Path $v9Dir 'runs'
$oldDssmRoot=Join-Path $runRoot 'DSSM'
$newTailRoot=Join-Path $recoveryDir 'runs\DSSM_TAIL16'
$matlabExe='C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$blocks=@(
    [ordered]@{block_id='DSSM_TAIL16';method_id='CORRECTED_DSSM14_G12_R32';alias='DSSM_TAIL16';calls=16;entry='TAIL'},
    [ordered]@{block_id='KAN';method_id='CORRECTED_KAN14_G12_R32';alias='KAN';calls=48;entry='V9'},
    [ordered]@{block_id='C5M110';method_id='C5_M110';alias='C5M110';calls=48;entry='V9'},
    [ordered]@{block_id='C5FREEZE';method_id='C5_FREEZE_TRAINED_W0';alias='C5FREEZE';calls=48;entry='V9'},
    [ordered]@{block_id='C5NOPRED';method_id='C5_NO_DELAYED_PREDICTION';alias='C5NOPRED';calls=48;entry='V9'}
)
function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file is absent: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required JSON is absent: $Path" }
    Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}
function Assert-Sha([string]$Path,[string]$Expected) {
    if ((Get-Sha256 $Path) -cne ([string]$Expected).ToLowerInvariant()) { throw "SHA-256 mismatch: $Path" }
}
function Assert-Array([object[]]$Actual,[object[]]$Expected,[string]$Name) {
    if ([string]::Join('|',[string[]]$Actual) -cne [string]::Join('|',[string[]]$Expected)) { throw "Ordered field mismatch: $Name" }
}
function Get-DirectoryBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return [long]0 }
    $sum=[long]0
    Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction Stop | ForEach-Object { $sum += [long]$_.Length }
    return $sum
}
function Assert-NoMatlab {
    $active=@(Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'")
    if ($active.Count -ne 0) { throw "A MATLAB process is active (PID $($active[0].ProcessId)); no overlap." }
}
function Convert-DeadlineUtc($Value) {
    if ($Value -is [DateTime]) { return $Value.ToUniversalTime() }
    if ($Value -is [DateTimeOffset]) { return $Value.UtcDateTime }
    [DateTimeOffset]::Parse([string]$Value).UtcDateTime
}
function Assert-DeadlineParser {
    $raw=Get-Content -Raw -LiteralPath $v9ContractPath
    $typed=$raw | ConvertFrom-Json
    $typedUtc=Convert-DeadlineUtc $typed.limits.hard_deadline_utc
    $match=[regex]::Match($raw,'"hard_deadline_utc"\s*:\s*"([^"]+)"')
    if (-not $match.Success) { throw 'Contract has no hard_deadline_utc string.' }
    $stringUtc=Convert-DeadlineUtc $match.Groups[1].Value
    $expected=[DateTimeOffset]::Parse('2026-10-24T17:01:00Z').UtcDateTime
    if ($typedUtc -ne $expected -or $stringUtc -ne $expected -or $typedUtc -ne $stringUtc) { throw 'Typed/string UTC deadline roundtrip failed.' }
    return $typedUtc
}
function Escape-MatlabString([string]$Value) {
    $forward=$Value.Replace([string][char]92,'/')
    $forward.Replace([string][char]39,([string][char]39)+([string][char]39))
}
function Assert-StaticSources {
    Assert-Sha $v9EntryPath 'b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1'
    Assert-Sha $v9LauncherPath '7034e2e6d5459fb33e9a66dcc2ad32c80677b7850a1eacd510b6d1648d631c8c'
    Assert-Sha $v9ContractPath 'd4132d2a00693bde5ca234e4ac7cf07ba2695971a086b2275539842d7f5c3210'
    Assert-Sha $v9ManifestPath 'f8998debf70835d0fb4dcab8c9d8fe77ef1702be80559622badd3dafa1b77d80'
    Assert-Sha $v9ReleasePath '59fae7920eb498d06f29c5c8d7eb1191843de79a640b6ec46e5c40fd32b1d06a'
    Assert-Sha $taskbookPath '5a179be1f740d9fc5dba224744081db9f689e28226be5fd468041cd4893173fd'
    Assert-Sha (Join-Path $incidentDir 'PARENT_FIRST31_COMMITTED_FILE_AUDIT_v1.json') '5e0e2299c397375eafc680b617dba6e99cb8b3d2e434fc54b8541e63339746d5'
    Assert-Sha (Join-Path $incidentDir 'PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json') '09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15'
    Assert-Sha $indexPath '90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68'
    $scope=Read-Json $scopePath; $idx=Read-Json $indexPath
    if ($scope.schema -cne 'RECOVERY208_SCOPE_V1' -or $scope.status -cne 'FIXED_SCOPE_CODE_ONLY_NO_PLANT' -or $scope.total_new_plant_calls -ne 208) { throw 'Scope is not the fixed 208-call code-only scope.' }
    $ids=@($idx.scene_ids); $scopeBlocks=@($scope.blocks)
    if ($ids.Count -ne 48 -or $scopeBlocks.Count -ne 5 -or [string]$idx.scene_set_sha256 -cne [string]$scope.frozen_scene_set_sha256) { throw 'Frozen input/scope cardinality changed.' }
    Assert-Array @($scopeBlocks.block_id) @('DSSM_TAIL16','KAN','C5M110','C5FREEZE','C5NOPRED') 'block order'
    Assert-Array @($scopeBlocks[0].scene_ids) @($ids[32..47]) 'DSSM tail scene order'
    Assert-Array @($scopeBlocks[0].canonical_batch_indices) @(33..48) 'DSSM canonical batch indices'
    Assert-Array @($scopeBlocks[0].tail_local_indices) @(1..16) 'DSSM tail-local indices'
    foreach ($b in $scopeBlocks[1..4]) { Assert-Array @($b.scene_ids) $ids "$($b.block_id) scene order" }
    if ($scopeBlocks[0].old_DSSM_natural_os_exit -cne 'UNKNOWN' -or -not $scopeBlocks[0].do_not_rerun_or_modify_old_records) { throw 'Old DSSM OS state or no-rerun guard changed.' }
    Assert-DeadlineParser | Out-Null
    $contract=Read-Json $v9ContractPath
    if ($contract.execution.max_unique_plant_calls -ne 240 -or $contract.execution.scene_count -ne 48 -or -not $contract.execution.B48_reused) { throw 'Frozen v9 240-call contract changed.' }
    if (-not (Test-Path -LiteralPath $tailEntryPath -PathType Leaf)) { throw 'Recovery DSSM tail entry is absent.' }
    return [pscustomobject]@{
        scope_sha256=(Get-Sha256 $scopePath);tail_entry_sha256=(Get-Sha256 $tailEntryPath)
        launcher_sha256=(Get-Sha256 $PSCommandPath);v9_entry_sha256=(Get-Sha256 $v9EntryPath)
        v9_launcher_sha256=(Get-Sha256 $v9LauncherPath);v9_contract_sha256=(Get-Sha256 $v9ContractPath)
        v9_manifest_sha256=(Get-Sha256 $v9ManifestPath);v9_parent_release_sha256=(Get-Sha256 $v9ReleasePath)
        taskbook_sha256=(Get-Sha256 $taskbookPath)
    }
}
function Assert-OldDssmState($Ids) {
    $batch=Read-Json (Join-Path $oldDssmRoot 'METHOD_BATCH_STATUS_v4.json')
    if ($batch.method_id -cne 'CORRECTED_DSSM14_G12_R32' -or $batch.status -cne 'RUNNING' -or
        $batch.completed_scenes -ne 31 -or $batch.plant_calls -ne 31 -or $batch.records.Count -ne 31) {
        throw 'Original DSSM no longer matches 31 committed scenes/31 Plant calls.'
    }
    for ($i=0; $i -lt 31; $i++) {
        if ($batch.records[$i].batch_index -ne ($i+1) -or $batch.records[$i].scene_id -cne $Ids[$i] -or
            $batch.records[$i].status -cne 'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT') { throw "Original DSSM metadata changed at index $($i+1)." }
    }
    $scene32=$Ids[31]; $attempt=Join-Path (Join-Path $oldDssmRoot $scene32) 'attempt_01'
    $status=Read-Json (Join-Path $attempt 'run_status_v4.json')
    if ($status.scene_id -cne $scene32 -or $status.batch_index -ne 32 -or $status.status -cne 'RUNNING_PREPLANT' -or
        -not (Test-Path -LiteralPath (Join-Path $attempt 'first_plant_step.marker') -PathType Leaf)) { throw 'Original scene32 status/marker changed.' }
    $markers=@(Get-ChildItem -LiteralPath $oldDssmRoot -Recurse -File -Filter 'first_plant_step.marker' |
        ForEach-Object { Split-Path (Split-Path $_.DirectoryName -Parent) -Leaf } | Sort-Object)
    $expected=@($Ids[0..31] | Sort-Object)
    Assert-Array $markers $expected 'original DSSM marker inventory'
    $oldReceipt=Join-Path (Split-Path -Parent $v9ManifestPath) 'RUN_DSSM_MATLAB_OS_EXIT_v1.json'
    if (Test-Path -LiteralPath $oldReceipt) { throw 'Original DSSM OS receipt exists; stop for parent review.' }
}
function Assert-UnstartedDestinations {
    if (Test-Path -LiteralPath $newTailRoot) { throw 'DSSM tail output exists; no retry or resume.' }
    foreach ($b in $blocks | Where-Object { $_.entry -eq 'V9' }) {
        $methodOut=Join-Path $runRoot $b.alias
        $oldReceipt=Join-Path (Split-Path -Parent $v9ManifestPath) ('RUN_'+$b.alias+'_MATLAB_OS_EXIT_v1.json')
        if ((Test-Path -LiteralPath $methodOut) -or (Test-Path -LiteralPath $oldReceipt)) { throw "Existing v9 output/receipt: $($b.method_id)" }
    }
    foreach ($b in $blocks) {
        foreach ($name in @($b.block_id+'_RECOVERY208_PROCESS_OS_EXIT_v1.json',$b.block_id+'_RECOVERY208_BLOCK_COMPLETION_v1.json',$b.block_id+'_stdout.bin',$b.block_id+'_stderr.bin')) {
            if (Test-Path -LiteralPath (Join-Path $reportDir $name)) { throw "Recovery artifact exists for $($b.block_id); no retry." }
        }
        if (Test-Path -LiteralPath (Join-Path $reportDir ('MATLAB_PREFDIR\'+$b.block_id))) { throw "MATLAB_PREFDIR exists for $($b.block_id)." }
    }
}
function Assert-Budget([long]$RemainingCalls,[int]$RemainingProcesses,$Contract) {
    $limits=$Contract.limits; $deadline=Assert-DeadlineParser
    $need=[long]$RemainingCalls*[long]$limits.per_scene_seconds_guard+[long]$RemainingProcesses*[long]$limits.process_exit_buffer_seconds
    if (($deadline-[DateTime]::UtcNow).TotalSeconds -lt $need) { throw 'Deadline guard failed.' }
    $drive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($repoRoot))
    $reserve=[long]$RemainingCalls*[long]$limits.per_scene_output_reserve_bytes
    if (($drive.AvailableFreeSpace-$reserve) -lt [long]$limits.minimum_free_bytes_after_reserve) { throw 'Reserve-adjusted free-space floor failed.' }
    $dirs=@('experiments\c5_test48_v3','reports\paper_continuation_20261023\test_entry_v3',
        'experiments\c5_test48_v4','reports\paper_continuation_20261023\test_entry_v4',
        'experiments\c5_test48_v5','reports\paper_continuation_20261023\test_entry_v5',
        'experiments\c5_test48_v6','reports\paper_continuation_20261023\test_entry_v6',
        'experiments\c5_test48_v7','reports\paper_continuation_20261023\test_entry_v7',
        'experiments\c5_test48_v8','reports\paper_continuation_20261023\test_entry_v8',
        'experiments\c5_test48_v9','reports\paper_continuation_20261023\test_entry_v9',
        'experiments\c5_test48_recovery_v1','reports\paper_continuation_20261023\test_handoff_incident_v1\recovery_v1')
    $bytes=[long]$limits.prior_created_bytes
    foreach ($relative in $dirs) { $bytes += Get-DirectoryBytes (Join-Path $repoRoot $relative) }
    if (($bytes+$reserve) -gt [long]$limits.max_output_bytes) { throw 'Output cap plus reserve exceeded.' }
}
function Assert-RunRelease($Identity) {
    $r=Read-Json $releasePath
    if ($r.schema -cne 'RECOVERY208_RUN_RELEASE_V1' -or $r.status -cne 'APPROVED_RUN_RECOVERY208' -or
        -not $r.MATLAB_authorized -or -not $r.Plant_authorized -or -not $r.TEST_run_authorized -or
        $r.TEST_generation_authorized -or $r.training_authorized -or $r.training_steps -ne 0 -or $r.optimizer_steps -ne 0 -or
        $r.parameter_or_seed_search -or $r.max_plant_calls -ne 208 -or $r.scene_count -ne 48 -or
        -not $r.B48_reused -or -not $r.no_retry -or $r.original_DSSM_natural_os_exit -cne 'UNKNOWN' -or -not $r.scene32_reuse_without_rerun) {
        throw 'No exact parent authorization for recovery208.'
    }
    Assert-Array @($r.block_order) @('DSSM_TAIL16','KAN','C5M110','C5FREEZE','C5NOPRED') 'release block order'
    Assert-Array @($r.method_ids) @('CORRECTED_DSSM14_G12_R32','CORRECTED_KAN14_G12_R32','C5_M110','C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION') 'release method IDs'
    Assert-Array @($r.plant_calls_by_block) @(16,48,48,48,48) 'release per-block calls'
    $fields=@(
        @{name='scope_sha256';value=$Identity.scope_sha256},@{name='recovery_launcher_sha256';value=$Identity.launcher_sha256},
        @{name='dssm_tail_entry_sha256';value=$Identity.tail_entry_sha256},@{name='v9_entry_sha256';value=$Identity.v9_entry_sha256},
        @{name='v9_launcher_sha256';value=$Identity.v9_launcher_sha256},@{name='v9_contract_sha256';value=$Identity.v9_contract_sha256},
        @{name='v9_manifest_sha256';value=$Identity.v9_manifest_sha256},@{name='v9_parent_release_sha256';value=$Identity.v9_parent_release_sha256},
        @{name='taskbook_sha256';value=$Identity.taskbook_sha256},
        @{name='first31_parent_audit_sha256';value='5e0e2299c397375eafc680b617dba6e99cb8b3d2e434fc54b8541e63339746d5'},
        @{name='scene32_parent_identity_sha256';value='09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15'}
    )
    foreach ($f in $fields) { if ([string]$r.($f.name) -cne [string]$f.value) { throw "Release binding differs: $($f.name)" } }
}
function Assert-BlockComplete($Block) {
    if ($Block.entry -eq 'TAIL') {
        $dir=$newTailRoot; $body=Read-Json (Join-Path $dir 'METHOD_BODY_COMPLETE_v1.json')
        $batch=Read-Json (Join-Path $dir 'METHOD_BATCH_STATUS_v1.json')
        if ($body.schema -cne 'RECOVERY208_DSSM_TAIL16_BODY_V1' -or $body.status -cne 'RECOVERY_TAIL16_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or
            $body.completed_scenes -ne 16 -or $body.plant_calls -ne 16 -or $body.DSSM_full_48_complete -or
            $body.original_DSSM_natural_os_exit -cne 'UNKNOWN' -or $batch.status -cne 'RECOVERY_TAIL16_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or
            $batch.completed_scenes -ne 16 -or $batch.plant_calls -ne 16) { throw 'DSSM tail body/batch is not exactly 16 complete.' }
        $bodyPath=Join-Path $dir 'METHOD_BODY_COMPLETE_v1.json'; $batchPath=Join-Path $dir 'METHOD_BATCH_STATUS_v1.json'
    } else {
        $dir=Join-Path $runRoot $Block.alias; $body=Read-Json (Join-Path $dir 'METHOD_BODY_COMPLETE_v4.json')
        $batch=Read-Json (Join-Path $dir 'METHOD_BATCH_STATUS_v4.json')
        if ($body.status -cne 'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $body.method_id -cne $Block.method_id -or
            $body.completed_scenes -ne 48 -or $body.plant_calls -ne 48 -or $batch.status -cne 'COMPLETE_RAW_PENDING_PARENT_AUDIT' -or
            $batch.completed_scenes -ne 48 -or $batch.plant_calls -ne 48) { throw "Frozen v9 method incomplete: $($Block.method_id)" }
        $bodyPath=Join-Path $dir 'METHOD_BODY_COMPLETE_v4.json'; $batchPath=Join-Path $dir 'METHOD_BATCH_STATUS_v4.json'
    }
    [pscustomobject]@{status=[string]$body.status;completed_scenes=[int]$body.completed_scenes;plant_calls=[int]$body.plant_calls;body_path=$bodyPath;batch_path=$batchPath}
}
function Write-NewJson([string]$Path,$Value) {
    if (Test-Path -LiteralPath $Path) { throw "No-retry artifact already exists: $Path" }
    Set-Content -LiteralPath $Path -Value (ConvertTo-Json -InputObject $Value -Depth 16) -Encoding utf8
}
function Invoke-Block($Block,$Identity,$ReleaseSha,[int]$BlockNumber,[long]$RemainingCalls,[int]$RemainingProcesses) {
    Assert-NoMatlab
    $contract=Read-Json $v9ContractPath
    Assert-Budget $RemainingCalls $RemainingProcesses $contract
    if ($Block.entry -eq 'TAIL') {
        $entryDir=$recoveryDir; $entryPath=$tailEntryPath; $literal=Escape-MatlabString $entryDir
        $batchCode="addpath('$literal'); run_dssm_tail16_v1();"
    } else {
        $entryDir=$v9Dir; $entryPath=$v9EntryPath; $literal=Escape-MatlabString $entryDir
        $method=Escape-MatlabString $Block.method_id
        $batchCode="addpath('$literal'); test48_entry_v4('RUN_UNSTARTED_TEST_PARENT_APPROVED','$method');"
    }
    $stdoutPath=Join-Path $reportDir ($Block.block_id+'_stdout.bin')
    $stderrPath=Join-Path $reportDir ($Block.block_id+'_stderr.bin')
    $receiptPath=Join-Path $reportDir ($Block.block_id+'_RECOVERY208_PROCESS_OS_EXIT_v1.json')
    $completionPath=Join-Path $reportDir ($Block.block_id+'_RECOVERY208_BLOCK_COMPLETION_v1.json')
    $prefDir=Join-Path (Join-Path $reportDir 'MATLAB_PREFDIR') $Block.block_id
    foreach ($p in @($stdoutPath,$stderrPath,$receiptPath,$completionPath,$prefDir)) {
        if (Test-Path -LiteralPath $p) { throw "Existing process artifact for $($Block.block_id); no retry." }
    }
    New-Item -ItemType Directory -Path $prefDir | Out-Null
    $psi=[Diagnostics.ProcessStartInfo]::new()
    $psi.FileName=$matlabExe; $psi.WorkingDirectory=$repoRoot
    $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
    $psi.Environment['MATLAB_PREFDIR']=$prefDir
    foreach ($arg in @('-singleCompThread','-wait','-batch',$batchCode)) { [void]$psi.ArgumentList.Add($arg) }
    $started=[DateTimeOffset]::UtcNow; $stdoutStream=$null; $stderrStream=$null; $p=$null
    try {
        $stdoutStream=[IO.File]::Open($stdoutPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        $stderrStream=[IO.File]::Open($stderrPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
        $p=[Diagnostics.Process]::new(); $p.StartInfo=$psi
        if (-not $p.Start()) { throw 'Process.Start returned false.' }
    } catch {
        if ($null -ne $stdoutStream) { $stdoutStream.Dispose() }
        if ($null -ne $stderrStream) { $stderrStream.Dispose() }
        Write-NewJson $receiptPath ([ordered]@{
            schema='RECOVERY208_PROCESS_OS_EXIT_V1';status='LAUNCH_FAILED_NO_RETRY'
            block_id=$Block.block_id;method_id=$Block.method_id;process_started=$false
            natural_wait_for_exit=$false;matlab_os_exit_code=$null;error=$_.Exception.Message
            recovery_launcher_path=$PSCommandPath;recovery_launcher_sha256=$Identity.launcher_sha256
            recovery_ps_pid=$PID;ps_version=$PSVersionTable.PSVersion.ToString()
            matlab_entry_path=$entryPath;matlab_entry_sha256=(Get-Sha256 $entryPath)
            matlab_prefdir=$prefDir;stdout_path=$stdoutPath;stderr_path=$stderrPath
            parent_release_sha256=$ReleaseSha;created_utc=[DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        })
        throw
    }
    $processId=[int]$p.Id
    $stdoutCopy=$p.StandardOutput.BaseStream.CopyToAsync($stdoutStream)
    $stderrCopy=$p.StandardError.BaseStream.CopyToAsync($stderrStream)
    $p.WaitForExit()
    $finished=[DateTimeOffset]::UtcNow
    $osExitCode=[int]$p.ExitCode
    $streamError=''
    try { $stdoutCopy.GetAwaiter().GetResult() } catch { $streamError=$_.Exception.Message }
    try { $stderrCopy.GetAwaiter().GetResult() } catch { if($streamError){$streamError+='; '}; $streamError+=$_.Exception.Message }
    try { $stdoutStream.Dispose() } catch { if($streamError){$streamError+='; '}; $streamError+=$_.Exception.Message }
    try { $stderrStream.Dispose() } catch { if($streamError){$streamError+='; '}; $streamError+=$_.Exception.Message }
    $stdoutSha=''; $stderrSha=''; $logHashError=''
    try { $stdoutSha=Get-Sha256 $stdoutPath } catch { $logHashError=$_.Exception.Message }
    try { $stderrSha=Get-Sha256 $stderrPath } catch { if($logHashError){$logHashError+='; '}; $logHashError+=$_.Exception.Message }
    $osReceipt=[ordered]@{
        schema='RECOVERY208_PROCESS_OS_EXIT_V1';status='NATURAL_OS_EXIT_RECORDED'
        block_id=$Block.block_id;block_index=$BlockNumber;method_id=$Block.method_id
        expected_new_plant_calls=[int]$Block.calls;process_started=$true;process_id=$processId
        recovery_ps_pid=$PID;ps_version=$PSVersionTable.PSVersion.ToString()
        process_start_utc=$started.ToString('yyyy-MM-ddTHH:mm:ssZ');natural_wait_for_exit=$true
        process_exit_utc=$finished.ToString('yyyy-MM-ddTHH:mm:ssZ');matlab_os_exit_code=$osExitCode
        matlab_executable=$matlabExe;matlab_arguments=@('-singleCompThread','-wait','-batch',$batchCode)
        matlab_prefdir=$prefDir;thread_argument='-singleCompThread'
        matlab_entry_path=$entryPath;matlab_entry_sha256=(Get-Sha256 $entryPath)
        recovery_launcher_path=$PSCommandPath;recovery_launcher_sha256=$Identity.launcher_sha256
        recovery_scope_path=$scopePath;recovery_scope_sha256=$Identity.scope_sha256
        source_manifest_path=$v9ManifestPath;source_manifest_sha256=$Identity.v9_manifest_sha256
        v9_scientific_entry_path=$v9EntryPath;v9_scientific_entry_sha256=$Identity.v9_entry_sha256
        v9_parent_release_path=$v9ReleasePath;v9_parent_release_sha256=$Identity.v9_parent_release_sha256
        recovery_parent_release_path=$releasePath;recovery_parent_release_sha256=$ReleaseSha
        stdout_path=$stdoutPath;stdout_sha256=$stdoutSha;stderr_path=$stderrPath;stderr_sha256=$stderrSha
        log_hash_error=$logHashError;stream_copy_error=$streamError
        training_steps=0;optimizer_steps=0;parameter_or_seed_search=$false
        original_DSSM_natural_os_exit='UNKNOWN';scene32_reused_without_rerun=$true
    }
    Write-NewJson $receiptPath $osReceipt
    if ($osExitCode -ne 0) {
        Write-NewJson $completionPath ([ordered]@{schema='RECOVERY208_BLOCK_COMPLETION_REVIEW_V1';status='NOT_CHECKED_NONZERO_EXIT';block_id=$Block.block_id;matlab_os_exit_code=$osExitCode;created_utc=[DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')})
        throw "MATLAB exited naturally with code $osExitCode for $($Block.block_id); OS receipt preserved, no retry."
    }
    try {
        if ($logHashError -or $streamError) { throw "Process log capture/hash failed: $logHashError $streamError" }
        $review=Assert-BlockComplete $Block
        $completion=[ordered]@{
            schema='RECOVERY208_BLOCK_COMPLETION_REVIEW_V1';status='BLOCK_COMPLETE'
            block_id=$Block.block_id;method_id=$Block.method_id;body_status=$review.status
            completed_scenes=$review.completed_scenes;plant_calls=$review.plant_calls
            body_path=$review.body_path;body_sha256=(Get-Sha256 $review.body_path)
            batch_path=$review.batch_path;batch_sha256=(Get-Sha256 $review.batch_path)
            process_os_exit_receipt=$receiptPath;process_os_exit_receipt_sha256=(Get-Sha256 $receiptPath)
            created_utc=[DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
        Write-NewJson $completionPath $completion
    } catch {
        Write-NewJson $completionPath ([ordered]@{
            schema='RECOVERY208_BLOCK_COMPLETION_REVIEW_V1';status='BLOCK_OUTPUT_INVALID_NO_RETRY'
            block_id=$Block.block_id;method_id=$Block.method_id;matlab_os_exit_code=$osExitCode
            validation_error=$_.Exception.Message;process_os_exit_receipt=$receiptPath
            created_utc=[DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        })
        throw
    }
}
$identity=Assert-StaticSources
$index=Read-Json $indexPath
Assert-OldDssmState @($index.scene_ids)
Assert-UnstartedDestinations
Assert-NoMatlab
if ($Mode -eq 'CODE_ONLY') {
    Write-Output ('CODE_ONLY_VALIDATED; MATLAB/Plant not started; scope SHA-256='+$identity.scope_sha256)
    return
}
Assert-RunRelease $identity
if (-not (Test-Path -LiteralPath $matlabExe -PathType Leaf)) { throw "MATLAB R2025b absent: $matlabExe" }
$release=Read-Json $releasePath; $releaseSha=Get-Sha256 $releasePath
$remainingCalls=[long]208
for ($i=0; $i -lt $blocks.Count; $i++) {
    $remainingCalls -= [long]$blocks[$i].calls
    $callsForGuard=$remainingCalls+[long]$blocks[$i].calls
    $processesForGuard=$blocks.Count-$i
    Invoke-Block $blocks[$i] $identity $releaseSha ($i+1) $callsForGuard $processesForGuard
    Assert-NoMatlab
}
Write-Output 'RECOVERY208_BLOCKS_COMPLETE; five sequential processes receipted; statistical reader not run.'
