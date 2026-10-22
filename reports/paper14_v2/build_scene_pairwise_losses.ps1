if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Run with PowerShell 7 or newer.' }

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$culture = [Globalization.CultureInfo]::InvariantCulture
$inputs = @(
    @{ Path = 'reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv'; Sha256 = 'b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137' },
    @{ Path = 'experiments/paper14_v2_round1_frozen_w0_screen/reports/round1_screen_results.csv'; Sha256 = '2090abdc99b386650c6f5debf75974b34943dfa2b45129fe913efeafb1214dc4' },
    @{ Path = 'experiments/paper14_v2_round2_pcf_screen/reports/round2_screen_results.csv'; Sha256 = '197cef3db125b229972e72b6ac4bfe3d0c34b85ab2351184dc3ce460b79d3443' },
    @{ Path = 'experiments/paper14_v2_round3_xy_pcf_screen/reports/round3_xy_screen_results.csv'; Sha256 = 'def5bcdee85a46f93bed8f1a881565b125c5d79485af1b32f4cd9d282637774d' }
)
foreach ($input in $inputs) {
    $path = Join-Path $root $input.Path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing source: $($input.Path)" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $input.Sha256) { throw "Source SHA mismatch: $($input.Path)" }
}

$losses = [Collections.Generic.List[object]]::new()
$comparisons = [Collections.Generic.List[object]]::new()
function Add-Comparison {
    param(
        [string]$Study, [string]$Candidate, [string]$Comparator,
        [object[]]$Rows, [string]$CandidateQ, [string]$ComparatorQ,
        [string]$SceneColumn = 'scene_id'
    )
    $wins = 0; $ties = 0; $lossCount = 0
    $deltas = [Collections.Generic.List[double]]::new()
    foreach ($row in $Rows) {
        $candidateValue = [double]::Parse([string]$row.$CandidateQ, $culture)
        $referenceValue = [double]::Parse([string]$row.$ComparatorQ, $culture)
        $delta = $candidateValue - $referenceValue
        $deltas.Add($delta)
        if ($delta -lt -1e-12) { $wins++; continue }
        if ($delta -le 1e-12) { $ties++; continue }
        $lossCount++
        $scene = [string]$row.$SceneColumn
        $match = [regex]::Match($scene, '_W(\d{2})$')
        if (-not $match.Success) { throw "Cannot derive wind band from $scene" }
        $wind = [int]$match.Groups[1].Value
        $band = if ($wind -le 8) { 'W00_W08' } elseif ($wind -le 14) { 'W09_W14' } else { 'W15' }
        $losses.Add([pscustomobject]@{
            study = $Study; candidate = $Candidate; comparator = $Comparator
            split = $row.split; task = $row.task; wind_group = $band; scene_id = $scene
            q_candidate_m = $candidateValue.ToString('R', $culture)
            q_comparator_m = $referenceValue.ToString('R', $culture)
            delta_candidate_minus_comparator_mm = ($delta * 1000).ToString('R', $culture)
            failure_rule = 'candidate Q - comparator Q > 1e-12 m'
        })
    }
    $comparisons.Add([pscustomobject]@{
        study = $Study; candidate = $Candidate; comparator = $Comparator; n = $Rows.Count
        wins = $wins; ties = $ties; losses = $lossCount
        mean_delta_candidate_minus_comparator_mm = [math]::Round((($deltas | Measure-Object -Average).Average * 1000), 6)
    })
}

$benchmark = Import-Csv (Join-Path $root $inputs[0].Path)
Add-Comparison 'Existing current14 72-scene benchmark' 'corrected DSSM14' 'B' @($benchmark | Where-Object method_id -eq 'CORRECTED_TRAIN_DSSM14_G12_R32') 'candidate_Q_0_20_m' 'B_Q_0_20_m' 'source_scene_id'
Add-Comparison 'Existing current14 72-scene benchmark' 'corrected KAN14' 'B' @($benchmark | Where-Object method_id -eq 'CORRECTED_TRAIN_KAN14_G12_R32') 'candidate_Q_0_20_m' 'B_Q_0_20_m' 'source_scene_id'
$r1 = Import-Csv (Join-Path $root $inputs[1].Path)
Add-Comparison 'R1 frozen W0 screen' 'frozen-W0 coupled branch' 'PCF-on' $r1 'q_off_0_20_m' 'q_on_0_20_m'
Add-Comparison 'R1 frozen W0 screen' 'frozen-W0 coupled branch' 'B' $r1 'q_off_0_20_m' 'q_b_0_20_m'
$r2 = Import-Csv (Join-Path $root $inputs[2].Path)
Add-Comparison 'R2 whole-PCF-off screen' 'PCF-off' 'PCF-on' $r2 'off_q_0_20_m' 'on_q_0_20_m'
Add-Comparison 'R2 whole-PCF-off screen' 'PCF-off' 'B' $r2 'off_q_0_20_m' 'b_q_0_20_m'
$r3 = Import-Csv (Join-Path $root $inputs[3].Path)
Add-Comparison 'R3 XY eta-mask screen' 'DSSM14_PCF_XY' 'B' $r3 'xy_q_0_20_m' 'b_q_0_20_m'
Add-Comparison 'R3 XY eta-mask screen' 'DSSM14_PCF_XY' 'PCF-on' $r3 'xy_q_0_20_m' 'on_q_0_20_m'
Add-Comparison 'R3 XY eta-mask screen' 'DSSM14_PCF_XY' 'PCF-off' $r3 'xy_q_0_20_m' 'off_q_0_20_m'

if ($losses.Count -ne 120) { throw "Unexpected pairwise loss row count: $($losses.Count); expected 120." }
$output = Join-Path $PSScriptRoot 'SCENE_PAIRWISE_LOSSES_20261022.csv'
$losses | Sort-Object study, candidate, comparator, split, task, scene_id | Export-Csv -LiteralPath $output -NoTypeInformation -Encoding utf8NoBOM
$check = Import-Csv -LiteralPath $output
if ($check.Count -ne 120 -or @($check | Where-Object { [double]::Parse($_.delta_candidate_minus_comparator_mm, $culture) -le 0 }).Count -gt 0) {
    throw 'Generated loss table failed validation.'
}
[pscustomobject]@{
    status = 'PASS'; source_files_sha_verified = $inputs.Count
    pairwise_loss_rows = $check.Count; comparisons = @($comparisons)
    output_sha256 = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json -Depth 5
