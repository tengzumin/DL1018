"""Read frozen C5 DEV72 attitude tracking; no new simulation or TEST reads."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'reports/paper_continuation_20261023/c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json'
OUT = Path(__file__).with_name('C5_DEV72_ATTITUDE_BASELINE_v1.json')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parent_hash = sha(PARENT)
    assert parent_hash == 'bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab'
    parent = json.loads(PARENT.read_text(encoding='utf-8-sig'))
    assert len(parent['rows']) == 72
    rows = []
    for entry in parent['rows']:
        source = entry['C5_metrics']
        p = Path(source['path'])
        assert p.is_relative_to(ROOT) and sha(p) == source['sha256']
        with h5py.File(p, 'r') as f:
            g = f['log']
            x = g['state'][()].T[:-1]
            ref = g['filtered_attitude_reference'][()].T
            rr = g['filtered_attitude_rate'][()].T
            t = g['time'][()].reshape(-1)[:-1]
            assert x.shape == (20000, 12) and ref.shape == rr.shape == (20000, 3)
            assert np.isfinite(x).all() and np.isfinite(ref).all() and np.isfinite(rr).all()
            R = Rotation.from_euler('ZYX', x[:, [8, 7, 6]]).as_matrix()
            Rd = Rotation.from_euler('ZYX', ref[:, [2, 1, 0]]).as_matrix()
            angle = Rotation.from_matrix(np.einsum('nji,njk->nik', Rd, R)).magnitude()
            ph, th = ref[:, 0], ref[:, 1]
            a, b, c = rr.T
            wr = np.column_stack((a-np.sin(th)*c, np.cos(ph)*b+np.sin(ph)*np.cos(th)*c,
                                  -np.sin(ph)*b+np.cos(ph)*np.cos(th)*c))
            we = x[:, 9:12] - np.einsum('nji,njk,nk->ni', R, Rd, wr)
            e = np.arctan2(np.sin(ref-x[:, 6:9]), np.cos(ref-x[:, 6:9]))
            for label, mask in [('ALL', np.ones(len(t), dtype=bool)), ('PRE_0_5', t < 5), ('POST_5', t >= 5)]:
                rows.append({'scene_id': entry['scene_id'], 'class': entry['scene_id'].split('_')[-2],
                             'task': entry['scene_id'].split('_')[-3], 'wind': entry['scene_id'].split('_')[-1],
                             'period': label, 'samples': int(np.sum(mask)), 'path': str(p), 'raw_sha256': source['sha256'],
                             'SO3_RMSE_deg': float(np.rad2deg(np.sqrt(np.mean(angle[mask]**2)))),
                             'SO3_peak_deg': float(np.rad2deg(np.max(angle[mask]))),
                             'Euler_axis_RMSE_deg': np.rad2deg(np.sqrt(np.mean(e[mask]**2, axis=0))).tolist(),
                             'transported_body_rate_RMSE_rads': np.sqrt(np.mean(we[mask]**2, axis=0)).tolist()})
    groups = []
    for period in ['ALL', 'PRE_0_5', 'POST_5']:
        for label in ['ALL', 'C00', 'ACTIVE']:
            selected = [r for r in rows if r['period'] == period and
                        (label == 'ALL' or (r['class'] == 'C00') == (label == 'C00'))]
            groups.append({'group': label, 'period': period, 'n': len(selected),
                           'scene_equal_mean_SO3_RMSE_deg': float(np.mean([r['SO3_RMSE_deg'] for r in selected])),
                           'max_SO3_peak_deg': max(r['SO3_peak_deg'] for r in selected)})
    result = {'schema': 'C5_DEV72_ATTITUDE_BASELINE_V1', 'parent_sha256': parent_hash,
              'script_sha256': sha(Path(__file__)), 'scope': 'Frozen C5 DEV only, descriptive tracking baseline; no candidate comparison or TEST selection.',
              'alignment': '20,000 left transition states and same-row filtered command, not terminal state.',
              'body_rate_definition': 'omega - R_actual^T R_ref omega_ref, omega_ref=T(ref)^-1 etaDot_ref',
              'new_rollouts': 0, 'training_steps': 0, 'groups': groups, 'rows': rows}
    with OUT.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'groups': groups}, ensure_ascii=False))


if __name__ == '__main__':
    main()
