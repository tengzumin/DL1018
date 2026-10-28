"""Independently check the released DEV input audit, including actual B MAT bytes.

No generator, Plant, TEST arrays or training is invoked. MATLAB leaf hashes are
recomputed from HDF5 numeric datasets using independently constructed headers.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PHYSICAL = ['time', 'initial_state', 'environment_wind_I']
PHYSICAL += ['reference/' + k for k in ('position', 'velocity', 'acceleration', 'yaw', 'yaw_rate', 'yaw_acceleration')]
PHYSICAL += ['arms/' + k for k in ('command', 'rhoDot_hat', 'rhoDot_true', 'rho_hat', 'rho_true')]

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def array_sha(dataset):
    a = np.asarray(dataset)
    assert a.ndim == 2 and np.isfinite(a).all(), dataset.name
    a = a.T
    cls = dataset.attrs['MATLAB_class']
    cls = cls.decode() if isinstance(cls, bytes) else str(cls)
    shape = '[' + ' '.join(str(x) for x in a.shape) + ']'
    # MATLAB stores value(:); h5py exposes the reversed dimension convention.
    h = hashlib.sha256((cls + '|' + shape + '|').encode('utf-8'))
    h.update(a.tobytes(order='F'))
    return h.hexdigest(), cls, shape

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--report-dir', type=Path, required=True)
    p.add_argument('--experiment-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists(), 'Preserve earlier reviews'
    d, e = args.report_dir, args.experiment_dir
    rp = d / 'DEV_INPUT_EQUIVALENCE_RESULT_v1.json'
    op = d / 'DEV_INPUT_EQUIVALENCE_MATLAB_OS_EXIT_v1.json'
    lp = d / 'DEV_INPUT_EQUIVALENCE_PARENT_RELEASE_v1.json'
    mp = d / 'TEST_METHOD_SOURCE_MANIFEST_v1.json'
    cp = e / 'TEST48_RUN_CONTRACT_v1.json'
    result, os, release, manifest, contract = map(read, (rp, op, lp, mp, cp))
    assert os['matlab_os_exit_code'] == 0 and os['natural_wait_used'] is True
    assert os['TEST_accessed'] is False and os['plant_authorized'] is False
    assert result['status'] == 'PASS_DEV_ALL72_GENERATOR_EQUIVALENCE'
    assert result['scene_count'] == 72 and result['TEST_accessed'] is False and result['plant_calls'] == 0
    assert release['plant_authorized'] is False and release['TEST_accessed'] is False
    assert release['contract_sha256'] == sha(cp) and release['method_source_manifest_sha256'] == sha(mp)
    assert release['entry_sha256'] == sha(e / 'test48_entry_v1.m')
    assert release['launcher_sha256'] == sha(e / 'RUN_TEST48_EXACT_v1.ps1')
    assert os['command_sha256'] == release['launcher_sha256']
    assert os['contract_sha256'] == sha(cp) and os['source_manifest_sha256'] == sha(mp)
    for prefix in ('stdout', 'stderr'):
        assert os[prefix + '_sha256'] == sha(os[prefix + '_path'])
    ids = result['scene_ids']
    assert len(ids) == len(set(ids)) == 72
    assert sum(x.startswith('DL1018_DEV_') for x in ids) == 24
    assert sum(x.startswith('DL1018_VAL_') for x in ids) == 48
    assert all(x.startswith(('DL1018_DEV_', 'DL1018_VAL_')) for x in ids)
    c5 = next(x for x in manifest['methods'] if x['method_id'] == 'C5_M110')
    lock = read(c5['input_lock_path'])
    assert ids == lock['scene_ids_all_72']
    assert result['C5_DEV72_input_lock_sha256'] == sha(c5['input_lock_path'])
    methods = result['six_method_cfg_opts_model_preflight']
    assert len(methods) == 6
    assert [x['method_id'] for x in methods] == [x['id'] for x in contract['method_order']]
    assert len({x['cfg_value_sha256'] for x in methods}) == 1
    for actual, expected in zip(methods, manifest['methods']):
        assert actual['snapshot_file_sha256'] == expected['cfg_opts_snapshot_sha256']
        assert actual['TEST_accessed'] is False and actual['plant_calls'] == 0
        expected_paths = {Path(x['path']).stem: Path(x['path']).resolve()
                          for x in expected['source_refs'] if Path(x['path']).suffix.lower() == '.m'}
        seen = set()
        for binding in actual['which_bindings']:
            name = binding['function_name']; seen.add(name)
            assert Path(binding['resolved_first_path']).resolve() == expected_paths[name]
            assert Path(binding['expected_path']).resolve() == expected_paths[name]
        assert seen == set(expected_paths)
        if actual['method_id'] != 'B_TRACEABLE':
            assert actual['model_mat_sha256'] == next(x['sha256'] for x in expected['model_refs'] if x['role'] == 'model_mat')
            assert actual['normalizer_sha256'] == next(x['sha256'] for x in expected['model_refs'] if x['role'] == 'normalizer')
            assert actual['initial_weight_identity'] == actual['model_identity']['W0_sha256']
    records = result['records']; assert len(records) == 72
    assert [x['scene_id'] for x in records] == ids
    locked = {x['scene_id']: x for x in lock['scenes']}
    physical_fields = 0; all_fields = 0; max_diff = 0.; actual_scene_hashes = []; id_representations = []
    for record in records:
        sid = record['scene_id']; src = locked[sid]['B_source']
        assert Path(record['B_source_path']).resolve() == Path(src['path']).resolve()
        assert record['B_source_sha256'] == src['sha256'] == sha(src['path'])
        for key in ('current_vs_B_max_abs', 'corrected_vs_current_max_abs'):
            assert 0 <= record[key] <= 1e-12
            max_diff = max(max_diff, record[key])
        fields = record['field_audits']; all_fields += len(fields)
        by_relation = {}
        for row in fields:
            assert row['scene_id'] == sid
            if row['shape_a'] != row['shape_b'] or row['class_a'] != row['class_b']:
                assert row['relation'] == 'B_source_vs_current' and row['field_path'] == 'scene.scene_id'
                assert sid.startswith(('DL1018_DEV_T2_', 'DL1018_VAL_T2_'))
                assert (row['shape_a'], row['class_a'], row['shape_b'], row['class_b']) == ('[1 21]', 'char', '[1 1]', 'string')
                assert row['exact_value_equal'] is True and row['bit_equal'] is False
                expected_char_sha = hashlib.sha256(('char|[1 21]|').encode() + sid.encode('utf-16-le')).hexdigest()
                assert row['sha256_a'] == expected_char_sha
                id_representations.append(dict(scene_id=sid, historical='char', current='string', text_equal=True, byte_equal=False))
            else:
                assert row['shape_a'] == row['shape_b'] and row['class_a'] == row['class_b']
            assert math.isfinite(row['max_abs_diff']) and 0 <= row['max_abs_diff'] <= 1e-12
            assert row['bit_equal'] == (row['sha256_a'] == row['sha256_b'])
            key = (row['relation'], row['field_path']); assert key not in by_relation
            by_relation[key] = row
        with h5py.File(src['path'], 'r') as f:
            id_row = by_relation[('B_source_vs_current', 'scene.scene_id')]
            # B raw scene may be a serialized MATLAB string; only char leaves decode as UTF-16.
            ds = f['scene/scene_id']; cls = ds.attrs['MATLAB_class']
            cls = cls.decode() if isinstance(cls, bytes) else str(cls)
            if cls == 'char':
                actual_text = bytes(np.asarray(ds, dtype='<u2').T.tobytes(order='F')).decode('utf-16-le')
                assert actual_text in (sid, sid + '_ACC_FIX_V1')
            for key in PHYSICAL:
                digest, cls, shape = array_sha(f['scene/' + key])
                row = by_relation[('B_source_vs_current', 'scene.' + key.replace('/', '.'))]
                assert (digest, cls, shape) == (row['sha256_a'], row['class_a'], row['shape_a']), (sid, key)
                counterpart = by_relation[('current_vs_corrected_fixed', row['field_path'])]
                assert row['sha256_b'] == counterpart['sha256_a'], (sid, key)
                physical_fields += 1
        notes = record['reference_contract_note_normalizations']
        assert len(notes) == 3
        assert all(x['current_value'] == 'DL1018_SCENE_REF_FIG8_A2_V2' and x['historical_field_absent'] is True for x in notes)
        actual_scene_hashes.append(dict(scene_id=sid,physical_arrays_independently_rehashed=len(PHYSICAL),B_source_sha256=src['sha256']))
    assert physical_fields == 72 * len(PHYSICAL)
    assert len(id_representations) == 24
    out = dict(status='PASS_ROOT_DEV72_INPUT_EQUIVALENCE_AND_SIX_METHOD_PREFLIGHT',
        scene_count=72,methods=6,physical_arrays_independently_rehashed=physical_fields,
        field_rows_checked=all_fields,max_reported_abs_difference=max_diff,
        text_identity_representation_differences=id_representations,
        physical_byte_equivalence=True, whole_pack_byte_equivalence=False,
        note='24 historical normalized T2 IDs use char versus string. IDs match exactly as text; physical arrays remain byte-identical. Top-level MATLAB bit_equal is isequaln value equivalence, not a whole-pack byte digest.',
        scenes=actual_scene_hashes,result_sha256=sha(rp),os_exit_sha256=sha(op),release_sha256=sha(lp),
        manifest_sha256=sha(mp),contract_sha256=sha(cp),checker_sha256=sha(Path(__file__)),
        TEST_accessed=False,Plant_started=False,TEST_input_freeze_authorized=False)
    args.output.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k != 'scenes'}))

if __name__ == '__main__':
    main()
