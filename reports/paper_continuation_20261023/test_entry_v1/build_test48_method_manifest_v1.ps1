$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$outPath = Join-Path $root 'reports/paper_continuation_20261023/test_entry_v1/TEST_METHOD_SOURCE_MANIFEST_v1.json'
$sha = { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$legacyManifestShas = @(
    '2ccf22e96f9c1a4a3e63403b56b2915bd7b7e038d761253077a75e29b2118199',
    '49956de48385f2a8d19e9b6b54b1414541715e50dd31adb415d4455755edf1fe',
    '6638b2a847536079858c98f57efa17f87d36e3cbee314abe8ad68fd39a744053',
    'e857629e032a7803ad641e81ea581307dcf2f66530e9e5728ce490909d368efe'
)
$frozenManifestSha = '66f6d2e0c042dff9aa07e75f6d0443d38d694097495b30d551dfd94f2c90919c'
$existingManifestSha = ''
if (Test-Path -LiteralPath $outPath) {
    $existingManifestSha = & $sha $outPath
    if ($existingManifestSha -notin $legacyManifestShas -and $existingManifestSha -ne $frozenManifestSha) {
        throw 'Refusing to replace a source manifest outside the reviewed states.'
    }
}
$identityPath = 'reports/paper_continuation_20261023/test_readiness_readonly/TEST_METHOD_IDENTITIES_v1.json'
$readinessPath = 'reports/paper_continuation_20261023/test_readiness_readonly/TEST_READINESS_SOURCE_FINDINGS_v1_ZH.md'
$protocolPath = 'reports/paper_continuation_20261023/TEST48_CONDITIONAL_PROTOCOL_DRAFT_ZH.md'
if ((& $sha $identityPath) -ne '569238514cea604a3f613de6a99c161f0142dfdff3e9b246c728597ee3060669') { throw 'Method identity table SHA changed.' }
if ((& $sha $readinessPath) -ne '972b30399b471bab4fba74cbabc87797a08e28f7ea051bcc299f3d9c1ba940e1') { throw 'Readiness report SHA changed.' }
$identity = Get-Content -Raw -LiteralPath $identityPath | ConvertFrom-Json
$methods = @()
foreach ($m in $identity.methods) {
    $lockPath = ''; $contractPath = ''; $snapshotPath = ''; $lockSha = ''; $contractSha = ''
    $runtimeRefs = @(); $modelObj = $null
    if ($m.method_id -eq 'B_TRACEABLE') {
        $lockPath = $m.input_lock.path; $snapshotPath = $m.cfg_opts_snapshot.path
        $lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
        $runtimeRefs = @($lock.active_source_inventory | ForEach-Object { [pscustomobject]@{ role=$_.role; path=$_.path; sha256=$_.sha256 } })
        $contractPath = 'experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json'
    } elseif ($m.method_id -eq 'C5_M110') {
        $lockPath = $m.input_lock.path; $snapshotPath = $m.cfg_opts_snapshot.path
        $lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
        $runtimeRefs = @($lock.active_source_inventory | ForEach-Object { [pscustomobject]@{ role=$_.role; path=$_.path; sha256=$_.sha256 } })
        $runtimeRefs += @($lock.shared_input_files | ForEach-Object { [pscustomobject]@{ role=$_.role; path=$_.path; sha256=$_.sha256 } })
        $contractPath = 'experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_RUN_CONTRACT_v3.json'
        $modelObj = $m.model_identity
    } elseif ($m.method_id -in @('C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION')) {
        $lockPath = $m.input_lock.path; $snapshotPath = $m.cfg_opts_snapshot.path
        $lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
        $runtimeRefs = @($lock.active_source_inventory | ForEach-Object { [pscustomobject]@{ role=$_.role; path=$_.path; sha256=$_.sha256 } })
        $runtimeRefs += @($lock.shared_input_files | ForEach-Object { [pscustomobject]@{ role=$_.role; path=$_.path; sha256=$_.sha256 } })
        $contractPath = Join-Path (Split-Path $lockPath -Parent) 'C5_ABLATION_DEV72_RUN_CONTRACT_v3.json'
        $modelInput = @($lock.shared_input_files | Where-Object { $_.role -eq 'model_mat' })
        $normalizerInput = @($lock.shared_input_files | Where-Object { $_.role -eq 'normalizer_npz' })
        if ($modelInput.Count -ne 1 -or $normalizerInput.Count -ne 1) { throw "C5 shared model/normalizer refs are incomplete for $($m.method_id)" }
        $modelObj = [pscustomobject]@{
            model_id='DSSM14'; model_mat_path=$modelInput[0].path; model_mat_sha256=$modelInput[0].sha256
            normalizer_shared_path=$normalizerInput[0].path; normalizer_sha256=$normalizerInput[0].sha256
        }
    } elseif ($m.method_id -like 'CORRECTED_*') {
        $runtimeRoot = $m.runtime.root
        $runtimeRefs = @(Get-ChildItem -LiteralPath $runtimeRoot -Recurse -File -Filter '*.m' | Sort-Object Name | ForEach-Object {
            [pscustomobject]@{ role='corrected_runtime_m'; path=$_.FullName; sha256=(& $sha $_.FullName) }
        })
        $treeParts = foreach ($r in $runtimeRefs) { $r.path + ':' + $r.sha256 + [char]10 }
        $treeSha = ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes(($treeParts -join ''))))).ToLowerInvariant()
        if ($treeSha -ne $m.runtime.runtime_tree_sha256) { throw "Corrected runtime tree mismatch for $($m.method_id): $treeSha" }
        $snapshotPath = $m.cfg_opts_snapshot_example.path
        $modelObj = $m.model
        if ($m.method_id -eq 'CORRECTED_KAN14_G12_R32') {
            $kanErratumPath = 'reports/paper_continuation_20261023/PARENT_KAN14_FIELD_COUNT_ERRATUM_v1.json'
            $kanErratum = Get-Content -Raw -LiteralPath $kanErratumPath | ConvertFrom-Json
            if ($kanErratum.status -ne 'PASS_ACTUAL_KAN14_MODEL_SCHEMA_RECOUNT' -or
                $kanErratum.model_sha256 -ne $modelObj.model_mat_sha256 -or
                $kanErratum.actual_field_count -ne 15 -or $kanErratum.TEST_accessed -or $kanErratum.Plant_started) {
                throw 'Actual KAN14 field-count erratum does not bind the locked model or the 15-field no-TEST audit.'
            }
            $modelObj.model_field_count = [int]$kanErratum.actual_field_count
            $modelObj.model_schema_note = 'Actual KAN14 MAT has 15 named model fields, including silu_unclipped; field-count correction is bound by PARENT_KAN14_FIELD_COUNT_ERRATUM_v1.json.'
        }
    } else { throw "Unexpected method id: $($m.method_id)" }
    if ($lockPath) { $lockSha = & $sha $lockPath; $contractSha = & $sha $contractPath }
    foreach ($r in $runtimeRefs) {
        if (-not (Test-Path -LiteralPath $r.path -PathType Leaf)) { throw "Missing source $($r.path)" }
        if ((& $sha $r.path) -ne $r.sha256) { throw "Source SHA mismatch: $($r.path)" }
    }
    $modelRefs = @()
    if ($modelObj -and $modelObj.PSObject.Properties.Name -contains 'model_mat_path') {
        $modelRefs += [pscustomobject]@{ role='model_mat'; path=$modelObj.model_mat_path; sha256=$modelObj.model_mat_sha256 }
    }
    if ($modelObj -and $modelObj.PSObject.Properties.Name -contains 'checkpoint_path') {
        $modelRefs += [pscustomobject]@{ role='checkpoint'; path=$modelObj.checkpoint_path; sha256=$modelObj.checkpoint_sha256 }
    }
    if ($modelObj -and $modelObj.PSObject.Properties.Name -contains 'normalizer_path') {
        $nsha = if ($modelObj.PSObject.Properties.Name -contains 'normalizer_file_sha256') { $modelObj.normalizer_file_sha256 } else { $modelObj.normalizer_sha256 }
        $modelRefs += [pscustomobject]@{ role='normalizer'; path=$modelObj.normalizer_path; sha256=$nsha }
    } elseif ($modelObj -and $modelObj.PSObject.Properties.Name -contains 'normalizer_shared_path') {
        $modelRefs += [pscustomobject]@{ role='normalizer'; path=$modelObj.normalizer_shared_path; sha256=$modelObj.normalizer_sha256 }
    }
    foreach ($r in $modelRefs) {
        if (-not (Test-Path -LiteralPath $r.path -PathType Leaf)) { throw "Missing model file $($r.path)" }
        if ((& $sha $r.path) -ne $r.sha256) { throw "Model input SHA mismatch: $($r.path)" }
    }
    $refs = @()
    if ($lockPath) { $refs += [pscustomobject]@{ role='input_lock'; path=(Join-Path $root $lockPath); sha256=$lockSha } }
    if ($contractPath) { $refs += [pscustomobject]@{ role='run_contract'; path=(Join-Path $root $contractPath); sha256=$contractSha } }
    if ($snapshotPath) { $refs += [pscustomobject]@{ role='cfg_opts_snapshot'; path=$snapshotPath; sha256=(& $sha $snapshotPath) } }
    $refs += $runtimeRefs; $refs += $modelRefs
    $aliases = @{ B_TRACEABLE='BTR'; CORRECTED_DSSM14_G12_R32='DSSM'; CORRECTED_KAN14_G12_R32='KAN'; C5_M110='C5M110'; C5_FREEZE_TRAINED_W0='C5FREEZE'; C5_NO_DELAYED_PREDICTION='C5NOPRED' }
    $treePath = ''; $treeShaOut = ''
    if ($m.runtime.PSObject.Properties.Name -contains 'root') { $treePath = $m.runtime.root }
    if ($m.runtime.PSObject.Properties.Name -contains 'runtime_tree_sha256') { $treeShaOut = $m.runtime.runtime_tree_sha256 }
    $schemaNote = if ($m.method_id -like 'CORRECTED_*') { 'Historical run_start has top-level cfg,opts,meta,scene,sceneMeta,spec; no runStart variable.' } else { 'Prepared MATLAB v7.3 snapshot; C5 modelIdentity fields are W0_sha256,input_dim,model_id,normalizer_arrays_sha256,selected_step,window.' }
    $methods += [pscustomobject][ordered]@{
        method_id=$m.method_id; order=$methods.Count+1; alias=$aliases[$m.method_id]; role=$m.role
        input_lock_path=$(if ($lockPath) { Join-Path $root $lockPath } else { '' }); input_lock_sha256=$lockSha
        run_contract_path=$(if ($contractPath) { Join-Path $root $contractPath } else { '' }); run_contract_sha256=$contractSha
        cfg_opts_snapshot_path=$snapshotPath; cfg_opts_snapshot_sha256=$(if ($snapshotPath) { & $sha $snapshotPath } else { '' })
        runtime_tree_path=$treePath; runtime_tree_sha256=$treeShaOut; source_refs=@($refs); model_identity=$modelObj; model_refs=@($modelRefs); cfg_opts_schema=$schemaNote
    }
}
$sharedRefs = @()
$sharedPaths = @(
    @('readiness_report',$readinessPath,'972b30399b471bab4fba74cbabc87797a08e28f7ea051bcc299f3d9c1ba940e1'),
    @('method_identity_table',$identityPath,'569238514cea604a3f613de6a99c161f0142dfdff3e9b246c728597ee3060669'),
    @('protocol_draft',$protocolPath,'42715535e67ecee826dc493bd46a32e29f27d55c28b27b7db8fa04f5bbd05ccd'),
    @('scene_specs','configs/scene_specs.csv','d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3'),
    @('effective_config','configs/effective_config.mat','cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f'),
    @('current_scene_generator','matlab/scenes/make_scenes_dl1018.m','7d11b4ebf63105b016c67f4b3c427282b35dafa53280ef2daf5578a6a16bb9ec'),
    @('corrected_fixed_scene_generator','C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/REFERENCE_FIX_FULL72_20261021_022342_313/sources/reference_fixed/make_scenes_dl1018.m','454106ad22f44ebf5a2210fbd50a7672b5508e550ebfc80c16158e5cdbee544a'),
    @('dev_input_equivalence_metadata_erratum','reports/paper_continuation_20261023/DEV_INPUT_EQUIVALENCE_METADATA_ERRATUM_ZH.md','d4b781909f784f553c79c28a4cf14fbac2dc8b2d8369a3f3c5c7abd7becaeabd'),
    @('resource_creation_time_observation','reports/paper_continuation_20261023/RESOURCE_CREATION_TIME_OBSERVATION_v2.json','94d094050d3ce3dc9f5621161157df0605edb4e020cb90315a2af84fcff86158'),
    @('test48_score_statistics_contract','reports/paper_continuation_20261023/TEST48_SCORE_STATISTICS_CONTRACT_v1.json','c7d2983a031b56b16950ede637cce598f6c169b1fea6dc3a092f4337489d992c'),
    @('kan14_field_count_erratum','reports/paper_continuation_20261023/PARENT_KAN14_FIELD_COUNT_ERRATUM_v1.json','c2b2e97b38f7ba051a8c32ddd983d8a87ccc67799793f89816a5ed30c78883fa')
)
foreach ($x in $sharedPaths) {
    if (-not (Test-Path -LiteralPath $x[1] -PathType Leaf)) { throw "Missing shared source $($x[1])" }
    $actual = & $sha $x[1]; if ($actual -ne $x[2]) { throw "Shared SHA mismatch: $($x[1])" }
    $full = if ([IO.Path]::IsPathRooted($x[1])) { $x[1] } else { Join-Path $root $x[1] }
    $sharedRefs += [pscustomobject]@{ role=$x[0]; path=$full; sha256=$actual }
}
$manifest = [ordered]@{
    schema='TEST48_METHOD_SOURCE_MANIFEST_V1'; status='CODE_ONLY_SOURCE_IDENTITY; TEST_NOT_OPENED'
    taskbook_sha256='e0b58545fda8d779f2672afa50de976596ac510f82f6aa83493ed7583216130b'
    code_only_release_sha256='75f32b259ab3fe901b52ac1f4162f0ea04ee3bb1145c9b958fb5e311a24f1b58'
    method_identity_table_sha256=(& $sha $identityPath); readiness_report_sha256=(& $sha $readinessPath)
    parent_actual_46_file_refs_check_sha256='370ee51f2db150a7fbcec7d1fcd95222ec52f81763170e0ee5444b4744691da2'
    test_accessed=$false; plant_started=$false; training_steps=0; methods=$methods; shared_source_refs=$sharedRefs
    source_path_note='Corrected pair sources remain read-only at their original runtime paths. No TEST scene arrays or outcome raws were read.'
}
$renderedManifest = ($manifest | ConvertTo-Json -Depth 14)+[Environment]::NewLine
$manifestBytes = [Text.UTF8Encoding]::new($false).GetBytes($renderedManifest)
$hasher = [Security.Cryptography.SHA256]::Create()
try { $renderedManifestSha = ([BitConverter]::ToString($hasher.ComputeHash($manifestBytes))).Replace('-','').ToLowerInvariant() }
finally { $hasher.Dispose() }
if ($existingManifestSha -eq $frozenManifestSha) {
    if ($renderedManifestSha -ne $existingManifestSha) { throw 'Current source manifest is already frozen; reconstructed content differs.' }
} elseif (-not $existingManifestSha -or $existingManifestSha -in $legacyManifestShas) {
    [IO.File]::WriteAllText($outPath,$renderedManifest,[Text.UTF8Encoding]::new($false))
} else {
    throw 'Refusing to replace the frozen source manifest.'
}
Write-Output ("TEST_METHOD_SOURCE_MANIFEST_v1.json SHA256=" + (& $sha $outPath))
