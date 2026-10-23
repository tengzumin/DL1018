"""Verify the proof's sampled physical and held-output identities on closed DEV72."""
from pathlib import Path
import hashlib
import json

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json'
OUT = HERE/'ACTUAL_PHYSICAL_BRIDGE_DEV72_CHECK_v1.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def maximum(a):
    assert np.isfinite(a).all()
    return float(np.max(np.abs(a)))


def main():
    assert not OUT.exists()
    assert sha(SOURCE) == 'bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab'
    parent = json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    assert len(parent['rows']) == 72
    rows = []
    for row in parent['rows']:
        metric = row['C5_metrics']
        raw = Path(metric['path'])
        assert sha(raw) == metric['sha256']
        before = raw.stat()
        with h5py.File(raw, 'r') as mat:
            log = mat['log']

            def read(name):
                a = np.asarray(log[name])
                return a.T if a.ndim == 2 else a

            state = read('state')
            rp, rv, ra = [read('reference/'+name) for name in ('position', 'velocity', 'acceleration')]
            req = read('stage1_position_pcf_a_req_mps2')
            rf = read('stage1_position_pcf_r_f_mps2')
            u = read('position_compensation_applied_acceleration_mps2')
            e = rp-state[:, :3]
            sigma = rv+e-state[:, 3:6]
            d0 = np.diff(state[:, 3:6], axis=0)/.001-req
            rho_p = np.diff(rp, axis=0)-.001*rv[:-1]-(np.diff(state[:, :3], axis=0)-.001*state[:-1, 3:6])
            rho_s = np.diff(rv, axis=0)-.001*ra[:-1]+rho_p
            errors = {
                'requested_acceleration_identity': maximum(req-(ra[:-1]+5*sigma[:-1]-u)),
                'physical_e_recursion': maximum(e[1:]-(.999*e[:-1]+.001*sigma[:-1]+rho_p)),
                'physical_sigma_recursion': maximum(sigma[1:]-(-.001*e[:-1]+.996*sigma[:-1]+.001*(u-d0)+rho_s)),
            }
            ids = np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
            assert np.array_equal(ids, np.arange(320, 19991, 10))
            phi = read('stage1_position_event_phi_33')[ids]
            wb = np.asarray(log['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1)
            z = np.einsum('nfi,nf->ni', wb, phi)
            beta = read('stage1_position_event_beta').ravel()[ids]
            y = read('stage1_position_delayed_prediction_target_mps2')[ids][1:]
            repeated_z, repeated_y = np.repeat(z[:-1], 10, axis=0), np.repeat(y, 10, axis=0)
            repeated_beta = np.repeat(beta[:-1], 10)[:, None]
            clip_delta = np.clip(repeated_z, -3, 3)-repeated_z
            interval = slice(320, 19990)
            masked_rf = rf[interval]*[1, 1, 0]
            dm = d0[interval]+masked_rf
            forcing_terms = (repeated_beta*(repeated_z-repeated_y)
                             +(repeated_beta*repeated_y-dm)
                             +repeated_beta*clip_delta+masked_rf)
            errors['held_applied_output'] = maximum(u[interval]-repeated_beta*np.clip(repeated_z, -3, 3))
            errors['F_physical_forcing_decomposition'] = maximum(u[interval]-d0[interval]-forcing_terms)
            assert max(errors.values()) < 5e-12, (row['scene_id'], errors)
        after = raw.stat()
        assert before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
        rows.append({'scene_id': row['scene_id'], 'raw_sha256': metric['sha256'], 'max_absolute_residuals': errors})
    result = {
        'status': 'PASS_ALL72_NUMERICAL_PHYSICAL_RECURSIONS_AND_HELD_INTERVAL_MAPPING',
        'scope': 'Ordinary floating-point consistency of the stated proof-to-code mapping; not interval certification, prior Plant stability, independent TEST or a causal ablation.',
        'scene_count': 72, 'full_recursion_samples_per_scene': 20000,
        'held_interval_samples_per_scene': 19670,
        'maximum_residuals': {key: max(row['max_absolute_residuals'][key] for row in rows) for key in rows[0]['max_absolute_residuals']},
        'source_sha256': sha(SOURCE), 'checker_sha256': sha(Path(__file__)), 'rows': rows,
        'Plant_started': False, 'TEST_accessed': False, 'training_started': False,
    }
    with OUT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'rows'}))


if __name__ == '__main__':
    main()
