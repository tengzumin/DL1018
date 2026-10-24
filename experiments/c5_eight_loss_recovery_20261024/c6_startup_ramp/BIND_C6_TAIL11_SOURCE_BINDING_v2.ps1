$ErrorActionPreference = 'Stop'
$taskDir = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'
$baselinePath = Join-Path $taskDir 'C6_TAIL11_SOURCE_BINDING_v1.json'
$bindingPath = Join-Path $taskDir 'C6_TAIL11_SOURCE_BINDING_v2.json'
$tailContractPath = Join-Path $taskDir 'C6_TAIL11_RUN_CONTRACT_v1.json'
$releasePath = Join-Path $taskDir 'C6_TAIL11_PARENT_RELEASE_v1.json'
$runnerPath = Join-Path $taskDir 'run_c6_startup_ramp_tail11_v2.m'
$launcherPath = Join-Path $taskDir 'RUN_C6_TAIL11_EXACT_v2.ps1'
if (Test-Path -LiteralPath $bindingPath) { throw 'V2 source binding already exists; preserve it and do not overwrite.' }
if (Test-Path -LiteralPath $releasePath) { throw 'A tail release exists; do not rebind sources after release.' }
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$baselineSha = & $sha $baselinePath
if ($baselineSha -cne '62c270ec8df255fbd80ad5937794d8212e06ce455c5915394a31af4fb3294602') {
    throw 'The frozen v1 tail binding differs from the parent-reviewed baseline.'
}
$baseline = Get-Content -LiteralPath $baselinePath -Raw | ConvertFrom-Json
$binding = $baseline
if ($binding.schema -ne 'C6_TAIL11_SOURCE_BINDING_V1' -or $binding.state -ne 'SOURCE_BOUND_C6_TAIL11_WAIT_PARENT_RELEASE_V1') {
    throw 'Unexpected v1 source binding schema/state.'
}
$tailContractSha = & $sha $tailContractPath
$tailRefs = @($binding.source_files | Where-Object { $_.role -ceq 'tail_contract' })
if ($tailRefs.Count -ne 1 -or $tailContractSha -cne 'df833c66edc8e3c02f9e2cc58bd1e2acea9b7f1c21698e3a4ce3c177f4abaa8c' -or
    $tailRefs[0].path -cne $tailContractPath -or $tailRefs[0].sha256 -cne $tailContractSha) {
    throw 'The frozen v1 tail science contract differs from the parent-reviewed baseline.'
}
$runnerSha = & $sha $runnerPath
$launcherSha = & $sha $launcherPath
$builderSha = & $sha $PSCommandPath
foreach ($role in @('tail_runner','launcher','tail_binding_builder')) {
    $refs = @($binding.source_files | Where-Object { $_.role -ceq $role })
    if ($refs.Count -ne 1) { throw "Expected exactly one source reference for $role." }
}
$binding.schema = 'C6_TAIL11_SOURCE_BINDING_V2'
$binding.state = 'SOURCE_BOUND_C6_TAIL11_WAIT_PARENT_RELEASE_V2'
$binding.created_utc = [DateTime]::UtcNow.ToString('o')
$binding.tail_runner_sha256 = $runnerSha
foreach ($ref in $binding.source_files) {
    switch ($ref.role) {
        'tail_runner' { $ref.path = $runnerPath; $ref.sha256 = $runnerSha }
        'launcher' { $ref.path = $launcherPath; $ref.sha256 = $launcherSha }
        'tail_binding_builder' { $ref.path = $PSCommandPath; $ref.sha256 = $builderSha }
    }
}
if ($binding.source_files.Count -ne 11 -or (Test-Path -LiteralPath $releasePath)) {
    throw 'Unexpected binding inventory size or a tail release appeared during binding.'
}
$json = $binding | ConvertTo-Json -Depth 32
$bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
$stream = [IO.File]::Open($bindingPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
Write-Output ("C6 TAIL11 V2 SOURCE BINDING READY; RUNNER_SHA256={0}; LAUNCHER_SHA256={1}; BINDING_SHA256={2}; RELEASE_CREATED=false" -f $runnerSha,$launcherSha,(& $sha $bindingPath))
