from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Keep numeric kernels CPU-only and single-threaded before importing NumPy.
for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RECON = ROOT / 'reports' / 'train_pcf_contract_reconstruction_20261022'
PARENT_REVIEW = ROOT / 'reports' / 'train_pcf_contract_parent_review_20261022'
ARCHIVE = ROOT.parent / 'REFERENCE_FIX_FULL72_20261021_022342_313' / 'corrected_reference_training_v1'
PAIR = ARCHIVE / 'corrected_pair_training'
RUNS = RECON / 'TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv'
PHASE_STATE = RECON / 'TRAIN_FIXED_MODEL_5ca776c5f476_PHASE_STATE.json'
METRICS = RECON / 'TRAIN_FIXED_MODEL_5ca776c5f476_METRICS.csv'
TRAIN_GATE = PARENT_REVIEW / 'TRAIN_COMPLETED_PHASE_PARENT_GATE.json'
TRAIN_INDEX = PAIR / 'manifests' / 'PAIR_TRAINING_INPUT_INDEX.csv'
PROTOCOL = PAIR / 'protocol.json'

EXPECTED = {
    'train_index_sha256': '257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca',
    'runs_sha256': '4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190',
    'phase_state_sha256': 'b5fb66aafc7f934ae199037bd318c85974d1e41724bc54c805ed14900beaf002',
    'metrics_sha256': 'c4d5fa3092266daf133977b8ffc97e30a1616516845f080032d97e19af0c0866',
    'worker_sha256': '5ca776c5f476c8e7ad824c11ab1381d48b6fdf0b385f9471522a8f5826a8021a',
    'core_sha256': 'd2e2c807b8119b32eddba8f765c6c566bee40d5e37c0590363f9091d30a47f70',
    'model_sha256': 'f6fc258dbee1d33dbac608d94f690b23e5329d375d2806d9bb0601a667506ea5',
    'pair_workflow_sha256': 'a82f92465587f64f60b3c3109875a480a8ae164bf8562670808347820dbc233b',
    'teacher_data_sha256': '3d6ec20f544cda2ec99c3bddf17e595a75683c90fbd6b542475d006b6d2badad',
    'teacher_models_sha256': '7d38948b0ea2f70ec7d1f3c433063cdc7f264080e5f717262e56ba4fd8ec1c22',
    'fit_models_sha256': '31a08407f5b3fe66b42a7e930925e5ae4cdabfa0a764c218356eedb82ca4e9ff',
    'protocol_sha256': '28e63d588f1e693140a04f3bbcedc9f608cda74306e310ce5bae9e21961feba6',
    'episodes': 1536,
    'windows_per_episode': 394,
    'window_length': 32,
    'stride': 5,
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def stat_key(path: Path) -> tuple[int, int]:
    st = path.stat()
    return int(st.st_size), int(st.st_mtime_ns)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def scalar_text(z: np.lib.npyio.NpzFile, key: str) -> str:
    v = np.asarray(z[key])
    require(v.shape == (), f'{key} is not scalar: {v.shape}')
    return str(v.item())


def check_static_inputs() -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, int]]:
    paths = {
        'train_index_sha256': TRAIN_INDEX,
        'runs_sha256': RUNS,
        'phase_state_sha256': PHASE_STATE,
        'metrics_sha256': METRICS,
        'protocol_sha256': PROTOCOL,
        'pair_workflow_sha256': PAIR / 'scripts' / 'pair_workflow.py',
        'teacher_data_sha256': PAIR / 'scripts' / 'teacher_data.py',
        'teacher_models_sha256': PAIR / 'scripts' / 'teacher_models.py',
        'fit_models_sha256': PAIR / 'scripts' / 'fit_models.py',
    }
    actual = {k: sha256_file(p) for k, p in paths.items()}
    for key, value in actual.items():
        require(value == EXPECTED[key], f'{key} mismatch: {value} != {EXPECTED[key]}')

    gate = json.loads(TRAIN_GATE.read_text(encoding='utf-8-sig'))
    require(gate.get('status') == 'PASS_PARENT_COMPLETED_PHASE_GATE', 'TRAIN parent gate is not PASS')
    require(gate.get('split') == 'TRAIN' and int(gate.get('episodes', -1)) == 1536, 'TRAIN gate identity mismatch')
    require(bool(gate.get('sidecars_all_hash_verified')) and bool(gate.get('recorded_source_hash_stat_unchanged')), 'TRAIN gate hash/stat check failed')
    require(int(gate.get('sidecar_bytes', -1)) == 769172595, 'TRAIN sidecar byte count mismatch')
    gate_inputs = gate.get('inputs_sha256', {})
    require(gate_inputs.get(str(RUNS)) == EXPECTED['runs_sha256'], 'TRAIN gate does not bind RUNS CSV')
    require(gate_inputs.get(str(PHASE_STATE)) == EXPECTED['phase_state_sha256'], 'TRAIN gate does not bind PHASE_STATE')
    require(gate_inputs.get(str(METRICS)) == EXPECTED['metrics_sha256'], 'TRAIN gate does not bind METRICS CSV')

    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8-sig'))
    require(protocol.get('schema') == 'CORRECTED_PAIR_FIXED60K_PROTOCOL_V1', 'unexpected training protocol')
    require(protocol.get('training', {}).get('window') == 32 and protocol.get('training', {}).get('stride') == 5, 'training window/stride mismatch')
    require(protocol.get('training', {}).get('loss') == 'mean-axis SmoothL1(pred/3,target_clip/3), hierarchical endpoint weight', 'training loss definition mismatch')
    require(protocol.get('training', {}).get('weight_decay') == 1e-05, 'weight decay source mismatch')
    require(int(protocol.get('data', {}).get('train_episodes', -1)) == 1536 and int(protocol.get('data', {}).get('train_windows', -1)) == 605184, 'protocol TRAIN dimensions mismatch')

    source_rows = read_csv(TRAIN_INDEX)
    source_by_id = {r['run_id']: r for r in source_rows}
    require(len(source_by_id) == len(source_rows), 'duplicate run_id in frozen training index')
    runs = read_csv(RUNS)
    require(len(runs) == EXPECTED['episodes'], f'expected 1536 RUNS rows, got {len(runs)}')
    require(len({r['run_id'] for r in runs}) == len(runs), 'duplicate run_id in RUNS')
    require(all(r.get('split') == 'TRAIN' for r in runs), 'RUNS contains a non-TRAIN row')
    require(all(r.get('status') == 'PASS' for r in runs), 'RUNS has non-PASS status')
    require(all(r.get('worker_script_sha256') == EXPECTED['worker_sha256'] for r in runs), 'worker identity mismatch')
    require(all(r.get('core_script_sha256') == EXPECTED['core_sha256'] for r in runs), 'core identity mismatch')
    require(all(r.get('model_source_sha256') == EXPECTED['model_sha256'] for r in runs), 'model source identity mismatch')
    require(all(r.get('model_id') == 'CORRECTED_DSSM14_SEED2026102001_FINAL60000' for r in runs), 'model ID mismatch')

    source_by_id = {r['run_id']: r for r in source_rows if r.get('split', '').upper() == 'TRAIN'}
    require(set(source_by_id) == {r['run_id'] for r in runs}, 'TRAIN RUNS IDs differ from frozen training index')
    scene_counts = Counter((r['role'], r['task'], int(r['class_index'])) for r in source_by_id.values())
    for run in runs:
        src = source_by_id[run['run_id']]
        for key in ('role', 'task', 'wind_cell'):
            require(str(src[key]) == str(run[key]), f'{run["run_id"]}: source/RUNS {key} mismatch')
        require(str(src['split']).upper() == 'TRAIN', f'{run["run_id"]}: source split mismatch')
        require(Path(src['cache_path']).is_file(), f'{run["run_id"]}: cache missing')
        require(run.get('sidecar_path') and Path(run['sidecar_path']).is_file(), f'{run["run_id"]}: sidecar missing')
        require(run.get('sidecar_sha256') and run.get('cache_sha256_before') == src['cache_sha256'] and run.get('cache_sha256_after') == src['cache_sha256'], f'{run["run_id"]}: frozen cache/sidecar SHA missing or mismatched')
    return runs, source_by_id, dict(scene_counts)


def read_guarded_npz(path: Path, expected_sha: str) -> np.lib.npyio.NpzFile:
    before_stat = stat_key(path)
    before_sha = sha256_file(path)
    require(before_sha == expected_sha, f'pre-read SHA mismatch: {path}')
    return np.load(path, allow_pickle=False), before_stat, before_sha


def phase_weights(phase: np.ndarray, scene_n: int) -> tuple[np.ndarray, dict[int, int], int]:
    unique, counts = np.unique(phase, return_counts=True)
    phase_n = int(len(unique))
    require(phase_n > 0 and scene_n > 0, 'empty phase/class scene set')
    count_map = dict(zip(unique.tolist(), counts.tolist()))
    base = 0.5 / (3.0 * 16.0 * float(scene_n) * float(phase_n))
    weights64 = np.asarray([base / count_map[int(code)] for code in phase], dtype=np.float64)
    weights32 = weights64.astype(np.float32)
    require(np.isfinite(weights32).all() and (weights32 > 0).all(), 'invalid float32 training weights')
    return weights32, {int(k): int(v) for k, v in count_map.items()}, phase_n


def smooth_l1_unit(d: np.ndarray) -> np.ndarray:
    a = np.abs(d)
    return np.where(a < 1.0, 0.5 * a * a, a - 0.5)


class Agg:
    def __init__(self) -> None:
        self.n = 0
        self.units = 0
        self.mass = 0.0
        self.lp = np.zeros(3, dtype=np.float64)
        self.lz = np.zeros(3, dtype=np.float64)
        self.sq_pc = np.zeros(3, dtype=np.float64)
        self.sq_zc = np.zeros(3, dtype=np.float64)
        self.bias_pc = np.zeros(3, dtype=np.float64)
        self.bias_zc = np.zeros(3, dtype=np.float64)
        self.sq_pr = np.zeros(3, dtype=np.float64)
        self.sq_zr = np.zeros(3, dtype=np.float64)
        self.bias_pr = np.zeros(3, dtype=np.float64)
        self.bias_zr = np.zeros(3, dtype=np.float64)
        self.eq = {name: np.zeros(3, dtype=np.float64) for name in (
            'prior_rmse_clip', 'zero_rmse_clip', 'prior_bias_clip', 'zero_bias_clip',
            'prior_rmse_raw', 'zero_rmse_raw', 'prior_bias_raw', 'zero_bias_raw')}

    def add_unit(self, w: np.ndarray, pred: np.ndarray, clip_y: np.ndarray, raw_y: np.ndarray) -> None:
        wd = w.astype(np.float64, copy=False)
        mass = float(wd.sum())
        require(mass > 0 and np.isfinite(mass), 'invalid weight mass')
        epc, ezc = pred - clip_y, -clip_y
        epr, ezr = pred - raw_y, -raw_y
        lpc = smooth_l1_unit(epc / 3.0) / 3.0
        lzc = smooth_l1_unit(ezc / 3.0) / 3.0
        self.n += int(len(w))
        self.units += 1
        self.mass += mass
        self.lp += np.sum(wd[:, None] * lpc, axis=0)
        self.lz += np.sum(wd[:, None] * lzc, axis=0)
        self.sq_pc += np.sum(wd[:, None] * (epc * epc), axis=0)
        self.sq_zc += np.sum(wd[:, None] * (ezc * ezc), axis=0)
        self.bias_pc += np.sum(wd[:, None] * epc, axis=0)
        self.bias_zc += np.sum(wd[:, None] * ezc, axis=0)
        self.sq_pr += np.sum(wd[:, None] * (epr * epr), axis=0)
        self.sq_zr += np.sum(wd[:, None] * (ezr * ezr), axis=0)
        self.bias_pr += np.sum(wd[:, None] * epr, axis=0)
        self.bias_zr += np.sum(wd[:, None] * ezr, axis=0)
        self.eq['prior_rmse_clip'] += np.sqrt(self.sq_pc * 0 + np.sum(wd[:, None] * (epc * epc), axis=0) / mass)
        self.eq['zero_rmse_clip'] += np.sqrt(np.sum(wd[:, None] * (ezc * ezc), axis=0) / mass)
        self.eq['prior_bias_clip'] += np.sum(wd[:, None] * epc, axis=0) / mass
        self.eq['zero_bias_clip'] += np.sum(wd[:, None] * ezc, axis=0) / mass
        self.eq['prior_rmse_raw'] += np.sqrt(np.sum(wd[:, None] * (epr * epr), axis=0) / mass)
        self.eq['zero_rmse_raw'] += np.sqrt(np.sum(wd[:, None] * (ezr * ezr), axis=0) / mass)
        self.eq['prior_bias_raw'] += np.sum(wd[:, None] * epr, axis=0) / mass
        self.eq['zero_bias_raw'] += np.sum(wd[:, None] * ezr, axis=0) / mass

    def merge(self, other: 'Agg') -> None:
        self.n += other.n
        self.units += other.units
        self.mass += other.mass
        for name in ('lp','lz','sq_pc','sq_zc','bias_pc','bias_zc','sq_pr','sq_zr','bias_pr','bias_zr'):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        for name in self.eq:
            self.eq[name] += other.eq[name]


def load_one(run: dict[str, str], source: dict[str, str], scene_counts: dict[tuple[str, str, int], int]) -> tuple[np.ndarray, ...]:
    run_id = run['run_id']
    cache_path = Path(source['cache_path'])
    side_path = Path(run['sidecar_path'])
    cache, cache_stat, cache_sha = read_guarded_npz(cache_path, source['cache_sha256'])
    side, side_stat, side_sha = read_guarded_npz(side_path, run['sidecar_sha256'])
    try:
        require(scalar_text(cache, 'run_id') == run_id and scalar_text(side, 'run_id') == run_id, f'{run_id}: embedded run_id mismatch')
        require(scalar_text(cache, 'split').upper() == 'TRAIN' and scalar_text(side, 'split').upper() == 'TRAIN', f'{run_id}: embedded split mismatch')
        require(scalar_text(cache, 'task') == run['task'] and scalar_text(side, 'task') == run['task'], f'{run_id}: task mismatch')
        require(scalar_text(cache, 'role') == run['role'] and scalar_text(side, 'role') == run['role'], f'{run_id}: role mismatch')
        x14 = cache['x14']
        clip_y_all = cache['y']
        raw_y_all = cache['raw']
        phase_all = cache['phase']
        side_x14 = side['X14']
        side_y = side['Y_clip']
        side_phase = side['phase_code']
        require(x14.shape == (1999, 14) and x14.dtype == np.float32, f'{run_id}: cache X14 schema mismatch')
        require(clip_y_all.shape == (1999, 3) and clip_y_all.dtype == np.float32, f'{run_id}: cache y schema mismatch')
        require(raw_y_all.shape == (1999, 3) and raw_y_all.dtype == np.float32, f'{run_id}: cache raw schema mismatch')
        require(phase_all.shape == (1999,) and phase_all.dtype == np.uint8, f'{run_id}: cache phase schema mismatch')
        require(np.array_equal(x14, side_x14), f'{run_id}: cache X14 != sidecar X14')
        require(np.array_equal(clip_y_all, side_y), f'{run_id}: cache y != sidecar Y_clip')
        require(np.array_equal(phase_all, side_phase), f'{run_id}: cache phase != sidecar phase_code')
        require(np.isfinite(x14).all() and np.isfinite(clip_y_all).all() and np.isfinite(raw_y_all).all(), f'{run_id}: nonfinite cache values')
        ends = np.arange(31, 1999, 5, dtype=np.int32)
        require(len(ends) == 394 and int(ends[0]) == 31 and int(ends[-1]) == 1996, 'endpoint recipe mismatch')
        pred_all = side['pred_raw_valid']
        require(pred_all.shape == (1968, 3) and pred_all.dtype == np.float64 and np.isfinite(pred_all).all(), f'{run_id}: raw prior prediction schema/finite mismatch')
        require(int(np.asarray(side['valid_start_zero_based']).item()) == 31, f'{run_id}: valid-start mismatch')
        pred = pred_all[ends - 31]
        clip_y = clip_y_all[ends].astype(np.float64)
        raw_y = raw_y_all[ends].astype(np.float64)
        phase = phase_all[ends]
        require(np.isfinite(pred).all(), f'{run_id}: endpoint prediction nonfinite')
        scene_n = scene_counts[(run['role'], run['task'], int(source['class_index']))]
        weights, phase_counts, phase_n = phase_weights(phase, scene_n)
        require(float(weights.sum()) > 0, f'{run_id}: zero weight mass')
    finally:
        cache.close()
        side.close()
    require(stat_key(cache_path) == cache_stat and sha256_file(cache_path) == cache_sha, f'{run_id}: cache changed during read')
    require(stat_key(side_path) == side_stat and sha256_file(side_path) == side_sha, f'{run_id}: sidecar changed during read')
    return ends, pred, clip_y, raw_y, phase, weights, phase_counts, phase_n


def stats_table(groups: dict[tuple[str, ...], Agg], all_prior_loss: float, all_zero_loss: float) -> list[dict[str, object]]:
    axis_names = ('X', 'Y', 'Z')
    rows: list[dict[str, object]] = []
    for key in sorted(groups):
        scope, run_id, task, role, wind_band, wind_cell, phase_code = key
        a = groups[key]
        for j, axis in enumerate(axis_names):
            mass = a.mass
            prior_loss = float(a.lp[j])
            zero_loss = float(a.lz[j])
            rows.append({
                'scope': scope, 'run_id': run_id, 'task': task, 'role': role,
                'wind_band': wind_band, 'wind_cell': wind_cell, 'phase_code': phase_code,
                'axis': axis, 'run_or_phase_units': a.units, 'window_count': a.n,
                'weight_mass': mass,
                'prior_smoothl1_contribution_axis_div3': prior_loss,
                'zero_smoothl1_contribution_axis_div3': zero_loss,
                'prior_total_objective_contribution_group': float(a.lp.sum()),
                'zero_total_objective_contribution_group': float(a.lz.sum()),
                'prior_loss_share_of_full_train': prior_loss / all_prior_loss if all_prior_loss else None,
                'zero_loss_share_of_full_train': zero_loss / all_zero_loss if all_zero_loss else None,
                'prior_loss_per_weight_mass': prior_loss / mass if mass else None,
                'zero_loss_per_weight_mass': zero_loss / mass if mass else None,
                'prior_rmse_clip_weighted': float(np.sqrt(a.sq_pc[j] / mass)) if mass else None,
                'zero_rmse_clip_weighted': float(np.sqrt(a.sq_zc[j] / mass)) if mass else None,
                'prior_bias_clip_weighted': float(a.bias_pc[j] / mass) if mass else None,
                'zero_bias_clip_weighted': float(a.bias_zc[j] / mass) if mass else None,
                'prior_rmse_raw_weighted': float(np.sqrt(a.sq_pr[j] / mass)) if mass else None,
                'zero_rmse_raw_weighted': float(np.sqrt(a.sq_zr[j] / mass)) if mass else None,
                'prior_bias_raw_weighted': float(a.bias_pr[j] / mass) if mass else None,
                'zero_bias_raw_weighted': float(a.bias_zr[j] / mass) if mass else None,
                'prior_rmse_clip_run_equal': float(a.eq['prior_rmse_clip'][j] / a.units) if a.units else None,
                'zero_rmse_clip_run_equal': float(a.eq['zero_rmse_clip'][j] / a.units) if a.units else None,
                'prior_bias_clip_run_equal': float(a.eq['prior_bias_clip'][j] / a.units) if a.units else None,
                'zero_bias_clip_run_equal': float(a.eq['zero_bias_clip'][j] / a.units) if a.units else None,
                'prior_rmse_raw_run_equal': float(a.eq['prior_rmse_raw'][j] / a.units) if a.units else None,
                'zero_rmse_raw_run_equal': float(a.eq['zero_rmse_raw'][j] / a.units) if a.units else None,
                'prior_bias_raw_run_equal': float(a.eq['prior_bias_raw'][j] / a.units) if a.units else None,
                'zero_bias_raw_run_equal': float(a.eq['zero_bias_raw'][j] / a.units) if a.units else None,
            })
    return rows


def write_csv_once(path: Path, rows: list[dict[str, object]]) -> None:
    require(not path.exists(), f'refusing to overwrite existing output: {path}')
    if not rows:
        raise RuntimeError(f'no rows for {path.name}')
    with path.open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def main() -> int:
    parser = argparse.ArgumentParser(description='Replay frozen TRAIN objective from exact cache labels and W0 raw sidecars')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--smoke', action='store_true', help='read and check only the first frozen TRAIN sample')
    group.add_argument('--execute-after-audit', action='store_true', help='full TRAIN1536 replay; requires prior parent approval')
    args = parser.parse_args()
    start = time.perf_counter()
    command = 'python -B ' + ' '.join(sys.argv)
    try:
        runs, source_by_id, scene_counts = check_static_inputs()
        if args.smoke:
            run = runs[0]
            result = load_one(run, source_by_id[run['run_id']], scene_counts)
            ends, pred, y, raw_y, phase, weights, phase_counts, phase_n = result
            e = pred - y
            one = {
                'status': 'PASS_SMOKE_ONE_TRAIN_RUN', 'command': command,
                'generated_local': local_now(), 'run_id': run['run_id'],
                'script_sha256': sha256_file(Path(__file__)),
                'train_runs_sha256': EXPECTED['runs_sha256'],
                'training_index_sha256': EXPECTED['train_index_sha256'],
                'cache_sha256': source_by_id[run['run_id']]['cache_sha256'],
                'sidecar_sha256': run['sidecar_sha256'],
                'endpoint_count': int(len(ends)), 'first_end_0based': int(ends[0]), 'last_end_0based': int(ends[-1]),
                'valid_start_0based': 31, 'phase_code_counts': phase_counts, 'phase_n': phase_n,
                'float32_weight_mass_this_run': float(weights.astype(np.float64).sum()),
                'pred_raw_valid_shape': [1968, 3], 'pred_raw_finite': True,
                'cache_x14_phase_y_equal_sidecar': True,
                'sample_prior_clip_rmse_axis': np.sqrt(np.mean(e * e, axis=0)).tolist(),
                'sample_zero_clip_rmse_axis': np.sqrt(np.mean(y * y, axis=0)).tolist(),
                'numerical_definition': 'sidecar-double raw prior vs exact cache-float32 labels; original SmoothL1 definition, not bitwise Torch replay',
                'optimizer_steps': 0, 'plant_calls': 0, 'gpu_jobs': 0, 'test_accessed': False,
                'wall_seconds': time.perf_counter() - start,
            }
            stamp = datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')
            out = OUT / f'SMOKE_{stamp}.json'
            out.write_text(json.dumps(one, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            print(json.dumps(one, ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        output_names = ('OBJECTIVE_GROUP_METRICS.csv', 'OBJECTIVE_SUMMARY.json', 'FULL_RUN_STATE.json')
        for name in output_names:
            require(not (OUT / name).exists(), f'refusing to overwrite existing output: {OUT / name}')
        groups: dict[tuple[str, ...], Agg] = {}
        phase_seen: Counter[int] = Counter()
        total_weight = 0.0
        sidecar_bytes = 0
        for i, run in enumerate(runs, start=1):
            src = source_by_id[run['run_id']]
            sidecar_bytes += int(run['sidecar_bytes'])
            ends, pred, y, raw_y, phase, weights, phase_counts, _ = load_one(run, src, scene_counts)
            total_weight += float(weights.astype(np.float64).sum())
            phase_seen.update(phase_counts.keys())
            base_fields = (run['run_id'], run['task'], run['role'], run['wind_band'], run['wind_cell'])
            phase_groups = []
            for code in sorted(phase_counts):
                mask = phase == code
                phase_groups.append((str(code), mask))
            scopes: list[tuple[tuple[str, ...], np.ndarray]] = [
                (('ALL', '', '', '', '', '', ''), np.ones(len(ends), dtype=bool)),
                (('RUN', run['run_id'], run['task'], run['role'], run['wind_band'], run['wind_cell'], ''), np.ones(len(ends), dtype=bool)),
                (('TASK_ROLE_WIND_BAND', '', run['task'], run['role'], run['wind_band'], '', ''), np.ones(len(ends), dtype=bool)),
                (('TASK_ROLE_WIND_CELL', '', run['task'], run['role'], run['wind_band'], run['wind_cell'], ''), np.ones(len(ends), dtype=bool)),
            ]
            for code_text, mask in phase_groups:
                scopes.extend([
                    (('RUN_PHASE', run['run_id'], run['task'], run['role'], run['wind_band'], run['wind_cell'], code_text), mask),
                    (('TASK_ROLE_WIND_BAND_PHASE', '', run['task'], run['role'], run['wind_band'], '', code_text), mask),
                    (('TASK_ROLE_WIND_CELL_PHASE', '', run['task'], run['role'], run['wind_band'], run['wind_cell'], code_text), mask),
                ])
            for key, mask in scopes:
                unit = Agg()
                unit.add_unit(weights[mask], pred[mask], y[mask], raw_y[mask])
                groups.setdefault(key, Agg()).merge(unit)
            if i % 128 == 0 or i == len(runs):
                print(f'PROGRESS {i}/{len(runs)} runs; endpoint weights={total_weight:.9f}; elapsed={time.perf_counter()-start:.1f}s', flush=True)

        require(len(runs) == 1536 and sum(phase_seen.values()) > 0, 'TRAIN replay cardinality/phase failure')
        require(abs(total_weight - 1.0) < 2e-6, f'float32 hierarchical weight sum differs from one: {total_weight}')
        check_static_inputs()  # Re-hash frozen manifests/source identities before publishing outputs.
        all_key = ('ALL', '', '', '', '', '', '')
        all_prior_loss = float(groups[all_key].lp.sum())
        all_zero_loss = float(groups[all_key].lz.sum())
        rows = stats_table(groups, all_prior_loss, all_zero_loss)
        csv_out = OUT / 'OBJECTIVE_GROUP_METRICS.csv'
        write_csv_once(csv_out, rows)
        summary = {
            'status': 'PASS_TRAIN1536_OBJECTIVE_REPLAY', 'generated_local': local_now(), 'command': command,
            'script_sha256': sha256_file(Path(__file__)), 'train_runs_sha256': EXPECTED['runs_sha256'],
            'training_index_sha256': EXPECTED['train_index_sha256'], 'phase_state_sha256': EXPECTED['phase_state_sha256'],
            'train_parent_gate': str(TRAIN_GATE), 'train_parent_gate_sha256': sha256_file(TRAIN_GATE),
            'source_scripts_sha256': {k: sha256_file(v) for k, v in {
                'pair_workflow.py': PAIR / 'scripts' / 'pair_workflow.py',
                'teacher_data.py': PAIR / 'scripts' / 'teacher_data.py',
                'teacher_models.py': PAIR / 'scripts' / 'teacher_models.py',
                'fit_models.py': PAIR / 'scripts' / 'fit_models.py',
            }.items()},
            'episode_count': len(runs), 'windows_per_episode': 394, 'total_windows': len(runs) * 394,
            'endpoint_recipe_0based': '31+5*k, k=0..393', 'prediction_source': 'frozen sidecar pred_raw_valid (MATLAB-equivalent double export inference)',
            'label_source': 'cache y float32 exact; sidecar Y_clip equality checked per run',
            'raw_label_source': 'cache raw float32, descriptive only; not used by training loss',
            'loss_definition': 'mean_axis SmoothL1(pred_raw/3,cache_y/3,beta=1); objective contribution is sum_i float32_weight_i * per_window_i',
            'minibatch_estimator_reference': '(N/actual_batch_size)*sum_batch(float32_weight_i*per_window_i)',
            'weight_definition': 'double hierarchical weight from frozen teacher_data.EpisodeBank.windows, cast to float32 before use',
            'total_float32_weight_mass': total_weight, 'prior_smoothl1_objective': all_prior_loss,
            'zero_smoothl1_objective': all_zero_loss, 'prior_objective_share': 1.0, 'zero_objective_share': 1.0,
            'sidecar_bytes_read': sidecar_bytes, 'derived_csv_rows': len(rows),
            'metric_caveat': 'Original loss-definition diagnostic using sidecar double predictions and exact cache float32 labels; not bitwise Torch training replay. Run-equally-weighted metrics are explicitly separate from hierarchical objective metrics.',
            'optimizer_steps': 0, 'plant_calls': 0, 'gpu_jobs': 0, 'test_accessed': False, 'dev_labels_used': False,
            'wall_seconds': time.perf_counter() - start,
            'outputs': {'metrics_csv': str(csv_out), 'metrics_csv_sha256': sha256_file(csv_out), 'metrics_csv_bytes': csv_out.stat().st_size},
        }
        summary_path = OUT / 'OBJECTIVE_SUMMARY.json'
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        state_path = OUT / 'FULL_RUN_STATE.json'
        state = {
            'status': 'PASS_TRAIN1536_OBJECTIVE_REPLAY', 'generated_local': local_now(), 'command': command,
            'script_sha256': summary['script_sha256'], 'metrics_csv_sha256': summary['outputs']['metrics_csv_sha256'],
            'summary_sha256': sha256_file(summary_path), 'episodes': len(runs), 'windows': len(runs) * 394,
            'optimizer_steps': 0, 'plant_calls': 0, 'gpu_jobs': 0, 'test_accessed': False,
            'wall_seconds': summary['wall_seconds'], 'failures': [],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        fail_path = OUT / 'FAILURE_STATE.json'
        failure = {'status': 'FAILED', 'generated_local': local_now(), 'command': command,
                   'script_sha256': sha256_file(Path(__file__)), 'exception_type': type(exc).__name__,
                   'exception': str(exc), 'wall_seconds': time.perf_counter() - start,
                   'optimizer_steps': 0, 'plant_calls': 0, 'gpu_jobs': 0, 'test_accessed': False}
        if not fail_path.exists():
            fail_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(failure, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
