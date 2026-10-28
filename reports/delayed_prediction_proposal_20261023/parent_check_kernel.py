"""Independent synthetic one-step checks; no data/model/runtime loading."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'construction/delayed_prediction_kernel.py'
EXPECTED = '6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED
spec = importlib.util.spec_from_file_location('candidate_for_parent_check', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

w = np.arange(99, dtype=float).reshape(33, 3)/100
unchanged = w.copy()
phi = np.cos(np.arange(33))+1.1
phi /= np.linalg.norm(phi)
past = np.arange(1, 34, dtype=float)
past /= np.linalg.norm(past)
target = np.array([.2, -.1, .4])
surface = np.array([.1, .2, -.3])
out = module.delayed_prediction_step(w, phi, surface, 330, .330,
    phi_prev=past, y_prev=target, previous_index=320, previous_time_s=.320)
beta = 331/1800
raw = np.array([sum(w[i, a]*phi[i] for i in range(33)) for a in range(3)])
past_raw = np.array([sum(w[i, a]*past[i] for i in range(33)) for a in range(3)])
expected_w = np.array([[max(-60., min(60., w[i, a]-.01*12*beta*phi[i]*surface[a]
    -.01*.002*w[i, a]-.01*past[i]*(past_raw[a]-target[a]))) for a in range(3)] for i in range(33)])
assert abs(out['beta']-beta) < 1e-16
assert np.max(np.abs(out['raw']-raw)) < 2e-14
assert np.max(np.abs(out['applied']-beta*np.clip(raw, -3, 3))) < 2e-14
assert np.max(np.abs(out['W_next']-expected_w)) < 2e-14
assert np.array_equal(w, unchanged)
first = module.delayed_prediction_step(w, phi, surface, 320, .320)
assert abs(first['beta']-321/1800) < 1e-16 and not first['has_previous']
assert np.count_nonzero(first['prediction_gradient']) == 0

fd_errors = []
for i in (0, 16, 32):
    for a in range(3):
        def loss(delta):
            prediction = [sum((w[r, c]+(delta if (r, c)==(i, a) else 0))*past[r]
                              for r in range(33)) for c in range(3)]
            return .5*sum((prediction[c]-target[c])**2 for c in range(3))
        fd = (loss(1e-6)-loss(-1e-6))/2e-6
        fd_errors.append(abs(fd-out['prediction_gradient'][i, a]))
assert max(fd_errors) < 1e-8
rejected = []
for name, args, kw in [
    ('later_missing_history', (w, phi, surface, 330, .330), {}),
    ('fabricated_pre_ready_history', (w, phi, surface, 320, .320),
     dict(phi_prev=past, y_prev=target, previous_index=310, previous_time_s=.310))]:
    try:
        module.delayed_prediction_step(*args, **kw)
    except ValueError:
        rejected.append(name)
    else:
        raise AssertionError(name)
result = {'status': 'PASS_PARENT_SYNTHETIC_KERNEL_ONLY', 'candidate_python_sha256': EXPECTED,
          'joint_update_max_abs_difference': float(np.max(np.abs(out['W_next']-expected_w))),
          'dense_feature_coordinate_FD_checks': len(fd_errors), 'max_FD_error': max(fd_errors),
          'rejected_cases': rejected, 'input_weights_unchanged': True,
          'real_data_or_model_used': False, 'MATLAB_executed': False, 'Plant': 0,
          'training_or_optimizer_steps': 0, 'runtime_integration_or_parity_proven': False}
with (HERE/'PARENT_KERNEL_CHECK.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps(result))
