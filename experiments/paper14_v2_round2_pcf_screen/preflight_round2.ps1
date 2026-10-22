param(
    [ValidateSet('PROBE','CONTINUE')][string] $Mode='PROBE',
    [switch] $ParentReviewed,
    [string] $ReportPathOverride
)
$ErrorActionPreference='Stop'
$expDir=$PSScriptRoot
$repoRoot=Split-Path -Parent (Split-Path -Parent $expDir)
$lockPath=Join-Path $expDir 'frozen_inputs.json'
$reportsRoot=[IO.Path]::GetFullPath((Join-Path $expDir 'reports'))
$reportPath=Join-Path $reportsRoot 'preflight_round2.json'
if(-not [string]::IsNullOrWhiteSpace($ReportPathOverride)){
    if([IO.Path]::IsPathRooted($ReportPathOverride)){$reportPath=[IO.Path]::GetFullPath($ReportPathOverride)}
    else {$reportPath=[IO.Path]::GetFullPath((Join-Path $expDir $ReportPathOverride))}
}
$reportsPrefix=$reportsRoot.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not $reportPath.StartsWith($reportsPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Preflight report path must stay under this experiment reports directory.' }
if(-not [string]::IsNullOrWhiteSpace($ReportPathOverride) -and (Test-Path -LiteralPath $reportPath)){throw 'Refusing to overwrite an existing versioned preflight report.'}
$errors=[System.Collections.Generic.List[string]]::new()
$checked=[System.Collections.Generic.List[object]]::new()
$verifierExit=$null
$verifierText=''
$gpuProbe=[ordered]@{schema='ROUND2_WDDM_GPU_RESOURCE_AUDIT_V2';status='NOT_CHECKED';driver_model='UNKNOWN';nvidia_smi_executable=$null;raw_nvidia_process_rows=@();raw_nvidia_pids_query=@();parsed_nvidia_pids_rows=@();raw_compute_query_rows=@();compute_query_pids=@();process_entries=@();wddm_pids_fallback_entries=@();gpu_utilization_rows=@();gpu_engine_counter_status='NOT_CHECKED';gpu_engine_counter_total_rows=$null;gpu_engine_counters_by_pid=@();gpu_engine_compute_counters=@();gpu_engine_compute_counters_by_pid=@();active_compute_engine_rows=@();errors=@()}
function Get-Sha256([string]$Path) {
    if(-not (Test-Path -LiteralPath $Path -PathType Leaf)){throw "Missing file: $Path"}
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Check-Hash([string]$Label,[string]$Path,[string]$Expected) {
    try { $actual=Get-Sha256 $Path; $ok=$actual -eq $Expected.ToLowerInvariant();
        $checked.Add([pscustomobject]@{label=$Label;path=$Path;expected=$Expected;actual=$actual;pass=$ok});
        if(-not $ok){$errors.Add("SHA256 mismatch: $Label ($Path)")}
    } catch {$errors.Add($_.Exception.Message)}
}
function Get-GpuProcessAudit([string]$NvidiaSmi,[object[]]$Win32Processes,[string[]]$AllowedGraphicsTypes,[string[]]$SuspiciousImagePatterns) {
    $issues=[System.Collections.Generic.List[string]]::new()
    $probe=[ordered]@{schema='ROUND2_WDDM_GPU_RESOURCE_AUDIT_V2';status='BLOCKED';driver_model='UNKNOWN';nvidia_smi_executable=$NvidiaSmi;raw_nvidia_process_rows=@();raw_nvidia_pids_query=@();parsed_nvidia_pids_rows=@();raw_compute_query_rows=@();compute_query_pids=@();process_entries=@();wddm_pids_fallback_entries=@();gpu_utilization_rows=@();gpu_engine_counter_status='NOT_CHECKED';gpu_engine_counter_total_rows=$null;gpu_engine_counters_by_pid=@();gpu_engine_compute_counters=@();gpu_engine_compute_counters_by_pid=@();active_compute_engine_rows=@();errors=@()}
    $procById=@{}
    foreach($proc in $Win32Processes){$procById[[string]$proc.ProcessId]=$proc}
    $typedEntries=[System.Collections.Generic.List[object]]::new()
    $pidsById=@{}
    try {
        $fullOutput=@(& $NvidiaSmi 2>&1|ForEach-Object {[string]$_});$fullExit=$LASTEXITCODE
        $probe.nvidia_smi_full_exit_code=$fullExit
        if($fullExit -ne 0){throw "nvidia-smi full query exited $($fullExit): $([string]::Join(' ', $fullOutput))"}
        $fullText=$fullOutput -join "`n"
        if($fullText -notmatch 'Processes:'){throw 'nvidia-smi output has no recognizable process table.'}
        if($fullText -match '\bWDDM\b'){$probe.driver_model='WDDM'}else{$issues.Add('GPU driver model is not confirmed as WDDM; process types are not trusted.')}
        $tableRows=@($fullOutput|Where-Object {$_ -match '^\|\s*\d+\s+\S+\s+\S+\s+\d+\s+\S+'})
        $probe.raw_nvidia_process_rows=$tableRows
        $rowPattern='^\|\s*(?<gpu>\d+)\s+\S+\s+\S+\s+(?<pid>\d+)\s+(?<type>\S+)\s+(?<image>.+?)\s+(?<memory>N/A|\d+\s*MiB)\s*\|$'
        foreach($line in $tableRows){
            if($line -notmatch $rowPattern){$issues.Add("Unrecognized NVIDIA process-table row: $line");continue}
            $gpuIndex=[int]$Matches.gpu;$processId=[int]$Matches.pid;$type=$Matches.type;$nvidiaImage=$Matches.image.Trim();$proc=$procById[[string]$processId]
            $imageName=if($proc){[string]$proc.Name}else{$null}
            $classification='UNKNOWN_OR_SUSPECTED_COMPUTE';$blockReason=$null
            if(-not $proc){$blockReason='PID is not present in the Win32_Process image map.';$issues.Add("Unknown GPU process PID $processId.")}
            elseif($type -eq 'C'){$classification='COMPUTE_PROCESS';$blockReason='NVIDIA type C is a compute-only process.';$issues.Add("GPU compute process detected: PID $processId ($imageName).")}
            elseif($probe.driver_model -eq 'WDDM' -and $type -in $AllowedGraphicsTypes){
                if($imageName -match ($SuspiciousImagePatterns -join '|')){$blockReason='A Python/MATLAB/Jupyter image with a GPU context is a suspected training or simulation job.';$issues.Add("Suspected GPU compute workload: PID $processId ($imageName), NVIDIA type $type.")}
                else{$classification='WDDM_GRAPHICS_CONTEXT'}
            }else{$blockReason="NVIDIA process type '$type' is not an approved WDDM graphics type.";$issues.Add("Unknown or compute-capable GPU process type for PID $($processId): $type.")}
            $typedEntries.Add([pscustomobject]@{gpu=$gpuIndex;pid=$processId;type=$type;nvidia_process_name=$nvidiaImage;image_name=$imageName;classification=$classification;blocked=[bool]$blockReason;block_reason=$blockReason;raw_row=$line.Trim()})
        }
    } catch {$issues.Add("NVIDIA process-table query failed closed: $($_.Exception.Message)")}
    $probe.process_entries=$typedEntries.ToArray()
    try {
        $pidsOutput=@(& $NvidiaSmi -q -d PIDS 2>&1|ForEach-Object {[string]$_});$pidsExit=$LASTEXITCODE
        $probe.nvidia_pids_query_exit_code=$pidsExit;$probe.raw_nvidia_pids_query=$pidsOutput
        if($pidsExit -ne 0){throw "nvidia-smi PIDS query exited $($pidsExit): $([string]::Join(' ', $pidsOutput))"}
        $pidsText=[string]::Join("`n",$pidsOutput)
        $pidsMatches=[regex]::Matches($pidsText,'(?ms)^\s*Process ID\s*:\s*(?<pid>\d+)\s*(?<body>.*?)(?=^\s*Process ID\s*:|\z)')
        $pidsHeaderCount=[regex]::Matches($pidsText,'(?im)^\s*Process ID\s*:').Count
        if($pidsHeaderCount -ne $pidsMatches.Count){$issues.Add('PIDS query contains an unparseable Process ID header or row.')}
        $parsedPids=[System.Collections.Generic.List[object]]::new()
        foreach($match in $pidsMatches){
            $body=$match.Groups['body'].Value;$typeMatch=[regex]::Match($body,'(?im)^[ \t]*Type[ \t]*:[ \t]*(?<type>\S+)');$nameMatch=[regex]::Match($body,'(?im)^[ \t]*Name[ \t]*:[ \t]*(?<name>[^\r\n]*)')
            if(-not $typeMatch.Success){$issues.Add("PIDS query row for PID $($match.Groups['pid'].Value) has unknown/missing type.");continue}
            $parsedPid=[int]$match.Groups['pid'].Value;$type=$typeMatch.Groups['type'].Value.Trim();$nvidiaName=if($nameMatch.Success){$nameMatch.Groups['name'].Value.Trim()}else{''}
            $proc=$procById[[string]$parsedPid];$imageName=if($proc){[string]$proc.Name}else{$null}
            $entry=[pscustomobject]@{pid=$parsedPid;type=$type;nvidia_process_name=$nvidiaName;image_name=$imageName;raw_block=$match.Value.Trim()}
            $parsedPids.Add($entry)
            if(-not $proc){$issues.Add("PIDS query PID $parsedPid is unknown to Win32_Process.")}
            if($type -eq 'C'){$issues.Add("PIDS query reports compute-only Type C for PID $parsedPid ($imageName).")}
            elseif($probe.driver_model -eq 'WDDM' -and $type -notin $AllowedGraphicsTypes){$issues.Add("PIDS query has unknown or unapproved type '$type' for PID $parsedPid.")}
            if($proc -and $imageName -match ($SuspiciousImagePatterns -join '|')){$issues.Add("PIDS query maps suspected compute image PID $parsedPid ($imageName), type $type.")}
            if(-not $pidsById.ContainsKey([string]$parsedPid)){$pidsById[[string]$parsedPid]=[System.Collections.Generic.List[object]]::new()};$pidsById[[string]$parsedPid].Add($entry)
        }
        if($parsedPids.Count -eq 0){$issues.Add('NVIDIA PIDS query returned no parseable process rows.')}
        $probe.parsed_nvidia_pids_rows=$parsedPids.ToArray()
        foreach($row in $typedEntries){
            $matches=@($pidsById[[string]$row.pid])
            if($matches.Count -eq 0){$issues.Add("Ordinary process-table PID $($row.pid) is absent from the PIDS table.")}
            elseif(@($matches|Where-Object {$_.type -ne $row.type}).Count -gt 0){$issues.Add("Ordinary/PIDS type cross-check differs for PID $($row.pid).")}
        }
    } catch {$issues.Add("NVIDIA PIDS query failed closed: $($_.Exception.Message)")}
    try {
        $computeOutput=@(& $NvidiaSmi --query-compute-apps=pid,process_name --format=csv,noheader,nounits 2>&1|ForEach-Object {[string]$_});$computeExit=$LASTEXITCODE
        $probe.nvidia_compute_query_exit_code=$computeExit;$probe.raw_compute_query_rows=$computeOutput
        if($computeExit -ne 0){throw "nvidia-smi compute query exited $($computeExit): $([string]::Join(' ', $computeOutput))"}
        $computePids=[System.Collections.Generic.List[int]]::new()
        foreach($line in @($computeOutput|ForEach-Object {$_.Trim()}|Where-Object {$_})){
            if($line -match '^No running processes found'){continue}
            $parts=$line -split ',',2
            if($parts.Count -ne 2 -or $parts[0].Trim() -notmatch '^\d+$'){$issues.Add("Unrecognized NVIDIA compute-query row: $line");continue}
            $processId=[int]$parts[0].Trim();$proc=$procById[[string]$processId];$typed=@($typedEntries|Where-Object {$_.pid -eq $processId})
            $computePids.Add($processId)
            if(-not $proc){$issues.Add("Compute-query PID $processId is unknown to Win32_Process.")}
            if($typed.Count -eq 0){
                $pids=@($pidsById[[string]$processId])
                if($pids.Count -ne 1){$issues.Add("Compute-query PID $processId has no ordinary process-table row and lacks one unique PIDS fallback row.");continue}
                $pidsRow=$pids[0];$imageName=if($proc){[string]$proc.Name}else{$null};$reason=$null
                if(-not $proc){$reason='No Win32 image mapping.'}
                elseif($probe.driver_model -ne 'WDDM' -or $pidsRow.type -notin $AllowedGraphicsTypes){$reason="PIDS fallback type '$($pidsRow.type)' is not an approved WDDM graphics context."}
                elseif($imageName -match ($SuspiciousImagePatterns -join '|')){$reason='PIDS fallback image is suspected compute/training/simulation.'}
                if($reason){$issues.Add("Compute-query PID $processId PIDS fallback blocked: $reason");$classification='UNKNOWN_OR_SUSPECTED_COMPUTE'}else{$classification='WDDM_GRAPHICS_CONTEXT'}
                $fallback=[pscustomobject]@{pid=$processId;type=$pidsRow.type;nvidia_process_name=$pidsRow.nvidia_process_name;image_name=$imageName;classification=$classification;source='WDDM_PIDS_FALLBACK';blocked=[bool]$reason;block_reason=$reason;per_pid_gpu_engine_counter_rows=@();per_pid_gpu_engine_counter_status='PENDING'}
                $probe.wddm_pids_fallback_entries=@($probe.wddm_pids_fallback_entries)+$fallback
                $typedEntries.Add($fallback)
            }
            elseif(@($typed|Where-Object {$_.classification -ne 'WDDM_GRAPHICS_CONTEXT'}).Count -gt 0){$issues.Add("Compute-query PID $processId is not confirmed as a WDDM graphics-only context.")}
        }
        $probe.compute_query_pids=@($computePids|Sort-Object -Unique)
    } catch {$issues.Add("NVIDIA compute-app query failed closed: $($_.Exception.Message)")}
    try {
        $utilOutput=@(& $NvidiaSmi --query-gpu=index,utilization.gpu --format=csv,noheader,nounits 2>&1|ForEach-Object {[string]$_});$utilExit=$LASTEXITCODE
        $probe.gpu_utilization_query_exit_code=$utilExit;$probe.gpu_utilization_raw_rows=$utilOutput
        if($utilExit -ne 0){throw "nvidia-smi utilization query exited $($utilExit): $([string]::Join(' ', $utilOutput))"}
        $utilRows=[System.Collections.Generic.List[object]]::new()
        foreach($line in @($utilOutput|ForEach-Object {$_.Trim()}|Where-Object {$_})){
            if($line -notmatch '^(?<gpu>\d+)\s*,\s*(?<util>\d+)\s*$'){$issues.Add("Unrecognized NVIDIA utilization row: $line");continue}
            $utilRows.Add([pscustomobject]@{gpu=[int]$Matches.gpu;utilization_percent=[int]$Matches.util})
        }
        if($utilRows.Count -eq 0){$issues.Add('NVIDIA utilization query returned no parseable GPU rows.')}
        $probe.gpu_utilization_rows=$utilRows.ToArray()
    } catch {$issues.Add("NVIDIA utilization query failed closed: $($_.Exception.Message)")}
    try {
        $engineRows=@(Get-CimInstance -ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction Stop)
        $probe.gpu_engine_counter_total_rows=$engineRows.Count
        if($engineRows.Count -eq 0){throw 'GPU engine performance-counter provider returned no rows.'}
        $computeCounters=@($engineRows|Where-Object {[string]$_.Name -match 'engtype_Compute'})
        $probe.gpu_engine_compute_counters=@($computeCounters|ForEach-Object {[pscustomobject]@{name=[string]$_.Name;utilization_percentage=$_.UtilizationPercentage}})
        $allByPid=[System.Collections.Generic.List[object]]::new()
        $active=[System.Collections.Generic.List[object]]::new()
        foreach($counter in $engineRows){
            $util=0.0
            if(-not [double]::TryParse([string]$counter.UtilizationPercentage,[ref]$util)){$issues.Add("GPU engine counter is unparseable: $($counter.Name)");continue}
            if([double]::IsNaN($util) -or [double]::IsInfinity($util) -or $util -lt 0 -or $util -gt 100){$issues.Add("GPU engine counter is nonfinite or outside [0,100]: $($counter.Name)=$($counter.UtilizationPercentage)");continue}
            $pidMatch=[regex]::Match([string]$counter.Name,'(?:^|_)pid_(?<pid>\d+)(?:_|$)')
            $allByPid.Add([pscustomobject]@{pid=if($pidMatch.Success){[int]$pidMatch.Groups['pid'].Value}else{$null};name=[string]$counter.Name;utilization_percentage=$util})
            if([string]$counter.Name -match 'engtype_Compute' -and $util -gt 0){$active.Add([pscustomobject]@{name=[string]$counter.Name;utilization_percentage=$util})}
        }
        $probe.gpu_engine_counters_by_pid=$allByPid.ToArray()
        $probe.gpu_engine_compute_counters_by_pid=@($allByPid|Where-Object {$_.name -match 'engtype_Compute'})
        foreach($fallback in @($probe.wddm_pids_fallback_entries)){
            $rows=@($allByPid|Where-Object {$_.pid -eq $fallback.pid})
            $fallback.per_pid_gpu_engine_counter_rows=$rows
            $computeRows=@($rows|Where-Object {$_.name -match 'engtype_Compute'})
            $fallback | Add-Member -NotePropertyName per_pid_gpu_compute_counter_rows -NotePropertyValue $computeRows -Force
            if($rows.Count -eq 0){$fallback.per_pid_gpu_engine_counter_status='MISSING';$issues.Add("WDDM PIDS fallback PID $($fallback.pid) has no per-PID GPU engine counters.")}
            elseif(@($computeRows|Where-Object {$_.utilization_percentage -gt 0}).Count -gt 0){$fallback.per_pid_gpu_engine_counter_status='ACTIVE_COMPUTE';$issues.Add("WDDM PIDS fallback PID $($fallback.pid) has an active per-PID Compute engine counter.")}
            else{$fallback.per_pid_gpu_engine_counter_status='NO_ACTIVE_COMPUTE'}
        }
        $probe.active_compute_engine_rows=$active.ToArray();$probe.gpu_engine_counter_status='PASS'
        if($active.Count -gt 0){$issues.Add("Active GPU compute engine counters detected ($($active.Count)).")}
    } catch {$probe.gpu_engine_counter_status='BLOCKED';$issues.Add("GPU engine compute-counter query failed closed: $($_.Exception.Message)")}
    $probe.process_entries=$typedEntries.ToArray()
    $probe.wddm_graphics_context_count=@($typedEntries|Where-Object {$_.classification -eq 'WDDM_GRAPHICS_CONTEXT'}).Count
    $probe.compute_process_count=@($typedEntries|Where-Object {$_.classification -eq 'COMPUTE_PROCESS'}).Count
    $probe.unknown_or_suspected_process_count=@($typedEntries|Where-Object {$_.classification -eq 'UNKNOWN_OR_SUSPECTED_COMPUTE'}).Count
    $probe.errors=$issues.ToArray();$probe.status=if($issues.Count -eq 0){'PASS'}else{'BLOCKED'}
    return $probe
}
try {
    if(-not $ParentReviewed){$errors.Add('A fresh parent-review marker is required; this no-marker harness run is not approval.')}
    $lock=Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json -DateKind String
    if($lock.schema -ne 'ROUND2_PCF_SCREEN_INPUTS_V1'){$errors.Add('Unexpected R2 frozen input schema.')}
    if($lock.repo_root -ne $repoRoot){$errors.Add('Repository root differs from R2 input lock.')}
    if($lock.safety.gpu_compute_jobs_must_be_zero -ne $true -or $lock.safety.gpu_unknown_pid_blocks -ne $true -or $lock.safety.gpu_engine_compute_counters_required -ne $true -or $lock.safety.gpu_wddm_pids_query_required -ne $true -or $lock.safety.gpu_compute_query_pid_pids_fallback_required -ne $true -or $lock.safety.gpu_per_pid_engine_counters_required -ne $true -or (@($lock.safety.gpu_wddm_allowed_graphics_types) -join '|') -ne 'C+G|G' -or @($lock.safety.gpu_suspected_compute_image_patterns).Count -lt 3){$errors.Add('Frozen WDDM GPU resource-audit policy is missing or changed.')}
    $deadline=[DateTimeOffset]::Parse([string]$lock.safety.global_deadline_utc).ToUniversalTime()
    if($deadline -ne [DateTimeOffset]::Parse('2026-10-24T17:01:00Z') -or [DateTimeOffset]::UtcNow -ge $deadline){$errors.Add('Fixed global deadline 2026-10-24T17:01:00Z has passed or changed.')}
    Check-Hash 'round1_input_lock' $lock.upstream_round1.lock_path $lock.upstream_round1.lock_sha256
    Check-Hash 'round1_results' $lock.upstream_round1.results_path $lock.upstream_round1.results_sha256
    Check-Hash 'round1_summary' $lock.upstream_round1.summary_path $lock.upstream_round1.summary_sha256
    foreach($entry in @(
        @{n='scene_list';p=$lock.scene_list.path;h=$lock.scene_list.sha256},
        @{n='reuse_manifest';p=$lock.reuse_manifest.path;h=$lock.reuse_manifest.sha256},
        @{n='ON_rescore';p=$lock.rescores[0].path;h=$lock.rescores[0].sha256},
        @{n='B_rescore';p=$lock.rescores[1].path;h=$lock.rescores[1].sha256},
        @{n='candidate_RAW_INDEX';p=$lock.raw_index.path;h=$lock.raw_index.sha256},
        @{n='model_binding';p=$lock.model_binding.path;h=$lock.model_binding.sha256},
        @{n='model_MAT';p=$lock.model.mat_path;h=$lock.model.mat_sha256},
        @{n='normalizer_NPZ';p=$lock.normalizer.npz_path;h=$lock.normalizer.npz_file_sha256},
        @{n='normalizer_report';p=$lock.normalizer.train_only_report_path;h=$lock.normalizer.train_only_report_sha256},
        @{n='lineage';p=$lock.lineage.path;h=$lock.lineage.sha256},
        @{n='scoring_helper';p=$lock.scoring_helper.path;h=$lock.scoring_helper.sha256},
        @{n='scene_payload_identity';p=$lock.scene_payload_identity.path;h=$lock.scene_payload_identity.sha256},
        @{n='R2_taskbook';p=$lock.taskbook.path;h=$lock.taskbook.sha256})) { Check-Hash $entry.n $entry.p $entry.h }
    foreach($e in $lock.mechanism_evidence){Check-Hash 'mechanism_evidence' $e.path $e.sha256}
    foreach($f in $lock.runtimeFiles){Check-Hash 'locked_runtime_or_config' $f.path $f.sha256}
    foreach($f in $lock.plantFiles){Check-Hash "locked_plant_$($f.name)" $f.path $f.sha256}
    foreach($f in $lock.setupFiles){Check-Hash "R2_setup_$($f.name)" $f.path $f.sha256}

    $ids=@('DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00','DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T1_C00_W07','DL1018_VAL_T3_C12_W09','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00')
    $sceneRows=@(Import-Csv -LiteralPath $lock.scene_list.path)
    if($sceneRows.Count -ne 12 -or (($sceneRows.scene_id -join '|') -ne ($ids -join '|')) -or (Compare-Object $ids @($sceneRows.scene_id)).Count -ne 0 -or (@($sceneRows.scene_id|Sort-Object -Unique)).Count -ne 12 -or @($sceneRows|Where-Object {$_.scene_id -notlike 'DL1018_VAL_*'}).Count -ne 0){$errors.Add('Scene list differs from the exact twelve VAL IDs/order.')}
    $rawRows=@(Import-Csv -LiteralPath $lock.reuse_manifest.path)
    $onScore=@(Import-Csv -LiteralPath $lock.rescores[0].path)
    $bScore=@(Import-Csv -LiteralPath $lock.rescores[1].path)
    if($rawRows.Count -ne 24 -or @($rawRows|Where-Object {$_.split -ne 'VAL'}).Count -ne 0){$errors.Add('Reuse manifest must contain exactly the 24 paired VAL raws.')}
    $evidence=@(Import-Csv -LiteralPath $lock.scene_payload_identity.path)
    if($evidence.Count -ne 12 -or (@($evidence|Where-Object {$_.status -ne 'IDENTICAL' -or [int]$_.physical_field_count -ne 14 -or [int]$_.time_samples -ne 20001 -or [double]$_.max_abs_physical_scene_diff -ne 0})).Count -ne 0){$errors.Add('Scene evidence must prove 12/12 identical payloads, 14 fields and zero difference.')}
    foreach($id in $ids){foreach($role in @('ON_CANDIDATE','B_BASELINE')){
        $pair=@($rawRows|Where-Object {$_.scene_id -eq $id -and $_.role -eq $role})
        if($pair.Count -ne 1){$errors.Add("Expected one $role raw for $id.");continue}
        $row=$pair[0]; Check-Hash "$role raw $id" $row.raw_path $row.raw_sha256
        if($role -eq 'ON_CANDIDATE'){
            $score=@($onScore|Where-Object {$_.scene_id -eq $id})
            if($row.source_index_path -ne $lock.raw_index.path -or $row.source_index_sha256 -ne $lock.raw_index.sha256 -or $score.Count -ne 1 -or $score[0].raw_path -ne $row.raw_path -or $score[0].raw_sha256_expected -ne $row.raw_sha256 -or $score[0].'rescore_matches_pair_with_1e-12_m_tolerance' -ne 'True'){$errors.Add("ON raw/rescore identity mismatch: $id")}
        } else {
            $score=@($bScore|Where-Object {$_.scene_id -eq $id})
            if($row.rescore_csv_sha256 -ne $lock.rescores[1].sha256 -or $row.source_index_sha256 -ne $lock.rescores[1].sha256 -or $row.raw_scan_helper_sha256 -ne $lock.scoring_helper.sha256 -or $score.Count -ne 1 -or $score[0].resolved_raw_path -ne $row.raw_path -or $score[0].resolved_raw_sha256_expected -ne $row.raw_sha256 -or $score[0].manifest_source_raw_path -ne $row.paired_source_raw_path -or $score[0].'rescore_matches_pair_with_1e-12_m_tolerance' -ne 'True'){$errors.Add("B raw/rescore identity mismatch: $id")}
        }
    }}
    $py=(Get-Command python -ErrorAction Stop).Source
    $vout=@(& $py (Join-Path $expDir 'verify_scene_payload_identity.py') 2>&1); $verifierExit=$LASTEXITCODE; $verifierText=[string]::Join([Environment]::NewLine,@($vout))
    if($verifierExit -ne 0){$errors.Add("Scene payload verifier failed with exit code $verifierExit.")}

    if(-not (Test-Path -LiteralPath $lock.matlab.exe -PathType Leaf)){$errors.Add('Locked MATLAB executable is missing.')}
    else {$version=(Get-Item -LiteralPath $lock.matlab.exe).VersionInfo.ProductVersion;if($version -ne $lock.matlab.product_version){$errors.Add("MATLAB version changed: $version")}}
    $matlab=@(Get-Process -Name matlab -ErrorAction SilentlyContinue)
    $allProcesses=@(Get-CimInstance Win32_Process -ErrorAction Stop)
    $python=@($allProcesses|Where-Object {$_.Name -match '^python(w)?\.exe$'}|ForEach-Object {$cmd=[string]$_.CommandLine;$cat=if($cmd -match 'solidworks-mcp|mcp_cad'){'SOLIDWORKS_MCP_CAD'}else{'OTHER_PYTHON'};[pscustomobject]@{pid=$_.ProcessId;name=$_.Name;category=$cat;command_line=$cmd}})
    if($matlab.Count -gt 0){$errors.Add("MATLAB already running ($($matlab.Count)); no new runner may start.")}
    try {$nvidiaSmi=(Get-Command nvidia-smi -CommandType Application -ErrorAction Stop).Source;$gpuProbe=Get-GpuProcessAudit -NvidiaSmi $nvidiaSmi -Win32Processes $allProcesses -AllowedGraphicsTypes $lock.safety.gpu_wddm_allowed_graphics_types -SuspiciousImagePatterns $lock.safety.gpu_suspected_compute_image_patterns}
    catch {$gpuProbe=[ordered]@{schema='ROUND2_WDDM_GPU_RESOURCE_AUDIT_V1';status='BLOCKED';errors=@($_.Exception.Message)} }
    foreach($gpuError in $gpuProbe.errors){$errors.Add("GPU audit: $gpuError")}
    if($gpuProbe.status -ne 'PASS'){$errors.Add('GPU zero-compute-job gate is not satisfied; existing processes were not stopped.')}
    $disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    if([long]$disk.FreeSpace -lt [long]$lock.safety.minimum_free_bytes){$errors.Add('C: free space is below the 30 GB threshold.')}
    $runs=Join-Path $expDir 'runs';$existingBytes=[long]0;$remainingBytes=[long]$lock.safety.estimated_cycle_output_bytes;$remainingSeconds=[long]$lock.safety.estimated_cycle_runtime_seconds;$probeStart=$null
    if(Test-Path -LiteralPath $runs){$items=@(Get-ChildItem -LiteralPath $runs -Force -Recurse);$existingBytes=[long](($items|Where-Object {-not $_.PSIsContainer}|Measure-Object Length -Sum).Sum)
        if($Mode -eq 'PROBE' -and $items.Count -gt 0){$errors.Add('PROBE refuses any existing run artifact; retries are forbidden.')}
        if($Mode -eq 'CONTINUE'){
            $id=$ids[0];$attempt=Join-Path $runs "$id\attempt_01";$statusPath=Join-Path $attempt 'run_status.json';$summaryPath=Join-Path $expDir 'reports\probe_round2.json'
            $expectedRelative=@("runs\$id","runs\$id\attempt_01","runs\$id\attempt_01\attempt_started.marker","runs\$id\attempt_01\raw_run.mat","runs\$id\attempt_01\run_start.mat","runs\$id\attempt_01\run_status.json")|Sort-Object
            $actualRelative=@($items|ForEach-Object {$_.FullName.Substring($expDir.Length+1)}|Sort-Object)
            if((Compare-Object $expectedRelative $actualRelative).Count -ne 0){$errors.Add('CONTINUE accepts only the first probe artifact set; retries or extras are forbidden.')}
            if(-not (Test-Path -LiteralPath $statusPath -PathType Leaf) -or -not (Test-Path -LiteralPath $summaryPath -PathType Leaf)){$errors.Add('CONTINUE requires a complete first-scene PROBE.')}
            else {$st=Get-Content $statusPath -Raw|ConvertFrom-Json;$sm=Get-Content $summaryPath -Raw|ConvertFrom-Json;$probeStart=[DateTimeOffset]::Parse([string]$sm.probe_started_utc).ToUniversalTime();$observedAttemptSeconds=[double]$sm.attempt_execution_and_raw_persistence_seconds;$remainingSeconds=[long][Math]::Ceiling([Math]::Max([double]$lock.safety.estimated_runtime_per_attempt_seconds,$observedAttemptSeconds)*11*1.25);$per=[long][Math]::Ceiling([Math]::Max([long]$lock.safety.estimated_bytes_per_attempt,[long]$sm.attempt_output_bytes)*1.25);$remainingBytes=$per*11
                if([double]$sm.episode_runtime_seconds -le 0 -or $observedAttemptSeconds -le 0){$errors.Add('PROBE timing summary lacks positive episode and bounded attempt-persistence durations.')}
                if($st.scene_id -ne $id -or $st.status -ne 'STABLE' -or $st.last_transition -ne 20000 -or $st.update_enabled -ne $true -or $st.head_enabled -ne $true -or $st.pcf_enabled -ne $false -or [long]$st.update_event_count -le 0 -or [double]$st.max_abs_event_weight_delta_unitless -le [double]$lock.run.weight_delta_threshold_unitless -or [double]$st.max_abs_eta_before_mps -gt [double]$lock.run.signal_tolerance_mps -or [double]$st.max_abs_eta_after_mps -gt [double]$lock.run.signal_tolerance_mps -or [double]$st.max_abs_surface_clip_error_mps -gt [double]$lock.run.signal_tolerance_mps -or $st.model_mat_sha256 -ne $lock.model.mat_sha256 -or $st.model_binding_sha256 -ne $lock.model_binding.sha256 -or $st.normalizer_npz_sha256 -ne $lock.normalizer.npz_file_sha256 -or $st.normalizer_arrays_identity_sha256 -ne $lock.normalizer.actual_runner_arrays_identity_sha256 -or $st.W0_output_W_sha256 -ne $lock.model.w0_output_W_double_f_order_sha256 -or $st.scene_payload_identity_csv_sha256 -ne $lock.scene_payload_identity.sha256 -or @($st.plant_source_sha256).Count -ne $lock.plantFiles.Count -or @($st.runtime_source_sha256).Count -ne $lock.runtimeFiles.Count -or $sm.status -ne 'PROBE_COMPLETE'){$errors.Add('PROBE identity/PCF/update/eta/clipping/safety evidence is invalid.')}
                if((Get-Sha256 (Join-Path $attempt 'raw_run.mat')) -ne [string]$st.raw_sha256){$errors.Add('PROBE raw SHA does not match run_status.')}
                if((Get-Sha256 (Join-Path $attempt 'run_start.mat')) -ne [string]$st.run_start_sha256){$errors.Add('PROBE run_start SHA does not match run_status.')}
            }
            foreach($id2 in $ids[1..11]){if(Test-Path -LiteralPath (Join-Path $runs "$id2\attempt_01")){$errors.Add("CONTINUE refuses existing/partial attempt: $id2")}}
            if($probeStart -and [DateTimeOffset]::UtcNow.AddSeconds($remainingSeconds) -gt $deadline){$errors.Add('Projected remaining runtime exceeds the fixed global deadline.')}
        }
    } elseif($Mode -eq 'CONTINUE'){$errors.Add('CONTINUE cannot run without the first-scene PROBE.')}
    if($lock.single_difference.path -ne 'opts.stage1_position_runtime.command_filter_coordination_v3_5.enabled' -or $lock.single_difference.ON -ne $true -or $lock.single_difference.OFF -ne $false){$errors.Add('Single-factor lock is invalid.')}
    if($lock.safety.minimum_free_bytes -ne 30000000000 -or $lock.safety.max_cycle_output_bytes -ne 80000000000 -or $lock.safety.estimated_cycle_output_bytes -gt $lock.safety.max_cycle_output_bytes -or $lock.run.pcf_enabled -ne $false -or $lock.run.update_enabled -ne $true){$errors.Add('Frozen option or resource budget values are invalid.')}
    if([DateTimeOffset]::UtcNow.AddSeconds($remainingSeconds) -gt $deadline){$errors.Add('Projected runtime exceeds the fixed global deadline.')}
    if($existingBytes+$remainingBytes -gt [long]$lock.safety.max_cycle_output_bytes){$errors.Add('Existing plus projected output exceeds the 80 GB cap.')}
    if([long]$disk.FreeSpace-$remainingBytes -lt [long]$lock.safety.minimum_free_bytes){$errors.Add('Projected free space violates the 30 GB refusal threshold.')}
} catch {$errors.Add($_.Exception.Message);$matlab=@();$python=@();$disk=$null}
$status=if($errors.Count -eq 0){'PASS'}else{'BLOCKED'}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath)|Out-Null
$lockSha=if(Test-Path $lockPath){Get-Sha256 $lockPath}else{$null}
$report=[ordered]@{schema='ROUND2_PCF_SCREEN_PREFLIGHT_V1';status=$status;resource_preflight_only=$true;run_authorization_granted=$false;report_path=$reportPath;mode=$Mode;parent_reviewed_switch_present=[bool]$ParentReviewed;created_utc=[DateTime]::UtcNow.ToString('o');repo_root=$repoRoot;frozen_inputs_sha256=$lockSha;checked_sha256=$checked.ToArray();checked_sha256_failure_count=@($checked|Where-Object {-not $_.pass}).Count;scene_payload_verifier_exit_code=$verifierExit;scene_payload_verifier_output=$verifierText;matlab_executable=$lock.matlab.exe;matlab_product_version=$lock.matlab.product_version;matlab_process_count=@($matlab).Count;gpu_resource_audit=$gpuProbe;python_process_categories=@($python|Group-Object category|ForEach-Object {[ordered]@{category=$_.Name;count=$_.Count}});c_free_bytes=if($disk){[long]$disk.FreeSpace}else{$null};existing_output_bytes=$existingBytes;estimated_remaining_seconds=$remainingSeconds;estimated_remaining_bytes=$remainingBytes;deadline_utc=$lock.safety.global_deadline_utc;errors=$errors.ToArray()}
$report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output "ROUND2_PREFLIGHT $status mode=$Mode checked_sha256=$($checked.Count) hash_failures=$(@($checked|Where-Object {-not $_.pass}).Count) scene_verifier_exit=$verifierExit"
$errors|ForEach-Object {Write-Output "BLOCKED: $_"}
if($status -eq 'PASS'){exit 0}else{exit 2}


