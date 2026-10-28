"""Independent raw audit; never starts MATLAB or updates weights in a rollout."""
import argparse
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('c2_score', ROOT/'reports/c2_deployable_residual_parent_20261023/score_c2_beta_recovered.py')
import hashlib
assert hashlib.sha256(Path(spec.origin).read_bytes()).hexdigest() == '320755d6e570abb14c66a2abf2c3350a007f9c2cc4db750b0246de48837eddba'
c2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2)


def verify(path, candidate_sha256, comparator_path, comparator_sha256):
    row, _, external = c2.score_raw(path, candidate_sha256, False)
    comparator, _, comparator_external = c2.score_raw(comparator_path, comparator_sha256, True)
    assert row['scene_id'] == comparator['scene_id'], 'Frozen C2 scene mismatch'
    assert external == comparator_external, 'Frozen C2 external physical input mismatch'
    with h5py.File(path, 'r') as f:
        g = f['log']
        def read(key):
            a = np.asarray(g[key])
            return a.T if a.ndim == 2 else a
        ids = np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
        assert np.array_equal(ids, np.arange(320, 19991, 10))
        assert read('stage1_position_delayed_prediction_enabled').item() == 1
        assert read('stage1_position_replacement_enabled').item() == 1
        assert read('stage1_position_search_gamma').item() == 12
        assert read('stage1_position_search_kappa').item() == 1
        assert read('stage1_position_pcf_coordination_enabled').item() == 1
        initial = read('stage1_position_search_initial_weight')
        assert np.array_equal(read('stage1_position_weight_initial'), initial)
        assert hashlib.sha256(np.asarray(initial, dtype='<f8').tobytes(order='F')).hexdigest() == '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'
        phi = read('stage1_position_event_phi_33')[ids]
        wb = np.asarray(g['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1)
        wa = np.asarray(g['stage1_position_event_weight_after_33x3']).transpose(0, 2, 1)
        assert np.array_equal(wb[0], initial), 'First ready weight differs from frozen W0'
        velocity = read('state')[:, 3:6]
        af = read('stage1_position_pcf_a_f_mps2')
        target = read('stage1_position_delayed_prediction_target_mps2')[ids]
        prev = read('stage1_position_delayed_prediction_prev_index_zero_based').ravel()[ids]
        assert np.isnan(prev[0]) and np.isnan(target[0]).all()
        assert np.array_equal(prev[1:], ids[:-1])
        # Direct disjoint block means, independent of runtime cumulative sums.
        y = np.array([(velocity[k]-velocity[j])/.01-af[j:k].mean(axis=0)
                      for j, k in zip(ids[:-1], ids[1:])])
        beta = np.minimum((ids+1)*.001/1.8, 1)
        raw = np.einsum('nfi,nf->ni', wb, phi)
        gradient = np.zeros_like(wb)
        residual = np.einsum('nfi,nf->ni', wb[1:], phi[:-1])-y
        gradient[1:] = phi[:-1, :, None]*residual[:, None, :]
        s = read('stage1_position_pcf_event_s_coord_eff_mps')[ids]
        expected = np.clip(wb-.12*beta[:, None, None]*phi[:, :, None]*s[:, None, :]
                           -.00002*wb-.01*gradient, -60, 60)
        checks = {
            'beta_clock': float(np.max(np.abs(read('stage1_position_event_beta').ravel()[ids]-beta))),
            'event_dt': float(np.max(np.abs(read('stage1_position_event_dt_s').ravel()[ids]-.01))),
            'past_interval_target': float(np.max(np.abs(target[1:]-y))),
            'output_before_update': float(np.max(np.abs(read('stage1_position_event_raw_acceleration_mps2')[ids]-raw))),
            'applied_beta_clip': float(np.max(np.abs(read('stage1_position_event_applied_acceleration_mps2')[ids]-beta[:, None]*np.clip(raw, -3, 3)))),
            'single_joint_update': float(np.max(np.abs(wa-expected))),
            'weight_continuity': float(np.max(np.abs(wb[1:]-wa[:-1]))),
            'prediction_term_norm': float(np.max(np.abs(read('stage1_position_delayed_prediction_term_norm').ravel()[ids]-.01*np.linalg.norm(gradient, axis=(1, 2)))))
        }
        assert all(np.isfinite(value) and value < 1e-10 for value in checks.values()), checks
    return dict(status='PASS_RAW_AUDIT', metrics=row, external_identity_sha256=external,
                frozen_C2_raw_path=str(comparator_path), frozen_C2_sha256=comparator_sha256,
                event_count=len(ids), checks=checks, timing_qualification='NONISOLATED_NOT_FORMAL')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--candidate-sha256', required=True, help='Expected SHA from saved C3 run status')
    parser.add_argument('--c2-raw', type=Path, required=True)
    parser.add_argument('--c2-sha256', required=True, help='Expected SHA from frozen C2 evidence, not computed from untrusted input')
    args = parser.parse_args()
    assert not args.output.exists(), 'Do not overwrite previous audit'
    args.output.write_text(json.dumps(verify(args.raw, args.candidate_sha256, args.c2_raw, args.c2_sha256), indent=2, allow_nan=False), encoding='utf-8')
