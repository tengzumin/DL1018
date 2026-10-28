param([Parameter(Mandatory=$true)][ValidateSet('PROBE','CONTINUE')][string]$Mode,[switch]$DryRun)
$ErrorActionPreference='Stop'
$Here=$PSScriptRoot
$Root=[System.IO.Path]::GetFullPath((Join-Path $Here '..\..'))
$LockPath=Join-Path $Here 'C1_SOURCE_LOCK_v2.json'
$ReleasePath=Join-Path $Here 'C1_RELEASE_v7.json'
$Lock=Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
$Release=Get-Content -LiteralPath $ReleasePath -Raw | ConvertFrom-Json
if($Lock.schema -ne 'C1_PRIOR_SCALE_SCREEN_V1' -or [System.IO.Path]::GetFullPath($Lock.repo_root) -ne $Root){throw 'C1 lock/root mismatch.'}
function Get-Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Check-File([string]$Path,[string]$Expected){if(!(Test-Path -LiteralPath $Path -PathType Leaf)){throw "Missing locked input: $Path"};$Actual=Get-Sha $Path;if($Actual -ne $Expected.ToLowerInvariant()){throw "SHA mismatch: $Path"}}
$LockSha=Get-Sha $LockPath
$ReleaseSha=Get-Sha $ReleasePath
if($LockSha -ne $Release.source_lock_sha256 -or
   (Get-Sha (Join-Path $Here 'run_c1_screen.m')) -ne $Release.runner_sha256 -or
   (Get-Sha (Join-Path $Here 'build_c1_options.m')) -ne $Release.builder_sha256 -or
   (Get-Sha (Join-Path $Here 'offline_options_smoke_c1.m')) -ne $Release.smoke_sha256 -or
   (Get-Sha (Join-Path $Here 'preflight_c1.ps1')) -ne $Release.preflight_sha256){throw 'C1 implementation SHA mismatch.'}
Check-File $Lock.r2_lock.path $Lock.r2_lock.sha256
Check-File $Lock.calibration.result_path $Lock.calibration.result_sha256
Check-File $Lock.calibration.fit_script_path $Lock.calibration.fit_script_sha256
Check-File $Lock.taskbook.path $Lock.taskbook.sha256
Check-File $Lock.resource_timing_clarification.path $Lock.resource_timing_clarification.sha256
$R2=Get-Content -LiteralPath $Lock.r2_lock.path -Raw | ConvertFrom-Json
foreach($Item in $R2.runtimeFiles){Check-File $Item.path $Item.sha256}
foreach($Item in $R2.plantFiles){Check-File $Item.path $Item.sha256}
foreach($Spec in @(@($R2.model.mat_path,$R2.model.mat_sha256),@($R2.model_binding.path,$R2.model_binding.sha256),
    @($R2.normalizer.npz_path,$R2.normalizer.npz_file_sha256),@($R2.normalizer.train_only_report_path,$R2.normalizer.train_only_report_sha256),
    @($R2.scene_list.path,$R2.scene_list.sha256),@($R2.scene_payload_identity.path,$R2.scene_payload_identity.sha256),
    @($R2.reuse_manifest.path,$R2.reuse_manifest.sha256))){Check-File $Spec[0] $Spec[1]}
$Now=[DateTime]::UtcNow
$Deadline=[DateTime]::Parse('2026-10-24T17:01:00Z').ToUniversalTime()
if($Now -ge $Deadline){throw 'C1 hard deadline has passed.'}
$MATLAB=@(Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe' OR Name='MATLABWindow.exe'" -ErrorAction Stop)
if($MATLAB.Count -ne 0){throw "MATLAB process(es) already exist; no process will be stopped. Count=$($MATLAB.Count)"}
$Nvidia=Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
if(!$Nvidia){$NvidiaPath='C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'}else{$NvidiaPath=$Nvidia.Source}
if(!(Test-Path -LiteralPath $NvidiaPath -PathType Leaf)){throw 'Cannot inspect GPU compute PIDs; preflight fails closed.'}
$GpuAppLines=@(& $NvidiaPath --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>&1)
if($LASTEXITCODE -ne 0){throw "nvidia-smi compute-app query failed: $($GpuAppLines -join ' ')"}
$GpuBeforeLines=@(& $NvidiaPath --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>&1)
if($LASTEXITCODE -ne 0){throw "nvidia-smi GPU-utilization query failed: $($GpuBeforeLines -join ' ')"}
$GpuBefore=@(); foreach($Line in $GpuBeforeLines){if([string]$Line -match '^\s*(\d+)\s*,\s*(\d+)'){ $GpuBefore += [pscustomobject]@{utilization_percent=[int]$Matches[1];memory_used_mib=[int]$Matches[2]} }}
if($GpuBefore.Count -eq 0){throw 'GPU utilization output was unreadable.'}
$GpuEngineClass='Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine'
try{$GpuEngineBeforeAll=@(Get-CimInstance -ClassName $GpuEngineClass -ErrorAction Stop);$GpuEngineBefore=@($GpuEngineBeforeAll|Where-Object {$_.Name -match 'engtype_Compute'}|Select-Object Name,UtilizationPercentage)}
catch{throw "Cannot inspect WDDM GPU compute engines; preflight fails closed: $($_.Exception.Message)"}
$Processes=@(Get-CimInstance Win32_Process -ErrorAction Stop)
$PreflightProcessId=[int][System.Diagnostics.Process]::GetCurrentProcess().Id
$Cpu0=@{}; foreach($Proc in Get-Process -ErrorAction SilentlyContinue){try{$Cpu0[[int]$Proc.Id]=[double]$Proc.CPU}catch{}}
$SampleStarted=[DateTime]::UtcNow
Start-Sleep -Seconds 1
$SampleSeconds=([DateTime]::UtcNow-$SampleStarted).TotalSeconds
$Cpu1=@{}; foreach($Proc in Get-Process -ErrorAction SilentlyContinue){try{$Cpu1[[int]$Proc.Id]=[double]$Proc.CPU}catch{}}
$GpuEngineAfterAll=@(Get-CimInstance -ClassName $GpuEngineClass -ErrorAction Stop);$GpuEngineAfter=@($GpuEngineAfterAll|Where-Object {$_.Name -match 'engtype_Compute'}|Select-Object Name,UtilizationPercentage)
$ProcessRows=@(); $HeavyRows=@(); $NonResearchDesktopRows=@()
foreach($Proc in $Processes){
    $TaskProcessId=[int]$Proc.ProcessId; if($TaskProcessId -eq 0 -or $TaskProcessId -eq $PreflightProcessId){continue}; $Name=[string]$Proc.Name
    if($Cpu0.ContainsKey($TaskProcessId) -and $Cpu1.ContainsKey($TaskProcessId)){$CpuRate=([math]::Max(0,$Cpu1[$TaskProcessId]-$Cpu0[$TaskProcessId]))/[math]::Max(.1,$SampleSeconds)}else{$CpuRate=$null}
    $Cmd=[string]$Proc.CommandLine
    $Cmd=$Cmd -replace '(?i)(--?(?:token|password|secret|api[_-]?key)(?:=|\s+))\S+','$1<redacted>'
    $IsPython=$Name -match '^(pythonw?|jupyter(?:-lab)?)\.exe$'
    $IsCad=$Name -match '^(sldworks|solidworks)(?:\.exe)?$'
    $IsKnownDesktop=$Name -in @('ChatGPT.exe','VALORANT-Win64-Shipping.exe')
    $CommandLooksTraining=$Cmd -match '(?i)train|fit|torch|cuda|optimizer|pytorch'
    $Classification='SAMPLED_PROCESS_ACTIVITY'; $Block=$false
    if($IsKnownDesktop -and $null -ne $CpuRate -and $CpuRate -gt 0){$Classification='NON_RESEARCH_DESKTOP_LOAD'}
    elseif($IsPython -and $null -ne $CpuRate -and (($CpuRate -ge .15) -or ($CommandLooksTraining -and $CpuRate -ge .05))){$Classification='PYTHON_HEAVY';$Block=$true}
    elseif($null -ne $CpuRate -and $CpuRate -ge .8){$Classification='OTHER_CPU_HEAVY';$Block=$true}
    $Row=[pscustomobject]@{pid=$TaskProcessId;name=$Name;cpu_seconds_per_wall_second=$CpuRate;command=$Cmd;python=$IsPython;cad=$IsCad;command_looks_training=$CommandLooksTraining;classification=$Classification;block=$Block}
    if($Classification -eq 'NON_RESEARCH_DESKTOP_LOAD'){$NonResearchDesktopRows += $Row}
    if($Block){$HeavyRows += $Row}
    if($IsPython -or $IsCad -or ($null -ne $CpuRate -and $CpuRate -ge .15)){$ProcessRows += $Row}
}
$GpuAfterLines=@(& $NvidiaPath --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>&1)
if($LASTEXITCODE -ne 0){throw "nvidia-smi second GPU query failed: $($GpuAfterLines -join ' ')"}
$GpuAfter=@(); foreach($Line in $GpuAfterLines){if([string]$Line -match '^\s*(\d+)\s*,\s*(\d+)'){ $GpuAfter += [pscustomobject]@{utilization_percent=[int]$Matches[1];memory_used_mib=[int]$Matches[2]} }}
if($GpuAfter.Count -ne $GpuBefore.Count){throw 'GPU count changed or second query was unreadable.'}
$GpuRows=@()
foreach($Line in $GpuAppLines){
    $Parts=([string]$Line).Split(',')
    if($Parts.Count -ge 3 -and $Parts[0].Trim() -match '^\d+$' -and $Parts[2].Trim() -match '^\d+$'){
        $TaskProcessId=[int]$Parts[0].Trim(); $GpuName=$Parts[1].Trim(); $MemoryMiB=[int]$Parts[2].Trim()
        $Proc=$Processes|Where-Object {[int]$_.ProcessId -eq $TaskProcessId}|Select-Object -First 1
        if(!$Proc){$GpuRows += [pscustomobject]@{pid=$TaskProcessId;process_name=$GpuName;used_memory_mib=$MemoryMiB;classification='UNRESOLVED_NUMERIC_COMPUTE_PID';block=$true};$HeavyRows += $GpuRows[-1];continue}
        $CpuRate=$null; if($Cpu0.ContainsKey($TaskProcessId) -and $Cpu1.ContainsKey($TaskProcessId)){$CpuRate=([math]::Max(0,$Cpu1[$TaskProcessId]-$Cpu0[$TaskProcessId]))/[math]::Max(.1,$SampleSeconds)}
        $IsPython=([string]$Proc.Name) -match '^(pythonw?|jupyter(?:-lab)?)\.exe$'
        $IsCad=([string]$Proc.Name) -match '^(sldworks|solidworks)(?:\.exe)?$'
        $Cmd=[string]$Proc.CommandLine; $Cmd=$Cmd -replace '(?i)(--?(?:token|password|secret|api[_-]?key)(?:=|\s+))\S+','$1<redacted>'
        $Block=$true; $Class='NUMERIC_NVIDIA_COMPUTE_PID'
        $GpuRows += [pscustomobject]@{pid=$TaskProcessId;process_name=[string]$Proc.Name;gpu_reported_name=$GpuName;used_memory_mib=$MemoryMiB;cpu_seconds_per_wall_second=$CpuRate;command=$Cmd;classification=$Class;block=$Block}
        if($Block){$HeavyRows += $GpuRows[-1]}
    }elseif($Parts.Count -ge 3 -and $Parts[0].Trim() -match '^\d+$' -and $Parts[2].Trim() -match '(?i)^\[?N/?A\]?$'){
        $TaskProcessId=[int]$Parts[0].Trim(); $Proc=$Processes|Where-Object {[int]$_.ProcessId -eq $TaskProcessId}|Select-Object -First 1
        $Name=if($Proc){[string]$Proc.Name}else{'<unresolved>'}; $CpuRate=$null
        if($Cpu0.ContainsKey($TaskProcessId) -and $Cpu1.ContainsKey($TaskProcessId)){$CpuRate=([math]::Max(0,$Cpu1[$TaskProcessId]-$Cpu0[$TaskProcessId]))/[math]::Max(.1,$SampleSeconds)}
        $Cmd=''; if($Proc){$Cmd=[string]$Proc.CommandLine;$Cmd=$Cmd -replace '(?i)(--?(?:token|password|secret|api[_-]?key)(?:=|\s+))\S+','$1<redacted>'}
        $GpuRows += [pscustomobject]@{pid=$TaskProcessId;process_name=$Name;gpu_reported_name=$Parts[1].Trim();used_memory_mib=$null;cpu_seconds_per_wall_second=$CpuRate;command=$Cmd;classification='NVIDIA_DETAILS_UNAVAILABLE_COUNTER_REQUIRED';block=$false;raw_line=[string]$Line}
    }elseif(([string]$Line).Trim() -match '(?i)^\[?N/?A\]?\s*,'){
        $GpuRows += [pscustomobject]@{pid=$null;process_name=([string]$Line).Split(',')[1].Trim();used_memory_mib=$null;classification='WDDM_CONTEXT_NA_NOT_COMPUTE_EVIDENCE';block=$false;raw_line=[string]$Line}
    }elseif(([string]$Line).Trim() -and ([string]$Line) -notmatch '(?i)no running processes found'){
        throw "Unparseable nvidia-smi compute-app row: $Line"
    }
}
$GpuEngineRows=@(); $EngineNames=@($GpuEngineBefore.Name)+@($GpuEngineAfter.Name)|Sort-Object -Unique
foreach($EngineName in $EngineNames){
    $BeforeRow=$GpuEngineBefore|Where-Object {$_.Name -eq $EngineName}|Select-Object -First 1
    $AfterRow=$GpuEngineAfter|Where-Object {$_.Name -eq $EngineName}|Select-Object -First 1
    $BeforeUtil=if($BeforeRow){[double]$BeforeRow.UtilizationPercentage}else{0.0}; $AfterUtil=if($AfterRow){[double]$AfterRow.UtilizationPercentage}else{0.0}
    if($EngineName -notmatch 'pid_(\d+)'){continue}; $TaskProcessId=[int]$Matches[1]
    $Proc=$Processes|Where-Object {[int]$_.ProcessId -eq $TaskProcessId}|Select-Object -First 1
    $CpuRate=$null; if($Cpu0.ContainsKey($TaskProcessId) -and $Cpu1.ContainsKey($TaskProcessId)){$CpuRate=([math]::Max(0,$Cpu1[$TaskProcessId]-$Cpu0[$TaskProcessId]))/[math]::Max(.1,$SampleSeconds)}
    $MaxEngineUtil=[math]::Max($BeforeUtil,$AfterUtil); $Block=$false; $Class='COMPUTE_ENGINE_IDLE'
        if($MaxEngineUtil -gt 0){
        if(!$Proc){$Class='UNKNOWN_ACTIVE_GPU_COMPUTE';$Block=$true}
        else{$Class='ACTIVE_GPU_COMPUTE';$Block=$true}
    }
    $Cmd=''; if($Proc){$Cmd=[string]$Proc.CommandLine;$Cmd=$Cmd -replace '(?i)(--?(?:token|password|secret|api[_-]?key)(?:=|\s+))\S+','$1<redacted>'}
    $GpuEngineRows += [pscustomobject]@{name=$EngineName;pid=$TaskProcessId;before_utilization_percent=$BeforeUtil;after_utilization_percent=$AfterUtil;cpu_seconds_per_wall_second=$CpuRate;process_name=$(if($Proc){[string]$Proc.Name}else{'<unresolved>'});command=$Cmd;classification=$Class;block=$Block}
    if($Block){$HeavyRows += $GpuEngineRows[-1]}
}
if($HeavyRows.Count -gt 0){
    $ReportsDir=Join-Path $Here 'reports'
    if(!(Test-Path -LiteralPath $ReportsDir)){New-Item -ItemType Directory -Path $ReportsDir|Out-Null}
    $BlockedPath=Join-Path $ReportsDir ("C1_PREFLIGHT_BLOCKED_{0}.json" -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
    [ordered]@{status='BLOCKED_OTHER_HEAVY_JOB';mode=$Mode;created_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ');
        gpu_compute_rows=$GpuRows;gpu_engine_counter_total=$GpuEngineAfterAll.Count;gpu_compute_counter_total=$GpuEngineRows.Count;
        gpu_compute_counter_active_rows=@($GpuEngineRows|Where-Object {$_.before_utilization_percent -gt 0 -or $_.after_utilization_percent -gt 0}).Count;
        gpu_engine_rows=$GpuEngineRows;gpu_utilization_before=$GpuBefore;gpu_utilization_after=$GpuAfter;
        sampled_process_activity=$ProcessRows;non_research_desktop_loads=$NonResearchDesktopRows;
        blocking_process_activity=$HeavyRows;timing_isolated=$false;formal_timing_qualified=$false;processes_stopped=$false} |
        ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $BlockedPath -Encoding utf8
    throw "Other heavy CPU/GPU job detected; no process was stopped. Evidence=$BlockedPath"
}
$Drive=[System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Root)); $Free=[int64]$Drive.AvailableFreeSpace
$Floor=[int64]30000000000; $Cap=[int64]6442450944; $Runs=Join-Path $Here 'runs'; $ExistingBytes=[int64]0
if(Test-Path -LiteralPath $Runs){$ExistingBytes=[int64](Get-ChildItem -LiteralPath $Runs -File -Recurse | Measure-Object -Property Length -Sum).Sum}
if($Mode -eq 'PROBE'){$Count=36;$MaxSeconds=30.0;$MaxBytes=[int64]55000000}
else{
    $ProbePath=Join-Path $Here 'reports/probe_c1.json'; if(!(Test-Path -LiteralPath $ProbePath)){throw 'CONTINUE requires probe evidence.'}
    $Probe=Get-Content -LiteralPath $ProbePath -Raw|ConvertFrom-Json
    if($Probe.status -ne 'PROBE_COMPLETE' -or $Probe.completed_runs -ne 3 -or $Probe.run_rows.Count -ne 3){throw 'CONTINUE probe gate failed.'}
    if($Probe.source_lock_sha256 -ne $LockSha -or $Probe.release_sha256 -ne $ReleaseSha){throw 'Probe source identity mismatch.'}
    $Count=33; $MaxSeconds=[math]::Max(30.0,[double](($Probe.run_rows|Measure-Object -Property attempt_execution_and_raw_persistence_seconds -Maximum).Maximum))
    $MaxBytes=[int64][math]::Max(55000000,[double](($Probe.run_rows|Measure-Object -Property attempt_output_bytes -Maximum).Maximum))
}
$ProjectedSeconds=[int64][math]::Ceiling($Count*$MaxSeconds*1.25)
$ProjectedBytes=[int64][math]::Ceiling($Count*$MaxBytes*1.25)
if($ExistingBytes+$ProjectedBytes -gt $Cap -or $Free-$ProjectedBytes -lt $Floor){throw 'C1 output budget or 30-GB free-space floor failed.'}
if($Now.AddSeconds($ProjectedSeconds) -gt $Deadline){throw 'Projected C1 stage duration exceeds the fixed 2026-10-24T17:01:00Z deadline.'}
if($Mode -eq 'PROBE' -and (Test-Path -LiteralPath $Runs) -and @(Get-ChildItem -LiteralPath $Runs -Force).Count -ne 0){throw 'PROBE refuses existing or partial output.'}
$Report=[ordered]@{
    status='PASS';mode=$Mode;created_utc=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ');repo_root=$Root
    source_lock_sha256=$LockSha;release_sha256=$ReleaseSha;deadline_utc=$Deadline.ToString('yyyy-MM-ddTHH:mm:ssZ')
    matlab_process_count=0;matlab_process_stopped=$false;gpu_compute_rows=$GpuRows;gpu_engine_counter_total=$GpuEngineAfterAll.Count
    gpu_compute_counter_total=$GpuEngineRows.Count
    gpu_compute_counter_active_rows=@($GpuEngineRows|Where-Object {$_.before_utilization_percent -gt 0 -or $_.after_utilization_percent -gt 0}).Count
    gpu_engine_rows=$GpuEngineRows;gpu_utilization_before=$GpuBefore;gpu_utilization_after=$GpuAfter
    gpu_utilization_interpretation='Record only; global WDDM desktop utilization is not compute-training evidence.'
    sampled_process_activity=$ProcessRows;non_research_desktop_loads=$NonResearchDesktopRows
    fixed_step_screen_allowed=$true;timing_isolated=($NonResearchDesktopRows.Count -eq 0)
    formal_timing_qualified=($NonResearchDesktopRows.Count -eq 0);other_heavy_job_count=0;free_bytes_before=$Free;minimum_free_bytes=$Floor
    existing_run_output_bytes=$ExistingBytes;projected_reserved_bytes=$ProjectedBytes;max_output_bytes=$Cap
    estimated_max_attempt_seconds=$MaxSeconds;estimated_stage_seconds=$ProjectedSeconds;remaining_attempt_count=$Count
    expected_total_runs=36;probe_runs=3;remaining_runs_after_probe=33;optimizer_steps=0;gpu_jobs=0;Plant_started=$false;TEST_accessed=$false
}
$ReportPath=Join-Path $Here ("reports/preflight_c1_{0}.json" -f $Mode.ToLowerInvariant())
if($DryRun){$Report.status='PASS_DRY_RUN';$Report|ConvertTo-Json -Depth 7|Write-Output;Write-Output "C1_PREFLIGHT DRY_RUN mode=$Mode free_bytes=$Free reserve=$ProjectedBytes duration_s=$ProjectedSeconds compute_counters=$($GpuEngineRows.Count) active=$($Report.gpu_compute_counter_active_rows) timing_isolated=$($Report.timing_isolated)"}
else{if(Test-Path -LiteralPath $ReportPath){throw "Refusing to overwrite preflight record: $ReportPath"};$ReportsDir=Split-Path -Parent $ReportPath;if(!(Test-Path -LiteralPath $ReportsDir)){New-Item -ItemType Directory -Path $ReportsDir|Out-Null};$Report|ConvertTo-Json -Depth 7|Set-Content -LiteralPath $ReportPath -Encoding utf8;Write-Output "C1_PREFLIGHT PASS mode=$Mode free_bytes=$Free reserve=$ProjectedBytes duration_s=$ProjectedSeconds compute_counters=$($GpuEngineRows.Count) active=$($Report.gpu_compute_counter_active_rows) timing_isolated=$($Report.timing_isolated)"}
