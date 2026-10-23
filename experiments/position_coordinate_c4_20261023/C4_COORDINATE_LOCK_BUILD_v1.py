from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
C3 = ROOT / 'experiments' / 'position_delayed_prediction_c3_dev72_20261023'
LOCK_OUT = HERE / 'C4_INPUT_LOCK_v1.json'
TASKBOOK_SHA = 'a785c5289244dcb41eb3ad6d23b8873a2e4dbbaca9f3b1d2b723a0823dc78ab5'
C3_LOCK_SHA = 'a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730'

def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def ref(path: str | Path) -> dict[str, str]:
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': sha(p)}

def main() -> None:
    assert not LOCK_OUT.exists(), f'refusing to overwrite {LOCK_OUT}'
    c3_lock_path = C3 / 'C3_DEV72_INPUT_LOCK_v2.json'
    c3_lock = json.loads(c3_lock_path.read_text(encoding='utf-8'))
    contract_path = HERE / 'C4_RUN_CONTRACT_v1.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8-sig'))
    taskbook = ROOT / 'reports' / 'paper_continuation_20261023' / 'C4_COORDINATE_SCREEN_TASKBOOK_ZH.md'
    assert sha(taskbook) == TASKBOOK_SHA
    assert sha(c3_lock_path) == C3_LOCK_SHA
    assert contract['coordinate_factor_m'] == 0 and len(contract['scene_ids']) == 12
    assert contract['scene_ids'][4] == contract['first_scene_id'] == 'DL1018_VAL_T2_C00_W10'

    local = {
        'runtime_core': HERE / 'run_dl1018_closed_loop.m',
        'episode_wrapper': HERE / 'run_episode_dl1018.m',
        'prediction_helper': HERE / 'delayed_prediction_step_candidate.m',
    }
    old_local = {x['role']: x for x in c3_lock['source_files']['isolated_c3_sources']}
    assert sha(C3 / 'run_dl1018_closed_loop.m') == old_local['runtime_core']['sha256']
    assert sha(C3 / 'run_episode_dl1018.m') == old_local['episode_wrapper']['sha256']
    assert sha(C3 / 'delayed_prediction_step_candidate.m') == old_local['prediction_helper']['sha256']

    base = c3_lock['c3_source_lock']
    active: list[dict[str, str]] = []
    for item in base['frozen_runtime_files']:
        leaf = Path(item['path']).name.lower()
        if leaf == 'run_dl1018_closed_loop.m': role = 'runtime_core'
        elif leaf == 'run_episode_dl1018.m': role = 'episode_wrapper'
        else: role = ''
        p = local[role] if role else Path(item['path'])
        if not role:
            assert sha(p) == item['sha256'], f'upstream runtime source changed: {p}'
        active.append({'role': role or Path(item['path']).name, 'path': str(Path(p).resolve()), 'sha256': sha(p)})
    active.append({'role': 'prediction_helper', 'path': str(local['prediction_helper'].resolve()),
                   'sha256': sha(local['prediction_helper'])})
    for item in base['frozen_plant_files']:
        p = Path(item['path'])
        assert sha(p) == item['sha256'], f'upstream Plant source changed: {p}'
        active.append({'role': item['name'], 'path': str(p.resolve()), 'sha256': sha(p)})
    assert len(active) == 32 and sum(Path(x['path']).suffix.lower() == '.m' for x in active) == 31
    assert sum(Path(x['path']).suffix.lower() == '.mat' for x in active) == 1

    by_id = {x['scene_id']: x for x in c3_lock['scenes']}
    scenes = []
    for scene_id in contract['scene_ids']:
        row = by_id[scene_id]
        assert row['candidate_action'] == 'REUSE_C3_SCREEN' and row.get('C3_reuse')
        scenes.append({'scene_id': scene_id, 'B_source': row['B_source'],
                       'b_scene_to_scored_log': row['b_scene_to_scored_log'],
                       'C3_reuse': row['C3_reuse']})

    refs = {
        'taskbook': ref(taskbook),
        'design_review': ref(ROOT / 'reports/paper_continuation_20261023/c4_coordinate_design_review/C4_COORDINATE_DESIGN_REVIEW_ZH.md'),
        'realization_review': ref(ROOT / 'reports/paper_continuation_20261023/realization_mechanism_review/REALIZATION_MECHANISM_REVIEW_ZH.md'),
        'c3_input_lock': ref(c3_lock_path),
        'c3_run_contract': ref(C3 / 'C3_DEV72_RUN_CONTRACT_v2.json'),
        'c3_prepare_result': ref(C3 / 'C3_DEV72_PREPARE_RESULT_v2.json'),
        'c3_prepared_snapshot': ref(C3 / 'C3_DEV72_PREPARED_CONFIG_OPTS_v2.mat'),
        'c3_core': ref(C3 / 'run_dl1018_closed_loop.m'),
        'c3_episode_wrapper': ref(C3 / 'run_episode_dl1018.m'),
        'prediction_helper': ref(C3 / 'delayed_prediction_step_candidate.m'),
    }
    upstream = c3_lock['c3_reference_refs']
    refs['c3_source_lock'] = {'path': upstream['c3_source_lock']['path'], 'sha256': upstream['c3_source_lock']['sha256']}
    refs['c3_authorization'] = {'path': c3_lock['authorization_and_scope_refs']['authorization']['path'],
                               'sha256': c3_lock['authorization_and_scope_refs']['authorization']['sha256']}
    refs['shared_job_release'] = {'path': base['c1_release']['path'], 'sha256': base['c1_release']['sha256']}

    source_files = {
        'lock_builder': ref(__file__),
        'prepare_entry': ref(HERE / 'prepare_c4_coordinate_v1.m'),
        'single_scene_runner': ref(HERE / 'run_c4_coordinate_v1.m'),
        'contract': ref(contract_path),
        'synthetic_check': ref(HERE / 'c4_coordinate_synthetic_check.py'),
        'isolated_sources': [x for x in active if x['role'] in {'runtime_core', 'episode_wrapper', 'prediction_helper'}],
    }
    payload = {
        'schema': 'C4_COORDINATE_INPUT_LOCK_V1',
        'state': 'LOCKED_C4_COORDINATE_NO_PLANT_PARENT_REVIEW_REQUIRED_V1',
        'plant_authorized_by_this_lock': False,
        'created_utc': '2026-10-23T00:00:00Z',
        'repo_root': str(ROOT),
        'taskbook_sha256': TASKBOOK_SHA,
        'c3_dev72_input_lock_sha256': C3_LOCK_SHA,
        'c3_source_lock_sha256': refs['c3_source_lock']['sha256'],
        'candidate_identity': contract['model'],
        'coordinate_factor_m': 0,
        'pcf_auxiliary_enabled': True,
        'source_files': source_files,
        'active_source_inventory': active,
        'source_counts': {'total': len(active), 'matlab': 31, 'mat': 1},
        'upstream_refs': refs,
        'shared_input_files': c3_lock['shared_input_files'],
        'scene_ids_reuse_12': contract['scene_ids'],
        'first_scene_id': contract['first_scene_id'],
        'scenes': scenes,
        'scope': contract,
        'notes': [
            'No Plant release is created by this lock.',
            'C3 results are reused through their frozen raw/status/run_start identities.',
            'Historical B runtime identity limitations remain as recorded in the C3 lock.',
        ],
    }
    LOCK_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'LOCK_BUILT_NO_PLANT', 'path': str(LOCK_OUT),
                      'sha256': sha(LOCK_OUT), 'active_sources': len(active),
                      'matlab_sources': 31, 'mat_sources': 1, 'scenes': len(scenes)}, indent=2))

if __name__ == '__main__':
    main()
