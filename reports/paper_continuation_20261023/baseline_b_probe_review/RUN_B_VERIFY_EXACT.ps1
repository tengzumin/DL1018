$ErrorActionPreference = 'Stop'
$env:MATLAB_PREFDIR = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023/matlab_prefdir_v2'
$taskExitPath = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023/B_TRACEABLE_VERIFY_EXIT_v2.json'
if (Test-Path -LiteralPath $taskExitPath) { throw 'Preserve existing verification exit record.' }
if (Test-Path -LiteralPath 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023/B_TRACEABLE_VERIFY_RESULT_v2.json') { throw 'Verification result already exists; do not rerun.' }
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/b_traceable_c3core_20261023'); result=verify_b_traceable_probe_v2(); fprintf('B_TRACEABLE_VERIFY_COMPLETE=%s\n',result.status); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$taskMatlabExit = $LASTEXITCODE
$taskExitRecord = [ordered]@{
    schema = 'B_TRACEABLE_READONLY_VERIFY_OS_EXIT_V1'
    exit_code = $taskMatlabExit
    completed_utc = [DateTime]::UtcNow.ToString('o')
    command_file = $PSCommandPath
    command_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    verification_only = $true
    Plant_authorized = $false
}
[IO.File]::WriteAllText($taskExitPath, ($taskExitRecord | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
exit $taskMatlabExit
