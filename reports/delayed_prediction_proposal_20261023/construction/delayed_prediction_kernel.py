"""Pure, single-step delayed-raw-prediction proposal; synthetic checks only."""
from __future__ import annotations

import json
import numpy as np

FEATURES, AXES, FIRST_VALID = 33, 3, 320
H, GAMMA, LAMBDA, TAU = 0.01, 12.0, 0.002, 1.0
RHO, BETA_RISE, PLANT_DT = H / TAU, 1.8, 0.001
S_LIMIT = np.array([7.0, 8.0, 10.0])
PRED_LIMIT, WEIGHT_LIMIT = 3.0, 60.0
DEVELOPMENT_FAILURES = [{
    "command": "python -B 'reports/delayed_prediction_proposal_20261023/construction/delayed_prediction_kernel.py'",
    "script_sha256": "f12360a06c75ff80fe38132cd84f375b810d43b5c63b808b55cacc5e343152f2",
    "exit_code": 1, "error": "AssertionError: projection check expected applied output at beta=.5 after clock changed to (n+1)*dt/1.8",
    "resolution": "Compute the expected applied output from the fixed C2 zero-based-index/one-based-beta clock.",
    "plant_or_real_data_used": False,
}]


def _vec(name, value, size):
    a = np.asarray(value, dtype=np.float64)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise ValueError(f"{name} must be a finite ({size},) vector")
    return a


def _beta_clip(raw, beta):
    """The output map also remains well-defined at beta=0."""
    return float(beta) * np.clip(raw, -PRED_LIMIT, PRED_LIMIT)


def delayed_prediction_step(W_k, phi_k, s_eff_k, current_index, current_time_s, *,
                            phi_prev=None, y_prev=None, previous_index=None,
                            previous_time_s=None):
    """Compute raw/applied output, then one joint tracking+leak+prediction projection.

    W is (33,3); feature vectors and signals are 1-D. Previous target must already
    be causal: y_prev=(v[k]-v[j])/0.01 - mean(a_f[j:k]), j=k-10.
    """
    W = np.asarray(W_k, dtype=np.float64)
    if W.shape != (FEATURES, AXES) or not np.isfinite(W).all():
        raise ValueError("W_k must be finite with shape (33,3)")
    phi = _vec("phi_k", phi_k, FEATURES)
    s = _vec("s_eff_k", s_eff_k, AXES)
    if abs(np.linalg.norm(phi) - 1.0) > 1e-10:
        raise ValueError("phi_k must have unit norm")
    if np.any(np.abs(s) > S_LIMIT + 1e-12):
        raise ValueError("s_eff_k must already obey the original axis limits")
    if isinstance(current_index, bool) or int(current_index) != current_index:
        raise ValueError("current_index must be an integer plant-step index")
    k = int(current_index)
    t = float(current_time_s)
    if k < FIRST_VALID or k % 10 or not np.isfinite(t) or t < 0:
        raise ValueError("current event must be a finite nonnegative 100-Hz step")
    if abs(t - k * PLANT_DT) > 1e-12:
        raise ValueError("current time must match current_index * 1 ms")

    supplied = (phi_prev is not None, y_prev is not None,
                previous_index is not None, previous_time_s is not None)
    if any(supplied) and not all(supplied):
        raise ValueError("previous phi/target/index/time must be supplied together")
    has_previous = all(supplied)
    if not has_previous and k != FIRST_VALID:
        raise ValueError("only the first ready event n=320 may omit a previous target")
    pred_grad = np.zeros((FEATURES, AXES), dtype=np.float64)
    prev_raw = prev_residual = None
    if has_previous:
        old_phi = _vec("phi_prev", phi_prev, FEATURES)
        target = _vec("y_prev", y_prev, AXES)
        j = int(previous_index)
        tj = float(previous_time_s)
        if j != previous_index or j < FIRST_VALID or j % 10 or k - j != 10:
            raise ValueError("previous event must be the valid event j=k-10")
        if not np.isfinite(tj) or abs(tj - j * PLANT_DT) > 1e-12:
            raise ValueError("previous time must match previous_index * 1 ms")
        if abs((t - tj) - H) > 1e-12:
            raise ValueError("previous target interval must be exactly 10 ms")
        if abs(np.linalg.norm(old_phi) - 1.0) > 1e-10:
            raise ValueError("phi_prev must have unit norm")
        prev_raw = W.T @ old_phi
        prev_residual = prev_raw - target
        pred_grad = np.outer(old_phi, prev_residual)

    # C2 uses MATLAB one-based k=n+1 while the logged/raw index n is zero-based.
    beta = min((k + 1) * PLANT_DT / BETA_RISE, 1.0)
    raw = W.T @ phi
    applied = _beta_clip(raw, beta)
    candidate = (W - H * GAMMA * beta * np.outer(phi, s)
                 - H * LAMBDA * W - RHO * pred_grad)
    W_next = np.clip(candidate, -WEIGHT_LIMIT, WEIGHT_LIMIT)
    if not (np.isfinite(raw).all() and np.isfinite(applied).all()
            and np.isfinite(W_next).all()):
        raise ValueError("non-finite candidate output")
    return {"raw": raw, "applied": applied, "beta": beta,
            "has_previous": has_previous, "previous_raw": prev_raw,
            "previous_residual": prev_residual,
            "prediction_gradient": pred_grad,
            "preprojection_candidate": candidate, "W_next": W_next}


def _expect_error(fn):
    try:
        fn()
    except (ValueError, TypeError):
        return
    raise AssertionError("invalid input was not rejected")


def self_check():
    rng = np.random.default_rng(20261023)
    W = rng.normal(0.0, 0.2, (FEATURES, AXES))
    phi = np.zeros(FEATURES); phi[0] = 1.0
    original = W.copy()

    # No previous target: exactly the old tracking+leak step at the first raw index.
    first = delayed_prediction_step(W, phi, [1, 2, 3], 320, 0.32)
    old = np.clip(W - H * GAMMA * first["beta"] * np.outer(phi, [1, 2, 3])
                  - H * LAMBDA * W, -WEIGHT_LIMIT, WEIGHT_LIMIT)
    assert not first["has_previous"] and np.array_equal(first["W_next"], old)
    assert first["beta"] == 321 * PLANT_DT / BETA_RISE
    assert np.array_equal(_beta_clip(np.array([3.0, -3.0, 1.0]), 0.0), np.zeros(AXES))
    assert np.array_equal(W, original)

    # Old phi is evaluated with current W; output is computed before this update.
    old_phi = np.zeros(FEATURES); old_phi[1] = 1.0
    target = np.array([0.3, -0.2, 0.1])
    step = delayed_prediction_step(W, phi, [1, 2, 3], 330, 0.33,
                                   phi_prev=old_phi, y_prev=target,
                                   previous_index=320, previous_time_s=0.32)
    assert step["beta"] == 331 * PLANT_DT / BETA_RISE
    assert np.array_equal(step["raw"], W.T @ phi)
    assert np.array_equal(step["previous_raw"], W.T @ old_phi)
    assert not np.array_equal(step["W_next"], W)

    # Central finite difference for 0.5*||W.T*phi_prev-y_prev||^2.
    grad = step["prediction_gradient"]
    eps, max_fd = 1e-6, 0.0
    for i in range(FEATURES):
        for a in range(AXES):
            wp, wm = W.copy(), W.copy()
            wp[i, a] += eps; wm[i, a] -= eps
            lp = 0.5 * np.sum((wp.T @ old_phi - target) ** 2)
            lm = 0.5 * np.sum((wm.T @ old_phi - target) ** 2)
            max_fd = max(max_fd, abs((lp - lm) / (2 * eps) - grad[i, a]))
    assert max_fd < 1e-9

    # One joint projection clips both signs after summing all update terms.
    wb = np.zeros((FEATURES, AXES)); wb[0, :2] = [59.9, -59.9]
    projected = delayed_prediction_step(wb, phi, [-7, 7, 0], 320, 0.32)
    assert projected["preprojection_candidate"][0, 0] > 60
    assert projected["preprojection_candidate"][0, 1] < -60
    assert projected["W_next"][0, 0] == 60 and projected["W_next"][0, 1] == -60
    assert np.array_equal(projected["applied"], projected["beta"] * np.array([3.0, -3.0, 0.0]))

    # Reject malformed shapes, non-10-ms pairing, and mismatched event indices.
    _expect_error(lambda: delayed_prediction_step(W, np.zeros(32), [0, 0, 0], 320, 0.32))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 310, 0.31))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 330, 0.33))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 320, 0.32,
        phi_prev=old_phi, y_prev=target, previous_index=310, previous_time_s=0.31))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 330, 0.33,
        phi_prev=old_phi, y_prev=target, previous_index=321, previous_time_s=0.32))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 330, 0.33,
        phi_prev=old_phi, y_prev=target, previous_index=320, previous_time_s=0.321))
    _expect_error(lambda: delayed_prediction_step(W, phi, [0, 0, 0], 330, 0.33,
        phi_prev=old_phi, y_prev=None, previous_index=320, previous_time_s=0.32))

    return {"status": "PASS_SYNTHETIC_SINGLE_STEP_ONLY", "checks": [
        "only n=320 may omit previous data; that step reduces to tracking+leak law",
        "beta=0 output map returns zero without division; schedule uses C2 one-based clock",
        "raw/applied outputs and previous prediction use pre-update current W",
        "previous innovation gradient passes central finite difference",
        "tracking, leak, and prediction are combined before one box projection",
        "bad shape, later missing previous data, j=310 at n=320, wrong index, and wrong time are rejected",
    ], "max_prediction_gradient_fd_abs_error": max_fd,
       "development_failures": DEVELOPMENT_FAILURES,
       "plant_runtime_model_matlab_execution_or_training_used": False}


if __name__ == "__main__":
    print(json.dumps(self_check(), indent=2))
