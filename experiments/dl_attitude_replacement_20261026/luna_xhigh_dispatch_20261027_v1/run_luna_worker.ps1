param([Parameter(Mandatory)][ValidateSet('implementation','peer_review')][string]$Role)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'PowerShell 7 is required.'}
$workspace='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018'
$cli='C:\Users\35326\AppData\Local\OpenAI\Codex\bin\2993767bd1dfb009\codex.exe'
$promptPath=Join-Path $PSScriptRoot ($Role+'_prompt.txt')
$stdoutPath=Join-Path $PSScriptRoot ($Role+'.jsonl')
$stderrPath=Join-Path $PSScriptRoot ($Role+'.stderr.log')
$lastPath=Join-Path $PSScriptRoot ($Role+'_final.md')
$statusPath=Join-Path $PSScriptRoot ($Role+'_status.json')
if(Test-Path -LiteralPath $statusPath){throw 'Existing worker dispatch must be preserved.'}
$state=[ordered]@{role=$Role;runner_pid=$PID;status='RUNNING';requested_model='gpt-6-luna';reasoning_effort='xhigh';service_tier='default';started_utc=[DateTime]::UtcNow.ToString('o');prompt_sha256=(Get-FileHash -LiteralPath $promptPath -Algorithm SHA256).Hash.ToLowerInvariant()}
$state|ConvertTo-Json|Set-Content -LiteralPath $statusPath -Encoding utf8
$workerArgs=@('exec','--model','gpt-6-luna','-c','model_reasoning_effort="xhigh"','-c','service_tier="default"','-c','approval_policy="never"','--sandbox','danger-full-access','--ephemeral','--color','never','--json','--output-last-message',$lastPath,'--cd',$workspace,'-')
try {
    Get-Content -Raw -LiteralPath $promptPath | & $cli @workerArgs 1> $stdoutPath 2> $stderrPath
    $exitCode=$LASTEXITCODE
    $state.exit_code=$exitCode
    $state.status=if($exitCode -eq 0){'COMPLETED'}else{'FAILED'}
} catch {
    $state.status='FAILED';$state.error=$_.Exception.Message
} finally {
    $state.finished_utc=[DateTime]::UtcNow.ToString('o')
    if(Test-Path -LiteralPath $lastPath){$state.final_message_sha256=(Get-FileHash -LiteralPath $lastPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    $state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $statusPath -Encoding utf8
}
