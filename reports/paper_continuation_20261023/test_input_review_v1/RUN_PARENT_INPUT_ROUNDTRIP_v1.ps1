$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$result = Join-Path $PSScriptRoot 'PARENT_TEST_INPUT_LOAD_ROUNDTRIP_v1.json'
$receipt = Join-Path $PSScriptRoot 'PARENT_INPUT_ROUNDTRIP_OS_EXIT_v1.json'
$stdout = Join-Path $PSScriptRoot 'roundtrip.stdout.log'
$stderr = Join-Path $PSScriptRoot 'roundtrip.stderr.log'
$prefdir = Join-Path $PSScriptRoot 'matlab_prefdir_roundtrip_v1'
foreach ($p in @($result,$receipt,$stdout,$stderr,$prefdir)) {
    if (Test-Path -LiteralPath $p) { throw "Preserve existing output: $p" }
}
$freezeReceipt = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v3/TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json') | ConvertFrom-Json
if ($freezeReceipt.matlab_os_exit_code -ne 0 -or -not $freezeReceipt.natural_wait_used) { throw 'Actual freeze natural OS0 required.' }
if (Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'") { throw 'A MATLAB process is running; do not overlap.' }
New-Item -ItemType Directory -Path $prefdir | Out-Null
$env:MATLAB_PREFDIR = $prefdir
$matlabRoot = $repoRoot.Replace('\','/').Replace("'","''")
$expr = "try; cd('$matlabRoot'); addpath('reports/paper_continuation_20261023/test_input_review_v1'); check_test_input_load_roundtrip_v1(); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$started = [DateTime]::UtcNow.ToString('o')
$proc = Start-Process -FilePath 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -ArgumentList ('-singleCompThread -wait -batch "'+$expr+'"') -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
while (-not $proc.WaitForExit(5000)) { }
$proc.Refresh()
$body = [ordered]@{
    schema='ROOT_TEST_INPUT_LOAD_ROUNDTRIP_OS_EXIT_V1'; matlab_os_exit_code=[int]$proc.ExitCode
    natural_wait_used=$true; pid=$proc.Id; started_utc=$started; completed_utc=[DateTime]::UtcNow.ToString('o')
    TEST_accessed=$true; TEST_outcomes_accessed=$false; Plant_calls=0; scene_generation_calls=0; training_steps=0
    checker_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'check_test_input_load_roundtrip_v1.m') -Algorithm SHA256).Hash.ToLowerInvariant()
    launcher_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    stdout_path=$stdout; stdout_sha256=(Get-FileHash -LiteralPath $stdout -Algorithm SHA256).Hash.ToLowerInvariant()
    stderr_path=$stderr; stderr_sha256=(Get-FileHash -LiteralPath $stderr -Algorithm SHA256).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText($receipt,($body|ConvertTo-Json -Depth 6)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
if ($proc.ExitCode -ne 0) { throw 'Read-only roundtrip failed; preserve receipt and logs.' }
if (-not (Test-Path -LiteralPath $result -PathType Leaf)) { throw 'OS0 without roundtrip result.' }
Write-Output 'ROOT_INPUT_ROUNDTRIP_NATURAL_OS0'
