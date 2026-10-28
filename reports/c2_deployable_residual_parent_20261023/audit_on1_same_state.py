"""Independent offline same-state audit; physical truth is never a deployment input."""
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
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def body_z(euler):
    roll, pitch, yaw = euler.T
    return np.column_stack((np.cos(yaw)*np.sin(pitch)*np.cos(roll)+np.sin(yaw)*np.sin(roll),
                            np.sin(yaw)*np.sin(pitch)*np.cos(roll)-np.cos(yaw)*np.sin(roll),
                            np.cos(pitch)*np.cos(roll)))


def main():
    output = HERE/'C2_ON1_PARENT_SAME_STATE_AUDIT.json'
    assert not output.exists()
    lock = json.loads((ROOT/'experiments/position_beta_clock_c2_20261023/C2_SOURCE_LOCK.json').read_text(encoding='utf-8-sig'))
    cfgpath = Path(lock['shared_c1_inputs']['effective_config_path'])
    assert sha(cfgpath) == lock['shared_c1_inputs']['effective_config_sha256']
    cfg = loadmat(cfgpath, simplify_cells=True)['cfg']['plant']
    mass, gravity = float(cfg['mass']), float(cfg['g'])
    with (ROOT/'experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv').open(encoding='utf-8-sig') as stream:
        runs = [r for r in csv.DictReader(stream) if r['condition'] == 'ON1']
    assert len(runs) == 12
    rows, checks = [], []
    for run in runs:
        path = Path(run['raw_path']); before = path.stat()
        assert sha(path) == run['raw_sha256']
        with h5py.File(path) as f:
            g = f['log']; read = lambda key: np.asarray(g[key]).T
            ids = np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
            assert np.array_equal(ids, np.arange(320, 19991, 10))
            state = read('state')[ids]
            a_actual = (read('realized_generalized')[ids, :1]*body_z(state[:, 6:9])+
                        read('wind_force_I')[ids])/mass
            a_actual[:, 2] -= gravity
            a_req = read('position_commanded_force_N')[ids]/mass
            a_f = read('requested_generalized')[ids, :1]*body_z(read('filtered_attitude_reference')[ids])/mass
            a_f[:, 2] -= gravity
            rf = a_req-a_f; y = a_actual-a_req; d = y+rf
            assert read('stage1_position_pcf_coordination_enabled').item() == 1
            errors = {name: float(np.max(np.abs(actual-read(key)[ids]))) for name, actual, key in
                      [('a_req', a_req, 'stage1_position_pcf_a_req_mps2'),
                       ('a_f', a_f, 'stage1_position_pcf_a_f_mps2'),
                       ('r_f', rf, 'stage1_position_pcf_r_f_mps2')]}
            errors['full_axis_identity'] = float(np.max(np.abs(d-(a_actual-a_f))))
            assert max(errors.values()) < 1e-12, errors
            checks.append({'scene_id': run['scene_id'], 'errors_mps2': errors,
                           'raw_sha256': run['raw_sha256']})
            phi = read('stage1_position_event_phi_33')[ids]
            w0 = read('stage1_position_weight_initial')
            raw0 = phi@w0
            online_raw = read('stage1_position_event_raw_acceleration_mps2')[ids]
            beta = read('stage1_position_event_beta').ravel()[ids, None]
            u0 = beta*np.clip(raw0, -3, 3)
            online = read('stage1_position_event_applied_acceleration_mps2')[ids]
            assert np.max(np.abs(online-beta*np.clip(online_raw, -3, 3))) < 1e-13
            sc = read('stage1_position_pcf_event_s_coord_eff_mps')[ids]
            times = read('transition_time').ravel()[ids]
            for phase, mask in [('all_valid', times >= 0), ('early_0_5', times < 5), ('late_5_20', times >= 5)]:
                for target_name, target in [('Y', y), ('Y_plus_rf_full3D', d)]:
                    for axis, cols in [('ALL', [0, 1, 2]), ('X', [0]), ('Y', [1]), ('Z', [2])]:
                        t = target[mask][:, cols]
                        row = {'scene_id': run['scene_id'], 'task': run['task'], 'wind_band': run['wind_band'],
                               'phase': phase, 'target': target_name, 'axis': axis, 'events': int(mask.sum()),
                               'target_rms_mps2': float(np.sqrt(np.mean(t*t)))}
                        for label, pred in [('W0_same_phi', u0), ('online', online)]:
                            err = pred[mask][:, cols]-t
                            row[label+'_rmse_mps2'] = float(np.sqrt(np.mean(err*err)))
                            row[label+'_bias_mps2'] = float(np.mean(err))
                            row[label+'_surface_cross_m2ps3'] = float(np.mean(np.sum(sc[mask][:, cols]*err, axis=1)))
                        rows.append(row)
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        assert sha(path) == run['raw_sha256']
    report = {'status': 'PASS_OFFLINE_SAME_STATE_DESCRIPTIVE_NOT_CAUSAL', 'runs': 12, 'rows': rows,
              'identity_checks': checks, 'mass_kg': mass, 'gravity_mps2': gravity,
              'limits': ['All observations use original ON1 closed-loop states and features; W0 is not a new rollout.',
                         'Physical instantaneous acceleration reconstructed from realized force, state and logged true wind; offline only.',
                         'Full3D PCF target Y+rf; no old Teacher XY mask is reused.',
                         'Applied outputs compared to physical targets; early beta and clipping remain part of the comparison.',
                         'Effective/clipped update surface cross term is descriptive, not an exact Lyapunov derivative.',
                         'No claim that lower target RMSE implies lower position Q.'], 'Plant': 0, 'training': 0, 'TEST': False}
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({'status': report['status'], 'runs': 12, 'rows': len(rows)}))


if __name__ == '__main__':
    main()
