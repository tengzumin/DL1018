"""Independent read-only metrics for explicitly manifested development raws."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def historical_manifest(root, scope_path):
    scope = json.loads(scope_path.read_text(encoding='utf-8-sig'))
    pair_path = root / scope['source_table']
    assert sha(pair_path) == scope['source_table_sha256']
    pair = rows(pair_path)
    wanted = {r['scene_id'] for r in scope['rows']}
    assert len(wanted) == 72 and len(pair) == 144
    baseline_path = root / 'reports/paper14_v2/phase1/baseline_b_raw_rescore.csv'
    baseline = rows(baseline_path)
    archive = root.parent / 'REFERENCE_FIX_FULL72_20261021_022342_313/corrected_reference_training_v1'
    indexes = [archive / part / 'reports/RAW_INDEX.csv' for part in
               ('corrected_pair_eval_v1', 'corrected_pair_eval_tail21_v1')]
    indexed = {}
    for path in indexes:
        for r in rows(path):
            if r['raw_sha256'] and r['action'] == 'RUN' and r['status'] == 'RUN_COMPLETE_STABLE':
                indexed[r['raw_sha256'].lower()] = r
    selected = []
    for r in baseline:
        sid = r['scene_id']
        assert sid in wanted and r['raw_sha256_before'] == r['raw_sha256_after']
        selected.append(dict(scene_id=sid, method='B', path=r['resolved_raw_path'],
                             sha256=r['raw_sha256_before'], expected_Q_m=float(r['pair_table_b_q_m'])))
    for r in pair:
        sid = r['source_scene_id']
        digest = r['candidate_raw_sha256'].lower()
        old = indexed[digest]
        assert old['source_scene_id'] == sid and old['method_id'] == r['method_id']
        assert old['complete'].lower() == old['finite'].lower() == 'true'
        selected.append(dict(scene_id=sid, method='DSSM14' if 'DSSM14' in r['method_id'] else 'KAN14',
                             path=str(root.parent / old['raw_path']), sha256=digest,
                             expected_Q_m=float(r['candidate_Q_0_20_m'])))
    assert len(selected) == len({(r['scene_id'], r['method']) for r in selected}) == 216
    assert {r['scene_id'] for r in selected} == wanted
    return dict(scope='HISTORICAL_DEV72_ONLY_NO_TEST',
                source_files=[dict(path=str(p), sha256=sha(p)) for p in
                              [scope_path, pair_path, baseline_path, *indexes]], rows=selected)


def score(item):
    path = Path(item['path'])
    before = path.stat()
    assert sha(path) == item['sha256'], path
    with h5py.File(path, 'r') as file:
        log = file['log']

        def read(key):
            a = np.asarray(log[key])
            return a.T if a.ndim == 2 else a

        def text(key):
            return ''.join(chr(int(c)) for c in np.asarray(log[key]).ravel() if c)

        t, state, reference = read('transition_time').ravel(), read('state'), read('reference/position')
        assert len(t) == 20000 and np.max(np.abs(t - np.arange(20000) * .001)) < 4e-15
        assert state.shape[0] == 20001 and reference.shape == (20001, 3)
        assert np.isfinite(state).all() and np.isfinite(reference).all()
        assert text('status') == 'STABLE' and not text('safety_stop_reason')
        assert read('last_transition').item() == 20000
        error = state[:-1, :3] - reference[:-1]
        result = {k: item[k] for k in ('scene_id', 'method', 'path', 'sha256')}
        for phase, lo, hi in [('0_20', 0, 20), ('0_5', 0, 5), ('5_20', 5, 20)]:
            subset = error[(t >= lo) & (t < hi)]
            result[f'Q_{phase}_m'] = float(np.sqrt(np.sum(subset * subset) / len(subset)))
            for axis, name in enumerate('xyz'):
                result[f'rmse_{name}_{phase}_m'] = float(np.sqrt(np.mean(subset[:, axis] ** 2)))
        if 'expected_Q_m' in item:
            result['Q_minus_frozen_table_m'] = result['Q_0_20_m'] - item['expected_Q_m']
            assert abs(result['Q_minus_frozen_table_m']) < 1e-12
        norm = np.sqrt(np.sum(error * error, axis=1))
        result.update(peak_m=float(norm.max()), p95_m=float(np.quantile(norm, .95)))
        for key in ('motor_saturated', 'generalized_clipped'):
            a = read(key)
            assert a.shape[0] == 20000 and np.isfinite(a).all()
            result[key + '_fraction'] = float(np.mean(np.any(a != 0, axis=1)))
        timing = read('controller_call_time_s').ravel()
        assert len(timing) == 20000 and np.isfinite(timing).all() and np.all(timing >= 0)
        result.update(controller_mean_s=float(np.mean(timing)), controller_p95_s=float(np.quantile(timing, .95)))
        digest = hashlib.sha256()
        external_keys = ['initial_state', 'time', 'transition_time', 'environment_wind_I',
                         'arms/command', 'arms/rho_true', 'arms/rhoDot_true', 'arms/rho_hat', 'arms/rhoDot_hat']
        external_keys += ['reference/' + key for key in sorted(log['reference'])]
        for key in external_keys:
            a = read(key)
            assert np.isfinite(a).all()
            digest.update((key + '\0' + repr((a.shape, str(a.dtype))) + '\0').encode())
            digest.update(a.tobytes(order='C'))
        result['external_identity_sha256'] = digest.hexdigest()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--create-historical-manifest', action='store_true')
    args = parser.parse_args()
    assert not args.output.exists(), 'Preserve earlier evidence'
    root = Path(__file__).resolve().parents[2]
    if args.create_historical_manifest:
        assert not args.manifest.exists(), 'Preserve earlier manifest'
        manifest = historical_manifest(root, root / 'reports/delayed_prediction_c3_parent_20261023/DEV72_SCENE_SCOPE_DRAFT.json')
        args.manifest.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    scored = [score(item) for item in manifest['rows']]
    for sid in {r['scene_id'] for r in scored}:
        assert len({r['external_identity_sha256'] for r in scored if r['scene_id'] == sid}) == 1, sid
    result = dict(status='PASS_RAW_IDENTITIES_METRICS_AND_PAIRED_EXTERNAL_INPUTS',
                  manifest_sha256=sha(args.manifest), script_sha256=sha(Path(__file__)), rows=scored,
                  timing_qualification='NONISOLATED_NOT_FORMAL', new_Plant=0, training=0, TEST_accessed=False)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], raw_count=len(scored),
                         max_Q_table_difference_m=max(abs(r.get('Q_minus_frozen_table_m', 0)) for r in scored))))
