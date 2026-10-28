"""Independent reconstruction of 15 causal CM18 input columns from raw records.

The alpha_BS columns require nominal physical reconstruction and are not covered.
"""
from pathlib import Path
import hashlib
import json
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/attitude_position_context_probe_20261024/c5_matched_train24_v1'
TASK = ROOT / 'reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json'
TASK_SHA = '88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read_json = lambda p: json.loads(Path(p).read_text(encoding='utf-8-sig'))


def audit_scene(scene_id):
    ap = BASE / 'event_exports_v1' / scene_id / f'{scene_id}_CSTAR_AUDIT_v1.json'
    a = read_json(ap)
    assert a['status'] == 'PASS' and a['canonical_scene_id'] == scene_id
    ident = a['identity']
    assert sha(ident['flight_raw_path']) == ident['flight_raw_sha256']
    assert sha(ident['flight_run_start_path']) == ident['flight_run_start_sha256']
    assert sha(a['cache_path']) == a['cache_sha256']
    with h5py.File(ident['flight_raw_path'], 'r') as f:
        state = np.asarray(f['log/state']).T
        request = np.asarray(f['log/requested_generalized']).T
        command = np.asarray(f['scene/arms/command']).T
        t = np.asarray(f['scene/time']).ravel()
        flags = np.asarray(f['log/attitude_event_flag']).ravel()
    with h5py.File(ident['flight_run_start_path'], 'r') as f:
        mass = float(np.asarray(f['runStart/cfg/plant/mass']).item())
    with h5py.File(a['cache_path'], 'r') as f:
        x = np.asarray(f['events/X18']).T
        idx = np.asarray(f['events/plant_index']).ravel().astype(int)-1
        event_t = np.asarray(f['events/event_time_s']).ravel()
    assert x.shape == (1999, 18) and state.shape == (20001, 12)
    assert command.shape == (20001, 4) and request.shape == (20000, 4)
    assert np.array_equal(idx, np.arange(10, 19991, 10))
    assert np.array_equal(np.flatnonzero(flags), idx)
    dt = np.diff(t)
    assert np.max(np.abs(dt-.001)) < 1e-12 and mass > 0
    z = np.vstack([np.zeros((1, 4)), np.cumsum(command[:-1]*dt[:, None], axis=0)])
    previous = np.array([np.sum(request[k-10:k, 1:4]*dt[k-10:k, None], axis=0)/np.sum(dt[k-10:k]) for k in idx])
    errors = {
        'omega': np.max(np.abs(x[:, :3]-state[idx, 9:12])),
        'thrust_per_mass': np.max(np.abs(x[:, 6]-request[idx, 0]/mass)),
        'current_command': np.max(np.abs(x[:, 7:11]-command[idx])),
        'past_command_integral': np.max(np.abs(x[:, 11:15]-z[idx])),
        'previous_complete_interval_torque': np.max(np.abs(x[:, 15:18]-previous)),
        'event_time': np.max(np.abs(event_t-t[idx])),
    }
    assert np.isfinite(x).all() and all(np.isfinite(list(errors.values())))
    assert max(errors.values()) < 1e-10, errors
    return {'scene_id': scene_id, 'status': 'PASS', 'covered_columns': 15,
            'max_error_by_component': {k: float(v) for k, v in errors.items()},
            'raw_sha256': ident['flight_raw_sha256'], 'cache_sha256': a['cache_sha256']}


if __name__ == '__main__':
    assert sha(TASK) == TASK_SHA
    rows = read_json(TASK)['scene_rows']
    assert len(rows) == 24
    results = [audit_scene(r['canonical_scene_id']) for r in rows]
    out = BASE / 'ROOT_TRAIN24_CAUSAL_INPUT_AUDIT_v1.json'
    with out.open('x', encoding='utf-8') as f:
        json.dump({'schema': 'ROOT_TRAIN24_CAUSAL_INPUT_AUDIT_V1', 'status': 'PASS',
                   'scene_count': len(results), 'source_sha256': sha(__file__),
                   'taskbook_sha256': TASK_SHA, 'scenes': results,
                   'scope': '15/18 input columns independently reconstructed from raw; alpha_BS and physical targets not covered.',
                   'Plant_calls': 0, 'optimizer_steps': 0, 'TEST_accessed': False}, f, indent=2)
    print('PASS', len(results))
