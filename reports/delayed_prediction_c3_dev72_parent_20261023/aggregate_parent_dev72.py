"""Aggregate frozen C3 development metrics; never select or tune a model."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def write_csv(path, rows):
    assert rows and not path.exists()
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-review', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    history_path = here / 'PARENT_HISTORICAL_216_RAW_REVIEW.json'
    output = here / 'PARENT_DEV72_SUMMARY.json'
    assert not output.exists(), 'Preserve earlier evidence'
    history = json.loads(history_path.read_text())
    candidate = json.loads(args.candidate_review.read_text(encoding='utf-8-sig'))
    assert history['status'] == candidate['status'] == 'PASS_RAW_IDENTITIES_METRICS_AND_PAIRED_EXTERNAL_INPUTS'
    assert len(history['rows']) == 216 and len(candidate['rows']) == 72
    data = history['rows'] + candidate['rows']
    by_key = {(row['scene_id'], row['method']): row for row in data}
    assert len(by_key) == len(data) == 288
    ids = sorted({row['scene_id'] for row in data})
    methods = ['B', 'DSSM14', 'KAN14', 'C3']
    assert len(ids) == 72 and {r['method'] for r in candidate['rows']} == {'C3'}
    for sid in ids:
        assert len({by_key[sid, m]['external_identity_sha256'] for m in methods}) == 1, sid
    paired = []
    for sid in ids:
        for baseline in methods[:-1]:
            base = by_key[sid, baseline]['Q_0_20_m']
            q = by_key[sid, 'C3']['Q_0_20_m']
            delta = q - base
            paired.append(dict(scene_id=sid, split=sid.split('_')[1], task=sid.split('_')[2],
                               wind=sid.split('_')[-1], comparator=baseline,
                               comparator_Q_m=base, C3_Q_m=q, delta_C3_minus_comparator_m=delta,
                               result='WIN' if delta < -1e-12 else 'LOSS' if delta > 1e-12 else 'TIE'))
    groups = {'ALL72': ids, 'HF_W09_W14': [s for s in ids if 9 <= int(s[-2:]) <= 14],
              'W15': [s for s in ids if s.endswith('W15')],
              'LOW_W00_W08': [s for s in ids if int(s[-2:]) <= 8]}
    groups.update({task: [s for s in ids if s.split('_')[2] == task] for task in ['T1', 'T2', 'T3']})
    groups.update({split: [s for s in ids if s.split('_')[1] == split] for split in ['DEV', 'VAL']})
    groups.update({f'W{i:02d}': [s for s in ids if s.endswith(f'W{i:02d}')] for i in range(16)})
    groups = {name: subset for name, subset in groups.items() if subset}
    numeric_keys = [k for k, v in data[0].items() if isinstance(v, (int, float)) and k != 'Q_minus_frozen_table_m']
    summaries, summary_rows = {}, []
    for name, subset in groups.items():
        group = dict(n=len(subset), methods={}, C3_paired={})
        for method in methods:
            means = {key: math.fsum(by_key[sid, method][key] for sid in subset) / len(subset) for key in numeric_keys}
            group['methods'][method] = means
            summary_rows.append(dict(group=name, n=len(subset), method=method, **means))
        for baseline in methods[:-1]:
            ps = [r for r in paired if r['scene_id'] in subset and r['comparator'] == baseline]
            group['C3_paired'][baseline] = {verdict: sum(r['result'] == verdict for r in ps) for verdict in ['WIN', 'LOSS', 'TIE']}
        summaries[name] = group
    checks = dict(wins_at_least_62=summaries['ALL72']['C3_paired']['B']['WIN'] >= 62,
                  overall_mean_strictly_better_B=summaries['ALL72']['methods']['C3']['Q_0_20_m'] < summaries['ALL72']['methods']['B']['Q_0_20_m'],
                  HF_mean_not_above_B=summaries['HF_W09_W14']['methods']['C3']['Q_0_20_m'] <= summaries['HF_W09_W14']['methods']['B']['Q_0_20_m'],
                  W15_mean_not_above_B=summaries['W15']['methods']['C3']['Q_0_20_m'] <= summaries['W15']['methods']['B']['Q_0_20_m'])
    sensitivity, bootstrap = {}, {}
    for baseline in methods[:-1]:
        improvements = np.array([by_key[sid, baseline]['Q_0_20_m'] - by_key[sid, 'C3']['Q_0_20_m'] for sid in ids])
        sensitivity[baseline] = {str(margin): int(np.sum(improvements > margin)) for margin in [1e-12, 1e-6, 1e-5]}
        rng = np.random.default_rng(2026102001)
        resampled_means = improvements[rng.integers(0, 72, size=(10000, 72))].mean(axis=1)
        bootstrap[baseline] = dict(mean_improvement_m=float(improvements.mean()),
                                   percentile95_mean_improvement_m=np.quantile(resampled_means, [.025, .975]).tolist())
    write_csv(here / 'PARENT_ALL288_METRICS.csv', data)
    write_csv(here / 'PARENT_ALL216_PAIRED_COMPARISONS.csv', paired)
    write_csv(here / 'PARENT_ALL_LOSING_PAIRS.csv', [r for r in paired if r['result'] == 'LOSS'])
    write_csv(here / 'PARENT_ALL_GROUP_METRICS.csv', summary_rows)
    result = dict(status='DEVELOPMENT_NUMERICAL_PERFORMANCE_GATE_PASS' if all(checks.values()) else 'DEVELOPMENT_NUMERICAL_PERFORMANCE_GATE_FAIL',
                  checks=checks, groups=summaries, win_margin_sensitivity=sensitivity,
                  paired_scene_bootstrap=dict(seed=2026102001, repetitions=10000, results=bootstrap,
                      limitation='Descriptive paired development-scene resampling; no independent TEST, time-window independence or cross-seed inference'),
                  raw_manifest_inputs=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [history_path, args.candidate_review]],
                  timing_qualification='NONISOLATED_NOT_FORMAL', paper_qualified=False,
                  safety_note='All raw metrics require STABLE/no safety stop; full event/source audit is a separate gate', TEST_accessed=False)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], checks=checks, ALL72=summaries['ALL72'], HF=summaries['HF_W09_W14'], W15=summaries['W15']), indent=2))
