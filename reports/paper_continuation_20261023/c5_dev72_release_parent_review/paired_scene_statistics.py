"""Independent scene-paired statistics; no time-window resampling or Plant."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

SEED = 2026102301  # Analysis RNG only; no training or seed search.
BOOTSTRAPS = 10000
TOL = 1e-12


def paired_interval(b, c, seed=SEED):
    b, c = np.asarray(b, dtype=float), np.asarray(c, dtype=float)
    assert b.shape == c.shape and b.ndim == 1 and len(b) > 0
    assert np.isfinite(b).all() and np.isfinite(c).all() and np.all(b > 0)
    indices = np.random.default_rng(seed).integers(0, len(b), size=(BOOTSTRAPS, len(b)))
    bm, cm = b[indices].mean(axis=1), c[indices].mean(axis=1)
    return dict(mean_difference_m=float(np.mean(c-b)),
                difference_95_percentile_interval_m=np.quantile(cm-bm, [.025, .975]).tolist(),
                ratio_of_macro_means_improvement=float(1-c.mean()/b.mean()),
                improvement_95_percentile_interval=np.quantile(1-cm/bm, [.025, .975]).tolist())


def self_check():
    b = np.arange(1, 8, dtype=float)
    x = paired_interval(b, b-.25)
    assert np.allclose(x['difference_95_percentile_interval_m'], [-.25, -.25], rtol=0, atol=1e-14)
    y = paired_interval(b, 2*b)
    assert np.array_equal(y['improvement_95_percentile_interval'], [-1., -1.])
    assert np.array_equal(paired_interval(b, b)['difference_95_percentile_interval_m'], [0., 0.])


def main(source, output):
    assert not output.exists()
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    assert data['matlab_os_exit_code'] == 0 and data['scene_count'] == 72
    assert data['new_scenes_event_checked'] == 60 and data['reused_scenes_event_audit_refs'] == 12
    assert data['TEST_accessed'] is False and data['plant_calls_in_audit'] == 0
    rows = data['rows']
    assert len(rows) == len({r['scene_id'] for r in rows}) == 72
    groups = {'ALL72': rows, 'HF28': [r for r in rows if 9 <= int(r['scene_id'][-2:]) <= 14],
              'W15': [r for r in rows if r['scene_id'].endswith('W15')]}
    groups.update({f'T{t}': [r for r in rows if f'_T{t}_' in r['scene_id']] for t in (1, 2, 3)})
    assert (len(groups['HF28']), len(groups['W15'])) == (28, 6)
    result = {}
    for offset, (name, selected) in enumerate(groups.items()):
        b = np.array([r['B_metrics']['Q_0_20_m'] for r in selected])
        c = np.array([r['C5_metrics']['Q_0_20_m'] for r in selected])
        d = c-b
        result[name] = dict(n=len(selected), mean_B_m=float(b.mean()), mean_C5_m=float(c.mean()),
                            wins=int(np.sum(d < -TOL)), losses=int(np.sum(d > TOL)),
                            ties=int(np.sum(abs(d) <= TOL)), wins_gt_1um=int(np.sum(-d > 1e-6)),
                            wins_gt_10um=int(np.sum(-d > 1e-5)),
                            median_absolute_improvement_m=float(np.median(-d)),
                            **paired_interval(b, c, SEED+offset))
    all72 = result['ALL72']
    assert all72['wins'] == data['wins_vs_B']
    assert all72['wins_gt_1um'] == data['wins_improved_gt_1um']
    assert all72['wins_gt_10um'] == data['wins_improved_gt_10um']
    assert abs(all72['mean_C5_m']-data['groups']['ALL72']['C5']['Q_0_20_m']) < 1e-15
    raw_statuses = {r['status'] for r in data['event_check_rows']}
    assert raw_statuses <= {'PASS_C5_RAW_ALL_EVENTS', 'PASS_REUSED_C5_SCREEN_AUDIT'}
    safety = {m: dict(max_motor_saturation_fraction=max(r[m+'_metrics']['motor_saturated_fraction'] for r in rows),
                     max_generalized_clipping_fraction=max(r[m+'_metrics']['generalized_clipped_fraction'] for r in rows))
              for m in ('C5', 'C3', 'B')}
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    payload = dict(status='PASS_INDEPENDENT_PAIRED_SCENE_STATISTICS', groups=result, safety=safety,
                   bootstrap_unit='ONE_PAIRED_PHYSICAL_SCENE', bootstrap_replicates=BOOTSTRAPS,
                   analysis_seed=SEED, group_order=list(groups), interval='percentile 2.5%/97.5%',
                   qualification='DEV descriptive only; fixed scenario distribution, one training seed; not held-out evidence or cross-seed reliability; intervals not adjusted for multiple comparisons',
                   input=dict(path=str(source.resolve()),sha256=digest(source)),
                   script=dict(path=str(Path(__file__).resolve()),sha256=digest(Path(__file__))),
                   TEST_accessed=False, new_Plant=0)
    with output.open('x',encoding='utf-8') as f:
        json.dump(payload,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')
    print(json.dumps(dict(status=payload['status'],groups=result)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    self_check()
    if args.self_check:
        print('PASS exact paired resampling checks; no data read or output written')
    else:
        assert args.source and args.output
        main(args.source,args.output)
