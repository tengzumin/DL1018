from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'experiments/dl_attitude_replacement_20261026'
FEATURES = BASE / 'mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz'
TARGETS = BASE / 'nominal_command_target_data_v1/nominal_command_target_v1.npz'
TARGET_MANIFEST = BASE / 'nominal_command_target_data_v1/MANIFEST_v1.json'
TARGET_STATS = BASE / 'nominal_command_target_data_v1/TARGET_STATS_v1.csv'
LOCKED_CFG = BASE / 'gru_stream_ncmd_dev_v1/LOCKED_CFG.json'
COSINE_MODEL = BASE / 'gru_stream_cosine_c5_teacher_v1/runs/GRU32_STREAM72_COSINE_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
NCMD_MODEL = BASE / 'gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
OUT = Path(__file__).resolve().parent

EXPECTED = {
    'features': 'b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f',
    'targets': '88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7',
    'target_manifest': 'fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab',
    'target_stats': '599af4527376b88c0020b255a758586f333ca72151a70f09db48c8e829765344',
    'normalizer': '612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693',
    'cosine_model': 'b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567',
    'ncmd_model': 'cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6',
}
AXES = ('roll', 'pitch', 'yaw')
PHASES = {
    'all': slice(0, 1999),
    'early_0_5s': slice(0, 499),
    'late_15_20s': slice(1499, 1999),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_from_mat(path: Path) -> dict[str, np.ndarray]:
    raw = loadmat(path)
    vector = ('input_mean', 'input_std', 'target_rms', 'gru_bias_ih', 'gru_bias_hh', 'head_bias')
    names = (*vector, 'gru_weight_ih', 'gru_weight_hh', 'head_weight')
    return {k: np.asarray(raw[k]).reshape(-1) if k in vector else np.asarray(raw[k]) for k in names}


def stream(raw_x: np.ndarray, model: dict[str, np.ndarray]) -> np.ndarray:
    # Same reset/update/new gate order and double arithmetic as the deployed MATLAB helper.
    mu, sigma = model['input_mean'], model['input_std']
    wih, whh = model['gru_weight_ih'], model['gru_weight_hh']
    bih, bhh = model['gru_bias_ih'], model['gru_bias_hh']
    h = np.zeros(32, dtype=np.float64)
    y = np.empty((len(raw_x), 3), dtype=np.float64)
    for i, row in enumerate(np.asarray(raw_x, dtype=np.float64)):
        gi = wih @ ((row - mu) / sigma) + bih
        gh = whh @ h + bhh
        r = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
        z = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
        n = np.tanh(gi[64:96] + r * gh[64:96])
        h = (1.0 - z) * n + z * h
        y[i] = (model['head_weight'] @ h + model['head_bias']) * model['target_rms']
    return y


def meta(scene_id: str) -> dict[str, str]:
    m = re.fullmatch(r'DL1018_(?:DEV|VAL)_(T[123])_(C\d{2})_(W\d{2})', scene_id)
    if not m:
        raise ValueError(f'unexpected scene id {scene_id}')
    task, course, wind = m.groups()
    return {'task': task, 'course': course, 'wind': wind,
            'wind_group': 'W15_NO_WIND' if wind == 'W15' else ('HF_W09_W14' if 9 <= int(wind[1:]) <= 14 else 'W00_W08')}


def groups(scene_id: str) -> tuple[str, ...]:
    m = meta(scene_id)
    out = ['ALL72', m['task'], m['wind_group'], f"WIND_{m['wind']}"]
    if scene_id == 'DL1018_VAL_T2_C05_W15':
        out.append('T2_C05_W15')
    return tuple(out)


def main() -> None:
    actual = {
        'features': sha(FEATURES), 'targets': sha(TARGETS),
        'target_manifest': sha(TARGET_MANIFEST), 'target_stats': sha(TARGET_STATS),
        'cosine_model': sha(COSINE_MODEL),
        'ncmd_model': sha(NCMD_MODEL),
    }
    assert actual == {k: v for k, v in EXPECTED.items() if k != 'normalizer'}, actual
    models = {'COSINE': model_from_mat(COSINE_MODEL), 'NCMD': model_from_mat(NCMD_MODEL)}
    for k in ('input_mean', 'input_std', 'target_rms'):
        assert np.array_equal(models['COSINE'][k], models['NCMD'][k]), k
    norm_bytes = np.concatenate([models['NCMD'][k].astype(np.float64).ravel() for k in ('input_mean', 'input_std', 'target_rms')]).tobytes()
    # Confirm byte identity against the fixed model export's adjacent parity vector.
    parity_path = NCMD_MODEL.with_name('stream_parity_vector_v1.mat')
    parity = loadmat(parity_path)
    for k in ('input_mean', 'input_std', 'target_rms'):
        assert np.array_equal(models['NCMD'][k].reshape(1, -1), np.asarray(parity[k])), k
    cfg = json.loads(LOCKED_CFG.read_text(encoding='utf-8-sig'))
    dmax = np.asarray(cfg['dmax'], dtype=np.float64).reshape(3)
    features = np.load(FEATURES, allow_pickle=False)
    targets = np.load(TARGETS, allow_pickle=False)
    stat_phase = {'all': 'all', 'early_0_5s': '0-5s', 'late_15_20s': '15-20s'}
    target_clip_rate: dict[tuple[str, str, int], float] = {}
    with TARGET_STATS.open(newline='', encoding='utf-8-sig') as fstats:
        for sr in csv.DictReader(fstats):
            if sr['phase'] in ('all', '0-5s', '15-20s'):
                target_clip_rate[(sr['scene_id'], sr['phase'], int(sr['axis']) - 1)] = float(sr['clip_ratio'])
    rows: list[dict] = []
    lag_rows: list[dict] = []
    arrays: dict[str, list[tuple[str, np.ndarray, np.ndarray, np.ndarray]]] = {'DEV24': [], 'VAL48_AS_DEV_TRAIN': []}
    for split, x_key, ids_key, old_y_key, new_y_key in (
        ('DEV24', 'c5_train_x', 'c5_train_scene_ids', 'c5_train_y', 'c5_train_y_clipped_float32'),
        ('VAL48_AS_DEV_TRAIN', 'c5_val_x', 'c5_val_scene_ids', 'c5_val_y', 'c5_val_y_clipped_float32'),
    ):
        X = np.asarray(features[x_key], dtype=np.float64)
        ids = np.asarray(features[ids_key]).astype(str)
        ids_ncmd = np.asarray(targets[ids_key]).astype(str)
        old_y = np.asarray(features[old_y_key], dtype=np.float64)
        new_y = np.asarray(targets[new_y_key], dtype=np.float64)
        assert X.shape == (len(ids), 1999, 13) and old_y.shape == new_y.shape == (len(ids), 1999, 3)
        assert np.array_equal(ids, ids_ncmd) and np.isfinite(X).all() and np.isfinite(old_y).all() and np.isfinite(new_y).all()
        for i, scene_id in enumerate(ids):
            pred = {name: stream(X[i], model) for name, model in models.items()}
            arrays[split].append((scene_id, new_y[i], old_y[i], pred['NCMD']))
            for group in groups(scene_id):
                for phase, event_slice in PHASES.items():
                    sl = event_slice
                    for axis, axis_name in enumerate(AXES):
                        yn = new_y[i, sl, axis]
                        yt = old_y[i, sl, axis]
                        p_raw = pred['NCMD'][sl, axis]
                        p_clip = np.clip(p_raw, -dmax[axis], dmax[axis])
                        target_shift = yn - yt
                        for model_name, p in pred.items():
                            p0 = p[sl, axis]
                            for target_name, y in (('NCMD_CLIPPED', yn), ('C5_TEACHER', yt)):
                                e = p0 - y
                                ec = np.clip(p0, -dmax[axis], dmax[axis]) - y
                                rows.append({
                                    'split': split, 'scene_id': scene_id, 'group': group, 'phase': phase,
                                    'model': model_name, 'target': target_name, 'axis': axis_name,
                                    'n': len(e), 'bias_rad_s2': float(np.mean(e)),
                                    'rmse_rad_s2': float(np.sqrt(np.mean(e*e))),
                                    'clipped_output_rmse_rad_s2': float(np.sqrt(np.mean(ec*ec))),
                                    'pred_clip_rate': float(np.mean(np.abs(p0) > dmax[axis])),
                                    'label_clip_rate': (target_clip_rate[(scene_id, stat_phase[phase], axis)]
                                                        if target_name == 'NCMD_CLIPPED'
                                                        else float(np.mean(np.abs(y) >= dmax[axis]))),
                                    'target_rms_rad_s2': float(np.sqrt(np.mean(y*y))),
                                })
                        rows.append({
                            'split': split, 'scene_id': scene_id, 'group': group, 'phase': phase,
                            'model': 'TARGET_CHANGE', 'target': 'NCMD_MINUS_C5', 'axis': axis_name,
                            'n': len(target_shift), 'bias_rad_s2': float(np.mean(target_shift)),
                            'rmse_rad_s2': float(np.sqrt(np.mean(target_shift**2))),
                            'clipped_output_rmse_rad_s2': '', 'pred_clip_rate': '', 'label_clip_rate': '',
                            'target_rms_rad_s2': float(np.sqrt(np.mean(yn*yn))),
                        })
            # Per-scene, no-wrap lag scan for NCMD prediction vs NCMD target.
            for offset in (-2, -1, 0, 1, 2):
                if offset < 0:
                    pp, yy = pred['NCMD'][-offset:], new_y[i, :1999+offset]
                elif offset > 0:
                    pp, yy = pred['NCMD'][:-offset], new_y[i, offset:]
                else:
                    pp, yy = pred['NCMD'], new_y[i]
                for group in groups(scene_id):
                    for axis, axis_name in enumerate(AXES):
                        err = pp[:, axis] - yy[:, axis]
                        lag_rows.append({'split': split, 'scene_id': scene_id, 'group': group,
                                         'offset_events': offset, 'axis': axis_name, 'n': len(err),
                                         'bias_rad_s2': float(np.mean(err)),
                                         'rmse_rad_s2': float(np.sqrt(np.mean(err*err)))})

    def write_csv(path: Path, data: list[dict]) -> None:
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader(); w.writerows(data)

    scene_csv = OUT / 'open_loop_scene_metrics_v1.csv'
    lag_csv = OUT / 'ncmd_event_lag_scan_v1.csv'
    write_csv(scene_csv, rows); write_csv(lag_csv, lag_rows)
    group_rows: list[dict] = []
    group_keys = {(r['split'], r['group'], r['phase'], r['model'], r['target'], r['axis']) for r in rows}
    group_keys |= {('FULL72', r['group'], r['phase'], r['model'], r['target'], r['axis']) for r in rows}
    group_keys = sorted(group_keys)
    for split, group, phase, model_name, target_name, axis_name in group_keys:
        rr = [r for r in rows if (r['group'], r['phase'], r['model'], r['target'], r['axis']) ==
              (group, phase, model_name, target_name, axis_name)
              and (split == 'FULL72' or r['split'] == split)]
        nall = sum(int(r['n']) for r in rr)
        pooled_bias = sum(int(r['n']) * float(r['bias_rad_s2']) for r in rr) / nall
        pooled_rmse = float(np.sqrt(sum(int(r['n']) * float(r['rmse_rad_s2']) ** 2 for r in rr) / nall))
        pooled_clip_rmse = '' if rr[0]['clipped_output_rmse_rad_s2'] == '' else float(np.sqrt(
            sum(int(r['n']) * float(r['clipped_output_rmse_rad_s2']) ** 2 for r in rr) / nall))
        group_rows.append({'split': split, 'group': group, 'phase': phase, 'model': model_name,
                           'target': target_name, 'axis': axis_name, 'scene_count': len(rr), 'event_count': nall,
                           'pooled_bias_rad_s2': pooled_bias, 'pooled_rmse_rad_s2': pooled_rmse,
                           'scenario_macro_bias_rad_s2': float(np.mean([float(r['bias_rad_s2']) for r in rr])),
                           'scenario_macro_rmse_rad_s2': float(np.mean([float(r['rmse_rad_s2']) for r in rr])),
                           'pooled_clipped_output_rmse_rad_s2': pooled_clip_rmse,
                           'pooled_pred_clip_rate': (sum(int(r['n']) * float(r['pred_clip_rate']) for r in rr) / nall
                                                      if rr[0]['pred_clip_rate'] != '' else ''),
                           'pooled_label_clip_rate': (sum(int(r['n']) * float(r['label_clip_rate']) for r in rr) / nall
                                                       if rr[0]['label_clip_rate'] != '' else ''),
                           'pooled_target_rms_rad_s2': float(np.sqrt(
                               sum(int(r['n']) * float(r['target_rms_rad_s2']) ** 2 for r in rr) / nall))})
    group_csv = OUT / 'open_loop_group_metrics_v1.csv'
    write_csv(group_csv, group_rows)
    lag_group_rows: list[dict] = []
    lag_keys = sorted({(r['split'], r['group'], r['offset_events'], r['axis']) for r in lag_rows})
    for split, group, offset, axis_name in lag_keys:
        rr = [r for r in lag_rows if (r['split'], r['group'], r['offset_events'], r['axis']) ==
              (split, group, offset, axis_name)]
        nall = sum(int(r['n']) for r in rr)
        lag_group_rows.append({'split': split, 'group': group, 'offset_events': offset, 'axis': axis_name,
                               'scene_count': len(rr), 'event_count': nall,
                               'pooled_bias_rad_s2': sum(int(r['n']) * float(r['bias_rad_s2']) for r in rr) / nall,
                               'pooled_rmse_rad_s2': float(np.sqrt(
                                   sum(int(r['n']) * float(r['rmse_rad_s2']) ** 2 for r in rr) / nall)),
                               'scenario_macro_rmse_rad_s2': float(np.mean([float(r['rmse_rad_s2']) for r in rr]))})
    lag_group_csv = OUT / 'ncmd_event_lag_group_metrics_v1.csv'
    write_csv(lag_group_csv, lag_group_rows)
    report = {
        'schema': 'DL1018_NCMD_LABEL_PREDICTABILITY_V1', 'status': 'PASS_HISTORICAL_C5_OFFLINE_DIAGNOSTIC',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {'training': False, 'optimizer_updates': 0, 'Plant_calls': 0, 'TEST_read': False,
                  'raws_read': False, 'dataset_role': 'DEV24 + VAL48_AS_DEV_TRAIN; all 72 are development material, no independent validation'},
        'method': {'model_inference': 'per-scene hidden reset; double precision; deployed GRU reset/update/new gate equation; legal 13D feature X only',
                   'events_per_scene': 1999, 'event_period_s': 0.01, 'target': 'NCMD clipped_float32 only',
                   'old_teacher_y': 'read only as historical label comparison; not training input for NCMD',
                   'lag_scan': 'prediction event j compared with label event j+offset, offsets -2..+2; no cross-scene wrap',
                   'groups': ['ALL72','T1','T2','T3','W15_NO_WIND','HF_W09_W14','W00_W08','T2_C05_W15'],
                   'phases': {'all': 'events 1..1999', 'early_0_5s': 'events 1..499', 'late_15_20s': 'events 1500..1999'}},
        'identity': {'feature_npz_sha256': actual['features'], 'ncmd_target_npz_sha256': actual['targets'],
                     'ncmd_target_manifest_sha256': actual['target_manifest'],
                     'target_stats_csv_sha256': actual['target_stats'],
                     'cosine_model_sha256': actual['cosine_model'], 'ncmd_model_sha256': actual['ncmd_model'],
                     'normalizer_member_values_match_between_models': True,
                     'normalizer_sha256_from_approved_lock': EXPECTED['normalizer'],
                     'dmax_rad_s2': dmax.tolist()},
        'outputs': {'scene_csv': str(scene_csv), 'scene_csv_sha256': sha(scene_csv),
                    'scene_rows': len(rows), 'group_csv': str(group_csv), 'group_csv_sha256': sha(group_csv),
                    'group_rows': len(group_rows), 'lag_csv': str(lag_csv), 'lag_csv_sha256': sha(lag_csv),
                    'lag_rows': len(lag_rows), 'lag_group_csv': str(lag_group_csv),
                    'lag_group_csv_sha256': sha(lag_group_csv), 'lag_group_rows': len(lag_group_rows)},
        'script_sha256': sha(Path(__file__)),
    }
    out_json = OUT / 'OPEN_LOOP_FIT_DIAGNOSTIC_v1.json'
    out_json.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'scene_rows': len(rows), 'lag_rows': len(lag_rows),
                      'scene_csv': str(scene_csv), 'group_csv': str(group_csv), 'lag_csv': str(lag_csv), 'json': str(out_json),
                      'model_sha256': actual['ncmd_model']}, indent=2))


if __name__ == '__main__':
    main()
