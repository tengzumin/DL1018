$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$reportDir=$PSScriptRoot
$matlabExe='C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
$diagnosticPath=Join-Path $reportDir 'run_path_diagnostic_v1.m'
$provenancePath=Join-Path $reportDir 'EXTRACTED_SOURCE_MANIFEST_v1.json'
$receiptPath=Join-Path $reportDir 'MATLAB_OS_EXIT_v1.json'
$resultPath=Join-Path $reportDir 'PATH_DIAGNOSTIC_RESULT_v1.json'
$failurePath=Join-Path $reportDir 'PATH_DIAGNOSTIC_FAILURE_v1.json'
$stdoutPath=Join-Path $reportDir 'logs/PATH_DIAGNOSTIC.stdout.log'
$stderrPath=Join-Path $reportDir 'logs/PATH_DIAGNOSTIC.stderr.log'
$prefPath=Join-Path $reportDir 'matlab_prefdir'
if(-not (Test-Path -LiteralPath $matlabExe -PathType Leaf)){throw 'Locked MATLAB R2025b executable is missing.'}
$active=Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'"
if($active){$active|Select-Object ProcessId,ParentProcessId,Name,CommandLine|Format-List;throw 'A MATLAB process is active; do not overlap.'}
$entryPath=Join-Path $repoRoot 'experiments/c5_test48_v4/test48_entry_v4.m'
$contractPath=Join-Path $repoRoot 'experiments/c5_test48_v4/TEST48_RUN_CONTRACT_v4.json'
$manifestPath=Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v4/TEST_METHOD_SOURCE_MANIFEST_v4.json'
$contract=Get-Content -LiteralPath $contractPath -Raw|ConvertFrom-Json
$checks=@(
    @{path=$entryPath;sha=$contract.entry_sha256},
    @{path=(Join-Path $repoRoot 'experiments/c5_test48_v4/RUN_TEST48_EXACT_v1.ps1');sha=$contract.launcher_sha256},
    @{path=$manifestPath;sha=$contract.method_source_manifest_sha256}
)
foreach($item in $checks){
    $actual=(Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if($actual -ne ([string]$item.sha).ToLowerInvariant()){throw "Frozen SHA mismatch: $($item.path)"}
}
$provenance=Get-Content -LiteralPath $provenancePath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $diagnosticPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $provenance.diagnostic_script_sha256){throw 'Diagnostic script SHA differs from extracted source manifest.'}
foreach($path in @($receiptPath,$resultPath,$failurePath,$stdoutPath,$stderrPath,$prefPath)){
    if(Test-Path -LiteralPath $path){throw "No-retry guard: diagnostic output exists: $path"}
}
$logDir=Split-Path -Parent $stdoutPath
New-Item -ItemType Directory -Path $logDir|Out-Null
New-Item -ItemType Directory -Path $prefPath|Out-Null
$oldPref=$env:MATLAB_PREFDIR
$env:MATLAB_PREFDIR=$prefPath
$rootForMatlab=$repoRoot
$reportForMatlab=$reportDir
$expr="try; cd('$rootForMatlab'); addpath('$reportForMatlab'); run_path_diagnostic_v1(); quit(0,'force'); catch ME; fprintf(2,'%s',getReport(ME,'extended','hyperlinks','off')); fprintf(2,char(10)); quit(1,'force'); end"
$argLine='-singleCompThread -wait -batch "'+$expr+'"'
$started=[DateTime]::UtcNow.ToString('o')
try{
    $cpu=@(Get-CimInstance Win32_Processor|Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    $computer=Get-CimInstance Win32_ComputerSystem
    $proc=Start-Process -FilePath $matlabExe -ArgumentList $argLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $pidValue=[int]$proc.Id
    $snapshot=Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue"
    $peak=[int64]0;$cpuSeconds=0.0
    while(-not $proc.HasExited){
        $proc.Refresh()
        $peak=[Math]::Max($peak,[int64]$proc.PeakWorkingSet64)
        $cpuSeconds=$proc.TotalProcessorTime.TotalSeconds
        if($proc.WaitForExit(5000)){break}
    }
    $proc.Refresh()
    $peak=[Math]::Max($peak,[int64]$proc.PeakWorkingSet64)
    $cpuSeconds=$proc.TotalProcessorTime.TotalSeconds
    $exitCode=[int]$proc.ExitCode
    $receipt=[ordered]@{
        schema='TEST48_V4_PATH_DIAGNOSTIC_OS_EXIT_V1'
        mode='PATH_DIAGNOSTIC_ONLY'
        matlab_os_exit_code=$exitCode
        natural_wait_used=$true
        started_utc=$started
        completed_utc=[DateTime]::UtcNow.ToString('o')
        diagnostic_script_path=$diagnosticPath
        diagnostic_script_sha256=(Get-FileHash -LiteralPath $diagnosticPath -Algorithm SHA256).Hash.ToLowerInvariant()
        extracted_source_manifest_path=$provenancePath
        extracted_source_manifest_sha256=(Get-FileHash -LiteralPath $provenancePath -Algorithm SHA256).Hash.ToLowerInvariant()
        stdout_path=$stdoutPath
        stdout_sha256=(Get-FileHash -LiteralPath $stdoutPath -Algorithm SHA256).Hash.ToLowerInvariant()
        stderr_path=$stderrPath
        stderr_sha256=(Get-FileHash -LiteralPath $stderrPath -Algorithm SHA256).Hash.ToLowerInvariant()
        process_snapshot=[ordered]@{
            pid=$pidValue
            command_line=$(if($snapshot){$snapshot.CommandLine}else{''})
            creation_date=$(if($snapshot){$snapshot.CreationDate}else{''})
            cpu_processors=$cpu
            logical_cpu_count=$computer.NumberOfLogicalProcessors
            physical_memory_bytes=$computer.TotalPhysicalMemory
            matlab_cpu_time_s=$cpuSeconds
            peak_working_set_bytes=$peak
            monitor_poll_ms=5000
        }
    }
    [IO.File]::WriteAllText($receiptPath,(ConvertTo-Json -InputObject $receipt -Depth 30)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    if($exitCode -ne 0){throw "MATLAB naturally exited OS $exitCode; preserve diagnostic evidence and stop without retry."}
    if(-not (Test-Path -LiteralPath $resultPath -PathType Leaf)){throw 'MATLAB exited OS0 but no diagnostic result exists.'}
    "OS_EXIT=$exitCode PID=$pidValue RECEIPT=$receiptPath"
}
finally{
    if($null -ne $oldPref){$env:MATLAB_PREFDIR=$oldPref}else{Remove-Item Env:MATLAB_PREFDIR -ErrorAction SilentlyContinue}
}