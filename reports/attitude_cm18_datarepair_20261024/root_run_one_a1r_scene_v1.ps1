param([Parameter(Mandatory=$true)][ValidateRange(2,12)][int]$SequenceIndex)
$ErrorActionPreference='Stop'
$taskRepo=Split-Path (Split-Path $PSScriptRoot)
Set-Location -LiteralPath $taskRepo
$taskDir='reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1'
$taskPrep=Get-Content "$taskDir/A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json" -Raw | ConvertFrom-Json
$taskRow=$taskPrep.scene_rows[$SequenceIndex-1]
if($taskRow.sequence_index -ne $SequenceIndex){throw 'Scene order mismatch'}
$taskPrior=@()
for($taskIndex=0;$taskIndex -lt ($SequenceIndex-1);$taskIndex++){
    $taskPriorScene=$taskPrep.scene_rows[$taskIndex].scene_id
    $taskPriorPath="$taskDir/A1R_SCREEN12_LOG_AUDIT_${taskPriorScene}_v1.json"
    $taskAudit=Get-Content $taskPriorPath -Raw | ConvertFrom-Json
    if($taskAudit.status -ne 'PASS' -or $taskAudit.scene_id -ne $taskPriorScene){throw 'Prior audit not PASS'}
    $taskPrior+= (Get-FileHash $taskPriorPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$taskFirst=$taskPrep.scene_rows[0].scene_id
$taskRelease=Get-Content "$taskDir/ROOT_A1R_SCREEN12_CONTROL_RELEASE_${taskFirst}_v2.json" -Raw | ConvertFrom-Json
$taskRelease.scene_id=$taskRow.scene_id
$taskRelease.sequence_index=$SequenceIndex
$taskRelease.prior_audit_sha256=$taskPrior
$taskRelease.prepared_snapshot_sha256=$taskRow.prepared_snapshot_sha256
$taskRelease.baseline_C5_raw_sha256=$taskRow.baseline_C5_raw_sha256
$taskRelease.created_at=(Get-Date).ToString('o')
$taskReleasePath="$taskDir/ROOT_A1R_SCREEN12_CONTROL_RELEASE_$($taskRow.scene_id)_v2.json"
if(Test-Path -LiteralPath $taskReleasePath){throw 'Release exists; no retry'}
$taskRelease | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskReleasePath -Encoding utf8NoBOM
$taskSha=(Get-FileHash $taskReleasePath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskLog="$taskDir/ROOT_EXECUTION_$($taskRow.scene_id)_v2.log"
if(Test-Path -LiteralPath $taskLog){throw 'Execution log exists; no retry'}
& 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe' -batch "cd('$($taskRepo.Replace('\','/'))'); addpath('experiments/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1','-begin'); run_a1r_screen12_control_v2('$($taskRow.scene_id)','$taskReleasePath','$taskSha');" *> $taskLog
if($LASTEXITCODE -ne 0){throw 'MATLAB failed; retain evidence and stop'}
python reports/attitude_cm18_datarepair_20261024/a1r_screen12_control_v1/audit_a1r_screen12_log_v1.py --repo-root . --scene-id $taskRow.scene_id
if($LASTEXITCODE -ne 0){throw 'Independent raw audit failed; stop'}
$taskFinal=Get-Content "$taskDir/A1R_SCREEN12_LOG_AUDIT_$($taskRow.scene_id)_v1.json" -Raw | ConvertFrom-Json
$taskFinal | Select-Object status,scene_id,raw_sha256,counts,max_abs_reconstruction_delta,safety | ConvertTo-Json -Depth 5
