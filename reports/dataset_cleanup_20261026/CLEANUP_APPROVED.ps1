param([switch]$CheckOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Only the user-approved, frozen 5,394-file manifest is accepted.
$ReportRoot = 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\dataset_cleanup_20261026'
$ManifestPath = Join-Path $ReportRoot 'DELETE_MANIFEST.csv'
$ExpectedManifestHash = 'DCD9B70113EA9B27CA1C30F5F81D2091A248B7C338B891D9FAD1D6C4F5FDF60B'
$AllowedRoots = @(
    'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009',
    'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
)

function Get-CheckedFile($Row) {
    $target = [System.IO.Path]::GetFullPath($Row.path)
    $matchingRoots = @($AllowedRoots | Where-Object {
        $target.StartsWith($_ + '\', [System.StringComparison]::OrdinalIgnoreCase)
    })
    if ($matchingRoots.Count -ne 1) { throw "超出两个允许的文件夹：$target" }
    if ($target -ne $Row.path) { throw "清单路径不是规范绝对路径：$target" }
    $file = Get-Item -LiteralPath $target -Force
    if ($file -isnot [System.IO.FileInfo] -or $file.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) {
        throw "目标不是普通文件：$target"
    }
    $ancestor = $file.Directory
    while ($null -ne $ancestor) {
        if ($ancestor.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) {
            throw "路径包含链接或重定向目录：$target"
        }
        $ancestor = $ancestor.Parent
    }
    if ($file.Length -ne [long]$Row.size -or $file.LastWriteTimeUtc.Ticks -ne [long]$Row.mtime_ticks) {
        throw "文件在审计后发生变化，停止清理：$target"
    }
    return $file
}

$deletedCount = 0
$deletedBytes = [long]0
$logPath = $null

try {
    if ((Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash -ne $ExpectedManifestHash) {
        throw '清单内容发生变化，拒绝执行。'
    }
    $rows = @(Import-Csv -LiteralPath $ManifestPath)
    if ($rows.Count -ne 5394) { throw '清单文件数必须为 5,394。' }
    if (($rows | Measure-Object -Property size -Sum).Sum -ne 76577531856) {
        throw '清单总字节数与审核结果不一致。'
    }

    $pending = [System.Collections.Generic.List[object]]::new()
    $alreadyMissing = 0
    foreach ($row in $rows) {
        # Missing files are skipped; they never cause a broader directory scan.
        if (-not (Test-Path -LiteralPath $row.path)) { $alreadyMissing++; continue }
        $null = Get-CheckedFile $row
        $pending.Add($row)
    }

    $pendingBytes = [long]0
    foreach ($row in $pending) { $pendingBytes += [long]$row.size }
    Write-Host "已校验：待删 $($pending.Count) 个文件，约 $([math]::Round($pendingBytes / 1GB, 3)) GiB。"
    Write-Host "范围：仅 DL1009 / DL1018 的固定清单；不删除目录。已不存在的清单文件：$alreadyMissing。"
    if ($CheckOnly) {
        Write-Host '检查模式通过：没有删除文件，没有写入执行日志。'
        exit 0
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $logPath = Join-Path $ReportRoot "EXECUTION_MANUAL_$stamp.csv"
    if (Test-Path -LiteralPath $logPath) { throw '执行日志名称发生冲突，停止。' }
    Write-Host '开始永久删除你已确认的清单文件……'

    foreach ($row in $pending) {
        # Recheck the exact file immediately before each individual deletion.
        $file = Get-CheckedFile $row
        Remove-Item -LiteralPath $file.FullName -Force
        if (Test-Path -LiteralPath $file.FullName) { throw "文件仍存在：$($file.FullName)" }
        $deletedCount++
        $deletedBytes += [long]$row.size
        [pscustomobject]@{
            project = $row.project
            category = $row.action
            path = $row.path
            size = $row.size
            result = 'DELETED'
            deleted_utc = [DateTime]::UtcNow.ToString('o')
        } | Export-Csv -LiteralPath $logPath -Append -NoTypeInformation -Encoding utf8BOM
        if (($deletedCount % 100) -eq 0) {
            Write-Host "已删除 $deletedCount / $($pending.Count) 个文件。"
        }
    }

    [pscustomobject]@{
        status = 'COMPLETE'
        manifest_sha256 = $ExpectedManifestHash
        deleted_files = $deletedCount
        deleted_bytes = $deletedBytes
        already_missing_files = $alreadyMissing
        execution_log = $logPath
        finished_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReportRoot "MANUAL_RESULT_$stamp.json") -Encoding utf8
    Write-Host "完成：删除 $deletedCount 个文件，释放约 $([math]::Round($deletedBytes / 1GB, 3)) GiB。"
    Write-Host "日志：$logPath"
    exit 0
}
catch {
    Write-Host "清理已停止：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "本次已删除 $deletedCount 个文件；不会继续删除其他文件。"
    if ($null -ne $logPath) { Write-Host "已完成部分的日志：$logPath" }
    exit 1
}
