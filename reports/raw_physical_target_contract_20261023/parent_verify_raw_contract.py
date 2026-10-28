"""Independent fixed-log comparison; no updates, fitting, or rollout."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFLIGHT = ROOT / 'reports/delayed_innovation_design_audit_20261023/construction/INPUT_PREFLIGHT.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4194304), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    assert digest(PREFLIGHT) == 'd704bc0d7e8900caf273dce0ad18224addaa988aa8ea76f0b089499db5bcaa25'
    records = json.loads(PREFLIGHT.read_text(encoding='utf-8'))['raw_records']
    rows = []
    for record in records:
        path = Path(record['raw_path'])
        signature = (path.stat().st_size, path.stat().st_mtime_ns)
        assert digest(path) == record['expected_sha256']
        with h5py.File(path, 'r') as f:
            log = f['log']
            valid = np.array(log['stage1_position_event_inference_valid']).reshape(-1).astype(bool)
            phi = np.array(log['stage1_position_event_phi_33']).T
            beta = np.array(log['stage1_position_event_beta']).reshape(-1)
            velocity = np.array(log['state']).T[:, 3:6]
            af = np.array(log['stage1_position_pcf_a_f_mps2']).T
            w = np.array(log['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1)
            time = np.array(log['transition_time']).reshape(-1)
        event = np.flatnonzero(valid)
        assert np.array_equal(event, np.arange(320, 19991, 10))
        j, k = event[:-1], event[1:]
        target = np.array([(velocity[b]-velocity[a])/.01-af[a:b].mean(0) for a, b in zip(j, k)])
        z = np.array([phi[a] @ w[n+1] for n, a in enumerate(j)])
        applied = beta[j, None]*np.clip(z, -3, 3)
        gr = phi[j, :, None]*(z-target)[:, None, :]
        ga = phi[j, :, None]*(beta[j, None]*(np.abs(z)<3)*(applied-target))[:, None, :]
        selections = {'OLD_BETA_LT1': beta[j]<1, 'OLD_BETA_EQ1': beta[j]==1,
                      'CURRENT_0P33_1P8': time[k]<1.8,
                      'CURRENT_1P8_5': (time[k]>=1.8)&(time[k]<5),
                      'CURRENT_5_20': time[k]>=5}
        phases = []
        for phase, keep in selections.items():
            assert keep.any()
            gradient_diff = np.abs(gr[keep]-ga[keep])
            p = {'phase': phase, 'pairs': int(keep.sum()),
                 'raw_error_element_rmse_mps2': float(np.sqrt(np.mean((z[keep]-target[keep])**2))),
                 'applied_error_element_rmse_mps2': float(np.sqrt(np.mean((applied[keep]-target[keep])**2))),
                 'prediction_max_abs_difference_mps2': float(np.abs(z[keep]-applied[keep]).max()),
                 'gradient_max_abs_difference': float(gradient_diff.max()),
                 'raw_saturated_axis_entries': int((np.abs(z[keep])>3).sum()),
                 'exact_kink_axis_entries': int((np.abs(z[keep])==3).sum())}
            if phase in ('OLD_BETA_EQ1', 'CURRENT_5_20'):
                assert p['raw_saturated_axis_entries'] == p['exact_kink_axis_entries'] == 0
                assert p['prediction_max_abs_difference_mps2'] == p['gradient_max_abs_difference'] == 0
                assert p['raw_error_element_rmse_mps2'] == p['applied_error_element_rmse_mps2']
            phases.append(p)
        assert signature == (path.stat().st_size, path.stat().st_mtime_ns)
        assert digest(path) == record['expected_sha256']
        rows.append({'scene_id': record['scene_id'], 'task': record['task'], 'wind_band': record['wind_band'],
                     'raw_sha256': record['expected_sha256'], 'first_current_index': int(k[0]),
                     'first_old_beta_eq1_current_index': int(k[beta[j]==1][0]), 'phases': phases})
    out = {'status': 'PASS_PARENT_RAW_APPLIED_CONTRACT_INDEPENDENT_CHECK', 'raw_count': len(rows),
           'script_sha256': digest(Path(__file__)), 'rows': rows,
           'resource_scope': {'Plant': 0, 'MATLAB': 0, 'optimizer': 0, 'training': 0, 'TEST': 0},
           'limits': 'Equality on frozen recorded states and weights does not imply equality of counterfactual rollouts or rule out adding a prediction term.'}
    with (HERE/'PARENT_RAW_CONTRACT_CHECK.json').open('x', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': out['status'], 'raw_count': len(rows), 'phase_rows': sum(len(r['phases']) for r in rows)}))


if __name__ == '__main__':
    main()
