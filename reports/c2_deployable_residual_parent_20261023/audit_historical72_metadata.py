"""Read-only 72-pair run-start cfg/opts comparison, never opens raw trajectories."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PHASE = ROOT/'reports/paper14_v2/phase1'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def describe(value):
    a = np.asarray(value) if not isinstance(value, tuple) else None
    return {'shape': list(a.shape) if a is not None else None,
            'value_preview': str(value)[:500],
            'decoded_value_sha256': hashlib.sha256(repr(value).encode()).hexdigest()}


def main():
    out = HERE/'HISTORICAL72_CFG_OPTS_REVIEW.json'
    assert not out.exists()
    helper = PHASE/'audit_w15_position_replay.py'
    spec = importlib.util.spec_from_file_location('w15_mat_helpers', helper)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    bs, ns = PHASE/'baseline_b_raw_rescore.csv', PHASE/'mechanism_run_start_lineage.csv'
    for path in (bs, ns):
        assert digest(path) == m.INPUT_TABLE_SHA256[path.relative_to(ROOT).as_posix()]
    b = {r['scene_id']: r for r in rows(bs)}
    n = {r['scene_id']: r for r in rows(ns)}
    assert len(b) == len(n) == 72 and b.keys() == n.keys()
    results = []
    for sid in sorted(b):
        paths = {'B': Path(b[sid]['resolved_raw_path']).with_name('run_start.mat'),
                 'ON1': Path(n[sid]['run_start_path'])}
        trees, identities = {}, {}
        for role, path in paths.items():
            assert path.name == 'run_start.mat' and path.is_file()
            before = path.stat()
            h = digest(path)
            expected = (n[sid]['run_start_sha256_before'] if role == 'ON1'
                        else m.B_RUN_START_SHA256.get(sid))
            if expected is not None:
                assert h == expected
            trees[role] = {section: m.flatten(m.matlab_section(path, section))
                           for section in ('cfg', 'opts')}
            after = path.stat()
            assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            assert digest(path) == h
            identities[role] = {'path': str(path), 'sha256': h,
                                'historical_run_start_sha_binding_available': expected is not None,
                                'bytes': before.st_size}
        comparison = {}
        for section in ('cfg', 'opts'):
            left, right = trees['B'][section], trees['ON1'][section]
            common = sorted(left.keys() & right.keys())
            diffs = [{'field': key, 'B': describe(left[key]), 'ON1': describe(right[key])}
                     for key in common if not m.same_value(left[key], right[key])]
            comparison[section] = {'leaf_count_B': len(left), 'leaf_count_ON1': len(right),
                                   'common_leaf_count': len(common), 'common_differences': diffs,
                                   'only_B': sorted(left.keys()-right.keys()),
                                   'only_ON1': sorted(right.keys()-left.keys())}
        results.append({'scene_id': sid, 'identities': identities, 'comparison': comparison})
    cfg_diff = [r['scene_id'] for r in results if
                r['comparison']['cfg']['common_differences'] or
                r['comparison']['cfg']['only_B'] or r['comparison']['cfg']['only_ON1']]
    result = {'status': 'COMPLETE_METADATA_COMPARISON', 'pair_count': 72,
              'cfg_different_scenes': cfg_diff,
              'opts_common_difference_fields': sorted({d['field'] for r in results
                  for d in r['comparison']['opts']['common_differences']}),
              'rows': results,
              'limits': ['No raw trajectories opened.',
                         'Numeric MATLAB logical shapes/values compared via existing MAT reader. Numeric dtypes are not independently normalized here.',
                         'Matching NaNs are conservatively reported as differences by the reused helper.',
                         'Old B per-run runtime executable identity gap is not closed by configuration equality.',
                         'B run-start hashes without prior binding are new read-only observations, not recovered historical proof.'],
              'inputs': {str(p): digest(p) for p in (bs, ns, helper)},
              'Plant_called': False, 'TEST_accessed': False}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'pair_count', 'cfg_different_scenes',
                                           'opts_common_difference_fields')}))


if __name__ == '__main__':
    main()
