from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np
from scipy.io import loadmat

ROOT = Path.cwd()
OUT = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/audits'
BASE = ROOT / 'experiments/dl_attitude_replacement_20261026'
DATA = BASE / 'mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz'
MANIFEST = BASE / 'mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json'
MODEL = BASE / 'gru_stream_cosine_c5_teacher_v1/runs/GRU32_STREAM72_COSINE_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
ROOT_METRICS = BASE / 'gru_stream_dev_v1/ROOT_SIX_PYTHON_METRICS_v1.json'
ROOT_DECISION = BASE / 'gru_stream_dev_v1/ROOT_SIX_SCENE_DECISION_v1.json'
OLD_SCRIPT = BASE / 'attitude_target_semantics_diagnosis_20261027_v1/diagnose_target_semantics.py'
MODEL_SHA = None
DT, BETA_RISE = 0.001, 2.2
AXES = ('roll', 'pitch', 'yaw')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def vec(a):
    return np.asarray(a, dtype=np.float64).reshape(-1)


def infer_scene(features, model):
    mean, std = vec(model['input_mean']), vec(model['input_std'])
    target_rms = vec(model['target_rms'])
    wih = np.asarray(model['gru_weight_ih'], dtype=np.float64)
    whh = np.asarray(model['gru_weight_hh'], dtype=np.float64)
    bih, bhh = vec(model['gru_bias_ih']), vec(model['gru_bias_hh'])
    head_w = np.asarray(model['head_weight'], dtype=np.float64)
    head_b = vec(model['head_bias'])
    h = np.zeros(32, dtype=np.float64)
    pred_raw = np.empty((len(features), 3), dtype=np.float64)
    hidden = np.empty((len(features), 32), dtype=np.float64)
    pred_norm = np.empty((len(features), 3), dtype=np.float64)
    for t, f in enumerate(features):
        x = (np.asarray(f, dtype=np.float64) - mean) / std
        gi, gh = wih @ x + bih, whh @ h + bhh
        reset = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
        update = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
        candidate = np.tanh(gi[64:96] + reset * gh[64:96])
        h = (1.0 - update) * candidate + update * h
        pred_norm[t] = head_w @ h + head_b
        pred_raw[t] = pred_norm[t] * target_rms
        hidden[t] = h
    return pred_raw, pred_norm, hidden


def metric(pred, target):
    err = pred - target
    return {
        'valid_n': int(len(err)),
        'rmse_rad_s2': np.sqrt(np.mean(err * err, axis=0)).tolist(),
        'mean_bias_prediction_minus_target_rad_s2': np.mean(err, axis=0).tolist(),
        'target_rms_rad_s2': np.sqrt(np.mean(target * target, axis=0)).tolist(),
    }


def grad_summary(pred_norm, target_norm):
    clipped = np.clip(pred_norm - target_norm, -1.0, 1.0)
    # SmoothL1 mean reduction over events and 3 outputs.
    g = np.mean(clipped, axis=0) / 3.0
    return {'head_bias_gradient': g.tolist(), 'l2_norm': float(np.linalg.norm(g)),
            'max_abs_component': float(np.max(np.abs(g)))}


def main():
    result_path = OUT / 'COSINE_FULL72_TEACHER_FIT_AND_HEAD_GRADIENT.json'
    if result_path.exists():
        raise FileExistsError(f'refusing to overwrite {result_path}')
    model_sha = sha256(MODEL)
    assert MODEL.is_file()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert manifest['dataset_sha256'] == sha256(DATA)
    decision = json.loads(ROOT_DECISION.read_text(encoding='utf-8'))
    assert decision['status'] == 'SCREEN_FAIL_NO_DEV72_OR_TEST_EXPANSION'
    assert decision['TEST_read'] is False
    root_metrics = json.loads(ROOT_METRICS.read_text(encoding='utf-8'))
    assert root_metrics['TEST_read'] is False and root_metrics['Plant_calls'] == 6
    old_script_hash = sha256(OLD_SCRIPT)
    mat = loadmat(MODEL)
    model = {k: mat[k] for k in ('input_mean','input_std','target_rms','gru_weight_ih',
        'gru_weight_hh','gru_bias_ih','gru_bias_hh','head_weight','head_bias')}
    ds = np.load(DATA, allow_pickle=False)
    splits = {
        'TRAIN24': (ds['c5_train_scene_ids'], ds['c5_train_x'], ds['c5_train_y']),
        'VAL48': (ds['c5_val_scene_ids'], ds['c5_val_x'], ds['c5_val_y']),
    }
    all_ids = [str(x) for split in splits.values() for x in split[0].tolist()]
    assert len(all_ids) == 72 and len(set(all_ids)) == 72
    assert all(split[1].shape == (len(split[0]), 1999, 13) and
               split[2].shape == (len(split[0]), 1999, 3) for split in splits.values())
    means, stds = vec(model['input_mean']), vec(model['input_std'])
    target_rms = vec(model['target_rms'])
    assert means.shape == stds.shape == (13,) and target_rms.shape == (3,)
    assert np.all(stds > 0) and np.all(target_rms > 0)
    events = np.arange(10, 20_000, 10, dtype=np.int64)
    times = events * DT
    beta = np.minimum((events + 1) * DT / BETA_RISE, 1.0)
    masks = {'all_events': np.ones(1999, dtype=bool),
             'beta_mature_events': beta >= 1.0,
             'late_last_5s_events': times >= 15.0}

    all_preds_list, all_targets_list, all_norm_pred_list = [], [], []
    all_chunk_grads = []
    split_results = {}
    for split_name, (ids, xs, ys) in splits.items():
        preds, targets, pred_norms = [], [], []
        split_chunk_grads = []
        scene_ids = [str(x) for x in ids.tolist()]
        for scene_id, x, y in zip(scene_ids, xs, ys):
            x64, y64 = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
            assert np.isfinite(x64).all() and np.isfinite(y64).all()
            pred, pred_norm, hidden = infer_scene(x64, model)  # h=0 separately for every scene.
            assert pred.shape == y64.shape == (1999, 3) and hidden.shape == (1999, 32)
            preds.append(pred); targets.append(y64); pred_norms.append(pred_norm)
            all_preds_list.append(pred); all_targets_list.append(y64); all_norm_pred_list.append(pred_norm)
            for start in range(0, 1999, 128):
                end = min(start + 128, 1999)
                cgrad = np.mean(np.clip(pred_norm[start:end] - y64[start:end] / target_rms, -1.0, 1.0), axis=0) / 3.0
                split_chunk_grads.append(cgrad)
        pred_all = np.concatenate(preds, axis=0)
        target_all = np.concatenate(targets, axis=0)
        norm_pred_all = np.concatenate(pred_norms, axis=0)
        norm_target_all = target_all / target_rms[None, :]
        split_results[split_name] = {
            'scene_count': len(scene_ids), 'events_per_scene': 1999,
            'teacher_fit_pre_DMAX': {name: metric(pred_all[np.tile(mask, len(scene_ids))],
                target_all[np.tile(mask, len(scene_ids))]) for name, mask in masks.items()},
            'head_bias_smoothl1_gradient': {
                'event_equal': grad_summary(norm_pred_all, norm_target_all),
                'scene_chunk_equal_16_chunks_of_128_then_79': {
                    'head_bias_gradient': np.mean(np.stack(split_chunk_grads), axis=0).tolist(),
                    'l2_norm': float(np.linalg.norm(np.mean(np.stack(split_chunk_grads), axis=0))),
                    'max_abs_component': float(np.max(np.abs(np.mean(np.stack(split_chunk_grads), axis=0)))),
                    'scene_chunk_count': len(split_chunk_grads),
                    'chunk_sizes': [min(128, 1999 - start) for start in range(0, 1999, 128)],
                },
            },
        }
        all_chunk_grads.extend(split_chunk_grads)

    all_preds = np.concatenate(all_preds_list, axis=0)
    all_targets = np.concatenate(all_targets_list, axis=0)
    all_norm_pred = np.concatenate(all_norm_pred_list, axis=0)
    all_norm_target = all_targets / target_rms[None, :]
    all_chunk_grad = np.mean(np.stack(all_chunk_grads), axis=0)
    split_results['ALL72'] = {
        'scene_count': 72, 'events_per_scene': 1999,
        'teacher_fit_pre_DMAX': {name: metric(all_preds[np.tile(mask, 72)],
            all_targets[np.tile(mask, 72)]) for name, mask in masks.items()},
        'head_bias_smoothl1_gradient': {
            'event_equal': grad_summary(all_norm_pred, all_norm_target),
            'scene_chunk_equal_16_chunks_of_128_then_79': {
                'head_bias_gradient': all_chunk_grad.tolist(),
                'l2_norm': float(np.linalg.norm(all_chunk_grad)),
                'max_abs_component': float(np.max(np.abs(all_chunk_grad))),
                'scene_chunk_count': len(all_chunk_grads),
                'chunk_sizes': [min(128, 1999 - start) for start in range(0, 1999, 128)],
                'training_batch_interpretation': 'Per 128-event chunk, loss mean over each 4-scene batch / valid events / 3 outputs; average the resulting fixed-hidden gradients equally over all 72 scenes and 16 time chunks. This is a read-only current-gradient summary, not a replay of historical Adam updates.',
            },
        },
    }
    # Validation that split metrics are weighted consistently with the concatenated all-72 data.
    assert split_results['ALL72']['teacher_fit_pre_DMAX']['all_events']['valid_n'] == 72 * 1999
    chunk_sizes = [min(128, 1999 - start) for start in range(0, 1999, 128)]
    assert chunk_sizes == [128] * 15 + [79]
    hashes = {str(p): sha256(p) for p in (DATA, MANIFEST, MODEL, ROOT_METRICS, ROOT_DECISION, OLD_SCRIPT)}
    out = {
        'schema': 'FULL72_TEACHER_FIT_AND_HEAD_GRADIENT_V1',
        'status': 'PASS_READ_ONLY_FULL72_FIXED_HIDDEN_DIAGNOSTIC',
        'analysis_script_sha256': sha256(Path(__file__)),
        'scope': {'Plant_calls': 0, 'training_jobs': 0, 'optimizer_updates': 0, 'TEST_read': False,
                  'true_inertia_read': False, 'Jhat_used': False, 'Jdot_used': False},
        'input_sha256': hashes,
        'frozen_model_sha256': model_sha,
        'data_source': 'C5 teacher matched_teacher_data_v1.npz only; no scene raw or physical run parameters read.',
        'event_clock': {'sample_indices_zero_based': [10,20,30,19990], 'event_count_per_scene': 1999,
                        'first_last_time_s': [0.01,19.99], 'mature_beta_rule': 'min((index+1)*0.001/2.2,1)>=1',
                        'late_window_rule': 'event time >= 15 s'},
        'target_fit_prediction': 'Frozen GRU raw pre-DMAX output in rad/s^2 compared with C5 teacher y; output from h=0 reset separately at scene start.',
        'gradient': {'loss': 'mean SmoothL1 over 3 output dimensions; derivative clip(pred_norm-target_norm,-1,1)/3 per output bias component.',
                     'fixed_hidden': True, 'readout_bias_only': True, 'no_optimizer_or_parameter_update': True},
        'splits': {'TRAIN24': split_results['TRAIN24'], 'VAL48': split_results['VAL48'], 'ALL72': split_results['ALL72']},
        'scene_ids': {'TRAIN24': [str(x) for x in splits['TRAIN24'][0].tolist()],
                      'VAL48': [str(x) for x in splits['VAL48'][0].tolist()]},
    }
    result_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': out['status'], 'scenes': 72,
        'all72_fit': split_results['ALL72']['teacher_fit_pre_DMAX'],
        'all72_bias_grad_event_equal': split_results['ALL72']['head_bias_smoothl1_gradient']['event_equal'],
        'all72_bias_grad_chunk_equal': split_results['ALL72']['head_bias_smoothl1_gradient']['scene_chunk_equal_16_chunks_of_128_then_79'],
        'json': str(result_path), 'json_sha256': sha256(result_path)}, indent=2))

if __name__ == '__main__':
    main()