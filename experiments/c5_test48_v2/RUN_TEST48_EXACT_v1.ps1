param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('DEV_INPUT_EQUIVALENCE_ONLY','TEST_INPUT_FREEZE_ONLY','LOCKED_TEST48_PARENT_APPROVED')]
    [string]$Mode
)
$ErrorActionPreference = 'Stop'
$taskDir = [IO.Path]::GetDirectoryName($PSCommandPath)
$repoRoot = [IO.Path]::GetFullPath((Join-Path $taskDir '..\..'))
$reportDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v2'
$contractPath = Join-Path $taskDir 'TEST48_RUN_CONTRACT_v1.json'
$manifestPath = Join-Path $reportDir 'TEST_METHOD_SOURCE_MANIFEST_v1.json'
$codeOnlyReleasePath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_CODE_ONLY_PARENT_RELEASE_v1.json'
$taskbookPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_CODE_ONLY_TASKBOOK_ZH.md'
$identityPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_readiness_readonly/TEST_METHOD_IDENTITIES_v1.json'
$readinessPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_readiness_readonly/TEST_READINESS_SOURCE_FINDINGS_v1_ZH.md'
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing frozen file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Resolve-ManifestPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return $Path }
    return Join-Path $repoRoot $Path
}
function Read-Json([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required authorization/evidence file is absent: $Path" }
    Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}
function Require-Value($Object,[string]$Name,$Expected) {
    if (-not ($Object.PSObject.Properties.Name -contains $Name)) { throw "Required field '$Name' is absent." }
    if ($Object.$Name -is [bool] -or $Expected -is [bool]) {
        if ([bool]$Object.$Name -ne [bool]$Expected) { throw "Authorization field '$Name' does not equal the required value." }
    } elseif ([string]$Object.$Name -cne [string]$Expected) { throw "Authorization field '$Name' does not equal the required value." }
}
function Convert-DeadlineUtc($Value) {
    if ($Value -is [DateTime]) { return $Value.ToUniversalTime() }
    if ($Value -is [DateTimeOffset]) { return $Value.UtcDateTime }
    return [DateTimeOffset]::Parse([string]$Value).UtcDateTime
}
function Assert-DeadlineParser() {
    $raw = Get-Content -Raw -LiteralPath $contractPath
    $typed = $raw | ConvertFrom-Json
    $typedUtc = Convert-DeadlineUtc $typed.limits.hard_deadline_utc
    $match = [regex]::Match($raw,'"hard_deadline_utc"\s*:\s*"([^"]+)"')
    if (-not $match.Success) { throw 'The actual contract JSON has no hard_deadline_utc string.' }
    $stringUtc = Convert-DeadlineUtc $match.Groups[1].Value
    $expected = [DateTimeOffset]::Parse('2026-10-24T17:01:00Z').UtcDateTime
    if ($typedUtc -ne $expected -or $stringUtc -ne $expected -or $typedUtc -ne $stringUtc) {
        throw 'PS7 DateTime/string UTC conversion failed the exact deadline roundtrip.'
    }
}
function Assert-NoMatlab() {
    $active = Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'"
    if ($active) { throw 'A MATLAB process is active. Do not overlap TEST entry work.' }
}
function Assert-ShortPath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute.Length -ge 240) { throw "Planned new output path is too long ($($absolute.Length)): $absolute" }
}
function Assert-FrozenInputs($Contract,$Manifest) {
    if ((Get-Sha256 $taskbookPath) -ne $Contract.taskbook_sha256) { throw 'Taskbook SHA changed.' }
    if ((Get-Sha256 $codeOnlyReleasePath) -ne $Contract.code_only_release_sha256) { throw 'Code-only parent release SHA changed.' }
    if ((Get-Sha256 $manifestPath) -ne $Contract.method_source_manifest_sha256) { throw 'Method source manifest SHA changed.' }
    if ((Get-Sha256 $identityPath) -ne $Manifest.method_identity_table_sha256 -or
        (Get-Sha256 $readinessPath) -ne $Manifest.readiness_report_sha256) { throw 'Readiness identities changed.' }
    $resourcePath=Resolve-ManifestPath ([string]$Contract.limits.prior_creation_observation_path)
    if ((Get-Sha256 $resourcePath) -ne $Contract.limits.prior_creation_observation_sha256) { throw 'Cycle-wide resource baseline SHA changed.' }
    $resource=Read-Json $resourcePath
    if ([int64]$resource.observed_created_bytes -ne [int64]$Contract.limits.prior_created_bytes -or
        $resource.TEST_started -ne $false -or $resource.stat_errors.Count -ne 0) { throw 'Cycle-wide resource baseline fields differ from the frozen contract.' }
    if ($Manifest.schema -ne 'TEST48_METHOD_SOURCE_MANIFEST_V1' -or
        $Manifest.test_accessed -ne $false -or $Manifest.plant_started -ne $false -or
        $Manifest.methods.Count -ne 6 -or $Contract.method_order.Count -ne 6) { throw 'Source manifest scope/schema is invalid.' }
    for ($i=0; $i -lt 6; $i++) {
        if ($Manifest.methods[$i].method_id -cne $Contract.method_order[$i].id -or
            $Manifest.methods[$i].alias -cne $Contract.method_order[$i].alias -or
            $Manifest.methods[$i].order -ne ($i+1)) { throw 'Six-method order/alias differs from the frozen contract.' }
        foreach ($ref in $Manifest.methods[$i].source_refs) {
            if ((Get-Sha256 $ref.path) -ne $ref.sha256) { throw "Method source changed: $($ref.path)" }
        }
        foreach ($ref in $Manifest.methods[$i].model_refs) {
            if ((Get-Sha256 $ref.path) -ne $ref.sha256) { throw "Method model/normalizer changed: $($ref.path)" }
        }
        $methodArtifacts = @(
            @{path=[string]$Manifest.methods[$i].input_lock_path; sha=[string]$Manifest.methods[$i].input_lock_sha256},
            @{path=[string]$Manifest.methods[$i].run_contract_path; sha=[string]$Manifest.methods[$i].run_contract_sha256},
            @{path=[string]$Manifest.methods[$i].cfg_opts_snapshot_path; sha=[string]$Manifest.methods[$i].cfg_opts_snapshot_sha256}
        )
        foreach ($artifact in $methodArtifacts) {
            $pathValue=$artifact.path; $shaValue=$artifact.sha
            if ($pathValue) {
                if (-not $shaValue -or (Get-Sha256 (Resolve-ManifestPath $pathValue)) -ne $shaValue) { throw "Method identity artifact changed: $pathValue" }
            }
        }
    }
    foreach ($ref in $Manifest.shared_source_refs) {
        if ((Get-Sha256 $ref.path) -ne $ref.sha256) { throw "Shared input/source changed: $($ref.path)" }
    }
    $codeOnly = Read-Json $codeOnlyReleasePath
    if ($codeOnly.status -ne 'APPROVED_CODE_IMPLEMENTATION_ONLY' -or
        $codeOnly.MATLAB_authorized -or $codeOnly.Plant_authorized -or
        $codeOnly.TEST_generation_authorized -or $codeOnly.TEST_unsealed -or $codeOnly.training_authorized) {
        throw 'Code-only release must remain non-authorizing for all execution modes.'
    }
}
function Assert-ParentRelease($Release,[string]$ExpectedSchema,[string]$ExpectedStatus,[bool]$Plant,[bool]$SceneGeneration,[bool]$TestAccess) {
    Require-Value $Release 'schema' $ExpectedSchema
    Require-Value $Release 'status' $ExpectedStatus
    Require-Value $Release 'taskbook_sha256' (Get-Sha256 $taskbookPath)
    Require-Value $Release 'contract_sha256' (Get-Sha256 $contractPath)
    Require-Value $Release 'method_source_manifest_sha256' (Get-Sha256 $manifestPath)
    Require-Value $Release 'plant_authorized' $Plant
    Require-Value $Release 'scene_generation_authorized' $SceneGeneration
    Require-Value $Release 'TEST_accessed' $TestAccess
    Require-Value $Release 'training_authorized' $false
    Require-Value $Release 'entry_sha256' (Get-Sha256 (Join-Path $taskDir 'test48_entry_v1.m'))
    Require-Value $Release 'launcher_sha256' (Get-Sha256 $PSCommandPath)
}
function Write-ExitReceipt([string]$Path,[string]$Stage,[string]$Method,[int]$ExitCode,[string]$Stdout,[string]$Stderr,[string]$StartUtc,$ProcessSnapshot) {
    if (Test-Path -LiteralPath $Path) { throw "Refusing to overwrite exit record: $Path" }
    $receipt = [ordered]@{
        schema='TEST48_MATLAB_OS_EXIT_V1'; mode=$Mode; stage=$Stage; method_id=$Method
        process_scope=$(if ($Method) { 'ONE_SEQUENTIAL_METHOD_MATLAB_PROCESS' } else { 'ONE_STAGE_MATLAB_PROCESS' })
        matlab_os_exit_code=$ExitCode; natural_wait_used=$true
        started_utc=$StartUtc; completed_utc=[DateTime]::UtcNow.ToString('o')
        command_file=$PSCommandPath; command_sha256=(Get-Sha256 $PSCommandPath)
        contract_sha256=(Get-Sha256 $contractPath); source_manifest_sha256=(Get-Sha256 $manifestPath)
        stdout_path=$Stdout; stdout_sha256=$(if (Test-Path -LiteralPath $Stdout) { Get-Sha256 $Stdout } else { '' })
        stderr_path=$Stderr; stderr_sha256=$(if (Test-Path -LiteralPath $Stderr) { Get-Sha256 $Stderr } else { '' })
        TEST_accessed=($Mode -ne 'DEV_INPUT_EQUIVALENCE_ONLY'); plant_authorized=($Mode -eq 'LOCKED_TEST48_PARENT_APPROVED')
        matlab_executable=$matlabExe; thread_argument='-singleCompThread'; process_snapshot=$ProcessSnapshot
    }
    [IO.File]::WriteAllText($Path,($receipt | ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
}
function Invoke-MatlabStage([string]$Stage,[string]$Method,[string]$ReceiptPath,[string]$StdoutPath,[string]$StderrPath) {
    foreach ($p in @($ReceiptPath,$StdoutPath,$StderrPath)) { Assert-ShortPath $p; if (Test-Path -LiteralPath $p) { throw "No-retry guard: output exists: $p" } }
    if (-not (Test-Path -LiteralPath $matlabExe -PathType Leaf)) { throw 'Locked MATLAB R2025b executable is missing.' }
    Assert-NoMatlab
    $logDir = Split-Path -Parent $StdoutPath
    if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $pref = Join-Path $taskDir ('matlab_prefdir_'+$Stage.ToLowerInvariant()+$(if($Method){'_'+$Method.ToLowerInvariant()}else{''}))
    Assert-ShortPath $pref
    if (Test-Path -LiteralPath $pref) { throw "No-retry guard: MATLAB preference directory already exists: $pref" }
    New-Item -ItemType Directory -Path $pref | Out-Null
    $env:MATLAB_PREFDIR = $pref
    $rootForMatlab = $repoRoot.Replace('\','/').Replace("'","''")
    $modeForMatlab = $Stage.Replace("'","''")
    $methodForMatlab = $Method.Replace("'","''")
    $expr = "try; cd('$rootForMatlab'); addpath('experiments/c5_test48_v2'); test48_entry_v1('$modeForMatlab','$methodForMatlab'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
    $argLine = '-singleCompThread -wait -batch "' + $expr + '"'
    $started = [DateTime]::UtcNow.ToString('o')
    $cpuInfo = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    $computerInfo = Get-CimInstance Win32_ComputerSystem
    $proc = Start-Process -FilePath $matlabExe -ArgumentList $argLine -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    $matlabPid = [int]$proc.Id
    $snapshot = Get-CimInstance Win32_Process -Filter "ProcessId=$matlabPid"
    $peakWorkingSet = [int64]0; $cpuSeconds = 0.0
    while (-not $proc.HasExited) {
        $proc.Refresh()
        $peakWorkingSet = [Math]::Max($peakWorkingSet,[int64]$proc.PeakWorkingSet64)
        $cpuSeconds = $proc.TotalProcessorTime.TotalSeconds
        if ($proc.WaitForExit(5000)) { break }
    }
    $proc.Refresh()
    $peakWorkingSet = [Math]::Max($peakWorkingSet,[int64]$proc.PeakWorkingSet64)
    $cpuSeconds = $proc.TotalProcessorTime.TotalSeconds
    $code = [int]$proc.ExitCode
    $processSnapshot=[ordered]@{
        pid=$matlabPid; command_line=$(if($snapshot){$snapshot.CommandLine}else{''}); creation_date=$(if($snapshot){$snapshot.CreationDate}else{''})
        cpu_processors=$cpuInfo; logical_cpu_count=$computerInfo.NumberOfLogicalProcessors
        physical_memory_bytes=$computerInfo.TotalPhysicalMemory; matlab_cpu_time_s=$cpuSeconds
        peak_working_set_bytes=$peakWorkingSet; monitor_poll_ms=5000
    }
    Write-ExitReceipt $ReceiptPath $Stage $Method $code $StdoutPath $StderrPath $started $processSnapshot
    if ($code -ne 0) { throw "MATLAB naturally exited with OS code $code. Preserve outputs and stop; no retry." }
}
function Get-UsedBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [int64]0 }
    $sum=[int64]0
    Get-ChildItem -LiteralPath $Path -Recurse -File | ForEach-Object { $sum += [int64]$_.Length }
    return $sum
}

# Static source and deadline checks happen before mode-specific authorization and before MATLAB.
$contract = Read-Json $contractPath
$manifest = Read-Json $manifestPath
if ($contract.schema -ne 'TEST48_RUN_CONTRACT_V1' -or $contract.state -ne 'CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES') { throw 'TEST48 contract is not the code-only version.' }
Assert-FrozenInputs $contract $manifest
Assert-DeadlineParser

switch ($Mode) {
    'DEV_INPUT_EQUIVALENCE_ONLY' {
        $releasePath=Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_PARENT_RELEASE_v1.json'
        $release=Read-Json $releasePath
        Assert-ParentRelease $release 'TEST48_DEV_INPUT_EQUIVALENCE_RELEASE_V1' 'APPROVED_DEV_INPUT_EQUIVALENCE_ONLY' $false $false $false
        Require-Value $release 'dev_input_equivalence_authorized' $true
        $receipt=Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_MATLAB_OS_EXIT_v1.json'
        $stdout=Join-Path $reportDir 'logs/DEV_INPUT_EQUIVALENCE.stdout.log'; $stderr=Join-Path $reportDir 'logs/DEV_INPUT_EQUIVALENCE.stderr.log'
        Invoke-MatlabStage $Mode '' $receipt $stdout $stderr
        $result=Read-Json (Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_RESULT_v1.json')
        if ($result.status -ne 'PASS_DEV_ALL72_GENERATOR_EQUIVALENCE' -or $result.TEST_accessed -or $result.plant_calls -ne 0) { throw 'DEV no-Plant equivalence result is incomplete or invalid.' }
    }
    'TEST_INPUT_FREEZE_ONLY' {
        $devExit=Read-Json (Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_MATLAB_OS_EXIT_v1.json')
        $devResultPath=Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_RESULT_v1.json'
        $devResult=Read-Json $devResultPath
        if ($devExit.matlab_os_exit_code -ne 0 -or $devResult.status -ne 'PASS_DEV_ALL72_GENERATOR_EQUIVALENCE' -or $devResult.TEST_accessed -or $devResult.plant_calls -ne 0) { throw 'A natural-OS0 DEV equivalence pass is required before TEST input freeze.' }
        $releasePath=Join-Path $reportDir 'TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json'
        $release=Read-Json $releasePath
        Assert-ParentRelease $release 'TEST48_INPUT_FREEZE_RELEASE_V1' 'APPROVED_TEST_INPUT_FREEZE_ONLY' $false $true $true
        Require-Value $release 'dev_result_sha256' (Get-Sha256 $devResultPath)
        Require-Value $release 'dev_os_exit_sha256' (Get-Sha256 (Join-Path $reportDir 'DEV_INPUT_EQUIVALENCE_MATLAB_OS_EXIT_v1.json'))
        Require-Value $release 'scene_specs_sha256' (Get-Sha256 (Join-Path $repoRoot 'configs/scene_specs.csv'))
        $inputDir=Join-Path $taskDir 'input'; foreach($p in @($inputDir,(Join-Path $inputDir 'TEST_SCENES_SHARED_v1.mat'),(Join-Path $inputDir 'TEST_METHOD_CFG_OPTS_v1.mat'),(Join-Path $inputDir 'TEST_INPUT_INDEX_v1.json'),(Join-Path $reportDir 'TEST_INPUT_FREEZE_RESULT_v1.json'),(Join-Path $reportDir 'TEST_INPUT_FREEZE_FAILURE_v1.json'),(Join-Path $reportDir 'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json'))){if(Test-Path -LiteralPath $p){throw "No-retry guard: TEST freeze output already exists: $p"}}
        $receipt=Join-Path $reportDir 'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json'
        $stdout=Join-Path $reportDir 'logs/TEST_INPUT_FREEZE.stdout.log'; $stderr=Join-Path $reportDir 'logs/TEST_INPUT_FREEZE.stderr.log'
        Invoke-MatlabStage $Mode '' $receipt $stdout $stderr
        $index=Read-Json (Join-Path $inputDir 'TEST_INPUT_INDEX_v1.json')
        $result=Read-Json (Join-Path $reportDir 'TEST_INPUT_FREEZE_RESULT_v1.json')
        if ($index.scene_ids.Count -ne 48 -or $result.status -ne 'PREPARED_TEST48_INPUTS_NO_PLANT' -or -not $result.TEST_accessed -or $result.plant_calls -ne 0) { throw 'TEST input freeze did not produce exactly 48 TEST inputs without Plant.' }
    }
    'LOCKED_TEST48_PARENT_APPROVED' {
        $freezeExit=Read-Json (Join-Path $reportDir 'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json')
        $indexPath=Join-Path $taskDir 'input/TEST_INPUT_INDEX_v1.json'
        $sceneMatPath=Join-Path $taskDir 'input/TEST_SCENES_SHARED_v1.mat'
        $cfgOptsPath=Join-Path $taskDir 'input/TEST_METHOD_CFG_OPTS_v1.mat'
        $freezeResultPath=Join-Path $reportDir 'TEST_INPUT_FREEZE_RESULT_v1.json'
        if ($freezeExit.matlab_os_exit_code -ne 0 -or (Read-Json $freezeResultPath).status -ne 'PREPARED_TEST48_INPUTS_NO_PLANT') { throw 'TEST input freeze must have naturally exited OS0.' }
        $runReleasePath=Join-Path $reportDir 'LOCKED_TEST48_PARENT_RELEASE_v1.json'
        $release=Read-Json $runReleasePath
        Assert-ParentRelease $release 'TEST48_LOCKED_RUN_RELEASE_V1' 'APPROVED_LOCKED_TEST48_PARENT_V1' $true $false $true
        Require-Value $release 'max_plant_calls' 288
        Require-Value $release 'scene_count' 48
        Require-Value $release 'input_index_sha256' (Get-Sha256 $indexPath)
        Require-Value $release 'shared_scenes_mat_sha256' (Get-Sha256 $sceneMatPath)
        Require-Value $release 'method_cfg_opts_sha256' (Get-Sha256 $cfgOptsPath)
        Require-Value $release 'scene_set_sha256' (Read-Json $indexPath).scene_set_sha256
        Require-Value $release 'freeze_result_sha256' (Get-Sha256 $freezeResultPath)
        Require-Value $release 'freeze_os_exit_sha256' (Get-Sha256 (Join-Path $reportDir 'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json'))
        $methods=@($contract.method_order | ForEach-Object { $_.id })
        if ((Compare-Object $methods @($release.method_ids) -SyncWindow 0)) { throw 'Plant release method order differs from the fixed six.' }
        $index=Read-Json $indexPath
        if ($index.scene_ids.Count -ne 48 -or $index.TEST_accessed -ne $true -or $index.scene_specs_sha256 -ne (Get-Sha256 (Join-Path $repoRoot 'configs/scene_specs.csv'))) { throw 'Frozen TEST input index does not match the sealed design metadata.' }
        $allMethods=@($contract.method_order)
        foreach($m in $allMethods){
            foreach($sceneId in $index.scene_ids){
                $attempt=Join-Path (Join-Path (Join-Path (Join-Path $taskDir 'runs') $m.alias) $sceneId) 'attempt_01'
                foreach($name in @('attempt_started.marker','first_plant_step.marker','run_start.mat','raw_run.mat','run_status.json','FAILURE_NO_RETRY_v1.json')){
                    Assert-ShortPath (Join-Path $attempt $name)
                }
            }
        }
        foreach($m in $allMethods){
            $methodRoot=Join-Path (Join-Path $taskDir 'runs') $m.alias
            $exitPath=Join-Path $reportDir ($m.alias+'_MATLAB_OS_EXIT_v1.json')
            $stdout=Join-Path $reportDir ('logs/'+$m.alias+'.stdout.log'); $stderr=Join-Path $reportDir ('logs/'+$m.alias+'.stderr.log')
            foreach($p in @($methodRoot,$exitPath,$stdout,$stderr)){if(Test-Path -LiteralPath $p){throw "No-retry guard: method output exists: $p"};Assert-ShortPath $p}
        }
        Assert-NoMatlab
        $hardDeadline=Convert-DeadlineUtc $contract.limits.hard_deadline_utc
        for($i=0;$i -lt $allMethods.Count;$i++){
            $m=$allMethods[$i]; $methodsRemaining=$allMethods.Count-$i; $remaining=$methodsRemaining*48
            $reserve=[int64]$remaining*[int64]$contract.limits.per_scene_output_reserve_bytes
            $drive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskDir))
            if ($drive.AvailableFreeSpace-$reserve -lt [int64]$contract.limits.minimum_free_bytes_after_reserve) { throw 'Reserve-adjusted free-space floor failed; do not delete data.' }
            $observedBase=[int64]$contract.limits.prior_created_bytes
            $currentArtifacts=(Get-UsedBytes $taskDir)+(Get-UsedBytes $reportDir)
            if ($observedBase+$currentArtifacts+$reserve -gt [int64]$contract.limits.max_output_bytes) { throw 'Cycle-wide creation baseline plus TEST output/reserve exceeds the cap.' }
            $requiredSeconds=$remaining*[int64]$contract.limits.per_scene_seconds_guard+$methodsRemaining*[int64]$contract.limits.process_exit_buffer_seconds
            if ($hardDeadline -lt [DateTime]::UtcNow.AddSeconds($requiredSeconds)) { throw 'Conservative deadline budget failed; do not launch this method.' }
            Invoke-MatlabStage $Mode $m.id (Join-Path $reportDir ($m.alias+'_MATLAB_OS_EXIT_v1.json')) `
                (Join-Path $reportDir ('logs/'+$m.alias+'.stdout.log')) (Join-Path $reportDir ('logs/'+$m.alias+'.stderr.log'))
            $bodyPath=Join-Path (Join-Path $taskDir 'runs') (Join-Path $m.alias 'METHOD_BODY_COMPLETE_v1.json')
            $body=Read-Json $bodyPath
            if ($body.status -ne 'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT' -or $body.method_id -cne $m.id -or $body.completed_scenes -ne 48 -or -not $body.TEST_accessed) { throw "Method process returned OS0 without a complete 48-scene body: $($m.id)" }
        }
    }
}
Write-Output "CODE_PATH_FINISHED mode=$Mode"
