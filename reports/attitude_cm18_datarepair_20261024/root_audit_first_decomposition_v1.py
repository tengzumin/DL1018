"""Independent event arithmetic review; no Plant, trainer, or raw mutation."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/attitude_cm18_datarepair_20261024'
SRC = BASE / ('a1t_same_state_decomposition_v1/DL1018_DEV_T1_C01_W15/'
              'A1T_SAME_STATE_DECOMPOSITION_DL1018_DEV_T1_C01_W15_v1.json')
OUT = BASE / 'a1t_screen12_control_v1/ROOT_FIRST_DECOMPOSITION_EVENT_AUDIT_v1.json'
assert not OUT.exists(), 'No overwrite'
data = json.loads(SRC.read_text(encoding='utf-8-sig'))
release_path = BASE / 'a1t_screen12_control_v1/ROOT_DECOMPOSITION_FIRST_EXECUTION_RELEASE_v4.json'
release = json.loads(release_path.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT / release['source_path']) == release['source_sha256']
assert data['status'] == 'PASS_SINGLE_SCENE_ONLY'
events = data['event_records']
assert len(events) == 1999
max_error = 0.0
for i, e in enumerate(events):
    assert e['plant_index'] == 11 + 10 * i
    assert abs(e['time_s'] - (e['plant_index'] - 1) * .001) < 1e-10
    g = e['G_row_major']
    c, beta, y = e['Cstar_rad_s2'], e['beta'], e['raw_output']
    for a in range(3):
        reconstructed = sum(g[a*3+b] * c[b] for b in range(3))
        max_error = max(max_error, abs(reconstructed - e['E0_rad_s2'][a]))
        max_error = max(max_error, abs(e['raw_output_minus_target'][a] - (y[a]-c[a]/beta)))
        max_error = max(max_error, abs(e['fit_applied_rad_s2'][a] - (c[a]-beta*y[a])))
        fit, clip = e['linear_fit_error_rad_s2'][a], e['linear_clip_error_rad_s2'][a]
        max_error = max(max_error, abs(e['linear_actual_residual_rad_s2'][a]-fit-clip))
assert max_error < 1e-9

def stats(rows):
    n = len(rows)
    return {'count': n, 'signed_mean': [sum(r[a] for r in rows)/n for a in range(len(rows[0]))],
            'rms': [math.sqrt(sum(r[a]**2 for r in rows)/n) for a in range(len(rows[0]))]}

windows = []
for name, select in [('ALL', lambda e: True), ('PRE', lambda e: e['time_s'] < 5),
                     ('POST', lambda e: e['time_s'] >= 5)]:
    es = [e for e in events if select(e)]
    diff = [[e['full_allocator_actual_error_rad_s2'][a]-e['linear_actual_residual_rad_s2'][a]
             for a in range(3)] for e in es]
    windows.append({'window': name, 'raw_output_minus_target_rad_s2': stats([e['raw_output_minus_target'] for e in es]),
                    'full_allocator_minus_linear_rad_s2': stats(diff),
                    'base_allocator_minus_matrix_channels_N_Nm_Nm_Nm': stats([e['base_matrix_delta_N'] for e in es])})
assert max(abs(v) for w in windows for v in w['full_allocator_minus_linear_rad_s2']['rms']) < 1e-9
report = {'schema': 'ROOT_FIRST_DECOMPOSITION_EVENT_AUDIT_V1', 'status': 'PASS_SINGLE_SCENE_ONLY',
          'input_path': str(SRC.relative_to(ROOT)), 'input_sha256': sha(SRC),
          'diagnostic_source_sha256': release['source_sha256'], 'auditor_source_sha256': sha(Path(__file__)),
          'events': len(events), 'max_independent_arithmetic_error': max_error, 'windows': windows,
          'scope': 'Independent arithmetic and identity audit of existing event records; no full12 conclusion or closed-loop prediction.'}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': report['status'], 'events': len(events), 'max_error': max_error}))
