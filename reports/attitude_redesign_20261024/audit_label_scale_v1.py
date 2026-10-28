"""Read TRAIN/VAL event labels only; no training, rollouts or TEST access."""
import collections
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('LABEL_SCALE_AUDIT_v1.json')


def main():
    rows = []
    sums = collections.defaultdict(lambda: {'n': 0, 'ss': np.zeros(3), 'peak': np.zeros(3)})
    for split in ('train', 'val'):
        for p in sorted((ROOT / 'data/events/attitude' / split).glob('*/*.h5')):
            with h5py.File(p, 'r') as f:
                y = np.asarray(f['target_raw'], dtype=float)
                phase = np.asarray(f['phase_code']).reshape(-1)
                t = np.asarray(f['event_time_s']).reshape(-1)
                assert y.shape == (1999, 3) and len(phase) == len(t) == len(y), str(p)
                assert np.isfinite(y).all() and np.isfinite(t).all(), str(p)
                assert np.all(np.diff(t) > 0), str(p)
                scene = str(f.attrs['scene_id'])
                cls = scene.split('_')[-2]
                task = scene.split('_')[-3]
                row = {'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                       'split': split, 'scene': scene, 'class': cls, 'task': task,
                       'axis_rms_rads2': np.sqrt(np.mean(y*y, axis=0)).tolist(),
                       'axis_peak_rads2': np.max(np.abs(y), axis=0).tolist(),
                       'events_above_1e_8_rads2': int(np.sum(np.any(np.abs(y) > 1e-8, axis=1)))}
                rows.append(row)
                for label, mask in [('ALL', np.ones(len(y), dtype=bool)), ('PRE_0_5', t < 5),
                                    ('POST_5', t >= 5)]:
                    z = y[mask]
                    for group in ('ALL', cls, task):
                        a = sums[(split, group, label)]
                        a['n'] += len(z)
                        a['ss'] += np.sum(z*z, axis=0)
                        if len(z):
                            a['peak'] = np.maximum(a['peak'], np.max(np.abs(z), axis=0))
                for code in np.unique(phase):
                    z = y[phase == code]
                    a = sums[(split, 'PHASE_' + str(int(code)), 'ALL')]
                    a['n'] += len(z)
                    a['ss'] += np.sum(z*z, axis=0)
                    a['peak'] = np.maximum(a['peak'], np.max(np.abs(z), axis=0))
    groups = [{'split': s, 'group': g, 'period': p, 'events': a['n'],
               'axis_rms_rads2': np.sqrt(a['ss']/a['n']).tolist(),
               'axis_peak_rads2': a['peak'].tolist()} for (s, g, p), a in sorted(sums.items())]
    result = {'schema': 'ATTITUDE_LABEL_SCALE_AUDIT_V1', 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'All TRAIN/VAL H5 target_raw finite/order/scale checks, per-file hashes. Not raw replay, source provenance, split independence or deployable feature qualification.',
              'group_weighting': 'Pooled event RMS for supervision scale diagnosis; not scene-equal closed-loop performance.',
              'new_rollouts': 0, 'training_steps': 0, 'TEST_accessed': False,
              'file_count': len(rows), 'groups': groups, 'files': rows}
    with OUT.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({'file_count': len(rows), 'all_groups': [g for g in groups if g['group'] == 'ALL'],
                      'near_zero_scenes': sum(max(r['axis_peak_rads2']) <= 1e-8 for r in rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
