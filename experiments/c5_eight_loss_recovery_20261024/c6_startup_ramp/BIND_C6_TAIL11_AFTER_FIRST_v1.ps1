$ErrorActionPreference = 'Stop'
function Get-C6FixedDeadlineUtc {
    param([string]$JsonPath, [object]$Value, [string]$Label)
    $expectedText = '2026-10-24T17:01:00Z'
    $rawJson = [IO.File]::ReadAllText($JsonPath)
    $deadlineMatches = [regex]::Matches($rawJson, '"deadline_utc"\s*:\s*"([^"]+)"')
    if ($deadlineMatches.Count -ne 1 -or $deadlineMatches[0].Groups[1].Value -cne $expectedText) {
        throw "$Label raw JSON deadline must be exactly $expectedText."
    }
    if ($Value -is [DateTimeOffset]) {
        $parsedUtc = $Value.ToUniversalTime()
    } elseif ($Value -is [DateTime]) {
        if ($Value.Kind -eq [DateTimeKind]::Unspecified) {
            $parsedUtc = [DateTimeOffset]::new([DateTime]$Value, [TimeSpan]::Zero).ToUniversalTime()
        } else {
            $parsedUtc = ([DateTimeOffset]$Value).ToUniversalTime()
        }
    } elseif ($Value -is [string]) {
        $styles = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
        $parsedUtc = [DateTimeOffset]::ParseExact($Value, "yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture, $styles)
    } else {
        throw "$Label deadline has unsupported parsed type: $($Value.GetType().FullName)"
    }
    $fixedUtc = [DateTimeOffset]::new(2026, 10, 24, 17, 1, 0, [TimeSpan]::Zero)
    if ($parsedUtc.UtcDateTime.Ticks -ne $fixedUtc.UtcDateTime.Ticks) {
        throw "$Label typed deadline differs from the fixed UTC deadline."
    }
    return $parsedUtc.UtcDateTime
}

$taskRoot = 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018'
$taskDir = Join-Path $taskRoot 'experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'
$reportDir = Join-Path $taskRoot 'reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp'
$lockPath = Join-Path $taskDir 'C6_STARTUP_RAMP_INPUT_LOCK_v1.json'
$contractPath = Join-Path $taskDir 'C6_STARTUP_RAMP_RUN_CONTRACT_v1.json'
$preparePath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARE_RESULT_v1.json'
$snapshotPath = Join-Path $taskDir 'C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat'
$sourceBindingPath = Join-Path $taskDir 'C6_SOURCE_BINDING_v1.json'
$firstReleasePath = Join-Path $taskDir 'C6_FIRST_PARENT_RELEASE_v1.json'
$tailContractPath = Join-Path $taskDir 'C6_TAIL11_RUN_CONTRACT_v1.json'
$tailBindingPath = Join-Path $taskDir 'C6_TAIL11_SOURCE_BINDING_v1.json'
$tailReleasePath = Join-Path $taskDir 'C6_TAIL11_PARENT_RELEASE_v1.json'
$tailReleaseContractPath = Join-Path $taskDir 'C6_TAIL11_PARENT_RELEASE_CONTRACT_v1.json'
$tailRunnerPath = Join-Path $taskDir 'run_c6_startup_ramp_tail11_v1.m'
$tailLauncherPath = Join-Path $taskDir 'RUN_C6_TAIL11_EXACT_v1.ps1'
$rawReviewPath = Join-Path $reportDir 'C6_FIRST_SCENE_RAW_REVIEW_v1.json'
$metadataReviewPath = Join-Path $reportDir 'C6_FIRST_SCENE_METADATA_OS_REVIEW_v1.json'
$osExitPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_OS_EXIT_v1.json'
$receiptPath = Join-Path $reportDir 'C6_FIRST_SCENE_EXECUTION_RECEIPT_v1.json'
$historyPath = Join-Path $reportDir 'C6_FIRST_SCENE_OUTER_INVOCATION_HISTORY_v1.json'
$stdoutPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_STDOUT_v1.log'
$stderrPath = Join-Path $reportDir 'C6_FIRST_SCENE_MATLAB_STDERR_v1.log'
$firstId = 'DL1018_VAL_T1_C00_W07'
$attemptDir = Join-Path $taskDir (Join-Path 'runs_c6_startup_ramp_v1' (Join-Path $firstId 'C6_STARTUP_PREDICTION_RAMP/attempt_01'))
foreach ($path in @($lockPath,$contractPath,$preparePath,$snapshotPath,$sourceBindingPath,$firstReleasePath,$tailReleaseContractPath,$tailRunnerPath,$tailLauncherPath,$rawReviewPath,$metadataReviewPath,$osExitPath,$receiptPath,$historyPath,$stdoutPath,$stderrPath,$attemptDir)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required C6 first-scene artifact is missing: $path" }
}
if (Test-Path -LiteralPath $tailBindingPath) { throw 'A tail binding already exists; preserve it and do not overwrite.' }
if (Test-Path -LiteralPath $tailReleasePath) { throw 'A parent tail release already exists; this binder never overwrites or creates releases.' }
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json
$tailReleaseContract = Get-Content -LiteralPath $tailReleaseContractPath -Raw | ConvertFrom-Json
$runContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $contractPath -Value $contract.limits.deadline_utc -Label 'C6 run contract'
$tailReleaseContractDeadline = Get-C6FixedDeadlineUtc -JsonPath $tailReleaseContractPath -Value $tailReleaseContract.required_values.deadline_utc -Label 'C6 tail release contract'
if ($runContractDeadline.Ticks -ne $tailReleaseContractDeadline.Ticks) { throw 'C6 run-contract and tail-release-contract deadlines differ.' }
if (($runContractDeadline - [DateTime]::UtcNow).TotalSeconds -lt (180 * 11 + 600)) { throw 'C6 fixed eleven-scene tail lacks the preregistered runtime and exit buffer before deadline.' }
$prep = Get-Content -LiteralPath $preparePath -Raw | ConvertFrom-Json
$firstRelease = Get-Content -LiteralPath $firstReleasePath -Raw | ConvertFrom-Json
$rawReview = Get-Content -LiteralPath $rawReviewPath -Raw | ConvertFrom-Json
$metadataReview = Get-Content -LiteralPath $metadataReviewPath -Raw | ConvertFrom-Json
$osExit = Get-Content -LiteralPath $osExitPath -Raw | ConvertFrom-Json
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
$history = Get-Content -LiteralPath $historyPath -Raw | ConvertFrom-Json
$runStatusPath = Join-Path $attemptDir 'run_status.json'
$runStartPath = Join-Path $attemptDir 'run_start.mat'
$rawPath = Join-Path $attemptDir 'raw_run.mat'
$markerPath = Join-Path $attemptDir 'first_plant_step.marker'
foreach ($path in @($runStatusPath,$runStartPath,$rawPath,$markerPath)) { if (-not (Test-Path -LiteralPath $path)) { throw "First-scene Plant artifact is missing: $path" } }
$runStatus = Get-Content -LiteralPath $runStatusPath -Raw | ConvertFrom-Json
$rawSha = & $sha $rawPath
$runStatusSha = & $sha $runStatusPath
$runStartSha = & $sha $runStartPath
$markerSha = & $sha $markerPath
$firstReleaseSha = & $sha $firstReleasePath
$osExitSha = & $sha $osExitPath
$receiptSha = & $sha $receiptPath
$historySha = & $sha $historyPath
$rawReviewSha = & $sha $rawReviewPath
$metadataReviewSha = & $sha $metadataReviewPath
if ($lock.schema -ne 'C6_STARTUP_RAMP_INPUT_LOCK_V1' -or $contract.schema -ne 'C6_STARTUP_RAMP_RUN_CONTRACT_V1' -or $prep.status -ne 'PREPARED_C6_STARTUP_RAMP_NO_PLANT_WAIT_PARENT_RELEASE_V1') { throw 'C6 prepared lock/contract/result identity changed.' }
if ($firstRelease.schema -ne 'C6_FIRST_PARENT_RELEASE_V1' -or $firstRelease.state -ne 'APPROVED_C6_FIRST_SCENE_V1' -or $firstRelease.scene_id -ne $firstId -or [int]$firstRelease.max_new_Plant -ne 1) { throw 'First-scene release does not authorize exactly the fixed first scene.' }
if ($runStatus.schema -ne 'C6_STARTUP_RAMP_RUN_STATUS_V1' -or $runStatus.status -ne 'RUN_COMPLETE_RAW_PENDING_AUDIT' -or $runStatus.scene_id -ne $firstId -or [int]$runStatus.plant_calls -ne 1 -or $runStatus.log_status -ne 'STABLE' -or [int]$runStatus.last_transition -ne 20000 -or [int]$runStatus.transitions -ne 20000 -or [int]$runStatus.state_samples -ne 20001 -or -not [bool]$runStatus.actual_weight_update_enabled -or -not [bool]$runStatus.actual_prediction_gradient_enabled -or $runStatus.raw_sha256 -ne $rawSha) { throw 'First C6 scene run status is not the exact complete stable one-call result.' }
if ($rawReview.status -ne 'PASS_C6_FIRST_RAW_ALL_EVENTS' -or [int]$rawReview.event_count -ne 1968 -or $rawReview.raw_sha256 -ne $rawSha -or $rawReview.prepared_snapshot_sha256 -ne (& $sha $snapshotPath)) { throw 'Independent C6 first-scene raw review is incomplete or mismatched.' }
if ($metadataReview.status -ne 'PASS_C6_FIRST_RAW_METADATA_NATURAL_OS0' -or [int]$metadataReview.event_count -ne 1968 -or [int]$metadataReview.natural_MATLAB_OS_exit_code -ne 0 -or [int]$metadataReview.actual_candidate_Plant -ne 1 -or [int]$metadataReview.new_Plant_in_this_audit -ne 0 -or [bool]$metadataReview.first_scene_review_is_tail_authorization) { throw 'Independent metadata/OS review is not a non-authorizing C6 review.' }
if ($osExit.schema -ne 'C6_FIRST_SCENE_OS_EXIT_V1' -or [int]$osExit.matlab_os_exit_code -ne 0 -or -not [bool]$osExit.natural_process_return -or $osExit.release_sha256 -ne $firstReleaseSha -or $osExit.raw_sha256 -ne $rawSha) { throw 'First-scene natural MATLAB exit receipt is not bound to this output.' }
if ($receipt.schema -ne 'C6_FIRST_SCENE_EXECUTION_RECEIPT_V1' -or [int]$receipt.matlab_os_exit_code -ne 0 -or [int]$receipt.shell_natural_exit_code -ne 0 -or $receipt.run_status -ne 'RUN_COMPLETE_RAW_PENDING_AUDIT' -or [int]$receipt.plant_calls -ne 1 -or $receipt.artifacts.raw.sha256 -ne $rawSha -or $receipt.artifacts.run_status.sha256 -ne $runStatusSha) { throw 'First-scene execution receipt is incomplete or mismatched.' }
if ([int]$history.preflight_path_error.MATLAB_launches -ne 0 -or [int]$history.preflight_path_error.Plant_calls -ne 0 -or [int]$history.preflight_path_error.outputs_created -ne 0 -or [int]$history.actual_execution.MATLAB_OS_exit_code -ne 0 -or [int]$history.actual_execution.natural_shell_process_exit_code -ne 0 -or $history.actual_execution.MATLAB_stdout_path -ne $stdoutPath -or $history.actual_execution.MATLAB_stderr_path -ne $stderrPath) { throw 'Outer invocation history is incomplete or reports a prior failed attempt.' }
$tailIds = [string[]]@($contract.scene_ids | Where-Object { $_ -ne $contract.first_scene_id })
if ($tailIds.Count -ne 11) { throw 'The frozen scene list does not yield exactly eleven tail scenes.' }
$bindingFileRefs = @(
    [ordered]@{role='tail_runner';path=$tailRunnerPath;sha256=(& $sha $tailRunnerPath)},
    [ordered]@{role='launcher';path=$tailLauncherPath;sha256=(& $sha $tailLauncherPath)},
    [ordered]@{role='tail_contract';path=$tailContractPath;sha256='DYNAMIC'},
    [ordered]@{role='parent_release_contract';path=$tailReleaseContractPath;sha256=(& $sha $tailReleaseContractPath)},
    [ordered]@{role='input_lock';path=$lockPath;sha256=(& $sha $lockPath)},
    [ordered]@{role='original_run_contract';path=$contractPath;sha256=(& $sha $contractPath)},
    [ordered]@{role='prepare_result';path=$preparePath;sha256=(& $sha $preparePath)},
    [ordered]@{role='prepared_snapshot';path=$snapshotPath;sha256=(& $sha $snapshotPath)},
    [ordered]@{role='first_scene_release';path=$firstReleasePath;sha256=$firstReleaseSha},
    [ordered]@{role='first_scene_source_binding';path=$sourceBindingPath;sha256=(& $sha $sourceBindingPath)},
    [ordered]@{role='tail_binding_builder';path=$PSCommandPath;sha256=(& $sha $PSCommandPath)}
)
$pilotRefs = [ordered]@{
    first_raw=[ordered]@{path=$rawPath;sha256=$rawSha}
    run_status=[ordered]@{path=$runStatusPath;sha256=$runStatusSha}
    run_start=[ordered]@{path=$runStartPath;sha256=$runStartSha}
    first_plant_step_marker=[ordered]@{path=$markerPath;sha256=$markerSha}
    matlab_os_exit=[ordered]@{path=$osExitPath;sha256=$osExitSha}
    execution_receipt=[ordered]@{path=$receiptPath;sha256=$receiptSha}
    outer_invocation_history=[ordered]@{path=$historyPath;sha256=$historySha}
    raw_review=[ordered]@{path=$rawReviewPath;sha256=$rawReviewSha}
    metadata_os_review=[ordered]@{path=$metadataReviewPath;sha256=$metadataReviewSha}
    stdout=[ordered]@{path=$stdoutPath;sha256=(& $sha $stdoutPath)}
    stderr=[ordered]@{path=$stderrPath;sha256=(& $sha $stderrPath)}
}
$b72 = [ordered]@{
    parent_review_path=$firstRelease.b72_parent_review_path; parent_review_sha256=$firstRelease.b72_parent_review_sha256
    raw_manifest_path=$firstRelease.b72_raw_manifest_path; raw_manifest_sha256=$firstRelease.b72_raw_manifest_sha256
    batch_status_path=$firstRelease.b72_batch_status_path; batch_status_sha256=$firstRelease.b72_batch_status_sha256
}
$binding = [ordered]@{
    schema='C6_TAIL11_SOURCE_BINDING_V1'; state='SOURCE_BOUND_C6_TAIL11_WAIT_PARENT_RELEASE_V1'
    created_utc=[DateTime]::UtcNow.ToString('o'); candidate=$contract.candidate; taskbook_sha256=$lock.taskbook_sha256
    input_lock_sha256=(& $sha $lockPath); original_run_contract_sha256=(& $sha $contractPath)
    prepare_result_sha256=(& $sha $preparePath); snapshot_sha256=(& $sha $snapshotPath)
    first_scene_release_sha256=$firstReleaseSha; tail_runner_sha256=(& $sha $tailRunnerPath)
    coordinate_mask=@(1,1,0); active_source_count=$lock.active_source_inventory.Count; shared_input_count=$lock.shared_input_files.Count
    tail_scene_ids=$tailIds; first_scene_review_is_tail_authorization=$false
    pilot_refs=$pilotRefs; b72=$b72; lock_upstream_refs=$lock.upstream_refs; upstream_refs=$lock.upstream_refs
    source_files=$bindingFileRefs; active_source_inventory=$lock.active_source_inventory; shared_input_files=$lock.shared_input_files
}
$tailContract = [ordered]@{
    schema='C6_TAIL11_RUN_CONTRACT_V1'; state='LOCKED_C6_TAIL11_WAIT_PARENT_RELEASE_V1'
    candidate=$contract.candidate; taskbook_sha256=$lock.taskbook_sha256; coordinate_mask=@(1,1,0)
    model=$contract.model; fixed_parameters=$contract.fixed_parameters; update_rule=$contract.algorithm_change
    scoring_comparator=$contract.scoring_comparator; original_run_contract_sha256=(& $sha $contractPath)
    input_lock_sha256=(& $sha $lockPath); prepare_result_sha256=(& $sha $preparePath); snapshot_sha256=(& $sha $snapshotPath)
    original_scene_ids=$contract.scene_ids; first_scene_id=$contract.first_scene_id; tail_scene_ids=$tailIds
    limits=[ordered]@{ max_new_Plant=11; max_total_Plant_including_pilot=12; max_output_bytes=[int64]$contract.limits.max_output_bytes; minimum_free_bytes=[int64]$contract.limits.minimum_free_bytes; per_scene_output_reserve_bytes=[int64]$contract.limits.per_scene_output_reserve_bytes; deadline_utc=$contract.limits.deadline_utc; seconds_per_remaining_scene_for_deadline_guard=180; process_exit_buffer_seconds=600 }
    b72_binding=[ordered]@{ raw_manifest_path=$firstRelease.b72_raw_manifest_path; raw_manifest_sha256=$firstRelease.b72_raw_manifest_sha256; parent_review_path=$firstRelease.b72_parent_review_path; parent_review_sha256=$firstRelease.b72_parent_review_sha256; batch_status_path=$firstRelease.b72_batch_status_path; batch_status_sha256=$firstRelease.b72_batch_status_sha256; input_lock_sha256=$lock.upstream_refs.b72_input_lock.sha256; run_contract_sha256=$lock.upstream_refs.b72_run_contract.sha256; prepare_result_sha256=$lock.upstream_refs.b72_prepare_result.sha256; release_sha256=$lock.upstream_refs.b72_release.sha256 }
    b72_complete_scene_count=72; first_scene_review=[ordered]@{ raw_review_sha256=$rawReviewSha; metadata_os_review_sha256=$metadataReviewSha; review_is_tail_authorization=$false; scientific_outcome_claimed=$false }
    first_scene_review_is_tail_authorization=$false; first_scene_outcome_used_as_authorization=$false
}
$binding.source_files[2].sha256 = 'PENDING'
$tailContractJson = $tailContract | ConvertTo-Json -Depth 16
$tailContractBytes = [Text.UTF8Encoding]::new($false).GetBytes($tailContractJson)
$tailContractSha = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($tailContractBytes)).ToLowerInvariant()
$binding.source_files[2].sha256 = $tailContractSha
$bindingJson = $binding | ConvertTo-Json -Depth 20
$bindingTemp = "$tailBindingPath.tmp"
$tailTemp = "$tailContractPath.tmp"
[IO.File]::WriteAllText($tailTemp, $tailContractJson, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($bindingTemp, $bindingJson, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $tailTemp -Destination $tailContractPath -Force
Move-Item -LiteralPath $bindingTemp -Destination $tailBindingPath
Write-Output ("C6 TAIL11 BINDING READY; FIRST_SCENE={0}; TAIL_SCENES={1}; TAIL_CONTRACT_SHA256={2}; BINDING_SHA256={3}; RELEASE_CREATED=false" -f $firstId,$tailIds.Count,$tailContractSha,(& $sha $tailBindingPath))