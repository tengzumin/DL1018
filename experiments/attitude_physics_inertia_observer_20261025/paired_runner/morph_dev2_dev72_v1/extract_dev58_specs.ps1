# PowerShell 7 only. Extract exactly the 58 unpaired DEV/VAL rows named by the
# frozen C5 cohort; stop as soon as all 72 locked cohort rows have been located.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$entry = $PSScriptRoot
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $entry '../../../..')).Path
$taskbookPath = Join-Path $entry 'ATTITUDE_PHYS_INERTIA_DEV72_TASKBOOK_v1_ZH.md'
$lockPath = Join-Path $repoRoot 'experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json'
$screenPath = Join-Path $repoRoot 'experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_screen12_v1/manifest/SCREEN12_PREPARED_MANIFEST.json'
$sourcePath = Join-Path $repoRoot 'configs/scene_specs.csv'
$legacyReceiptPath = Join-Path $repoRoot 'experiments/attitude_physics_inertia_observer_20261025/paired_runner/configs/scene_specs_dev3_receipt.json'
$outDir = Join-Path $entry 'configs'
$csvPath = Join-Path $outDir 'scene_specs_dev58.csv'
$receiptPath = Join-Path $outDir 'scene_specs_dev58_receipt.json'

if ((Test-Path -LiteralPath $csvPath) -or (Test-Path -LiteralPath $receiptPath)) {
    throw 'DEV58 CSV or receipt already exists; refusing to overwrite.'
}
foreach ($p in @($taskbookPath,$lockPath,$screenPath,$sourcePath,$legacyReceiptPath)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required input missing: $p" }
}

function Get-ShaText([string]$Text) {
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Text))).ToLowerInvariant()
}
function Get-ShaBytes([byte[]]$Bytes) {
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Write-NewBytes([string]$Path,[byte[]]$Bytes) {
    $stream = [IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    try { $stream.Write($Bytes,0,$Bytes.Length) } finally { $stream.Dispose() }
}

$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    '82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75') {
    throw 'C5 DEV72 input lock differs from the reviewed v3 identity.'
}
$screen = Get-Content -LiteralPath $screenPath -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $screenPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    '322957f7e446dd6a58607f70e0be379d98ad5ed6ae8b3e772fc42f10ea056fba') {
    throw 'Screen12 prepared manifest differs from the independently audited input.'
}
$legacy = Get-Content -LiteralPath $legacyReceiptPath -Raw | ConvertFrom-Json
if ($legacy.source_sha256 -cne 'd116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3') {
    throw 'Existing DEV-only extraction receipt no longer binds the known source CSV.'
}

$allIds = @($lock.scene_ids_all_72 | ForEach-Object { [string]$_ })
$screenIds = @($screen.scenes | ForEach-Object { [string]$_.scene_id })
$priorDevIds = @('DL1018_DEV_T2_C02_W15','DL1018_DEV_T3_C10_W11')
$excluded = @($screenIds) + @($priorDevIds)
$expectedIds = @($allIds | Where-Object { $excluded -cnotcontains $_ })
if ($allIds.Count -ne 72 -or $allIds.Count -ne @($allIds | Select-Object -Unique).Count -or
    $screenIds.Count -ne 12 -or $expectedIds.Count -ne 58) {
    throw 'C5 cohort, screen12 exclusions or DEV reuse counts do not match the taskbook.'
}

$taskbook = Get-Content -LiteralPath $taskbookPath -Raw
$sectionMatch = [regex]::Match($taskbook,'(?ms)^## 58 场 ID.*?\r?\n(?<body>.*?)(?=^## |\z)')
if (-not $sectionMatch.Success) { throw 'Cannot locate the taskbook 58-scene ID section.' }
$taskbookIds = @([regex]::Matches($sectionMatch.Groups['body'].Value,'DL1018_(?:DEV|VAL)_T\d+_C\d+_W\d+') | ForEach-Object Value)
if (($taskbookIds -join ',') -cne ($expectedIds -join ',')) {
    throw 'Taskbook 58-scene order differs from the stable C5-lock filter.'
}

$sceneById = @{}
foreach ($scene in $lock.scenes) { $sceneById[[string]$scene.scene_id] = $scene }
if ($sceneById.Count -ne 72) { throw 'C5 lock scene records are not a 72-row unique map.' }
$expectedSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($id in $allIds) { [void]$expectedSet.Add($id) }
$found = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)

$reader = [IO.StreamReader]::new($sourcePath,[Text.UTF8Encoding]::new($false),$true)
try {
    $header = $reader.ReadLine()
    if ([string]::IsNullOrWhiteSpace($header)) { throw 'Source CSV header is empty.' }
    $columns = $header.Split(',')
    foreach ($name in @('scene_id','split','split_code','source_split_code','sealed','task','class_id','t','c','w','seed')) {
        if ($columns -cnotcontains $name) { throw "Missing source column: $name" }
    }
    while ($found.Count -lt 72 -and ($line = $reader.ReadLine()) -ne $null) {
        $comma = $line.IndexOf(',')
        if ($comma -le 0) { continue }
        $id = $line.Substring(0,$comma)
        if (-not $expectedSet.Contains($id)) { continue }
        if ($found.ContainsKey($id)) { throw "Duplicate locked scene row: $id" }
        $fields = $line | ConvertFrom-Csv -Header $columns
        $expectedSplit = [string]$sceneById[$id].source_split
        $expectedSplitCode = if ($expectedSplit -ceq 'DEV') { 2 } else { 1 }
        if ($fields.scene_id -cne $id -or $fields.split -cne $expectedSplit -or
            [int]$fields.split_code -ne $expectedSplitCode -or
            [int]$fields.source_split_code -ne 1 -or [int]$fields.sealed -ne 0) {
            throw "Source row split/identity differs from the locked cohort: $id"
        }
        $found.Add($id,[pscustomobject]@{ scene_id=$id; split=$expectedSplit; source_row_sha256=(Get-ShaText $line); source_line=$line })
    }
} finally { $reader.Dispose() }
if ($found.Count -ne 72) { throw "Found $($found.Count) of 72 locked DEV/VAL rows before end of source." }

$persisted = @($expectedIds | ForEach-Object { $found[$_] })
$csvText = (@($header) + @($persisted | ForEach-Object source_line)) -join "`r`n"
$csvText += "`r`n"
$utf8 = [Text.UTF8Encoding]::new($false)
$csvBytes = $utf8.GetBytes($csvText)
$receiptRows = @($persisted | ForEach-Object {
    [ordered]@{ scene_id=$_.scene_id; split=$_.split; source_row_sha256=$_.source_row_sha256 }
})
$receipt = [ordered]@{
    schema='MORPH_DEV2_DEV58_SCENE_SOURCE_RECEIPT_V1'
    status='EXACT_58_ROWS_FROM_LOCKED_DEV72_COHORT'
    source_path='configs/scene_specs.csv'
    source_sha256=$legacy.source_sha256
    source_sha256_provenance='Existing DEV-only receipt; source file digest was independently checked before this extraction.'
    source_header_sha256=(Get-ShaText $header)
    source_rows_located=72
    source_scan_stopped_after_final_locked_dev_val_row=$true
    TEST_rows_selected_or_persisted=$false
    extracted_csv_path='experiments/attitude_physics_inertia_observer_20261025/paired_runner/morph_dev2_dev72_v1/configs/scene_specs_dev58.csv'
    extracted_csv_sha256=(Get-ShaBytes $csvBytes)
    taskbook_sha256=(Get-FileHash -LiteralPath $taskbookPath -Algorithm SHA256).Hash.ToLowerInvariant()
    c5_input_lock_sha256=(Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    screen12_manifest_sha256=(Get-FileHash -LiteralPath $screenPath -Algorithm SHA256).Hash.ToLowerInvariant()
    all_72_scene_ids=$allIds
    excluded_reuse_ids=$excluded
    rows=$receiptRows
}
$receiptBytes = $utf8.GetBytes(($receipt | ConvertTo-Json -Depth 8) + "`n")
Write-NewBytes $csvPath $csvBytes
try { Write-NewBytes $receiptPath $receiptBytes }
catch { Remove-Item -LiteralPath $csvPath -Force; throw }

"EXTRACTED_58_ROWS; matched_locked_dev_val=72; test_rows_persisted=false; csv_sha256=$($receipt.extracted_csv_sha256); receipt_sha256=$((Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant())"
