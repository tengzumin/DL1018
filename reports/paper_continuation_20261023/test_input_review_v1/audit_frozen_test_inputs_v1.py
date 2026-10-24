"""Root input-only audit. Run after natural freeze OS0 and MATLAB load check."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / 'reports/paper_continuation_20261023'
ENTRY = REPORT / 'test_entry_v3'
EXP = ROOT / 'experiments/c5_test48_v3'
INPUT = EXP / 'input'
PHYSICAL = ['time', 'initial_state', 'environment_wind_I']
PHYSICAL += ['reference/' + k for k in ('position', 'velocity', 'acceleration', 'yaw', 'yaw_rate', 'yaw_acceleration')]
PHYSICAL += ['arms/' + k for k in ('command', 'rhoDot_hat', 'rhoDot_true', 'rho_hat', 'rho_true')]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unwrap(node):
    while isinstance(node, h5py.Dataset) and node.dtype.kind == 'O':
        refs = np.asarray(node).ravel()
        assert len(refs) == 1 and refs[0], node.name
        node = node.file[refs[0]]
    return node


def leaf(group, path):
    value = group
    for part in path.split('/'):
        value = unwrap(value[part])
    assert isinstance(value, h5py.Dataset), path
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Preserve earlier output'
    assert not (EXP / 'runs').exists(), 'This release audit must precede Plant'
    index_path = INPUT / 'TEST_INPUT_INDEX_v1.json'
    result_path = ENTRY / 'TEST_INPUT_FREEZE_RESULT_v1.json'
    receipt_path = ENTRY / 'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json'
    release_path = ENTRY / 'TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json'
    roundtrip_path = Path(__file__).parent / 'PARENT_TEST_INPUT_LOAD_ROUNDTRIP_v1.json'
    index, result, receipt, release, roundtrip = map(read, (index_path, result_path, receipt_path, release_path, roundtrip_path))
    assert receipt['matlab_os_exit_code'] == 0 and receipt['natural_wait_used'] is True
    assert receipt['TEST_accessed'] is True and receipt['plant_authorized'] is False
    assert result['status'] == 'PREPARED_TEST48_INPUTS_NO_PLANT' and result['plant_calls'] == 0
    assert result['TEST_accessed'] is True and result['training_steps'] == 0
    assert roundtrip['status'] == 'PASS_FROZEN_TEST48_LOAD_ROUNDTRIP_AND_SIX_CFG_OPTS'
    assert roundtrip['Plant_calls'] == roundtrip['scene_generation_calls'] == roundtrip['training_steps'] == 0
    assert roundtrip['TEST_outcomes_accessed'] is False and roundtrip['scene_count'] == 48
    assert result['freeze_release_sha256'] == index['freeze_release_sha256'] == sha(release_path)
    assert result['input_index_sha256'] == sha(index_path)
    for key, name in (('shared_scenes_mat_sha256', 'TEST_SCENES_SHARED_v1.mat'), ('method_cfg_opts_sha256', 'TEST_METHOD_CFG_OPTS_v1.mat')):
        assert index[key] == result[key] == sha(INPUT / name)
    for prefix in ('stdout', 'stderr'):
        assert receipt[prefix + '_sha256'] == sha(receipt[prefix + '_path'])
    assert release['contract_sha256'] == receipt['contract_sha256'] == sha(EXP / 'TEST48_RUN_CONTRACT_v1.json')
    assert release['method_source_manifest_sha256'] == receipt['source_manifest_sha256'] == index['method_source_manifest_sha256'] == sha(ENTRY / 'TEST_METHOD_SOURCE_MANIFEST_v1.json')
    assert release['entry_sha256'] == sha(EXP / 'test48_entry_v1.m')
    assert release['launcher_sha256'] == receipt['command_sha256'] == sha(EXP / 'RUN_TEST48_EXACT_v1.ps1')
    assert release['statistics_source_sha256'] == sha(REPORT / 'test_statistics_v1/test48_statistics.py')
    assert index['scene_specs_sha256'] == release['scene_specs_sha256'] == sha(ROOT / 'configs/scene_specs.csv')
    with (ROOT / 'configs/scene_specs.csv').open(encoding='utf-8-sig', newline='') as stream:
        expected_ids = sorted(row['scene_id'] for row in csv.DictReader(stream) if row['split'] == 'TEST')
    assert len(expected_ids) == len(set(expected_ids)) == 48
    assert index['scene_ids'] == expected_ids
    assert index['scene_set_sha256'] == hashlib.sha256('\n'.join(expected_ids).encode()).hexdigest()
    assert [r['scene_id'] for r in roundtrip['scenes']] == expected_ids
    assert [r['serialized_pack_sha256'] for r in roundtrip['scenes']] == index['scene_digests']
    assert len(roundtrip['methods']) == 6
    physical_rows = []
    with h5py.File(INPUT / 'TEST_SCENES_SHARED_v1.mat', 'r') as file:
        refs = np.asarray(file['scenePacks']).ravel()
        assert len(refs) == 48
        for i, (sid, ref) in enumerate(zip(expected_ids, refs)):
            pack = unwrap(file[ref]); scene = unwrap(pack['scene'])
            inventory = {row['field_path']: row for row in index['scene_field_arrays'][i]}
            assert len(inventory) == len(index['scene_field_arrays'][i])
            for key in PHYSICAL:
                dataset = leaf(scene, key)
                value = np.asarray(dataset).T
                assert value.ndim == 2 and np.isfinite(value).all(), (sid, key)
                cls = dataset.attrs['MATLAB_class']
                cls = cls.decode() if isinstance(cls, bytes) else str(cls)
                shape = '[' + ' '.join(str(n) for n in value.shape) + ']'
                digest = hashlib.sha256((cls + '|' + shape + '|').encode() + value.tobytes(order='F')).hexdigest()
                expected = inventory['pack.scene.' + key.replace('/', '.')]
                assert (digest, cls, shape) == (expected['array_sha256'], expected['matlab_class'], expected['shape']), (sid, key)
                physical_rows.append({'scene_id': sid, 'field': key, 'sha256': digest})
    assert len(physical_rows) == 672
    out = {'status': 'PASS_ROOT_TEST48_FROZEN_INPUTS_IDENTITIES_ARRAYS_ROUNDTRIP',
           'scene_count': 48, 'method_count': 6, 'physical_arrays_independently_rehashed': len(physical_rows),
           'physical_arrays': physical_rows, 'index_sha256': sha(index_path),
           'freeze_result_sha256': sha(result_path), 'freeze_os_exit_sha256': sha(receipt_path),
           'roundtrip_review_sha256': sha(roundtrip_path), 'freeze_release_sha256': sha(release_path),
           'checker_sha256': sha(Path(__file__)), 'TEST_accessed': True, 'TEST_outcomes_accessed': False,
           'Plant_calls': 0, 'training_steps': 0, 'Plant_run_authorized_by_this_output': False}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(out, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'physical_arrays'}))


if __name__ == '__main__':
    main()
