from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'experiments/dl_attitude_replacement_20261026'
STUDY = BASE / 'gru_stream_ncmd_dev_v1'
FEATURES = BASE / 'mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz'
MODEL_PATH = BASE / 'gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
CFG_PATH = STUDY / 'LOCKED_CFG.json'
OUT = Path(__file__).resolve().parent
SCENES = (
    'DL1018_VAL_T1_C08_W15', 'DL1018_VAL_T2_C05_W15', 'DL1018_VAL_T3_C02_W15',
    'DL1018_VAL_T1_C05_W12', 'DL1018_VAL_T2_C02_W12', 'DL1018_VAL_T3_C00_W13',
)
IN_DIMS = (0, 1, 2, 3, 4, 5)  # attitude-error xyz and body-rate xyz


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_model(path: Path) -> dict[str, np.ndarray]:
    raw = loadmat(path)
    vec = ('input_mean', 'input_std', 'target_rms', 'gru_bias_ih', 'gru_bias_hh', 'head_bias')
    names = (*vec, 'gru_weight_ih', 'gru_weight_hh', 'head_weight')
    return {k: np.asarray(raw[k]).reshape(-1) if k in vec else np.asarray(raw[k]) for k in names}


def one(x: np.ndarray, h0: np.ndarray, m: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    gi = m['gru_weight_ih'] @ ((x - m['input_mean']) / m['input_std']) + m['gru_bias_ih']
    gh = m['gru_weight_hh'] @ h0 + m['gru_bias_hh']
    r = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
    z = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
    n = np.tanh(gi[64:96] + r * gh[64:96])
    h1 = (1.0 - z) * n + z * h0
    y = (m['head_weight'] @ h1 + m['head_bias']) * m['target_rms']
    return y, h1


def stream_before(X: np.ndarray, m: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    h = np.zeros(32, dtype=np.float64)
    hb = np.empty((len(X), 32), dtype=np.float64)
    y = np.empty((len(X), 3), dtype=np.float64)
    for i, x in enumerate(np.asarray(X, dtype=np.float64)):
        hb[i] = h
        y[i], h = one(x, h, m)
    return y, hb


def local(x: np.ndarray, h: np.ndarray, m: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    y0, _ = one(x, h, m)
    jac = np.empty((3, len(IN_DIMS)), dtype=np.float64)
    for col, dim in enumerate(IN_DIMS):
        eps = 1e-4 * m['input_std'][dim]  # +/- 1e-4 in normalized feature coordinates
        xp, xm = x.copy(), x.copy()
        xp[dim] += eps; xm[dim] -= eps
        yp, _ = one(xp, h, m); ym, _ = one(xm, h, m)
        jac[:, col] = (yp - ym) / (2.0 * eps)
    y_zero_hidden, _ = one(x, np.zeros(32, dtype=np.float64), m)
    return jac, y0 - y_zero_hidden


def scene_tag(scene: str) -> dict[str, str]:
    match = re.fullmatch(r'DL1018_VAL_(T[123])_(C\d{2})_(W\d{2})', scene)
    if not match:
        raise ValueError(scene)
    task, course, wind = match.groups()
    group = 'W15_NO_WIND' if wind == 'W15' else ('HF_W09_W14' if 9 <= int(wind[1:]) <= 14 else 'W00_W08')
    return {'task': task, 'course': course, 'wind': wind, 'wind_group': group}


def groups(scene: str) -> tuple[str, ...]:
    t = scene_tag(scene)
    out = ['ALL6', t['task'], t['wind_group'], f"WIND_{t['wind']}"]
    if scene == 'DL1018_VAL_T2_C05_W15':
        out.append('T2_C05_W15')
    return tuple(out)


def main() -> None:
    model = read_model(MODEL_PATH)
    cfg = json.loads(CFG_PATH.read_text(encoding='utf-8-sig'))
    J0 = np.asarray(cfg['J0_kgm2'], dtype=np.float64)
    beta_rise = float(cfg['beta_rise_time_s'])
    dt = float(cfg['simulation_sample_time_s'])
    features = np.load(FEATURES, allow_pickle=False)
    ids_tr = np.asarray(features['c5_train_scene_ids']).astype(str)
    ids_va = np.asarray(features['c5_val_scene_ids']).astype(str)
    c5_X = {}
    for ids, key in ((ids_tr, 'c5_train_x'), (ids_va, 'c5_val_x')):
        arr = np.asarray(features[key], dtype=np.float64)
        for i, scene in enumerate(ids):
            c5_X[scene] = arr[i]

    event_rows: list[dict] = []
    hidden_swap_rows: list[dict] = []
    raw_ids: dict[str, dict] = {}
    for scene in SCENES:
        raw_dir = STUDY / 'runs' / scene
        raw_path = raw_dir / 'raw_run.mat'
        status = json.loads((raw_dir / 'run_status.json').read_text(encoding='utf-8-sig'))
        audit = json.loads((STUDY / 'audits' / f'{scene}_GRU_STREAM_RAW_AUDIT.json').read_text(encoding='utf-8-sig'))
        raw_hash = sha(raw_path)
        assert status['state'] == 'COMPLETED' and status['raw_sha256'] == raw_hash
        assert audit['status'] == 'PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY' and audit['candidate_raw_sha256'] == raw_hash
        # C5 hidden-before is replayed from its legal 13-D X with the same frozen NCMD weights.
        c5_pred, c5_hidden = stream_before(c5_X[scene], model)
        with h5py.File(raw_path, 'r') as f:
            log = f['log']
            event_indices = np.flatnonzero(np.asarray(log['attitude_event_flag'][0, :], dtype=np.uint8))
            refs = log['gru_stream_attitude_trace'][0, :]
            on_x = np.empty((len(event_indices), 13), dtype=np.float64)
            on_hidden = np.empty((len(event_indices), 32), dtype=np.float64)
            on_pred = np.empty((len(event_indices), 3), dtype=np.float64)
            on_beta = np.empty(len(event_indices), dtype=np.float64)
            for j, idx in enumerate(event_indices):
                trace = f[refs[idx]]
                on_x[j] = np.asarray(trace['feature_raw'][()], dtype=np.float64).reshape(13)
                on_hidden[j] = np.asarray(trace['hidden_before'][()], dtype=np.float64).reshape(32)
                on_pred[j] = np.asarray(trace['raw_residual_rad_s2'][()], dtype=np.float64).reshape(3)
                on_beta[j] = float(np.asarray(trace['beta'][()]).reshape(-1)[0])
                sample = int(idx) + 1  # MATLAB one-based sample index binding the interval start.
                expected_beta = min(sample * dt / beta_rise, 1.0)
                assert abs(on_beta[j] - expected_beta) < 1e-12
        assert on_x.shape == (1999, 13) and on_hidden.shape == (1999, 32)
        assert np.max(np.abs(stream_before(on_x, model)[0] - on_pred)) < 1e-8
        for event_i in range(1999):
            # Cross hidden-before state at each fixed current feature sequence. This
            # isolates the recurrent-state contribution at that same current feature.
            y_c5x_onh, _ = one(c5_X[scene][event_i], on_hidden[event_i], model)
            y_ncmdx_c5h, _ = one(on_x[event_i], c5_hidden[event_i], model)
            delta_at_c5_feature = y_c5x_onh - c5_pred[event_i]
            delta_at_ncmd_feature = on_pred[event_i] - y_ncmdx_c5h
            swap = {'scene_id': scene, 'event_1based': event_i + 1,
                    'hidden_before_l2_distance': float(np.linalg.norm(on_hidden[event_i] - c5_hidden[event_i])),
                    'feature_l2_distance': float(np.linalg.norm(on_x[event_i] - c5_X[scene][event_i]))}
            for axis, axis_name in enumerate(('roll', 'pitch', 'yaw')):
                swap[f'output_shift_at_fixed_C5_feature_{axis_name}'] = float(delta_at_c5_feature[axis])
                swap[f'output_shift_at_fixed_NCMD_feature_{axis_name}'] = float(delta_at_ncmd_feature[axis])
            swap['output_shift_norm_at_fixed_C5_feature'] = float(np.linalg.norm(delta_at_c5_feature))
            swap['output_shift_norm_at_fixed_NCMD_feature'] = float(np.linalg.norm(delta_at_ncmd_feature))
            hidden_swap_rows.append(swap)

        for condition, X, H, beta in (
            ('C5_HISTORY', c5_X[scene], c5_hidden,
             np.minimum(np.arange(11, 20001, 10, dtype=np.float64) * dt / beta_rise, 1.0)),
            ('NCMD_SELF_CLOSED_LOOP', on_x, on_hidden, on_beta),
        ):
            for event_i, (x, h, b) in enumerate(zip(X, H, beta)):
                jac, h_effect = local(x, h, model)
                domega = jac[:, 3:6]
                # Nominal issued torque is tau_nominal - J0*beta*NN_output. This is only
                # the local command-map slope; it is not a Plant or closed-loop stability model.
                command_slope = -float(b) * J0 @ domega
                symmetric_eigs = np.linalg.eigvalsh(0.5 * (command_slope + command_slope.T))
                row = {'scene_id': scene, 'condition': condition, 'event_1based': event_i + 1,
                       'beta': float(b), 'hidden_memory_output_norm_rad_s2': float(np.linalg.norm(h_effect)),
                       'gyro_jacobian_fro_norm': float(np.linalg.norm(domega, ord='fro')),
                       'gyro_jacobian_spectral_norm': float(np.linalg.norm(domega, ord=2)),
                       'issued_torque_gyro_slope_trace': float(np.trace(command_slope)),
                       'issued_torque_gyro_slope_sigma_max': float(np.linalg.norm(command_slope, ord=2)),
                       'symmetric_slope_lambda_min': float(symmetric_eigs[0]),
                       'symmetric_slope_lambda_max': float(symmetric_eigs[-1])}
                for oi, out_name in enumerate(('roll', 'pitch', 'yaw')):
                    for ij, in_name in enumerate(('err_roll', 'err_pitch', 'err_yaw', 'rate_roll', 'rate_pitch', 'rate_yaw')):
                        row[f'd{out_name}_d{in_name}'] = float(jac[oi, ij])
                for oi, out_name in enumerate(('roll', 'pitch', 'yaw')):
                    for ij, in_name in enumerate(('roll', 'pitch', 'yaw')):
                        row[f'dtau{out_name}_drate{in_name}'] = float(command_slope[oi, ij])
                event_rows.append(row)
        raw_ids[scene] = {'raw_sha256': raw_hash, 'raw_path': str(raw_path),
                          'independent_replay_status': audit['status'], 'events': 1999}

    event_csv = OUT / 'local_feedback_event_metrics_v1.csv'
    with event_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(event_rows[0]))
        writer.writeheader(); writer.writerows(event_rows)
    summaries: list[dict] = []
    for condition in ('C5_HISTORY', 'NCMD_SELF_CLOSED_LOOP'):
        source = [r for r in event_rows if r['condition'] == condition]
        for group in ('ALL6', 'W15_NO_WIND', 'HF_W09_W14', 'T1', 'T2', 'T3', 'T2_C05_W15'):
            group_rows = [r for r in source if group in groups(r['scene_id'])]
            if not group_rows:
                continue
            for metric in ('gyro_jacobian_spectral_norm', 'issued_torque_gyro_slope_sigma_max',
                           'issued_torque_gyro_slope_trace', 'symmetric_slope_lambda_min',
                           'symmetric_slope_lambda_max', 'hidden_memory_output_norm_rad_s2'):
                vals = np.asarray([float(r[metric]) for r in group_rows])
                summaries.append({'condition': condition, 'group': group, 'metric': metric,
                                  'scene_count': len({r['scene_id'] for r in group_rows}), 'event_count': len(vals),
                                  'mean': float(np.mean(vals)), 'median': float(np.median(vals)),
                                  'p95': float(np.quantile(vals, 0.95)),
                                  'fraction_positive': float(np.mean(vals > 0.0)) if metric in (
                                      'issued_torque_gyro_slope_trace', 'symmetric_slope_lambda_min',
                                      'symmetric_slope_lambda_max') else ''})
    summary_csv = OUT / 'local_feedback_group_metrics_v1.csv'
    with summary_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader(); writer.writerows(summaries)
    swap_csv = OUT / 'hidden_before_same_feature_swap_v1.csv'
    with swap_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(hidden_swap_rows[0]))
        writer.writeheader(); writer.writerows(hidden_swap_rows)
    swap_summaries: list[dict] = []
    for group in ('ALL6', 'W15_NO_WIND', 'HF_W09_W14', 'T1', 'T2', 'T3', 'T2_C05_W15'):
        g_rows = [r for r in hidden_swap_rows if group in groups(r['scene_id'])]
        if not g_rows:
            continue
        for feature_condition in ('C5', 'NCMD'):
            for axis, axis_name in enumerate(('roll', 'pitch', 'yaw')):
                col = f'output_shift_at_fixed_{feature_condition}_feature_{axis_name}'
                v = np.asarray([float(r[col]) for r in g_rows])
                swap_summaries.append({'group': group, 'feature_condition': feature_condition,
                                       'axis': axis_name, 'scene_count': len({r['scene_id'] for r in g_rows}),
                                       'event_count': len(v), 'pooled_bias_rad_s2': float(np.mean(v)),
                                       'pooled_rmse_rad_s2': float(np.sqrt(np.mean(v*v))),
                                       'p95_abs_rad_s2': float(np.quantile(np.abs(v), 0.95)),
                                       'hidden_before_l2_mean': float(np.mean([float(r['hidden_before_l2_distance']) for r in g_rows])),
                                       'feature_l2_mean': float(np.mean([float(r['feature_l2_distance']) for r in g_rows]))})
    swap_summary_csv = OUT / 'hidden_before_same_feature_swap_summary_v1.csv'
    with swap_summary_csv.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(swap_summaries[0]))
        writer.writeheader(); writer.writerows(swap_summaries)
    report = {'schema': 'DL1018_NCMD_LOCAL_FEEDBACK_SENSITIVITY_V1', 'status': 'PASS_OFFLINE_LOCAL_MAP_DIAGNOSTIC',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': {'new_training': False, 'optimizer_updates': 0, 'new_Plant_calls': 0, 'TEST_read': False,
                        'true_inertia_mass_wind_fields_read': False},
              'definition': {'held_fixed': 'current 13-D feature and its own trajectory hidden-before state',
                             'perturbed_features': 'attitude-error x/y/z and body-rate x/y/z',
                             'finite_difference': 'central difference, +/-1e-4 normalized feature standard deviations',
                             'issued_torque_slope': 'd(tau_nominal - J0*beta*NN_output)/d(body_rate)',
                             'boundary': 'local command-map sensitivity only; does not include Plant dynamics or prove closed-loop stability'},
              'identity': {'feature_npz_sha256': sha(FEATURES), 'model_sha256': sha(MODEL_PATH),
                           'locked_cfg_sha256': sha(CFG_PATH), 'J0_source': 'fixed locked nominal J0 only'},
              'raws': raw_ids,
              'outputs': {'event_csv': str(event_csv), 'event_csv_sha256': sha(event_csv),
                          'event_rows': len(event_rows), 'group_csv': str(summary_csv),
                          'group_csv_sha256': sha(summary_csv), 'group_rows': len(summaries),
                          'hidden_swap_csv': str(swap_csv), 'hidden_swap_csv_sha256': sha(swap_csv),
                          'hidden_swap_rows': len(hidden_swap_rows),
                          'hidden_swap_summary_csv': str(swap_summary_csv),
                          'hidden_swap_summary_csv_sha256': sha(swap_summary_csv),
                          'hidden_swap_summary_rows': len(swap_summaries)},
              'script_sha256': sha(Path(__file__))}
    report_path = OUT / 'LOCAL_FEEDBACK_SENSITIVITY_v1.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'event_rows': len(event_rows), 'group_rows': len(summaries),
                      'event_csv_sha256': sha(event_csv), 'group_csv_sha256': sha(summary_csv),
                      'json_sha256': sha(report_path)}, indent=2))


if __name__ == '__main__':
    main()
