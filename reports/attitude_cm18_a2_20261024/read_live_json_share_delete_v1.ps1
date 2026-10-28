param([Parameter(Mandatory = $true)][string]$LiteralPath)
$ErrorActionPreference = 'Stop'
# Allow delete sharing and close promptly. On this Windows build that flag
# alone does not guarantee os.replace succeeds while the handle stays open.
$resolvedPath = (Resolve-Path -LiteralPath $LiteralPath).Path
$sharing = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
$stream = [IO.File]::Open($resolvedPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, $sharing)
try {
    $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8, $true)
    try { $jsonText = $reader.ReadToEnd() } finally { $reader.Dispose() }
} finally { $stream.Dispose() }
# Emit only after the file handle has been closed.
$jsonText | ConvertFrom-Json | ConvertTo-Json -Depth 30
