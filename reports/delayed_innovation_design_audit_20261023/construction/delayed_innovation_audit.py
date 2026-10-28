from __future__ import annotations
import argparse, csv, hashlib, json, math, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import h5py
import numpy as np
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TASKBOOK = ROOT / 'reports/delayed_innovation_design_audit_20261023/TASKBOOK_ZH.md'
PREFLIGHT = HERE / 'INPUT_PREFLIGHT.json'
C1_DIR = ROOT / 'experiments/position_prior_calibration_c1_20261022_v9'
LOCK_PATH = C1_DIR / 'C1_SOURCE_LOCK_v2.json'
MANIFEST_PATH = C1_DIR / 'reports/C1_SCREEN_PER_RUN.csv'
CAUSAL_DIR = ROOT / 'reports/c2_deployable_residual_parent_20261023/causal_observability_10ms'
CAUSAL_SCRIPT = CAUSAL_DIR / 'replay_10ms_observable.py'
CAUSAL_JSON = CAUSAL_DIR / 'CAUSAL_10MS_FIXED12.json'
CAUSAL_CSV = CAUSAL_DIR / 'CAUSAL_10MS_METRICS.csv'
LOCK_SHA = '02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5'
PREFLIGHT_SHA = 'd704bc0d7e8900caf273dce0ad18224adda a988aa8ea76f0b089499db5bcaa25'.replace(' ', '')
MANIFEST_SHA = '43aab1c0fa906dfa5e3d7f175339a5607bd4ec2e2cc55687741524d34fa08bac'
SCENE_SHA = '176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e'
CAUSAL_SCRIPT_SHA = 'ce2b347d3debab155b75739d7f8ccd19182c37b0c57c25eec591d29a468c28f2'
CAUSAL_JSON_SHA = 'b1d03dcb1ecce65ba93f1e7e82599dd9d5670fdb29246da4b916311c7a2ceb4d'
CAUSAL_CSV_SHA = '0a305a86d682543b46881c8c8c62e2582f5e22926e717e10278e0484703b199e'
RUNTIME_SHA = {
    'run_dl1018_closed_loop.m': '01d83dec95aea5d30feef3afd0628a2ce0911f70465f0773a4f568a01b08450b',
    'position_only_search_head_step.m': '3bd0fe9686c3b75793575e517d4cc5f08de58ab6a26a2bc7516aa690422bb7dc',
}
EXPECTED_EVENTS = np.arange(320, 19991, 10, dtype=np.int64)
DT, WINDOW_STEPS, BETA_RISE_S, D_MAX, W_MAX = 0.001, 10, 1.8, 3.0, 60.0
GAMMA, LEAK, FD_STEP = 12.0, 0.002, 1e-6
MAX_OUTPUT_BYTES = 50 * 1024 * 1024
OUT_CSV = HERE / 'DELAYED_INNOVATION_GROUPS.csv'
OUT_JSON = HERE / 'DELAYED_INNOVATION_SUMMARY.json'
OUT_REPORT = HERE / 'REPORT_ZH.md'
OUT_HASHES = HERE / 'ARTIFACT_SHA256.json'
OUT_FAILURE = HERE / 'FAILURE.json'

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def stat_signature(path: Path) -> dict[str, int]:
    st = path.stat()
    return {'bytes': int(st.st_size), 'mtime_ns': int(st.st_mtime_ns)}

def finite_max_abs(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if x.size else 0.0

def safe_float(x: float) -> float | None:
    return float(x) if math.isfinite(float(x)) else None

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def parse_input_identities() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]], dict[str, Any]]:
    assert sha256(PREFLIGHT) == PREFLIGHT_SHA, 'input preflight SHA mismatch'
    preflight = json.loads(PREFLIGHT.read_text(encoding='utf-8-sig'))
    assert preflight['status'] == 'PASS_ALL_FIXED12_RAW_AND_CAUSAL_SOURCE_IDENTITIES'
    assert preflight['checks']['raw_count'] == 12
    assert preflight['checks']['static_pre_post_sha_and_stat_equal'] is True
    assert sha256(LOCK_PATH) == LOCK_SHA, 'C1 lock SHA mismatch'
    lock = json.loads(LOCK_PATH.read_text(encoding='utf-8-sig'))
    assert sha256(MANIFEST_PATH) == MANIFEST_SHA == preflight['checks']['manifest_sha256_before']
    assert preflight['checks']['manifest_sha256_after'] == MANIFEST_SHA
    scene_path = Path(lock['scene_list']['path'])
    assert sha256(scene_path) == SCENE_SHA == lock['scene_list']['sha256']
    with MANIFEST_PATH.open(encoding='utf-8-sig', newline='') as stream:
        manifest_all = list(csv.DictReader(stream))
    with scene_path.open(encoding='utf-8-sig', newline='') as stream:
        scenes = list(csv.DictReader(stream))
    on1_rows = [r for r in manifest_all if r.get('condition') == 'ON1']
    assert len(on1_rows) == len(scenes) == 12
    preflight_raw = {r['scene_id']: r for r in preflight['raw_records']}
    by_scene = {r['scene_id']: r for r in on1_rows}
    assert len(preflight_raw) == len(by_scene) == 12
    ordered_runs = []
    for scene in scenes:
        sid = scene['scene_id']
        run = by_scene[sid]
        assert run['task'] == scene['task'] and run['wind_band'] == scene['band']
        assert run['status'] == 'STABLE' and run['safe_complete_finite'].lower() == 'true'
        pf = preflight_raw[sid]
        raw_path = Path(run['raw_path'])
        assert str(raw_path) == pf['raw_path'] and raw_path.is_file()
        assert run['raw_sha256'] == pf['expected_sha256'] == pf['actual_sha256']
        assert pf['stat_before'] == pf['stat_after']
        assert stat_signature(raw_path) == pf['stat_after'], f'raw stat changed since preflight: {sid}'
        ordered_runs.append({**run, 'task': scene['task'], 'wind_band': scene['band']})
    def locked_file(bucket: str, name: str) -> tuple[Path, str]:
        entry = next(x for x in lock[bucket] if Path(x['path']).name == name)
        path = Path(entry['path'])
        assert sha256(path) == entry['sha256'], f'locked file SHA mismatch: {name}'
        return path, entry['sha256']
    runtime_ids = {}
    for name, expected in RUNTIME_SHA.items():
        path, actual = locked_file('frozen_runtime_files', name)
        assert actual == expected, f'frozen runtime identity mismatch: {name}'
        runtime_ids[name] = {'path': str(path), 'sha256': actual, 'stat': stat_signature(path)}
    cfg_path, cfg_sha = locked_file('frozen_runtime_files', 'effective_config.mat')
    cfg_stat = stat_signature(cfg_path)
    cfg = loadmat(cfg_path, simplify_cells=True)['cfg']
    dt = float(cfg['plant']['dt'])
    beta_rise = float(cfg['rbf']['position']['beta_rise_time'])
    dmax = np.asarray(cfg['rbf']['position']['dmax'], dtype=np.float64).reshape(-1)
    assert abs(dt - DT) < 1e-15 and abs(beta_rise - BETA_RISE_S) < 1e-12
    assert dmax.shape == (3,) and np.array_equal(dmax, np.array([3.0, 3.0, 3.0]))
    assert stat_signature(cfg_path) == cfg_stat and sha256(cfg_path) == cfg_sha
    model_mat = Path(lock['model']['mat_path'])
    model_sha = lock['model']['mat_sha256']
    assert sha256(model_mat) == model_sha
    normalizer_path = Path(lock['normalizer']['npz_path'])
    normalizer_sha = lock['normalizer']['npz_file_sha256']
    assert sha256(normalizer_path) == normalizer_sha
    normalizer_report = Path(lock['normalizer']['train_only_report_path'])
    normalizer_report_sha = lock['normalizer']['train_only_report_sha256']
    assert sha256(normalizer_report) == normalizer_report_sha
    causal_ids = {}
    for path, expected in ((CAUSAL_SCRIPT, CAUSAL_SCRIPT_SHA), (CAUSAL_JSON, CAUSAL_JSON_SHA), (CAUSAL_CSV, CAUSAL_CSV_SHA)):
        before = stat_signature(path)
        actual = sha256(path)
        assert actual == expected, f'causal source SHA mismatch: {path.name}'
        causal_ids[path.name] = {'path': str(path), 'sha256': actual, 'stat_before': before}
    static = {
        'taskbook_path': str(TASKBOOK), 'taskbook_sha256': sha256(TASKBOOK),
        'preflight_path': str(PREFLIGHT), 'preflight_sha256': PREFLIGHT_SHA,
        'C1_source_lock_path': str(LOCK_PATH), 'C1_source_lock_sha256': LOCK_SHA,
        'C1_manifest_path': str(MANIFEST_PATH), 'C1_manifest_sha256': MANIFEST_SHA,
        'scene_list_path': str(scene_path), 'scene_list_sha256': SCENE_SHA,
        'frozen_runtime_sources': runtime_ids,
        'effective_config': {'path': str(cfg_path), 'sha256': cfg_sha, 'stat_before': cfg_stat,
                             'dt_s': dt, 'beta_rise_time_s': beta_rise, 'dmax_mps2': dmax.tolist()},
        'model_identity_from_C1_lock': {
            'canonical_id': lock['model']['canonical_id'], 'checkpoint_sha256': lock['model']['checkpoint_sha256'],
            'W0_output_W_double_f_order_sha256': lock['model']['w0_output_W_double_f_order_sha256'],
            'mat_path': str(model_mat), 'mat_sha256': model_sha,
        },
        'normalizer_identity_from_C1_lock': {
            'path': str(normalizer_path), 'sha256': normalizer_sha,
            'actual_runner_arrays_identity_sha256': lock['normalizer']['actual_runner_arrays_identity_sha256'],
            'train_only_report_path': str(normalizer_report), 'train_only_report_sha256': normalizer_report_sha,
        },
        'causal_observability_inputs': causal_ids,
        'manifest_row_count_all_conditions': len(manifest_all), 'fixed_ON1_count': len(ordered_runs),
        'readout_gamma_s_minus2': GAMMA, 'readout_leak_s_minus1': LEAK,
    }
    return lock, preflight, ordered_runs, static

def read_raw_array(log: h5py.Group, name: str) -> np.ndarray:
    return np.asarray(log[name]).T

def read_one(run: dict[str, str], preflight: dict[str, Any], beta_rise: float) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(run['raw_path'])
    before_stat = stat_signature(path)
    assert before_stat == preflight['stat_after']
    before_sha = sha256(path)
    assert before_sha == run['raw_sha256'] == preflight['actual_sha256']
    with h5py.File(path, 'r') as f:
        log = f['log']
        state = read_raw_array(log, 'state')
        time_s = read_raw_array(log, 'time').reshape(-1)
        transition_time = read_raw_array(log, 'transition_time').reshape(-1)
        valid = read_raw_array(log, 'stage1_position_event_inference_valid').reshape(-1).astype(bool)
        phi = read_raw_array(log, 'stage1_position_event_phi_33')
        beta = read_raw_array(log, 'stage1_position_event_beta').reshape(-1)
        raw_output = read_raw_array(log, 'stage1_position_event_raw_acceleration_mps2')
        applied_output = read_raw_array(log, 'stage1_position_event_applied_acceleration_mps2')
        held_applied = read_raw_array(log, 'stage1_position_held_applied_acceleration_mps2')
        a_f = read_raw_array(log, 'stage1_position_pcf_a_f_mps2')
        s_eff = read_raw_array(log, 'stage1_position_pcf_event_s_coord_eff_mps')
        event_dt = read_raw_array(log, 'stage1_position_event_dt_s').reshape(-1)
        step_index = read_raw_array(log, 'stage1_position_event_step_index').reshape(-1)
        gamma = float(read_raw_array(log, 'stage1_position_search_gamma').item())
        w_before = read_raw_array(log, 'stage1_position_event_weight_before_33x3').transpose(2, 0, 1)
        w_after = read_raw_array(log, 'stage1_position_event_weight_after_33x3').transpose(2, 0, 1)
        pcf_enabled = int(read_raw_array(log, 'stage1_position_pcf_coordination_enabled').item())
        initial_w = read_raw_array(log, 'stage1_position_weight_initial')
    assert pcf_enabled == 1, f'PCF not enabled: {run["scene_id"]}'
    assert state.shape == (20001, 12)
    assert time_s.shape == (20001,) and transition_time.shape == (20000,)
    assert valid.shape == beta.shape == event_dt.shape == (20000,)
    assert phi.shape == (20000, 33)
    assert raw_output.shape == applied_output.shape == held_applied.shape == a_f.shape == s_eff.shape == (20000, 3)
    assert w_before.shape == w_after.shape == (1968, 33, 3) and step_index.shape == (1968,)
    assert initial_w.shape == (33, 3) and gamma == GAMMA
    assert finite_max_abs(initial_w - w_before[0]) < 1e-12, 'initial weight/event-before identity mismatch'
    event_ids = np.flatnonzero(valid)
    assert np.array_equal(event_ids, EXPECTED_EVENTS)
    assert np.array_equal(step_index, event_ids + 1), 'MATLAB 1-based event step mapping mismatch'
    assert np.max(np.abs(np.diff(time_s) - DT)) < 1e-12
    assert np.max(np.abs(time_s[:-1] - transition_time)) < 1e-12
    assert np.max(np.abs(transition_time[event_ids] - time_s[event_ids])) < 1e-12
    assert np.max(np.abs(event_dt[event_ids] - 0.01)) < 1e-12
    for name, array in (('state', state), ('time', time_s), ('transition_time', transition_time),
                        ('event_dt', event_dt), ('held_applied', held_applied), ('a_f', a_f),
                        ('weights_before', w_before), ('weights_after', w_after)):
        assert np.isfinite(array).all(), f'nonfinite {name} in {run["scene_id"]}'
    event_only = {'phi': phi, 'beta': beta, 'raw_output': raw_output,
                  'applied_output': applied_output, 's_eff': s_eff}
    event_only_non_event_nonfinite = {}
    for name, array in event_only.items():
        assert np.isfinite(array[valid]).all(), f'nonfinite valid-event {name} in {run["scene_id"]}'
        outside = array[~valid]
        assert not np.isinf(outside).any(), f'infinite non-event {name} in {run["scene_id"]}'
        event_only_non_event_nonfinite[name] = int(np.count_nonzero(~np.isfinite(outside)))
    expected_beta = np.clip(transition_time[event_ids] / beta_rise, 0.0, 1.0)
    beta_time_error = finite_max_abs(beta[event_ids] - expected_beta)
    assert beta_time_error < 2e-14, f'beta event clock mismatch: {run["scene_id"]} {beta_time_error}'
    phi_norm_error = finite_max_abs(np.linalg.norm(phi[event_ids], axis=1) - 1.0)
    assert phi_norm_error < 2e-12, f'phi normalization mismatch: {run["scene_id"]} {phi_norm_error}'
    raw_rebuild = np.einsum('ni,nij->nj', phi[event_ids], w_before)
    hist_raw_error = finite_max_abs(raw_rebuild - raw_output[event_ids])
    hist_applied_rebuild = beta[event_ids, None] * np.clip(raw_output[event_ids], -D_MAX, D_MAX)
    hist_applied_error = finite_max_abs(hist_applied_rebuild - applied_output[event_ids])
    next_weight_error = finite_max_abs(w_after[:-1] - w_before[1:])
    assert hist_raw_error < 1e-12 and hist_applied_error < 1e-12 and next_weight_error < 1e-12
    update_unprojected = w_before + event_dt[event_ids, None, None] * (
        -gamma * beta[event_ids, None, None] * phi[event_ids, :, None] * s_eff[event_ids, None, :]
        - LEAK * w_before
    )
    update_closure_error = finite_max_abs(np.clip(update_unprojected, -W_MAX, W_MAX) - w_after)
    assert update_closure_error < 2e-12, f'original update closure failed: {run["scene_id"]} {update_closure_error}'
    held_error = 0.0
    for previous, current in zip(event_ids[:-1], event_ids[1:]):
        held_error = max(held_error, finite_max_abs(held_applied[previous:current] - applied_output[previous]))
    assert held_error < 1e-12, f'held event output timing mismatch: {run["scene_id"]} {held_error}'
    js, ks = event_ids[:-1], event_ids[1:]
    assert np.array_equal(ks - js, np.full(1967, WINDOW_STEPS, dtype=np.int64))
    prefix_af = np.vstack([np.zeros((1, 3), dtype=np.float64), np.cumsum(a_f, axis=0)])
    mean_af = (prefix_af[ks] - prefix_af[js]) / WINDOW_STEPS
    target = (state[ks, 3:6] - state[js, 3:6]) / (WINDOW_STEPS * DT) - mean_af
    assert target.shape == (1967, 3) and np.isfinite(target).all()
    phi_old, beta_old = phi[js], beta[js]
    current_event_positions = np.arange(1, len(event_ids), dtype=np.int64)
    w_now = w_before[current_event_positions]
    z_replay = np.einsum('ni,nij->nj', phi_old, w_now)
    replay_output = beta_old[:, None] * np.clip(z_replay, -D_MAX, D_MAX)
    historical_output = applied_output[js].copy()
    historical_raw = raw_output[js].copy()
    hist_log_formula_error = finite_max_abs(beta_old[:, None] * np.clip(historical_raw, -D_MAX, D_MAX) - historical_output)
    replay_error = replay_output - target
    historical_error = historical_output - target
    active = np.abs(z_replay) < D_MAX
    exact_kink = np.abs(np.abs(z_replay) - D_MAX) == 0.0
    near_kink = np.abs(np.abs(z_replay) - D_MAX) <= 1e-12
    gradient = phi_old[:, :, None] * (beta_old[:, None] * active.astype(np.float64) * replay_error)[:, None, :]
    actual_delta = w_after[current_event_positions] - w_before[current_event_positions]
    event_times = transition_time[ks]
    run_record = {
        'scene_id': run['scene_id'], 'task': run['task'], 'wind_band': run['wind_band'],
        'raw_path': str(path), 'raw_sha256_before': before_sha, 'raw_sha256_after': None,
        'raw_bytes': before_stat['bytes'], 'raw_stat_before': before_stat, 'raw_stat_after': None,
        'all_valid_events': int(event_ids.size), 'eligible_previous_valid_phi_pairs': int(ks.size),
        'first_current_event_index_zero_based': int(ks[0]), 'last_current_event_index_zero_based': int(ks[-1]),
        'first_eligible_time_s': float(event_times[0]), 'last_eligible_time_s': float(event_times[-1]),
        'beta_clock_max_abs_error': beta_time_error, 'phi_norm_max_abs_error': phi_norm_error,
        'non_event_uncomputed_field_nonfinite_counts': event_only_non_event_nonfinite,
        'history_raw_from_Wbefore_max_abs_error_mps2': hist_raw_error,
        'history_applied_from_beta_clip_max_abs_error_mps2': hist_applied_error,
        'history_applied_formula_on_pairs_max_abs_error_mps2': hist_log_formula_error,
        'Wafter_previous_to_Wbefore_current_max_abs_error': next_weight_error,
        'held_output_previous_event_interval_max_abs_error_mps2': held_error,
        'original_tracking_update_reconstruction_max_abs_error': update_closure_error,
        'gamma_s_minus2': gamma, 'beta_mean_previous_event': float(np.mean(beta_old)),
        'beta_min_previous_event': float(np.min(beta_old)), 'beta_max_previous_event': float(np.max(beta_old)),
    }
    arrays = {
        'task': run['task'], 'wind_band': run['wind_band'], 'scene_id': run['scene_id'],
        'time': event_times, 'target': target, 'history': historical_output,
        'history_raw': historical_raw, 'replay': replay_output, 'replay_z': z_replay,
        'beta': beta_old, 'phi_norm': np.linalg.norm(phi_old, axis=1),
        'gradient': gradient, 'delta': actual_delta,
        'saturated': np.abs(z_replay) > D_MAX, 'exact_kink': exact_kink,
        'near_kink': near_kink, 'hist_saturated': np.abs(historical_raw) > D_MAX,
    }
    after_stat, after_sha = stat_signature(path), sha256(path)
    assert after_stat == before_stat and after_sha == before_sha
    run_record['raw_sha256_after'], run_record['raw_stat_after'] = after_sha, after_stat
    return run_record, arrays

def deterministic_direction() -> np.ndarray:
    i = np.arange(1, 100, dtype=np.float64)
    d = (np.sin(i * math.sqrt(2.0)) + 0.37 * np.cos(i * math.sqrt(3.0))).reshape(33, 3)
    return d / np.linalg.norm(d)

def finite_difference_row(sample_id: str, scene_id: str, k: int | None, j: int | None,
                          phi: np.ndarray, w: np.ndarray, beta: float, target: np.ndarray,
                          direction: np.ndarray, note: str) -> dict[str, Any]:
    z0 = phi @ w
    e0 = beta * np.clip(z0, -D_MAX, D_MAX) - target
    mask0 = np.abs(z0) < D_MAX
    exact_kink = bool(np.any(np.abs(np.abs(z0) - D_MAX) == 0.0))
    plus_z = phi @ (w + FD_STEP * direction)
    minus_z = phi @ (w - FD_STEP * direction)
    plus_mask, minus_mask = np.abs(plus_z) < D_MAX, np.abs(minus_z) < D_MAX
    same_active_set = bool(np.array_equal(mask0, plus_mask) and np.array_equal(mask0, minus_mask))
    base = {
        'sample_id': sample_id, 'scene_id': scene_id, 'current_event_index_zero_based': k,
        'previous_event_index_zero_based': j, 'beta_previous': float(beta),
        'phi_norm': float(np.linalg.norm(phi)), 'fd_step': FD_STEP,
        'min_distance_to_clip_kink': float(np.min(np.abs(np.abs(z0) - D_MAX))),
        'saturated_axis_count': int(np.sum(np.abs(z0) > D_MAX)),
        'exact_kink_axis_count': int(np.sum(np.abs(np.abs(z0) - D_MAX) == 0.0)),
        'near_kink_axis_count': int(np.sum(np.abs(np.abs(z0) - D_MAX) <= 1e-12)),
        'same_active_set_plus_minus': same_active_set,
        'analytic_directional_derivative': None, 'central_difference': None,
        'absolute_error': None, 'relative_error': None, 'status': None, 'note': note,
    }
    if exact_kink:
        base['status'] = 'SKIP_EXACT_CLIP_KINK'
        return base
    if not same_active_set:
        base['status'] = 'SKIP_ACTIVE_SET_CROSSED'
        return base
    g = phi[:, None] * (beta * mask0 * e0)[None, :]
    analytic = float(np.sum(g * direction))
    def objective(weight: np.ndarray) -> float:
        e = beta * np.clip(phi @ weight, -D_MAX, D_MAX) - target
        return 0.5 * float(e @ e)
    fd = (objective(w + FD_STEP * direction) - objective(w - FD_STEP * direction)) / (2.0 * FD_STEP)
    abs_err = abs(fd - analytic)
    rel_err = abs_err / max(1e-12, abs(fd), abs(analytic))
    base.update({
        'analytic_directional_derivative': analytic, 'central_difference': fd,
        'absolute_error': abs_err, 'relative_error': rel_err,
        'status': 'PASS' if abs_err < 1e-7 and rel_err < 1e-5 else 'CHECK_NUMERICAL_ERROR',
    })
    return base

def finite_difference_checks(records: list[dict[str, Any]], arrays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    direction = deterministic_direction()
    rows = []
    for rec, data in zip(records, arrays):
        n = len(data['time'])
        raw_path = Path(rec['raw_path'])
        raw_stat_before, raw_sha_before = stat_signature(raw_path), sha256(raw_path)
        assert raw_sha_before == rec['raw_sha256_before'] and raw_stat_before == rec['raw_stat_before']
        with h5py.File(raw_path, 'r') as f:
            log = f['log']
            phi_full = read_raw_array(log, 'stage1_position_event_phi_33')
            ids = np.flatnonzero(read_raw_array(log, 'stage1_position_event_inference_valid').reshape(-1).astype(bool))
            wb = read_raw_array(log, 'stage1_position_event_weight_before_33x3').transpose(2, 0, 1)
            beta_full = read_raw_array(log, 'stage1_position_event_beta').reshape(-1)
        assert stat_signature(raw_path) == raw_stat_before and sha256(raw_path) == raw_sha_before
        for label, pos in (('FIRST', 0), ('MIDDLE', n // 2), ('LAST', n - 1)):
            k = int(ids[pos + 1])
            j = int(ids[pos])
            rows.append(finite_difference_row(
                f'{label}_ELIGIBLE_PAIR', rec['scene_id'], k, j,
                phi_full[j], wb[pos + 1], float(beta_full[j]), data['target'][pos], direction,
                'Fixed direction; current W_before[k] on previous valid phi_j; no update applied.',
            ))
    phi = np.arange(1, 34, dtype=np.float64)
    phi /= np.linalg.norm(phi)
    w = np.outer(phi, np.array([0.4, -3.4, 1.2], dtype=np.float64))
    target = np.array([-0.2, 2.1, 0.5], dtype=np.float64)
    rows.append(finite_difference_row(
        'SYNTHETIC_MIXED_ACTIVE_SATURATED', 'SYNTHETIC', None, None,
        phi, w, 0.65, target, direction,
        'Constructed q=[0.4,-3.4,1.2], beta=0.65; one saturated axis, two active.',
    ))
    return rows
def scope_definitions(records: list[dict[str, Any]]) -> list[tuple[str, str, list[int]]]:
    scopes = [('ALL12', 'ALL12', list(range(len(records))))]
    for band in ('W00_W08', 'W09_W11', 'W12_W14', 'W15'):
        ix = [i for i, r in enumerate(records) if r['wind_band'] == band]
        assert len(ix) == 3
        scopes.append(('WIND', band, ix))
    hf = [i for i, r in enumerate(records) if r['wind_band'] in ('W09_W11', 'W12_W14')]
    assert len(hf) == 6
    scopes.append(('HF_W09_W14', 'HF_W09_W14', hf))
    for task in ('FIG8_3D', 'HELIX', 'SQUARE'):
        ix = [i for i, r in enumerate(records) if r['task'] == task]
        assert len(ix) == 4
        scopes.append(('TASK', task, ix))
    for i, r in enumerate(records):
        scopes.append(('RUN', r['scene_id'], [i]))
    return scopes

def metric_row(scope_kind: str, scope: str, members: list[int], phase: str,
               records: list[dict[str, Any]], arrays: list[dict[str, Any]], axis: str) -> dict[str, Any]:
    parts = []
    for ix in members:
        d = arrays[ix]
        if phase == 'EARLY_0_5S':
            keep = d['time'] < 5.0
        elif phase == 'LATE_5_20S':
            keep = (d['time'] >= 5.0) & (d['time'] < 20.0)
        else:
            keep = np.ones(d['time'].shape, dtype=bool)
        if np.any(keep):
            parts.append((d, keep))
    assert parts
    cat = lambda key: np.concatenate([d[key][keep] for d, keep in parts], axis=0)
    target, history, history_raw = cat('target'), cat('history'), cat('history_raw')
    replay, z, beta = cat('replay'), cat('replay_z'), cat('beta')
    grad, delta = cat('gradient'), cat('delta')
    near_kink, exact_kink = cat('near_kink'), cat('exact_kink')
    hist_sat = cat('hist_saturated')
    cols = np.arange(3) if axis == 'ALL' else np.array([{'X': 0, 'Y': 1, 'Z': 2}[axis]])
    e_hist = (history[:, cols] - target[:, cols]).reshape(-1)
    e_replay = (replay[:, cols] - target[:, cols]).reshape(-1)
    target_flat, hist_flat = target[:, cols].reshape(-1), history[:, cols].reshape(-1)
    replay_flat = replay[:, cols].reshape(-1)
    z_flat, hist_raw_flat = z[:, cols].reshape(-1), history_raw[:, cols].reshape(-1)
    g_view, dw_view = grad[:, :, cols].reshape(len(beta), -1), delta[:, :, cols].reshape(len(beta), -1)
    g_norm, dw_norm = np.linalg.norm(g_view, axis=1), np.linalg.norm(dw_view, axis=1)
    dots = np.sum((-g_view) * dw_view, axis=1)
    denom = g_norm * dw_norm
    cos_valid = denom > 0
    cosine = np.zeros_like(dots)
    cosine[cos_valid] = np.clip(dots[cos_valid] / denom[cos_valid], -1.0, 1.0)
    angles = np.degrees(np.arccos(cosine[cos_valid]))
    n_events = len(beta)
    return {
        'scope_kind': scope_kind, 'scope': scope, 'phase': phase, 'axis': axis,
        'run_count': len(members), 'event_pair_count': n_events, 'output_scalar_count': int(e_replay.size),
        'target_rms_mps2': float(np.sqrt(np.mean(target_flat * target_flat))),
        'historical_output_rms_mps2': float(np.sqrt(np.mean(hist_flat * hist_flat))),
        'replay_output_rms_mps2': float(np.sqrt(np.mean(replay_flat * replay_flat))),
        'historical_error_rmse_mps2': float(np.sqrt(np.mean(e_hist * e_hist))),
        'historical_error_bias_mps2': float(np.mean(e_hist)),
        'replay_error_rmse_mps2': float(np.sqrt(np.mean(e_replay * e_replay))),
        'replay_error_bias_mps2': float(np.mean(e_replay)),
        'mean_event_gradient_norm': float(np.mean(g_norm)),
        'rms_event_gradient_norm': float(np.sqrt(np.mean(g_norm * g_norm))),
        'summed_gradient_norm': float(np.linalg.norm(np.sum(g_view, axis=0))),
        'mean_actual_total_deltaW_norm': float(np.mean(dw_norm)),
        'rms_actual_total_deltaW_norm': float(np.sqrt(np.mean(dw_norm * dw_norm))),
        'mean_descent_vs_actual_total_deltaW_dot': float(np.mean(dots)),
        'mean_descent_vs_actual_total_deltaW_cosine': safe_float(float(np.mean(cosine[cos_valid]))) if np.any(cos_valid) else None,
        'positive_alignment_fraction': safe_float(float(np.mean(cosine[cos_valid] > 0))) if np.any(cos_valid) else None,
        'mean_angle_deg': safe_float(float(np.mean(angles))) if angles.size else None,
        'cosine_valid_event_count': int(np.sum(cos_valid)),
        'replay_saturated_scalar_count': int(np.sum(np.abs(z_flat) > D_MAX)),
        'history_saturated_scalar_count': int(np.sum(np.abs(hist_raw_flat) > D_MAX)),
        'replay_exact_kink_scalar_count': int(np.sum(exact_kink[:, cols])),
        'replay_near_kink_scalar_count': int(np.sum(near_kink[:, cols])),
        'mean_previous_beta': float(np.mean(beta)), 'min_previous_beta': float(np.min(beta)),
        'max_previous_beta': float(np.max(beta)), 'mean_inverse_previous_beta': float(np.mean(1.0 / beta)),
        'phi_norm_max_abs_error': max(float(records[i]['phi_norm_max_abs_error']) for i in members),
    }

def all_metric_rows(records: list[dict[str, Any]], arrays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for kind, scope, members in scope_definitions(records):
        for phase in ('ALL_ELIGIBLE', 'EARLY_0_5S', 'LATE_5_20S'):
            for axis in ('ALL', 'X', 'Y', 'Z'):
                rows.append(metric_row(kind, scope, members, phase, records, arrays, axis))
    return rows

def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)

def write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open('x', encoding='utf-8', newline='') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')

def make_report(summary: dict[str, Any], rows: list[dict[str, Any]], fd_rows: list[dict[str, Any]]) -> str:
    lookup = {(r['scope'], r['phase'], r['axis']): r for r in rows}
    lines = [
        '# 延迟残差创新离线构造核验', '',
        f"状态：{summary['status']}。固定使用原 C1 ON1 12 条 raw；不训练、不累积更新、不运行 MATLAB/Plant/GPU/TEST。", '',
        '开发阶段的五次 smoke/启动失败均已保留在 DEVELOPMENT_FAILURES.json；失败均发生在离线读取/构造阶段，没有写出分析产物；raw 身份未变。', '',
        '## 构造', '',
        '对当前事件索引 k=330,…,19990（步长 10）取上一有效事件 j=k−10。目标只用当前及过去速度与已知滤波加速度：', '',
        r'\[\hat d^-_k = \frac{v_k-v_j}{10\,dt} - \frac1{10}\sum_{\ell=j}^{k-1}a_{f,\ell},\quad dt=1\,\mathrm{ms}.\]', '',
        r'历史实发为 $u^{hist}_j=\beta_j\operatorname{clip}(\phi_j^T W_j,\pm3)$；当前权重重放为 $u^{rep}_{k\leftarrow j}=\beta_j\operatorname{clip}(\phi_j^T W_k,\pm3)$，$W_k$ 是事件 k 更新前权重。两者分别与 $\hat d^-_k$ 比较。', '',
        r'逐事件 $L_k=\frac12\|u^{rep}_{k\leftarrow j}-\hat d^-_k\|_2^2$，解析梯度 $G_k=\phi_j[\beta_j(m_k\odot e_k)]^T$，$m=1\{|\phi_j^TW_k|<3\}$。精确 clip 边界取零子梯度并计不可微；有限差分只在双侧活动集一致处计算。', '',
        f"每条有 {summary['sample_definition']['eligible_pairs_per_run']} 个合法配对（共 {summary['sample_definition']['eligible_pairs_total']}）；k=320 不配伪造的 k=310 输出。", '',
        '## 结果', '',
        '全轴 RMSE 单位 m/s²。CSV 包含 ALL12、HF（W09_W11 与 W12_W14 合并）、W15、四个单独风组、任务和逐条记录，并按 XYZ、全部轴及早/晚段分层。', '',
        '| 范围 | 时段 | 历史实发误差RMSE | 当前W重放误差RMSE | 梯度均值范数 | 与实际总ΔW平均cos | 正向对齐比例 |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for scope in ('ALL12', 'HF_W09_W14', 'W15'):
        for phase in ('ALL_ELIGIBLE', 'EARLY_0_5S', 'LATE_5_20S'):
            r = lookup[(scope, phase, 'ALL')]
            cos = '' if r['mean_descent_vs_actual_total_deltaW_cosine'] is None else f"{r['mean_descent_vs_actual_total_deltaW_cosine']:.6g}"
            pos = '' if r['positive_alignment_fraction'] is None else f"{r['positive_alignment_fraction']:.4f}"
            lines.append(f"| {scope} | {phase} | {r['historical_error_rmse_mps2']:.6g} | {r['replay_error_rmse_mps2']:.6g} | {r['mean_event_gradient_norm']:.6g} | {cos} | {pos} |")
    passed = sum(r['status'] == 'PASS' for r in fd_rows)
    skipped = sum(str(r['status']).startswith('SKIP') for r in fd_rows)
    max_abs = max((r['absolute_error'] or 0.0) for r in fd_rows if r['absolute_error'] is not None)
    max_rel = max((r['relative_error'] or 0.0) for r in fd_rows if r['relative_error'] is not None)
    lines += [
        '', f'有限差分：{passed} PASS，{skipped} 个真实点因 kink/双侧活动集变化跳过；最大通过点绝对误差 {max_abs:.3g}、相对误差 {max_rel:.3g}。', '',
        '## 单位与边界', '',
        'φ 单位范数且无量纲；β 无量纲；创新 e 单位 m/s²，平方损失单位 m²/s⁴，∂L/∂W 与 W 同为 m/s²。原跟踪律 γ=12 s⁻²，不能直接当预测增益。若另用 L̃=½‖e/β‖²，由于 G_raw 已含 β，G_tilde=G_raw/β²=φ[m⊙e/β]^T；β≈0.18 时相对原损失梯度约放大 30.86 倍，而 e 前显式系数为 1/β≈5.56。仅为尺度说明，本检查没有采用该损失或选择增益。', '',
        '无量纲创新可写为 ν=Σ_d^(-1/2)e/β_j，其中 Σ_d 单位 (m/s²)²；本数据无测量噪声模型，不能推定 Σ_d。若速度测量每轴独立标准差为 σ_v，10 ms 差分噪声标准差为 √2 σ_v/0.01；σ_v 未知，记录中的仿真速度不是含噪传感器数据。', '',
        '比较方向使用实际记录的总 ΔW_k=W_after−W_before，包含跟踪项、leakage 与 projection。内积/夹角只说明该记录点上延迟损失梯度下降方向与实际总权重变化的局部几何关系，不代表纯 tracking 方向、新自适应律收益、闭环稳定性或反事实轨迹；没有执行新权重更新。', '',
        f"脚本 SHA-256 `{summary['artifacts']['script_sha256']}`；逐场输入身份与闭合误差见 JSON；完整分组表见 `{OUT_CSV.name}`。", '',
    ]
    return '\n'.join(lines)
def run() -> None:
    started = time.perf_counter()
    lock, preflight, runs, static = parse_input_identities()
    beta_rise = static['effective_config']['beta_rise_time_s']
    static['stats_before_read'] = {
        'taskbook': stat_signature(TASKBOOK), 'preflight': stat_signature(PREFLIGHT),
        'C1_lock': stat_signature(LOCK_PATH), 'manifest': stat_signature(MANIFEST_PATH),
        'scene_list': stat_signature(Path(lock['scene_list']['path'])),
        'effective_config': stat_signature(Path(static['effective_config']['path'])),
        'model_mat': stat_signature(Path(static['model_identity_from_C1_lock']['mat_path'])),
        'normalizer': stat_signature(Path(static['normalizer_identity_from_C1_lock']['path'])),
        'normalizer_report': stat_signature(Path(static['normalizer_identity_from_C1_lock']['train_only_report_path'])),
        'causal_files': {name: stat_signature(Path(item['path'])) for name, item in static['causal_observability_inputs'].items()},
        'runtime_sources': {name: stat_signature(Path(item['path'])) for name, item in static['frozen_runtime_sources'].items()},
    }
    records, arrays, raw_snapshots = [], [], []
    for run_row in runs:
        pfrow = next(r for r in preflight['raw_records'] if r['scene_id'] == run_row['scene_id'])
        record, data = read_one(run_row, pfrow, beta_rise)
        records.append(record)
        arrays.append(data)
        raw_snapshots.append({
            'scene_id': record['scene_id'], 'sha256_before': record['raw_sha256_before'],
            'sha256_after': record['raw_sha256_after'], 'stat_before': record['raw_stat_before'],
            'stat_after': record['raw_stat_after'],
        })
    fd_rows = finite_difference_checks(records, arrays)
    assert all(r['status'] in ('PASS', 'SKIP_EXACT_CLIP_KINK', 'SKIP_ACTIVE_SET_CROSSED') for r in fd_rows)
    synthetic = next(r for r in fd_rows if r['sample_id'] == 'SYNTHETIC_MIXED_ACTIVE_SATURATED')
    assert synthetic['status'] == 'PASS' and synthetic['saturated_axis_count'] == 1
    metric_rows = all_metric_rows(records, arrays)
    assert len(metric_rows) == 252
    assert all(np.isfinite(float(row['historical_error_rmse_mps2'])) and np.isfinite(float(row['replay_error_rmse_mps2'])) for row in metric_rows)

    static_post = {
        'taskbook_sha256': sha256(TASKBOOK), 'preflight_sha256': sha256(PREFLIGHT),
        'C1_lock_sha256': sha256(LOCK_PATH), 'manifest_sha256': sha256(MANIFEST_PATH),
        'scene_list_sha256': sha256(Path(lock['scene_list']['path'])),
        'effective_config_sha256': sha256(Path(static['effective_config']['path'])),
        'model_mat_sha256': sha256(Path(static['model_identity_from_C1_lock']['mat_path'])),
        'normalizer_sha256': sha256(Path(static['normalizer_identity_from_C1_lock']['path'])),
        'normalizer_report_sha256': sha256(Path(static['normalizer_identity_from_C1_lock']['train_only_report_path'])),
        'causal_files': {name: sha256(Path(item['path'])) for name, item in static['causal_observability_inputs'].items()},
        'runtime_sources': {name: sha256(Path(item['path'])) for name, item in static['frozen_runtime_sources'].items()},
    }
    assert static_post['C1_lock_sha256'] == LOCK_SHA and static_post['manifest_sha256'] == MANIFEST_SHA
    assert static_post['preflight_sha256'] == PREFLIGHT_SHA and static_post['scene_list_sha256'] == SCENE_SHA
    assert static_post['causal_files'] == {name: item['sha256'] for name, item in static['causal_observability_inputs'].items()}
    assert static_post['runtime_sources'] == {name: item['sha256'] for name, item in static['frozen_runtime_sources'].items()}
    assert static_post['model_mat_sha256'] == lock['model']['mat_sha256']
    assert static_post['normalizer_sha256'] == lock['normalizer']['npz_file_sha256']
    assert static_post['normalizer_report_sha256'] == lock['normalizer']['train_only_report_sha256']
    assert static_post['effective_config_sha256'] == static['effective_config']['sha256']
    assert static_post['taskbook_sha256'] == static['taskbook_sha256']
    static_post['stats_after_read'] = {
        'taskbook': stat_signature(TASKBOOK), 'preflight': stat_signature(PREFLIGHT),
        'C1_lock': stat_signature(LOCK_PATH), 'manifest': stat_signature(MANIFEST_PATH),
        'scene_list': stat_signature(Path(lock['scene_list']['path'])),
        'effective_config': stat_signature(Path(static['effective_config']['path'])),
        'model_mat': stat_signature(Path(static['model_identity_from_C1_lock']['mat_path'])),
        'normalizer': stat_signature(Path(static['normalizer_identity_from_C1_lock']['path'])),
        'normalizer_report': stat_signature(Path(static['normalizer_identity_from_C1_lock']['train_only_report_path'])),
        'causal_files': {name: stat_signature(Path(item['path'])) for name, item in static['causal_observability_inputs'].items()},
        'runtime_sources': {name: stat_signature(Path(item['path'])) for name, item in static['frozen_runtime_sources'].items()},
    }
    assert static_post['stats_after_read'] == static['stats_before_read'], 'a static source stat changed during processing'
    for rec in records:
        assert rec['raw_sha256_before'] == rec['raw_sha256_after'] and rec['raw_stat_before'] == rec['raw_stat_after']
    static['post_run_hashes'] = static_post
    static['raw_pre_post_hash_and_stat'] = raw_snapshots

    csv_size_guard = sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
    assert csv_size_guard < MAX_OUTPUT_BYTES
    write_csv(OUT_CSV, metric_rows)
    script_path = Path(__file__).resolve()
    script_sha = sha256(script_path)
    csv_sha = sha256(OUT_CSV)
    summary = {
        'schema': 'DELAYED_INNOVATION_DESIGN_AUDIT_FIXED12_V1',
        'status': 'PASS_FIXED12_OFFLINE_DELAYED_INNOVATION_DIAGNOSTIC',
        'created_utc': now_utc(), 'source_script_sha256': script_sha,
        'development_failure_ledger': {'path': str(HERE / 'DEVELOPMENT_FAILURES.json'), 'sha256': sha256(HERE / 'DEVELOPMENT_FAILURES.json')},
        'command': 'python -B reports/delayed_innovation_design_audit_20261023/construction/delayed_innovation_audit.py --execute-offline',
        'resource_scope': {'Plant': 0, 'MATLAB': 0, 'training': 0, 'optimizer': 0, 'new_weight_updates': 0,
                           'gain_search': 0, 'GPU': 0, 'TEST': 0, 'CPU_threads_requested': 1},
        'sample_definition': {
            'records': 12, 'all_valid_head_event_indices_zero_based': '320..19990 inclusive, step 10',
            'valid_head_events_per_run': 1968, 'first_event_k320_has_no_previous_valid_head': True,
            'eligible_pair_current_k': '330..19990 inclusive, step 10',
            'eligible_previous_event_j': 'k-10', 'eligible_pairs_per_run': 1967,
            'eligible_pairs_total': 12 * 1967,
            'event_time_segments': {'EARLY_0_5S': 'current event transition_time < 5.0 s',
                                    'LATE_5_20S': '5.0 <= current event transition_time < 20.0 s'},
        },
        'definitions': {
            'past_interval_target': 'd_hat_minus(k)=(v[k]-v[j])/(10*dt)-mean(a_f[j:k]), j=k-10, dt=0.001 s; uses only current/past velocity and internal filter acceleration.',
            'historical_output': 'u_hist(j)=logged applied output at j; checked against beta[j]*clip(phi[j]^T W_before[j],-3,3).',
            'current_weight_replay': 'u_rep(k<-j)=beta[j]*clip(phi[j]^T W_before[k],-3,3); W_before[k] is current pre-update weight, not W_after[k].',
            'per_event_loss': 'L_k=0.5*||u_rep(k<-j)-d_hat_minus(k)||_2^2.',
            'analytic_gradient': 'G_k=phi[j]*(beta[j]*m_k*e_k)^T; m_k[a]=1 if abs((phi[j]^T W_before[k])[a])<3, else 0. Exact +/-3 uses selected zero subgradient and is counted nondifferentiable.',
            'actual_logged_weight_delta': 'DeltaW_k=W_after[k]-W_before[k], includes the runtime leakage and any elementwise projection; rebuilt from frozen runtime equation and compared geometrically to -G_k only.',
            'beta_clock': 'Original ON1 beta at past event j is read from log and checked against min(transition_time[j]/1.8 s,1).',
            'feature_normalization': 'Logged phi_33 is read directly and norm-checked to 1; no encoder re-execution or refit.',
            'clip_counting': 'saturated iff abs(z)>3; exact kink iff abs(abs(z)-3)==0; near kink iff distance<=1e-12.',
        },
        'units_and_symbolic_normalization': {
            'phi': 'dimensionless with logged norm 1.', 'beta': 'dimensionless event ramp factor.',
            'raw_innovation': 'e=u_rep-d_hat_minus, m/s^2.', 'loss': 'L=0.5*||e||^2, m^2/s^4.',
            'gradient_wrt_W': 'm/s^2, same units as W.', 'tracking_gamma': '12 s^-2; not a prediction gain.',
            'symbolic_dimensionless_innovation': 'nu_k=Sigma_d^(-1/2)*e_k/beta_j, where Sigma_d has units (m/s^2)^2; Sigma_d is unknown and not estimated here.',
            'beta_squared_loss_scaling': 'Since e=beta*clip-target and G_raw already contains beta, for L_tilde=0.5*||e/beta_j||^2, G_tilde=G_raw/beta_j^2=phi*(m*e/beta_j)^T. At beta=0.18 the relative gradient multiplier is ~30.86; the explicit coefficient on e is 1/beta=~5.56. Scale note only; no alternative loss or gain was used.',
            'measurement_noise_bound': 'If per-axis velocity sensor noise is independent with SD sigma_v, differencing contributes sqrt(2)*sigma_v/0.01 m/s^2; sigma_v is unknown. Logged state velocity is not a noisy sensor record.',
        },
        'identity_and_runtime_checks': {
            'static_inputs': static, 'records': records, 'all_static_and_raw_pre_post_checks_passed': True,
            'history_output_and_update_closure_checked': True, 'event_index_and_hold_timing_checked': True,
            'phi_norm_error_max': max(r['phi_norm_max_abs_error'] for r in records),
            'history_raw_reconstruction_error_max_mps2': max(r['history_raw_from_Wbefore_max_abs_error_mps2'] for r in records),
            'history_applied_reconstruction_error_max_mps2': max(r['history_applied_from_beta_clip_max_abs_error_mps2'] for r in records),
            'held_interval_error_max_mps2': max(r['held_output_previous_event_interval_max_abs_error_mps2'] for r in records),
            'original_tracking_update_reconstruction_error_max': max(r['original_tracking_update_reconstruction_max_abs_error'] for r in records),
        },
        'finite_difference': {
            'direction': 'fixed deterministic unit-Frobenius matrix sin(i*sqrt(2))+0.37*cos(i*sqrt(3)), i=1..99.',
            'step': FD_STEP, 'real_samples_per_run': ['FIRST', 'MIDDLE', 'LAST'],
            'rows': fd_rows, 'synthetic_mixed_active_saturated_case': synthetic,
            'pass_count': sum(r['status'] == 'PASS' for r in fd_rows),
            'skip_count_exact_kink': sum(r['status'] == 'SKIP_EXACT_CLIP_KINK' for r in fd_rows),
            'skip_count_active_set_crossed': sum(r['status'] == 'SKIP_ACTIVE_SET_CROSSED' for r in fd_rows),
            'max_absolute_error_passed': max((r['absolute_error'] or 0.0) for r in fd_rows if r['absolute_error'] is not None),
            'max_relative_error_passed': max((r['relative_error'] or 0.0) for r in fd_rows if r['relative_error'] is not None),
        },
        'group_csv': {'path': str(OUT_CSV), 'sha256': csv_sha, 'row_count': len(metric_rows)},
        'interpretation_limits': [
            'No weight update, training, optimizer, new gain, or closed-loop counterfactual was performed.',
            'Gradient-to-original-update cosine/dot is local geometric evidence only, not an adaptive-law or closed-loop benefit result.',
            'The delay target is a causal 10 ms finite-difference approximation; deployment noise floor is unknown.',
            'The original update is tracking-error driven with beta, leakage and projection; it need not minimize this delayed prediction loss.',
        ],
        'elapsed_seconds': time.perf_counter() - started,
    }
    summary['artifacts'] = {
        'script_path': str(script_path), 'script_sha256': script_sha,
        'csv_path': str(OUT_CSV), 'csv_sha256': csv_sha,
        'summary_path': str(OUT_JSON), 'report_path': str(OUT_REPORT),
    }
    write_json(OUT_JSON, summary)
    report_text = make_report(summary, metric_rows, fd_rows)
    with OUT_REPORT.open('x', encoding='utf-8', newline='') as stream:
        stream.write(report_text)
    outputs = {
        'script': {'path': str(script_path), 'sha256': script_sha},
        'input_preflight': {'path': str(PREFLIGHT), 'sha256': sha256(PREFLIGHT)},
        'csv': {'path': str(OUT_CSV), 'sha256': sha256(OUT_CSV), 'bytes': OUT_CSV.stat().st_size},
        'summary_json': {'path': str(OUT_JSON), 'sha256': sha256(OUT_JSON), 'bytes': OUT_JSON.stat().st_size},
        'report': {'path': str(OUT_REPORT), 'sha256': sha256(OUT_REPORT), 'bytes': OUT_REPORT.stat().st_size},
        'development_failures': {'path': str(HERE / 'DEVELOPMENT_FAILURES.json'), 'sha256': sha256(HERE / 'DEVELOPMENT_FAILURES.json')},
    }
    write_json(OUT_HASHES, {'schema': 'DELAYED_INNOVATION_ARTIFACT_HASHES_V1', 'created_utc': now_utc(), 'artifacts': outputs})
    output_bytes = sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())
    assert output_bytes <= MAX_OUTPUT_BYTES, f'construction output exceeds 50 MiB: {output_bytes}'
    print(json.dumps({
        'status': summary['status'], 'records': 12, 'eligible_pairs': 12 * 1967,
        'metric_rows': len(metric_rows), 'fd_pass': summary['finite_difference']['pass_count'],
        'fd_skips': summary['finite_difference']['skip_count_exact_kink'] + summary['finite_difference']['skip_count_active_set_crossed'],
        'elapsed_seconds': summary['elapsed_seconds'], 'output_bytes': output_bytes, 'artifacts': outputs,
    }, ensure_ascii=False))

def main() -> None:
    parser = argparse.ArgumentParser(description='Fixed 12-run offline delayed innovation audit; never updates a weight.')
    parser.add_argument('--execute-offline', action='store_true', required=True)
    parser.parse_args()
    for output in (OUT_CSV, OUT_JSON, OUT_REPORT, OUT_HASHES, OUT_FAILURE):
        if output.exists():
            raise SystemExit(f'refusing to overwrite existing artifact: {output}')
    try:
        run()
    except Exception as exc:
        if not OUT_FAILURE.exists():
            failure = {
                'schema': 'DELAYED_INNOVATION_FAILURE_V1', 'status': 'FAILED_NO_RETRY',
                'created_utc': now_utc(), 'script_sha256': sha256(Path(__file__).resolve()),
                'exception_type': type(exc).__name__, 'exception': str(exc),
                'traceback': traceback.format_exc(), 'Plant': 0, 'training': 0,
                'optimizer': 0, 'GPU': 0, 'TEST': 0,
            }
            write_json(OUT_FAILURE, failure)
        raise

if __name__ == '__main__':
    main()
