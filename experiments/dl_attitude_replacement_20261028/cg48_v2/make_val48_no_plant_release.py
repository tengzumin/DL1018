from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT = HERE / 'BATCH_INPUT_v2.json'
PLAN = HERE / 'BATCH_PLAN_v2.json'
PROTOCOL = HERE / 'BATCH_EXECUTION_PROTOCOL_v2.json'
BUDGET = HERE / 'BUDGET_LEDGER_v2.json'
CONTRACT = HERE / 'BATCH_SCORE_CONTRACT_v2.json'
LOCK = HERE / 'SOURCE_LOCK_VAL48_v1.json'
RELEASE = HERE / 'RELEASE.json'
NUMERIC_DIFF = HERE / 'VAL48_NUMERIC_SOURCE_HASH_PRESERVATION_v1.json'
TRAIN_ROOT = HERE.parent / 'causal_n4_gate_train24_batch_v2'
TRAIN_RELEASE = TRAIN_ROOT / 'RELEASE.json'
TRAIN_PLAN = TRAIN_ROOT / 'BATCH_PLAN_v2.json'
TRAIN_EXECUTION_PROTOCOL = TRAIN_ROOT / 'BATCH_EXECUTION_PROTOCOL_v2.json'
SCORE_SOURCE = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py'
SCORE_CONSTANTS = ROOT / 'experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json'
NUMERIC_RUNTIME_NAMES = (
    'position_compensation_n4_causal_gate_init.m',
    'position_compensation_n4_causal_gate_step.m',
    'position_compensation_static_n4_init.m',
    'position_compensation_static_n4_step.m',
    'position_applied_accel_notch_zoh.m',
)
BINDING_SOURCE_PAIRS = (
    ('dataset_path', 'dataset_sha256'), ('dataset_manifest_path', 'dataset_manifest_sha256'),
    ('dataset_source_lock_path', 'dataset_source_lock_sha256'),
    ('parent_cosine_release_path', 'parent_cosine_release_sha256'),
    ('parent_cosine_manifest_path', 'parent_cosine_manifest_sha256'),
    ('parent_cosine_source_lock_path', 'parent_cosine_source_lock_sha256'),
    ('parent_cosine_model_path', 'parent_cosine_model_sha256'),
    ('parent_raw_path', 'parent_raw_sha256'), ('parent_status_path', 'parent_status_sha256'),
    ('parent_run_start_path', 'parent_run_start_sha256'),
    ('c5_input_lock_path', 'c5_input_lock_sha256'), ('c5_raw_path', 'c5_raw_sha256'),
    ('c5_status_path', 'c5_status_sha256'), ('c5_run_start_path', 'c5_run_start_sha256'),
    ('b72_scoring_raw_path', 'b72_scoring_raw_sha256'),
    ('b72_scoring_status_path', 'b72_scoring_status_sha256'),
    ('scene_payload_source_path', 'scene_payload_source_sha256'),
    ('c5_snapshot_path', 'c5_snapshot_sha256'), ('position_model_path', 'position_model_sha256'),
    ('c5_receipt_path', 'c5_receipt_sha256'),
)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value) -> str:
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def numeric_normalize(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value).hex()
    if isinstance(value, list):
        return [numeric_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: numeric_normalize(item) for key, item in value.items()}
    return value


def json_text(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'


def write_replace(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json_text(value), encoding='utf-8')
    tmp.replace(path)


def write_or_check(path: Path, value: dict, write: bool) -> None:
    data = json_text(value)
    if write:
        write_replace(path, value)
    elif not path.is_file() or path.read_text(encoding='utf-8') != data:
        raise RuntimeError(f'VAL48 freeze changed since no-Plant release: {path}')


def pinned_source(root: Path, ref: dict) -> Path:
    path = (root / ref['path']).resolve()
    if not path.is_file() or sha(path).lower() != ref['sha256'].lower():
        raise RuntimeError(f'Pinned source missing or changed: {path}')
    return path


def add_file(files: dict[str, dict], path: Path, expected: str | None = None) -> None:
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f'Missing frozen source: {path}')
    actual = sha(path)
    if expected and actual.lower() != expected.lower():
        raise RuntimeError(f'Frozen source hash mismatch: {path}')
    key = str(path).lower()
    previous = files.get(key)
    if previous and previous['sha256'].lower() != actual.lower():
        raise RuntimeError(f'Conflicting frozen hash: {path}')
    files[key] = {'path': str(path), 'sha256': actual}


def code_paths() -> list[Path]:
    root_scripts = [p for p in (*HERE.glob('*.py'), *HERE.glob('*.m')) if p.is_file()]
    runtime = [p for p in (HERE / 'candidate_runner_work').rglob('*.m') if p.is_file()]
    return sorted(set(root_scripts + runtime), key=lambda p: p.as_posix().lower())


def input_sources(batch: dict, n4_release_path: Path) -> tuple[Path, dict, dict]:
    cohort = batch['cohort']
    ids = cohort['source_scene_ids']
    if (cohort['source_split'] != 'VAL48' or cohort['scene_count'] != 48 or len(ids) != 48
            or len(set(ids)) != 48 or any(not sid.startswith('DL1018_VAL_') for sid in ids)
            or cohort['val_used_for_tuning'] or cohort['TEST_read'] or cohort['Plant_calls'] != 0):
        raise RuntimeError('BATCH_INPUT_v2.json must lock the exact unused-for-tuning VAL48 cohort.')
    manifest_ref = batch['cohort_sources']['source_manifest_v1']
    manifest_path = pinned_source(ROOT, manifest_ref)
    n4_ref = batch['n4_gate_v2']['release']
    if n4_release_path != pinned_source(ROOT, n4_ref):
        raise RuntimeError('N4 release path does not match BATCH_INPUT_v2.json.')
    return manifest_path, manifest_ref, n4_ref


def build_documents(batch: dict, ids: list[str], numeric: dict, candidate_sha: str,
                    n4_ref: dict, n4_protocol_ref: dict, n4_protocol: dict,
                    python_protocol: dict, binding_inventory: list[dict], bindings: list[dict]) -> tuple[dict, dict, dict, dict]:
    python_path = Path(python_protocol['python_executable_path']).resolve()
    python_sha = python_protocol['python_executable_sha256'].lower()
    if not python_path.is_file() or sha(python_path).lower() != python_sha:
        raise RuntimeError(f'Frozen TCN0906 Python executable missing or changed: {python_path}')
    entries = [{'scene_id': sid, 'source_order_zero_based': i,
                'binding_path': str((HERE / 'bindings' / f'{sid}.json').resolve()),
                'binding_sha256': binding_inventory[i]['sha256'], 'mode': 'NEW_SINGLE_CALL'}
               for i, sid in enumerate(ids)]
    plan = {
        'schema': 'DL1018_CAUSAL_N4_VAL48_BATCH_PLAN_V2',
        'status': 'FROZEN_VAL48_48_NEW_SCENES_READY',
        'study_id': batch['study_id'], 'source_split': 'VAL48', 'scene_count': 48,
        'ordered_scene_ids': ids, 'input_path': str(INPUT.resolve()), 'input_sha256': sha(INPUT),
        'source_lock_path': str(LOCK.resolve()), 'candidate_identity_sha256': candidate_sha,
        'controller': copy.deepcopy(batch['fixed_controller']),
        'fixed_n4_filter': numeric,
        'attempt_policy': {'attempt_id': 'attempt_01', 'max_attempts_per_scene': 1,
                           'new_attempt_count': 48, 'Plant_calls_at_freeze': 0,
                           'authorized_Plant_calls': 48, 'potential_budget_calls': 48,
                           'retry_or_overwrite': False},
        'score_contract': 'Frozen full72 score_raw, same-scene B/C5/parent, diagnostic misses retained.',
        'entries': entries,
    }
    protocol = {
        'schema': 'DL1018_CAUSAL_N4_VAL48_BATCH_EXECUTION_PROTOCOL_V2',
        'status': 'FROZEN_BEFORE_VAL48_PLANT_CALLS',
        'study_id': batch['study_id'], 'source_split': 'VAL48',
        'ordered_scene_ids': ids, 'reuse_scene_ids': [], 'new_attempt_scene_ids': ids,
        'reuse_rule': 'No reuse; exactly one attempt per locked VAL48 scene.',
        'attempt_policy': {'attempt_id': 'attempt_01', 'max_attempts_per_scene': 1,
                           'overwrite_or_retry': False, 'remaining_Plant_call_cap': 48},
        'controller': copy.deepcopy(batch['fixed_controller']),
        'intervention': 'Byte-frozen N4 v2 causal gate and SOS coefficients from the pinned n4cg_v2 release.',
        'execution': 'Use copied TRAIN24 runner/core/scenes with the VAL48 adapter and fixed scene bindings.',
        'budget_rule': 'Record RESERVED before attempt marker and Plant; never retry a reserved scene.',
        'failure_rule': 'Continue on score-target misses; stop on safety, non-STABLE/incomplete, non-finite, or source-integrity failure.',
        'scope': {'TEST_read': False, 'VAL_data_read': True,
                  'inertia_reconstruction_enabled': False, 'parameter_tuning': False},
        'candidate_identity_sha256': candidate_sha,
        'fixed_n4_filter': numeric,
        'n4_call_protocol_sha256': n4_protocol_ref['sha256'],
        'n4_release_sha256': n4_ref['sha256'],
        'python_executable_path': str(python_path), 'python_executable_sha256': python_sha,
        'python_packages': python_protocol.get('python_packages', {}),
    }
    budget = {
        'schema': 'DL1018_CAUSAL_N4_VAL48_BUDGET_LEDGER_V2',
        'status': 'FROZEN_CAP_48', 'study_id': batch['study_id'], 'source_split': 'VAL48',
        'scene_count': 48, 'authorized_batch_call_cap': 48, 'scene_order': ids,
        'one_call_per_scene': True, 'max_attempts_per_scene': 1,
        'Plant_calls_at_freeze': 0, 'TEST_read': False, 'VAL_data_read': True,
        'inertia_reconstruction_enabled': False, 'candidate_identity_sha256': candidate_sha,
        'python_executable_path': str(python_path), 'python_executable_sha256': python_sha,
        'reservation_event': 'RESERVED is durable before attempt marker creation and Plant entry.',
        'no_retry_or_overwrite': True,
    }
    tasks = sorted({sid.split('_')[2] for sid in ids})
    winds = sorted({sid.rsplit('W', 1)[1] for sid in ids})
    contract = {
        'schema': 'DL1018_CAUSAL_N4_VAL48_BATCH_SCORE_CONTRACT_V2',
        'status': 'FROZEN_BEFORE_VAL48_PLANT_CALLS', 'source_split': 'VAL48',
        'scene_source': 'All 48 exact BATCH_INPUT_v2.json.cohort members, in listed order.',
        'scene_count': 48, 'scorer': 'score_full72_candidate_v1.score_raw with frozen gravity/max-tilt and same-scene B/C5/parent.',
        'scene_metrics': ['candidate/B/C5/parent Q_m', 'task_SO3_rad', 'inner_SO3_rad', 'same-scene paired ratios'],
        'groups': {'all_48': ids, 'task_groups': tasks, 'wind_groups': winds,
                   'HF_W09_W14': [sid for sid in ids if 9 <= int(sid.rsplit('W', 1)[1]) <= 14]},
        'targets': {'all48_ratio_of_summed_Q_candidate_over_C5_at_most': 1.05,
                    'retain_B_position_advantage': 'Report candidate/B Q and task ratios overall and by fixed groups.',
                    'HF_W09_W14_candidate_task_at_most_B': 'Report per-scene and aggregate flags.'},
        'aggregation': 'Report ratio of sums, paired mean/median, every scene, and all target misses.',
        'stop_rule': 'Metric misses do not stop. Stop only on safety, non-STABLE/incomplete, non-finite, or source-integrity failure.',
        'scope': {'TEST_read': False, 'VAL_data_read': True, 'inertia_reconstruction_enabled': False},
        'candidate_identity_sha256': candidate_sha,
        'n4_call_protocol_sha256': n4_protocol_ref['sha256'],
        'score_source_path': str(SCORE_SOURCE.resolve()), 'score_constants_path': str(SCORE_CONSTANTS.resolve()),
        'score_program_path': str((HERE / 'score_val48_batch_v2.py').resolve()),
        'python_executable_path': str(python_path), 'python_executable_sha256': python_sha,
    }
    return plan, protocol, budget, contract


def make_lock(batch: dict, manifest_path: Path, manifest_ref: dict, n4_ref: dict,
              n4_release_path: Path, train_release: dict, train_plan: dict,
              python_protocol: dict, binding_inventory: list[dict], plan: dict) -> dict:
    files: dict[str, dict] = {}
    for ref in batch['cohort_sources'].values():
        add_file(files, pinned_source(ROOT, ref), ref['sha256'])
    for key in ('release', 'protocol', 'source_lock', 'three_scene_result'):
        ref = batch['n4_gate_v2'][key]
        add_file(files, pinned_source(ROOT, ref), ref['sha256'])
    n4_lock_path = pinned_source(ROOT, batch['n4_gate_v2']['source_lock'])
    for item in read(n4_lock_path)['files']:
        add_file(files, Path(item['path']), item['sha256'])
    add_file(files, TRAIN_RELEASE)
    add_file(files, TRAIN_PLAN, batch['cohort_sources']['train24_batch_plan']['sha256'])
    add_file(files, TRAIN_EXECUTION_PROTOCOL)
    add_file(files, Path(python_protocol['python_executable_path']), python_protocol['python_executable_sha256'])
    add_file(files, SCORE_SOURCE)
    add_file(files, SCORE_CONSTANTS)
    for path in (PROTOCOL, BUDGET, CONTRACT):
        add_file(files, path)
    for path in code_paths():
        add_file(files, path)
    for item in binding_inventory:
        path = Path(item['path'])
        binding = read(path)
        add_file(files, path, item['sha256'])
        for path_key, hash_key in BINDING_SOURCE_PAIRS:
            add_file(files, Path(binding[path_key]), binding[hash_key])
    file_list = sorted(files.values(), key=lambda x: x['path'].lower())
    return {
        'schema': 'DL1018_CAUSAL_N4_VAL48_SOURCE_LOCK_V1',
        'study_id': batch['study_id'], 'source_split': 'VAL48',
        'cohort_scene_count': 48,
        'cohort_scene_ids_sha256': canonical_sha(batch['cohort']['source_scene_ids']),
        'batch_input': {'path': INPUT.name, 'sha256': sha(INPUT)},
        'source_manifest': {'path': manifest_ref['path'], 'sha256': sha(manifest_path)},
        'n4_gate_release': {'path': batch['n4_gate_v2']['release']['path'], 'sha256': sha(n4_release_path)},
        'training_numeric_source_only': {
            'path': str(TRAIN_RELEASE.relative_to(ROOT).as_posix()), 'sha256': sha(TRAIN_RELEASE)},
        'candidate_identity_sha256': plan['candidate_identity_sha256'],
        'binding_inventory': binding_inventory,
        'binding_inventory_sha256': canonical_sha(binding_inventory),
        'code_inventory': [{'path': str(p.resolve()), 'sha256': sha(p)} for p in code_paths()],
        'files': file_list,
        'file_count': len(file_list),
    }


def numeric_preservation(batch: dict, n4_release: dict, train_release: dict) -> dict:
    source_root = TRAIN_ROOT / 'candidate_runner_work' / 'matlab'
    target_root = HERE / 'candidate_runner_work' / 'matlab'
    numeric_files = []
    for name in NUMERIC_RUNTIME_NAMES:
        source = source_root / 'runtime' / name
        target = target_root / 'runtime' / name
        same = sha(source).lower() == sha(target).lower()
        numeric_files.append({'file': name, 'source_sha256': sha(source),
                              'target_sha256': sha(target), 'byte_identical': same})
        if not same:
            raise RuntimeError(f'Numeric runner helper changed in the cg48 copy: {name}')
    source_numeric = train_release['applied_acceleration_static_n4']
    target_numeric = n4_release['applied_acceleration_static_n4']
    source_hash = canonical_sha(numeric_normalize(source_numeric))
    target_hash = canonical_sha(numeric_normalize(target_numeric))
    if source_hash != target_hash or not all(x['byte_identical'] for x in numeric_files):
        raise RuntimeError('Fixed N4 numeric source hash preservation failed.')
    source_runner = TRAIN_ROOT / 'candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m'
    target_runner = HERE / 'candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m'
    return {
        'schema': 'DL1018_CAUSAL_N4_VAL48_NUMERIC_SOURCE_HASH_DIFF_V1',
        'source_split': 'VAL48', 'source_numeric_configuration_sha256': source_hash,
        'pinned_n4_numeric_configuration_sha256': target_hash,
        'n4_numeric_configuration_equal': True,
        'candidate_identity_sha256': train_release['candidate_identity_sha256'],
        'numeric_runtime_files': numeric_files,
        'runner_entry_source_sha256': sha(source_runner),
        'runner_entry_target_sha256': sha(target_runner),
        'runner_changes': 'Release schema/split gate and VAL48 scene validator dispatch only; gate/N4 step code remains byte-identical.',
        'gate_or_model_numeric_values_changed': False,
    }


def main() -> None:
    args = sys.argv[1:]
    mode, scene_id = 'no-plant', None
    if args == ['--single']:
        raise SystemExit('usage: make_val48_no_plant_release.py [--single <DL1018_VAL_...>]')
    if len(args) == 2 and args[0] == '--single':
        mode, scene_id = 'single', args[1]
    elif args not in ([], ['--no-plant']):
        raise SystemExit('usage: make_val48_no_plant_release.py [--no-plant] | --single <DL1018_VAL_...>')
    write = mode == 'no-plant'
    if write and ( (HERE / 'runs').exists() or (HERE / 'scores').exists() ):
        raise RuntimeError('Refusing to refreeze sources after any attempt or score exists.')

    batch = read(INPUT);ids = batch['cohort']['source_scene_ids']
    n4_ref = batch['n4_gate_v2']['release'];n4_release_path = pinned_source(ROOT, n4_ref)
    manifest_path, manifest_ref, _ = input_sources(batch, n4_release_path)
    n4_release = read(n4_release_path)
    n4_protocol_ref = batch['n4_gate_v2']['protocol']
    n4_protocol_path = pinned_source(ROOT, n4_protocol_ref);n4_protocol = read(n4_protocol_path)
    train_release = read(TRAIN_RELEASE)
    train_plan_path = pinned_source(ROOT, batch['cohort_sources']['train24_batch_plan'])
    train_plan = read(train_plan_path)
    if train_release['applied_acceleration_static_n4'] != n4_release['applied_acceleration_static_n4']:
        raise RuntimeError('Fixed N4 numeric configuration differs from the pinned shared release.')
    candidate_sha = train_release['candidate_identity_sha256']
    if not candidate_sha or candidate_sha != train_plan['candidate_identity_sha256']:
        raise RuntimeError('Fixed candidate identity differs from its source batch plan.')
    python_protocol = read(TRAIN_EXECUTION_PROTOCOL)

    binding_inventory=[];bindings=[]
    for order,sid in enumerate(ids):
        path=HERE/'bindings'/f'{sid}.json';binding=read(path)
        if (binding['schema']!='DL1018_CAUSAL_N4_VAL48_SCENE_BINDING_V2'
                or binding['status']!='PASS_VAL48_FIXED_COHORT_BINDING'
                or binding['selected_scene_id']!=sid or binding['source_order_zero_based']!=order
                or binding['source_split']!='VAL48' or not binding['VAL_data_read']
                or binding['TEST_read'] or binding['Plant_calls']!=0
                or binding['inertia_reconstruction_enabled'] or 'fold_id' in binding):
            raise RuntimeError(f'Binding is not a fold-free VAL48 row: {path}')
        binding_inventory.append({'scene_id':sid,'path':str(path.resolve()),'sha256':sha(path)})
        bindings.append(binding)

    plan,protocol,budget,contract=build_documents(batch,ids,n4_release['applied_acceleration_static_n4'],
        candidate_sha,n4_ref,n4_protocol_ref,n4_protocol,python_protocol,binding_inventory,bindings)
    write_or_check(PROTOCOL,protocol,write);write_or_check(BUDGET,budget,write);write_or_check(CONTRACT,contract,write)
    lock=make_lock(batch,manifest_path,manifest_ref,n4_ref,n4_release_path,train_release,train_plan,
                   python_protocol,binding_inventory,plan)
    write_or_check(LOCK,lock,write)
    lock_sha=sha(LOCK) if LOCK.is_file() else hashlib.sha256(json_text(lock).encode('utf-8')).hexdigest()
    plan['source_lock_sha256']=lock_sha;write_or_check(PLAN,plan,write)
    plan_sha=sha(PLAN) if PLAN.is_file() else hashlib.sha256(json_text(plan).encode('utf-8')).hexdigest()
    diff=numeric_preservation(batch,n4_release,train_release)
    write_or_check(NUMERIC_DIFF,diff,write)

    if mode=='single':
        if scene_id not in ids:
            raise RuntimeError('Single-call release scene is outside BATCH_INPUT_v2.json.cohort.')
        current=read(RELEASE)
        if (current['schema']!='DL1018_CAUSAL_N4_GATE_VAL48_NOPLANT_V2'
                or current['source_lock_sha256'].lower()!=lock_sha.lower()
                or current['batch_plan_sha256'].lower()!=plan_sha.lower()):
            raise RuntimeError('Single-call release requires the current frozen no-Plant release.')
        if (HERE/'runs'/scene_id).exists() or (HERE/'scores'/scene_id).exists():
            raise RuntimeError('Refusing to authorize an existing attempt or score.')
        release=copy.deepcopy(current)
        release.update({'schema':'DL1018_CAUSAL_N4_GATE_VAL48_SINGLE_CALL_V2','status':'RELEASED',
                        'fixed_scene_id':scene_id,'authorized_scenes':[scene_id],
                        'authorized_Plant_calls':1,'Plant_calls':1,'potential_budget_calls':1})
        write_replace(RELEASE,release)
        print(json.dumps({'status':'PASS_VAL48_SINGLE_CALL_RELEASE','scene_id':scene_id,
                          'authorized_scene_count':1,'source_split':'VAL48','Plant_calls':1,
                          'release':str(RELEASE.resolve())},indent=2))
        return

    release={
        'schema':'DL1018_CAUSAL_N4_GATE_VAL48_NOPLANT_V2',
        'status':'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT','study_id':batch['study_id'],
        'source_split':'VAL48','authorized_scenes':ids,
        'authorized_Plant_calls':0,'Plant_calls':0,'potential_budget_calls':0,
        'VAL_data_read':True,'TEST_read':False,'val_used_for_tuning':False,
        'parameter_tuning':False,'inertia_reconstruction_enabled':False,
        'source_lock_path':LOCK.name,'source_lock_sha256':lock_sha,
        'batch_input_sha256':sha(INPUT),'batch_plan_sha256':plan_sha,
        'source_manifest_path':manifest_ref['path'],'source_manifest_sha256':sha(manifest_path),
        'binding_inventory_sha256':lock['binding_inventory_sha256'],
        'candidate_identity_sha256':candidate_sha,
        'call_protocol_sha256':n4_protocol_ref['sha256'],
        'n4_release_sha256':n4_ref['sha256'],
        'numeric_source_sha256':diff['pinned_n4_numeric_configuration_sha256'],
        'applied_acceleration_static_n4':n4_release['applied_acceleration_static_n4'],
    }
    write_replace(RELEASE,release)
    print(json.dumps({'status':'PASS_VAL48_NO_PLANT_FREEZE','source_split':'VAL48',
                      'scene_count':48,'Plant_calls':0,'TEST_read':False,
                      'file_count':lock['file_count'],'source_lock_sha256':lock_sha,
                      'numeric_diff':str(NUMERIC_DIFF.resolve()),'release':str(RELEASE.resolve())},indent=2))


if __name__=='__main__':
    main()
