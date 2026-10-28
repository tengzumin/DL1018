from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
INPUT_PATH = HERE / 'BATCH_INPUT_v2.json'
PLAN_PATH = HERE / 'BATCH_PLAN_v2.json'
LOCK_PATH = HERE / 'SOURCE_LOCK_TRAIN24_v2.json'
RELEASE_PATH = HERE / 'RELEASE.json'
PREPARED_PATH = HERE / 'DRY_RUN_PREPARED_v2.json'
AUDIT_PATH = HERE / 'DRY_RUN_AUDIT_EXEC_ID_v2.json'
REUSE_IDENTITIES_PATH = HERE / 'REUSE_IDENTITIES_v2.json'
INITIAL_LOCK_PATH = HERE / 'SOURCE_LOCK_TRAIN24_PRE_EXEC_IDENTITY_v2.json'
BINDINGS_DIR = HERE / 'bindings'
STUDY_ID = 'causal_n4_gate_train24_batch_v2'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical_sha(obj) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json_once(path: Path, obj) -> None:
    if path.exists():
        raise RuntimeError(f'Refusing to overwrite {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def resolve(path_text: str) -> Path:
    p = Path(path_text)
    return p if p.is_absolute() else WORKSPACE / p


def check_ref(ref: dict, label: str) -> Path:
    p = resolve(ref['path'])
    if not p.is_file() or sha(p).lower() != ref['sha256'].lower():
        raise RuntimeError(f'{label} missing or hash mismatch: {p}')
    return p


def result_file_ref(scene: dict, name: str) -> dict:
    return scene['files'][name]


def add_source(sources: dict[str, dict], path_text: str, expected_sha: str, label: str) -> None:
    p = resolve(path_text)
    if not p.is_file():
        raise RuntimeError(f'{label} missing: {p}')
    actual = sha(p)
    if actual.lower() != expected_sha.lower():
        raise RuntimeError(f'{label} hash mismatch: {p}')
    key = str(p.resolve()).lower()
    previous = sources.get(key)
    if previous and previous['sha256'].lower() != actual.lower():
        raise RuntimeError(f'Conflicting locked hashes for {p}')
    sources[key] = {'path': str(p.resolve()), 'sha256': actual}


def source_map(lock_doc: dict) -> dict[str, str]:
    return {str(Path(x['path']).resolve()).lower(): x['sha256'].lower() for x in lock_doc['files']}


def runtime_refs(n4_root: Path, n4_lock: dict, one_lock: dict | None = None) -> list[dict]:
    refs = []
    # One shared copy of the frozen runtime tree serves every scene binding.
    shared_tree = HERE / 'candidate_runner_work'
    if not shared_tree.is_dir():
        raise RuntimeError(f'Missing shared batch runtime: {shared_tree}')
    for p in shared_tree.rglob('*'):
        if p.is_file():
            refs.append({'path': str(p.resolve()), 'sha256': sha(p)})
    for item in n4_lock['files']:
        name = Path(item['path']).name.lower()
        if name in {'run_causal_n4_single_call.m', 'score_call_v2.py', 'setup_calls_v2.py',
                    'run_helper_parity_v2.m', 'summarize_v2.py', 'helper_parity_v2.py'}:
            refs.append({'path': item['path'], 'sha256': item['sha256']})
    # Completed calls lock the frozen full72 scorer and score constants separately.
    if one_lock is not None:
        for item in one_lock['files']:
            name = Path(item['path']).name.lower()
            low = item['path'].lower().replace('/', '\\')
            if name == 'score_full72_candidate_v1.py' or '\\mlp15_composite_dev_v3\\release.json' in low:
                refs.append({'path': item['path'], 'sha256': item['sha256']})
    unique = {}
    for item in refs:
        k = str(resolve(item['path']).resolve()).lower()
        old = unique.get(k)
        if old and old['sha256'].lower() != item['sha256'].lower():
            raise RuntimeError(f'Runtime lock conflict: {item["path"]}')
        unique[k] = item
    return sorted(unique.values(), key=lambda x: x['path'].lower())


def algorithm_equivalence(runtime: list[dict], n4_root: Path) -> tuple[str, dict]:
    new_root = HERE / 'candidate_runner_work'
    old_root = n4_root / 'candidate_runner_work'
    new_runner = new_root / 'matlab/runtime/run_mlp15_dev72_closed_loop.m'
    old_runner = old_root / 'matlab/runtime/run_mlp15_dev72_closed_loop.m'
    new_text = new_runner.read_text(encoding='utf-8')
    normalized = new_text
    normalized = normalized.replace(
        "{'DL1018_CAUSAL_N4_GATE_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2', ...\n        'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_TRAIN24_SINGLE_CALL_V2'}",
        "{'DL1018_CAUSAL_N4_GATE_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2'}")
    normalized = normalized.replace("strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2')",
                                    "strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_NOPLANT_V2')")
    normalized = normalized.replace("strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_TRAIN24_SINGLE_CALL_V2')",
                                    "strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2')")
    normalized = normalized.replace('causal_n4_gate_train24_batch_v2', 'causal_n4_gate_v2')
    if normalized != old_runner.read_text(encoding='utf-8'):
        raise RuntimeError('The copied core runner differs beyond release identity/membership guards.')
    runner_original_sha = sha(old_runner)
    entries = {}
    for item in runtime:
        p = resolve(item['path'])
        try:
            rel = p.relative_to(new_root)
        except ValueError:
            rel = None
        if rel is not None:
            if rel.as_posix() == 'matlab/runtime/prepare_causal_n4_train24_scene_no_plant.m':
                continue  # Study/binding adapter; prepared identity is compared with prior raw logs.
            key = 'runtime/' + rel.as_posix()
            entries[key] = runner_original_sha if p == new_runner else item['sha256'].lower()
        else:
            entries['external/' + str(p.resolve()).lower()] = item['sha256'].lower()
    return canonical_sha(entries), {'runner_exact_sha256':sha(new_runner),
        'runner_original_sha256':runner_original_sha,'runner_identity_gate_normalized_sha256':sha(old_runner),
        'runner_normalization_equal_to_original':True,'runtime_file_count':len(entries)}


def validate_inputs():
    cfg = read_json(INPUT_PATH)
    if cfg['study_id'] != STUDY_ID or cfg['policy']['Plant_calls'] != 0 or cfg['policy']['authorized_Plant_calls'] != 0:
        raise RuntimeError('Unexpected study identity or nonzero Plant policy.')
    for label, ref in cfg['cohort_sources'].items():
        check_ref(ref, f'cohort source {label}')
    for label in ('release', 'protocol', 'source_lock', 'three_scene_result'):
        check_ref(cfg['n4_gate_v2'][label], f'N4 v2 {label}')

    batch = read_json(resolve(cfg['cohort_sources']['batch_bindings']['path']))
    batch_cfg = read_json(resolve(cfg['cohort_sources']['batch_input']['path']))
    manifest = read_json(resolve(cfg['cohort_sources']['dataset_manifest']['path']))
    physical = read_json(resolve(cfg['cohort_sources']['physical_manifest']['path']))
    n4_release = read_json(resolve(cfg['n4_gate_v2']['release']['path']))
    protocol = read_json(resolve(cfg['n4_gate_v2']['protocol']['path']))
    n4_lock = read_json(resolve(cfg['n4_gate_v2']['source_lock']['path']))
    summary = read_json(resolve(cfg['n4_gate_v2']['three_scene_result']['path']))

    if batch['schema'] != 'NO_POSITION_GRU_NOTCH_TRAIN24_BATCH_BINDINGS_V1' or batch['status'] != 'PREPARED_NO_PLANT_INPUTS_LOCKED':
        raise RuntimeError('The source batch is not the pinned source-only TRAIN_C5_24 binding pack.')
    if batch['input_config_sha256'].lower() != cfg['cohort_sources']['batch_input']['sha256'].lower():
        raise RuntimeError('Pinned source batch config hash differs.')
    if batch['preparer_script_sha256'].lower() != cfg['cohort_sources']['batch_preparer']['sha256'].lower():
        raise RuntimeError('Pinned source batch preparer hash differs.')
    ids = manifest['source_scene_ids']
    batch_ids = batch['cohort']['scene_ids']
    physical_ids = [r['scene_id'] for r in physical['records']]
    if len(ids) != 24 or len(set(ids)) != 24 or ids != batch_ids or ids != physical_ids:
        raise RuntimeError('The three pinned TRAIN_C5_24 scene lists do not match exactly.')
    if any(not x.startswith('DL1018_DEV_') or 'TEST' in x or 'VAL' in x for x in ids):
        raise RuntimeError('Noncanonical DEV-prefix TRAIN membership detected.')
    if manifest.get('scene_count') != 24 or manifest.get('scope', {}).get('TEST_read') is not False or manifest.get('scope', {}).get('VAL_raw_read') is not False:
        raise RuntimeError('The physical TRAIN24 manifest scope flags changed.')
    if physical.get('TEST_read') is not False or physical.get('Plant_called') is not False:
        raise RuntimeError('The physical TRAIN24 source manifest has unexpected scope flags.')
    records = {r['scene_id']: r for r in physical['records']}
    bindings = batch['bindings']
    if len(bindings) != 24 or [b['scene_id'] for b in bindings] != ids:
        raise RuntimeError('The pinned 24 scene binding order changed.')
    for b in bindings:
        rec = records[b['scene_id']]
        if b['scene_identity_sha256'].lower() != rec['scene_identity_sha256'].lower():
            raise RuntimeError(f'Physical scene identity mismatch: {b["scene_id"]}')

    if n4_release['schema'] != 'DL1018_CAUSAL_N4_GATE_NOPLANT_V2' or n4_release['status'] != 'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT':
        raise RuntimeError('N4 v2 release is not the frozen no-Plant release.')
    if n4_release['authorized_Plant_calls'] != 0 or n4_release['Plant_calls'] != 0 or n4_release['potential_budget_calls'] != 0:
        raise RuntimeError('N4 v2 source release unexpectedly carries Plant budget.')
    if n4_release['TEST_read'] or n4_release['VAL_data_read'] or n4_release['inertia_reconstruction_enabled'] or n4_release['extra_position_residual_gru_enabled']:
        raise RuntimeError('N4 v2 release scope or controller flags changed.')
    if protocol['study_id'] != 'causal_n4_gate_v2' or protocol['source_split'] != 'TRAIN_C5_24':
        raise RuntimeError('N4 protocol source/split changed.')
    if summary['status'] != 'PASS_FIXED_THREE_SCENE_CAUSAL_GATE_DIAGNOSTIC' or summary['Plant_calls'] != 3:
        raise RuntimeError('The pinned completed three-scene N4 result is not PASS.')
    if summary['TEST_read'] or summary['VAL_read'] or summary['inertia_reconstruction_enabled']:
        raise RuntimeError('The three-scene result has an unexpected scope flag.')
    if [s['scene_id'] for s in summary['scenes']] != protocol['call_order']:
        raise RuntimeError('The three-scene result and fixed N4 protocol order differ.')
    if any(not all(s['criteria'].values()) for s in summary['scenes']):
        raise RuntimeError('A completed N4 scene has a failed score criterion.')

    return cfg, batch, manifest, physical, n4_release, protocol, n4_lock, summary


def build_binding(base: dict, shared: dict, scene: dict, candidate_sha: str, policy: dict) -> dict:
    d = copy.deepcopy(base)
    scene_id = scene['scene_id']
    comps = scene['same_scene_comparators']
    models = shared['models']
    d.update({
        'schema': 'DL1018_CAUSAL_N4_TRAIN24_SCENE_BINDING_V2',
        'scope': 'Exact physical TRAIN_C5_24 row; no TEST/VAL raw, no Plant, no inertia reconstruction.',
        'selected_scene_id': scene_id,
        'source_order_zero_based': scene['source_order_zero_based'],
        'source_split': 'TRAIN_C5_24 (canonical ID prefix DEV)',
        'fold_id': scene['diagnostic_fold_id'],
        'dataset_path': shared['dataset']['path'], 'dataset_sha256': shared['dataset']['sha256'],
        'dataset_manifest_path': shared['dataset_manifest']['path'], 'dataset_manifest_sha256': shared['dataset_manifest']['sha256'],
        'dataset_source_lock_path': shared['dataset_source_lock']['path'], 'dataset_source_lock_sha256': shared['dataset_source_lock']['sha256'],
        'parent_cosine_release_path': models['parent_release']['path'], 'parent_cosine_release_sha256': models['parent_release']['sha256'],
        'parent_cosine_manifest_path': models['parent_manifest']['path'], 'parent_cosine_manifest_sha256': models['parent_manifest']['sha256'],
        'parent_cosine_source_lock_path': models['parent_source_lock']['path'], 'parent_cosine_source_lock_sha256': models['parent_source_lock']['sha256'],
        'parent_cosine_model_path': models['parent_cosine_model']['path'], 'parent_cosine_model_sha256': models['parent_cosine_model']['sha256'],
        'parent_raw_path': comps['parent_cosine_gru']['raw_path'], 'parent_raw_sha256': comps['parent_cosine_gru']['raw_sha256'],
        'parent_status_path': comps['parent_cosine_gru']['status_path'], 'parent_status_sha256': comps['parent_cosine_gru']['status_sha256'],
        'parent_run_start_path': comps['parent_cosine_gru']['run_start_path'], 'parent_run_start_sha256': comps['parent_cosine_gru']['run_start_sha256'],
        'c5_input_lock_path': shared['c5_input_lock']['path'], 'c5_input_lock_sha256': shared['c5_input_lock']['sha256'],
        'c5_raw_path': comps['C5']['raw_path'], 'c5_raw_sha256': comps['C5']['raw_sha256'],
        'c5_status_path': comps['C5']['status_path'], 'c5_status_sha256': comps['C5']['status_sha256'],
        'c5_run_start_path': comps['C5']['run_start_path'], 'c5_run_start_sha256': comps['C5']['run_start_sha256'],
        'b72_scoring_raw_path': comps['B']['raw_path'], 'b72_scoring_raw_sha256': comps['B']['raw_sha256'],
        'b72_scoring_status_path': comps['B']['status_path'], 'b72_scoring_status_sha256': comps['B']['status_sha256'],
        'scene_payload_source_path': scene['scene_payload']['path'], 'scene_payload_source_sha256': scene['scene_payload']['sha256'],
        'c5_snapshot_path': models['c5_snapshot']['path'], 'c5_snapshot_sha256': models['c5_snapshot']['sha256'],
        'position_model_path': models['position_dssm14_model']['path'], 'position_model_sha256': models['position_dssm14_model']['sha256'],
        'c5_receipt_path': models['c5_receipt']['path'], 'c5_receipt_sha256': models['c5_receipt']['sha256'],
        'external_identity_sha256': scene['scene_identity_sha256'],
        'local_scene_payload_path': scene['scene_payload']['path'], 'local_scene_payload_sha256': scene['scene_payload']['sha256'],
        'Plant_calls': 0, 'TEST_read': False, 'VAL_data_read': False,
        'inertia_reconstruction_enabled': False, 'extra_position_residual_gru_enabled': False, 'fixed_J0': True,
        'study_id': STUDY_ID, 'source_batch_binding_sha256': scene['binding_sha256'],
        'candidate_identity_sha256': candidate_sha,
    })
    attempt_dir = HERE / 'runs' / scene_id / policy['attempt_id']
    score_path = HERE / 'scores' / scene_id / 'SCORE_v2.json'
    d['candidate_attempt'] = {
        'attempt_id': policy['attempt_id'],
        'attempt_dir': str(attempt_dir.resolve()),
        'raw_path': str((attempt_dir / 'raw_run.mat').resolve()),
        'status_path': str((attempt_dir / 'run_status.json').resolve()),
        'run_start_path': str((attempt_dir / 'run_start.json').resolve()),
        'attempt_started_marker_path': str((attempt_dir / 'attempt_started.marker').resolve()),
        'first_plant_step_marker_path': str((attempt_dir / 'first_plant_step.marker').resolve()),
        'score_path': str(score_path.resolve()),
        'directory_created': False,
    }
    return d


def binding_source_refs(binding: dict) -> list[tuple[str, str]]:
    keys = [
        ('dataset_path','dataset_sha256'), ('dataset_manifest_path','dataset_manifest_sha256'),
        ('dataset_source_lock_path','dataset_source_lock_sha256'),
        ('parent_cosine_release_path','parent_cosine_release_sha256'), ('parent_cosine_manifest_path','parent_cosine_manifest_sha256'),
        ('parent_cosine_source_lock_path','parent_cosine_source_lock_sha256'), ('parent_cosine_model_path','parent_cosine_model_sha256'),
        ('parent_raw_path','parent_raw_sha256'), ('parent_status_path','parent_status_sha256'), ('parent_run_start_path','parent_run_start_sha256'),
        ('c5_input_lock_path','c5_input_lock_sha256'), ('c5_raw_path','c5_raw_sha256'), ('c5_status_path','c5_status_sha256'),
        ('c5_run_start_path','c5_run_start_sha256'), ('b72_scoring_raw_path','b72_scoring_raw_sha256'),
        ('b72_scoring_status_path','b72_scoring_status_sha256'), ('scene_payload_source_path','scene_payload_source_sha256'),
        ('c5_snapshot_path','c5_snapshot_sha256'), ('position_model_path','position_model_sha256'),
        ('c5_receipt_path','c5_receipt_sha256'),
    ]
    return [(binding[a], binding[b]) for a,b in keys]


def source_files_for_plan(cfg, batch, n4_release, n4_protocol, n4_lock, summary, bindings, reuse_locks):
    sources: dict[str, dict] = {}
    for label, ref in cfg['cohort_sources'].items():
        add_source(sources, ref['path'], ref['sha256'], f'cohort {label}')
    for label in ('release','protocol','source_lock','three_scene_result'):
        ref = cfg['n4_gate_v2'][label]
        add_source(sources, ref['path'], ref['sha256'], f'N4 {label}')
    runtime = runtime_refs(resolve(cfg['n4_gate_v2']['root']), n4_lock)
    for ref in runtime:
        add_source(sources, ref['path'], ref['sha256'], 'N4 candidate runtime')
    for binding in bindings:
        for path, expected in binding_source_refs(binding):
            add_source(sources, path, expected, f'bound input {binding["selected_scene_id"]}')
        bpath = HERE / 'bindings' / f'{binding["selected_scene_id"]}.json'
        add_source(sources, str(bpath), sha(bpath), 'generated scene binding')
    # Keep every completed gate artifact used to justify possible raw/score reuse.
    for scene in summary['scenes']:
        for key, ref in scene['files'].items():
            add_source(sources, ref['path'], ref['sha256'], f'completed N4 artifact {scene["scene_id"]}:{key}')
        lock_doc = read_json(Path(scene['files']['single_source_lock']['path']))
        # Include the exact scorer and constants that the completed score locked.
        for ref in runtime_refs(resolve(cfg['n4_gate_v2']['root']), n4_lock, lock_doc):
            add_source(sources, ref['path'], ref['sha256'], 'completed N4 candidate/scorer source')
    add_source(sources, str(INPUT_PATH), sha(INPUT_PATH), 'batch input')
    add_source(sources, str(Path(__file__).resolve()), sha(Path(__file__).resolve()), 'batch preparer')
    helper = HERE / 'candidate_runner_work' / 'matlab' / 'runtime' / 'prepare_causal_n4_train24_scene_no_plant.m'
    harness = HERE / 'run_train24_prepare_dryrun_v2.m'
    add_source(sources, str(helper), sha(helper), 'forked dynamic preparer')
    add_source(sources, str(harness), sha(harness), 'MATLAB dry-run harness')
    return sorted(sources.values(), key=lambda x: x['path'].lower()), runtime


def prepare() -> None:
    if any(p.exists() for p in (PLAN_PATH, LOCK_PATH, RELEASE_PATH, PREPARED_PATH, AUDIT_PATH, BINDINGS_DIR)):
        raise RuntimeError('Batch outputs already exist; refusing to overwrite or reuse an old release.')
    cfg, batch, manifest, physical, n4_release, protocol, n4_lock, summary = validate_inputs()
    input_sha = sha(INPUT_PATH)
    template_path = resolve(cfg['n4_gate_v2']['root']) / 'bindings' / f'{protocol["call_order"][0]}.json'
    template = read_json(template_path)
    old_single_source_lock = read_json(Path(summary['scenes'][0]['files']['single_source_lock']['path']))
    runtime = runtime_refs(resolve(cfg['n4_gate_v2']['root']), n4_lock, old_single_source_lock)
    algorithm_sha, runner_evidence = algorithm_equivalence(runtime, resolve(cfg['n4_gate_v2']['root']))
    fixed_identity = {
        'controller': cfg['fixed_controller'],
        'n4_filter': n4_release['applied_acceleration_static_n4'],
        'protocol_sha256': cfg['n4_gate_v2']['protocol']['sha256'],
        'candidate_source_files': runtime,
        'algorithm_equivalence_sha256': algorithm_sha,
        'runner_identity_gate_diff': runner_evidence,
        'source_lock_sha256': cfg['n4_gate_v2']['source_lock']['sha256'],
        'scoring': protocol['scoring'],
        'scorer_source_sha256': next(x['sha256'] for x in runtime if Path(x['path']).name.lower() == 'score_full72_candidate_v1.py'),
    }
    candidate_sha = canonical_sha(fixed_identity)
    BINDINGS_DIR.mkdir(parents=True)
    built=[]
    for scene in batch['bindings']:
        doc=build_binding(template, batch['shared_identity'], scene, candidate_sha, cfg['policy'])
        path=BINDINGS_DIR/f'{scene["scene_id"]}.json'
        write_json_once(path, doc)
        built.append(doc)

    source_files, runtime = source_files_for_plan(cfg, batch, n4_release, protocol, n4_lock, summary, built, {})
    lock_doc={'schema':'DL1018_CAUSAL_N4_TRAIN24_SOURCE_LOCK_V2','study_id':STUDY_ID,'files':source_files}
    write_json_once(LOCK_PATH, lock_doc)
    release=copy.deepcopy(n4_release)
    release.update({
        'schema':'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2','study_id':STUDY_ID,
        'status':'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT','source_split':'TRAIN_C5_24',
        'authorized_scenes':manifest['source_scene_ids'],'authorized_Plant_calls':0,'Plant_calls':0,
        'potential_budget_calls':0,'source_lock_path':str(LOCK_PATH.resolve()),'source_lock_sha256':sha(LOCK_PATH),
        'source_batch_bindings_path':cfg['cohort_sources']['batch_bindings']['path'],
        'source_batch_bindings_sha256':cfg['cohort_sources']['batch_bindings']['sha256'],
        'call_protocol_path':cfg['n4_gate_v2']['protocol']['path'],
        'call_protocol_sha256':cfg['n4_gate_v2']['protocol']['sha256'],
        'candidate_identity_sha256':candidate_sha,'prepared_for_source_only_dynamic_scene_binding':True,
    })
    write_json_once(RELEASE_PATH, release)
    reuse_ids=set(protocol['call_order'])
    plan_entries=[]
    for binding in built:
        sid=binding['selected_scene_id']; reuse=(sid in reuse_ids)
        attempt=binding['candidate_attempt']
        plan_entries.append({
            'scene_id':sid,'source_order_zero_based':binding['source_order_zero_based'],
            'scene_identity_sha256':binding['external_identity_sha256'],
            'binding_path':str((BINDINGS_DIR/f'{sid}.json').resolve()),
            'binding_sha256':sha(BINDINGS_DIR/f'{sid}.json'),
            'candidate_identity_sha256':candidate_sha,
            'mode':'VERIFY_EXISTING_RAW_REUSE' if reuse else 'NEW_ATTEMPT_AFTER_ROOT_RELEASE',
            'existing_result_scene_id':sid if reuse else None,
            'attempt':attempt,
        })
    plan={
        'schema':'DL1018_CAUSAL_N4_TRAIN24_BATCH_PLAN_V2','status':'PREPARED_SOURCE_ONLY_PENDING_DYNAMIC_DRY_RUN_AND_ROOT_AUDIT',
        'study_id':STUDY_ID,'source_split':'TRAIN_C5_24','scene_count':24,'ordered_scene_ids':manifest['source_scene_ids'],
        'input_path':str(INPUT_PATH.resolve()),'input_sha256':input_sha,
        'source_lock_path':str(LOCK_PATH.resolve()),'source_lock_sha256':sha(LOCK_PATH),
        'release_path':str(RELEASE_PATH.resolve()),'release_sha256':sha(RELEASE_PATH),
        'frozen_n4_source':{'release_sha256':cfg['n4_gate_v2']['release']['sha256'],'protocol_sha256':cfg['n4_gate_v2']['protocol']['sha256'],'source_lock_sha256':cfg['n4_gate_v2']['source_lock']['sha256']},
        'candidate_identity_sha256':candidate_sha,'candidate_identity':fixed_identity,
        'controller':cfg['fixed_controller'],'fixed_n4_filter':release['applied_acceleration_static_n4'],
        'score_contract':protocol['scoring'],'replay_tolerance_max_abs':protocol['replay_tolerance_max_abs'],
        'attempt_policy':{'attempt_id':cfg['policy']['attempt_id'],'max_attempts_per_scene':1,'new_attempts_if_three_reuse':21,
            'Plant_calls':0,'authorized_Plant_calls':0,'potential_budget_calls':0,'attempt_directories_created':0,'marker_files_created':0,
            'future_budget_requires_new_root_release':True},
        'existing_three_reuse_check':{'status':'PENDING_IDENTITY_COMPARISON','scene_ids':protocol['call_order'],
            'rule':'Reuse raw and score only if scene inputs, exact prepared identity/options, controller/model, N4 filter, candidate runtime and scorer hashes all match.'},
        'entries':plan_entries,
    }
    write_json_once(PLAN_PATH, plan)
    print(json.dumps({'status':plan['status'],'scene_count':24,'candidate_source_files':len(runtime),
        'source_lock_files':len(source_files),'Plant_calls':0,'authorized_Plant_calls':0,
        'potential_budget_calls':0,'new_attempt_paths':21},ensure_ascii=False,indent=2))


def h5_value(node):
    import numpy as np
    import h5py
    if isinstance(node,h5py.Group):
        return {k:h5_value(v) for k,v in node.items()}
    value=node[()]
    arr=np.asarray(value)
    if arr.dtype.kind=='u' and arr.dtype.itemsize==2 and arr.size>1:
        vals=[int(x) for x in arr.reshape(-1)]
        if all(0 < x < 128 for x in vals):
            return ''.join(chr(x) for x in vals).rstrip('\x00\n\r ')
    if arr.shape==():
        return arr.item()
    return arr.tolist()


def read_gate_identity(raw_path: Path, group_name: str) -> dict:
    import h5py
    with h5py.File(raw_path,'r') as f:
        return h5_value(f['log'][group_name])


def compare_reuse(scene: dict, new_binding: dict, prepared: dict, cfg: dict, n4_lock: dict, summary_scene: dict) -> dict:
    sid=scene['scene_id'];refs=summary_scene['files']
    binding_old=read_json(Path(refs['binding']['path']))
    status=read_json(Path(refs['run_status']['path']))
    score=read_json(Path(refs['score']['path']))
    checks={}
    checks['same_scene_binding_inputs']=all(
        binding_old[k].lower()==new_binding[k].lower()
        for k in ('selected_scene_id','external_identity_sha256','parent_cosine_model_sha256','position_model_sha256',
                  'c5_snapshot_sha256','c5_receipt_sha256','local_scene_payload_sha256','parent_raw_sha256',
                  'parent_status_sha256','parent_run_start_sha256','c5_raw_sha256','c5_status_sha256',
                  'b72_scoring_raw_sha256','b72_scoring_status_sha256')
    )
    prior_release=read_json(Path(refs['single_release']['path']))
    current_release=read_json(resolve(cfg['n4_gate_v2']['release']['path']))
    checks['fixed_filter_and_protocol']=(
        prior_release['applied_acceleration_static_n4']==current_release['applied_acceleration_static_n4'] and
        prior_release['call_protocol_sha256'].lower()==cfg['n4_gate_v2']['protocol']['sha256'].lower()
    )
    old_lock=read_json(Path(refs['single_source_lock']['path']))
    old_map=source_map(old_lock)
    new_root=HERE/'candidate_runner_work';old_root=resolve(cfg['n4_gate_v2']['root'])/'candidate_runner_work'
    runtime=runtime_refs(resolve(cfg['n4_gate_v2']['root']),n4_lock,old_lock)
    source_diffs=[]
    for item in runtime:
        p=resolve(item['path'])
        try: rel=p.relative_to(new_root)
        except ValueError: rel=None
        if rel is not None:
            if rel.as_posix()=='matlab/runtime/prepare_causal_n4_train24_scene_no_plant.m':
                continue
            oldp=old_root/rel
            got=old_map.get(str(oldp.resolve()).lower())
            expected=sha(oldp) if oldp.is_file() else None
            if got!=expected:
                source_diffs.append(str(rel))
            elif rel.as_posix()=='matlab/runtime/run_mlp15_dev72_closed_loop.m':
                new_runner=p.read_text(encoding='utf-8')
                normalized=new_runner
                normalized=normalized.replace(
                    "{'DL1018_CAUSAL_N4_GATE_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2', ...\n        'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_TRAIN24_SINGLE_CALL_V2'}",
                    "{'DL1018_CAUSAL_N4_GATE_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2'}")
                normalized=normalized.replace("strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2')","strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_NOPLANT_V2')")
                normalized=normalized.replace("strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_TRAIN24_SINGLE_CALL_V2')","strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2')")
                normalized=normalized.replace('causal_n4_gate_train24_batch_v2','causal_n4_gate_v2')
                if normalized!=oldp.read_text(encoding='utf-8'):
                    source_diffs.append(str(rel)+' (normalized runner)')
        else:
            got=old_map.get(str(p.resolve()).lower())
            if got!=item['sha256'].lower():
                source_diffs.append(str(p))
    checks['candidate_runtime_algorithm_hashes']=not source_diffs
    execution_identity=prepared['execution_identity']
    mode=prepared['identity_mode_audit']
    checks['only_no_plant_control_flag_changed']=(mode.get('changed_option')=='no_plant_boundary_check' and
        mode.get('prepared_no_plant_value') is True and mode.get('execution_value') is False and
        mode.get('identity_common_equal') is True and mode.get('identity_geometry_except_options_equal') is True and
        mode.get('runner_invoked') is False)
    checks['prepared_execution_identity_matches_raw_lock']=execution_identity==read_gate_identity(Path(refs['raw_run']['path']),'gate_identity_lock')
    checks['prepared_execution_identity_matches_raw_recomputed']=execution_identity==read_gate_identity(Path(refs['raw_run']['path']),'gate_identity_recomputed')
    checks['completed_raw_and_score_pass']=(
        status.get('state')=='COMPLETED' and status.get('status_value')=='STABLE' and status.get('transitions')==20000 and
        status.get('state_samples')==20001 and status.get('Plant_calls')==1 and
        status.get('raw_sha256','').lower()==refs['raw_run']['sha256'].lower() and
        score.get('status')=='PASS_FIXED_CAUSAL_GATE_SCENE' and score.get('raw_sha256','').lower()==refs['raw_run']['sha256'].lower() and
        score.get('run_status_sha256','').lower()==refs['run_status']['sha256'].lower()
    )
    return {'scene_id':sid,'status':'REUSE_ELIGIBLE' if all(checks.values()) else 'REQUIRES_NEW_ATTEMPT',
        'checks':checks,'source_differences':source_diffs,'passed_checks':sum(bool(x) for x in checks.values()),'check_count':len(checks),
        'existing_raw':refs['raw_run'],'existing_score':refs['score']}


def finalize() -> None:
    if not PLAN_PATH.is_file() or not PREPARED_PATH.is_file() or not REUSE_IDENTITIES_PATH.is_file():
        raise RuntimeError('The 24-scene dynamic dry-run and 3-scene execution-identity dry-run are required.')
    cfg, batch, manifest, physical, n4_release, protocol, n4_lock, summary = validate_inputs()
    plan=read_json(PLAN_PATH);prepared_audit=read_json(PREPARED_PATH);reuse_audit=read_json(REUSE_IDENTITIES_PATH)
    initial_plan=read_json(HERE/'BATCH_PLAN_PRE_EXEC_IDENTITY_v2.json')
    initial_by_id={x['scene_id']:x for x in initial_plan['entries']}
    if prepared_audit['status']!='PASS_TRAIN24_DYNAMIC_PREPARE_DRY_RUN' or prepared_audit['Plant_calls']!=0:
        raise RuntimeError('The original 24-scene dynamic prepare dry-run did not pass zero-Plant checks.')
    if sha(INITIAL_LOCK_PATH).lower()!=prepared_audit['source_lock_sha256'].lower():
        raise RuntimeError('The preserved initial 24-scene source lock does not match its dry-run record.')
    if reuse_audit['status']!='PASS_THREE_SCENE_EXECUTION_IDENTITY_DRY_RUN' or reuse_audit['Plant_calls']!=0 or reuse_audit['runner_invoked']:
        raise RuntimeError('The three-scene execution-identity dry-run is invalid.')
    if reuse_audit['source_lock_sha256'].lower()!=plan['source_lock_sha256'].lower():
        raise RuntimeError('The execution-identity dry-run used a different current source lock.')
    ids=manifest['source_scene_ids']
    if prepared_audit['ordered_scene_ids']!=ids or [e['scene_id'] for e in prepared_audit['entries']]!=ids:
        raise RuntimeError('The preserved 24-scene prepare did not resolve the exact manifest order.')
    plan_by_id={x['scene_id']:x for x in plan['entries']}
    if len(plan_by_id)!=24 or set(plan_by_id)!=set(ids):
        raise RuntimeError('Plan membership is not exact TRAIN_C5_24.')
    reuse_by_id={x['scene_id']:x for x in reuse_audit['entries']}
    if list(reuse_by_id)!=protocol['call_order']:
        raise RuntimeError('Execution identities do not follow the original fixed 3-scene order.')
    summary_by_id={x['scene_id']:x for x in summary['scenes']}
    original_by_id={x['scene_id']:x for x in prepared_audit['entries']}
    reuse_results=[]
    for sid in ids:
        item=plan_by_id[sid]
        original=original_by_id[sid]
        if original['binding_sha256'].lower()!=initial_by_id[sid]['binding_sha256'].lower():
            raise RuntimeError(f'Preserved 24-scene dry-run binding differs from its initial plan: {sid}')
        current_binding=read_json(Path(item['binding_path']))
        prior_binding=copy.deepcopy(current_binding)
        prior_binding['candidate_identity_sha256']=initial_plan['candidate_identity_sha256']
        prior_bytes=(json.dumps(prior_binding,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
        if hashlib.sha256(prior_bytes).hexdigest().lower()!=original['binding_sha256'].lower():
            raise RuntimeError(f'Binding changed beyond the candidate identity hash: {sid}')
        if original['scene_audit']['external_identity_sha256'].lower()!=item['scene_identity_sha256'].lower():
            raise RuntimeError(f'Dynamic scene identity mismatch: {sid}')
        if sid in protocol['call_order']:
            execution=reuse_by_id[sid]
            if execution['binding_sha256'].lower()!=item['binding_sha256'].lower():
                raise RuntimeError(f'Execution identity resolved a different binding: {sid}')
            prepared_for_reuse={**original,'execution_identity':execution['execution_identity'],
                'identity_mode_audit':execution['identity_mode_audit']}
            binding=read_json(Path(item['binding_path']))
            check=compare_reuse({'scene_id':sid},binding,prepared_for_reuse,cfg,n4_lock,summary_by_id[sid])
            reuse_results.append(check);item['reuse_check']=check
            item['mode']='REUSE_EXISTING_RAW_AND_SCORE' if check['status']=='REUSE_ELIGIBLE' else 'NEW_ATTEMPT_REQUIRED_HASH_MISMATCH'
        else:
            item['mode']='NEW_ATTEMPT_AFTER_ROOT_RELEASE'
    can_reuse=all(x['status']=='REUSE_ELIGIBLE' for x in reuse_results)
    plan['status']='PASS_SOURCE_ONLY_TRAIN24_DYNAMIC_PREPARE_PENDING_ROOT_AUDIT'
    plan['initial_24_scene_dry_run']={'path':str(PREPARED_PATH.resolve()),'sha256':sha(PREPARED_PATH),
        'source_lock_path':str(INITIAL_LOCK_PATH.resolve()),'source_lock_sha256':prepared_audit['source_lock_sha256'],
        'scenes_prepared':24,'source_hashes_checked':prepared_audit['source_hashes_checked']}
    plan['execution_identity_dry_run']={'path':str(REUSE_IDENTITIES_PATH.resolve()),'sha256':sha(REUSE_IDENTITIES_PATH),
        'source_lock_sha256':reuse_audit['source_lock_sha256'],'scenes_prepared':3,
        'runner_invoked':False,'Plant_calls':0}
    plan['dry_run_scope']={'scene_count':24,'source_hashes_checked':len(read_json(LOCK_PATH)['files']),
        'full_lock_hashes_checked_initially':prepared_audit['source_hashes_checked'],
        'updated_helper_and_harness_hashes_checked':2,'Plant_calls':0,'authorized_Plant_calls':0,
        'potential_budget_calls':0,'attempt_directories_created':0,'attempt_markers_created':0,
        'first_plant_markers_created':0,'TEST_read':False,'VAL_read':False,
        'inertia_reconstruction_enabled':False,'extra_position_residual_gru_enabled':False}
    plan['existing_three_reuse_check']={'status':'ALL_THREE_EXACT' if can_reuse else 'REUSE_BLOCKED',
        'scene_ids':protocol['call_order'],'results':reuse_results,
        'remaining_new_attempts_if_all_reuse':21 if can_reuse else None}
    plan['attempt_policy']['new_attempts_if_three_reuse']=21 if can_reuse else None
    plan['attempt_policy']['future_budget_requires_new_root_release']=True
    audit={'schema':'DL1018_CAUSAL_N4_TRAIN24_ZERO_PLANT_DRY_RUN_AUDIT_V2',
        'status':'PASS_ZERO_PLANT_SOURCE_AND_DYNAMIC_PREPARE' if can_reuse else 'PASS_PREPARE_REUSE_BLOCKED',
        'study_id':STUDY_ID,'scene_count':24,'Plant_calls':0,'authorized_Plant_calls':0,
        'potential_budget_calls':0,'source_lock_sha256':plan['source_lock_sha256'],
        'source_hashes_checked':len(read_json(LOCK_PATH)['files']),
        'three_scene_reuse':plan['existing_three_reuse_check'],
        'new_attempts_planned':21 if can_reuse else 24,'runs_or_marker_dirs_created':False,
        'TEST_read':False,'VAL_read':False,'inertia_reconstruction_enabled':False,
        'extra_position_residual_gru_enabled':False}
    write_json_once(AUDIT_PATH,audit)
    PLAN_PATH.write_text(json.dumps(plan,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':audit['status'],'scenes_prepared':24,
        'reuse_eligible':sum(x['status']=='REUSE_ELIGIBLE' for x in reuse_results),
        'new_attempts_planned':audit['new_attempts_planned'],'Plant_calls':0,
        'authorized_Plant_calls':0,'potential_budget_calls':0,'audit_path':str(AUDIT_PATH)},ensure_ascii=False,indent=2))


if __name__=='__main__':
    if sys.argv[1:]==['--prepare']:
        prepare()
    elif sys.argv[1:]==['--finalize']:
        finalize()
    else:
        raise SystemExit('usage: prepare_n4_train24_batch_v2.py --prepare | --finalize')

