from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
from typing import Any
import h5py
import numpy as np
from scipy.io import loadmat

ROOT = Path.cwd()
OUT = ROOT / 'reports/gru_stream_target_fit_diagnosis_20261027_v1'
BASE = ROOT / 'experiments/dl_attitude_replacement_20261026'
C5_DIR = BASE / 'mlp15_c5_teacher_redistill_v1'
C5_MANIFEST = C5_DIR / 'DATASET_MANIFEST_v1.json'
C5_DATASET = C5_DIR / 'matched_teacher_data_v1.npz'
OLD_DIAG = BASE / 'attitude_target_semantics_diagnosis_20261027_v1'
OLD_SCRIPT = OLD_DIAG / 'diagnose_target_semantics.py'
OLD_INPUTS = OLD_DIAG / 'INPUTS.json'
OLD_METRICS = OLD_DIAG / 'METRICS.json'
CAUSAL_REPORT = BASE / 'attitude_head_mechanism_v1/CAUSAL_NOMINAL_TORQUE_RESIDUAL.json'
GRU_DIR = BASE / 'gru_stream_dev_v1'
GRU_MODEL = BASE / 'gru_stream_c5_teacher_v1/runs/GRU32_STREAM72_S2026102001/gru_stream_c5_teacher_weights_v1.mat'
GRU_TRAIN_PARITY = BASE / 'gru_stream_c5_teacher_v1/runs/GRU32_STREAM72_S2026102001/stream_parity_vector_v1.mat'
ROOT_METRICS = GRU_DIR / 'ROOT_SIX_PYTHON_METRICS_v1.json'
ROOT_DECISION = GRU_DIR / 'ROOT_SIX_SCENE_DECISION_v1.json'
RELEASE = GRU_DIR / 'RELEASE.json'
DT = 0.001
BETA_RISE = 2.2
DMAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
AXES = ('roll', 'pitch', 'yaw')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def mat_vector(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=np.float64).reshape(-1)


def read2(group: h5py.Group, name: str) -> np.ndarray:
    a = np.asarray(group[name], dtype=np.float64)
    if a.ndim != 2:
        raise ValueError(f'{name} expected rank-2, got {a.shape}')
    return a.T


def read1(group: h5py.Group, name: str) -> np.ndarray:
    return np.asarray(group[name], dtype=np.float64).reshape(-1)


def gru_stream(features: np.ndarray, model: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frozen PyTorch GRU reset/update/new order; scene-local hidden starts at zero."""
    mean = mat_vector(model['input_mean'])
    std = mat_vector(model['input_std'])
    target_rms = mat_vector(model['target_rms'])
    wih = np.asarray(model['gru_weight_ih'], dtype=np.float64)
    whh = np.asarray(model['gru_weight_hh'], dtype=np.float64)
    bih = mat_vector(model['gru_bias_ih'])
    bhh = mat_vector(model['gru_bias_hh'])
    head_w = np.asarray(model['head_weight'], dtype=np.float64)
    head_b = mat_vector(model['head_bias'])
    assert features.ndim == 2 and features.shape[1] == 13 and mean.shape == std.shape == (13,)
    assert wih.shape == (96, 13) and whh.shape == (96, 32)
    assert bih.shape == bhh.shape == (96,) and head_w.shape == (3, 32) and head_b.shape == (3,)
    assert target_rms.shape == (3,) and np.all(std > 0) and np.all(target_rms > 0)
    hidden = np.zeros(32, dtype=np.float64)
    raw = np.empty((len(features), 3), dtype=np.float64)
    hidden_all = np.empty((len(features), 32), dtype=np.float64)
    for i, feature in enumerate(features):
        x = (np.asarray(feature, dtype=np.float64) - mean) / std
        gi = wih @ x + bih
        gh = whh @ hidden + bhh
        reset = 1.0 / (1.0 + np.exp(-(gi[:32] + gh[:32])))
        update = 1.0 / (1.0 + np.exp(-(gi[32:64] + gh[32:64])))
        candidate = np.tanh(gi[64:96] + reset * gh[64:96])
        hidden = (1.0 - update) * candidate + update * hidden
        raw[i] = (head_w @ hidden + head_b) * target_rms
        hidden_all[i] = hidden
    return raw, np.clip(raw, -DMAX, DMAX), hidden_all


def collect_trace_refs(raw: h5py.File, event_indices: np.ndarray) -> dict[str, np.ndarray]:
    trace = raw['log/gru_stream_attitude_trace']
    names = ('sample_index', 'time_s', 'beta', 'raw_residual_rad_s2',
             'clipped_residual_rad_s2', 'hidden_before', 'hidden_after', 'event_count')
    result: dict[str, list[np.ndarray]] = {name: [] for name in names}
    result['feature_raw'] = []
    for event_idx in event_indices:
        obj = raw[trace[0, int(event_idx)]]
        if not isinstance(obj, h5py.Group):
            raise ValueError(f'missing GRU trace at zero-based sample {event_idx}')
        for name in names:
            result[name].append(np.asarray(obj[name][()], dtype=np.float64).reshape(-1))
        result['feature_raw'].append(np.asarray(obj['feature_raw'][()], dtype=np.float64).reshape(-1))
    return {name: np.vstack(rows) if len(rows[0]) > 1 else np.asarray(rows).reshape(-1)
            for name, rows in result.items()}


def load_run(path: Path) -> dict[str, Any]:
    with h5py.File(path, 'r') as raw:
        log = raw['log']
        state = read2(log, 'state')
        time = read1(log, 'time')
        filtered_ref = read2(log, 'filtered_attitude_reference')
        nominal_torque = read2(log, 'attitude_bs_nominal_torque_Nm')
        requested = read2(log, 'requested_generalized')
        # MATLAB columns 2:4 correspond to Python row slice 1:4.
        issued_torque = np.asarray(log['requested_generalized'], dtype=np.float64)[1:4, :].T
        command = read2(raw['scene/arms'], 'command')
        event_flags = np.asarray(log['attitude_event_flag']).reshape(-1).astype(bool)
        event_indices = np.flatnonzero(event_flags)
        teacher_raw_all = read2(log, 'rbf_output_raw')
        teacher_unclipped_all = read2(log, 'rbf_output_unclipped')
        teacher_applied_all = read2(log, 'attitude_rbf_estimate_acceleration_rads2')
        rbf_applied_torque = read2(log, 'attitude_rbf_compensation_torque_Nm')
        applied_torque = read2(log, 'attitude_compensation_applied_torque_Nm')
        if 'gru_stream_attitude_trace' in log:
            trace = collect_trace_refs(raw, event_indices)
        else:
            trace = None
    return {
        'state': state, 'time': time, 'filtered_ref': filtered_ref,
        'nominal_torque': nominal_torque, 'issued_torque': issued_torque,
        'command': command, 'event_indices': event_indices,
        'teacher_raw_all': teacher_raw_all, 'teacher_unclipped_all': teacher_unclipped_all,
        'teacher_applied_all': teacher_applied_all, 'rbf_applied_torque': rbf_applied_torque,
        'applied_torque': applied_torque, 'trace': trace,
    }


def make_features(run: dict[str, Any], events: np.ndarray) -> np.ndarray:
    state = run['state']; ref = run['filtered_ref']; nominal = run['nominal_torque']; command = run['command']
    error = np.arctan2(np.sin(ref[events] - state[events, 6:9]),
                       np.cos(ref[events] - state[events, 6:9]))
    # Runtime feature order: wrapped Euler error, body omega, nominal BS torque, arm command.
    return np.concatenate((error, state[events, 9:12], nominal[events], command[events]), axis=1)


def interval_residual(run: dict[str, Any], event_indices: np.ndarray, j0: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """10 ms interval-average nominal residual ending at each attitude event."""
    omega = run['state'][:, 9:12]
    time = run['time']
    issued = run['issued_torque']
    observed = np.empty((len(event_indices), 3), dtype=np.float64)
    for j, k0 in enumerate(event_indices):
        k = int(k0)
        p = max(0, k - 10)
        span = time[k] - time[p]
        if p >= len(issued) or k > len(issued) or span <= 0:
            raise ValueError(f'invalid interval p={p}, k={k}, span={span}')
        gyro = np.cross(omega[p:k], omega[p:k] * j0[None, :], axis=1)
        observed[j] = ((omega[k] - omega[p]) / span +
                       np.mean((gyro - issued[p:k]) / j0[None, :], axis=0))
    return observed, time[event_indices], np.minimum((event_indices + 1) * DT / BETA_RISE, 1.0)


def metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    err = np.asarray(pred, dtype=np.float64) - np.asarray(target, dtype=np.float64)
    return {
        'valid_n': int(err.shape[0]),
        'rmse': np.sqrt(np.mean(err ** 2, axis=0)),
        'mean_bias_prediction_minus_target': np.mean(err, axis=0),
        'target_rms': np.sqrt(np.mean(np.asarray(target, dtype=np.float64) ** 2, axis=0)),
        'prediction_rms': np.sqrt(np.mean(np.asarray(pred, dtype=np.float64) ** 2, axis=0)),
    }


def categories_a(time: np.ndarray, beta: np.ndarray) -> dict[str, np.ndarray]:
    return {
        'all_events': np.ones(len(time), dtype=bool),
        'beta_immature_events': beta < 1.0,
        'beta_mature_events': beta >= 1.0,
        'early_first_5s_events': time < 5.0,
        'late_last_5s_events': time >= 15.0,
        'beta_mature_early_first_5s_events': (beta >= 1.0) & (time < 5.0),
        'beta_mature_late_last_5s_events': (beta >= 1.0) & (time >= 15.0),
    }


def categories_intervals(time_start: np.ndarray, beta_start: np.ndarray) -> dict[str, np.ndarray]:
    return {
        'all_start_aligned_intervals': np.ones(len(time_start), dtype=bool),
        'beta_immature_start_intervals': beta_start < 1.0,
        'beta_mature_start_intervals': beta_start >= 1.0,
        'early_first_5s_start_intervals': time_start < 5.0,
        'late_last_5s_start_intervals': time_start >= 15.0,
        'beta_mature_early_first_5s_start_intervals': (beta_start >= 1.0) & (time_start < 5.0),
        'beta_mature_late_last_5s_start_intervals': (beta_start >= 1.0) & (time_start >= 15.0),
    }


def safe_record(rows: list[dict[str, Any]], diagnostic: str, scene: str, cohort: str,
                period: str, comparison: str, values: dict[str, Any]) -> None:
    for axis_i, axis in enumerate(AXES):
        rows.append({
            'diagnostic': diagnostic, 'scene_id': scene, 'cohort': cohort,
            'period': period, 'comparison': comparison, 'axis': axis,
            'valid_n': values['valid_n'],
            'rmse_rad_s2': float(values['rmse'][axis_i]),
            'mean_bias_prediction_minus_target_rad_s2': float(values['mean_bias_prediction_minus_target'][axis_i]),
            'target_rms_rad_s2': float(values['target_rms'][axis_i]),
            'prediction_rms_rad_s2': float(values['prediction_rms'][axis_i]),
        })


def main() -> None:
    existing = [p.name for p in OUT.iterdir()] if OUT.exists() else []
    unexpected = [name for name in existing if name != Path(__file__).name]
    if unexpected:
        raise FileExistsError(f'output artifacts already exist; refusing overwrite: {unexpected}')
    OUT.mkdir(parents=True, exist_ok=True)
    c5_manifest = json.loads(C5_MANIFEST.read_text(encoding='utf-8'))
    root_metrics = json.loads(ROOT_METRICS.read_text(encoding='utf-8'))
    root_decision = json.loads(ROOT_DECISION.read_text(encoding='utf-8'))
    release = json.loads(RELEASE.read_text(encoding='utf-8'))
    causal = json.loads(CAUSAL_REPORT.read_text(encoding='utf-8'))
    old_metrics = json.loads(OLD_METRICS.read_text(encoding='utf-8'))
    ds = np.load(C5_DATASET, allow_pickle=False)
    model_mat = loadmat(GRU_MODEL)
    model = {key: model_mat[key] for key in (
        'input_mean','input_std','target_rms','gru_weight_ih','gru_weight_hh',
        'gru_bias_ih','gru_bias_hh','head_weight','head_bias')}
    j0 = np.asarray(c5_manifest['fixed_J0_reference']['diagonal_kg_m2'], dtype=np.float64)
    assert j0.shape == (3,) and np.all(j0 > 0)
    assert np.max(np.abs(j0 - np.diag(np.asarray(causal['fixed_J0_kgm2'])))) < 1e-15
    assert release['status'] == 'CLOSED_SIX_SCENE_PERFORMANCE_FAIL'
    assert release['Plant_calls'] == 6 and release['TEST_read'] is False
    assert root_decision['status'] == 'SCREEN_FAIL_NO_DEV72_OR_TEST_EXPANSION'
    assert root_decision['TEST_read'] is False
    assert causal['Plant_calls'] == 0 and causal['TEST_read'] is False
    assert old_metrics['inputs']['scope']['TEST_read'] is False
    assert sha256(GRU_MODEL) == '963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021'
    assert sha256(C5_DATASET) == c5_manifest['dataset_sha256']
    assert sha256(OLD_SCRIPT) == json.loads(OLD_INPUTS.read_text(encoding='utf-8'))['files_sha256'][str(OLD_SCRIPT)]

    scene_ids = [row['scene_id'] for row in root_metrics['rows']]
    c5_rows = {row['scene_id']: row for row in c5_manifest['rows'] if row.get('split') == 'C5_VAL48'}
    causal_rows = {row['scene_id']: row for row in causal['rows']}
    val_ids = [s.decode() if isinstance(s, bytes) else str(s) for s in ds['c5_val_scene_ids'].tolist()]
    gru_parity_path = BASE / 'gru_stream_c5_teacher_v1/runs/GRU32_STREAM72_S2026102001/stream_parity_vector_v1.mat'
    parity = loadmat(GRU_TRAIN_PARITY)
    input_mean = mat_vector(model['input_mean']); input_std = mat_vector(model['input_std'])
    assert np.array_equal(input_mean, mat_vector(parity['input_mean']))
    assert np.array_equal(input_std, mat_vector(parity['input_std']))
    assert len(scene_ids) == 6 and set(scene_ids).issubset(set(c5_rows)) and set(scene_ids).issubset(set(val_ids))

    loaded: dict[str, dict[str, Any]] = {}
    data: dict[str, dict[str, np.ndarray]] = {}
    input_hashes: dict[str, str] = {}
    validation_errors: dict[str, dict[str, float]] = {}
    scene_summary: dict[str, Any] = {}
    metric_rows: list[dict[str, Any]] = []
    c5_event_a: dict[str, dict[str, np.ndarray]] = {}
    c5_interval_b: dict[str, dict[str, np.ndarray]] = {}
    gru_interval_c: dict[str, dict[str, np.ndarray]] = {}
    residual_audit_error: dict[str, float] = {}

    for scene_id in scene_ids:
        c5_rec = c5_rows[scene_id]
        c5_raw = Path(c5_rec['raw_path'])
        c5_hash = sha256(c5_raw)
        assert c5_hash == c5_rec['raw_sha256'] == causal_rows[scene_id]['source_raw_sha256']
        c5 = load_run(c5_raw)
        events = c5['event_indices']
        expected = np.arange(10, 20_000, 10, dtype=np.int64)
        assert np.array_equal(events, expected) and len(events) == 1999
        feat = make_features(c5, events)
        npz_index = val_ids.index(scene_id)
        npz_feat = np.asarray(ds['c5_val_x'][npz_index], dtype=np.float64)
        npz_teacher = np.asarray(ds['c5_val_y'][npz_index], dtype=np.float64)
        teacher = c5['teacher_raw_all'][events]
        feature_error = float(np.max(np.abs(feat - npz_feat)))
        teacher_error = float(np.max(np.abs(teacher - npz_teacher)))
        clip_error = float(np.max(np.abs(teacher - np.clip(c5['teacher_unclipped_all'][events], -DMAX, DMAX))))
        beta = np.minimum((events + 1) * DT / BETA_RISE, 1.0)
        beta_error = float(np.max(np.abs(c5['teacher_applied_all'][events] - beta[:, None] * teacher)))
        issued_torque_error = float(np.max(np.abs(c5['applied_torque'] - c5['rbf_applied_torque'])))
        assert feature_error < 2e-6 and teacher_error < 2e-6 and clip_error < 1e-12
        assert beta_error < 1e-10 and issued_torque_error == 0.0
        gru_pre, gru_post, gru_hidden = gru_stream(feat, model)
        observed_c5, event_time, beta_logged = interval_residual(c5, events, j0)
        assert np.max(np.abs(beta - beta_logged)) == 0.0
        # Match the already-validated causal residual audit on mature C5 samples.
        mature_event = event_time >= 3.0
        prior = causal_rows[scene_id]
        rmse_check = np.max(np.abs(np.sqrt(np.mean(observed_c5[mature_event] ** 2, axis=0)) -
                                    np.asarray(prior['mature_observed_residual_RMS_rad_s2'])))
        residual_audit_error[scene_id] = float(rmse_check)
        assert rmse_check < 1e-7
        # A: same C5 recorded event states, h=0 at scene start, output compared to post-DMAX/pre-beta teacher.
        a_data = {
            'time': event_time, 'beta': beta, 'gru_post': gru_post,
            'gru_pre': gru_pre, 'teacher': teacher,
        }
        c5_event_a[scene_id] = a_data
        for period, mask in categories_a(event_time, beta).items():
            for comparison, pred, target in (
                ('GRU_post_DMAX_vs_RBF_post_DMAX_pre_beta', gru_post, teacher),
                ('GRU_pre_DMAX_vs_RBF_post_DMAX_pre_beta_diagnostic', gru_pre, teacher),
            ):
                safe_record(metric_rows, 'A_C5_same_state_teacher_fit', scene_id,
                            'scene', period, comparison, metrics(pred[mask], target[mask]))

        # B: same C5 trace; R_j is paired with the model/teacher output at the preceding event j-1.
        c5_interval_b[scene_id] = {
            'time_start': event_time[:-1], 'time_end': event_time[1:],
            'beta_start': beta[:-1], 'residual_end': observed_c5[1:],
            'gru_start': gru_post[:-1], 'teacher_start': teacher[:-1],
        }
        c5_interval_b[scene_id]['categories'] = categories_intervals(event_time[:-1], beta[:-1])
        for period, mask in c5_interval_b[scene_id]['categories'].items():
            for comparison, pred in (
                ('GRU_post_DMAX_at_interval_start_vs_R_nominal_10ms_end', gru_post[:-1],),
                ('RBF_teacher_post_DMAX_pre_beta_at_interval_start_vs_R_nominal_10ms_end', teacher[:-1],),
            ):
                safe_record(metric_rows, 'B_C5_same_state_approx_residual', scene_id,
                            'scene', period, comparison, metrics(pred[mask], observed_c5[1:][mask]))

        # C: actual GRU closed-loop raw: use logged applied post-DMAX output at interval start.
        gru_raw = GRU_DIR / 'runs' / scene_id / 'raw_run.mat'
        run_status = json.loads((GRU_DIR / 'runs' / scene_id / 'run_status.json').read_text(encoding='utf-8'))
        audit_path = GRU_DIR / 'audits' / f'{scene_id}_GRU_STREAM_RAW_AUDIT.json'
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        gru_hash = sha256(gru_raw)
        assert run_status['state'] == 'COMPLETED' and run_status['Plant_calls'] == 1
        assert audit['status'] == 'PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY'
        assert gru_hash == run_status['raw_sha256'] == audit['candidate_raw_sha256']
        actual = load_run(gru_raw)
        gru_events = actual['event_indices']
        assert np.array_equal(gru_events, events)
        trace = actual['trace']
        assert trace is not None and trace['clipped_residual_rad_s2'].shape == (1999, 3)
        trace_feature_error = float(np.max(np.abs(trace['feature_raw'].reshape(1999, 13) - make_features(actual, gru_events))))
        trace_clip_error = float(np.max(np.abs(trace['clipped_residual_rad_s2'].reshape(1999, 3) -
                                           np.clip(trace['raw_residual_rad_s2'].reshape(1999, 3), -DMAX, DMAX))))
        actual_pre, actual_post_recomputed, actual_hidden = gru_stream(make_features(actual, gru_events), model)
        replay_output_error = float(np.max(np.abs(actual_pre - trace['raw_residual_rad_s2'].reshape(1999, 3))))
        replay_clip_error = float(np.max(np.abs(actual_post_recomputed - trace['clipped_residual_rad_s2'].reshape(1999, 3))))
        assert trace_feature_error < 1e-9 and trace_clip_error < 1e-12
        assert replay_output_error < 1e-8 and replay_clip_error < 1e-12
        observed_gru, gru_time, gru_beta = interval_residual(actual, gru_events, j0)
        # The trace beta is per event; compare it to the same 1-based sample clock used by runtime.
        assert np.max(np.abs(gru_beta - trace['beta'])) < 1e-12
        gru_interval_c[scene_id] = {
            'time_start': gru_time[:-1], 'time_end': gru_time[1:],
            'beta_start': gru_beta[:-1], 'residual_end': observed_gru[1:],
            'gru_actual_start': trace['clipped_residual_rad_s2'].reshape(1999, 3)[:-1],
            'categories': categories_intervals(gru_time[:-1], gru_beta[:-1]),
        }
        for period, mask in gru_interval_c[scene_id]['categories'].items():
            safe_record(metric_rows, 'C_GRU_own_closed_loop_approx_residual', scene_id,
                        'scene', period, 'GRU_actual_post_DMAX_at_interval_start_vs_R_nominal_10ms_end',
                        metrics(gru_interval_c[scene_id]['gru_actual_start'][mask], observed_gru[1:][mask]))

        cohort = 'W15' if scene_id.endswith('W15') else 'HF'
        scene_summary[scene_id] = {
            'cohort': cohort, 'c5_raw_sha256': c5_hash, 'gru_raw_sha256': gru_hash,
            'c5_event_count': int(len(events)), 'gru_event_count': int(len(gru_events)),
            'valid_start_aligned_intervals_B': int(len(observed_c5) - 1),
            'valid_start_aligned_intervals_C': int(len(observed_gru) - 1),
            'feature_max_abs_diff_vs_C5_teacher_npz': feature_error,
            'teacher_max_abs_diff_vs_C5_teacher_npz': teacher_error,
            'teacher_DMAX_clip_max_abs_error': clip_error,
            'teacher_beta_application_max_abs_error': beta_error,
            'actual_GRU_trace_feature_max_abs_error': trace_feature_error,
            'actual_GRU_Python_replay_output_max_abs_error': replay_output_error,
            'actual_GRU_Python_replay_clipped_max_abs_error': replay_clip_error,
            'existing_C5_residual_audit_mature_RMS_max_abs_error': residual_audit_error[scene_id],
        }
        loaded[scene_id] = {'c5_raw': c5_raw, 'gru_raw': gru_raw, 'gru_audit': audit_path}
        data[scene_id] = {'features': feat, 'teacher_raw': teacher, 'gru_post': gru_post,
                          'observed_c5': observed_c5, 'observed_gru': observed_gru}

    # Pooled scene-group rows (event/interval pooled, not per-scene macro means).
    cohorts = {'W15': [s for s in scene_ids if s.endswith('W15')],
               'HF': [s for s in scene_ids if not s.endswith('W15')],
               'ALL6': scene_ids}
    for cohort, members in cohorts.items():
        for period in categories_a(np.concatenate([c5_event_a[s]['time'] for s in members]),
                                  np.concatenate([c5_event_a[s]['beta'] for s in members])):
            all_time = np.concatenate([c5_event_a[s]['time'] for s in members])
            all_beta = np.concatenate([c5_event_a[s]['beta'] for s in members])
            mask = categories_a(all_time, all_beta)[period]
            for comparison, pkey in (('GRU_post_DMAX_vs_RBF_post_DMAX_pre_beta','gru_post'),
                                     ('GRU_pre_DMAX_vs_RBF_post_DMAX_pre_beta_diagnostic','gru_pre')):
                pred = np.concatenate([c5_event_a[s][pkey] for s in members], axis=0)
                target = np.concatenate([c5_event_a[s]['teacher'] for s in members], axis=0)
                safe_record(metric_rows,'A_C5_same_state_teacher_fit','POOLED',cohort,period,comparison,metrics(pred[mask],target[mask]))
        # B pooled comparisons
        tstart=np.concatenate([c5_interval_b[s]['time_start'] for s in members]); bstart=np.concatenate([c5_interval_b[s]['beta_start'] for s in members])
        cm=categories_intervals(tstart,bstart)
        for period,mask in cm.items():
            for comparison,key in (('GRU_post_DMAX_at_interval_start_vs_R_nominal_10ms_end','gru_start'),
                                   ('RBF_teacher_post_DMAX_pre_beta_at_interval_start_vs_R_nominal_10ms_end','teacher_start')):
                pred=np.concatenate([c5_interval_b[s][key] for s in members],axis=0)
                target=np.concatenate([c5_interval_b[s]['residual_end'] for s in members],axis=0)
                safe_record(metric_rows,'B_C5_same_state_approx_residual','POOLED',cohort,period,comparison,metrics(pred[mask],target[mask]))
        # C pooled comparisons
        tstart=np.concatenate([gru_interval_c[s]['time_start'] for s in members]); bstart=np.concatenate([gru_interval_c[s]['beta_start'] for s in members])
        cm=categories_intervals(tstart,bstart)
        for period,mask in cm.items():
            pred=np.concatenate([gru_interval_c[s]['gru_actual_start'] for s in members],axis=0)
            target=np.concatenate([gru_interval_c[s]['residual_end'] for s in members],axis=0)
            safe_record(metric_rows,'C_GRU_own_closed_loop_approx_residual','POOLED',cohort,period,
                        'GRU_actual_post_DMAX_at_interval_start_vs_R_nominal_10ms_end',metrics(pred[mask],target[mask]))

    input_paths = [C5_MANIFEST, C5_DATASET, OLD_SCRIPT, OLD_INPUTS, OLD_METRICS, CAUSAL_REPORT,
                   GRU_MODEL, GRU_TRAIN_PARITY, ROOT_METRICS, ROOT_DECISION, RELEASE]
    for scene_id in scene_ids:
        input_paths.extend([loaded[scene_id]['c5_raw'], loaded[scene_id]['gru_raw'],
                            GRU_DIR / 'runs' / scene_id / 'run_status.json', loaded[scene_id]['gru_audit']])
    inputs = {
        'schema': 'GRU_STREAM_TARGET_FIT_DIAGNOSIS_INPUTS_V1',
        'files_sha256': {str(path): sha256(path) for path in input_paths},
        'scene_ids_all_six': scene_ids,
        'cohorts': {'W15': [s for s in scene_ids if s.endswith('W15')],
                    'HF': [s for s in scene_ids if not s.endswith('W15')]},
        'fixed_J0_diagonal_kg_m2': j0.tolist(), 'dmax_rad_s2': DMAX.tolist(),
        'dt_s': DT, 'beta_rise_time_s': BETA_RISE,
        'teacher_target': 'C5 log rbf_output_raw = clip(rbf_output_unclipped, +/-dmax), post-DMAX/pre-beta rad/s^2.',
        'GRU_target_comparison': 'Main A/B/C output is clipped_residual_rad_s2 (post-DMAX/pre-beta); pre-DMAX network output appears only as A diagnostic.',
        'interval_target_formula': 'R=(omega[k]-omega[p])/(time[k]-time[p]) + mean((cross(omega[i],J0*omega[i])-tau_issued[i])/J0), i=p..k-1; p=max(0,k-10), tau_issued=requested_generalized MATLAB columns 2:4.',
        'interval_alignment': 'R ending at event j is paired only with post-DMAX output at preceding event j-1; first interval is excluded. Event index k is zero-based sample 10,20,...,19990, not event ordinal.',
        'interpretation_limit': 'R is an offline 10 ms interval-average nominal-model residual approximation, not true instantaneous physical residual, not a closed-loop counterfactual, and not a deployment input.',
        'forbidden_inputs_used': {'true_inertia': False, 'Jhat': False, 'Jdot': False, 'Plant_truth': False, 'TEST': False},
        'training_or_parameter_search': {'training_jobs': 0, 'relabeling': 0, 'parameter_sweeps': 0},
        'validation_split_caveat': 'C5_VAL48 is included in the C5 full72 training data; A and B are same-record fit/accounting diagnostics, not independent generalization evidence.',
        'prior_validated_script': str(OLD_SCRIPT),
        'prior_validated_script_sha256': sha256(OLD_SCRIPT),
        'prior_clock_formula': 'beta=min((event_index_zero_based+1)*0.001/2.2,1); residual interval endpoint uses time[k]-time[p].',
    }
    (OUT / 'INPUTS.json').write_text(json.dumps(inputs, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with (OUT / 'FIT_METRICS.csv').open('w', newline='', encoding='utf-8') as stream:
        fields = ['diagnostic','scene_id','cohort','period','comparison','axis','valid_n',
                  'rmse_rad_s2','mean_bias_prediction_minus_target_rad_s2','target_rms_rad_s2','prediction_rms_rad_s2']
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(metric_rows)
    report = {
        'schema': 'GRU_STREAM_TARGET_FIT_DIAGNOSIS_V1',
        'Plant_calls': 0, 'training_jobs': 0, 'TEST_read': False,
        'model_sha256': sha256(GRU_MODEL), 'model_path': str(GRU_MODEL),
        'scene_summary': scene_summary,
        'output_csv': str(OUT / 'FIT_METRICS.csv'),
        'output_csv_sha256': sha256(OUT / 'FIT_METRICS.csv'),
        'output_inputs_sha256': sha256(OUT / 'INPUTS.json'),
        'grouping_method': 'pooled event/interval samples within each W15/HF group; per-scene rows are also included; no scene filtering.',
        'metric_definition': 'RMSE and mean bias are prediction minus target, computed per axis; target_rms is the RMS of the approximate interval target or teacher target within that exact category.',
        'diagnostics': {
            'A': 'GRU scene-reset streaming output on each original C5 record vs logged C5 RBF post-DMAX/pre-beta teacher, same event index.',
            'B': 'On original C5 record: GRU and RBF teacher output at interval start vs 10 ms fixed-J0 approximate residual at interval end.',
            'C': 'On each GRU closed-loop raw: logged GRU post-DMAX output at interval start vs same 10 ms fixed-J0 approximate residual at interval end.',
        },
        'feature_and_interval_replay_errors': validation_errors,
        'existing_C5_residual_audit_validation_max_abs_error_by_scene': residual_audit_error,
    }
    (OUT / 'METRICS.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status':'PASS_GRU_STREAM_TARGET_FIT_DIAGNOSIS',
        'scene_count':len(scene_ids),'metric_rows':len(metric_rows),
        'model_sha256':sha256(GRU_MODEL),'report':str(OUT/'METRICS.json'),
        'csv':str(OUT/'FIT_METRICS.csv'),'csv_sha256':sha256(OUT/'FIT_METRICS.csv'),
        'c5_residual_audit_max_error':residual_audit_error},indent=2))

if __name__ == '__main__':
    main()