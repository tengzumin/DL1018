"""Independent NumPy reference for 300 composite-head events; synthetic only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

HERE = Path(__file__).resolve().parent
MODEL = (HERE.parents[1] / "mlp15_c5_teacher_full72_v1" / "runs" /
         "C5_MLP15_FULL72_SEED2026102001" / "mlp15_attitude_weights_v1.mat")
FIXTURE = HERE / "fixtures" / "composite_head_fixture.mat"
MODEL_SHA256 = "67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b"
K1 = np.array([1.5, 1.5, 1.3])
J0 = np.array([[0.003257553333333334, -2.168404344971009e-19, 0.0],
               [-2.168404344971009e-19, 0.0032575533333333334, 0.0],
               [0.0, 0.0, 0.006360648333333333]])
DMAX = np.array([45.0, 45.0, 4.7124])


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def euler_map(eta: np.ndarray) -> np.ndarray:
    phi, theta = eta[0], eta[1]
    theta = np.clip(theta, -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4)
    return np.array([[1.0, np.sin(phi) * np.tan(theta), np.cos(phi) * np.tan(theta)],
                     [0.0, np.cos(phi), -np.sin(phi)],
                     [0.0, np.sin(phi) / np.cos(theta),
                      np.cos(phi) / np.cos(theta)]])


def silu(x: np.ndarray) -> np.ndarray:
    return x / (1.0 + np.exp(-np.clip(x, -80.0, 80.0)))


def main() -> None:
    assert sha(MODEL) == MODEL_SHA256, "frozen MLP15 model hash changed"
    model = loadmat(MODEL)
    mean = model["input_mean"].ravel()
    std = model["input_std"].ravel()
    scale = model["target_rms"].ravel()
    count, sample_dt, event_dt = 300, 0.001, 0.010
    time_all = np.arange(3001, dtype=float) * sample_dt
    omega = np.tile([0.15, -0.10, 0.07], (time_all.size, 1))
    eta = np.tile([0.20, -0.15, 0.10], (time_all.size, 1))
    eta_ref = eta + np.array([0.025, -0.020, 0.015])
    eta_rate_ref = np.tile([0.0225, -0.012, 0.006], (time_all.size, 1))
    disturbance = np.column_stack((2.0 * np.sin(0.8 * time_all[:-1]),
                                   -3.0 * np.cos(1.2 * time_all[:-1]),
                                   0.2 * np.sin(0.3 * time_all[:-1])))
    disturbance[time_all[:-1] >= 2.70] += [0.0, 0.0, 10000.0]
    gyro = np.cross(omega[:-1], omega[:-1] @ J0.T)
    torque = (np.diff(omega, axis=0) / sample_dt - disturbance) @ J0.T + gyro

    sample_indices = 11 + 10 * np.arange(count)  # one-based MATLAB indices
    zero_indices = sample_indices - 1
    tracking_T = np.empty((3, 3, count))
    tracking_surface = np.empty((3, count))
    features = np.empty((13, count))
    rng = np.random.default_rng(2026102701)
    for i, k in enumerate(zero_indices):
        T = euler_map(eta[k])
        e = wrap(eta_ref[k] - eta[k])
        tracking_T[:, :, i] = T
        tracking_surface[:, i] = eta_rate_ref[k] + K1 * e - T @ omega[k]
        features[:3, i] = e
        features[3:6, i] = omega[k]
        features[6:9, i] = [0.02, -0.03, 0.01]
        features[9:13, i] = 0.20
    beta = np.minimum(time_all[zero_indices] / 2.2, 1.0)
    event_dt = np.full(count, event_dt)
    event_dt[0] = 0.0

    history = np.zeros((13, 14))
    W = np.zeros((33, 3))
    P = 10.0 * np.eye(33)
    previous_phi: np.ndarray | None = None
    previous_base: np.ndarray | None = None
    previous_beta = 0.0
    outputs = {name: np.zeros((3, count)) for name in
               ("base", "raw", "clipped", "torque", "observed")}
    weights_before = np.zeros((33, 3, count))
    weights_after = np.zeros_like(weights_before)
    tracking_drive = np.zeros_like(weights_before)
    covariance_diagonal = np.zeros((33, count))
    updated = np.zeros(count, dtype=np.uint8)
    tracking_updated = np.zeros(count, dtype=np.uint8)
    projected = np.zeros(count, dtype=np.uint8)
    clipped = np.zeros(count, dtype=np.uint8)
    minimum_cholesky_diagonal = np.inf
    max_cross_cancellation_error = 0.0

    for i, k in enumerate(zero_indices):
        x_norm = (features[:, i] - mean) / std
        window = np.column_stack((history, x_norm))
        history = window[:, 1:]
        hidden = silu(model["fc1_weight"] @ window.ravel(order="F") +
                      model["fc1_bias"].ravel())
        hidden = silu(model["fc2_weight"] @ hidden + model["fc2_bias"].ravel())
        base = (model["head_weight"] @ hidden + model["head_bias"].ravel()) * scale
        phi = np.r_[hidden, 1.0]
        phi /= np.linalg.norm(phi)
        weights_before[:, :, i] = W
        raw = base + scale * (W.T @ phi)
        clip = np.clip(raw, -DMAX, DMAX)
        outputs["base"][:, i] = base
        outputs["raw"][:, i] = raw
        outputs["clipped"][:, i] = clip
        outputs["torque"][:, i] = J0 @ (beta[i] * clip)
        clipped[i] = np.any(np.abs(raw - clip) > 1e-12)

        if i:
            first, last = zero_indices[i - 1], k
            observed = ((omega[last] - omega[first]) / (time_all[last] - time_all[first]) +
                        np.mean(np.linalg.solve(J0, (gyro[first:last] - torque[first:last]).T).T,
                                 axis=0))
            outputs["observed"][:, i] = observed
            if previous_beta >= 1.0 and beta[i] >= 1.0:
                P_prior = P / 0.999
                gain = (P_prior @ previous_phi) / (1.0 + previous_phi @ P_prior @ previous_phi)
                innovation = observed / scale - previous_base - W.T @ previous_phi
                after_rls = W + np.outer(gain, innovation)
                A = np.eye(33) - np.outer(gain, previous_phi)
                P = A @ P_prior @ A.T + np.outer(gain, gain)
                P = (P + P.T) / 2.0
                np.linalg.cholesky(P)
                updated[i] = 1
            else:
                after_rls = W.copy()

            if beta[i] >= 1.0:
                h = beta[i] * scale * (tracking_T[:, :, i].T @ tracking_surface[:, i])
                drive = -np.outer(P @ phi, h)
                tracking_drive[:, :, i] = drive
                after_rls += event_dt[i] * drive
                tracking_updated[i] = 1
            else:
                h = np.zeros(3)
                drive = np.zeros((33, 3))

            magnitude = np.linalg.norm(after_rls)
            if magnitude > 20.0:
                after_rls *= 20.0 / magnitude
                projected[i] = 1
            W = after_rls

            if beta[i] >= 1.0:
                # Independent parameter-metric cancellation check; no clipping.
                probe = rng.normal(0.0, 0.1, (33, 3))
                cross = float((tracking_surface[:, i] @ tracking_T[:, :, i]) @
                              (beta[i] * scale * (probe.T @ phi)))
                metric_rate = float(np.sum(probe * np.linalg.solve(P, drive)))
                max_cross_cancellation_error = max(max_cross_cancellation_error,
                                                   abs(cross + metric_rate))

        weights_after[:, :, i] = W
        covariance_diagonal[:, i] = np.diag(P)
        chol = np.linalg.cholesky(P)
        minimum_cholesky_diagonal = min(minimum_cholesky_diagonal,
                                        float(np.min(np.diag(chol))))
        previous_phi, previous_base = phi, base / scale
        previous_beta = beta[i]

    print("fixture diagnostics:", {"updates": int(updated.sum()),
          "tracking": int(tracking_updated.sum()), "projection": int(projected.sum()),
          "clipped": int(clipped.sum()), "max_abs_raw": float(np.max(np.abs(outputs["raw"]))),
          "max_abs_raw_by_axis": np.max(np.abs(outputs["raw"]), axis=1).tolist(),
          "max_weight_norm": float(np.max(np.linalg.norm(weights_before, axis=(0, 1))))})
    assert np.sum(updated) > 0 and np.sum(tracking_updated) > 0
    assert np.sum(projected) > 0, "synthetic fixture did not exercise the weight projection"
    assert np.sum(clipped) > 0, "synthetic fixture did not exercise dmax clipping"
    assert max_cross_cancellation_error < 1e-11
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    savemat(FIXTURE, {
        "features": features, "omega": omega, "issued_torque": torque,
        "time_all": time_all[:, None], "sample_indices": sample_indices[:, None],
        "beta": beta[:, None], "event_dt": event_dt[:, None], "J0": J0,
        "tracking_T": tracking_T, "tracking_surface": tracking_surface,
        "K1": K1[:, None], "dmax": DMAX[:, None],
        "expected_base": outputs["base"], "expected_raw": outputs["raw"],
        "expected_clipped": outputs["clipped"], "expected_torque": outputs["torque"],
        "expected_observed": outputs["observed"],
        "expected_weight_before": weights_before, "expected_weight_after": weights_after,
        "expected_tracking_drive": tracking_drive,
        "expected_covariance_diagonal": covariance_diagonal,
        "expected_covariance_final": P,
        "expected_updated": updated[:, None],
        "expected_tracking_updated": tracking_updated[:, None],
        "expected_projection": projected[:, None], "expected_clip_active": clipped[:, None],
    }, do_compression=True)
    report = {
        "status": "PASS_SYNTHETIC_NUMPY_REFERENCE",
        "synthetic_events": count,
        "Plant_calls": 0,
        "training_jobs": 0,
        "TEST_read": False,
        "model_sha256": sha(MODEL),
        "fixture_sha256": sha(FIXTURE),
        "script_sha256": sha(Path(__file__)),
        "residual_update_events": int(updated.sum()),
        "tracking_update_events": int(tracking_updated.sum()),
        "projection_events": int(projected.sum()),
        "dmax_clipped_events": int(clipped.sum()),
        "minimum_covariance_cholesky_diagonal": minimum_cholesky_diagonal,
        "max_cross_term_cancellation_error": max_cross_cancellation_error,
    }
    (HERE / "PYTHON_FIXTURE.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
