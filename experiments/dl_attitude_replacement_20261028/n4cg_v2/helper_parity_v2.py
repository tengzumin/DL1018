"""Build a SciPy reference from the locked TRAIN24 event audit and one stress case."""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy.io import savemat
from scipy.signal import butter, sosfilt

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent / 'causal_n4_gate_train24_acden_v2'
NPZ = AUDIT / 'CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz'
AUDIT_JSON = AUDIT / 'CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.json'
BP = butter(2, [2., 5.], btype='bandpass', fs=100, output='sos')
LO = butter(2, [.5, 2.], btype='bandpass', fs=100, output='sos')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def reference(u, t):
    bp, lo = sosfilt(BP, u, axis=0), sosfilt(LO, u, axis=0)
    rho_e, rho_g = np.exp(-.01), np.exp(-.01 / .3)
    e_bp = e_lo = g = 0.
    n4_state = np.zeros((4, 3, 4))
    initialized = False
    w = 2 * np.pi * np.array([2.2, 3.2, 3.7, 4.8]) / 100
    alpha = np.sin(w) / 8
    b = np.column_stack((1 / (1 + alpha), -2 * np.cos(w) / (1 + alpha), 1 / (1 + alpha)))
    a = np.column_stack((np.ones(4), -2 * np.cos(w) / (1 + alpha), (1 - alpha) / (1 + alpha)))
    out, n4, diag = np.zeros_like(u), np.zeros_like(u), np.zeros((len(t), 5))
    for i, x in enumerate(u):
        e_bp = rho_e * e_bp + (1-rho_e) * float(bp[i] @ bp[i])
        e_lo = rho_e * e_lo + (1-rho_e) * float(lo[i] @ lo[i])
        ratio = e_bp / (e_bp + e_lo + 1e-8)
        target = float(np.clip((ratio-.35)/.30, 0, 1)) if t[i] >= 2 else 0.
        g = rho_g*g + (1-rho_g)*target if t[i] >= 2 else 0.
        y = x.copy()
        if not initialized:
            if np.max(np.abs(x)) > 1e-12:
                n4_state[:] = x[None, :, None]
                initialized = True
        else:
            for j in range(4):
                z = n4_state[j]
                v = b[j,0]*y+b[j,1]*z[:,0]+b[j,2]*z[:,1]-a[j,1]*z[:,2]-a[j,2]*z[:,3]
                n4_state[j] = np.column_stack((y, z[:,0], v, z[:,2]))
                y = v
        n4[i] = y
        out[i] = np.clip(x+g*(y-x), -3, 3)
        diag[i] = (e_bp, e_lo, ratio, target, g)
    return out, n4, diag


def main():
    fixture = HERE / 'HELPER_PARITY_FIXTURE_v2.mat'
    if fixture.exists():
        raise RuntimeError('Refusing to overwrite existing parity fixture')
    audit = json.loads(AUDIT_JSON.read_text(encoding='utf-8'))
    if sha(NPZ) != audit['source']['per_event_npz_sha256']:
        raise RuntimeError('TRAIN24 audit NPZ hash mismatch')
    with np.load(NPZ) as d:
        u = d['parent_action_used_mps2'].copy()
        t = d['event_time_s'].copy()
        ready = d['ready_mask'].copy()
        expected_audit = np.stack([d['action_Ebp_2_5'], d['action_Eaclo_0p5_2'],
                                   d['action_ratio_ac'], d['action_g_target_ac'], d['action_gate_ac']], axis=2)
        ids = d['scene_ids'].copy()
    assert u.shape == (24, 1999, 3) and t.shape == (24, 1999)
    assert np.all(ready.sum(axis=1) == 1968) and np.all(~ready[:, :31]) and np.all(u[:, :31] == 0)
    assert np.allclose(t, np.arange(1, 2000)[None, :] * .01, atol=2e-8, rtol=0)
    results = [reference(x, tm) for x, tm in zip(u, t)]
    gate = np.stack([r[2] for r in results])
    audit_diag = expected_audit.copy()
    audit_diag[:, :, 3] = np.where(t < 2, 0., audit_diag[:, :, 3])
    audit_error = float(np.max(np.abs(gate-audit_diag)))
    assert audit_error < 2e-10

    # A nonzero startup signal checks state evolution before the gate opens;
    # one >3 input additionally exercises the final limiter.
    ts = np.arange(1, 2000) * .01
    stress = np.column_stack((1.5*np.sin(2*np.pi*3.2*ts),
                              .8*np.sin(2*np.pi*4.8*ts), .4*np.cos(2*np.pi*2.2*ts)))
    stress[:31] = 0
    stress[59, 0] = 4.2
    stress_result = reference(stress, ts)
    assert np.any(np.abs(stress) > 3) and stress_result[0][59,0] == 3
    assert np.all(stress_result[2][:199,3:] == 0) and stress_result[2][198,0] > 0
    assert stress_result[2][199,4] > 0 and np.max(np.abs(stress_result[1][:199]-stress[:199])) > 1e-3
    u = np.concatenate((u, stress[None]), axis=0)
    t = np.concatenate((t, ts[None]), axis=0)
    results.append(stress_result)
    savemat(fixture, {'u': u.transpose(2,1,0), 'time_s': t.T,
                      'expected_out': np.stack([r[0] for r in results]).transpose(2,1,0),
                      'expected_n4_raw': np.stack([r[1] for r in results]).transpose(2,1,0),
                      'expected_diag': np.stack([r[2] for r in results]).transpose(2,1,0),
                      'bp_sos': BP, 'lo_sos': LO}, do_compression=True)
    meta = {'source_audit_npz_sha256': sha(NPZ), 'source_audit_json_sha256': sha(AUDIT_JSON),
            'fixture_sha256': sha(fixture), 'train_scenes': ids.tolist(), 'events_per_scene': 1999,
            'python_to_train24_audit_max_abs_error': audit_error, 'synthetic_stress_cases': 1,
            'plant_calls': 0, 'VAL_TEST_read': False}
    (HERE / 'HELPER_PARITY_INPUT_v2.json').write_text(json.dumps(meta, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
