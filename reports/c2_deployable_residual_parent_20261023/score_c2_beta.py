"""Primary raw scoring/event checks for the single clock-aligned C2 candidate."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXP = ROOT/'experiments/position_beta_clock_c2_20261023'
COND = 'C2_ON1_BETA_ALIGNED'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def table(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def score_raw(path, expected_sha, check_candidate):
    before = path.stat()
    assert sha(path) == expected_sha
    with h5py.File(path, 'r') as f:
        g = f['log']
        def read(k):
            a = np.asarray(g[k])
            return a.T if a.ndim == 2 else a
        def text(k):
            return ''.join(chr(int(c)) for c in np.asarray(g[k]).ravel() if c)
        t = read('transition_time').ravel()
        assert len(t) == 20000 and np.allclose(t, np.arange(20000)/1000, rtol=0, atol=4e-15)
        x, ref = read('state'), read('reference/position')
        assert x.shape[0] == 20001 and ref.shape == (20001, 3)
        assert np.isfinite(x).all() and np.isfinite(ref).all()
        assert text('status') == 'STABLE' and not text('safety_stop_reason')
        assert read('last_transition').item() == 20000
        control_time = read('controller_call_time_s').ravel()
        assert len(control_time) == 20000 and np.isfinite(control_time).all() and (control_time >= 0).all()
        external = hashlib.sha256()
        external_keys = ['initial_state', 'time', 'transition_time', 'environment_wind_I',
                         'arms/command', 'arms/rho_true', 'arms/rhoDot_true', 'arms/rho_hat', 'arms/rhoDot_hat']
        external_keys += ['reference/'+key for key in sorted(g['reference'])]
        for key in external_keys:
            a = read(key)
            assert np.isfinite(a).all()
            external.update((key+'\0'+repr((a.shape, str(a.dtype)))+'\0').encode())
            external.update(a.tobytes(order='C'))
        errors = ref[:-1]-x[:-1, :3]
        row = {'scene_id': text('scene_id'), 'raw_path': str(path), 'raw_sha256': expected_sha}
        for phase, lo, hi in [('0_20', 0, 20), ('0_5', 0, 5), ('5_20', 5, 20)]:
            e = errors[(t >= lo) & (t < hi)]
            row[f'Q_{phase}_m'] = float(np.linalg.norm(e, 'fro')/math.sqrt(len(e)))
            for axis, name in enumerate('xyz'):
                row[f'rmse_{name}_{phase}_m'] = float(np.linalg.norm(e[:, axis])/math.sqrt(len(e)))
        norm = np.linalg.norm(errors, axis=1)
        row.update(peak_m=float(norm.max()), p95_m=float(np.quantile(norm, .95)))
        for key in ('motor_saturated', 'generalized_clipped'):
            a = read(key)
            assert a.shape[0] == 20000 and np.isfinite(a).all()
            row[key+'_fraction'] = float(np.mean(np.any(a != 0, axis=1)))
        if check_candidate:
            ids = np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
            beta = read('stage1_position_event_beta').ravel()[ids]
            dt = read('stage1_position_event_dt_s').ravel()[ids]
            phi = read('stage1_position_event_phi_33')[ids]
            wb = np.asarray(g['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1)
            wa = np.asarray(g['stage1_position_event_weight_after_33x3']).transpose(0, 2, 1)
            s = read('stage1_position_pcf_event_s_coord_eff_mps')[ids]
            raw = read('stage1_position_event_raw_acceleration_mps2')[ids]
            applied = read('stage1_position_event_applied_acceleration_mps2')[ids]
            assert np.array_equal(ids, np.arange(320, 19991, 10)), 'Unexpected valid-event schedule'
            gamma = read('stage1_position_search_gamma').item()
            assert gamma == 12 and read('stage1_position_search_kappa').item() == 1
            assert read('stage1_position_pcf_coordination_enabled').item() == 1
            assert read('stage1_position_replacement_enabled').item() == 1
            initial = read('stage1_position_search_initial_weight')
            assert hashlib.sha256(np.asarray(initial, dtype='<f8').tobytes(order='F')).hexdigest() == '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'
            assert np.array_equal(read('stage1_position_weight_initial'), initial)
            checks = {'beta_matches_B_clock': float(np.max(np.abs(beta-np.minimum((ids+1)*.001/1.8, 1)))),
                      'output_before_update': float(np.max(np.abs(raw-np.einsum('nfi,nf->ni', wb, phi)))),
                      'applied_beta_clip': float(np.max(np.abs(applied-beta[:, None]*np.clip(raw, -3, 3)))),
                      'full_discrete_update': float(np.max(np.abs(wa-np.clip(wb+dt[:, None, None]*(
                          -gamma*beta[:, None, None]*phi[:, :, None]*s[:, None, :]-.002*wb), -60, 60))))}
            assert max(checks.values()) < 1e-13, checks
            row['event_checks'] = checks
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return row, ref, external.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['probe', 'full'], required=True)
    args = parser.parse_args()
    out = HERE/f'C2_{args.mode.upper()}_PRIMARY_RAW_REVIEW.json'
    assert not out.exists()
    fixed = table(ROOT/'reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv')
    baselines = table(ROOT/'experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv')
    if args.mode == 'probe':
        fixed = fixed[:1]
    scored = []
    for scene in fixed:
        sid = scene['scene_id']
        path = EXP/'runs_c2'/sid/COND/'attempt_01/raw_run.mat'
        status = json.loads(path.with_name('run_status.json').read_text(encoding='utf-8-sig'))
        assert status['status'] == 'STABLE' and status['scene_id'] == sid
        assert status['condition'] == COND
        candidate, reference, external = score_raw(path, status['raw_sha256'], True)
        for condition in ('B', 'ON1'):
            b = next(r for r in baselines if r['scene_id'] == sid and r['condition'] == condition)
            row, ref, other_external = score_raw(Path(b['raw_path']), b['raw_sha256'], False)
            assert np.array_equal(reference, ref)
            assert external == other_external, 'Paired exogenous inputs differ'
            ids = np.arange(320, 19991, 10)
            with h5py.File(b['raw_path'], 'r') as base_file:
                bg = base_file['log']
                if condition == 'B':
                    baseline_beta = np.asarray(bg['position_event_beta']).ravel()[ids]
                    expected_beta = np.minimum((ids+1)*.001/1.8, 1.)
                else:
                    actual_ids = np.flatnonzero(np.asarray(bg['stage1_position_event_inference_valid']).ravel())
                    assert np.array_equal(actual_ids, ids)
                    baseline_beta = np.asarray(bg['stage1_position_event_beta']).ravel()[ids]
                    expected_beta = np.minimum(ids*.001/1.8, 1.)
                assert np.max(np.abs(baseline_beta-expected_beta)) < 1e-14
            assert abs(row['Q_0_20_m']-float(b['Q_0_20_m'])) < 1e-14
            row.update(condition=condition, task=scene['task'], band=scene['band'])
            scored.append(row)
        candidate.update(condition=COND, task=scene['task'], band=scene['band'])
        scored.append(candidate)
    paired = []
    for scene in fixed:
        c = next(r for r in scored if r['scene_id'] == scene['scene_id'] and r['condition'] == COND)
        for baseline in ('B', 'ON1'):
            b = next(r for r in scored if r['scene_id'] == scene['scene_id'] and r['condition'] == baseline)
            delta = c['Q_0_20_m']-b['Q_0_20_m']
            paired.append({'scene_id': scene['scene_id'], 'task': scene['task'], 'band': scene['band'],
                           'baseline': baseline, 'delta_Q_m': delta,
                           'result': 'WIN' if delta < -1e-12 else 'LOSS' if delta > 1e-12 else 'TIE',
                           'improvement_ge_1um': delta <= -1e-6, 'improvement_ge_10um': delta <= -1e-5})
    groups = {'ALL': fixed, 'HF_W09_W14': [s for s in fixed if s['band'] in ('W09_W11', 'W12_W14')],
              'W15': [s for s in fixed if s['band'] == 'W15']}
    groups.update({t: [s for s in fixed if s['task'] == t] for t in sorted({s['task'] for s in fixed})})
    summary = {}
    for name, subset in groups.items():
        if not subset:
            continue
        ids = {s['scene_id'] for s in subset}
        summary[name] = {'n': len(ids), 'mean_Q_m': {c: math.fsum(r['Q_0_20_m'] for r in scored if
            r['scene_id'] in ids and r['condition'] == c)/len(ids) for c in ('B', 'ON1', COND)},
            'paired': {b: {key: sum(r['result'] == key for r in paired if r['scene_id'] in ids and
             r['baseline'] == b) for key in ('WIN', 'LOSS', 'TIE')} for b in ('B', 'ON1')}}
    result = {'status': 'PASS_RAW_EVENT_AND_NUMERICAL_CHECKS_NOT_PERFORMANCE_DECISION',
              'mode': args.mode, 'run_count': len(scored), 'new_candidate_runs': len(fixed),
              'rows': scored, 'paired': paired, 'groups': summary,
              'formal_timing_qualified': False, 'training': 0, 'TEST_accessed': False}
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'mode': args.mode, 'groups': summary}, indent=2))


if __name__ == '__main__':
    main()
