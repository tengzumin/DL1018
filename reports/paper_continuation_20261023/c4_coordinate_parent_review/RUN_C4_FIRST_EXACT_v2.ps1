$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'
$taskRunDir = Join-Path $taskRoot 'experiments/position_coordinate_c4_20261023'
$taskReleasePath = Join-Path $taskRunDir 'C4_RELEASE_v2.json'
$taskExitPath = Join-Path $taskRunDir 'C4_FIRST_RUN_OS_EXIT_v2.json'
if (Test-Path -LiteralPath $taskExitPath) { throw 'Preserve prior execution exit record; do not rerun.' }
$taskRelease = Get-Content -LiteralPath $taskReleasePath -Raw | ConvertFrom-Json
if ($taskRelease.state -ne 'APPROVED_C4_FIRST_SCENE_V2' -or $taskRelease.max_new_Plant -ne 1) { throw 'Wrong release scope.' }
foreach ($taskRef in $taskRelease.validation_and_comparator_refs) {
    if ((Get-FileHash -LiteralPath $taskRef.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskRef.sha256) {
        throw "Parent-reviewed validation/comparator identity changed: $($taskRef.path)"
    }
}
$env:MATLAB_PREFDIR = Join-Path $taskRunDir 'matlab_prefdir_first_v2'
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_coordinate_c4_20261023'); result=run_c4_coordinate_v2('PARENT_APPROVED_C4_FIRST_V2'); fid=fopen('C4_FIRST_BODY_COMPLETE_v2.json','w'); assert(fid>=0); fwrite(fid,jsonencode(struct('status',result.status,'plant_calls',result.plant_calls,'raw_sha256',result.raw_sha256,'body_completed',true)),'char'); fclose(fid); fprintf('C4_FIRST_RUN_COMPLETE=%s PLANT_CALLS=%d\n',result.status,result.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$taskMatlabExit = $LASTEXITCODE
$taskExitRecord = [ordered]@{
    schema = 'C4_FIRST_OS_EXIT_V2'
    exit_code = $taskMatlabExit
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText($taskExitPath, ($taskExitRecord | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
exit $taskMatlabExit
