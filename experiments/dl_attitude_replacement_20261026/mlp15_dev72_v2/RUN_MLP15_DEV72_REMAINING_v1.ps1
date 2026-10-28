$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 is required." }

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$StudyRoot = $PSScriptRoot
$RunRoot = Join-Path $StudyRoot 'runs'
$LogsRoot = Join-Path $StudyRoot 'logs'
$ManifestPath = Join-Path $StudyRoot 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'
$ReleasePath = Join-Path $StudyRoot 'MLP15_DEV72_RELEASE_v1.json'
$AuditPath = Join-Path $StudyRoot 'audits\MLP15_DEV72_FIRST_SCENE_AUDIT_v1.json'
$ProgressPath = Join-Path $StudyRoot 'MLP15_DEV72_EXECUTION_PROGRESS_v1.json'
$PrefDir = Join-Path $StudyRoot 'matlab_prefdir_run_v1'
$Matlab = 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe'
$FirstScene = 'DL1018_DEV_T1_C00_W03'
$ExpectedFirstRawHash = 'dcbde2d0ded11673b1c8ba2dc9f1c18ad2d2db50273156124cbf9733ddaab1d3'

$Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$Release = Get-Content -Raw -LiteralPath $ReleasePath | ConvertFrom-Json
$FirstAudit = Get-Content -Raw -LiteralPath $AuditPath | ConvertFrom-Json
if ($Manifest.status -ne 'PASS_NO_PLANT_REUSE' -or $Manifest.scene_count -ne 72) { throw 'Payload manifest gate failed.' }
if ($Release.status -ne 'RELEASED' -or $Release.plant_calls_authorized -ne 72) { throw 'Release gate failed.' }
if ($FirstAudit.status -ne 'PASS_ENGINEERING_GATE' -or $FirstAudit.candidate_raw_sha256 -ne $ExpectedFirstRawHash) { throw 'First scene engineering gate failed.' }

$FirstStatusPath = Join-Path $RunRoot "$FirstScene\attempt_01\run_status.json"
$FirstStatus = Get-Content -Raw -LiteralPath $FirstStatusPath | ConvertFrom-Json
if ($FirstStatus.state -ne 'COMPLETED' -or $FirstStatus.raw_sha256 -ne $ExpectedFirstRawHash) { throw 'First scene run receipt is invalid.' }
$FirstMarkerCount = @(Get-ChildItem -LiteralPath $RunRoot -Recurse -File -Filter 'attempt_started.marker').Count
if ($FirstMarkerCount -ne 1) { throw "Expected exactly one attempt marker before continuing; found $FirstMarkerCount." }

New-Item -ItemType Directory -Force -Path $LogsRoot,$PrefDir | Out-Null
$Records = @($Manifest.records | Sort-Object scene_id | Where-Object { $_.scene_id -ne $FirstScene })
if ($Records.Count -ne 71) { throw "Expected 71 remaining scenes; found $($Records.Count)." }

$CompletedIds = [System.Collections.Generic.List[string]]::new()
$CompletedIds.Add($FirstScene)
$Progress = [ordered]@{
  schema = 'DL1018_MLP15_DEV72_EXECUTION_PROGRESS_V1'
  status = 'RUNNING'
  total_scenes = 72
  completed_scenes = 1
  pending_scenes = 71
  plant_calls_started = 1
  first_scene_id = $FirstScene
  first_scene_engineering_audit_sha256 = (Get-FileHash -LiteralPath $AuditPath -Algorithm SHA256).Hash.ToLowerInvariant()
  scoring_rule_sha256 = (Get-FileHash -LiteralPath (Join-Path $StudyRoot 'MLP15_DEV72_SCORING_RULE_v1.md') -Algorithm SHA256).Hash.ToLowerInvariant()
  release_sha256 = (Get-FileHash -LiteralPath $ReleasePath -Algorithm SHA256).Hash.ToLowerInvariant()
  started_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  last_completed_scene_id = $FirstScene
  active_scene_id = ''
  completed_scene_ids = @($CompletedIds)
  test_data_read = $false
}
[IO.File]::WriteAllText($ProgressPath,($Progress | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

foreach ($Record in $Records) {
  $SceneId = [string]$Record.scene_id
  $AttemptDir = Join-Path $RunRoot "$SceneId\attempt_01"
  if (Test-Path -LiteralPath $AttemptDir) { throw "Attempt output already exists for $SceneId." }

  $ActiveMatlab = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^MATLAB\.exe$' })
  if ($ActiveMatlab.Count -ne 0) { throw "Another MATLAB process is active before $SceneId; stopping without interrupting it." }
  $FreeGiB = [math]::Round((Get-PSDrive -Name C).Free / 1GB, 2)
  if ($FreeGiB -lt 30) { throw "Free disk is below 30 GiB before $SceneId." }

  $Markers = @(Get-ChildItem -LiteralPath $RunRoot -Recurse -File -Filter 'attempt_started.marker')
  if ($Markers.Count -ne $CompletedIds.Count) { throw "Marker count mismatch before $SceneId." }
  $PayloadHash = (Get-FileHash -LiteralPath $Record.payload_path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($PayloadHash -ne [string]$Record.payload_sha256) { throw "Payload hash mismatch for $SceneId." }

  $Progress.active_scene_id = $SceneId
  $Progress.plant_calls_started = $Markers.Count + 1
  $Progress.completed_scene_ids = @($CompletedIds)
  [IO.File]::WriteAllText($ProgressPath,($Progress | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))

  $Runtime = Join-Path $StudyRoot 'candidate_runner_work\matlab\runtime'
  $Payload = (Resolve-Path -LiteralPath $Record.payload_path).Path
  $MatlabCommand = "cd('$($ProjectRoot.Replace('\','/'))'); addpath('$($Runtime.Replace('\','/'))'); run_mlp15_dev72_attempt('$($Payload.Replace('\','/'))','$($AttemptDir.Replace('\','/'))');"
  $LogFile = Join-Path $LogsRoot "DEV72_$SceneId.log"
  Write-Output "START $SceneId | completed=$($CompletedIds.Count)/72 | free=$FreeGiB GiB"

  $OldPref = $env:MATLAB_PREFDIR
  try {
    $env:MATLAB_PREFDIR = $PrefDir
    & $Matlab -logfile "$LogFile" -batch $MatlabCommand
    $MatlabExit = $LASTEXITCODE
  } finally {
    if ($null -ne $OldPref) { $env:MATLAB_PREFDIR = $OldPref }
    else { Remove-Item Env:MATLAB_PREFDIR -ErrorAction SilentlyContinue }
  }

  try {
    if ($MatlabExit -ne 0) { throw "MATLAB exit code $MatlabExit for $SceneId." }
    $StatusPath = Join-Path $AttemptDir 'run_status.json'
    $RawPath = Join-Path $AttemptDir 'raw_run.mat'
    if (!(Test-Path -LiteralPath $StatusPath) -or !(Test-Path -LiteralPath $RawPath)) { throw "Missing raw/status for $SceneId." }
    $Status = Get-Content -Raw -LiteralPath $StatusPath | ConvertFrom-Json
    $RawHash = (Get-FileHash -LiteralPath $RawPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Status.state -ne 'COMPLETED' -or $Status.status_value -ne 'STABLE' -or $Status.transitions -ne 20000 -or
        $Status.state_samples -ne 20001 -or $Status.test_data_read -ne $false -or
        $Status.raw_sha256 -ne $RawHash -or $Status.payload_sha256 -ne $PayloadHash -or
        $Status.b_raw_sha256 -ne [string]$Record.b_raw_sha256) {
      throw "Run status/hash/identity failed for $SceneId."
    }
    $CompletedIds.Add($SceneId)
    $Progress.completed_scenes = $CompletedIds.Count
    $Progress.pending_scenes = 72 - $CompletedIds.Count
    $Progress.plant_calls_started = $Markers.Count + 1
    $Progress.last_completed_scene_id = $SceneId
    $Progress.active_scene_id = ''
    $Progress.completed_scene_ids = @($CompletedIds)
    $Progress.last_raw_sha256 = $RawHash
    $Progress.last_status_sha256 = (Get-FileHash -LiteralPath $StatusPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Progress.last_completed_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    [IO.File]::WriteAllText($ProgressPath,($Progress | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    Write-Output "DONE  $SceneId | completed=$($CompletedIds.Count)/72 | raw=$RawHash"
  } catch {
    $Progress.status = 'STOPPED_FAILURE'
    $Progress.active_scene_id = $SceneId
    $Progress.failure_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $Progress.failure_reason = $_.Exception.Message
    $Progress.completed_scenes = $CompletedIds.Count
    $Progress.pending_scenes = 72 - $CompletedIds.Count
    [IO.File]::WriteAllText($ProgressPath,($Progress | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
    throw
  }
}

$Progress.status = 'CANDIDATE_RUNS_COMPLETE_AWAITING_INDEPENDENT_AUDIT'
$Progress.completed_scenes = 72
$Progress.pending_scenes = 0
$Progress.active_scene_id = ''
$Progress.completed_scene_ids = @($CompletedIds)
$Progress.finished_utc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
[IO.File]::WriteAllText($ProgressPath,($Progress | ConvertTo-Json -Depth 10)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
Write-Output "ALL 72 CANDIDATE RUNS COMPLETE; awaiting independent score/audit."
