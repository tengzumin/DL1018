"""Read-only dataset classification; writes manifests only, never deletes datasets."""
import collections
import csv
import hashlib
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = ROOT.parent
INV = json.loads((OUT / 'INVENTORY_BEFORE.json').read_text(encoding='utf-8'))
assert not INV['errors'], INV['errors']
FILES = [f for p in INV['projects'].values() for f in p['files']]
LOOKUP = {os.path.normcase(f['path']): f for f in FILES}
CURRENT = ROOT / 'experiments/dl_attitude_replacement_20261027'
PREVIOUS = ROOT / 'experiments/dl_attitude_replacement_20261026'
POS_AUDIT = json.loads((OUT / 'POS_OFF_CACHE_AUDIT.json').read_text(encoding='utf-8'))
POS_CANDIDATES = {r['path'] for r in POS_AUDIT['candidates']}
CLOSED_SUB = {
 'experiments/dl_attitude_replacement_20261027/task_attitude_filter_wn12_hf_screen_v1': 'experiments/dl_attitude_replacement_20261027/task_attitude_filter_wn12_hf_screen_v1/ROOT_SCREEN12_DECISION_v1.md',
 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1': 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json',
 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1': 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json',
 'experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1': 'experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json',
 'experiments/dl_attitude_replacement_20261026/mlp15_causal_head_v1': 'experiments/dl_attitude_replacement_20261026/mlp15_causal_head_v1/ROOT_RESULT_v1.json',
 'experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3': 'experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/ROOT_SIX_SCENE_DECISION_v1.json',
 'experiments/dl_attitude_replacement_20261026/mlp15_one_event_delay_v1': 'experiments/dl_attitude_replacement_20261026/mlp15_one_event_delay_v1/ROOT_SIX_SCENE_DECISION_v1.json',
 'experiments/dl_attitude_replacement_20261026/mlp15_balanced_devscreen_v1': 'experiments/dl_attitude_replacement_20261026/attitude_head_mechanism_v1/ROOT_DECISION.json',
 'experiments/dl_attitude_replacement_20261026/pilot_runs_mlp15_v2': 'experiments/dl_attitude_replacement_20261026/MLP15_GHP7_PILOT_ROOT_REVIEW_v1.md',
 'experiments/dl_attitude_replacement_20261026/pilot_runs_gru15_c5_full72_v1': 'experiments/dl_attitude_replacement_20261026/gru15_c5_teacher_full72_v1/ROOT_REVIEW_GRU15_GHP7_SIX_SCENE_v1.md',
}


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)

def resolve(value, source):
    value = value.strip().replace('/', '\\')
    if not value or '\n' in value or '\r' in value or len(value) > 1000:
        return None
    p = Path(value)
    paths = [p] if p.is_absolute() else [Path(source).parent / p, ROOT / p, BASE / 'DL1009' / p, CURRENT / p, PREVIOUS / p]
    for path in paths:
        key = os.path.normcase(os.path.abspath(path))
        if key in LOOKUP:
            return key
    return None

# Follow the current experiment's explicit JSON/CSV input dependencies, including
# source manifests. Do not treat obsolete reports mentioning a file as a live call.
queue = [f['path'] for f in FILES if f['path'].startswith(str(CURRENT) + '\\')
         and not any(f['rel'].replace('\\', '/').startswith(k + '/') for k in CLOSED_SUB)
         and Path(f['path']).suffix.lower() in ('.json', '.csv') and f['size'] < 8_000_000]
visited, protected = set(), {}
while queue:
    source = queue.pop()
    if source in visited:
        continue
    visited.add(source)
    p = Path('\\\\?\\' + source)
    try:
        if p.suffix.lower() == '.json':
            values = strings(json.loads(p.read_text(encoding='utf-8-sig')))
        else:
            with p.open(encoding='utf-8-sig', newline='') as handle:
                values = [cell for row in csv.reader(handle) for cell in row]
        for value in values:
            key = resolve(value, source)
            if key is None:
                continue
            protected.setdefault(key, source)
            f = LOOKUP[key]
            input_metadata = any(token in Path(f['path']).name.upper() for token in
                                 ('MANIFEST', 'INPUT_LOCK', 'BINDING', 'RELEASE', 'SOURCE_FILES', 'INPUT_INDEX', 'CACHE_INDEX'))
            if input_metadata and Path(f['path']).suffix.lower() in ('.json', '.csv') and f['size'] < 8_000_000:
                queue.append(f['path'])
    except (OSError, ValueError, UnicodeError, csv.Error):
        # The active experiment itself is protected in full, even if a live
        # progress JSON is briefly being replaced by its owning process.
        continue

FAILED = {
    'attitude_cm18_a1_20261024': 'reports/attitude_cm18_a1_20261024/refresh_interval_v1/ROOT_ALL4_REVIEW_DECISION_v1_ZH.md',
    'attitude_cm18_a2_20261024': 'reports/attitude_cm18_a2_20261024/ROOT_A2_FINAL_VAL_DECISION_v1_ZH.md',
    'attitude_cm18_datarepair_20261024': 'reports/attitude_cm18_datarepair_20261024/a1t_screen12_control_v1/ROOT_A1T_SCREEN12_DECISION_v1_ZH.md',
    'attitude_cm18_c524_screen12_20261025': 'reports/attitude_cm18_c524_screen12_20261025/C524_ROOT_CAUSE_DECISION_v1_ZH.md',
    'attitude_cm18_c524_coverage33_20261025': 'reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_15SCENE_CLOSED_LOOP_RESULT_v1_ZH.md',
    'paper14_v2_round2_pcf_screen': 'reports/paper14_v2/FINAL_CLOSEOUT_20261022.md',
    'paper14_v2_round3_xy_pcf_screen': 'reports/paper14_v2/FINAL_CLOSEOUT_20261022.md',
    'position_prior_calibration_c1_20261022': 'reports/low_residual_parent_review_20261022/C1_CLOSEOUT_ZH.md',
    'position_prior_calibration_c1_20261022_v9': 'reports/low_residual_parent_review_20261022/C1_CLOSEOUT_ZH.md',
    'position_beta_clock_c2_20261023': 'reports/c2_deployable_residual_parent_20261023/C2_CLOSEOUT_ZH.md',
    'position_coordinate_c4_20261023': 'reports/paper_continuation_20261023/STATE.json',
    'position_delayed_prediction_c3_20261023': 'reports/paper_continuation_20261023/STATE.json',
    'position_delayed_prediction_c3_dev72_20261023': 'reports/paper_continuation_20261023/STATE.json',
    'c5_eight_loss_recovery_20261024': 'reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp/PARENT_C6_NO_EXPANSION_DECISION_v1.json',
}
DATA_EXT = {'.mat', '.h5', '.hdf5', '.npz', '.npy', '.csv'}
RAW_NAMES = {'raw_run.mat', 'run_raw.mat', 'raw.mat', 'run_comparison.mat'}
DATA_DIRS = {'data', 'dataset', 'datasets', 'derived', 'derived_events', 'sequences', 'fixed_model_sidecars'}
CONFIG_DIRS = {'models', 'configs', 'config', 'inputs', 'payloads', 'fixtures', 'sources', 'snapshots'}

def classify(f):
    p = Path(f['rel']); parts = p.parts; name = p.name.lower(); ext = p.suffix.lower()
    if '.git' in parts:
        return 'KEEP_GIT', 'Version history is outside dataset cleanup scope', ''
    if f['rel'].startswith('reports\\dataset_cleanup_'):
        return 'KEEP_AUDIT', 'Cleanup evidence and frozen manifests', ''
    if os.path.normcase(f['path']) in protected:
        return 'KEEP_CURRENT_INPUT', 'Explicit dependency of the current attitude replacement workflow', protected[os.path.normcase(f['path'])]
    if f['project'] == 'DL1018':
        rel = p.as_posix()
        for branch, evidence in CLOSED_SUB.items():
            if rel.startswith(branch + '/') and (name in RAW_NAMES or name.endswith('_raw_run.mat')):
                return 'DELETE_CLOSED_SCREEN', 'Explicitly rejected screen; no current input reference; retain models, start configuration, raw audit and scores', evidence
    if f['project'] == 'DL1018' and len(parts) > 1 and parts[1] in (CURRENT.name, PREVIOUS.name):
        return 'KEEP_ACTIVE', 'Active MLP15/TCN experiment, including failed pilot reused by current research', ''
    if any(x.lower() in CONFIG_DIRS for x in parts) or any(x in name for x in ('normaliz', 'parameters', 'weights', 'checkpoint', 'run_start', 'runstart', 'prepared', 'cfg_opts', 'scene_payload', 'fixture', 'source_lock')):
        return 'KEEP_MODEL_CONFIG', 'Retain source models, configuration, run-start inputs and fixtures', ''
    if ext == '.csv' and any(x in name for x in ('manifest', 'index', 'ledger', 'summary', 'metric', 'contract', 'audit', 'scene_spec')):
        return 'KEEP_METADATA', 'Retain dataset indexes, provenance, metrics and audit summaries', ''
    is_raw = name in RAW_NAMES or name.endswith('_raw_run.mat') or name.endswith('_validation.mat')
    is_derived = ext in {'.h5', '.hdf5', '.npz', '.npy'} and any(x.lower() in DATA_DIRS for x in parts)
    if f['project'] == 'DL1009':
        if parts[:2] == ('RBF-BS0', 'experiments'):
            old_data = ext in DATA_EXT and any(x.lower() in DATA_DIRS for x in parts)
            decomposition = ext == '.csv' and name.startswith('event_output_decomposition')
            if is_raw or old_data or decomposition:
                return 'DELETE_LEGACY_DL1009', 'Superseded historical experimental data; no current input dependency; source/models/configs/results retained', 'DL1018/README.md; legacy experiment final reports'
        return 'KEEP_METADATA_OR_OTHER', 'Source, result summary, figure or unconfirmed non-dataset MAT', ''
    if f['path'] in POS_CANDIDATES:
        return 'DELETE_CACHED_POS_OFF_RAW', '816 scene H5/NPZ/start inputs validated, six raw representatives retained; no current input reference; offline training remains available, full trajectory requires rerunning simulation', 'reports/dataset_cleanup_20261027/POS_OFF_CACHE_AUDIT.json'
    if parts[0] == 'data':
        return 'KEEP_PRIMARY', 'Shared primary B/POS_OFF/DEV/events and certified training sources', ''
    if len(parts) > 1 and parts[1] in FAILED and (is_raw or ext in {'.h5', '.hdf5', '.npz', '.npy'}):
        return 'DELETE_CLOSED_FAILED', 'Closed failed/superseded branch; no current input dependency; raw regeneration requires rerunning simulation', FAILED[parts[1]]
    if 'attitude_physics_inertia_observer_20261025' in parts and 'paired_runner' in parts and is_raw:
        return 'DELETE_RETIRED_PHYSICS_ROLLOUT', 'Previous physics/observer DEV campaign superseded by current DL direction after matched-observer rejection; no current raw input reference; keep scores/configuration/source', 'experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/GHP7_FULL_PILOT_ROOT_CAUSE_AND_DL_NEXT_STEP_v1.md'
    if 'attitude_physics_inertia_observer_20261025' in parts and 'pilot_runs' in parts and is_raw:
        run_dir = parts[parts.index('pilot_runs') + 1]
        if run_dir.startswith(('C5_00_', 'C5_01_', 'C5_11_')):
            return 'DELETE_REJECTED_OBSERVER', 'Observer/zero-compensation and fixed-shape pilot branch stopped; B/C5_RBF/C5_10 and RBF_F comparators retained', 'experiments/attitude_physics_inertia_observer_20261025/holdout_gate_inspection_v2/GHP7_FULL_PILOT_ROOT_CAUSE_AND_DL_NEXT_STEP_v1.md'
    if parts[:3] == ('reports', 'attitude_position_context_probe_20261024', 'offline_events_v1') and name == 'events_t1_b_v1.json':
        return 'DELETE_BROKEN_INTERMEDIATE', '1.1 GiB malformed partial JSON superseded by small validated v2 exports', 'reports/attitude_position_context_probe_20261024/ROOT_INTERIM_MECHANISM_DECISION_v1_ZH.md'
    if len(parts) > 1 and parts[0] == 'reports' and parts[1] in ('train_pcf_contract_reconstruction_20261022', 'train_pcf_contract_reconstruction_val_v2_20261022') and is_derived:
        return 'DELETE_REBUILDABLE_SIDECAR', 'Reconstructable sidecars from retained primary raw, model and reconstruction scripts', ''
    return 'KEEP_SHARED_OR_EVIDENCE', 'Shared datasets, successful C5/physics/TEST benchmarks, or no confirmed abandonment', ''

all_rows, candidates = [], []
for f in FILES:
    action, reason, evidence = classify(f)
    record = {**f, 'action': action, 'reason': reason, 'evidence': evidence}
    all_rows.append(record)
    if action.startswith('DELETE_'):
        p = Path('\\\\?\\' + f['path']); st = p.stat()
        assert st.st_size == f['size'] and st.st_mtime_ns == f['mtime_ns'], f['path']
        assert not p.is_symlink()
        record['mtime_ticks'] = st.st_mtime_ns // 100 + 621355968000000000
        candidates.append(record)

fields = ['project', 'path', 'rel', 'size', 'mtime_ns', 'action', 'reason', 'evidence']
with (OUT / 'ALL_FILES_CLASSIFIED.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(all_rows)
with (OUT / 'DELETE_MANIFEST.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=fields + ['mtime_ticks']); writer.writeheader(); writer.writerows(candidates)
with (OUT / 'CURRENT_PROTECTED_REFERENCES.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.writer(handle); writer.writerow(['path', 'referenced_by'])
    for key, source in sorted(protected.items()): writer.writerow([LOOKUP[key]['path'], source])

groups = collections.defaultdict(lambda: {'files': 0, 'bytes': 0})
for r in candidates:
    p = Path(r['rel']); experiment = p.parts[2] if r['project'] == 'DL1009' else p.parts[1]
    g = groups[r['project'] + '/' + experiment]; g['files'] += 1; g['bytes'] += r['size']
summary = {'status': 'AUDITED_PENDING_EXECUTION', 'all_files_traversed': len(FILES), 'traversal_errors': INV['errors'],
           'current_metadata_files_followed': len(visited), 'current_explicit_protected_files': len(protected),
           'delete_files': len(candidates), 'delete_bytes': sum(r['size'] for r in candidates),
           'manifest_sha256': hashlib.sha256((OUT / 'DELETE_MANIFEST.csv').read_bytes()).hexdigest(), 'groups': groups}
(OUT / 'SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=True, indent=2))
