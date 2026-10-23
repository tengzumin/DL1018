$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'This exact batch command requires PowerShell 7.' }
$here = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023'
$releasePath = Join-Path $here 'B_TRACEABLE_DEV72_RELEASE_v3.json'
$exitPath = Join-Path $here 'B_TRACEABLE_DEV72_BATCH_OS_EXIT_v3.json'
$stdoutPath = Join-Path $here 'B_TRACEABLE_DEV72_BATCH_STDOUT_v3.txt'
$bodyPath = Join-Path $here 'B_TRACEABLE_DEV72_BODY_COMPLETE_v3.json'
$attemptRoot = Join-Path $here 'runs_b'
if (!(Test-Path -LiteralPath $releasePath -PathType Leaf)) { throw 'Parent-signed 71-scene release is required; no Plant started.' }
if ((Test-Path -LiteralPath $exitPath) -or (Test-Path -LiteralPath $stdoutPath) -or
    (Test-Path -LiteralPath $bodyPath) -or (Test-Path -LiteralPath $attemptRoot)) {
    throw 'Preserve prior batch evidence; no retry or overwrite.'
}
$env:MATLAB_PREFDIR = Join-Path $here 'matlab_prefdir_dev72_run_v3'
New-Item -ItemType Directory -Path $env:MATLAB_PREFDIR -Force | Out-Null
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
$matlabBatch = "try; cd('$here'); batchResult=run_b_traceable_dev72_v3('PARENT_APPROVED_B_TRACEABLE_DEV72_V3'); fid=fopen('B_TRACEABLE_DEV72_BODY_COMPLETE_v3.json','w'); assert(fid>=0); fwrite(fid,jsonencode(batchResult),'char'); fclose(fid); fprintf('B_DEV72_BATCH_COMPLETE=%s; SCENES=%d; PLANT_CALLS=%d',batchResult.status,batchResult.completed_scene_count,batchResult.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$startedUtc = [DateTime]::UtcNow.ToString('o')
& $matlabExe -singleCompThread -wait -batch $matlabBatch *> $stdoutPath
$matlabExit = $LASTEXITCODE
$commandSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$attemptExitRefs = @()
if (Test-Path -LiteralPath $attemptRoot -PathType Container) {
    $attemptDirs = Get-ChildItem -LiteralPath $attemptRoot -Directory -Recurse -Filter 'attempt_01'
    foreach ($attempt in $attemptDirs) {
        $marker = Join-Path $attempt.FullName 'attempt_started.marker'
        if (!(Test-Path -LiteralPath $marker -PathType Leaf)) { continue }
        $sceneId = Split-Path (Split-Path (Split-Path $attempt.FullName -Parent) -Parent) -Leaf
        $statusPath = Join-Path $attempt.FullName 'run_status.json'
        $runStartPath = Join-Path $attempt.FullName 'run_start.mat'
        $rawPath = Join-Path $attempt.FullName 'raw_run.mat'
        $firstPlantPath = Join-Path $attempt.FullName 'first_plant_step.marker'
        $statusSha = $null
        $rawSha = $null
        $statusLabel = $null
        if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
            $statusSha = (Get-FileHash -LiteralPath $statusPath -Algorithm SHA256).Hash.ToLowerInvariant()
            $statusObject = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json -Depth 20
            $statusLabel = $statusObject.status
            if ($statusObject.raw_sha256) { $rawSha = $statusObject.raw_sha256 }
            elseif ($statusObject.partial_raw_sha256) { $rawSha = $statusObject.partial_raw_sha256 }
        }
        $attemptExitPath = Join-Path $attempt.FullName 'B_TRACEABLE_OS_EXIT.json'
        if (Test-Path -LiteralPath $attemptExitPath) { throw "Preserve existing per-scene OS exit: $sceneId" }
        $attemptExit = [ordered]@{
            schema = 'B_TRACEABLE_C3CORE_DEV72_SCENE_OS_EXIT_V3'
            exit_scope = 'SHARED_BATCH_PROCESS_NOT_INDIVIDUAL_SCENE_PROCESS'
            batch_id = 'B_TRACEABLE_C3CORE_DEV72_20261023'
            scene_id = $sceneId
            matlab_os_exit_code = $matlabExit
            completed_utc = [DateTime]::UtcNow.ToString('o')
            command_file = $PSCommandPath
            command_sha256 = $commandSha
            status_path = if (Test-Path -LiteralPath $statusPath) { $statusPath } else { $null }
            status_sha256 = $statusSha
            run_status = $statusLabel
            raw_path = if (Test-Path -LiteralPath $rawPath) { $rawPath } else { $null }
            raw_sha256_from_status = $rawSha
            run_start_path = if (Test-Path -LiteralPath $runStartPath) { $runStartPath } else { $null }
            run_start_sha256 = if (Test-Path -LiteralPath $runStartPath) {
                (Get-FileHash -LiteralPath $runStartPath -Algorithm SHA256).Hash.ToLowerInvariant()
            } else { $null }
            attempt_started_marker_path = $marker
            attempt_started_marker_sha256 = (Get-FileHash -LiteralPath $marker -Algorithm SHA256).Hash.ToLowerInvariant()
            first_plant_step_marker_path = if (Test-Path -LiteralPath $firstPlantPath) { $firstPlantPath } else { $null }
            first_plant_step_marker_sha256 = if (Test-Path -LiteralPath $firstPlantPath) {
                (Get-FileHash -LiteralPath $firstPlantPath -Algorithm SHA256).Hash.ToLowerInvariant()
            } else { $null }
        }
        [IO.File]::WriteAllText($attemptExitPath,($attemptExit | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
        $attemptExitRefs += [ordered]@{
            scene_id = $sceneId
            path = $attemptExitPath
            sha256 = (Get-FileHash -LiteralPath $attemptExitPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$bodyStatus = $null
$completedScenes = 0
if (Test-Path -LiteralPath $bodyPath -PathType Leaf) {
    $body = Get-Content -LiteralPath $bodyPath -Raw | ConvertFrom-Json -Depth 20
    $bodyStatus = $body.status
    $completedScenes = [int]$body.completed_scene_count
}
$batchRecord = [ordered]@{
    schema = 'B_TRACEABLE_C3CORE_DEV72_BATCH_OS_EXIT_V3'
    batch_id = 'B_TRACEABLE_C3CORE_DEV72_20261023'
    exit_scope = 'SHARED_BATCH_PROCESS'
    matlab_os_exit_code = $matlabExit
    started_utc = $startedUtc
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = $commandSha
    release_sha256 = (Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    body_complete_status = $bodyStatus
    completed_scene_count = $completedScenes
    attempted_scene_count = $attemptExitRefs.Count
    scene_os_exit_records = $attemptExitRefs
    plant_authorized_by_command = $true
}
[IO.File]::WriteAllText($exitPath,($batchRecord | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
exit $matlabExit
