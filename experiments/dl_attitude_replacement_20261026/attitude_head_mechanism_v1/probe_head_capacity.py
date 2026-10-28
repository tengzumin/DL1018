"""Oracle-label, causal residual-head capacity check; NEVER a deployed controller."""
from pathlib import Path
import hashlib
import json
import os
import sys
# NumPy MKL and PyTorch ship different OpenMP runtimes in this Windows env.
# Use sequential BLAS for this small offline diagnostic; do not permit duplicates.
os.environ['MKL_THREADING_LAYER'] = 'SEQUENTIAL'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import numpy as np
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
BASE = RESEARCH / 'mlp15_c5_teacher_full72_v1'
RUN = BASE / 'runs/C5_MLP15_FULL72_SEED2026102001'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def causal_rls(phi, base, labels):
    """Predict before observing the current label. All labels here are offline oracle."""
    dim = phi.shape[1]
    covariance = 10 * np.eye(dim)
    correction = np.zeros((dim, 3))
    prediction = np.empty_like(base)
    max_norm = 0.
    min_eigenvalue = float('inf')
    for k, feature in enumerate(phi):
        prediction[k] = base[k] + feature @ correction
        pf = covariance @ feature
        gain = pf / (0.999 + feature @ pf)
        correction += np.outer(gain, labels[k] - prediction[k])
        covariance = (covariance - np.outer(gain, pf)) / 0.999
        covariance = (covariance + covariance.T) / 2
        max_norm = max(max_norm, float(np.linalg.norm(correction)))
        if k % 100 == 0 or k == len(phi) - 1:
            min_eigenvalue = min(min_eigenvalue, float(np.linalg.eigvalsh(covariance).min()))
    assert np.isfinite(prediction).all() and min_eigenvalue > 0
    return prediction, max_norm, min_eigenvalue

def main():
    out = HERE / 'ORACLE_HEAD_CAPACITY.json'
    if out.exists():
        raise FileExistsError(out)
    # A future/current label perturbation cannot alter past/current predictions.
    rng = np.random.default_rng(2026102001)
    phi = rng.normal(size=(60, 5)); y = rng.normal(size=(60, 3))
    a, _, _ = causal_rls(phi, np.zeros_like(y), y)
    changed = y.copy(); changed[30:] += 20
    b, _, _ = causal_rls(phi, np.zeros_like(y), changed)
    assert np.array_equal(a[:31], b[:31]) and not np.array_equal(a[31:], b[31:])
    torch.set_num_threads(1)
    sys.path.insert(0, str(BASE))
    import train_mlp15_c5_full72_v1 as data_source
    sys.path.insert(0, str(RESEARCH / 'mlp15_c5_teacher_ghp7_balance_v1'))
    import audit_ghp7_balanced_fit_v1 as replay
    lock = data_source.load_and_verify_lock(require_release=False)
    ids = lock['scene_ids_in_training_order']
    x, y = data_source._load_c5_training_arrays(lock, ids)
    manifest_path = RESEARCH / 'mlp15_distribution_countercheck_v1/MANIFEST.json'
    selected = [r['scene_id'] for r in json.loads(manifest_path.read_text())['records']]
    indices = [ids.index(s) for s in selected]; x, y = x[indices], y[indices].astype(np.float64)
    MLP15, make_windows = replay.load_model_helpers()
    model, mean, std, scale = replay.load_checkpoint(RUN / 'final_step_60000.pt', MLP15)
    assert sha(RUN / 'mlp15_attitude_weights_v1.mat') == '67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b'
    x_norm = ((x - mean) / std).astype(np.float32)
    padded = F.pad(torch.as_tensor(x_norm).permute(0, 2, 1), (14, 0))
    scene_index = torch.arange(6).repeat_interleave(1999)
    event_index = torch.arange(1999).repeat(6)
    windows = make_windows(padded, scene_index, event_index)
    with torch.inference_mode():
        hidden = model.net[:4](windows.flatten(start_dim=1))
        base = model.net[4](hidden).numpy().reshape(6, 1999, 3).astype(np.float64)
        latent = hidden.numpy().reshape(6, 1999, 32).astype(np.float64)
    rows = []
    for i, scene in enumerate(selected):
        features = np.column_stack((latent[i], np.ones(1999)))
        features /= np.linalg.norm(features, axis=1, keepdims=True)
        prediction, norm, eigen = causal_rls(features, base[i], y[i] / scale)
        base_y = np.clip(base[i] * scale, -replay.D_MAX, replay.D_MAX)
        adapt_y = np.clip(prediction * scale, -replay.D_MAX, replay.D_MAX)
        fixed_error = base_y - y[i]; head_error = adapt_y - y[i]
        fixed_rmse = float(np.sqrt(np.mean(np.sum(fixed_error**2, axis=1))))
        head_rmse = float(np.sqrt(np.mean(np.sum(head_error**2, axis=1))))
        late_fixed = float(np.sqrt(np.mean(np.sum(fixed_error[999:]**2, axis=1))))
        late_head = float(np.sqrt(np.mean(np.sum(head_error[999:]**2, axis=1))))
        rows.append({'scene_id': scene, 'fixed_vector_RMSE_rad_s2': fixed_rmse,
                     'oracle_vector_RMSE_rad_s2': head_rmse,
                     'fixed_late10s_RMSE_rad_s2': late_fixed, 'oracle_late10s_RMSE_rad_s2': late_head,
                     'late10s_reduction_fraction': 1 - late_head / late_fixed,
                     'oracle_axis_RMSE_rad_s2': np.sqrt(np.mean(head_error**2, axis=0)).tolist(),
                     'maximum_correction_weight_norm': norm, 'minimum_covariance_eigenvalue': eigen})
    no_wind = [r for r in rows if r['scene_id'].endswith('W15')]
    passed = all(r['late10s_reduction_fraction'] >= .3 for r in no_wind) and (
        sum(r['oracle_vector_RMSE_rad_s2']**2 for r in rows) < sum(r['fixed_vector_RMSE_rad_s2']**2 for r in rows))
    report = {'schema': 'ORACLE_CAUSAL_HEAD_CAPACITY_V1', 'status': 'CAPACITY_SUPPORTED' if passed else 'CAPACITY_GATE_FAILED',
              'Plant_calls': 0, 'training_jobs': 0, 'TEST_read': False,
              'deployed_online_head_validated': False, 'oracle_RBF_labels_used_OFFLINE_ONLY': True,
              'future_label_perturbation_causality_check': True,
              'taskbook_sha256': sha(HERE / 'TASKBOOK.md'), 'source_script_sha256': sha(__file__),
              'manifest_sha256': sha(manifest_path), 'rows': rows,
              'interpretation': 'Representation/linear-head capacity only. RBF labels are not available to a deployed replacement. No closed-loop or stability claim.'}
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
