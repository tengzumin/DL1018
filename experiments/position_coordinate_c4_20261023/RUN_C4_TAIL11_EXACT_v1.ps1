$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'
$taskDir = Join-Path $taskRoot 'experiments/position_coordinate_c4_20261023'
$bindingPath = Join-Path $taskDir 'C4_TAIL11_SOURCE_BINDING_v1.json'
$releaseContractPath = Join-Path $taskDir 'C4_TAIL11_PARENT_RELEASE_CONTRACT_v1.json'
$releasePath = Join-Path $taskDir 'C4_TAIL11_RELEASE_v1.json'
$batchPath = Join-Path $taskDir 'C4_TAIL11_BATCH_STATUS_v1.json'
$bodyPath = Join-Path $taskDir 'C4_TAIL11_BODY_COMPLETE_v1.json'
$exitPath = Join-Path $taskDir 'C4_TAIL11_OS_EXIT_v1.json'
$runnerPath = Join-Path $taskDir 'run_c4_tail11_v3.m'
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior tail11 exit record; do not rerun.' }
if ((Test-Path -LiteralPath $batchPath) -or (Test-Path -LiteralPath $bodyPath)) { throw 'Tail11 batch output exists; preserve it and do not rerun.' }
$parseTokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
if (-not ((Test-Path -LiteralPath $bindingPath) -and (Test-Path -LiteralPath $releaseContractPath) -and (Test-Path -LiteralPath $releasePath))) { throw 'Tail11 source binding and separate parent release are required.' }
$binding = Get-Content -LiteralPath $bindingPath -Raw | ConvertFrom-Json
$releaseContract = Get-Content -LiteralPath $releaseContractPath -Raw | ConvertFrom-Json
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$runnerSha = (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$bindingSha = (Get-FileHash -LiteralPath $bindingPath -Algorithm SHA256).Hash.ToLowerInvariant()
$launcherSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($release.schema -ne 'C4_TAIL11_PARENT_RELEASE_V1' -or $release.state -ne 'APPROVED_C4_TAIL11_V1' -or -not $release.plant_authorized -or -not $release.subsequent_11_flights_authorized -or $release.max_new_Plant -ne 11) { throw 'Exact parent approval for the remaining eleven scenes is required.' }
if ($release.tail_runner_sha256 -ne $runnerSha -or $release.tail_source_binding_sha256 -ne $bindingSha -or $release.launcher_sha256 -ne $launcherSha -or $release.parent_release_contract_sha256 -ne (Get-FileHash -LiteralPath $releaseContractPath -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Tail release does not bind the exact runner, source binding, launcher and release contract.' }
if ($binding.schema -ne 'C4_TAIL11_SOURCE_BINDING_V1' -or $releaseContract.schema -ne 'C4_TAIL11_PARENT_RELEASE_CONTRACT_V1') { throw 'Tail11 source binding or release contract schema mismatch.' }
$existingMatlab = Get-Process -Name MATLAB -ErrorAction SilentlyContinue
if ($existingMatlab) { throw 'A MATLAB process is already running; do not interrupt it or start a second heavy job.' }
$env:MATLAB_PREFDIR = Join-Path $taskDir 'matlab_prefdir_tail11_v1'
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'); batch=run_c4_tail11_v3('PARENT_APPROVED_C4_TAIL11_V1'); fid=fopen('C4_TAIL11_BODY_COMPLETE_v1.json','w'); assert(fid>=0); fwrite(fid,jsonencode(struct('status',batch.status,'completed_scenes',batch.completed_scenes,'plant_calls',batch.plant_calls,'source_binding_sha256',batch.source_binding_sha256)),'char'); fclose(fid); fprintf('C4_TAIL11_COMPLETE=%s SCENES=%d PLANT_CALLS=%d\n',batch.status,batch.completed_scenes,batch.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$batchStatus = $null
$completedScenes = 0
$plantCalls = 0
if (Test-Path -LiteralPath $batchPath) {
    $batchStatus = Get-Content -LiteralPath $batchPath -Raw | ConvertFrom-Json
    $completedScenes = $batchStatus.completed_scenes
    $plantCalls = $batchStatus.plant_calls
}
$bodyStatus = $null
if (Test-Path -LiteralPath $bodyPath) { $bodyStatus = (Get-Content -LiteralPath $bodyPath -Raw | ConvertFrom-Json).status }
$exitRecord = [ordered]@{
    schema = 'C4_TAIL11_OS_EXIT_V1'
    matlab_os_exit_code = $matlabOsExitCode
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    source_binding_sha256 = (Get-FileHash -LiteralPath $bindingPath -Algorithm SHA256).Hash.ToLowerInvariant()
    runner_sha256 = (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    parent_release_sha256 = (Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    batch_status = $batchStatus.status
    completed_scenes = $completedScenes
    plant_calls = $plantCalls
    body_status = $bodyStatus
    plant_authorized = [bool]$release.plant_authorized
    matlab_called_once = $true
}
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; BATCH={1}; SCENES={2}; PLANT_CALLS={3}" -f $matlabOsExitCode, $batchStatus.status, $completedScenes, $plantCalls)
exit $matlabOsExitCode
