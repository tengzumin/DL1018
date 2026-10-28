"""Double-precision NumPy reference; synthetic observations, no Plant or training."""
from pathlib import Path
import hashlib
import os
os.environ['MKL_THREADING_LAYER'] = 'SEQUENTIAL'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np
from scipy.io import loadmat, savemat
import json

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent
MODEL = RESEARCH / 'mlp15_c5_teacher_full72_v1/runs/C5_MLP15_FULL72_SEED2026102001/mlp15_attitude_weights_v1.mat'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    destination = HERE / 'HEAD_FIXTURE.mat'
    if destination.exists():
        raise FileExistsError(destination)
    assert sha(MODEL) == '67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b'
    model = loadmat(MODEL)
    mean = model['input_mean'].ravel(); std = model['input_std'].ravel(); scale = model['target_rms'].ravel()
    count = 300; dt = .001
    t = np.arange(10*count+1) * dt
    omega = np.column_stack((.4*np.sin(2*t), .3*np.cos(1.5*t), .1*np.sin(.7*t)))
    J0 = np.diag([.003257553333333334, .0032575533333333334, .006360648333333333])
    disturbance = np.column_stack((2*np.sin(.8*t[:-1]), -3*np.cos(1.2*t[:-1]), .2*np.sin(.3*t[:-1])))
    disturbance[t[:-1]>=2.6] += [2000, -1600, 200]  # Synthetic projection/clipping stress only.
    torque = ((np.diff(omega, axis=0)/dt - disturbance) @ J0.T
              + np.cross(omega[:-1], omega[:-1] @ J0.T))
    indices = 11 + 10*np.arange(count)  # MATLAB one-based state indices.
    beta = np.minimum(indices*dt/2.2, 1.)
    rng = np.random.default_rng(2026102001)
    features = mean[:, None] + std[:, None]*rng.normal(0, .2, (13, count))
    features[:3] = np.clip(features[:3], -.2, .2)
    features[3:6] = omega[indices-1].T
    features[9:13] = np.clip(features[9:13], .15, .25)
    history = np.zeros((13, 14)); W = np.zeros((33, 3)); P = 10*np.eye(33)
    previous_phi = previous_base = None
    outputs = {name: np.zeros((3, count)) for name in ['base', 'raw', 'clipped', 'torque', 'observed']}
    before = np.zeros((33, 3, count)); after = np.zeros_like(before)
    projected = np.zeros(count); updated = np.zeros(count)
    for i, index in enumerate(indices):
        current = (features[:, i]-mean)/std
        window = np.column_stack((history, current)); history = window[:, 1:]
        z = model['fc1_weight'] @ window.ravel(order='F') + model['fc1_bias'].ravel()
        z = z/(1+np.exp(-z))
        z = model['fc2_weight'] @ z + model['fc2_bias'].ravel(); z = z/(1+np.exp(-z))
        base_norm = model['head_weight'] @ z + model['head_bias'].ravel()
        base = base_norm*scale; phi = np.r_[z, 1.]; phi /= np.linalg.norm(phi)
        before[:, :, i] = W
        raw = base + scale*(W.T @ phi)
        dmax = np.asarray([45,45,4.7124])
        clipped = np.clip(raw, -dmax, dmax)
        outputs['base'][:, i] = base;outputs['raw'][:, i] = raw;outputs['clipped'][:, i] = clipped
        outputs['torque'][:, i] = J0 @ (beta[i]*clipped)
        if i:
            first = indices[i-1]-1; last = index-1
            observed = ((omega[last]-omega[first])/(t[last]-t[first])
                        + np.mean((np.cross(omega[first:last], omega[first:last] @ J0.T)-torque[first:last]) @ np.linalg.inv(J0).T, axis=0))
            assert np.max(np.abs(observed-disturbance[first:last].mean(axis=0))) < 1e-9
            outputs['observed'][:, i] = observed
            if beta[i-1] >= 1 and beta[i] >= 1:
                prior = P/.999
                gain = (prior @ previous_phi)/(1 + previous_phi @ prior @ previous_phi)
                innovation = observed/scale - previous_base - W.T @ previous_phi
                W = W + np.outer(gain, innovation)
                A = np.eye(33) - np.outer(gain, previous_phi)
                P = A @ prior @ A.T + np.outer(gain, gain); P = (P+P.T)/2
                np.linalg.cholesky(P)
                norm = np.linalg.norm(W)
                if norm > 20:
                    W *= 20/norm; projected[i] = 1
                updated[i] = 1
        after[:, :, i] = W
        previous_phi = phi; previous_base = base_norm
    assert projected.sum() > 0
    savemat(destination, {'features': features, 'omega': omega, 'issued_torque': torque,
                         'time_all': t[:, None], 'sample_indices': indices[:, None],
                         'beta': beta[:, None], 'J0': J0, 'expected_weight_before': before,
                         'expected_weight_after': after, 'expected_covariance_final': P,
                         'expected_projection': projected[:, None], 'expected_updated': updated[:, None],
                         **{f'expected_{key}': value for key, value in outputs.items()}})
    result = {'Plant_calls': 0, 'training_jobs': 0, 'TEST_read': False, 'synthetic_events': count,
              'synthetic_projection_events': int(projected.sum()), 'fixture_sha256': sha(destination),
              'model_sha256': sha(MODEL), 'script_sha256': sha(__file__)}
    (HERE / 'PYTHON_FIXTURE.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
