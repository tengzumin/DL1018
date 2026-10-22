param([ValidateSet('PROBE','CONTINUE')][string]$Mode='PROBE',[switch]$ParentReviewed)
$ErrorActionPreference='Stop'
$expDir=$PSScriptRoot;$repoRoot=Split-Path -Parent (Split-Path -Parent $expDir)
$lockPath=Join-Path $expDir 'frozen_inputs.json';$reportPath=Join-Path $expDir 'reports\preflight_round3.json'
$errors=[System.Collections.Generic.List[string]]::new();$checks=[ordered]@{}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Get-SetupManifestSha($Lock){
    $parts=@($Lock.setupFiles|ForEach-Object {"$($_.name)|$(([string]$_.sha256).ToLowerInvariant())"})
    $canonical=[string]::Join(';',$parts);$bytes=[Text.Encoding]::UTF8.GetBytes($canonical)
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}
function Add-Error([string]$Message){$script:errors.Add($Message)}
function Test-Hash([string]$Name,[string]$Path,[string]$Expected){
    try{if(-not(Test-Path -LiteralPath $Path -PathType Leaf)){Add-Error "$Name missing: $Path";return $false};$actual=Sha $Path
        if($actual -ne $Expected.ToLowerInvariant()){Add-Error "$Name SHA mismatch: $Path";return $false};return $true
    }catch{Add-Error "$Name hash query failed: $($_.Exception.Message)";return $false}
}
function Get-TreeBytes([string]$Path){if(-not(Test-Path -LiteralPath $Path)){return [int64]0};$sum=[int64]0;Get-ChildItem -LiteralPath $Path -Recurse -File -Force|ForEach-Object {$sum+=[int64]$_.Length};return $sum}
function Get-GpuAudit($Lock){
    $issues=[System.Collections.Generic.List[string]]::new();$processes=[System.Collections.Generic.List[object]]::new();$fallbacks=[System.Collections.Generic.List[object]]::new()
    $result=[ordered]@{schema='ROUND3_WDDM_GPU_AUDIT_V1';status='BLOCKED';driver_model='UNKNOWN';process_rows=@();pids_rows=@();compute_query_rows=@();engine_rows=@();active_compute_rows=@();errors=@()}
    try{$exe=(Get-Command nvidia-smi -ErrorAction Stop).Source;$normal=@(& $exe 2>&1|ForEach-Object {[string]$_});$exit=$LASTEXITCODE;$joined=[string]::Join("`n",$normal)
        if($exit -ne 0){throw "nvidia-smi exited $exit"};$result.driver_model=if($joined -match '\bWDDM\b'){'WDDM'}else{'UNKNOWN'}
        if($result.driver_model -ne 'WDDM'){$issues.Add('NVIDIA driver model is not confirmed WDDM.')}
        $rows=@($normal|Where-Object {$_ -match '^\|\s*\d+\s+\S+\s+\S+\s+\d+\s+\S+'});$result.process_rows=$rows
        $procById=@{};Get-CimInstance Win32_Process|ForEach-Object {$procById[[string]$_.ProcessId]=$_.Name}
        $byPid=@{};$pat='^\|\s*(?<gpu>\d+)\s+\S+\s+\S+\s+(?<pid>\d+)\s+(?<type>\S+)\s+(?<img>.+?)\s+(?:N/A|\d+\s*MiB)\s*\|$'
        foreach($line in $rows){if($line -notmatch $pat){$issues.Add("Unparseable NVIDIA process row: $line");continue}
            $processId=[int]$Matches.pid;$type=$Matches.type;$image=[string]$procById[[string]$processId]
            if(-not $image){$issues.Add("Unknown GPU process PID $processId.");continue}
            if($type -notin @('C+G','G') -or $image -match ($Lock.safety.gpu_suspected_compute_image_patterns -join '|')){$issues.Add("Compute/unknown/suspected GPU context PID $processId $image ($type).")}
            $entry=[pscustomobject]@{pid=$processId;type=$type;image=$image;raw=$line.Trim()};$processes.Add($entry)
            if(-not $byPid.ContainsKey([string]$processId)){$byPid[[string]$processId]=[System.Collections.Generic.List[object]]::new()};$byPid[[string]$processId].Add($entry)
        }
        $pids=@(& $exe -q -d PIDS 2>&1|ForEach-Object {[string]$_});$pidsExit=$LASTEXITCODE;if($pidsExit -ne 0){throw "PIDS query exited $pidsExit"}
        $ptext=[string]::Join("`n",$pids);$matches=[regex]::Matches($ptext,'(?ms)^\s*Process ID\s*:\s*(?<pid>\d+)\s*(?<body>.*?)(?=^\s*Process ID\s*:|\z)')
        $headers=[regex]::Matches($ptext,'(?im)^\s*Process ID\s*:').Count;if($headers -ne $matches.Count){$issues.Add('PIDS query has an unparseable PID row.')}
        foreach($match in $matches){$processId=[int]$match.Groups['pid'].Value;$body=$match.Groups['body'].Value
            $tm=[regex]::Match($body,'(?im)^[ \t]*Type[ \t]*:[ \t]*(?<type>\S+)');if(-not $tm.Success){$issues.Add("Missing PIDS type for PID $processId.");continue}
            $type=$tm.Groups['type'].Value;$image=[string]$procById[[string]$processId];$row=[pscustomobject]@{pid=$processId;type=$type;image=$image;raw=$match.Value.Trim()};$fallbacks.Add($row)
            if(-not $image){$issues.Add("Unknown PIDS PID $processId.")};if($type -notin @('C+G','G')){$issues.Add("Unknown/compute PIDS type $type PID $processId.")}
            if($image -match ($Lock.safety.gpu_suspected_compute_image_patterns -join '|')){$issues.Add("Suspected compute image in PIDS table PID $processId ($image).")}
            $ordinary=@($processes|Where-Object {$_.pid -eq $processId});if($ordinary.Count -gt 0 -and @($ordinary|Where-Object {$_.type -ne $type}).Count -gt 0){$issues.Add("Process/PIDS type mismatch PID $processId.")}
        }
        foreach($entry in $processes){$p=@($fallbacks|Where-Object {$_.pid -eq $entry.pid});if($p.Count -ne 1 -or $p[0].type -ne $entry.type){$issues.Add("Ordinary/PIDS table mismatch PID $($entry.pid).")}}
        $query=@(& $exe --query-compute-apps=pid,process_name --format=csv,noheader,nounits 2>&1|ForEach-Object {[string]$_});$qexit=$LASTEXITCODE
        if($qexit -ne 0){throw "Compute-app query exited $qexit"};$result.compute_query_rows=$query
        foreach($line in @($query|ForEach-Object {$_.Trim()}|Where-Object {$_ -and $_ -notmatch '^No running processes found'})){
            if($line -notmatch '^(?<pid>\d+)\s*,'){ $issues.Add("Unparseable compute-app row: $line");continue }
            $processId=[int]$Matches.pid;$normalRows=@($processes|Where-Object {$_.pid -eq $processId});$pidRows=@($fallbacks|Where-Object {$_.pid -eq $processId})
            if(-not $procById.ContainsKey([string]$processId) -or $pidRows.Count -ne 1 -or $pidRows[0].type -notin @('C+G','G') -or $normalRows.Count -gt 1){$issues.Add("Compute-query PID $processId lacks unique approved WDDM context and Win32 mapping.")}
        }
        $eng=@(Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction Stop)
        if($eng.Count -eq 0){throw 'GPU engine counters returned no rows.'}
        $outRows=[System.Collections.Generic.List[object]]::new();$active=[System.Collections.Generic.List[object]]::new()
        foreach($e in $eng){$v=0.0;if(-not [double]::TryParse([string]$e.UtilizationPercentage,[ref]$v) -or [double]::IsNaN($v) -or [double]::IsInfinity($v) -or $v -lt 0 -or $v -gt 100){$issues.Add("Invalid GPU engine counter $($e.Name)");continue}
            $row=[pscustomobject]@{name=[string]$e.Name;utilization_percentage=$v};$outRows.Add($row)
            if([string]$e.Name -match 'engtype_Compute' -and $v -gt 0){$active.Add($row)}
        }
        $result.engine_rows=$outRows.ToArray();$result.active_compute_rows=$active.ToArray()
        foreach($qline in @($query|ForEach-Object {$_.Trim()}|Where-Object {$_ -match '^\d+\s*,'})){
            $processId=[int](($qline -split ',')[0].Trim());$pidEng=@($outRows|Where-Object {$_.name -match "(?:^|_)pid_${processId}(?:_|$)"})
            if($pidEng.Count -eq 0){$issues.Add("No per-PID engine counter for WDDM fallback $processId.")}
            if(@($pidEng|Where-Object {$_.name -match 'engtype_Compute' -and $_.utilization_percentage -gt 0}).Count -gt 0){$issues.Add("Active per-PID Compute counter for $processId.")}
        }
        if($active.Count -gt 0){$issues.Add('Active GPU engtype_Compute counter detected.')}
        $result.errors=$issues.ToArray();$result.status=if($issues.Count -eq 0){'PASS'}else{'BLOCKED'};return $result
    }catch{$issues.Add("GPU audit failed closed: $($_.Exception.Message)");$result.errors=$issues.ToArray();return $result}
}

$lock=$null;$lockSha='';$probe=$null;$gpu=$null;$matlabCount=-1;$freeBytes=0L;$outputBytes=0L;$projectedBytes=0L;$projectedSeconds=0L
try{
    if($PSVersionTable.PSVersion.Major -lt 7){Add-Error 'PowerShell 7 or later is required.'}
    if(-not(Test-Path -LiteralPath $lockPath -PathType Leaf)){throw 'Frozen input lock is missing.'}
    $lockSha=Sha $lockPath;$lock=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json -Depth 100 -DateKind String
    if($lock.schema -ne 'ROUND3_XY_PCF_SCREEN_INPUTS_V1') {Add-Error 'Unexpected R3 lock schema.'}
    if($lock.safety.read_test -ne $false -or $lock.analysis.test_access -ne $false -or @($lock.scenes|Where-Object {$_.split -ne 'VAL' -or $_.scene_id -notlike 'DL1018_VAL_*'}).Count -gt 0){Add-Error 'Only the fixed VAL set is permitted; TEST is sealed.'}
    if($lock.taskbook.sha256 -ne 'a9d876f0e22175785f184707ba0f35090be3adf6a25317e83c39a9c88a1ccb4a'){Add-Error 'Frozen taskbook SHA changed.'}
    Test-Hash 'taskbook' $lock.taskbook.path $lock.taskbook.sha256|Out-Null
    Test-Hash 'upstream R2 lock' $lock.upstream_round2.lock_path $lock.upstream_round2.lock_sha256|Out-Null
    Test-Hash 'scene list' $lock.scene_list.path $lock.scene_list.sha256|Out-Null
    Test-Hash 'R2 reuse manifest' $lock.reuse_manifest.path $lock.reuse_manifest.sha256|Out-Null
    Test-Hash 'model MAT' $lock.model.mat_path $lock.model.mat_sha256|Out-Null
    Test-Hash 'normalizer' $lock.normalizer.npz_path $lock.normalizer.npz_file_sha256|Out-Null
    foreach($entry in @($lock.plantFiles)+@($lock.runtimeFiles)+@($lock.localRuntimeFiles)+@($lock.setupFiles)){Test-Hash "source $($entry.path)" $entry.path $entry.sha256|Out-Null}
    foreach($entry in $lock.rescores){Test-Hash "rescore $($entry.role)" $entry.path $entry.sha256|Out-Null}
    $deadline=[DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
    if($deadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or [DateTimeOffset]::UtcNow -ge $deadline){Add-Error 'Fixed global deadline passed or changed.'}
    if($Mode -eq 'PROBE'){$projectedSeconds=[int64][Math]::Ceiling($lock.safety.estimated_runtime_per_attempt_seconds*1.25);$projectedBytes=[int64][Math]::Ceiling($lock.safety.estimated_bytes_per_attempt*1.25)}
    elseif(Test-Path -LiteralPath (Join-Path $expDir 'reports\probe_round3.json')){$probe=Get-Content (Join-Path $expDir 'reports\probe_round3.json') -Raw|ConvertFrom-Json;$projectedSeconds=[int64][Math]::Ceiling([Math]::Max($lock.safety.estimated_runtime_per_attempt_seconds,$probe.attempt_execution_and_raw_persistence_seconds)*11*1.25);$projectedBytes=[int64][Math]::Ceiling([Math]::Max($lock.safety.estimated_bytes_per_attempt,$probe.attempt_output_bytes)*11*1.25)}else{Add-Error 'CONTINUE requires an existing PROBE summary.'}
    $drive=[IO.Path]::GetPathRoot($repoRoot);$freeBytes=[int64]([IO.DriveInfo]::new($drive)).AvailableFreeSpace
    if($freeBytes-$projectedBytes -lt [int64]$lock.safety.minimum_free_bytes){Add-Error 'Projected free-space floor below 30 GB.'}
    $outputBytes=Get-TreeBytes (Join-Path $expDir 'runs')
    if($outputBytes+$projectedBytes -gt [int64]$lock.safety.max_cycle_output_bytes){Add-Error 'Projected output exceeds 80 GB cycle cap.'}
    if([DateTimeOffset]::UtcNow.AddSeconds($projectedSeconds) -gt $deadline){Add-Error 'Projected run would exceed hard deadline.'}
    if($Mode -eq 'PROBE' -and (Get-ChildItem -LiteralPath (Join-Path $expDir 'runs') -Force -ErrorAction SilentlyContinue|Measure-Object).Count -gt 0){Add-Error 'PROBE refuses any existing runs output.'}
    if($Mode -eq 'CONTINUE'){for($i=1;$i -lt 12;$i++){if(Test-Path -LiteralPath (Join-Path $expDir ("runs\{0}\attempt_01" -f $lock.scenes[$i].scene_id))){Add-Error "CONTINUE refuses existing attempt $($lock.scenes[$i].scene_id)."}}}
    $matlabCount=@(Get-CimInstance Win32_Process|Where-Object {$_.Name -match '^matlab(?:window)?\.exe$'}).Count
    if($matlabCount -gt 0){Add-Error "MATLAB is already active ($matlabCount process(es)); do not interrupt it."}
    $gpu=Get-GpuAudit $lock;if($gpu.status -ne 'PASS'){$errors.AddRange([string[]]$gpu.errors);if($gpu.errors.Count -eq 0){Add-Error 'GPU compute-resource audit is blocked.'}}
    if($ParentReviewed){
        $reviewPath=Join-Path $expDir 'reports\main_review_round3.json'
        if(-not(Test-Path -LiteralPath $reviewPath -PathType Leaf)){Add-Error 'Main-model review record missing.'}
        else{
            $review=Get-Content $reviewPath -Raw|ConvertFrom-Json
            $setupSha=Get-SetupManifestSha $lock;$runnerPath=Join-Path $expDir 'run_round3_xy_pcf_screen.m';$runnerSha=Sha $runnerPath
            $staticPath=Join-Path $expDir 'reports\static_test_round3.json';$matPath=Join-Path $expDir 'reports\offline_math_smoke_matlab_final.json';$pyPath=Join-Path $expDir 'reports\offline_math_smoke_python_final.json'
            $reviewFields=@('static_report_sha256','matlab_smoke_report_sha256','python_smoke_report_sha256','setup_manifest_sha256','runner_sha256')
            foreach($field in $reviewFields){if([string]::IsNullOrWhiteSpace([string]$review.$field)){Add-Error "Main review lacks $field."}}
            if($review.status -ne 'APPROVED' -or $review.mode -ne $Mode -or $review.frozen_inputs_sha256 -ne $lockSha -or $review.taskbook_sha256 -ne $lock.taskbook.sha256 -or $review.setup_manifest_sha256 -ne $setupSha -or $review.runner_sha256 -ne $runnerSha){Add-Error 'Main-model approval does not bind the current mode/taskbook/lock/setup/runner.'}
            $evidence=@(
                [pscustomobject]@{path=$staticPath;sha=[string]$review.static_report_sha256;kind='static'},
                [pscustomobject]@{path=$matPath;sha=[string]$review.matlab_smoke_report_sha256;kind='matlab'},
                [pscustomobject]@{path=$pyPath;sha=[string]$review.python_smoke_report_sha256;kind='python'})
            foreach($item in $evidence){
                if(-not(Test-Path -LiteralPath $item.path -PathType Leaf)){Add-Error "Reviewed $($item.kind) evidence missing: $($item.path)";continue}
                if((Sha $item.path) -ne $item.sha.ToLowerInvariant()){Add-Error "Reviewed $($item.kind) evidence SHA changed.";continue}
                $doc=Get-Content -LiteralPath $item.path -Raw|ConvertFrom-Json
                if($doc.status -ne 'PASS' -or $doc.frozen_inputs_sha256 -ne $lockSha -or $doc.setup_manifest_sha256 -ne $setupSha){Add-Error "Reviewed $($item.kind) evidence is stale or not PASS."}
                if($doc.round3_runner_sha256 -ne $runnerSha -and $item.kind -ne 'static'){Add-Error "Reviewed $($item.kind) evidence does not bind the runner."}
            }
            if(Test-Path -LiteralPath $staticPath -PathType Leaf){$static=Get-Content $staticPath -Raw|ConvertFrom-Json;if($static.runner_sha256 -ne $runnerSha -or $static.matlab_smoke_report_sha256 -ne [string]$review.matlab_smoke_report_sha256 -or $static.python_smoke_report_sha256 -ne [string]$review.python_smoke_report_sha256){Add-Error 'Static report does not bind current runner and offline reports.'}}
            if(Test-Path -LiteralPath $matPath -PathType Leaf){$mat=Get-Content $matPath -Raw|ConvertFrom-Json;if($mat.test_accessed -ne $false){Add-Error 'MATLAB smoke does not assert TEST sealed.'}}
            if(Test-Path -LiteralPath $pyPath -PathType Leaf){$parity=Get-Content $pyPath -Raw|ConvertFrom-Json;if($parity.test_accessed -ne $false -or $parity.matlab_report_sha256 -ne [string]$review.matlab_smoke_report_sha256){Add-Error 'Python smoke does not bind MATLAB evidence/TEST seal.'}}
            $checks.setup_manifest_sha256=$setupSha;$checks.main_review_sha256=Sha $reviewPath
        }
    }else{Add-Error 'A manual -ParentReviewed marker is required; this preflight grants no run authorization.'}
    if($Mode -eq 'CONTINUE' -and $ParentReviewed){
        $prPath=Join-Path $expDir 'reports\probe_review_round3.json';$probeDir=Join-Path $expDir ("runs\{0}\attempt_01" -f $lock.scenes[0].scene_id)
        $probeStatusPath=Join-Path $probeDir 'run_status.json';$probeRawPath=Join-Path $probeDir 'raw_run.mat';$probeStartPath=Join-Path $probeDir 'run_start.mat';$probeSummaryPath=Join-Path $expDir 'reports\probe_round3.json'
        if(-not(Test-Path $prPath -PathType Leaf)-or -not(Test-Path $probeStatusPath -PathType Leaf)-or -not(Test-Path $probeRawPath -PathType Leaf)-or -not(Test-Path $probeStartPath -PathType Leaf)-or -not(Test-Path $probeSummaryPath -PathType Leaf)){Add-Error 'CONTINUE requires reviewed, complete PROBE artifacts.'}
        else{
            $pr=Get-Content $prPath -Raw|ConvertFrom-Json;$ps=Get-Content $probeStatusPath -Raw|ConvertFrom-Json;$summary=Get-Content $probeSummaryPath -Raw|ConvertFrom-Json
            $rawSha=Sha $probeRawPath;$startSha=Sha $probeStartPath;$statusSha=Sha $probeStatusPath
            if($pr.status -ne 'PASS' -or $pr.scene_id -ne $lock.scenes[0].scene_id -or $pr.frozen_inputs_sha256 -ne $lockSha -or $pr.raw_sha256 -ne $rawSha -or $pr.run_start_sha256 -ne $startSha -or $pr.run_status_sha256 -ne $statusSha -or $ps.scene_id -ne $lock.scenes[0].scene_id -or $ps.status -ne 'STABLE' -or $ps.mode -ne 'PROBE' -or $ps.last_transition -ne 20000 -or $ps.update_enabled -ne $true -or $ps.pcf_enabled -ne $true -or $ps.head_type -ne 'FEATURE' -or (@($ps.eta_mask) -join ',') -ne '1,1,0' -or $ps.raw_sha256 -ne $rawSha -or $ps.run_start_sha256 -ne $startSha -or $ps.frozen_inputs_sha256 -ne $lockSha -or $summary.status -ne 'PROBE_COMPLETE' -or $summary.scene_id -ne $lock.scenes[0].scene_id -or $summary.raw_sha256 -ne $rawSha -or $summary.run_start_sha256 -ne $startSha -or $summary.status_sha256 -ne $statusSha){Add-Error 'PROBE review raw/run_start/status SHA or status contract does not match current artifacts.'}
            $checks.probe_review_sha256=Sha $prPath;$checks.probe_artifact_sha256=[ordered]@{raw=$rawSha;run_start=$startSha;run_status=$statusSha}
        }
    }
    $python=Get-Command python -ErrorAction SilentlyContinue
    if(-not $python){Add-Error 'Python is required for the read-only VAL identity verifier.'}
    else{$verify=Join-Path $expDir 'verify_round3_identity.py';$verifyOut=@(& $python.Source $verify --inputs-only 2>&1|ForEach-Object {[string]$_});$verifyExit=$LASTEXITCODE;$checks.identity_verifier_exit_code=$verifyExit;$checks.identity_verifier_output=$verifyOut;if($verifyExit -ne 0){Add-Error 'Frozen VAL input/source identity verifier failed.'}}
}catch{Add-Error "Preflight exception: $($_.Exception.Message)"}
$identityExit=$checks['identity_verifier_exit_code'];$identityOutput=$checks['identity_verifier_output'];$taskbookSha=''
if($lock){$taskbookSha=[string]$lock.taskbook.sha256}
$checkDetails=[ordered]@{powershell_version=$PSVersionTable.PSVersion.ToString();mode=$Mode;parent_reviewed_switch_present=[bool]$ParentReviewed;
    frozen_inputs_sha256=$lockSha;taskbook_sha256=$taskbookSha;matlab_process_count=$matlabCount;
    free_bytes=$freeBytes;cycle_output_bytes=$outputBytes;projected_output_bytes=$projectedBytes;projected_runtime_seconds=$projectedSeconds;
    gpu_resource_audit=$gpu;identity_verifier_exit_code=$identityExit;identity_verifier_output=$identityOutput;errors=$errors.ToArray()}
$status=if($errors.Count -eq 0 -and $ParentReviewed){'PASS'}else{'BLOCKED'}
$report=[ordered]@{schema='ROUND3_PCF_XY_PREFLIGHT_V1';status=$status;resource_preflight_only=$true;run_authorization_granted=$false;
    created_utc=[DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");mode=$Mode;parent_reviewed_switch_present=[bool]$ParentReviewed;
    frozen_inputs_sha256=$lockSha;matlab_process_count=$matlabCount;checks=$checkDetails;errors=$errors.ToArray()}
$report|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output "ROUND3_PREFLIGHT $status mode=$Mode errors=$($errors.Count) report=$reportPath"
if($status -ne 'PASS'){exit 1};exit 0
