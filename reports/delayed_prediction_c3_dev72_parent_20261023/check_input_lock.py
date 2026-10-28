"""Check frozen lock scope and actual source/reference bytes before MATLAB."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def references(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield value
        else:
            for item in value.values():
                yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--expected-lock-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Preserve earlier evidence'
    assert sha(args.lock) == args.expected_lock_sha.lower()
    lock = json.loads(args.lock.read_text(encoding='utf-8-sig'))
    here = Path(__file__).resolve().parent
    scope = json.loads((here.parent / 'delayed_prediction_c3_parent_20261023/DEV72_SCENE_SCOPE_DRAFT.json').read_text(encoding='utf-8-sig'))
    expected = {r['scene_id']: r for r in scope['rows']}
    scenes = {r['scene_id']: r for r in lock['scenes']}
    assert len(scenes) == len(expected) == 72 and set(scenes) == set(expected)
    assert Counter(r['source_split'] for r in lock['scenes']) == {'DEV': 24, 'VAL': 48}
    new = [r['scene_id'] for r in lock['scenes'] if r['candidate_action'] == 'PROPOSE_NEW_C3_RUN']
    reuse = [r['scene_id'] for r in lock['scenes'] if r['candidate_action'] == 'REUSE_C3_SCREEN']
    assert new == sorted(new) == lock['scene_ids_new_60'] and len(new) == 60 and len(reuse) == 12
    for sid in reuse:
        row, frozen = scenes[sid]['C3_reuse'], expected[sid]
        assert Path(row['raw_path']).resolve() == Path(frozen['C3_existing_raw_path']).resolve()
        assert row['raw_sha256'] == frozen['C3_existing_raw_sha256']
        assert row['status_sha256'] == frozen['C3_status_sha256']
    checked = {}
    for section in ['authorization_and_scope_refs', 'historical_review_refs', 'c3_reference_refs',
                    'source_files', 'shared_input_files', 'frozen_runtime_files', 'frozen_plant_files',
                    'previous_attempt_refs']:
        for item in references(lock.get(section, {})):
            path = Path(item['path']).resolve()
            actual = checked.get(str(path), {}).get('actual_sha256') or sha(path)
            assert actual == item['sha256'].lower(), (str(path), item['sha256'], actual)
            checked[str(path)] = dict(path=str(path), actual_sha256=actual)
    isolated = {r['role']: r for r in lock['source_files']['isolated_c3_sources']}
    active = []
    for item in lock['frozen_runtime_files']:
        leaf = Path(item['path']).name
        replacement = {'run_dl1018_closed_loop.m': 'runtime_core', 'run_episode_dl1018.m': 'episode_wrapper'}.get(leaf)
        active.append(isolated[replacement] if replacement else item)
    active.append(isolated['prediction_helper'])
    active += lock['frozen_plant_files']
    assert len(active) == len({Path(r['path']).name for r in active}) == 32
    result = dict(status='PASS_FROZEN_SCOPE_SOURCE_BYTES_AND_12_REUSE_ANCHORS',
                  lock_path=str(args.lock.resolve()), lock_sha256=sha(args.lock),
                  checked_unique_references=list(checked.values()), active_source_inventory=active,
                  new_scenes=60, reused_scenes=12, historical_raw_rehash_in_this_check=False,
                  new_Plant=0, training=0, TEST_accessed=False)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], checked_unique_references=len(checked), active_sources=len(active))))
