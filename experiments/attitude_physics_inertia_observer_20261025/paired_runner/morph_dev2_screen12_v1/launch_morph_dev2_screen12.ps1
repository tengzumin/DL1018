param([Parameter(Mandatory=$true)][string]$ReleasePath,[Parameter(Mandatory=$true)][string]$ReleaseSha256)
Set-StrictMode -Version Latest;$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'PowerShell 7 required.'}
$entry=$PSScriptRoot;$matlab='C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$sha={param($p)(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$ReleasePath=(Resolve-Path -LiteralPath $ReleasePath).Path;$ReleaseSha256=$ReleaseSha256.ToLowerInvariant()
if((&$sha $ReleasePath) -ne $ReleaseSha256){throw 'Root release SHA mismatch.'}
$r=Get-Content -Raw -LiteralPath $ReleasePath|ConvertFrom-Json
$ids='DL1018_VAL_T1_C00_W07,DL1018_VAL_T1_C02_W09,DL1018_VAL_T1_C05_W12,DL1018_VAL_T1_C08_W15,DL1018_VAL_T2_C00_W10,DL1018_VAL_T2_C02_W12,DL1018_VAL_T2_C05_W15,DL1018_VAL_T2_C06_W00,DL1018_VAL_T3_C00_W13,DL1018_VAL_T3_C02_W15,DL1018_VAL_T3_C03_W00,DL1018_VAL_T3_C12_W09'
if($r.schema -ne 'PAIRED_MORPH_DEV2_SCREEN12_ROOT_RELEASE_V1' -or $r.approved -ne $true -or $r.scope -ne 'MORPH_DEV2_SCREEN12' -or $r.max_runner_calls -ne 24 -or $r.max_transitions -ne 480000 -or $r.max_new_bytes -ne 10737418240 -or $r.minimum_free_bytes -ne 32212254720 -or $r.training_authorized -ne $false -or $r.TEST_authorized -ne $false -or $r.retry_authorized -ne $false -or (@($r.scene_ids) -join ',') -ne $ids -or (@($r.arm_order) -join ',') -ne 'baseline,candidate'){throw 'Release does not approve exactly the 12 fixed VAL scenes.'}
$lockPath=(Resolve-Path -LiteralPath $r.source_lock_path).Path;if((&$sha $lockPath) -ne ([string]$r.source_lock_sha256).ToLowerInvariant()){throw 'Source lock SHA mismatch.'};$lock=Get-Content -Raw -LiteralPath $lockPath|ConvertFrom-Json
if($lock.schema -ne 'SOURCE_LOCK_MORPH_DEV2_SCREEN12_V1' -or $lock.status -ne 'FROZEN_INPUTS' -or $lock.executed -ne $false -or $lock.closed_loop_runs_authorized -ne $false -or $lock.manifest.sha256 -ne $r.manifest_sha256 -or @($lock.sources).Count -ne 39 -or @($lock.inputs).Count -ne 17){throw 'Frozen screen12 lock mismatch.'}
foreach($f in @($lock.sources)+@($lock.inputs)+@($lock.wrapper,$lock.launcher,$lock.checker,$lock.taskbook,$lock.state)){if((&$sha ([string]$f.path)) -ne ([string]$f.sha256).ToLowerInvariant()){throw "Input SHA mismatch: $($f.path)"}}
if((&$sha $matlab) -ne '6dc32276086121e44edf4846f033066ba5b0fae9bad002d8917a411e0a59afa9'){throw 'MATLAB executable SHA mismatch.'}
$attemptId=[string]$r.attempt_id;if($attemptId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'){throw 'Invalid attempt_id.'}
$attempt=Join-Path $entry (Join-Path 'attempts' $attemptId);if(Test-Path -LiteralPath $attempt){throw 'Attempt directory already exists.'};New-Item -ItemType Directory -Path $attempt -Force|Out-Null
$cmd="addpath('$($entry.Replace('\','/'))'); run_morph_dev2_screen12('$($ReleasePath.Replace('\','/'))','$ReleaseSha256','$($attempt.Replace('\','/'))');"
& $matlab -batch $cmd *> (Join-Path $attempt 'matlab_console.log');$exit=$LASTEXITCODE
if($exit -ne 0){throw "MATLAB runner failed with exit code $exit. Review batch_status.json and matlab_console.log."}