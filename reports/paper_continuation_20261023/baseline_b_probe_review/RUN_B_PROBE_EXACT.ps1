$ErrorActionPreference = 'Stop'
$env:MATLAB_PREFDIR = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023/matlab_prefdir_v2'
$taskExitPath = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023/B_TRACEABLE_RUN_EXIT_v2.json'
if (Test-Path -LiteralPath $taskExitPath) { throw 'Preserve prior execution exit record; do not rerun.' }
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023'); result=run_b_traceable_probe_v2('PARENT_APPROVED_B_PROBE_V2'); fid=fopen('B_TRACEABLE_BODY_COMPLETE_v2.json','w'); assert(fid>=0); fwrite(fid,jsonencode(struct('status',result.status,'plant_calls',result.plant_calls,'raw_sha256',result.raw_sha256,'body_completed',true)),'char'); fclose(fid); fprintf('B_TRACEABLE_RUN_COMPLETE=%s PLANT_CALLS=%d\n',result.status,result.plant_calls); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$taskMatlabExit = $LASTEXITCODE
$taskExitRecord = [ordered]@{
    schema = 'B_TRACEABLE_PROBE_OS_EXIT_V1'
    exit_code = $taskMatlabExit
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText($taskExitPath, ($taskExitRecord | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
exit $taskMatlabExit
