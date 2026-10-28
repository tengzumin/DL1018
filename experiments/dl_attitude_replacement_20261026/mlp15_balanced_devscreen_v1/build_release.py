"""Freeze one balanced-model development screen, reusing existing inputs/runtime."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
OLD = RESEARCH / 'mlp15_dev72_v2'
BALANCED = RESEARCH / 'mlp15_c5_teacher_ghp7_balance_v1'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    if (HERE / 'RELEASE_v2.json').exists() or (HERE / 'SOURCE_LOCK_v2.json').exists():
        raise FileExistsError('Preserve existing release; do not regenerate it.')
    parent_manifest = OLD / 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'
    manifest = read(parent_manifest)
    teacher_manifest = RESEARCH / 'mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json'
    teacher = read(teacher_manifest)
    old_lock_path = OLD / 'MLP15_DEV72_CANDIDATE_SOURCE_LOCK_v1.json'
    old_lock = read(old_lock_path)
    runner = OLD / 'candidate_runner_work'
    source = []
    for rec in old_lock['files']:
        path = runner / rec['relative_path']
        assert sha(path) == rec['sha256'], path
        source.append({'path': str(path), 'sha256': rec['sha256']})
    shared = RESEARCH / 'pilot_runner_mlp15_c5_full72_v1/candidate_runner_work'
    # The tested forward/step and common control path must match the GHP7 deployment.
    matched = []
    for rel in ['matlab/runtime/mlp15_attitude_step_v1.m',
                'matlab/runtime/mlp15_attitude_forward_v1.m',
                'matlab/runtime/make_paired_c5_options.m',
                'matlab/runtime/bind_paired_fixed_j0.m',
                'matlab/core/baseline_force_to_attitude.m',
                'matlab/core/attitude_bs_step.m',
                'matlab/core/position_bs_step.m',
                'matlab/core/command_filter_step.m']:
        assert sha(runner / rel) == sha(shared / rel), rel
        matched.append(rel)
    selected = []
    for task in ['T1', 'T2', 'T3']:
        for lower, upper in [(0, 8), (9, 11), (12, 14), (15, 15)]:
            candidates = [r for r in manifest['records']
                          if r['scene_id'].startswith(f'DL1018_VAL_{task}_')
                          and lower <= int(r['scene_id'].rsplit('_W', 1)[1]) <= upper]
            rec = dict(sorted(candidates, key=lambda r: r['scene_id'])[0])
            matches = [r for r in teacher['rows'] if r['teacher_source'] == 'C5_RBF'
                       and r['scene_id'] == rec['scene_id']]
            assert len(matches) == 1
            c5 = matches[0]
            rec.update(c5_raw_path=c5['raw_path'], c5_raw_sha256=c5['raw_sha256'],
                       c5_status_path=c5['status_path'], c5_status_sha256=c5['status_sha256'])
            for path_key, hash_key in [('payload_path', 'payload_sha256'),
                                       ('b_raw_path', 'b_raw_sha256'),
                                       ('b_status_path', 'b_status_sha256'),
                                       ('c5_raw_path', 'c5_raw_sha256'),
                                       ('c5_status_path', 'c5_status_sha256')]:
                assert sha(rec[path_key]) == rec[hash_key], rec[path_key]
            selected.append(rec)
    selected.sort(key=lambda r: r['scene_id'])
    assert len({r['scene_id'] for r in selected}) == 12
    assert all('TEST' not in r['scene_id'] for r in selected)
    train = BALANCED / 'runs/C5_MLP15_GHP7_BALANCE_SEED2026102001'
    model = train / 'mlp15_attitude_weights_v1.mat'
    expected = '8e048e212ae17f4e588ba35d7af18ed5183799074fbc2c66dfe7c6e5a77d8138'
    assert sha(model) == expected
    assert read(train / 'training_config.json')['status'] == 'PASS'
    assert read(train / 'training_config.json')['optimizer_steps'] == 60000
    assert read(train / 'run_receipt.json')['TEST48_read'] is False
    for path in [HERE / 'TASKBOOK.md', HERE / 'balanced_devscreen.m', Path(__file__),
                 model, train / 'final_step_60000.pt', train / 'training_config.json',
                 train / 'run_receipt.json', BALANCED / 'MLP15_C5_GHP7_BALANCE_SOURCE_LOCK_v1.json',
                 BALANCED / 'audits/MATLAB_PARITY_GHP7_BALANCE_v1.json',
                 parent_manifest, teacher_manifest, old_lock_path]:
        source.append({'path': str(path), 'sha256': sha(path)})
    input_manifest = {'schema': 'BALANCED_DEVSCREEN_INPUTS_V1',
          'TEST_read': False, 'teacher_data_already_used_for_training': True,
          'records': selected, 'matched_shared_control_sources': matched}
    if (HERE / 'MANIFEST.json').exists():
        assert read(HERE / 'MANIFEST.json') == input_manifest
    else:
        write(HERE / 'MANIFEST.json', input_manifest)
    source.append({'path': str(HERE / 'MANIFEST.json'), 'sha256': sha(HERE / 'MANIFEST.json')})
    write(HERE / 'SOURCE_LOCK_v2.json', {'schema': 'BALANCED_DEVSCREEN_SOURCE_LOCK_V2', 'files': source})
    write(HERE / 'RELEASE_v2.json', {'schema': 'BALANCED_DEVSCREEN_RELEASE_V2',
          'status': 'ROOT_RELEASED_FIRST_SCENE_THEN_REVIEW',
          'authorization': 'User: 倾角投影到底是什么，先放行呗',
          'created_utc': datetime.now(timezone.utc).isoformat(), 'max_Plant_calls': 12,
          'TEST_read': False, 'runtime_root': str(runner), 'model_path': str(model),
          'model_sha256': expected, 'source_lock_sha256': sha(HERE / 'SOURCE_LOCK_v2.json'),
          'manifest_sha256': sha(HERE / 'MANIFEST.json'),
          'taskbook_sha256': sha(HERE / 'TASKBOOK.md'),
          'first_scene_id': selected[0]['scene_id']})
    print(json.dumps({'status': 'RELEASE_BUILT', 'scenes': [r['scene_id'] for r in selected]}, indent=2))

if __name__ == '__main__':
    main()
