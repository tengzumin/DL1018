$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'This exact no-Plant command requires PowerShell 7.' }
$here = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_dev72_20261023'
$exitPath = Join-Path $here 'B_TRACEABLE_DEV72_PREPARE_OS_EXIT_v2.json'
$stdoutPath = Join-Path $here 'B_TRACEABLE_DEV72_PREPARE_STDOUT_v2.txt'
$resultPath = Join-Path $here 'B_TRACEABLE_DEV72_PREPARE_RESULT_v2.json'
$snapshotPath = Join-Path $here 'B_TRACEABLE_DEV72_PREPARED_CFG_OPTS_v2.mat'
$releasePath = Join-Path $here 'B_TRACEABLE_DEV72_RELEASE_v2.json'
if ((Test-Path -LiteralPath $exitPath) -or (Test-Path -LiteralPath $stdoutPath) -or
    (Test-Path -LiteralPath $resultPath) -or (Test-Path -LiteralPath $snapshotPath) -or
    (Test-Path -LiteralPath $releasePath)) {
    throw 'Preserve prior preparation evidence; do not rerun.'
}
$env:MATLAB_PREFDIR = Join-Path $here 'matlab_prefdir_dev72_prepare_v2'
New-Item -ItemType Directory -Path $env:MATLAB_PREFDIR -Force | Out-Null
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
$matlabBatch = "try; cd('$here'); result=prepare_b_traceable_dev72_v2(); fprintf('B_DEV72_PREPARED=%s; NEW_SCENES=%d; PLANT_CALLS=%d',result.status,result.new_scene_count,result.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$startedUtc = [DateTime]::UtcNow.ToString('o')
& $matlabExe -singleCompThread -wait -batch $matlabBatch *> $stdoutPath
$matlabExit = $LASTEXITCODE
$prepareStatus = $null
$snapshotSha = $null
if (Test-Path -LiteralPath $resultPath) {
    $prepareResult = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json -Depth 20
    $prepareStatus = $prepareResult.status
    if (Test-Path -LiteralPath $snapshotPath) {
        $snapshotSha = (Get-FileHash -LiteralPath $snapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$record = [ordered]@{
    schema = 'B_TRACEABLE_C3CORE_DEV72_PREPARE_OS_EXIT_V2'
    matlab_os_exit_code = $matlabExit
    started_utc = $startedUtc
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    input_lock_sha256 = if (Test-Path -LiteralPath (Join-Path $here 'B_TRACEABLE_DEV72_INPUT_LOCK_v2.json')) {
        (Get-FileHash -LiteralPath (Join-Path $here 'B_TRACEABLE_DEV72_INPUT_LOCK_v2.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { $null }
    prepare_entry_sha256 = if (Test-Path -LiteralPath (Join-Path $here 'prepare_b_traceable_dev72_v2.m')) {
        (Get-FileHash -LiteralPath (Join-Path $here 'prepare_b_traceable_dev72_v2.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { $null }
    prepare_result_status = $prepareStatus
    snapshot_sha256 = $snapshotSha
    plant_authorized = $false
    matlab_called_once = $true
}
[IO.File]::WriteAllText($exitPath,($record | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
exit $matlabExit
