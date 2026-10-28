"""Bind three fixed TRAIN scenes and freeze the isolated zero-Plant runner."""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy.signal import butter

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BATCH = BASE / 'no_position_gru_notch_train24_batch_prepare_v1/BATCH_BINDINGS_v1.json'
AUDIT = BASE / 'causal_n4_gate_train24_acden_v2/CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.json'
AUDIT_NPZ = BASE / 'causal_n4_gate_train24_acden_v2/CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz'
TEMPLATE = BASE / 'n4T3C09_v1/TRAIN_SCENE_BINDING_v1.json'
SCENES = ['DL1018_DEV_T3_C09_W09', 'DL1018_DEV_T1_C00_W03', 'DL1018_DEV_T1_C11_W12']


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, x):
    if path.exists():
        raise RuntimeError(f'Refusing to overwrite {path}')
    path.write_text(json.dumps(x, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def main():
    lock_path, release_path = HERE/'SOURCE_LOCK_v2.json', HERE/'RELEASE.json'
    if lock_path.exists() or release_path.exists() or any((HERE/'bindings').iterdir()):
        raise RuntimeError('Refusing to reuse existing lock, release, or bindings')
    audit, batch, parity = read(AUDIT), read(BATCH), read(HERE/'MATLAB_PARITY_RESULT_v2.json')
    assert audit['source']['bindings_sha256'] == sha(BATCH)
    assert audit['source']['per_event_npz_sha256'] == sha(AUDIT_NPZ)
    assert parity['status'] == 'PASS_MATLAB_HELPER_PARITY_V2' and parity['matlab_release'] == '2025b'
    assert parity['max_abs_error'] <= 2e-10 and parity['plant_calls'] == 0
    assert batch['scope'].startswith('TRAIN_C5_24 only') and len(batch['bindings']) == 24
    rows = {r['scene_id']: r for r in batch['bindings']}
    assert all(scene in rows for scene in SCENES)
    template = read(TEMPLATE)
    locked_sources = set()
    required_paths = ('dataset_manifest_path', 'dataset_source_lock_path', 'parent_cosine_model_path',
        'c5_snapshot_path', 'position_model_path', 'c5_receipt_path', 'local_scene_payload_path',
        'parent_raw_path', 'parent_status_path', 'parent_run_start_path', 'c5_raw_path', 'c5_status_path',
        'b72_scoring_raw_path', 'b72_scoring_status_path')
    for scene in SCENES:
        row = rows[scene]
        b = dict(template)
        c = row['same_scene_comparators']
        b.update({'selected_scene_id': scene, 'source_order_zero_based': row['source_order_zero_based'],
            'fold_id': row['diagnostic_fold_id'], 'external_identity_sha256': row['scene_identity_sha256'],
            'scene_payload_source_path': row['scene_payload']['path'],
            'scene_payload_source_sha256': row['scene_payload']['sha256'],
            'local_scene_payload_path': row['scene_payload']['path'],
            'local_scene_payload_sha256': row['scene_payload']['sha256'],
            'study_id': 'causal_n4_gate_v2'})
        for label, prefix in (('parent_cosine_gru','parent'), ('C5','c5'), ('B','b72_scoring')):
            for field in ('raw_path','raw_sha256','status_path','status_sha256'):
                b[f'{prefix}_{field}'] = c[label][field]
        for prefix, label in (('parent','parent_cosine_gru'),('c5','C5')):
            for field in ('run_start_path','run_start_sha256'):
                b[f'{prefix}_{field}'] = c[label][field]
        for k in list(b):
            if (k.startswith('fold_') and k != 'fold_id') or k.startswith('oof_') or k in {
                'local_fold_checkpoint_path','local_fold_checkpoint_sha256','weights_mat_path','weights_mat_sha256',
                'fold_checkpoint_path','fold_checkpoint_sha256'}:
                b.pop(k, None)
        for field in required_paths:
            path = Path(b[field])
            assert path.is_file() and sha(path) == b[field[:-5]+'_sha256'], f'{scene}: {field}'
            locked_sources.add(path)
        write(HERE/'bindings'/f'{scene}.json', b)
    w = 2*np.pi*np.array([2.2,3.2,3.7,4.8])/100
    alpha = np.sin(w)/8
    b = np.column_stack((1/(1+alpha), -2*np.cos(w)/(1+alpha), 1/(1+alpha)))
    a = np.column_stack((np.ones(4), -2*np.cos(w)/(1+alpha), (1-alpha)/(1+alpha)))
    sources = {p for p in (HERE/'candidate_runner_work').rglob('*') if p.is_file()}
    sources.update((HERE/'bindings').glob('*.json'))
    sources.update(locked_sources)
    sources.update({BATCH, AUDIT, AUDIT_NPZ, HERE/'helper_parity_v2.py', HERE/'run_helper_parity_v2.m',
        HERE/'HELPER_PARITY_FIXTURE_v2.mat', HERE/'HELPER_PARITY_INPUT_v2.json',
        HERE/'MATLAB_PARITY_RESULT_v2.json', HERE/'patch_runner_v2.py', Path(__file__).resolve()})
    files = [{'path': str(p.resolve()), 'sha256': sha(p)} for p in sorted(sources, key=lambda x: str(x).lower())]
    write(lock_path, {'study_id':'causal_n4_gate_v2', 'files':files})
    release = {'schema':'DL1018_CAUSAL_N4_GATE_NOPLANT_V2', 'study_id':'causal_n4_gate_v2',
        'status':'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT', 'authorized_scenes':SCENES,
        'authorized_Plant_calls':0, 'Plant_calls':0, 'potential_budget_calls':0,
        'source_lock_sha256':sha(lock_path),
        'applied_acceleration_static_n4':{'enabled':True, 'centers_hz':[2.2,3.2,3.7,4.8],
            'quality_factor_each':[4,4,4,4], 'sample_rate_hz':100, 'action_limit_mps2':3,
            'b':b.tolist(), 'a':a.tolist(),
            'gate_bp_sos':butter(2,[2,5],btype='bandpass',fs=100,output='sos').tolist(),
            'gate_lo_sos':butter(2,[.5,2],btype='bandpass',fs=100,output='sos').tolist(),
            'gate_energy_tau_s':1, 'gate_ratio_epsilon':1e-8, 'gate_ratio_low':.35,
            'gate_ratio_span':.30, 'gate_tau_s':.3, 'startup_gate_zero_until_s':2,
            'event_contract':'1999 events 0.01:0.01:19.99; 31 warmup actions are zero; ZOH at other 1-ms steps',
            'application_point':'final C5 applied compensation before position_bs_step',
            'state_initialization':'gate SOS zero; N4 first nonzero input initializes all section histories',
            'runtime_wind_or_W_code_branching':False},
        'extra_position_residual_gru_enabled':False, 'TEST_read':False, 'VAL_data_read':False,
        'inertia_reconstruction_enabled':False, 'Plant_truth_deployment_input':False}
    write(release_path, release)
    print(json.dumps({'source_lock_sha256':sha(lock_path), 'release_sha256':sha(release_path),
                      'source_files':len(files), 'scenes':SCENES, 'authorized_Plant_calls':0}, indent=2))


if __name__ == '__main__':
    main()
