"""Parent-only identity audit and exact release for the frozen C5 eleven-scene tail."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / 'experiments/position_axis_coordinate_c5_20261023'
OUT = Path(__file__).resolve().parent
EXEC = OUT.parent / 'c5_axis_coordinate_execution'
CACHE = {}


def sha(path):
    path = Path(path).resolve()
    if str(path) not in CACHE:
        with path.open('rb') as f:
            CACHE[str(path)] = hashlib.file_digest(f, 'sha256').hexdigest()
    return CACHE[str(path)]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verify_tree(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            assert sha(value['path']) == value['sha256'].lower(), value['path']
        for key, val in value.items():
            if key.endswith('_path') and key[:-5] + '_sha256' in value:
                assert sha(val) == value[key[:-5] + '_sha256'].lower(), val
            verify_tree(val)
    elif isinstance(value, list):
        for item in value:
            verify_tree(item)


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def main():
    release_path = EXP / 'C5_TAIL11_RELEASE_v1.json'
    assert not release_path.exists()
    ready = load(EXEC / 'C5_TAIL11_CODE_READY_v2.json')
    assert sha(EXEC / 'C5_TAIL11_CODE_READY_v2.json') == 'b5f591c7a5e9e04041733227e9d8d26d8728a3ed5bfadd241ef7b5bab5e2ab6b'
    binding = load(EXP / 'C5_TAIL11_SOURCE_BINDING_v1.json')
    contract = load(EXP / 'C5_TAIL11_RUN_CONTRACT_v1.json')
    release_contract = load(EXP / 'C5_TAIL11_PARENT_RELEASE_CONTRACT_v1.json')
    lock = load(EXP / 'C5_AXIS_COORDINATE_INPUT_LOCK_v1.json')
    first = load(EXP / 'C5_FIRST_PARENT_RELEASE_v1.json')
    original = load(EXP / 'C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json')
    for item in (ready, binding, contract, lock, first):
        verify_tree(item)
    roles = {r['role']: r for r in binding['source_files']}
    assert len(roles) == len(binding['source_files'])
    assert sha(roles['tail_runner']['path']) == 'a37782a9149bea1b6a745463e234e0b0f333985882a11b0f62bc3e7ed01c965b'
    assert sha(roles['launcher']['path']) == '6a3695b816e9bd43a9049cb97d8fa71148901def1ca1bd837b1483435fcae00e'
    assert sha(EXP / 'C5_TAIL11_SOURCE_BINDING_v1.json') == '87e034b4d6b27ee0af3f49b24ee492c350a5376aa05ae90630ef0f60555b1ecd'
    assert binding['active_source_inventory'] == lock['active_source_inventory']
    assert binding['shared_input_files'] == lock['shared_input_files']
    assert binding['lock_upstream_refs'] == lock['upstream_refs']
    assert contract['model'] == original['model'] and contract['fixed_parameters'] == original['fixed_parameters']
    expected = [s for s in original['scene_ids'] if s != first['scene_id']]
    assert len(expected) == len(set(expected)) == 11
    assert expected == contract['tail_scene_ids'] == binding['tail_scene_ids']
    assert contract['coordinate_mask'] == [1, 1, 0]
    for scene in expected:
        assert not (EXP / 'runs_c5_v1' / scene / 'C5_AXIS_MASK_M110/attempt_01').exists()
    refs = binding['pilot_refs']
    meta = load(refs['metadata_os_review']['path'])
    assert meta['status'] == 'PASS_C5_FIRST_RAW_METADATA_NATURAL_OS0_ALLOW_TAIL11_IMPLEMENTATION_ONLY'
    assert meta['natural_MATLAB_OS_exit_code'] == 0 and not meta['first_scene_beats_B']
    b72 = load(binding['b72']['raw_manifest_path'])
    assert len(b72['records']) == len({r['scene_id'] for r in b72['records']}) == 72
    c3lock = load(lock['upstream_refs']['c3_input_lock']['path'])
    assert [r['scene_id'] for r in b72['records']] == c3lock['scene_ids_all_72']
    for row in lock['scenes']:
        if row['scene_id'] in expected:
            verify_tree(row['B_source'])
    for row in b72['records']:
        if row['scene_id'] in expected:
            verify_tree(row)
    limits = contract['limits']
    free = shutil.disk_usage(ROOT).free
    total_bytes = sum(p.stat().st_size for p in EXP.rglob('*') if p.is_file())
    assert free - 11 * limits['per_scene_output_reserve_bytes'] >= limits['minimum_free_bytes']
    assert total_bytes + 11 * limits['per_scene_output_reserve_bytes'] <= limits['max_output_bytes']
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(limits['deadline_utc'].replace('Z', '+00:00'))
    assert (deadline - now).total_seconds() >= 11 * 180 + 600
    review = {
        'status': 'PASS_PARENT_C5_TAIL11_SOURCE_AND_IDENTITIES', 'created_utc': now.isoformat(),
        'verified_unique_files': len(CACHE), 'verified_file_sha256': CACHE.copy(),
        'scope': 'Parent read all 705 MATLAB runner lines, full PS launcher/contracts and source bindings; actual pilot review reused; no new Plant/raw decode in this review.',
        'engineering_fix': 'Prelaunch-only UtcNow method-to-property correction; old launcher/binding/CODE_READY retained by amendment.',
        'algorithm_changes_in_tail': 0, 'pilot_repeat_authorized': False,
        'free_bytes': free, 'experiment_bytes_before_release': total_bytes,
        'gates_unchanged': True, 'TEST_accessed': False,
    }
    review_path = OUT / 'PARENT_C5_TAIL11_SOURCE_REVIEW_v1.json'
    if not review_path.exists():
        write_new(review_path, review)
    else:
        # Preserve the already written source audit after a release-field assembly failure.
        prior = load(review_path)
        assert prior['status'] == review['status'] and prior['gates_unchanged']
        for path, digest in prior['verified_file_sha256'].items():
            assert sha(path) == digest, path
    release = dict(release_contract['required_values'])
    release.update({
        'schema': release_contract['parent_release_schema'], 'state': release_contract['required_release_state'],
        'created_utc': now.isoformat(), 'tail_scene_ids': expected,
        'tail_source_binding_sha256': sha(EXP / 'C5_TAIL11_SOURCE_BINDING_v1.json'),
        'tail_runner_sha256': roles['tail_runner']['sha256'], 'tail_runner_path': roles['tail_runner']['path'],
        'launcher_sha256': roles['launcher']['sha256'],
        'tail_run_contract_sha256': roles['tail_contract']['sha256'],
        'parent_release_contract_sha256': roles['parent_release_contract']['sha256'],
        'c5_input_lock_sha256': binding['input_lock_sha256'],
        'c5_run_contract_sha256': binding['original_run_contract_sha256'],
        'prepare_result_sha256': binding['prepare_result_sha256'],
        'cfg_opts_snapshot_sha256': binding['snapshot_sha256'],
        'first_scene_parent_release_sha256': binding['first_scene_release_sha256'],
        'deadline_utc': limits['deadline_utc'],
        'parent_source_review': {'path': str(review_path), 'sha256': sha(review_path)},
        'code_ready': {'path': str(EXEC / 'C5_TAIL11_CODE_READY_v2.json'), 'sha256': sha(EXEC / 'C5_TAIL11_CODE_READY_v2.json')},
    })
    for field, role in {
        'first_scene_raw_sha256': 'first_raw', 'first_scene_run_status_sha256': 'run_status',
        'first_scene_run_start_sha256': 'run_start', 'first_scene_first_plant_marker_sha256': 'first_plant_step_marker',
        'first_scene_matlab_os_exit_sha256': 'matlab_os_exit', 'first_scene_execution_receipt_sha256': 'execution_receipt',
        'first_scene_outer_invocation_history_sha256': 'outer_invocation_history',
        'first_scene_raw_review_sha256': 'raw_review', 'first_scene_metadata_os_review_sha256': 'metadata_os_review',
    }.items():
        release[field] = refs[role]['sha256']
    for field, val in binding['b72'].items():
        if field != 'complete_scene_count':
            release['b72_' + field] = val
    for suffix in ('input_lock', 'run_contract', 'prepare_result', 'release'):
        release['b72_' + suffix + '_sha256'] = lock['upstream_refs']['b72_' + suffix]['sha256']
    # These fields are actually consumed by the runner's first-scene B72 checks.
    for field in ('scene_id', 'b72_first_scene_raw_path', 'b72_first_scene_raw_sha256',
                  'b72_first_scene_status_path', 'b72_first_scene_status_sha256'):
        release[field] = first[field]
    assert set(release_contract['required_fields']) <= set(release), sorted(set(release_contract['required_fields']) - set(release))
    for key, val in release_contract['required_values'].items():
        assert release[key] == val, key
    verify_tree(release)
    write_new(release_path, release)
    print(json.dumps({'status': review['status'], 'verified_unique_files': len(CACHE),
                      'release_sha256': sha(release_path), 'release_path': str(release_path)}, indent=2))


if __name__ == '__main__':
    main()
