# PowerShell 7 only. Scans source lines, parses and persists only three exact DEV IDs.
# No MATLAB, Plant, MAT, raw evidence, or TEST rows are opened as artifacts.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$sourcePath = Join-Path $repoRoot 'configs/scene_specs.csv'
$sourceRelative = 'configs/scene_specs.csv'
$expectedSourceSha = 'd116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3'
$expected = [ordered]@{
    'DL1018_DEV_T1_C00_W03' = @{ task='HELIX'; class_id='NONE'; t=0; c=0; w=3; seed=2026121803; sha='4546e417fcb2af93f09c83999e6dc0535cf07b58d4f4240e1d751f98ed19a824' }
    'DL1018_DEV_T2_C02_W15' = @{ task='FIG8_3D'; class_id='2'; t=1; c=2; w=15; seed=2026122847; sha='c8f3dde48b76ae351fe40c30866ff55fa8235e32914a5128e03a1f6b954456f5' }
    'DL1018_DEV_T3_C10_W11' = @{ task='SQUARE'; class_id='34'; t=2; c=10; w=11; seed=2026123971; sha='9f4d08ddc375a4be074c659e04827c49d957518e6098a2a3128788eb87d1452a' }
}
function ShaText([string]$value) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($value))).ToLowerInvariant()
}
function ShaFile([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw 'Source scene specs CSV is missing.' }
$sourceSha = ShaFile $sourcePath
if ($sourceSha -ne $expectedSourceSha) { throw 'Source scene specs SHA differs from taskbook pin.' }
$rows = @{}
$reader = [IO.StreamReader]::new($sourcePath, [Text.UTF8Encoding]::new($false), $true)
try {
    $header = $reader.ReadLine()
    if ([string]::IsNullOrWhiteSpace($header)) { throw 'Missing CSV header.' }
    $columns = $header.Split(',')
    $requiredColumns = @('scene_id','split','split_code','source_split_code','sealed','task','class_id','t','c','w','seed')
    foreach ($column in $requiredColumns) {
        if ($columns -cnotcontains $column) { throw "Missing source CSV column: $column" }
    }
    while (($line = $reader.ReadLine()) -ne $null) {
        foreach ($id in $expected.Keys) {
            if (-not $line.StartsWith($id + ',', [StringComparison]::Ordinal)) { continue }
            if ($rows.ContainsKey($id)) { throw "Duplicate DEV scene row: $id" }
            $fields = $line | ConvertFrom-Csv -Header $columns
            $want = $expected[$id]
            if ($fields.scene_id -cne $id -or $fields.split -cne 'DEV' -or
                [int]$fields.split_code -ne 2 -or [int]$fields.source_split_code -ne 1 -or
                [int]$fields.sealed -ne 0 -or $fields.task -cne $want.task -or
                $fields.class_id -cne $want.class_id -or [int]$fields.t -ne $want.t -or
                [int]$fields.c -ne $want.c -or [int]$fields.w -ne $want.w -or
                [long]$fields.seed -ne $want.seed) { throw "DEV scene fields differ: $id" }
            $lineSha = ShaText $line
            if ($lineSha -ne $want.sha) { throw "DEV scene source row SHA differs: $id" }
            $rows[$id] = [pscustomobject]@{
                scene_id = $id; split = 'DEV'; split_code = 2; source_split_code = 1
                sealed = 0; task = $want.task; class_id = $want.class_id
                t = $want.t; c = $want.c; w = $want.w; seed = $want.seed
                source_row_sha256 = $lineSha; source_line = $line
            }
        }
    }
} finally {
    $reader.Dispose()
}
if ($rows.Count -ne 3) { throw "Expected exactly three unique DEV scene rows; found $($rows.Count)." }

$configDir = Join-Path $PSScriptRoot 'configs'
$csvPath = Join-Path $configDir 'scene_specs_dev3.csv'
$receiptPath = Join-Path $configDir 'scene_specs_dev3_receipt.json'
if ((Test-Path -LiteralPath $csvPath) -or (Test-Path -LiteralPath $receiptPath)) {
    throw 'DEV-only CSV or receipt already exists; refusing to overwrite.'
}
if (-not (Test-Path -LiteralPath $configDir)) { New-Item -ItemType Directory -Path $configDir | Out-Null }
$orderedRows = @($expected.Keys | ForEach-Object { $rows[$_] })
$csvText = (@($header) + @($orderedRows | ForEach-Object { $_.source_line })) -join "`r`n"
$csvText += "`r`n"
$utf8 = [Text.UTF8Encoding]::new($false)
$csvBytes = $utf8.GetBytes($csvText)
$receiptRows = @($orderedRows | ForEach-Object {
    [ordered]@{
        scene_id=$_.scene_id; split=$_.split; split_code=$_.split_code
        source_split_code=$_.source_split_code; sealed=$_.sealed; task=$_.task
        class_id=$_.class_id; t=$_.t; c=$_.c; w=$_.w; seed=$_.seed
        source_row_sha256=$_.source_row_sha256
    }
})
$receipt = [ordered]@{
    schema='PAIRED_DEV3_SPEC_EXTRACTION_V1'
    status='THREE_EXACT_DEV_ROWS_VERIFIED'
    source_path=$sourceRelative
    source_sha256=$sourceSha
    source_header_sha256=(ShaText $header)
    extracted_csv_path='configs/scene_specs_dev3.csv'
    extracted_csv_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($csvBytes)).ToLowerInvariant()
    extraction_script_sha256=(ShaFile $PSCommandPath)
    taskbook_sha256=(ShaFile (Join-Path $PSScriptRoot 'INPUT_IDENTITY_TASKBOOK_v1_ZH.md'))
    rows=$receiptRows
}
$csvStream = [IO.File]::Open($csvPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try { $csvStream.Write($csvBytes, 0, $csvBytes.Length) } finally { $csvStream.Dispose() }
$receiptText = ($receipt | ConvertTo-Json -Depth 6) + "`n"
$receiptBytes = $utf8.GetBytes($receiptText)
$receiptStream = [IO.File]::Open($receiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try { $receiptStream.Write($receiptBytes, 0, $receiptBytes.Length) } finally { $receiptStream.Dispose() }
Write-Output "THREE_EXACT_DEV_ROWS_VERIFIED source_sha256=$sourceSha csv_sha256=$($receipt.extracted_csv_sha256) receipt_sha256=$(ShaFile $receiptPath)"
