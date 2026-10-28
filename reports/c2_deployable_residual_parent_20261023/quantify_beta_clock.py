"""Quantify the frozen clock discrepancy on the same recorded ON1 states.

This changes neither recorded state nor controller; it does not estimate Q.
"""
import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    out = HERE/'BETA_CLOCK_SAME_STATE_QUANTIFICATION.json'
    assert not out.exists()
    config = ROOT/'configs/effective_config.mat'
    assert sha(config) == 'cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f'
    cfg = loadmat(config, simplify_cells=True)['cfg']
    T, h = float(cfg['rbf']['position']['beta_rise_time']), float(cfg['plant']['dt'])
    table = ROOT/'experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv'
    with table.open(encoding='utf-8-sig', newline='') as f:
        data = list(csv.DictReader(f))
    on = [r for r in data if r['condition'] == 'ON1']
    b = {r['scene_id']: r for r in data if r['condition'] == 'B'}
    results = []
    for row in on:
        p, bp = Path(row['raw_path']), Path(b[row['scene_id']]['raw_path'])
        before, bb = p.stat(), bp.stat()
        assert sha(p) == row['raw_sha256'] and sha(bp) == b[row['scene_id']]['raw_sha256']
        with h5py.File(p, 'r') as f, h5py.File(bp, 'r') as base:
            g = f['log']
            t = np.asarray(g['transition_time']).ravel()
            ids = np.flatnonzero(np.asarray(g['stage1_position_event_inference_valid']).ravel())
            beta = np.asarray(g['stage1_position_event_beta']).ravel()[ids]
            target = np.minimum((ids+1)*h/T, 1.)
            expected = np.clip(t[ids]/T, 0., 1.)
            b_beta = np.asarray(base['log/position_event_beta']).ravel()[ids]
            assert len(ids) == 1968 and np.max(np.abs(beta-expected)) < 1e-14
            assert np.max(np.abs(target-b_beta)) < 1e-14
            delta = target-beta
            assert np.min(delta) >= -1e-15
            assert np.max(np.abs(delta[t[ids] >= T])) == 0
            raw = np.asarray(g['stage1_position_event_raw_acceleration_mps2']).T[ids]
            applied = np.asarray(g['stage1_position_event_applied_acceleration_mps2']).T[ids]
            assert np.max(np.abs(applied-beta[:, None]*np.clip(raw, -3, 3))) < 1e-14
            du = delta[:, None]*np.clip(raw, -3, 3)
            phi = np.asarray(g['stage1_position_event_phi_33']).T[ids]
            s = np.asarray(g['stage1_position_pcf_event_s_coord_eff_mps']).T[ids]
            dt = np.asarray(g['stage1_position_event_dt_s']).ravel()[ids]
            dw = -12*dt[:, None, None]*delta[:, None, None]*phi[:, :, None]*s[:, None, :]
            results.append({'scene_id': row['scene_id'], 'valid_events': len(ids),
                            'different_beta_events': int(np.sum(delta > 1e-14)),
                            'max_beta_difference': float(delta.max()),
                            'same_state_applied_delta_max_abs_mps2': float(np.max(np.abs(du))),
                            'same_state_applied_delta_axis_rmse_mps2': np.sqrt(np.mean(du**2, axis=0)).tolist(),
                            'same_state_one_step_unprojected_weight_delta_max_fro': float(np.max(np.linalg.norm(dw, axis=(1, 2)))),
                            'raw_sha256': row['raw_sha256'], 'B_raw_sha256': b[row['scene_id']]['raw_sha256']})
        assert (p.stat().st_size, p.stat().st_mtime_ns) == (before.st_size, before.st_mtime_ns)
        assert (bp.stat().st_size, bp.stat().st_mtime_ns) == (bb.st_size, bb.st_mtime_ns)
    result = {'status': 'PASS_CONFIRMED_CLOCK_DIFFERENCE_ALL12', 'beta_rise_time_s': T,
              'plant_dt_s': h, 'rows': results,
              'interpretation': 'Same-state output and one-step unprojected update differences only; no closed-loop propagation or position-Q causal bound.',
              'C1_note': 'ON1 and ONC used the same original beta clock; this B-versus-ON clock discrepancy cannot explain their C1 performance difference by itself.',
              'Plant_called': False, 'TEST_accessed': False}
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'max_applied_delta_mps2': max(r['same_state_applied_delta_max_abs_mps2'] for r in results),
                      'different_events_each_run': sorted({r['different_beta_events'] for r in results})}))


if __name__ == '__main__':
    main()
