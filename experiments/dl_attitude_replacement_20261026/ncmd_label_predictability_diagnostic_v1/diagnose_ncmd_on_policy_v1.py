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
TARGETS = BASE / 'nominal_command_target_data_v1/nominal_command_target_v1.npz'
TARGET_MANIFEST = BASE / 'nominal_command_target_data_v1/MANIFEST_v1.json'
CFG_PATH = STUDY / 'LOCKED_CFG.json'
MODEL_PATH = BASE / 'gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
RUNS = STUDY / 'runs'
OUT = Path(__file__).resolve().parent
SCENES = (
    'DL1018_VAL_T1_C08_W15', 'DL1018_VAL_T2_C05_W15', 'DL1018_VAL_T3_C02_W15',
    'DL1018_VAL_T1_C05_W12', 'DL1018_VAL_T2_C02_W12', 'DL1018_VAL_T3_C00_W13',
)
AXES = ('roll', 'pitch', 'yaw')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mat_model(path: Path) -> dict[str, np.ndarray]:
    r = loadmat(path)
    vec = ('input_mean', 'input_std', 'target_rms', 'gru_bias_ih', 'gru_bias_hh', 'head_bias')
    names = (*vec, 'gru_weight_ih', 'gru_weight_hh', 'head_weight')
    return {k: np.asarray(r[k]).reshape(-1) if k in vec else np.asarray(r[k]) for k in names}


def forward(raw_x: np.ndarray, m: dict[str, np.ndarray]) -> np.ndarray:
    x = np.asarray(raw_x, dtype=np.float64)
    h = np.zeros(32, dtype=np.float64)
    y = np.empty((len(x), 3), dtype=np.float64)
    for i, row in enumerate(x):
        gi = m['gru_weight_ih'] @ ((row - m['input_mean']) / m['input_std']) + m['gru_bias_ih']
        gh = m['gru_weight_hh'] @ h + m['gru_bias_hh']
        r = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
        z = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
        n = np.tanh(gi[64:96] + r * gh[64:96])
        h = (1.0 - z) * n + z * h
        y[i] = (m['head_weight'] @ h + m['head_bias']) * m['target_rms']
    return y


def tag(scene: str) -> dict[str, str]:
    m = re.fullmatch(r'DL1018_VAL_(T[123])_(C\d{2})_(W\d{2})', scene)
    if not m:
        raise ValueError(scene)
    task, course, wind = m.groups()
    wind_group = 'W15_NO_WIND' if wind == 'W15' else ('HF_W09_W14' if 9 <= int(wind[1:]) <= 14 else 'W00_W08')
    return {'task': task, 'course': course, 'wind': wind, 'wind_group': wind_group}


def scene_groups(scene: str) -> tuple[str, ...]:
    m = tag(scene)
    gs = ['ALL6', m['task'], m['wind_group'], f"WIND_{m['wind']}"]
    if scene == 'DL1018_VAL_T2_C05_W15':
        gs.append('T2_C05_W15')
    return tuple(gs)


def scalar(group: h5py.Group, key: str) -> float:
    return float(np.asarray(group[key][()]).reshape(-1)[0])


def read_ncmd_raw(path: Path, J0: np.ndarray, dmax: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    # Only state gyro rows, requested generalized torque rows, event flags/trace outputs,
    # and timeline are selected. No realized command, wind, mass, or Plant parameter is read.
    with h5py.File(path, 'r') as f:
        log = f['log']
        omega = np.asarray(log['state'][9:12, :], dtype=np.float64)
        requested_torque = np.asarray(log['requested_generalized'][1:4, :], dtype=np.float64)
        times = np.asarray(log['time'][0, :], dtype=np.float64)
        event_flag = np.asarray(log['attitude_event_flag'][0, :], dtype=np.uint8).astype(bool)
        trace_refs = log['gru_stream_attitude_trace'][0, :]
        e_starts = np.arange(10, 20000, 10, dtype=np.int64)
        assert omega.shape == (3, 20001) and requested_torque.shape == (3, 20000)
        assert times.shape == (20001,) and np.array_equal(np.flatnonzero(event_flag), e_starts)
        assert np.allclose(np.diff(times), 0.001, rtol=0, atol=2e-12)
        # The target is the average 1 ms nominal command-port residual over the next 10 transitions.
        Jomega = J0 @ omega[:, :-1]
        gyro_coupling = np.cross(omega[:, :-1].T, Jomega.T).T
        one_ms = np.linalg.solve(J0, gyro_coupling - requested_torque)
        target = np.empty((len(e_starts), 3), dtype=np.float64)
        outputs = np.empty_like(target)
        output_clip_check = 0.0
        for j, e in enumerate(e_starts):
            target[j] = ((omega[:, e + 10] - omega[:, e]) / (times[e + 10] - times[e])
                         + np.mean(one_ms[:, e:e + 10], axis=1))
            node = f[trace_refs[e]]
            assert int(scalar(node, 'sample_index')) == e + 1
            assert abs(scalar(node, 'time_s') - times[e]) < 2e-12
            outputs[j] = np.asarray(node['raw_residual_rad_s2'][()], dtype=np.float64).reshape(3)
            logged_clip = np.asarray(node['clipped_residual_rad_s2'][()], dtype=np.float64).reshape(3)
            output_clip_check = max(output_clip_check, float(np.max(np.abs(logged_clip - np.clip(outputs[j], -dmax, dmax)))) )
    return outputs, target, {'events': len(e_starts), 'output_clip_replay_max_abs': output_clip_check,
                             'interval_first_zero_based': 10, 'interval_last_zero_based': 19990,
                             'raw_sha256': sha(path)}


def main() -> None:
    cfg = json.loads(CFG_PATH.read_text(encoding='utf-8-sig'))
    J0 = np.asarray(cfg['J0_kgm2'], dtype=np.float64)
    dmax = np.asarray(cfg['dmax'], dtype=np.float64)
    assert np.array_equal(J0, np.asarray([[0.003257553333333334, -2.168404344971009e-19, 0.0],
                                         [-2.168404344971009e-19, 0.0032575533333333334, 0.0],
                                         [0.0, 0.0, 0.006360648333333333]]))
    model = mat_model(MODEL_PATH)
    features = np.load(FEATURES, allow_pickle=False)
    targets = np.load(TARGETS, allow_pickle=False)
    train_ids = np.asarray(features['c5_train_scene_ids']).astype(str)
    val_ids = np.asarray(features['c5_val_scene_ids']).astype(str)
    ncmd_train_ids = np.asarray(targets['c5_train_scene_ids']).astype(str)
    ncmd_val_ids = np.asarray(targets['c5_val_scene_ids']).astype(str)
    id_to_c5: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ids, X, Y in (
        (train_ids, np.asarray(features['c5_train_x'], dtype=np.float64),
         np.asarray(targets['c5_train_y_clipped_float32'], dtype=np.float64)),
        (val_ids, np.asarray(features['c5_val_x'], dtype=np.float64),
         np.asarray(targets['c5_val_y_clipped_float32'], dtype=np.float64)),
    ):
        assert X.shape == (len(ids), 1999, 13) and Y.shape == (len(ids), 1999, 3)
        for i, scene_id in enumerate(ids):
            id_to_c5[scene_id] = (X[i], Y[i])
    assert np.array_equal(train_ids, ncmd_train_ids) and np.array_equal(val_ids, ncmd_val_ids)

    scene_rows: list[dict] = []
    event_rows: list[dict] = []
    raw_identity: dict[str, dict] = {}
    lag_by_scene: list[tuple[str, np.ndarray, np.ndarray]] = []
    for scene in SCENES:
        run_dir = RUNS / scene
        raw_path = run_dir / 'raw_run.mat'
        status = json.loads((run_dir / 'run_status.json').read_text(encoding='utf-8-sig'))
        replay = json.loads((STUDY / 'audits' / f'{scene}_GRU_STREAM_RAW_AUDIT.json').read_text(encoding='utf-8-sig'))
        raw_sha = sha(raw_path)
        assert status['state'] == 'COMPLETED' and status['scene_id'] == scene and status['raw_sha256'] == raw_sha
        assert replay['status'] == 'PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY' and replay['candidate_raw_sha256'] == raw_sha
        assert replay['model_sha256'] == sha(MODEL_PATH) and replay['event_count'] == 1999
        on_pred, yraw, raw_meta = read_ncmd_raw(raw_path, J0, dmax)
        assert raw_meta['events'] == 1999 and raw_meta['output_clip_replay_max_abs'] < 1e-12
        on_clip = np.clip(yraw, -dmax, dmax)
        # Re-run the same frozen model on the logged 13-D legal event features for parity.
        with h5py.File(raw_path, 'r') as f:
            log = f['log']
            event_indices = np.flatnonzero(np.asarray(log['attitude_event_flag'][0, :], dtype=np.uint8))
            event_x = np.empty((1999, 13), dtype=np.float64)
            for j, event_i in enumerate(event_indices):
                node = f[log['gru_stream_attitude_trace'][0, event_i]]
                event_x[j] = np.asarray(node['feature_raw'][()], dtype=np.float64).reshape(13)
        replay_pred = forward(event_x, model)
        model_replay_error = float(np.max(np.abs(replay_pred - on_pred)))
        assert model_replay_error < 1e-8, model_replay_error
        Xhist, Yhist = id_to_c5[scene]
        off_pred = forward(Xhist, model)
        lag_by_scene.append((scene, on_pred, on_clip))
        raw_identity[scene] = {**raw_meta, 'status_path': str(run_dir / 'run_status.json'),
                               'audit_path': str(STUDY / 'audits' / f'{scene}_GRU_STREAM_RAW_AUDIT.json'),
                               'model_replay_max_abs': model_replay_error}
        for group in scene_groups(scene):
            for axis, axis_name in enumerate(AXES):
                for condition, pred, truth, clipped_pred in (
                    ('NCMD_ON_POLICY_RAW_OUTPUT_VS_OWN_FORWARD10MS_RAW', on_pred, yraw, np.clip(on_pred, -dmax, dmax)),
                    ('NCMD_ON_POLICY_CLIPPED_OUTPUT_VS_OWN_FORWARD10MS_CLIPPED', np.clip(on_pred, -dmax, dmax), on_clip, np.clip(on_pred, -dmax, dmax)),
                    ('SAME_NCMD_MODEL_ON_C5_HISTORY_VS_C5_NCMD_TARGET', off_pred, Yhist, np.clip(off_pred, -dmax, dmax)),
                ):
                    err = pred[:, axis] - truth[:, axis]
                    scene_rows.append({'scene_id': scene, 'group': group, 'condition': condition, 'axis': axis_name,
                                       'n': len(err), 'bias_rad_s2': float(np.mean(err)),
                                       'rmse_rad_s2': float(np.sqrt(np.mean(err * err))),
                                       'target_rms_rad_s2': float(np.sqrt(np.mean(truth[:, axis] ** 2))),
                                       'output_clip_rate': float(np.mean(np.abs(on_pred[:, axis]) > dmax[axis])) if 'ON_POLICY' in condition else '',
                                       'label_clip_rate': float(np.mean(np.abs(yraw[:, axis]) > dmax[axis])) if 'ON_POLICY' in condition else ''})
        for j, e in enumerate(range(10, 20000, 10)):
            for a, axis_name in enumerate(AXES):
                event_rows.append({'scene_id': scene, 'event_1based': j + 1, 'interval_start_zero_based': e,
                                   'axis': axis_name, 'raw_target_rad_s2': yraw[j, a],
                                   'clipped_target_rad_s2': on_clip[j, a], 'model_output_raw_rad_s2': on_pred[j, a],
                                   'model_output_clipped_rad_s2': np.clip(on_pred[j, a], -dmax[a], dmax[a]),
                                   'abs_target_exceeded_dmax': bool(abs(yraw[j, a]) > dmax[a])})

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    scene_csv = OUT / 'onpolicy_scene_metrics_v1.csv'
    event_csv = OUT / 'onpolicy_event_values_v1.csv'
    write_csv(scene_csv, scene_rows); write_csv(event_csv, event_rows)
    # Pooled metrics and scene-macro RMSE are computed from scene-level summary rows.
    aggregate: list[dict] = []
    keys = sorted({(r['group'], r['condition'], r['axis']) for r in scene_rows})
    for group, condition, axis in keys:
        rr = [r for r in scene_rows if (r['group'], r['condition'], r['axis']) == (group, condition, axis)]
        nall = sum(int(r['n']) for r in rr)
        pooled_bias = sum(int(r['n']) * float(r['bias_rad_s2']) for r in rr) / nall
        pooled_rmse = np.sqrt(sum(int(r['n']) * float(r['rmse_rad_s2']) ** 2 for r in rr) / nall)
        aggregate.append({'group': group, 'condition': condition, 'axis': axis, 'scene_count': len(rr),
                          'event_count': nall, 'pooled_bias_rad_s2': pooled_bias,
                          'pooled_rmse_rad_s2': float(pooled_rmse),
                          'scenario_macro_rmse_rad_s2': float(np.mean([float(r['rmse_rad_s2']) for r in rr])),
                          'mean_target_rms_rad_s2': float(np.mean([float(r['target_rms_rad_s2']) for r in rr])),
                          'mean_output_clip_rate': float(np.mean([float(r['output_clip_rate']) for r in rr if r['output_clip_rate'] != ''])) if any(r['output_clip_rate'] != '' for r in rr) else '',
                          'mean_label_clip_rate': float(np.mean([float(r['label_clip_rate']) for r in rr if r['label_clip_rate'] != ''])) if any(r['label_clip_rate'] != '' for r in rr) else ''})
    aggregate_csv = OUT / 'onpolicy_group_metrics_v1.csv'
    write_csv(aggregate_csv, aggregate)

    lag_rows: list[dict] = []
    for scene, pred, target in lag_by_scene:
        for offset in (-2, -1, 0, 1, 2):
            if offset < 0:
                p, y = pred[-offset:], target[:1999 + offset]
            elif offset > 0:
                p, y = pred[:-offset], target[offset:]
            else:
                p, y = pred, target
            for axis, axis_name in enumerate(AXES):
                error = p[:, axis] - y[:, axis]
                lag_rows.append({'scene_id': scene, 'offset_events': offset, 'axis': axis_name,
                                 'n': len(error), 'bias_rad_s2': float(np.mean(error)),
                                 'rmse_rad_s2': float(np.sqrt(np.mean(error * error)))})
    lag_csv = OUT / 'onpolicy_event_lag_scan_v1.csv'
    write_csv(lag_csv, lag_rows)

    report = {
        'schema': 'DL1018_NCMD_ON_POLICY_LABEL_FIT_V1', 'status': 'PASS_OFFLINE_SIX_RAW_DIAGNOSTIC',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {'new_training': False, 'optimizer_updates': 0, 'new_Plant_calls': 0, 'TEST_read': False,
                  'no_true_inertia_or_mass_or_wind_fields_read': True,
                  'raw_source_note': 'six already completed NCMD closed-loop raw files; this script made no Plant call'},
        'target_definition': {'equation': 'Rcmd[e]=(omega[e+10]-omega[e])/(t[e+10]-t[e])+mean_i solve(J0,cross(omega[i],J0*omega[i])-tau_req[i]); i=e..e+9',
                              'e_zero_based': '10,20,...,19990', 'events_per_scene': 1999,
                              'requested_torque_source': 'raw log requested_generalized rows 2:4 MATLAB / rows 1:4 HDF5',
                              'J0_source': str(CFG_PATH), 'J0_sha256': sha(CFG_PATH),
                              'output_comparison': 'logged raw residual and exact DMAX-clipped residual vs own forward 10ms target'},
        'data_identity': {'feature_npz_sha256': sha(FEATURES), 'ncmd_target_npz_sha256': sha(TARGETS),
                          'target_manifest_sha256': sha(TARGET_MANIFEST), 'model_path': str(MODEL_PATH),
                          'model_sha256': sha(MODEL_PATH), 'locked_dmax': dmax.tolist(),
                          'c5_comparison': 'same NCMD model re-inferred on original 13-D C5 X; target is stored clipped NCMD label'},
        'raws': raw_identity,
        'metrics': {'scene_csv': str(scene_csv), 'scene_csv_sha256': sha(scene_csv),
                    'group_csv': str(aggregate_csv), 'group_csv_sha256': sha(aggregate_csv),
                    'event_csv': str(event_csv), 'event_csv_sha256': sha(event_csv),
                    'lag_csv': str(lag_csv), 'lag_csv_sha256': sha(lag_csv),
                    'scene_metric_rows': len(scene_rows), 'event_axis_rows': len(event_rows)},
        'interpretation_boundary': 'Historical C5 input and NCMD self-closed-loop trajectories are different states. On/off-policy fit difference is descriptive, not a causal estimate. The 72-scene C5 cohort is development material, not independent validation.',
        'script_sha256': sha(Path(__file__)),
    }
    out = OUT / 'ON_POLICY_LABEL_FIT_DIAGNOSTIC_v1.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'scene_metric_rows': len(scene_rows),
                      'event_axis_rows': len(event_rows), 'metrics': report['metrics']}, indent=2))


if __name__ == '__main__':
    main()
