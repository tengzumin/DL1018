"""Independent aggregation of closed matched ablations; no raw reads or Plant."""
from pathlib import Path
import csv
import hashlib
import json
import math

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'C5_MATCHED_ABLATION_DEV72_BOTH_RAW_PARENT_AUDIT_v3.json'
SUMMARY = HERE/'MATCHED_ABLATION_DEV72_INDEPENDENT_SUMMARY_v1.json'
PAIRS = HERE/'MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv'
REGRESSIONS = HERE/'C5_ALL_18_REGRESSIONS_VS_NO_PRED_v1.csv'
TOL = 1e-12


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(delta):
    return 'WIN' if delta < -TOL else 'LOSS' if delta > TOL else 'TIE'


def write_csv(path, rows):
    fields = sorted(set().union(*(set(row) for row in rows)))
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    assert all(not path.exists() for path in (SUMMARY, PAIRS, REGRESSIONS))
    assert sha(SOURCE) == 'ec696b9e80a1f22af26b8ef58cb3fcc0a275102ee68b82b286ddf6d54d0a75ba'
    source = json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    assert source['status'] == 'PASS_C5_MATCHED_ABLATION_DEV72_ALL_EVENTS'
    variants, paired, regression = {}, [], []
    all_baselines = {}
    for variant, data in source['variants'].items():
        rows = data['rows']
        assert len(rows) == len({row['scene_id'] for row in rows}) == 72
        assert sum(row['new_raw_audit'] for row in rows) == 60
        groups = {}
        for row in rows:
            sid = row['scene_id']
            baseline = {key: row['methods'][key] for key in ('B_TRACEABLE', 'C3', 'C5_M110')}
            if sid in all_baselines:
                assert all_baselines[sid] == baseline
            else:
                all_baselines[sid] = baseline
            candidate, c5 = row['methods'][variant], row['methods']['C5_M110']
            flat = {'variant': variant, 'scene_id': sid, 'task': row['task'], 'wind': row['wind'],
                    'split': row['split'], 'origin': row['data_origin']}
            for label, metric in [('candidate', candidate), *baseline.items()]:
                assert abs(metric['Q_0_20_m']**2-math.fsum(metric[f'rmse_{axis}_0_20_m']**2 for axis in 'xyz')) < 1e-14
                flat.update({f'{label}_{key}': value for key, value in metric.items() if key != 'scene_id'})
            delta = c5['Q_0_20_m']-candidate['Q_0_20_m']
            flat['C5_minus_ablation_Q_m'] = delta
            flat['C5_vs_ablation'] = compare(delta)
            paired.append(flat)
            if variant == 'C5_NO_DELAYED_PREDICTION' and compare(delta) == 'LOSS':
                regression.append(flat)
        for name, original in data['summary']['groups'].items():
            subset = [row for row in rows if row['scene_id'] in set(original['scene_ids'])]
            assert len(subset) == original['scene_count']
            methods = (variant, 'B_TRACEABLE', 'C3', 'C5_M110')
            means = {}
            for method in methods:
                means[method] = {}
                for key, reported in original['equal_scene_weighted_mean_metrics'][method].items():
                    actual = math.fsum(row['methods'][method][key] for row in subset)/len(subset)
                    assert abs(actual-reported) < 1e-14, (variant, name, method, key)
                    means[method][key] = actual
            d = np.array([row['methods']['C5_M110']['Q_0_20_m']-row['methods'][variant]['Q_0_20_m'] for row in subset])
            b = np.array([row['methods'][variant]['Q_0_20_m']-row['methods']['B_TRACEABLE']['Q_0_20_m'] for row in subset])
            old = original['candidate_vs_C5_M110']
            assert (sum(d > TOL), sum(d < -TOL), sum(np.abs(d) <= TOL)) == (old['wins'], old['losses'], old['ties_within_1e_12_m'])
            indices = np.random.default_rng(2026102301).integers(0, len(subset), size=(10000, len(subset)))
            groups[name] = {'n': len(subset), 'scene_equal_mean_metrics': means,
                            'C5_vs_ablation': {key: int(value) for key, value in (
                                ('wins', sum(d < -TOL)), ('losses', sum(d > TOL)), ('ties', sum(np.abs(d) <= TOL)),
                                ('wins_gt_1um', sum(d < -1e-6)), ('wins_gt_10um', sum(d < -1e-5)))},
                            'C5_minus_ablation_Q_m': math.fsum(d)/len(d),
                            'C5_minus_ablation_Q_95pct_scene_bootstrap_m': np.quantile(d[indices].mean(axis=1), [.025, .975]).tolist(),
                            'ablation_vs_B': {'wins': int(sum(b < -TOL)), 'losses': int(sum(b > TOL)), 'ties': int(sum(np.abs(b) <= TOL))}}
        variants[variant] = groups
    assert len(paired) == 144 and len(regression) == 18
    write_csv(PAIRS, paired)
    write_csv(REGRESSIONS, regression)
    result = {'status': 'PASS_INDEPENDENT_ALL_GROUP_RECOMPUTATION', 'source_SHA256': sha(SOURCE),
              'checker_SHA256': sha(Path(__file__)), 'bootstrap_seed': 2026102301, 'bootstrap_replicates': 10000,
              'bootstrap_unit': 'one paired physical scene, not windows or training seeds',
              'interval_scope': 'Descriptive development intervals; no multiplicity correction or independent TEST inference.',
              'variants': variants, 'paired_csv_SHA256': sha(PAIRS), 'all18_regression_csv_SHA256': sha(REGRESSIONS),
              'raw_read': False, 'Plant_started': False, 'TEST_accessed': False}
    with SUMMARY.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'summary_SHA256': sha(SUMMARY),
                      'paired_SHA256': sha(PAIRS), 'all18_regressions_SHA256': sha(REGRESSIONS)}))


if __name__ == '__main__':
    main()
