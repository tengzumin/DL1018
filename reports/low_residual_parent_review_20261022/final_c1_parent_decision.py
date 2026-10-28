"""Read completed C1 artifacts; independently recompute Q and frozen decision.

Never launches simulation, fits parameters, or edits run artifacts.
Worker tables share the earlier primary score helper. This check instead reads
each raw state/reference and computes Q through the Frobenius norm identity.
"""
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = ROOT / 'experiments/position_prior_calibration_c1_20261022_v9'
REPORTS = RUN / 'reports'
CONDITIONS = ('B', 'ON1', 'ONC')


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    out = HERE / 'C1_FINAL_PARENT_DECISION.json'
    assert not out.exists(), 'Do not overwrite a prior final decision'
    fixed = rows(ROOT / 'reports/paper14_v2/phase1/ROUND_SCREEN_12_SCENES.csv')
    table = rows(REPORTS / 'C1_SCREEN_PER_RUN.csv')
    assert len(fixed) == 12 and len(table) == 36
    assert [(r['scene_id'], r['condition']) for r in table] == [
        (s['scene_id'], c) for s in fixed for c in CONDITIONS]
    assert len({r['raw_path'] for r in table}) == 36
    assert sum(r['reused_prior_run'] == 'True' for r in table) == 1
    release = json.loads((RUN/'C1_RELEASE_v9.json').read_text(encoding='utf-8'))
    release_sha = digest(RUN/'C1_RELEASE_v9.json')
    reuse_path = Path(release['reuse_authorization_path'])
    assert digest(reuse_path) == release['reuse_authorization_sha256']
    reuse = json.loads(reuse_path.read_text(encoding='utf-8'))
    assert reuse['status'] == 'APPROVED_REUSE_EXACT_COMPLETED_B_NO_RERUN'
    references, numbers = {}, {}
    max_delta = 0.
    for r in table:
        path = Path(r['raw_path']).resolve()
        first_b = r['scene_id'] == fixed[0]['scene_id'] and r['condition'] == 'B'
        assert (r['reused_prior_run'] == 'True') == first_b
        assert r['actual_run_release'] == (release['prior_release_sha256'] if first_b else release_sha)
        assert r['source_lock_sha256'] == release['source_lock_sha256']
        if first_b:
            assert reuse['scene_id'] == r['scene_id'] and reuse['condition'] == 'B'
            for item in reuse['files']:
                assert digest(Path(item['path'])) == item['sha256']
        base = (ROOT / 'experiments/position_prior_calibration_c1_20261022/runs_v8'
                if first_b else RUN / 'runs_v9')
        assert path == (base / r['scene_id'] / r['condition'] / 'attempt_01/raw_run.mat').resolve()
        assert r['status'] == 'STABLE' and r['safe_complete_finite'] == 'True'
        assert r['completed_transition'] == '20000'
        assert r['formal_timing_qualified'] == 'False'
        before = path.stat()
        assert digest(path) == r['raw_sha256']
        with h5py.File(path, 'r') as f:
            log = f['log']
            x = np.asarray(log['state']).T
            ref = np.asarray(log['reference/position']).T
            t = np.asarray(log['transition_time']).ravel()
            assert x.shape[0] == 20001 and ref.shape == (20001, 3)
            assert len(t) == 20000 and np.allclose(t, np.arange(20000)/1000, atol=4e-15, rtol=0)
            assert np.isfinite(x).all() and np.isfinite(ref).all()
            if r['scene_id'] in references:
                assert np.array_equal(ref, references[r['scene_id']])
            else:
                references[r['scene_id']] = ref
            error = x[:-1, :3] - ref[:-1]
            q = float(np.linalg.norm(error, 'fro') / math.sqrt(20000))
            d = abs(q - float(r['Q_0_20_m']))
            assert d < 1e-14
            max_delta = max(max_delta, d)
            for axis, name in enumerate('xyz'):
                value = float(np.linalg.norm(error[:, axis]) / math.sqrt(20000))
                assert abs(value-float(r[f'rmse_{name}_0_20_m'])) < 1e-14
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        numbers[r['scene_id'], r['condition']] = q
    groups = {'ALL12': fixed,
              'HF_W09_W14': [s for s in fixed if s['band'] in ('W09_W11', 'W12_W14')],
              'W15': [s for s in fixed if s['band'] == 'W15'],
              'W00_W08': [s for s in fixed if s['band'] == 'W00_W08']}
    groups.update({task: [s for s in fixed if s['task'] == task]
                   for task in sorted({s['task'] for s in fixed})})
    stats = {}
    for name, subset in groups.items():
        means = {c: math.fsum(numbers[s['scene_id'], c] for s in subset)/len(subset)
                 for c in CONDITIONS}
        comparisons = {}
        for b in ('B', 'ON1'):
            ds = [numbers[s['scene_id'], 'ONC']-numbers[s['scene_id'], b] for s in subset]
            comparisons[b] = {'wins': sum(d < -1e-12 for d in ds),
                              'losses': sum(d > 1e-12 for d in ds),
                              'ties': sum(abs(d) <= 1e-12 for d in ds),
                              'improvement_ge_1um': sum(d <= -1e-6 for d in ds),
                              'improvement_ge_10um': sum(d <= -1e-5 for d in ds)}
        stats[name] = {'scene_count': len(subset), 'mean_Q_m': means, 'ONC_vs': comparisons}
    gates = {'all_36_numerically_complete': True}
    for g in ('W15', 'HF_W09_W14'):
        for b in ('B', 'ON1'):
            gates[f'{g}_mean_Q_not_above_{b}'] = stats[g]['mean_Q_m']['ONC'] <= stats[g]['mean_Q_m'][b]
    gates['ALL12_mean_Q_not_above_ON1'] = stats['ALL12']['mean_Q_m']['ONC'] <= stats['ALL12']['mean_Q_m']['ON1']
    losses = [{'scene_id': s['scene_id'], 'task': s['task'], 'band': s['band'], 'baseline': b,
               'delta_Q_m': numbers[s['scene_id'], 'ONC']-numbers[s['scene_id'], b]}
              for s in fixed for b in ('B', 'ON1')
              if numbers[s['scene_id'], 'ONC']-numbers[s['scene_id'], b] > 1e-12]
    reported = rows(REPORTS / 'C1_SCREEN_LOSSES.csv')
    assert {(r['scene_id'], r['baseline']) for r in reported} == {(r['scene_id'], r['baseline']) for r in losses}
    for r in reported:
        d = numbers[r['scene_id'], 'ONC']-numbers[r['scene_id'], r['baseline']]
        assert abs(d-float(r['delta_Q_0_20_m'])) < 1e-14
    result = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'NUMERICAL_SCREEN_PASS_PENDING_INDEPENDENT_REVIEW' if all(gates.values()) else 'STOP_C1_FROZEN_PERFORMANCE_GATE_FAILED',
              'gates': gates, 'groups': stats, 'all_losses': losses,
              'raw_Q_vs_worker_max_abs_m': max_delta,
              'group_gate_rule': 'Strict mean ONC <= comparator as frozen; 1e-12m tolerance applies to paired win/loss counts.',
              'limits': {'new_scalar_fits': 1, 'optimizer_steps': 0, 'actual_sorties': 36,
                         'TEST_accessed': False, 'new72_authorized': False,
                         'formal_timing_authorized': False, 'paper_status': 'NOT_QUALIFIED'},
              'input_sha256': {p.name: digest(p) for p in [
                  REPORTS/'C1_SCREEN_PER_RUN.csv', REPORTS/'C1_SCREEN_LOSSES.csv',
                  REPORTS/'C1_SCREEN_AUDIT.json', RUN/'C1_RELEASE_v9.json',
                  RUN/'C1_SOURCE_LOCK_v2.json', Path(__file__)]}}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'groups': stats, 'gates': gates}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
