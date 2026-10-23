param([Parameter(Mandatory=$true)][ValidateSet('REMAINING60')][string]$Phase)
$ErrorActionPreference = 'Stop'
$taskDir = [IO.Path]::GetDirectoryName($PSCommandPath)
$reportDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/reports/paper_continuation_20261023/c5_matched_ablation_execution/dev72'
$releasePath = Join-Path $taskDir 'C5_ABLATION_DEV72_REMAINING60_PARENT_RELEASE_v1.json'
$lockPath = Join-Path $taskDir 'C5_ABLATION_DEV72_INPUT_LOCK_v1.json'
$contractPath = Join-Path $taskDir 'C5_ABLATION_DEV72_RUN_CONTRACT_v1.json'
$bindingPath = Join-Path $taskDir 'C5_ABLATION_DEV72_SOURCE_BINDING_v1.json'
$preparePath = Join-Path $taskDir 'C5_ABLATION_DEV72_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C5_ABLATION_DEV72_PREPARED_CFG_OPTS_v1.mat'
$preflightPath = Join-Path $taskDir 'C5_ABLATION_DEV72_RUNNER_PREFLIGHT_v1.json'
$runnerPath = Join-Path $taskDir 'run_c5_matched_ablation_dev72_v1.m'
$launcherPath = $PSCommandPath
$variant = Split-Path $taskDir -Leaf
$exitPath = Join-Path $reportDir ("{0}_REMAINING60_MATLAB_OS_EXIT_v1.json" -f $variant)
$batchPath = Join-Path $taskDir 'C5_ABLATION_DEV72_REMAINING60_BATCH_STATUS_v1.json'
$bodyPath = Join-Path $taskDir 'C5_ABLATION_DEV72_REMAINING60_BODY_COMPLETE_v1.json'
$failurePath = Join-Path $taskDir 'C5_ABLATION_DEV72_RUNNER_PREFLIGHT_FAILURE_v1.json'
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'Exact parent release is required before MATLAB/Plant.' }
if (-not (Test-Path -LiteralPath $preflightPath) -or (Test-Path -LiteralPath $failurePath)) { throw 'Successful same-runner no-Plant preflight is required.' }
if ((Test-Path -LiteralPath $exitPath) -or (Test-Path -LiteralPath $batchPath) -or (Test-Path -LiteralPath $bodyPath)) { throw 'Phase output exists; preserve it and do not rerun.' }
$tokens=$null; $parseErrors=$null
[void][System.Management.Automation.Language.Parser]::ParseFile($launcherPath,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$activeMatlab=Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'"
if ($activeMatlab) { throw 'A MATLAB process is already active; do not overlap this phase.' }
$lock=Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
$contract=Get-Content -Raw -LiteralPath $contractPath | ConvertFrom-Json
$binding=Get-Content -Raw -LiteralPath $bindingPath | ConvertFrom-Json
$release=Get-Content -Raw -LiteralPath $releasePath | ConvertFrom-Json
$preflight=Get-Content -Raw -LiteralPath $preflightPath | ConvertFrom-Json
$sha = { param($Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$expectedIds=@($contract.scene_ids_remaining_60)
$required=@((Get-Content -Raw -LiteralPath (Join-Path $taskDir 'C5_ABLATION_DEV72_PARENT_RELEASE_CONTRACT_v1.json') | ConvertFrom-Json).required_fields)
if ($release.schema -ne 'C5_MATCHED_ABLATION_DEV72_PARENT_RELEASE_V1' -or -not $release.plant_authorized -or
    $release.phase -ne 'REMAINING60' -or $release.variant_id -ne $lock.variant_id -or
    $release.max_new_Plant -ne 60 -or @($release.scene_ids_remaining_60).Count -ne 60 -or
    $release.runner_sha256 -ne (& $sha $runnerPath) -or $release.launcher_sha256 -ne (& $sha $launcherPath) -or
    $preflight.status -ne 'PREFLIGHT_COMPLETE_C5_MATCHED_ABLATION_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V1' -or
    $release.runner_preflight_sha256 -ne (& $sha $preflightPath) -or
    $release.input_lock_sha256 -ne (& $sha $lockPath) -or $release.run_contract_sha256 -ne (& $sha $contractPath) -or
    $release.source_binding_sha256 -ne (& $sha $bindingPath) -or
    $release.prepare_result_sha256 -ne (& $sha $preparePath) -or
    $release.snapshot_sha256 -ne (& $sha $snapshotPath) -or
    $release.reuse12_binding_sha256 -ne $binding.reuse12_binding_sha256 -or
    $release.reuse12_parent_screen_audit_sha256 -ne $lock.upstream_refs.c5_freeze_screen12_parent_audit.sha256 -and $lock.variant_id -eq 'C5_FREEZE_TRAINED_W0' -or
    $release.reuse12_parent_screen_audit_sha256 -ne $lock.upstream_refs.c5_no_pred_screen12_parent_audit.sha256 -and $lock.variant_id -eq 'C5_NO_DELAYED_PREDICTION' -or
    (Compare-Object $expectedIds @($release.scene_ids_remaining_60) -SyncWindow 0)) { throw 'Release/source/preflight identity mismatch.' }
foreach ($name in $required) { if (-not ($release.PSObject.Properties.Name -contains $name)) { throw "Release lacks required field: $name" } }
$reserve=[int64]$contract.limits.per_scene_output_reserve_bytes
$rootPath=[IO.Path]::GetPathRoot($taskDir); $drive=[IO.DriveInfo]::new($rootPath)
if ($drive.AvailableFreeSpace - $reserve*60 -lt [int64]$contract.limits.minimum_free_bytes) { throw 'Reserve-adjusted free-space floor failed.' }
$deadline=[DateTime]::Parse($contract.limits.deadline_utc).ToUniversalTime()
if ($deadline -lt [DateTime]::UtcNow.AddSeconds(180*60+600)) { throw 'Frozen deadline guard failed.' }
$matlabExe='C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
if (-not (Test-Path -LiteralPath $matlabExe)) { throw 'Locked MATLAB executable is missing.' }
$prefDir=Join-Path $taskDir 'matlab_prefdir_remaining60_v1'
if (-not (Test-Path -LiteralPath $prefDir)) { New-Item -ItemType Directory -Path $prefDir | Out-Null }
$env:MATLAB_PREFDIR=$prefDir
$matlabMode='PARENT_APPROVED_C5_ABLATION_REMAINING60_V1'
& $matlabExe -singleCompThread -wait -batch "try; cd('$($taskDir.Replace('\','/'))'); run_c5_matched_ablation_dev72_v1('$matlabMode'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
$matlabOsExitCode=$LASTEXITCODE
$exitRecord=[ordered]@{schema='C5_MATCHED_ABLATION_DEV72_MATLAB_OS_EXIT_V1';variant_id=$lock.variant_id;phase=$Phase
    matlab_os_exit_code=$matlabOsExitCode;completed_utc=[DateTime]::UtcNow.ToString('o')
    exact_mode=$matlabMode;command_file=$launcherPath;command_sha256=& $sha $launcherPath
    release_sha256=& $sha $releasePath;runner_sha256=& $sha $runnerPath;preflight_sha256=& $sha $preflightPath
    plant_authorized=[bool]$release.plant_authorized;matlab_prefdir=$prefDir}
[IO.Directory]::CreateDirectory($reportDir) | Out-Null
[IO.File]::WriteAllText($exitPath,($exitRecord | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
Write-Output ("MATLAB_OS_EXIT_CODE={0}; PHASE={1}; MODE={2}" -f $matlabOsExitCode,$Phase,$matlabMode)
exit $matlabOsExitCode
