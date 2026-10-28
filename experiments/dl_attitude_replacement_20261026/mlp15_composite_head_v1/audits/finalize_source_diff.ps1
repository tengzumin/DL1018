$ErrorActionPreference = 'Stop'
$study = Split-Path $PSScriptRoot -Parent
$experimentRoot = Split-Path $study -Parent
$parent = Join-Path $experimentRoot 'mlp15_causal_head_v1/candidate_runner_work'
$candidate = Join-Path $study 'candidate_runner_work'
$releasePath = Join-Path $study 'RELEASE.json'
$release = Get-Content -Raw $releasePath | ConvertFrom-Json -AsHashtable
if ($release.status -ne 'PREPARED_ROOT_REVIEW_REQUIRED' -or
    $release.authorized_Plant_calls -ne 0 -or $release.Plant_calls -ne 0) {
    throw 'Refusing to finalize a release that is not prepared with a zero Plant budget.'
}

$files = @(
    'matlab/runtime/mlp15_attitude_step_v1.m',
    'matlab/runtime/run_gate_holdout_closed_loop.m'
)
$patchParts = [System.Collections.Generic.List[string]]::new()
foreach ($relative in $files) {
    $oldPath = Join-Path $parent $relative
    $newPath = Join-Path $candidate $relative
    $part = & git diff --no-index --no-ext-diff --unified=4 -- $oldPath $newPath
    if ($LASTEXITCODE -notin @(0, 1)) { throw "git diff failed for $relative" }
    $patchParts.AddRange([string[]]$part)
}

$patchPath = Join-Path $study 'SOURCE_DIFF.patch'
$patchText = ($patchParts -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText($patchPath, $patchText, [System.Text.UTF8Encoding]::new($false))
$patchSha = (Get-FileHash -LiteralPath $patchPath -Algorithm SHA256).Hash.ToLowerInvariant()

$diffPath = Join-Path $study 'SOURCE_DIFF.json'
$diff = Get-Content -Raw $diffPath | ConvertFrom-Json -AsHashtable
$diff.patch_file = 'SOURCE_DIFF.patch'
$diff.patch_sha256 = $patchSha
$diff.finalizer_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText($diffPath, (ConvertTo-Json -InputObject $diff -Depth 100) + "`n", `
    [System.Text.UTF8Encoding]::new($false))
$diffSha = (Get-FileHash -LiteralPath $diffPath -Algorithm SHA256).Hash.ToLowerInvariant()

$release.source_diff_json_sha256 = $diffSha
$release.source_diff_patch_path = 'SOURCE_DIFF.patch'
$release.source_diff_patch_sha256 = $patchSha
$release.source_diff_finalize_script_sha256 = $diff.finalizer_script_sha256
[System.IO.File]::WriteAllText($releasePath, (ConvertTo-Json -InputObject $release -Depth 100) + "`n", `
    [System.Text.UTF8Encoding]::new($false))
$releaseSha = (Get-FileHash -LiteralPath $releasePath -Algorithm SHA256).Hash.ToLowerInvariant()

$recordPath = Join-Path $study 'RELEASE_RECORD.json'
$record = Get-Content -Raw $recordPath | ConvertFrom-Json -AsHashtable
$record.release_sha256 = $releaseSha
$record.source_diff_patch_sha256 = $patchSha
[System.IO.File]::WriteAllText($recordPath, (ConvertTo-Json -InputObject $record -Depth 100) + "`n", `
    [System.Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    patch_sha256 = $patchSha
    source_diff_json_sha256 = $diffSha
    release_sha256 = $releaseSha
    authorized_Plant_calls = $release.authorized_Plant_calls
    Plant_calls = $release.Plant_calls
    status = $release.status
} | ConvertTo-Json -Depth 4
