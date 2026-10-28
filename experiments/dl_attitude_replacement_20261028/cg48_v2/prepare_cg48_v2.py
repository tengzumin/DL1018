from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'experiments/dl_attitude_replacement_20261028/causal_n4_gate_train24_batch_v2'
SOURCE72 = ROOT / 'experiments/dl_attitude_replacement_20261026/mlp15_dev72_v1/MLP15_DEV72_PAYLOAD_MANIFEST_v1.json'
PARENT72 = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1'
REUSE6 = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_dev_v1'
C5_LOCK = ROOT / 'experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json'
INPUT = HERE / 'BATCH_INPUT_v2.json'
PLAN = HERE / 'BATCH_PLAN_v2.json'
LOCK = HERE / 'SOURCE_LOCK_v2.json'
RELEASE = HERE / 'RELEASE.json'
BINDINGS = HERE / 'bindings'
STUDY_ID = 'causal_n4_gate_train24_batch_v2'
INPUT_SCHEMA = 'DL1018_CAUSAL_N4_TRAIN24_BATCH_INPUT_V2'
PLAN_SCHEMA = 'DL1018_CAUSAL_N4_TRAIN24_BATCH_PLAN_V2'
BINDING_SCHEMA = 'DL1018_CAUSAL_N4_VAL48_SCENE_BINDING_V2'
LOCK_SCHEMA = 'DL1018_CAUSAL_N4_TRAIN24_SOURCE_LOCK_V2'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical_sha(obj) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_once(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text(encoding='utf-8') != data:
            raise RuntimeError(f'Refusing to overwrite changed output: {path}')
        return
    path.write_text(data, encoding='utf-8')


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def source_ref(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f'Missing source: {path}')
    return {'path': rel(path), 'sha256': sha(path)}


def add_source(sources: dict[str, dict], path_text: str, expected: str, label: str) -> None:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_file() or sha(path).lower() != expected.lower():
        raise RuntimeError(f'{label} missing or hash mismatch: {path}')
    sources[str(path).lower()] = {'path': str(path), 'sha256': expected.lower()}


def input_doc(ids: list[str]) -> dict:
    base_input = read_json(BASE / 'BATCH_INPUT_v2.json')
    refs = {
        'source_manifest_v1': source_ref(SOURCE72),
        'parent_full72_manifest_v2': source_ref(PARENT72 / 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'),
        'parent_reuse_manifest_v2': source_ref(REUSE6 / 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'),
        'c5_input_lock_v3': source_ref(C5_LOCK),
        'train24_batch_input': source_ref(BASE / 'BATCH_INPUT_v2.json'),
        'train24_batch_plan': source_ref(BASE / 'BATCH_PLAN_v2.json'),
        'train24_binding_template': source_ref(BASE / 'bindings/DL1018_DEV_T1_C05_W06.json'),
    }
    return {
        'schema': INPUT_SCHEMA,
        'study_id': STUDY_ID,
        'scope': 'Fixed v2 evaluation on the exact VAL48 cohort; no tuning, TEST, Plant, or inertia reconstruction.',
        'cohort': {
            'source_split': 'VAL48',
            'scene_count': 48,
            'source_scene_ids': ids,
            'val_used_for_tuning': False,
            'TEST_read': False,
            'Plant_calls': 0,
        },
        'cohort_sources': refs,
        'n4_gate_v2': copy.deepcopy(base_input['n4_gate_v2']),
        'policy': {
            'attempt_id': 'attempt_01', 'max_attempts_per_scene': 1,
            'Plant_calls': 0, 'authorized_Plant_calls': 0, 'potential_budget_calls': 0,
            'create_attempt_directories': False, 'create_marker_files': False,
            'scoring_path_pattern': 'scores/<scene_id>/SCORE_v2.json',
            'attempt_path_pattern': 'runs/<scene_id>/attempt_01',
        },
        'fixed_controller': copy.deepcopy(base_input['fixed_controller']),
    }


def records_by_id(path: Path, key: str = 'records') -> dict[str, dict]:
    doc = read_json(path)
    return {r['scene_id']: r for r in doc[key]}


def val_ids() -> list[str]:
    records = read_json(SOURCE72)['records']
    ids = [r['scene_id'] for r in records if r['source_split'] == 'VAL']
    if len(ids) != 48 or len(set(ids)) != 48 or any(not x.startswith('DL1018_VAL_') for x in ids):
        raise RuntimeError('Expected the exact 48 canonical VAL scene IDs.')
    return ids


def file_info(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f'Missing bound scene input: {path}')
    return {'path': str(path), 'sha256': sha(path)}


def scene_binding(scene_id: str, input_data: dict, source: dict, parent_full: dict,
                  parent_reuse: dict, c5: dict, template: dict,
                  candidate_sha: str, order: int) -> dict:
    parent_base = PARENT72 if (PARENT72 / 'runs' / scene_id / 'raw_run.mat').is_file() else REUSE6
    parent_run = parent_base / 'runs' / scene_id
    if parent_base == PARENT72 and not parent_full:
        raise RuntimeError(f'No parent full72 run for {scene_id}')
    c5_reuse = c5['C5_reuse']
    if c5_reuse.get('reused'):
        c5_raw = Path(c5_reuse['raw_path'])
        c5_status = Path(c5_reuse['run_status_path'])
        c5_start = Path(c5_reuse['run_start_path'])
    else:
        attempt = ROOT / 'experiments/position_axis_coordinate_c5_dev72_20261023/runs_dev72_v3' / scene_id / 'C5_AXIS_MASK_M110/attempt_01'
        c5_raw, c5_status, c5_start = attempt / 'raw_run.mat', attempt / 'run_status.json', attempt / 'run_start.mat'
    b = copy.deepcopy(template)
    b.update({
        'schema': BINDING_SCHEMA,
        'status': 'PASS_VAL48_FIXED_COHORT_BINDING',
        'scope': 'Exact VAL48 row for fixed v2 evaluation only; no tuning, TEST, Plant, or inertia reconstruction.',
        'selected_scene_id': scene_id,
        'source_order_zero_based': order,
        'source_split': 'VAL48',
        'parent_raw_path': str((parent_run / 'raw_run.mat').resolve()),
        'parent_raw_sha256': sha(parent_run / 'raw_run.mat'),
        'parent_status_path': str((parent_run / 'run_status.json').resolve()),
        'parent_status_sha256': sha(parent_run / 'run_status.json'),
        'parent_run_start_path': str((parent_run / 'run_start.json').resolve()),
        'parent_run_start_sha256': sha(parent_run / 'run_start.json'),
        'c5_raw_path': str(c5_raw.resolve()), 'c5_raw_sha256': sha(c5_raw),
        'c5_status_path': str(c5_status.resolve()), 'c5_status_sha256': sha(c5_status),
        'c5_run_start_path': str(c5_start.resolve()), 'c5_run_start_sha256': sha(c5_start),
        'b72_scoring_raw_path': c5['B72_scoring']['raw_path'],
        'b72_scoring_raw_sha256': c5['B72_scoring']['raw_sha256'],
        'b72_scoring_status_path': c5['B72_scoring']['run_status_path'],
        'b72_scoring_status_sha256': c5['B72_scoring']['run_status_sha256'],
        'scene_payload_source_path': source['payload_path'],
        'scene_payload_source_sha256': source['payload_sha256'],
        'external_identity_sha256': source['external_identity_sha256'],
        'local_scene_payload_path': source['payload_path'],
        'local_scene_payload_sha256': source['payload_sha256'],
        'VAL_data_read': True,
        'TEST_read': False,
        'Plant_calls': 0,
        'inertia_reconstruction_enabled': False,
        'source_batch_binding_sha256': canonical_sha({
            'scene_id': scene_id, 'source_order_zero_based': order,
            'external_identity_sha256': source['external_identity_sha256'],
            'source_manifest_sha256': input_data['cohort_sources']['source_manifest_v1']['sha256'],
        }),
        'candidate_identity_sha256': candidate_sha,
    })
    b.pop('fold_id', None)
    attempt_dir = HERE / 'runs' / scene_id / 'attempt_01'
    b['candidate_attempt'] = {
        'attempt_id': 'attempt_01', 'attempt_dir': str(attempt_dir.resolve()),
        'raw_path': str((attempt_dir / 'raw_run.mat').resolve()),
        'status_path': str((attempt_dir / 'run_status.json').resolve()),
        'run_start_path': str((attempt_dir / 'run_start.json').resolve()),
        'attempt_started_marker_path': str((attempt_dir / 'attempt_started.marker').resolve()),
        'first_plant_step_marker_path': str((attempt_dir / 'first_plant_step.marker').resolve()),
        'score_path': str((HERE / 'scores' / scene_id / 'SCORE_v2.json').resolve()),
        'directory_created': False,
    }
    return b


def binding_inputs() -> tuple[dict, dict[str, dict], dict[str, dict], dict[str, dict], dict, dict, dict, str]:
    ids = val_ids()
    cfg = input_doc(ids)
    for ref in cfg['cohort_sources'].values():
        p = ROOT / ref['path']
        if sha(p).lower() != ref['sha256'].lower():
            raise RuntimeError(f'Pinned cohort source changed: {p}')
    source = records_by_id(SOURCE72)
    parent_full = records_by_id(PARENT72 / 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json')
    parent_reuse = records_by_id(REUSE6 / 'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json')
    c5_doc = read_json(C5_LOCK)
    c5 = {r['scene_id']: r for r in c5_doc['scenes']}
    train_plan = read_json(BASE / 'BATCH_PLAN_v2.json')
    template = read_json(BASE / 'bindings/DL1018_DEV_T1_C05_W06.json')
    candidate_sha = train_plan['candidate_identity_sha256']
    if len(source) != 72 or len(parent_full) != 72 or len(parent_reuse) != 72 or len(c5) != 72:
        raise RuntimeError('Pinned 72-scene source inventories changed.')
    for sid in ids:
        for records in (parent_full, parent_reuse):
            a, b = source[sid], records[sid]
            for key in ('external_identity_sha256', 'b_raw_sha256', 'b_status_sha256', 'payload_sha256'):
                if a[key].lower() != b[key].lower():
                    raise RuntimeError(f'72-source identity mismatch {sid}: {key}')
        if source[sid]['external_identity_sha256'].lower() != c5[sid]['external_identity_sha256'].lower():
            raise RuntimeError(f'C5 external identity mismatch: {sid}')
    write_once(INPUT, cfg)
    return cfg, source, parent_full, parent_reuse, c5, train_plan, template, candidate_sha


def generate_bindings(selected: list[str] | None = None) -> list[Path]:
    cfg, source, parent_full, parent_reuse, c5, train_plan, template, candidate_sha = binding_inputs()
    ids = cfg['cohort']['source_scene_ids']
    selected = selected or ids
    if any(sid not in ids for sid in selected):
        raise RuntimeError('Requested scene is outside the locked VAL48 cohort.')
    paths = []
    for sid in selected:
        doc = scene_binding(sid, cfg, source[sid], parent_full.get(sid), parent_reuse.get(sid),
                            c5[sid], template, candidate_sha, ids.index(sid))
        path = BINDINGS / f'{sid}.json'
        write_once(path, doc)
        paths.append(path)
    return paths


def main() -> None:
    if sys.argv[1:] == ['--bindings']:
        paths = generate_bindings()
    elif len(sys.argv) == 3 and sys.argv[1] == '--scene':
        paths = generate_bindings([sys.argv[2]])
    else:
        raise SystemExit('usage: prepare_cg48_v2.py --scene DL1018_VAL_... | --bindings')
    print(json.dumps({'status': 'PASS_VAL48_BINDING_GENERATION', 'bindings_written': len(paths),
                      'first_binding': str(paths[0].resolve()), 'last_binding': str(paths[-1].resolve()),
                      'Plant_calls': 0, 'TEST_read': False, 'val_used_for_tuning': False},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
