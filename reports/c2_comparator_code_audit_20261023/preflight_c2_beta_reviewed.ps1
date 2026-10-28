param(
    [Parameter(Mandatory=$true)][ValidateSet('PROBE','CONTINUE')][string]$Mode,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$Mode = $Mode.ToUpperInvariant()
$Here = $PSScriptRoot
$Root = [System.IO.Path]::GetFullPath((Join-Path $Here '..\..'))
$C2 = Join-Path $Root 'experiments\position_beta_clock_c2_20261023'
$Reports = Join-Path $C2 'reports'
$LockPath = Join-Path $C2 'C2_SOURCE_LOCK.json'
$ContractPath = Join-Path $C2 'C2_RUN_CONTRACT.json'
$ReleasePath = Join-Path $C2 'C2_RELEASE_v1.json'
$ApprovalPath = Join-Path $Reports "C2_${Mode}_APPROVAL.json"
$PreflightPath = Join-Path $Reports ("preflight_c2_{0}.json" -f $Mode.ToLowerInvariant())

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Require-File([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing required file: $Path" }
}
function Get-TreeBytes([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Container)) { return [int64]0 }
    $Files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
    if ($Files.Count -eq 0) { return [int64]0 }
    return [int64](($Files | Measure-Object -Property Length -Sum).Sum)
}
function Get-CpuSecondsByPid {
    $Map = @{}
    foreach ($Process in Get-Process -ErrorAction SilentlyContinue) {
        try { $Map[[int]$Process.Id] = [double]$Process.CPU } catch { }
    }
    return $Map
}

Require-File $LockPath
Require-File $ContractPath
Require-File $ReleasePath
Require-File $ApprovalPath
$Lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$Contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
$Release = Get-Content -LiteralPath $ReleasePath -Raw | ConvertFrom-Json
$Approval = Get-Content -LiteralPath $ApprovalPath -Raw | ConvertFrom-Json
$LockSha = Get-Sha256 $LockPath
$ContractSha = Get-Sha256 $ContractPath
$ReleaseSha = Get-Sha256 $ReleasePath
$ApprovalSha = Get-Sha256 $ApprovalPath

if ($Lock.schema -ne 'C2_BETA_CLOCK_ALIGNMENT_SOURCE_LOCK_V1' -or
    $Lock.state -ne 'PREPARED_NO_PLANT' -or
    [System.IO.Path]::GetFullPath($Lock.repo_root) -ne $Root) { throw 'C2 source lock/root/state mismatch.' }
if ($Contract.schema -ne 'C2_BETA_CLOCK_RUN_CONTRACT_V1' -or
    $Contract.limits.max_new_sorties -ne 12 -or
    $Contract.limits.output_cap_bytes -ne 1073741824 -or
    $Contract.limits.per_attempt_reserve_bytes -ne 80000000 -or
    $Contract.limits.per_attempt_hard_cap_bytes -ne 80000000 -or
    $Contract.limits.training -or $Contract.limits.optimizer -or $Contract.limits.gpu_jobs -or $Contract.limits.TEST -or $Contract.limits.full72) {
    throw 'C2 contract limits/scope mismatch.'
}
$RequiredFields = @(
    'status','mode','created_utc','source_lock_sha256','release_sha256','approval_sha256',
    'user_budget_authorization_sha256','fixed_step_screen_allowed','matlab_process_count',
    'other_heavy_job_count','gpu_compute_rows','gpu_compute_counter_active_rows','free_bytes_before',
    'minimum_free_bytes','existing_c2_bytes','projected_reserved_bytes','max_output_bytes',
    'remaining_attempt_count','timing_isolated','formal_timing_qualified','plant_started',
    'optimizer_steps','gpu_jobs','TEST_accessed'
)
if (@($Contract.preflight.required_fields | Where-Object { $_ -notin $RequiredFields }).Count -gt 0 -or
    @($RequiredFields | Where-Object { $_ -notin $Contract.preflight.required_fields }).Count -gt 0) {
    throw 'Preflight required fields differ from the frozen contract.'
}
if ($Contract.preflight.freshness_seconds_max -ne 300 -or $Contract.preflight.formal_timing_qualified -ne $false) {
    throw 'C2 preflight freshness/formal timing contract mismatch.'
}
if ($Release.schema -ne 'C2_BETA_CLOCK_EXECUTION_RELEASE_V1' -or
    $Release.state -ne 'PREPARED_FOR_SOURCE_REVIEW_NO_PLANT' -or
    $Release.candidate_condition_id -ne $Contract.candidate_condition_id -or
    $Release.source_lock_sha256.ToLowerInvariant() -ne $LockSha -or
    $Release.run_contract_sha256.ToLowerInvariant() -ne $ContractSha) { throw 'C2 release binding mismatch.' }
$ScriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
if ([System.IO.Path]::GetFullPath($Release.preflight_path) -ne $ScriptPath -or
    $Release.preflight_sha256.ToLowerInvariant() -ne (Get-Sha256 $ScriptPath)) { throw 'C2 release does not pin this exact preflight script.' }
if ([System.IO.Path]::GetFullPath($Release.source_lock_path) -ne [System.IO.Path]::GetFullPath($LockPath) -or
    [System.IO.Path]::GetFullPath($Release.run_contract_path) -ne [System.IO.Path]::GetFullPath($ContractPath)) {
    throw 'C2 release source/contract path mismatch.'
}

Require-File $Release.user_budget_authorization_path
$BudgetSha = Get-Sha256 $Release.user_budget_authorization_path
if ($BudgetSha -ne $Release.user_budget_authorization_sha256.ToLowerInvariant()) { throw 'User budget authorization SHA mismatch.' }
$Budget = Get-Content -LiteralPath $Release.user_budget_authorization_path -Raw | ConvertFrom-Json
if ($Budget.status -ne 'USER_AUTHORIZED_ADDITIONAL_MAX_12_SORTIES' -or
    $Budget.max_new_sorties -ne 12 -or $Budget.probe_sorties -ne 1 -or
    $Budget.remaining_sorties_after_parent_probe_gate -ne 11 -or
    !$Budget.reuse_B_and_original_ON1 -or $Budget.new_training -ne 0 -or
    $Budget.new_scalar_fits -ne 0 -or $Budget.TEST_authorized -or $Budget.full72_authorized -or
    $Budget.new_output_cap_bytes -ne 1073741824) { throw 'User budget authorization content mismatch.' }

Require-File $Lock.c1_source_lock.path
if ((Get-Sha256 $Lock.c1_source_lock.path) -ne $Lock.c1_source_lock.sha256.ToLowerInvariant() -or
    [System.IO.Path]::GetFullPath($Release.c1_source_lock_path) -ne [System.IO.Path]::GetFullPath($Lock.c1_source_lock.path) -or
    $Release.c1_source_lock_sha256.ToLowerInvariant() -ne $Lock.c1_source_lock.sha256.ToLowerInvariant()) {
    throw 'C1 scene identity source lock mismatch.'
}
$C1Lock = Get-Content -LiteralPath $Lock.c1_source_lock.path -Raw | ConvertFrom-Json
$SceneIds = @($C1Lock.shared_scenes | ForEach-Object { [string]$_.scene_id })
$InvalidSceneIds = @($SceneIds | Where-Object { [string]::IsNullOrWhiteSpace($_) })
if ($SceneIds.Count -ne 12 -or $InvalidSceneIds.Count -gt 0) { throw 'Expected twelve fixed C1 scene IDs.' }
$ExpectedRuns = if ($Mode -eq 'PROBE') { 1 } else { 11 }
$ExpectedIds = if ($Mode -eq 'PROBE') { @($SceneIds[0]) } else { @($SceneIds[1..11]) }
$ApprovedIds = @($Approval.scene_ids | ForEach-Object { [string]$_ })
if ($Approval.status -ne "APPROVED_${Mode}" -or $Approval.mode -ne $Mode -or
    $Approval.candidate_condition_id -ne $Contract.candidate_condition_id -or
    $Approval.source_lock_sha256.ToLowerInvariant() -ne $LockSha -or
    $Approval.release_sha256.ToLowerInvariant() -ne $ReleaseSha -or
    $Approval.user_budget_authorization_sha256.ToLowerInvariant() -ne $BudgetSha -or
    $Approval.expected_new_runs -ne $ExpectedRuns -or
    ($ApprovedIds -join '|') -ne ($ExpectedIds -join '|')) { throw 'C2 approval does not bind this exact authorized stage.' }

$Runs = Join-Path $C2 'runs_c2'
$Markers = @()
$AttemptDirs = @()
if (Test-Path -LiteralPath $Runs -PathType Container) {
    $Markers = @(Get-ChildItem -LiteralPath $Runs -Filter 'attempt_started.marker' -File -Recurse -Force)
    $AttemptDirs = @(Get-ChildItem -LiteralPath $Runs -Directory -Recurse -Force | Where-Object { $_.Name -like 'attempt_*' })
}
$StartedCount = $Markers.Count
$RemainingAttempts = 12 - $StartedCount
if ($RemainingAttempts -ne $(if ($Mode -eq 'PROBE') { 12 } else { 11 })) {
    throw "Started-attempt ledger conflicts with $Mode scope: markers=$StartedCount."
}
$ProbeSummaryPath = Join-Path $Reports 'C2_PROBE_SUMMARY.json'
if ($Mode -eq 'PROBE') {
    if (($AttemptDirs.Count -ne 0) -or (Test-Path -LiteralPath $ProbeSummaryPath)) { throw 'PROBE refuses any prior/partial C2 attempt or summary.' }
} else {
    if ($Markers.Count -ne 1 -or $AttemptDirs.Count -ne 1 -or
        [System.IO.Path]::GetFullPath($Markers[0].FullName) -ne [System.IO.Path]::GetFullPath((Join-Path $Runs "$($SceneIds[0])\C2_ON1_BETA_ALIGNED\attempt_01\attempt_started.marker"))) {
        throw 'CONTINUE requires exactly the first probe attempt and no retry/extra attempt.'
    }
    Require-File $ProbeSummaryPath
    $ProbeSha = Get-Sha256 $ProbeSummaryPath
    $Probe = Get-Content -LiteralPath $ProbeSummaryPath -Raw | ConvertFrom-Json
    if ($ProbeSha -ne $Approval.probe_summary_sha256.ToLowerInvariant() -or
        $Probe.status -ne 'PROBE_COMPLETE' -or $Probe.mode -ne 'PROBE' -or
        $Probe.candidate_condition_id -ne $Contract.candidate_condition_id -or
        $Probe.completed_runs -ne 1 -or $Probe.expected_runs -ne 1 -or
        @($Probe.run_rows).Count -ne 1 -or @($Probe.scene_ids).Count -ne 1 -or
        $Probe.scene_ids[0] -ne $SceneIds[0] -or $Probe.run_rows[0].scene_id -ne $SceneIds[0] -or
        $Probe.source_lock_sha256.ToLowerInvariant() -ne $LockSha -or
        $Probe.release_sha256.ToLowerInvariant() -ne $ReleaseSha -or
        $Probe.user_budget_authorization_sha256.ToLowerInvariant() -ne $BudgetSha) {
        throw 'CONTINUE probe summary identity/completion gate failed.'
    }
}

$Deadline = [DateTime]::Parse('2026-10-24T17:01:00Z').ToUniversalTime()
$Now = [DateTime]::UtcNow
if ($Now -ge $Deadline) { throw 'Fixed C2 deadline has passed.' }
$Matlab = @(Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe' OR Name='MATLABWindow.exe'" -ErrorAction Stop)
if ($Matlab.Count -gt 0) { throw "MATLAB process(es) already exist; no process will be stopped. Count=$($Matlab.Count)" }

$Nvidia = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
$NvidiaPath = if ($Nvidia) { $Nvidia.Source } else { 'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe' }
Require-File $NvidiaPath
$GpuLines = @(& $NvidiaPath --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>&1)
if ($LASTEXITCODE -ne 0) { throw "nvidia-smi compute-app query failed: $($GpuLines -join ' ')" }
$GpuRows = @()
$ActiveComputeRows = 0
$BlockingPids = [System.Collections.Generic.HashSet[int]]::new()
foreach ($LineObject in $GpuLines) {
    $Line = [string]$LineObject
    if ($Line -match '(?i)no running processes found' -or [string]::IsNullOrWhiteSpace($Line)) { continue }
    $Parts = $Line.Split(',')
    if ($Parts.Count -lt 3) { throw "Unparseable nvidia-smi compute row: $Line" }
    $PidText = $Parts[0].Trim(); $Name = $Parts[1].Trim(); $MemoryText = $Parts[2].Trim()
    if ($PidText -match '^\d+$' -and $MemoryText -match '^\d+$') {
        $TaskPid = [int]$PidText
        $GpuRows += [pscustomobject]@{ source='nvidia-smi'; pid=$TaskPid; name=$Name; used_memory_mib=[int]$MemoryText; classification='CUDA_COMPUTE_PROCESS'; active=$true }
        $ActiveComputeRows++
        [void]$BlockingPids.Add($TaskPid)
    } elseif (($PidText -match '^\d+$' -and $MemoryText -match '(?i)^\[?N/?A\]?$') -or
              $PidText -match '(?i)^\[?N/?A\]?$') {
        $GpuRows += [pscustomobject]@{ source='nvidia-smi'; pid=$(if ($PidText -match '^\d+$') { [int]$PidText } else { $null }); name=$Name; used_memory_mib=$null; classification='WDDM_NA_NOT_COMPUTE_EVIDENCE'; active=$false; raw_line=$Line }
    } else { throw "Unparseable nvidia-smi compute row: $Line" }
}

$EngineClass = 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine'
try {
    $EngineBefore = @(Get-CimInstance -ClassName $EngineClass -ErrorAction Stop | Where-Object { $_.Name -match 'engtype_Compute' })
    Start-Sleep -Milliseconds 1000
    $EngineAfter = @(Get-CimInstance -ClassName $EngineClass -ErrorAction Stop | Where-Object { $_.Name -match 'engtype_Compute' })
} catch { throw "Cannot inspect WDDM GPU compute engines; preflight fails closed: $($_.Exception.Message)" }
$EngineRows = @()
$EngineNames = @(@($EngineBefore.Name) + @($EngineAfter.Name) | Sort-Object -Unique)
foreach ($EngineName in $EngineNames) {
    $Before = $EngineBefore | Where-Object { $_.Name -eq $EngineName } | Select-Object -First 1
    $After = $EngineAfter | Where-Object { $_.Name -eq $EngineName } | Select-Object -First 1
    $BeforeUtil = if ($Before) { [double]$Before.UtilizationPercentage } else { 0.0 }
    $AfterUtil = if ($After) { [double]$After.UtilizationPercentage } else { 0.0 }
    $EnginePid = $null
    if ($EngineName -match 'pid_(\d+)') { $EnginePid = [int]$Matches[1] }
    $Active = ($BeforeUtil -gt 0 -or $AfterUtil -gt 0)
    $EngineRows += [pscustomobject]@{ name=$EngineName; pid=$EnginePid; before_utilization_percent=$BeforeUtil; after_utilization_percent=$AfterUtil; active=$Active; classification=$(if ($Active) { 'ACTIVE_WDDM_COMPUTE_ENGINE' } else { 'IDLE_WDDM_COMPUTE_ENGINE' }) }
    if ($Active) {
        $ActiveComputeRows++
        if ($null -ne $EnginePid) { [void]$BlockingPids.Add($EnginePid) }
    }
}

$Cpu0 = Get-CpuSecondsByPid
$SampleStart = [DateTime]::UtcNow
Start-Sleep -Milliseconds 1000
$SampleSeconds = ([DateTime]::UtcNow - $SampleStart).TotalSeconds
$Cpu1 = Get-CpuSecondsByPid
$Processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
$AllowedDesktop = @()
$Heavy = @()
foreach ($Process in $Processes) {
    $TaskPid = [int]$Process.ProcessId
    if ($TaskPid -eq 0 -or $TaskPid -eq $PID) { continue }
    $Name = [string]$Process.Name
    $CpuRate = $null
    if ($Cpu0.ContainsKey($TaskPid) -and $Cpu1.ContainsKey($TaskPid)) {
        $CpuRate = [math]::Max(0.0, $Cpu1[$TaskPid] - $Cpu0[$TaskPid]) / [math]::Max(0.1, $SampleSeconds)
    }
    if ($Name -in @('ChatGPT.exe','VALORANT-Win64-Shipping.exe')) {
        $AllowedDesktop += [pscustomobject]@{ pid=$TaskPid; name=$Name; cpu_seconds_per_wall_second=$CpuRate; classification='ALLOWED_NON_RESEARCH_DESKTOP_LOAD' }
        continue
    }
    $IsPython = $Name -match '^(pythonw?|jupyter(?:-lab)?)\.exe$'
    $CommandLooksTraining = ([string]$Process.CommandLine) -match '(?i)train|fit|torch|cuda|optimizer|pytorch'
    $BlockCpu = ($null -ne $CpuRate -and $CpuRate -ge 0.8) -or
        ($IsPython -and $null -ne $CpuRate -and (($CpuRate -ge 0.15) -or ($CommandLooksTraining -and $CpuRate -ge 0.05)))
    if ($BlockCpu) {
        $Heavy += [pscustomobject]@{ pid=$TaskPid; name=$Name; cpu_seconds_per_wall_second=$CpuRate; classification=$(if ($IsPython) { 'PYTHON_HEAVY' } else { 'OTHER_CPU_HEAVY' }) }
        [void]$BlockingPids.Add($TaskPid)
    }
}
foreach ($TaskPid in $BlockingPids) {
    if (!(@($Heavy | Where-Object { $_.pid -eq $TaskPid }).Count)) {
        $Proc = $Processes | Where-Object { [int]$_.ProcessId -eq $TaskPid } | Select-Object -First 1
        $Heavy += [pscustomobject]@{ pid=$TaskPid; name=$(if ($Proc) { [string]$Proc.Name } else { '<unresolved>' }); cpu_seconds_per_wall_second=$null; classification='ACTIVE_GPU_COMPUTE' }
    }
}
if ($ActiveComputeRows -gt 0 -or $Heavy.Count -gt 0) { throw "Active GPU compute or other heavy job detected; no process was stopped. GPU rows=$ActiveComputeRows heavy jobs=$($Heavy.Count)" }

$Drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Root))
$FreeBytes = [int64]$Drive.AvailableFreeSpace
$MinFreeBytes = [int64]30000000000
$MaxOutputBytes = [int64]$Budget.new_output_cap_bytes
$PerAttemptReserve = [int64]80000000
$ProjectedReserve = [int64]($RemainingAttempts * $PerAttemptReserve)
$ExistingBytes = Get-TreeBytes $C2
if ($ExistingBytes + $ProjectedReserve -gt $MaxOutputBytes) { throw "C2 output cap failed: existing=$ExistingBytes reserve=$ProjectedReserve cap=$MaxOutputBytes" }
if ($FreeBytes - $ProjectedReserve -lt $MinFreeBytes) { throw "30-GB free-space floor failed: free=$FreeBytes reserve=$ProjectedReserve floor=$MinFreeBytes" }

$Report = [ordered]@{
    status = 'PASS'
    mode = $Mode
    created_utc = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", [Globalization.CultureInfo]::InvariantCulture)
    source_lock_sha256 = $LockSha
    release_sha256 = $ReleaseSha
    approval_sha256 = $ApprovalSha
    user_budget_authorization_sha256 = $BudgetSha
    fixed_step_screen_allowed = $true
    matlab_process_count = 0
    other_heavy_job_count = 0
    gpu_compute_rows = @($GpuRows)
    gpu_compute_counter_active_rows = $ActiveComputeRows
    gpu_engine_rows = @($EngineRows)
    gpu_compute_counter_total_rows = $EngineRows.Count
    allowed_non_research_desktop_processes = @($AllowedDesktop)
    free_bytes_before = $FreeBytes
    minimum_free_bytes = $MinFreeBytes
    existing_c2_bytes = $ExistingBytes
    projected_reserved_bytes = $ProjectedReserve
    max_output_bytes = $MaxOutputBytes
    remaining_attempt_count = $RemainingAttempts
    timing_isolated = $false
    formal_timing_qualified = $false
    plant_started = $false
    optimizer_steps = 0
    gpu_jobs = 0
    TEST_accessed = $false
    deadline_utc = $Deadline.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    resource_note = 'ChatGPT/VALORANT desktop load is permitted but timing remains non-isolated; WDDM N/A rows are recorded, not counted as compute.'
}
if ($DryRun) {
    $Report.status = 'PASS_DRY_RUN'
    $Report | ConvertTo-Json -Depth 8
    return
}
if (Test-Path -LiteralPath $PreflightPath) { throw "Refusing to overwrite existing formal preflight: $PreflightPath" }
if (!(Test-Path -LiteralPath $Reports -PathType Container)) { New-Item -ItemType Directory -Path $Reports | Out-Null }
$Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $PreflightPath -Encoding utf8
Write-Output "C2_PREFLIGHT PASS mode=$Mode free_bytes=$FreeBytes reserve=$ProjectedReserve attempts_remaining=$RemainingAttempts output=$PreflightPath"

