"""Independent serialized-label audit; run only after the MATLAB batch finishes."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'reports/attitude_cm18_datarepair_20261024'
MANIFEST = BASE / 'cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json'
OUTPUT = BASE / 'ROOT_CSTAR_ALL816_INDEPENDENT_AUDIT_v1.json'
OLD_SHA = '3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0'
SOURCE_SHA = '0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5'
NORM_SHA = 'faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def arrays_digest(*values):
    return hashlib.sha256(b''.join(np.ascontiguousarray(v, dtype=np.float64).tobytes()
                                   for v in values)).hexdigest()


def main():
    assert not OUTPUT.exists(), 'Refusing audit overwrite'
    m = read(MANIFEST)
    assert m['status'] == 'PASS' and m['training_eligible'] and not m['TEST_accessed']
    assert m['schema'] == 'CM18_A1T_CSTAR_RELABEL_ALL816_V1'
    assert m['scene_count'] == m['qualified_count'] == 816 and m['failed_count'] == 0
    assert m['split_counts'] == {'TRAIN': 768, 'VAL': 48}
    assert m['dataset_manifest_sha256'] == OLD_SHA
    assert m['source_manifest_sha256'] == SOURCE_SHA
    assert digest(BASE / 'B_REF_REPAIRED_SOURCE_MANIFEST_v1.json') == SOURCE_SHA
    old_path = BASE / 'repaired_all816_v1/DATASET_MANIFEST_v1.json'
    assert digest(old_path) == OLD_SHA
    old_rows = read(old_path)['rows']
    assert len(m['rows']) == len(old_rows) == 816
    norm = read(ROOT / 'experiments/attitude_cm18_datarepair_20261024/training_a1r_v1/normalizer.json')
    mean = np.asarray(norm['input_mean_float64'], dtype=np.float64)
    std = np.asarray(norm['input_std_float64'], dtype=np.float64)
    old_rms = np.asarray(norm['train_axis_rms_rad_s2_float64'], dtype=np.float64)
    assert arrays_digest(mean, std, old_rms) == NORM_SHA
    targets = []
    splits = {'TRAIN': 0, 'VAL': 0}
    clips = np.zeros(3, dtype=np.int64)
    zero_nonzero = 0
    total_bytes = 0
    summaries = []
    stride = np.arange(0, 1996, 5)
    dmax = np.asarray(m['dmax_rad_s2']).reshape(3)
    for ordinal, (r, old) in enumerate(zip(m['rows'], old_rows, strict=True), 1):
        sid = r['scene_id']
        assert r['ordinal'] == ordinal == old['ordinal'] and sid == old['scene_id']
        assert r['status'] == 'PASS' and r['qualified'] and r['split'] == old['split']
        assert r['cache_schema'] == 'CM18_CSTAR_LABEL_CACHE_V1'
        assert r['input_cache_path'] == old['cache_path']
        assert r['input_cache_sha256'] == old['cache_sha256']
        cp = ROOT / r['cache_path']
        op = ROOT / r['input_cache_path']
        assert digest(cp) == r['cache_sha256'] and cp.stat().st_size == r['cache_bytes']
        assert digest(op) == old['cache_sha256']
        a = loadmat(cp, simplify_cells=True)
        o = loadmat(op, simplify_cells=True)
        assert 'X18' not in a and a['scene_id'] == sid and o['scene_id'] == sid
        assert a['split'] == r['split'] == o['split']
        assert a['old_cache_sha256'] == old['cache_sha256']
        assert a['source_manifest_sha256'] == SOURCE_SHA
        assert a['dataset_manifest_sha256'] == OLD_SHA
        x = o['X18']
        y = a['target_raw_output_rad_s2']
        cs = a['target_applied_acceleration_rad_s2']
        beta = a['beta']
        assert x.shape == (1999, 18) and y.shape == cs.shape == (1999, 3)
        assert np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(cs).all()
        assert np.array_equal(a['event_index'], np.arange(1, 2000))
        assert np.array_equal(a['plant_index'], np.arange(11, 20000, 10))
        for key in ('plant_index', 'event_time_s', 'phase_code'):
            assert np.array_equal(a[key], o[key]), (sid, key)
        expected_beta = np.minimum(a['plant_index'] * .001 / m['beta_rise_time_s'], 1)
        assert np.max(np.abs(beta - expected_beta)) < 1e-14 and np.all(beta > 0)
        assert np.max(np.abs(y * beta[:, None] - cs)) < 1e-10
        clipped = np.clip(y, -dmax, dmax)
        assert np.max(np.abs(a['target_after_clip_beta_rad_s2'] - clipped * beta[:, None])) < 1e-10
        mask = np.abs(y - clipped) > 1e-12
        assert np.array_equal(mask, a['output_clip_mask'].astype(bool))
        assert np.all(a['target_raw_output_reachable']) and not np.any(a['beta_zero_unreachable_mask'])
        g = a['G_column_major'].reshape(1999, 3, 3, order='F')
        assert np.isfinite(g).all() and np.all(np.linalg.matrix_rank(g) == 3)
        condition = np.linalg.cond(g)
        assert np.max(condition) < 1e12
        assert np.isclose(np.max(condition), r['max_G_condition_number'], rtol=1e-9, atol=1e-10)
        zb = np.all(x[:, 7:15] == 0, axis=1)
        zn = int(np.count_nonzero(np.any(np.abs(cs[zb]) > 1e-8, axis=1)))
        assert int(zb.sum()) == r['zero_morphology_basis_event_count']
        assert zn == r['zero_basis_nonzero_applied_target_count_gt_1e_8']
        for key in ('max_abs_behavior_target_vs_raw_physics_rad_s2',
                    'max_abs_behavior_target_vs_E0_matrix_relation_rad_s2',
                    'max_abs_E0_identity_rad_s2', 'max_abs_cstar_linear_solve_rad_s2'):
            assert r[key] <= 1e-8, (sid, key)
        assert np.array_equal(mask.sum(axis=0), [z['cstar_raw_output_clip_count'] for z in r['axis_summary']])
        for key, field in [('allocator_clip_mask', 'cstar_actual_beta_allocator_clip_count_by_channel'),
                           ('motor_saturation_mask', 'cstar_actual_beta_motor_saturation_count_by_motor')]:
            assert np.array_equal(a[key].sum(axis=0), r[field])
        splits[r['split']] += 1
        if r['split'] == 'TRAIN':
            targets.append(y[stride])
        clips += mask.sum(axis=0)
        zero_nonzero += zn
        total_bytes += cp.stat().st_size
        summaries.append({'scene_id': sid, 'split': r['split'], 'status': 'PASS',
                          'cache_sha256': r['cache_sha256']})
    assert splits == {'TRAIN': 768, 'VAL': 48}
    fit = np.concatenate(targets, axis=0)
    assert fit.shape == (307200, 3) and fit.flags.c_contiguous
    rms = np.sqrt(np.mean(fit * fit, axis=0, dtype=np.float64))
    assert np.isfinite(rms).all() and np.all(rms > 0)
    result = {'schema': 'CM18_CSTAR_ALL816_INDEPENDENT_AUDIT_V1', 'status': 'PASS',
              'scene_count': 816, 'split_counts': splits, 'train_fit_rows': 307200,
              'input_mean_float64': mean.tolist(), 'input_std_float64': std.tolist(),
              'target_axis_rms_rad_s2_float64': rms.tolist(),
              'canonical_normalizer_sha256': arrays_digest(mean, std, rms),
              'a1r_normalizer_canonical_sha256': NORM_SHA,
              'label_manifest_sha256': digest(MANIFEST), 'cache_bytes': total_bytes,
              'raw_output_clip_count_by_axis': clips.tolist(),
              'reachability_scope': 'Stored target_raw_output_reachable covers beta-zero division only; output_clip_mask separately reports limits that prevent exact application of cstar.',
              'zero_basis_nonzero_cstar_count_gt_1e_8': zero_nonzero,
              'scenes': summaries,
              'limits': 'Independent serialized-cache audit; raw physics closure values originate from reviewed MATLAB execution. Does not establish learnability or closed-loop stability.',
              'Plant_calls': 0, 'optimizer_steps': 0, 'TEST_accessed': False}
    OUTPUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(OUTPUT)


if __name__ == '__main__':
    main()
