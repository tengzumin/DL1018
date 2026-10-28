"""Read-only numerical check of the two actual position-controller paths.

Uses each run's own recorded state: different closed-loop forces are expected.
Checks equations, injection sign/unit and paired exogenous inputs, not Q causality.
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
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    out = HERE/'COMMON_POSITION_CHAIN_PARENT_CHECK.json'
    assert not out.exists()
    lock_path = ROOT/'experiments/position_prior_calibration_c1_20261022_v9/C1_SOURCE_LOCK_v2.json'
    assert sha(lock_path) == '02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    config_item = next(r for r in lock['frozen_runtime_files'] if Path(r['path']).name == 'effective_config.mat')
    config = Path(config_item['path'])
    assert sha(config) == config_item['sha256']
    cfg = loadmat(config, simplify_cells=True)['cfg']
    mass = float(cfg['plant']['mass'])
    k1 = np.asarray(cfg['control']['bs']['position']['k1'], dtype=float)
    k2 = np.asarray(cfg['control']['bs']['position']['k2'], dtype=float)
    table_path = ROOT/'experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv'
    with table_path.open(encoding='utf-8-sig', newline='') as stream:
        table = [r for r in csv.DictReader(stream) if r['condition'] in ('B', 'ON1')]
    assert len(table) == 24 and len({(r['scene_id'], r['condition']) for r in table}) == 24
    paired, checks = {}, []
    for row in table:
        path = Path(row['raw_path'])
        before = path.stat()
        assert sha(path) == row['raw_sha256']
        with h5py.File(path, 'r') as f:
            g = f['log']
            def read(key):
                v = np.asarray(g[key])
                return v.T if v.ndim >= 2 else v
            x = read('state')[:-1]
            ref = {k: read('reference/'+k) for k in g['reference']}
            ep, ev = ref['position'][:-1]-x[:, :3], ref['velocity'][:-1]-x[:, 3:6]
            nominal = mass*(ref['acceleration'][:-1]+k1*ev+ep+k2*(ev+k1*ep))
            observed_nominal = read('position_bs_nominal_force_N')
            requested = read('position_commanded_force_N')
            compensation_key = ('position_rbf_compensation_force_N' if row['condition'] == 'B'
                                else 'stage1_position_injected_force_I_N')
            compensation = read(compensation_key)
            errors = {'nominal_BS_max_abs_N': float(np.max(np.abs(nominal-observed_nominal))),
                      'force_injection_max_abs_N': float(np.max(np.abs(requested-(nominal-compensation))))}
            assert all(v < 2e-12 for v in errors.values()), errors
            if row['condition'] == 'ON1':
                errors['force_to_acceleration_max_abs_N'] = float(np.max(np.abs(
                    compensation-mass*read('stage1_position_held_applied_acceleration_mps2'))))
                errors['pcf_request_max_abs_mps2'] = float(np.max(np.abs(
                    requested/mass-read('stage1_position_pcf_a_req_mps2'))))
                assert all(v < 2e-12 for v in errors.values()), errors
            external = {'reference/'+k: a for k, a in ref.items()}
            for key in ['time', 'transition_time', 'initial_state', 'environment_wind_I',
                        'arms/command', 'arms/rho_true', 'arms/rhoDot_true',
                        'arms/rho_hat', 'arms/rhoDot_hat']:
                external[key] = read(key)
            if row['scene_id'] in paired:
                other = paired.pop(row['scene_id'])
                assert external.keys() == other.keys()
                for key in external:
                    assert np.array_equal(external[key], other[key]), (row['scene_id'], key)
            else:
                paired[row['scene_id']] = external
            checks.append({'scene_id': row['scene_id'], 'condition': row['condition'],
                           'raw_sha256': row['raw_sha256'], 'equation_errors': errors})
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert not paired
    result = {'status': 'PASS_RECORDED_COMMON_POSITION_EQUATIONS_AND_EXTERNAL_INPUTS',
              'runs': 24, 'scene_pairs': 12, 'mass_kg': mass,
              'k1': k1.tolist(), 'k2': k2.tolist(), 'config_sha256': sha(config),
              'table_sha256': sha(table_path), 'checks': checks,
              'limit': 'Checks nominal position BS and force injection on each run own state. Does not prove full post-head chain or closed-loop causal attribution.',
              'Plant_called': False, 'TEST_accessed': False}
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'runs': 24,
                      'max_error': max(max(r['equation_errors'].values()) for r in checks)}))


if __name__ == '__main__':
    main()
