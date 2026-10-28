$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $repo
$base = Join-Path $repo 'reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1'
$releasePath = Join-Path $base 'ROOT_DECOMPOSITION_REMAINING11_RELEASE_v1.json'
$release = Get-Content -LiteralPath $releasePath -Raw | ConvertFrom-Json
$source = Join-Path $repo $release.source_path
$prep = Get-Content -LiteralPath (Join-Path $base 'A1T_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json') -Raw | ConvertFrom-Json
# Sequence 2 is the separately supervised engineering check. Do not repeat it.
$first = Join-Path $repo 'reports/attitude_cm18_datarepair_20261024/a1t_same_state_decomposition_v2/DL1018_DEV_T1_C00_W03/A1T_SAME_STATE_DECOMPOSITION_DL1018_DEV_T1_C00_W03_v2.json'
if (-not (Test-Path -LiteralPath $first)) { throw 'Sequence2 result missing' }
$firstResult = Get-Content -LiteralPath $first -Raw | ConvertFrom-Json
if ($firstResult.status -ne 'PASS_SINGLE_SCENE_ONLY') { throw 'Sequence2 not PASS' }
foreach ($row in @($prep.scene_rows | Where-Object {$_.sequence_index -ge 3} | Sort-Object sequence_index)) {
    $sid = $row.scene_id
    if ($sid -notmatch '^DL1018_(DEV|VAL)_T[123]_C\d{2}_W\d{2}$' -or $sid -notin $release.scene_ids) { throw 'Unreleased scene' }
    if ((Get-FileHash -LiteralPath $source).Hash.ToLower() -ne $release.source_sha256) { throw 'Source changed' }
    $resultPath = Join-Path $repo "reports/attitude_cm18_datarepair_20261024/a1t_same_state_decomposition_v2/$sid/A1T_SAME_STATE_DECOMPOSITION_${sid}_v2.json"
    $receiptPath = Join-Path $base "ROOT_DECOMPOSITION_SEQ$('{0:D2}' -f [int]$row.sequence_index)_EXECUTION_v1.json"
    if ((Test-Path -LiteralPath $resultPath) -or (Test-Path -LiteralPath $receiptPath)) { throw 'No overwrite/restart' }
    $started = [DateTimeOffset]::Now.ToString('o')
    $startMarker = "$receiptPath.start.json"
    if (Test-Path -LiteralPath $startMarker) { throw 'Prior actual start exists; inspect before resume' }
    [ordered]@{scene_id=$sid;started_at=$started;source_sha256=$release.source_sha256} | ConvertTo-Json | Set-Content -LiteralPath $startMarker -Encoding utf8
    Write-Output "START $sid"
    $matlabCommand = "addpath('experiments/attitude_cm18_datarepair_20261024/a1t_same_state_decomposition_v2'); p=a1t_same_state_decomposition_v2('$sid'); disp(p);"
    & 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -batch $matlabCommand -logfile (Join-Path $base "ROOT_DECOMPOSITION_${sid}_attempt01.log")
    $osCode = $LASTEXITCODE
    $receipt = [ordered]@{scene_id=$sid;sequence_index=$row.sequence_index;started_at=$started;ended_at=[DateTimeOffset]::Now.ToString('o');os_exit_code=$osCode;source_sha256=$release.source_sha256;release_sha256=(Get-FileHash -LiteralPath $releasePath).Hash.ToLower();status='FAILED';plant_calls=0;training_steps=0;TEST_accessed=$false}
    if ($osCode -eq 0 -and (Test-Path -LiteralPath $resultPath)) {
        $j = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
        if ($j.status -ne 'PASS_SINGLE_SCENE_ONLY' -or $j.scope.scene_id -ne $sid -or $j.schedule.event_count -ne 1999) { throw 'Invalid result' }
        foreach ($key in @('max_abs_requested_generalized_closure','max_abs_reallocated_vs_raw_realized_generalized','max_abs_reconstructed_event_X18','max_abs_reconstructed_event_forward','max_abs_E0_minus_G_Cstar','max_abs_event_linear_fit_clip_identity','max_event_fresh_minus_held_rad_s2')) {
            if ($null -eq $j.closures.PSObject.Properties[$key]) { throw "Missing closure: $key" }
            $v = [double]$j.closures.$key
            if (-not [double]::IsFinite($v) -or $v -gt 1e-8) { throw "Closure failed: $key" }
        }
        $receipt.status = 'PASS_ENGINEERING_CLOSURE_PENDING_INDEPENDENT_AGGREGATE'
        $receipt.result_sha256 = (Get-FileHash -LiteralPath $resultPath).Hash.ToLower()
    }
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    if ($receipt.status -eq 'FAILED') { throw "Diagnostic failed: $sid" }
    Write-Output "COMPLETE $sid"
}
