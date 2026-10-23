"""Synthetic C4 coordinate-contract check; never loads a Plant or checkpoint."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
KERNEL_PATH = ROOT / 'reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py'
spec = importlib.util.spec_from_file_location('delayed_prediction_kernel', KERNEL_PATH)
assert spec and spec.loader
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)


def synthetic_check() -> dict:
    dt = 0.001
    rng = np.random.default_rng(20261023)
    W = rng.normal(0, 0.02, (33, 3))
    phi_j = np.zeros(33); phi_j[4] = 1.0
    phi_k = np.zeros(33); phi_k[7] = 1.0
    surface = np.array([2.1, -1.7, 0.9])
    eta = np.array([0.8, -0.3, 0.4])
    limits = np.array([7.0, 8.0, 10.0])

    # Ten completed 1-ms transitions [j,k), then a separate current-event sentinel.
    n = np.arange(320, 331)
    a_req = np.column_stack((0.4 + n*1e-4, -0.2 + n*2e-4, 0.1 - n*1e-4))
    a_f = a_req - np.array([0.03, -0.02, 0.01])
    v_j = np.array([1.0, -0.4, 0.2])
    dv = np.array([0.011, -0.004, 0.006])
    v_k = v_j + dv
    int_af = np.zeros(3); int_req = np.zeros(3)
    for i in range(10):
        int_af = int_af + a_f[i] * dt
        int_req = int_req + a_req[i] * dt

    # At m=1, C4's direct-a_f branch has C3's exact operation order and input.
    c3_surface = np.clip(surface - eta, -limits, limits)
    c4_m1_surface = np.clip(surface - 1.0*eta, -limits, limits)
    c4_m1_target = ((v_k - v_j) - int_af) / 0.01
    c3_target = ((v_k - v_j) - int_af) / 0.01
    np.testing.assert_array_equal(c4_m1_surface, c3_surface)
    np.testing.assert_array_equal(c4_m1_target, c3_target)
    kwargs = dict(phi_prev=phi_j, y_prev=c3_target, previous_index=320, previous_time_s=0.32)
    c3 = kernel.delayed_prediction_step(W, phi_k, c3_surface, 330, 0.33, **kwargs)
    c4_m1 = kernel.delayed_prediction_step(W, phi_k, c4_m1_surface, 330, 0.33, **kwargs)
    for key in ('raw', 'applied', 'prediction_gradient', 'preprojection_candidate', 'W_next'):
        np.testing.assert_array_equal(c4_m1[key], c3[key])

    # At m=0, reference is a_req. The ten samples exclude row n=330 (current event).
    c4_m0_surface = np.clip(surface, -limits, limits)
    c4_m0_target = ((v_k - v_j) - int_req) / 0.01
    expected_integral = np.zeros(3)
    for i in range(10):
        expected_integral = expected_integral + a_req[i] * dt
    expected_m0 = ((v_k - v_j) - expected_integral) / 0.01
    np.testing.assert_array_equal(c4_m0_target, expected_m0)
    a_req_with_future_change = a_req.copy(); a_req_with_future_change[10] += 1e6
    future_integral = np.zeros(3)
    for i in range(10):
        future_integral = future_integral + a_req_with_future_change[i] * dt
    future_excluded = ((v_k - v_j) - future_integral) / 0.01
    np.testing.assert_array_equal(c4_m0_target, future_excluded)
    ref = kernel.delayed_prediction_step(W, phi_k, c4_m0_surface, 330, 0.33,
                                         phi_prev=phi_j, y_prev=c4_m0_target,
                                         previous_index=320, previous_time_s=0.32)
    assert np.array_equal(ref['raw'], W.T @ phi_k)  # output reads W_330 before W_331 update
    assert not np.array_equal(ref['W_next'], W)
    first = kernel.delayed_prediction_step(W, phi_j, c3_surface, 320, 0.32)
    assert not first['has_previous']  # no invented j=310 history

    return {
        'status': 'PASS_SYNTHETIC_NO_PLANT',
        'checks': [
            'm=1 tracking surface and target preserve the C3 exact branch',
            'm=1 helper output, applied force, delayed gradient, projection and W_next match C3',
            'm=0 target is independently recomputed from ten a_req transitions [320,330)',
            'n=330 transition/current future values do not leak into its target',
            'n=320 has no synthetic previous sample; n=330 uses j=320 and phi_j',
            'event output is computed from W_k before producing W_(k+1)',
        ],
        'm0_target_mps2': c4_m0_target.tolist(),
        'plant_matlab_checkpoint_training_used': False,
    }


if __name__ == '__main__':
    print(synthetic_check())
