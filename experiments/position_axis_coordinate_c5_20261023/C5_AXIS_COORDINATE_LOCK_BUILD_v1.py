from __future__ import annotations
import copy, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
C4 = ROOT / 'experiments/position_coordinate_c4_20261023'
C3 = ROOT / 'experiments/position_delayed_prediction_c3_dev72_20261023'
B72 = ROOT / 'experiments/b_traceable_c3core_dev72_20261023'
TASKBOOK = ROOT / 'reports/paper_continuation_20261023/C5_AXIS_COORDINATE_SCREEN_TASKBOOK_ZH.md'
C4_LOCK = C4 / 'C4_INPUT_LOCK_v3.json'
LOCK = HERE / 'C5_AXIS_COORDINATE_INPUT_LOCK_v1.json'
CONTRACT = HERE / 'C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json'
BINDING = HERE / 'C5_SOURCE_BINDING_v1.json'
C4_LOCK_SHA = '59d1c81f73f8362c15183492d921f5f1d5d1afe12f41949b618497a9e75892d2'
TASKBOOK_SHA = '5c3f19548a5cd1f6e337d20dcd0c48f81560d3907d5a24d20676e9cf62545c38'
C3_LOCK_SHA = 'a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730'
C4_FINDINGS_SHA = '3f078b28468e3e83cf7733a6ec37fa53e4af9ee79dda6e6bd49f4dddab4bedc7'
C4_SUMMARY_SHA = '616e70afbb3b2d07b7837641c3f6ef579a1e03888fa5014b30627805eccfc44b'


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ref(p: Path) -> dict[str, str]:
    p = p.resolve()
    return {'path': str(p), 'sha256': sha(p)}


def main() -> None:
    assert not LOCK.exists() and not BINDING.exists(), 'refusing to overwrite C5 lock/binding'
    assert sha(C4_LOCK) == C4_LOCK_SHA and sha(TASKBOOK) == TASKBOOK_SHA
    assert sha(C3 / 'C3_DEV72_INPUT_LOCK_v2.json') == C3_LOCK_SHA
    c4 = json.loads(C4_LOCK.read_text(encoding='utf-8'))
    contract = json.loads(CONTRACT.read_text(encoding='utf-8'))
    assert c4['schema'] == 'C4_COORDINATE_INPUT_LOCK_V3'
    assert contract['schema'] == 'C5_AXIS_COORDINATE_RUN_CONTRACT_V1'
    assert contract['state'] == 'LOCKED_C5_AXIS_COORDINATE_NO_PLANT_PARENT_REVIEW_REQUIRED_V1'
    assert contract['coordinate_mask'] == [1, 1, 0]
    assert contract['scene_ids'] == c4['scene_ids_reuse_12']
    assert contract['first_scene_id'] == c4['first_scene_id']

    payload = copy.deepcopy(c4)
    payload['schema'] = 'C5_AXIS_COORDINATE_INPUT_LOCK_V1'
    payload['state'] = contract['state']
    payload['created_utc'] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    payload['taskbook_sha256'] = TASKBOOK_SHA
    payload['coordinate_mask'] = [1, 1, 0]
    payload.pop('coordinate_factor_m', None)
    payload['scope'] = contract
    payload['plant_authorized_by_this_lock'] = False
    payload['source_counts'] = {'total': 32, 'matlab': 31, 'mat': 1}
    payload['notes'] = [
        'No Plant release is created by this lock.',
        'C3 12-scene physical B_source rows remain the input-only identity; scoring B is the new traceable B72 manifest bound by a later parent release.',
        'C5 has exactly one permitted Plant mask M=diag(1,1,0); M=I and M=0 occur only in the no-Plant synthetic fixture.',
        'C5 uses the complete C3 sceneIdentity schema copied row-by-row; no legacy raw files are rewritten.'
    ]

    # Bind the three isolated source files and update those exact entries in the inherited 32-file runtime inventory.
    isolated = [
        ('runtime_core', HERE / 'run_dl1018_closed_loop.m'),
        ('episode_wrapper', HERE / 'run_episode_dl1018.m'),
        ('prediction_helper', HERE / 'delayed_prediction_step_candidate.m'),
    ]
    payload['source_files'] = {
        'lock_builder': ref(Path(__file__)),
        'prepare_entry': ref(HERE / 'prepare_c5_axis_coordinate_v1.m'),
        'single_scene_runner': ref(HERE / 'run_c5_axis_coordinate_v1.m'),
        'contract': ref(CONTRACT),
        'parent_release_contract': ref(HERE / 'C5_FIRST_PARENT_RELEASE_CONTRACT_v1.json'),
        'synthetic_generator': ref(HERE / 'c5_axis_coordinate_fixture_v1.py'),
        'synthetic_check': ref(HERE / 'check_c5_axis_coordinate_synthetic_v1.m'),
        'synthetic_fixture': ref(HERE / 'C5_CROSSLANG_FIXTURE_v1.json'),
        'no_plant_launcher': ref(HERE / 'RUN_C5_NOPLANT_EXACT_v1.ps1'),
        'first_scene_launcher': ref(HERE / 'RUN_C5_FIRST_EXACT_v1.ps1'),
        'isolated_sources': [{'role': role, **ref(path)} for role, path in isolated],
    }
    for role, path in isolated:
        matches = [i for i, item in enumerate(payload['active_source_inventory']) if item['role'] == role]
        assert len(matches) == 1, f'expected exactly one active role {role}'
        payload['active_source_inventory'][matches[0]] = {'role': role, **ref(path)}
    assert len(payload['active_source_inventory']) == 32
    assert payload['source_counts']['matlab'] == 31 and payload['source_counts']['mat'] == 1

    # C5 upstream evidence: frozen C3 source identities, C4 failure review, and current B72 no-Plant inputs.
    upstream = {k: v for k, v in payload['upstream_refs'].items() if k not in {'taskbook', 'design_review', 'realization_review'}}
    upstream.update({
        'c5_taskbook': ref(TASKBOOK),
        'c4_parent_findings': ref(ROOT / 'reports/paper_continuation_20261023/c4_coordinate_parent_review/C4_SCREEN12_PARENT_FINDINGS_ZH.md'),
        'c4_parent_summary': ref(ROOT / 'reports/paper_continuation_20261023/c4_coordinate_parent_review/screen12_parent_review/SUMMARY.json'),
        'b72_input_lock': ref(B72 / 'B_TRACEABLE_DEV72_INPUT_LOCK_v3.json'),
        'b72_run_contract': ref(B72 / 'B_TRACEABLE_DEV72_RUN_CONTRACT_v3.json'),
        'b72_prepare_result': ref(B72 / 'B_TRACEABLE_DEV72_PREPARE_RESULT_v3.json'),
        'b72_release': ref(B72 / 'B_TRACEABLE_DEV72_RELEASE_v3.json'),
    })
    assert upstream['c4_parent_findings']['sha256'] == C4_FINDINGS_SHA
    assert upstream['c4_parent_summary']['sha256'] == C4_SUMMARY_SHA
    payload['upstream_refs'] = upstream
    LOCK.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    # A flat, exact source binding is easy to audit and is independently hash-bound by a later Plant release.
    files = []
    for key, item in payload['source_files'].items():
        if key == 'isolated_sources': files.extend(item)
        elif isinstance(item, dict) and 'path' in item: files.append({'role': key, **item})
    files.extend(payload['active_source_inventory'])
    files.extend(payload['shared_input_files'])
    files.extend({'role': key, **item} for key, item in upstream.items())
    files.append({'role': 'c5_input_lock', **ref(LOCK)})
    unique = {}
    for item in files:
        unique[item['path'].lower()] = {'role': item.get('role', Path(item['path']).name),
                                        'path': item['path'], 'sha256': item['sha256']}
    binding = {
        'schema': 'C5_AXIS_COORDINATE_SOURCE_BINDING_V1',
        'state': 'SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V1',
        'input_lock_path': str(LOCK.resolve()),
        'input_lock_sha256': sha(LOCK),
        'contract_sha256': sha(CONTRACT),
        'runner_sha256': sha(HERE / 'run_c5_axis_coordinate_v1.m'),
        'coordinate_mask': [1, 1, 0],
        'active_source_count': len(payload['active_source_inventory']),
        'shared_input_count': len(payload['shared_input_files']),
        'file_refs': list(unique.values()),
        'plant_authorized': False,
        'created_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
    }
    assert binding['active_source_count'] == 32 and binding['shared_input_count'] == 6
    BINDING.write_text(json.dumps(binding, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'C5_LOCK_BUILT_NO_PLANT_PARENT_REVIEW_REQUIRED_V1',
                      'input_lock_path': str(LOCK.resolve()), 'input_lock_sha256': sha(LOCK),
                      'source_binding_path': str(BINDING.resolve()), 'source_binding_sha256': sha(BINDING),
                      'active_sources': 32, 'shared_inputs': 6, 'upstream_refs': len(upstream),
                      'scene_ids': contract['scene_ids']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
