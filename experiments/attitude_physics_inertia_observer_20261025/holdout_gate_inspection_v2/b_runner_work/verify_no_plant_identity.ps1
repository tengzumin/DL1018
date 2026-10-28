[CmdletBinding()]
param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
try {
    $work = $PSScriptRoot
    $identity = Get-Content -LiteralPath (Join-Path $work 'identity_no_plant.json') -Raw | ConvertFrom-Json
    $lockPath = [string]$identity.input_lock.path
    $lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
    $lockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $lockPath).Hash.ToLowerInvariant()
    if ($lockHash -ne [string]$identity.input_lock.sha256) { throw 'Input lock SHA mismatch.' }

    $lockedSources = @($lock.active_source_inventory | Where-Object { $_.path -match '\.m$' } | Sort-Object path)
    if ($lockedSources.Count -ne 31 -or $lockedSources.Count -ne [int]$identity.source_tree.count) { throw 'The locked MATLAB source count is not 31.' }
    $manifestText = ($lockedSources | ForEach-Object { '{0}|{1}' -f $_.path, $_.sha256.ToLowerInvariant() }) -join "`n"
    $manifestHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($manifestText))).ToLowerInvariant()
    if ($manifestHash -ne [string]$identity.source_tree.manifest_sha256) { throw 'Source manifest SHA mismatch.' }

    foreach ($source in $identity.source_tree.files) {
        $locked = $lockedSources | Where-Object { $_.path -eq [string]$source.source_path }
        if (@($locked).Count -ne 1 -or $locked.sha256.ToLowerInvariant() -ne [string]$source.sha256) { throw "Source does not match lock metadata: $($source.source_path)" }
        $originalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source.source_path).Hash.ToLowerInvariant()
        if ($originalHash -ne [string]$source.sha256) { throw "Frozen source changed since lock: $($source.source_path)" }
        $mirrorPath = Join-Path $work ([string]$source.mirror_relative_path)
        $mirrorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $mirrorPath).Hash.ToLowerInvariant()
        if ($mirrorHash -ne [string]$source.sha256) { throw "Isolated source copy SHA mismatch: $mirrorPath" }
    }

    $lockedSupport = @($lock.active_source_inventory | Where-Object { $_.path -match '\.mat$' } | Sort-Object path)
    if ($lockedSupport.Count -ne 1 -or $lockedSupport.Count -ne @($identity.source_tree.support_files).Count -or
        $lockedSources.Count + $lockedSupport.Count -ne [int]$identity.source_tree.active_inventory_count) { throw 'Locked active source inventory count mismatch.' }
    foreach ($source in $identity.source_tree.support_files) {
        $locked = $lockedSupport | Where-Object { $_.path -eq [string]$source.source_path }
        if (@($locked).Count -ne 1 -or $locked.sha256.ToLowerInvariant() -ne [string]$source.sha256) { throw "Support file does not match lock metadata: $($source.source_path)" }
        $originalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source.source_path).Hash.ToLowerInvariant()
        if ($originalHash -ne [string]$source.sha256) { throw "Locked support file changed: $($source.source_path)" }
        $mirrorPath = Join-Path $work ([string]$source.mirror_relative_path)
        $mirrorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $mirrorPath).Hash.ToLowerInvariant()
        if ($mirrorHash -ne [string]$source.sha256) { throw "Isolated support copy SHA mismatch: $mirrorPath" }
    }

    $overlays = @($identity.source_tree.runtime_overlay_files)
    if ($overlays.Count -ne 1) { throw 'Expected exactly one locked runtime overlay.' }
    foreach ($overlay in $overlays) {
        $originalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath ([string]$overlay.source_path)).Hash.ToLowerInvariant()
        if ($originalHash -ne [string]$overlay.sha256) { throw 'Runtime overlay source SHA mismatch.' }
        $mirror = Join-Path $work ([string]$overlay.mirror_relative_path)
        $mirrorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $mirror).Hash.ToLowerInvariant()
        if ($mirrorHash -ne [string]$overlay.sha256) { throw "Runtime overlay mirror SHA mismatch: $mirror" }
    }

    $snapshotPath = [string]$identity.configuration.snapshot_path
    $snapshotHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotPath).Hash.ToLowerInvariant()
    if ($snapshotHash -ne [string]$identity.configuration.snapshot_sha256) { throw 'No-Plant cfg/options snapshot SHA mismatch.' }
    if ([int64](Get-Item -LiteralPath $snapshotPath).Length -ne [int64]$identity.configuration.snapshot_size_bytes) { throw 'No-Plant cfg/options snapshot size mismatch.' }

    $c3Ref = $lock.upstream_refs.c3_prepared_snapshot
    if ([string]$c3Ref.path -ne [string]$identity.snapshot_cross_check.upstream_c3_snapshot_path -or
        $c3Ref.sha256.ToLowerInvariant() -ne [string]$identity.snapshot_cross_check.upstream_c3_snapshot_lock_sha256) { throw 'C3 snapshot reference no longer matches the input lock.' }
    $c3Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $c3Ref.path).Hash.ToLowerInvariant()
    if ($c3Hash -ne [string]$identity.snapshot_cross_check.upstream_c3_snapshot_sha256) { throw 'Upstream no-Plant C3 snapshot SHA mismatch.' }
    if (-not $identity.snapshot_cross_check.cfg_fields_identical -or
        -not $identity.snapshot_cross_check.common_opts_fields_identical_except_b_position_flags -or
        $identity.snapshot_cross_check.c3_only_opts_fields -notcontains 'stage1_position_runtime' -or
        $identity.snapshot_cross_check.b_only_opts_fields.Count -ne 0) { throw 'Recorded cfg/options cross-check contract is incomplete.' }
    if ($identity.model_binding.dssm_model_loaded -or $identity.model_binding.learned_model_payload_loaded -or $identity.model_binding.dssm_fields_present) { throw 'Identity unexpectedly binds a learned/DSSM model.' }

    if (-not $Quiet) { Write-Output "PASS: 31 locked MATLAB sources and 1 locked MAT support file match; B and upstream C3 no-Plant snapshot hashes match their identities. The recorded cfg/options cross-check excludes the C3 stage1 model field; no Plant execution performed." }
} catch {
    Write-Error $_
    exit 1
}



