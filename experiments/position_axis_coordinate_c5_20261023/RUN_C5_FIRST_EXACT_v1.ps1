$ErrorActionPreference = 'Stop'
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023'
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c5_axis_coordinate_execution'
$exitPath = Join-Path $reportDir 'C5_FIRST_SCENE_MATLAB_OS_EXIT_v1.json'
$releasePath = Join-Path $taskDir 'C5_FIRST_PARENT_RELEASE_v1.json'
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'Parent first-scene release is required.' }
if (Test-Path -LiteralPath $exitPath) { throw 'Preserve prior first-scene exit record; no retry.' }
$parseTokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
& $matlabExe -singleCompThread -wait -batch "try; cd('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023'); run_c5_axis_coordinate_v1('PARENT_APPROVED_C5_FIRST_V1'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode = $LASTEXITCODE
$exitRecord = [ordered]@{ schema='C5_FIRST_SCENE_OS_EXIT_V1'; matlab_os_exit_code=$matlabOsExitCode; completed_utc=[DateTime]::UtcNow.ToString('o'); command_file=$PSCommandPath; command_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant(); release_sha256=(Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant(); plant_authorized=$true; one_scene_only=$true }
[IO.File]::WriteAllText($exitPath, ($exitRecord | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}" -f $matlabOsExitCode)
exit $matlabOsExitCode
