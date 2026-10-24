$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$entryDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v3'
$output = Join-Path $PSScriptRoot 'TEST_MATLAB_PROCESS_OBSERVATIONS_v1.jsonl'
if (Test-Path -LiteralPath $output) { throw 'Preserve earlier process observations.' }
$deadline = [DateTimeOffset]::Parse('2026-10-24T17:01:00Z').UtcDateTime
$encoding = [Text.UTF8Encoding]::new($false)
while ([DateTime]::UtcNow -lt $deadline) {
    $rows = @()
    foreach ($item in @(Get-CimInstance Win32_Process -Filter "Name='MATLAB.exe'")) {
        $p = Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
        if ($p) {
            $rows += [ordered]@{ pid=$p.Id; parent_pid=$item.ParentProcessId; executable=$item.ExecutablePath
                cpu_seconds=$p.TotalProcessorTime.TotalSeconds; working_set_bytes=$p.WorkingSet64
                peak_working_set_bytes=$p.PeakWorkingSet64; thread_count=$p.Threads.Count }
        }
    }
    $receipts = @(Get-ChildItem -LiteralPath $entryDir -File -Filter '*_MATLAB_OS_EXIT_v1.json' |
        Where-Object { $_.Name -match '^(BTR|DSSM|KAN|C5M110|C5FREEZE|C5NOPRED)_' })
    $failed = @($receipts | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json } |
        Where-Object { $_.matlab_os_exit_code -ne 0 })
    $row = [ordered]@{ utc=[DateTime]::UtcNow.ToString('o'); poll_seconds=30; processes=$rows
        completed_method_receipts=$receipts.Count; failed_method_receipts=$failed.Count
        scope='Read-only process sampling; worker and launcher are separate. This is not controller timing.' }
    [IO.File]::AppendAllText($output,($row|ConvertTo-Json -Depth 6 -Compress)+[Environment]::NewLine,$encoding)
    if ($receipts.Count -eq 6 -or $failed.Count -gt 0) { break }
    Start-Sleep -Seconds 30
}
