"""Compare worker tables against independent raw reconstruction, without rerun."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


parent_path = HERE/'PARENT_RAW_CONTRACT_CHECK.json'
worker_path = HERE/'construction/RAW_PHYSICAL_TARGET_GROUPS.csv'
parent = json.loads(parent_path.read_text(encoding='utf-8'))
rows = list(csv.DictReader(worker_path.open(encoding='utf-8', newline='')))
indexed = {(r['scope'], r['group_id'], r['phase'], r['axis']): r for r in rows}
assert len(rows) == len(indexed) == 504
phase_map = {'OLD_BETA_LT1': 'OLD_BETA_LT_1', 'OLD_BETA_EQ1': 'OLD_BETA_EQ_1',
             'CURRENT_0P33_1P8': 'CURRENT_033_18', 'CURRENT_1P8_5': 'CURRENT_18_5',
             'CURRENT_5_20': 'CURRENT_5_20'}
diffs = []
for record in parent['rows']:
    for phase in record['phases']:
        r = indexed['RUN', record['scene_id'], phase_map[phase['phase']], 'ALL']
        assert int(r['n_pairs']) == phase['pairs']
        assert int(r['raw_saturated_axis_count']) == phase['raw_saturated_axis_entries']
        for wk, pk in [('raw_rmse_mps2', 'raw_error_element_rmse_mps2'),
                       ('applied_rmse_mps2', 'applied_error_element_rmse_mps2')]:
            delta = abs(float(r[wk])-phase[pk])
            assert delta < 2e-12, (record['scene_id'], phase['phase'], wk, delta)
            diffs.append(delta)
        if phase['phase'] in ('OLD_BETA_EQ1', 'CURRENT_5_20'):
            assert float(r['prediction_delta_rmse_mps2']) == 0
            assert float(r['mean_pair_gradient_delta_l2']) == 0
            assert float(r['summed_gradient_delta_l2']) == 0
for scope, group, phase, axis in indexed:
    if axis != 'ALL':
        continue
    r = indexed[scope, group, phase, axis]
    for kind in ('raw', 'applied'):
        squared = [float(indexed[scope, group, phase, a][kind+'_rmse_mps2'])**2 for a in 'XYZ']
        assert abs(float(r[kind+'_rmse_mps2'])-(sum(squared)/3)**.5) < 2e-12
        for a in ('X', 'Y', 'Z', 'ALL'):
            ar = indexed[scope, group, phase, a]
            assert abs(float(ar[kind+'_per_scalar_half_squared_error_mean'])-.5*float(ar[kind+'_rmse_mps2'])**2)<2e-12
result = {'status': 'PASS_INDEPENDENT_TABLE_NUMERICAL_RECOVERY_CHECK',
          'worker_process_exit_code': 1, 'worker_process_success': False,
          'numerical_table_usable': True, 'unique_rows': len(rows),
          'independent_run_phase_comparisons': 60, 'rmse_comparisons': len(diffs),
          'max_rmse_difference_mps2': max(diffs),
          'worker_csv_sha256': digest(worker_path), 'independent_raw_check_sha256': digest(parent_path),
          'script_sha256': digest(Path(__file__)),
          'limits': 'Table recovery is not a successful worker exit or a new rollout result.'}
with (HERE/'PARENT_TABLE_RECOVERY_CHECK.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps(result))
