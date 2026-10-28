$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$oldEntry = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v3'
$entryDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v4'
$output = Join-Path $PSScriptRoot 'TEST_MATLAB_PROCESS_OBSERVATIONS_v2.jsonl'
if (Test-Path -LiteralPath $output) { throw 'Preserve earlier process observations.' }
$deadline = [DateTimeOffset]::Parse('2026-10-24T17:01:00Z').UtcDateTime
$encoding = [Text.UTF8Encoding]::new($false)
$oldB = Get-Content -Raw -LiteralPath (Join-Path $oldEntry 'BTR_MATLAB_OS_EXIT_v1.json') | ConvertFrom-Json
$oldFailure = Get-Content -Raw -LiteralPath (Join-Path $oldEntry 'DSSM_MATLAB_OS_EXIT_v1.json') | ConvertFrom-Json
if ($oldB.matlab_os_exit_code -ne 0 -or $oldFailure.matlab_os_exit_code -ne 1) { throw 'Historical B48/failure receipts differ.' }
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
    $receipts = @(Get-ChildItem -LiteralPath $entryDir -File -Filter 'RUN_*_MATLAB_OS_EXIT_v1.json')
    $failed = @($receipts | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json } |
        Where-Object { $_.matlab_os_exit_code -ne 0 })
    $row = [ordered]@{ utc=[DateTime]::UtcNow.ToString('o'); poll_seconds=30; processes=$rows
        historical_B48_success_receipts=1; historical_DSSM_prePlant_failure_receipts=1
        v4_completed_method_receipts=$receipts.Count; v4_failed_method_receipts=$failed.Count
        scope='Read-only worker/launcher resource sampling, separate from controller timing; retained v3 failure does not stop v4 observation.' }
    [IO.File]::AppendAllText($output,($row|ConvertTo-Json -Depth 6 -Compress)+[Environment]::NewLine,$encoding)
    if ($receipts.Count -eq 5 -or $failed.Count -gt 0) { break }
    Start-Sleep -Seconds 30
}
