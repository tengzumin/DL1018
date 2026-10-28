"""Independent read-only reconstruction; no imported worker functions or updates."""
import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE / 'construction/INPUT_PREFLIGHT.json'
OUT = HERE / 'PARENT_INDEPENDENT_NUMERIC_REVIEW.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    inputs = json.loads(PREFLIGHT.read_text(encoding='utf-8-sig'))['raw_records']
    groups = list(csv.DictReader((HERE / 'construction/DELAYED_INNOVATION_GROUPS.csv').open(encoding='utf-8-sig', newline='')))
    output = []
    for item in inputs:
        path = Path(item['raw_path'])
        before = (path.stat().st_size, path.stat().st_mtime_ns)
        assert digest(path) == item['expected_sha256']
        with h5py.File(path, 'r') as f:
            log = f['log']
            state = np.array(log['state']).T
            af = np.array(log['stage1_position_pcf_a_f_mps2']).T
            phi = np.array(log['stage1_position_event_phi_33']).T
            beta = np.array(log['stage1_position_event_beta']).reshape(-1)
            valid = np.array(log['stage1_position_event_inference_valid']).reshape(-1).astype(bool)
            weights = np.array(log['stage1_position_event_weight_before_33x3']).transpose(0, 2, 1)
            after = np.array(log['stage1_position_event_weight_after_33x3']).transpose(0, 2, 1)
            times = np.array(log['transition_time']).reshape(-1)
        events = np.flatnonzero(valid)
        assert np.array_equal(events, np.arange(320, 19991, 10))
        assert weights.shape == (1968, 33, 3)
        old, current = events[:-1], events[1:]
        # Direct short blocks avoid the worker's cumulative-sum implementation.
        target = np.array([(state[k, 3:6] - state[j, 3:6]) / .01 - af[j:k].mean(axis=0)
                           for j, k in zip(old, current)])
        replay = np.array([beta[j] * np.clip(phi[j] @ weights[n+1], -3, 3)
                           for n, j in enumerate(old)])
        historical = np.array([beta[j] * np.clip(phi[j] @ weights[n], -3, 3)
                               for n, j in enumerate(old)])
        z = np.array([phi[j] @ weights[n+1] for n, j in enumerate(old)])
        grad = phi[old, :, None] * (beta[old, None] * (np.abs(z) < 3) * (replay - target))[:, None, :]
        delta = after[1:] - weights[1:]
        descent_dot = np.sum(-grad * delta, axis=(1, 2))
        denom = np.linalg.norm(grad, axis=(1, 2)) * np.linalg.norm(delta, axis=(1, 2))
        assert (denom > 0).all()
        fd = []
        for n in (0, len(old)//2, len(old)-1):
            j = old[n]
            p, w, b, y = phi[j], weights[n+1], beta[j], target[n]
            # Deterministic single-coordinate derivative, unlike worker's dense direction.
            row = int(np.argmax(np.abs(p)))
            axis = int(np.argmax(np.abs(grad[n, row])))
            wp, wm = w.copy(), w.copy()
            wp[row, axis] += 1e-6
            wm[row, axis] -= 1e-6
            assert np.array_equal(np.abs(p @ wp) < 3, np.abs(p @ wm) < 3)
            def loss(q):
                r = b * np.clip(p @ q, -3, 3) - y
                return .5 * float(r @ r)
            numeric = (loss(wp) - loss(wm)) / 2e-6
            analytic = float(grad[n, row, axis])
            assert abs(numeric - analytic) < 1e-8
            fd.append({'current_event': int(current[n]), 'coordinate': [row, axis],
                       'analytic': analytic, 'finite_difference': numeric, 'absolute_error': abs(numeric-analytic)})
        differences = []
        for phase in ('ALL_ELIGIBLE', 'EARLY_0_5S', 'LATE_5_20S'):
            keep = np.ones(len(old), dtype=bool) if phase == 'ALL_ELIGIBLE' else (times[current] < 5 if phase == 'EARLY_0_5S' else times[current] >= 5)
            row = next(r for r in groups if r['scope'] == item['scene_id'] and r['phase'] == phase and r['axis'] == 'ALL')
            values = {
                'historical_error_rmse_mps2': np.sqrt(np.mean((historical[keep]-target[keep])**2)),
                'replay_error_rmse_mps2': np.sqrt(np.mean((replay[keep]-target[keep])**2)),
                'mean_event_gradient_norm': np.linalg.norm(grad[keep], axis=(1, 2)).mean(),
                'mean_descent_vs_actual_total_deltaW_cosine': np.clip(descent_dot[keep]/denom[keep], -1, 1).mean(),
                'positive_alignment_fraction': (descent_dot[keep] > 0).mean(),
            }
            for name, value in values.items():
                error = abs(float(value) - float(row[name]))
                assert error < 2e-10, (item['scene_id'], phase, name, error)
                differences.append(error)
        assert before == (path.stat().st_size, path.stat().st_mtime_ns)
        assert digest(path) == item['expected_sha256']
        output.append({'scene_id': item['scene_id'], 'raw_sha256': item['expected_sha256'],
                       'eligible_pairs': len(old), 'finite_differences': fd,
                       'compared_metrics': len(differences), 'max_metric_difference': max(differences)})
    result = {'status': 'PASS_PARENT_INDEPENDENT_RAW_RECONSTRUCTION', 'raw_count': len(output),
              'finite_difference_count': sum(len(r['finite_differences']) for r in output),
              'compared_metrics': sum(r['compared_metrics'] for r in output),
              'script_sha256': digest(Path(__file__)), 'rows': output,
              'limitations': 'Historical recorded states only; no counterfactual weight update, controller rollout, performance or stability claim.'}
    with OUT.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))


if __name__ == '__main__':
    main()
