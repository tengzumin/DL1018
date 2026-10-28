[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('EngineeringGate','Remaining11')]
    [string]$Stage,
    [string]$MatlabExe = 'matlab'
)
$ErrorActionPreference = 'Stop'
$studyRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releasePath = Join-Path $studyRoot 'RELEASE.json'
if (-not (Test-Path -LiteralPath $releasePath -PathType Leaf)) { throw 'RELEASE.json is missing.' }
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
if ($release.status -ne 'RELEASED' -or [int]$release.authorized_Plant_calls -le 0) {
    throw 'DRAFT only: zero Plant authorization; no MATLAB process was started.'
}
if ($Stage -eq 'EngineeringGate') {
    $sceneIds = @('DL1018_DEV_T1_C10_W09')
    if ($release.authorization_phase -ne 'ENGINEERING_GATE' -or @($release.authorized_scenes).Count -ne 1 -or $release.authorized_scenes[0] -ne $sceneIds[0]) {
        throw 'Engineering gate release must authorize exactly DL1018_DEV_T1_C10_W09.'
    }
    if ([int]$release.authorized_Plant_calls -ne 1) { throw 'Engineering gate budget must equal one Plant call.' }
} else {
    $sceneIds = @(
      'DL1018_VAL_T1_C07_W14','DL1018_DEV_T2_C09_W10','DL1018_VAL_T2_C04_W14',
      'DL1018_DEV_T3_C09_W09','DL1018_VAL_T3_C01_W14','DL1018_DEV_T1_C01_W15',
      'DL1018_VAL_T2_C05_W15','DL1018_VAL_T3_C02_W15','DL1018_VAL_T1_C00_W07',
      'DL1018_DEV_T2_C00_W04','DL1018_DEV_T3_C00_W05'
    )
    if ($release.authorization_phase -ne 'REMAINING11' -or @($release.authorized_scenes).Count -ne 11 -or [int]$release.authorized_Plant_calls -ne 11) {
        throw 'Remaining phase requires a separate 11-call release.'
    }
    if ($release.engineering_gate_review.status -ne 'PASS_ROOT_REVIEW' -or [string]::IsNullOrWhiteSpace([string]$release.engineering_gate_review.result_sha256)) {
        throw 'Remaining 11 require a passing, hash-bound root review of the engineering gate.'
    }
    if (($sceneIds -join '|') -ne (@($release.authorized_scenes) -join '|')) {
        throw 'Remaining scene authorization does not exactly match the locked 11-scene order.'
    }
}
foreach ($fileHash in $release.execution_input_hashes.PSObject.Properties) {
    $path = Join-Path $studyRoot $fileHash.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing locked input: $($fileHash.Name)" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne ([string]$fileHash.Value).ToLowerInvariant()) { throw "SHA mismatch: $($fileHash.Name)" }
}
foreach ($sceneId in $sceneIds) {
    $quotedRoot = $studyRoot.Replace('\','/').Replace("'","''")
    $expr = "addpath('$quotedRoot'); run_gru_stream_tracking_head_filter_wn12_attempt('$sceneId');"
    & $MatlabExe -batch $expr
    if ($LASTEXITCODE -ne 0) { throw "MATLAB failed on $sceneId with exit code $LASTEXITCODE; stopping without retry." }
}
