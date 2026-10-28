"""Independent NumPy forward and event arithmetic audit of TRAIN4 MATLAB output."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/attitude_cm18_datarepair_20261024'
OUT = BASE / 'ROOT_PAIRED_TRAIN4_INDEPENDENT_AUDIT_v1.json'
assert not OUT.exists(), 'No overwrite'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
release = read(BASE/'ROOT_PAIRED_TRAIN4_EXECUTION_RELEASE_v1.json')
assert sha(ROOT/release['source_path']) == release['source_sha256']
report_path = BASE/'paired_train4_map_comparison_v1/PAIRED_TRAIN4_MAP_COMPARISON_v1.json'
report = read(report_path)
assert report['status'] == 'DIAGNOSTIC_COMPLETE' and len(report['scenes']) == 4
model_path = ROOT/'experiments/attitude_cm18_a1_20261024/model_cm18_v1.py'
assert sha(model_path) == 'ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6'
spec = importlib.util.spec_from_file_location('train4_audit_numpy', model_path)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
deploy = {n: read(ROOT/f'experiments/attitude_cm18_datarepair_20261024/postselection_{n.lower()}_v1/deployment_parameters_v1.json') for n in ('A1R', 'A1T')}
max_delta = 0.0
rows = []
for scene in report['scenes']:
    flight = scene['flight_id']
    ep = ROOT/f'reports/attitude_position_context_probe_20261024/offline_events_v2/events_{flight}_v2.json'
    assert sha(ep) == scene['event_export_sha256']
    x = np.asarray(read(ep)['X18'], dtype=float)
    if x.shape == (18, 1999):
        x = x.T
    assert x.shape == (1999, 18)
    events = scene['event_records']
    assert len(events) == 1999
    t = np.array([e['time_s'] for e in events])
    beta = np.array([e['beta'] for e in events])[:, None]
    g = np.array([e['G_row_major'] for e in events]).reshape(-1, 3, 3)
    e0 = np.array([e['E0_rad_s2'] for e in events])
    cstar = np.array([e['Cstar_rad_s2'] for e in events])
    assert np.max(np.abs(e0-np.einsum('nij,nj->ni', g, cstar))) < 1e-9
    residuals = {}
    for n in ('A1R', 'A1T'):
        assert sha(ROOT/f'experiments/attitude_cm18_datarepair_20261024/postselection_{n.lower()}_v1/deployment_parameters_v1.json') == report['deployments'][n]['deployment_sha256']
        y = model.forward(x, deploy[n]['parameters'])['physical_output_rad_s2']
        actual_y = np.array([e[n]['raw_prediction_rad_s2'] for e in events])
        max_delta = max(max_delta, float(np.max(np.abs(y-actual_y))))
        action = beta*np.clip(y, [-45, -45, -4.7124], [45, 45, 4.7124])
        error = e0-np.einsum('nij,nj->ni', g, action)
        max_delta = max(max_delta, float(np.max(np.abs(error-np.array([e[n]['linear_surrogate_E0_minus_G_action_rad_s2'] for e in events])))))
        residuals[n] = error
    for name, mask in [('ALL_0_20', t < 20), ('PRE_0_5', t < 5), ('POST_5_20', t >= 5)]:
        entry = {'flight_id': flight, 'scene_id': scene['scene_id'], 'window': name, 'event_count': int(mask.sum())}
        stored = next(w for w in scene['same_state_map_summary'] if w['window'] == name)
        for n, error in residuals.items():
            rms = float(np.sqrt(np.mean(np.sum(error[mask]**2, axis=1))))
            max_delta = max(max_delta, abs(rms-stored[n]['linear_surrogate_residual_vector_rms_rad_s2']))
            entry[n] = rms
        rows.append(entry)
assert max_delta < 1e-9
OUT.write_text(json.dumps({'schema': 'ROOT_PAIRED_TRAIN4_INDEPENDENT_AUDIT_V1', 'status': 'PASS',
                          'report_sha256': sha(report_path), 'source_sha256': sha(Path(__file__)),
                          'max_independent_delta': max_delta, 'rows': rows,
                          'scope': 'Same recorded inputs; independent NumPy forward and G/E0 arithmetic, no raw simulation or closed-loop claim.'}, indent=2), encoding='utf-8')
print(json.dumps({'status': 'PASS', 'max_delta': max_delta, 'all_window_rows': [r for r in rows if r['window'] == 'ALL_0_20']}))
