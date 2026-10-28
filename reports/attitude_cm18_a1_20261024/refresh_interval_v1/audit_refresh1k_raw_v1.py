"""Independent numeric audit for one completed CM18 1-kHz refresh raw MAT."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUTDIR = ROOT / "reports" / "attitude_cm18_a1_20261024" / "refresh_interval_v1"
MODEL_PATH = ROOT / "experiments" / "attitude_cm18_a1_20261024" / "deployment_v1" / "deployment_parameters_v1.json"
MODEL_SHA256 = "ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae"
CHECKPOINT_SHA256 = "105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4"
N = 20_000
DT = 0.001
N_EVENT = N - 10
REFRESH_ROWS = np.arange(10, N, dtype=np.int64)  # MATLAB k = 11:20000
LEGACY_ROWS = np.arange(10, 19_991, 10, dtype=np.int64)  # MATLAB k = 11:10:19991
TOL = 1e-10
MAX_FAILURE_ROWS = 30


class AuditError(RuntimeError):
    pass


def need(ok: bool, message: str) -> None:
    if not ok:
        raise AuditError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def mat(f: h5py.File, key: str) -> np.ndarray:
    if key not in f:
        raise AuditError(f"raw MAT is missing {key}")
    value = np.asarray(f[key])
    return value.T if value.ndim == 2 else value


def vec(f: h5py.File, key: str, dtype=np.float64) -> np.ndarray:
    return np.asarray(mat(f, key), dtype=dtype).reshape(-1)


def scalar(f: h5py.File, key: str):
    if key not in f:
        raise AuditError(f"raw MAT is missing {key}")
    return np.asarray(f[key]).reshape(-1)[0].item()


def text(f: h5py.File, key: str) -> str:
    if key not in f:
        raise AuditError(f"raw MAT is missing {key}")
    item = f[key]
    if bool(item.attrs.get("MATLAB_empty", False)):
        return ""
    value = np.asarray(item)
    if value.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in value.reshape(-1)).rstrip("\x00").rstrip()
    if value.dtype.kind in "SU":
        return "".join(x.decode() if isinstance(x, bytes) else str(x) for x in value.reshape(-1)).rstrip("\x00").rstrip()
    return str(value.reshape(-1)[0]).rstrip()


def close_max(a, b) -> float:
    return float(np.max(np.abs(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64))))


def track_delta(name, actual, expected, tolerance, matlab_rows, maxima, failures):
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    matlab_rows = np.asarray(matlab_rows, dtype=np.int64).reshape(-1)
    if actual.ndim == 1 and matlab_rows.size == 1:
        actual = actual.reshape(1, -1)
        expected = expected.reshape(1, -1)
    need(actual.shape == expected.shape, f"{name}: shape {actual.shape} != {expected.shape}")
    delta = np.abs(actual - expected)
    need(np.isfinite(delta).all(), f"{name}: non-finite comparison delta")
    if delta.size:
        flat = int(np.argmax(delta))
        loc = np.unravel_index(flat, delta.shape)
        maximum = float(delta[loc])
        if name not in maxima or maximum > maxima[name]["max_abs"]:
            maxima[name] = {
                "max_abs": maximum,
                "matlab_transition_index": int(matlab_rows[loc[0]]) if delta.ndim else None,
                "component_index_1based": int(loc[-1] + 1) if delta.ndim > 1 else None,
            }
        if maximum > tolerance:
            row_bad = np.any(delta > tolerance, axis=tuple(range(1, delta.ndim))) if delta.ndim > 1 else delta > tolerance
            bad = np.flatnonzero(row_bad)
            prior = failures.get(name, {"count": 0, "matlab_transition_indices_first": [], "tolerance": float(tolerance)})
            indices = prior["matlab_transition_indices_first"] + [int(matlab_rows[i]) for i in bad]
            failures[name] = {
                "count": int(prior["count"] + bad.size),
                "matlab_transition_indices_first": indices[:MAX_FAILURE_ROWS],
                "tolerance": float(tolerance),
            }
    return delta


def track_flags(name, actual, expected, matlab_rows, failures):
    actual = np.asarray(actual, dtype=bool).reshape(-1)
    expected = np.asarray(expected, dtype=bool).reshape(-1)
    need(actual.shape == expected.shape, f"{name}: flag shape mismatch")
    bad = np.flatnonzero(actual != expected)
    if bad.size:
        failures[name] = {
            "count": int(bad.size),
            "matlab_transition_indices_first": [int(matlab_rows[i]) for i in bad[:MAX_FAILURE_ROWS]],
        }


def forward(x: np.ndarray, p: dict) -> np.ndarray:
    mu = np.asarray(p["input_mean"], dtype=np.float64).reshape(18)
    sigma = np.asarray(p["input_std"], dtype=np.float64).reshape(18)
    axis_rms = np.asarray(p["train_axis_rms_rad_s2"], dtype=np.float64).reshape(3)
    h1 = np.tanh(np.asarray(p["W1"], dtype=np.float64) @ ((x - mu) / sigma) + np.asarray(p["b1"], dtype=np.float64).reshape(32))
    h2 = np.tanh(np.asarray(p["W2"], dtype=np.float64) @ h1 + np.asarray(p["b2"], dtype=np.float64).reshape(32))
    coefficients = (np.asarray(p["W3"], dtype=np.float64) @ h2 + np.asarray(p["b3"], dtype=np.float64).reshape(24)).reshape(3, 8)
    basis = np.r_[x[11:15] / 2.0, x[7:11]]
    return (coefficients @ basis) * axis_rms


def rotation_zyx(euler: np.ndarray) -> np.ndarray:
    phi, theta, yaw = np.asarray(euler, dtype=np.float64)
    cp, sp = np.cos(phi), np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.array([
        [cy * ct, cy * st * sp - sy * cp, cy * st * cp + sy * sp],
        [sy * ct, sy * st * sp + cy * cp, sy * st * cp - cy * sp],
        [-st, ct * sp, ct * cp],
    ])


def run_lengths(mask: np.ndarray, dt_s: float) -> tuple[float, float]:
    mask = np.asarray(mask, dtype=bool).reshape(-1)
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    stops = np.flatnonzero(edges == -1) - 1
    if starts.size == 0:
        return 0.0, 0.0
    durations = (stops - starts + 1) * dt_s
    return float(np.max(durations)), float(durations[-1] if mask[-1] else 0.0)


def score(time, state, ref_position, eta_ref, rate_ref):
    state_left = state[:N]
    pos_error = ref_position[:N] - state_left[:, :3]
    eta_actual = state_left[:, 6:9]
    omega_actual = state_left[:, 9:12]
    euler_error = np.arctan2(np.sin(eta_ref - eta_actual), np.cos(eta_ref - eta_actual))
    so3 = np.zeros(N)
    rate_error = np.zeros((N, 3))
    tilt = np.zeros(N)
    for i in range(N):
        ra = rotation_zyx(eta_actual[i])
        rr = rotation_zyx(eta_ref[i])
        rerr = ra.T @ rr
        cosine = float(np.clip((np.trace(rerr) - 1.0) / 2.0, -1.0, 1.0))
        sine = 0.5 * float(np.linalg.norm([
            rerr[2, 1] - rerr[1, 2], rerr[0, 2] - rerr[2, 0], rerr[1, 0] - rerr[0, 1],
        ]))
        so3[i] = np.arctan2(sine, cosine)
        phi, theta = eta_ref[i, :2]
        a, b, c = rate_ref[i]
        omega_ref_body = np.array([
            a - np.sin(theta) * c,
            np.cos(phi) * b + np.sin(phi) * np.cos(theta) * c,
            -np.sin(phi) * b + np.cos(phi) * np.cos(theta) * c,
        ])
        rate_error[i] = omega_actual[i] - rerr @ omega_ref_body
        tilt[i] = np.arccos(np.clip(ra[2, 2], -1.0, 1.0))

    masks = {
        "ALL_0_20": (time[:N] >= 0.0) & (time[:N] < 20.0),
        "PRE_0_5": (time[:N] >= 0.0) & (time[:N] < 5.0),
        "POST_5_20": (time[:N] >= 5.0) & (time[:N] < 20.0),
    }
    rows = {}
    for name, mask in masks.items():
        pe, ee, se, we = pos_error[mask], euler_error[mask], so3[mask], rate_error[mask]
        rows[name] = {
            "samples": int(np.count_nonzero(mask)),
            "position_Q_rmse_m": float(np.sqrt(np.mean(np.sum(pe * pe, axis=1)))),
            "position_axis_rmse_m": np.sqrt(np.mean(pe * pe, axis=0)).tolist(),
            "position_peak_m": float(np.max(np.linalg.norm(pe, axis=1))),
            "SO3_rmse_rad": float(np.sqrt(np.mean(se * se))),
            "SO3_peak_rad": float(np.max(se)),
            "SO3_rmse_deg": float(np.rad2deg(np.sqrt(np.mean(se * se)))),
            "SO3_peak_deg": float(np.rad2deg(np.max(se))),
            "Euler_axis_rmse_rad": np.sqrt(np.mean(ee * ee, axis=0)).tolist(),
            "transported_body_rate_rmse_rad_s": np.sqrt(np.mean(we * we, axis=0)).tolist(),
            "transported_body_rate_vector_rmse_rad_s": float(np.sqrt(np.mean(np.sum(we * we, axis=1)))),
            "transported_body_rate_peak_rad_s": float(np.max(np.linalg.norm(we, axis=1))),
        }
    pos_norm = np.linalg.norm(pos_error, axis=1)
    rate_norm = np.linalg.norm(omega_actual, axis=1)
    pos_run, pos_tail = run_lengths(pos_norm > 1.0, DT)
    tilt_run, tilt_tail = run_lengths(tilt > np.pi / 3.0, DT)
    rate_run, rate_tail = run_lengths(rate_norm > 20.0, DT)
    return rows, {
        "position_error_peak_m": float(np.max(pos_norm)),
        "thrust_axis_tilt_peak_rad": float(np.max(tilt)),
        "actual_body_rate_peak_rad_s": float(np.max(rate_norm)),
        "position_error_max_consecutive_s": pos_run,
        "tilt_max_consecutive_s": tilt_run,
        "body_rate_max_consecutive_s": rate_run,
        "logged_trailing_persistence_s": {
            "position": float(pos_tail), "tilt": float(tilt_tail), "body_rate": float(rate_tail),
        },
    }


def audit_raw(raw_path: Path, model: dict, raw_sha: str) -> dict:
    maxima, failures = {}, {}
    model_parameters = model["parameters"]
    with h5py.File(raw_path, "r") as f:
        need(all(k in f for k in ("log", "scene", "runStart")), "raw MAT lacks log/scene/runStart groups")
        need(text(f, "log/status") == "STABLE" and int(scalar(f, "log/last_transition")) == N, "run did not finish 20,000 stable transitions")
        need(text(f, "log/safety_stop_reason") == "", "engine recorded a safety stop")
        need(text(f, "log/cm18_model_profile") == "CM18_A1_MLP32x32_TO24_FIXED_J0", "unexpected CM18 model profile")
        need(text(f, "log/cm18_refresh_candidate") == "A1_REFRESH1K_DIAGNOSTIC", "unexpected refresh candidate")
        need(abs(float(scalar(f, "log/cm18_refresh_rate_hz")) - 1000.0) < 1e-12, "logged refresh rate is not 1000 Hz")
        need(int(scalar(f, "log/cm18_refresh_period_plant_steps")) == 1, "refresh period is not one Plant step")
        need(int(scalar(f, "log/cm18_refresh_expected_event_count")) == N_EVENT, "logged expected refresh count is incorrect")

        for key in ("cm18_rbf_attitude_runtime_enabled", "cm18_rbf_attitude_output_enabled", "cm18_rbf_attitude_update_enabled", "attitude_fusion_enabled", "attitude_head_enabled"):
            need(not bool(scalar(f, "log/" + key)), f"{key} must remain disabled")
        for key in ("rbf_attitude_enabled", "rbf_attitude_output_enabled", "rbf_attitude_update_enabled"):
            need(not bool(scalar(f, "runStart/opts/" + key)), f"runStart opts/{key} must remain disabled")
        need(bool(scalar(f, "runStart/opts/cm18_attitude_v1/enabled")), "runStart CM18 option is disabled")
        runtime_model = "runStart/opts/cm18_attitude_v1/model"
        for name, expected in model_parameters.items():
            actual = mat(f, runtime_model + "/" + name)
            need(actual.size == np.asarray(expected).size and close_max(actual.reshape(-1), np.asarray(expected, dtype=np.float64).reshape(-1)) == 0.0,
                 f"runtime model parameter {name} differs from pinned deployment JSON")
        for key in ("rbf_update_flag", "rbf_attitude_output_limit_active"):
            need(not np.asarray(mat(f, "log/" + key), dtype=bool).any(), f"disabled RBF field {key} is active")
        for key in ("rbf_update_dt", "rbf_output_raw", "rbf_output_unclipped", "rbf_output_held", "attitude_rbf_compensation_torque_Nm"):
            need(np.all(np.asarray(mat(f, "log/" + key), dtype=np.float64) == 0.0), f"disabled RBF field {key} is nonzero")

        time = vec(f, "log/time")
        transition_time = vec(f, "log/transition_time")
        state = np.asarray(mat(f, "log/state"), dtype=np.float64)
        ref_position = np.asarray(mat(f, "log/reference/position"), dtype=np.float64)
        eta_ref = np.asarray(mat(f, "log/filtered_attitude_reference"), dtype=np.float64)
        rate_ref = np.asarray(mat(f, "log/filtered_attitude_rate"), dtype=np.float64)
        command = np.asarray(mat(f, "scene/arms/command"), dtype=np.float64)
        logged_command = np.asarray(mat(f, "log/arms/command"), dtype=np.float64)
        requested = np.asarray(mat(f, "log/requested_generalized"), dtype=np.float64)
        nominal = np.asarray(mat(f, "log/attitude_bs_nominal_torque_Nm"), dtype=np.float64)
        need(time.shape == (N + 1,) and transition_time.shape == (N,) and state.shape == (N + 1, 12) and
             ref_position.shape == (N + 1, 3) and eta_ref.shape == (N, 3) and rate_ref.shape == (N, 3) and
             command.shape == (N + 1, 4) and logged_command.shape == command.shape and requested.shape == (N, 4) and
             nominal.shape == (N, 3), "timeline/controller arrays have unexpected dimensions")
        need(all(np.isfinite(x).all() for x in (time, transition_time, state, ref_position, eta_ref, rate_ref, command, requested, nominal)),
             "timeline/controller data contain non-finite values")
        dt_s = float(scalar(f, "runStart/cfg/plant/dt"))
        mass = float(scalar(f, "runStart/cfg/plant/mass"))
        need(abs(dt_s - DT) < 1e-15 and abs(time[0]) < 1e-12 and abs(time[-1] - 20.0) < 1e-12 and
             close_max(np.diff(time), np.full(N, DT)) < 1e-12 and close_max(transition_time, time[:-1]) < 1e-12,
             "timebase must be 1 ms over [0,20] with transition-left alignment")
        need(close_max(command, logged_command) == 0.0, "logged arm command differs from raw scene command")

        event = np.asarray(mat(f, "log/cm18_event_flag"), dtype=bool).reshape(-1)
        expected_event = np.zeros(N, dtype=bool)
        expected_event[REFRESH_ROWS] = True
        need(event.shape == (N,), "CM18 refresh event flag must have 20,000 transition rows")
        bad_refresh = np.flatnonzero(event != expected_event)
        need(bad_refresh.size == 0,
             f"CM18 refresh schedule mismatch at MATLAB transition indices {((bad_refresh[:MAX_FAILURE_ROWS] + 1).tolist())}")
        need(int(scalar(f, "log/cm18_event_count")) == N_EVENT, "CM18 event count is not 19,990")
        for name in ("position_event_flag", "attitude_event_flag"):
            flag = np.asarray(mat(f, "log/" + name), dtype=bool).reshape(-1)
            expected = np.zeros(N, dtype=bool)
            expected[LEGACY_ROWS] = True
            need(flag.shape == (N,), f"{name} must have 20,000 transition rows")
            bad_legacy = np.flatnonzero(flag != expected)
            need(bad_legacy.size == 0,
                 f"{name} schedule mismatch at MATLAB transition indices {((bad_legacy[:MAX_FAILURE_ROWS] + 1).tolist())}")

        J0 = np.asarray(mat(f, "log/cm18_fixed_inertia_J0_kgm2"), dtype=np.float64)
        dmax = vec(f, "log/cm18_dmax_rad_s2")
        dmax_cfg = vec(f, "runStart/cfg/rbf/attitude/dmax")
        tau = float(scalar(f, "log/cm18_beta_rise_time_s"))
        tau_cfg = float(scalar(f, "runStart/cfg/rbf/attitude/beta_rise_time"))
        need(J0.shape == (3, 3) and np.isfinite(J0).all() and np.linalg.eigvalsh((J0 + J0.T) / 2.0).min() > 0.0,
             "fixed J0 must be finite positive definite 3x3")
        need(np.array_equal(dmax, np.array([45.0, 45.0, 4.7124])) and close_max(dmax, dmax_cfg) == 0.0,
             "CM18 dmax differs from the frozen A1 axis limits")
        need(abs(tau - 2.2) < 1e-15 and abs(tau - tau_cfg) < 1e-15, "CM18 beta rise time is not the frozen 2.2-s value")

        event_only = {
            "input18": ("cm18_event_input_18", 18),
            "z": ("cm18_event_z_before_4", 4),
            "u": ("cm18_event_u_current_4", 4),
            "a_previous": ("cm18_event_a_previous_requested_torque_mean_Nm", 3),
            "raw_forward": ("cm18_event_raw_acceleration_rad_s2", 3),
            "clipped_forward": ("cm18_event_clipped_acceleration_rad_s2", 3),
        }
        event_data = {}
        for label, (key, width) in event_only.items():
            data = np.asarray(mat(f, "log/" + key), dtype=np.float64)
            need(data.shape == (N, width) and np.isfinite(data[event]).all() and np.isnan(data[~event]).all(),
                 f"{key} must be finite on refresh events and NaN elsewhere")
            event_data[label] = data
        interval = vec(f, "log/cm18_event_interval_s")
        expected_interval = np.r_[0.010, np.full(N_EVENT - 1, DT)]
        need(interval.shape == (N,) and np.all(interval[~event] == 0.0), "refresh interval log has invalid off-event values")
        track_delta("refresh_interval_s", interval[event], expected_interval, 1e-12, REFRESH_ROWS + 1, maxima, failures)

        z_expected = np.vstack((np.zeros(4), np.cumsum(command[:-1] * dt_s, axis=0)))
        expected_acc = np.zeros((N, 3))
        expected_beta = np.zeros(N)
        expected_torque = np.zeros((N, 3))
        expected_clip_flag = np.zeros(N, dtype=bool)
        current_acc = np.zeros(3)
        current_beta = 0.0
        current_torque = np.zeros(3)
        current_clip = False
        event_rows = REFRESH_ROWS
        for i in event_rows:
            omega = state[i, 9:12]
            # Recover alpha_BS from logged fixed-J0 nominal torque; this is not a BS source re-execution.
            alpha_bs = np.linalg.solve(J0, nominal[i] - np.cross(omega, J0 @ omega))
            past = slice(i - 10, i)
            weights = np.diff(time[i - 10:i + 1])
            need(weights.shape == (10,) and np.all(weights > 0.0) and abs(float(np.sum(weights)) - 0.010) < 1e-12,
                 f"event at MATLAB transition {i + 1} lacks a completed 10-ms past window")
            a_previous = np.sum(requested[past, 1:4] * weights[:, None], axis=0) / np.sum(weights)
            z_before = z_expected[i]
            u_current = command[i]
            x18 = np.r_[omega, alpha_bs, requested[i, 0] / mass, u_current, z_before, a_previous]
            raw_output = forward(x18, model_parameters)
            clipped = np.clip(raw_output, -dmax, dmax)
            beta = min((i + 1) * dt_s / tau, 1.0)
            current_acc = beta * clipped
            current_torque = J0 @ current_acc
            current_beta = beta
            current_clip = bool(np.any(raw_output != clipped))

            track_delta("X18", event_data["input18"][i], x18, TOL, np.array([i + 1]), maxima, failures)
            track_delta("z_before", event_data["z"][i], z_before, TOL, np.array([i + 1]), maxima, failures)
            track_delta("u_current", event_data["u"][i], u_current, TOL, np.array([i + 1]), maxima, failures)
            track_delta("a_previous", event_data["a_previous"][i], a_previous, TOL, np.array([i + 1]), maxima, failures)
            track_delta("alpha_BS_inverse", event_data["input18"][i, 3:6], alpha_bs, TOL, np.array([i + 1]), maxima, failures)
            track_delta("forward_raw", event_data["raw_forward"][i], raw_output, TOL, np.array([i + 1]), maxima, failures)
            track_delta("forward_clip", event_data["clipped_forward"][i], clipped, TOL, np.array([i + 1]), maxima, failures)
            expected_clip_flag[i] = current_clip
            expected_acc[i] = current_acc
            expected_beta[i] = current_beta
            expected_torque[i] = current_torque
            expected_clip_flag[i] = current_clip
        # Carry each event's held output through all intervening Plant transitions.
        held_acc = np.zeros(3)
        held_beta = 0.0
        held_torque = np.zeros(3)
        held_clip = False
        for i in range(N):
            if event[i]:
                held_acc = expected_acc[i]
                held_beta = expected_beta[i]
                held_torque = expected_torque[i]
                held_clip = expected_clip_flag[i]
            expected_acc[i] = held_acc
            expected_beta[i] = held_beta
            expected_torque[i] = held_torque
            expected_clip_flag[i] = held_clip

        logged_acc = np.asarray(mat(f, "log/cm18_applied_acceleration_held_rad_s2"), dtype=np.float64)
        logged_beta = vec(f, "log/cm18_beta_held")
        logged_torque = np.asarray(mat(f, "log/cm18_compensation_torque_held_Nm"), dtype=np.float64)
        logged_clip = np.asarray(mat(f, "log/cm18_clip_flag_held"), dtype=bool).reshape(-1)
        applied_torque = np.asarray(mat(f, "log/attitude_compensation_applied_torque_Nm"), dtype=np.float64)
        matlab_rows = np.arange(1, N + 1, dtype=np.int64)
        track_delta("held_acceleration", logged_acc, expected_acc, TOL, matlab_rows, maxima, failures)
        track_delta("held_beta", logged_beta, expected_beta, 1e-12, matlab_rows, maxima, failures)
        track_delta("held_torque", logged_torque, expected_torque, TOL, matlab_rows, maxima, failures)
        track_delta("applied_compensation_torque", applied_torque, expected_torque, TOL, matlab_rows, maxima, failures)
        track_flags("held_clip_flag", logged_clip, expected_clip_flag, matlab_rows, failures)
        track_delta("nominal_minus_compensation", requested[:, 1:4], nominal - expected_torque, TOL, matlab_rows, maxima, failures)

        motor_sat = np.asarray(mat(f, "log/motor_saturated"), dtype=bool)
        generalized_clip = np.asarray(mat(f, "log/generalized_clipped"), dtype=bool)
        tilt_limited = np.asarray(mat(f, "log/tilt_limited"), dtype=bool).reshape(-1)
        need(motor_sat.shape == (N, 4) and generalized_clip.shape == (N, 4) and tilt_limited.shape == (N,),
             "motor/generalized/tilt saturation arrays have unexpected dimensions")
        score_rows, safety = score(time, state, ref_position, eta_ref, rate_ref)
        need(max(safety["position_error_max_consecutive_s"], 0.0) < 0.2 and
             safety["tilt_max_consecutive_s"] < 0.1 and safety["body_rate_max_consecutive_s"] < 0.05,
             "recomputed safety persistence reaches an engine stop threshold")
        logged_safety = {
            "position": float(scalar(f, "log/safety_position_error_persistence_s")),
            "tilt": float(scalar(f, "log/safety_tilt_persistence_s")),
            "body_rate": float(scalar(f, "log/safety_body_rate_persistence_s")),
        }
        need(max(abs(logged_safety[k] - safety["logged_trailing_persistence_s"][k]) for k in logged_safety) <= 1e-12,
             "engine trailing safety persistence counters disagree with independent recomputation")
        safety["logged_trailing_persistence_s"] = logged_safety

        return {
            "schema": "ROOT_CM18_REFRESH1K_NUMERICAL_RAW_AUDIT_V1",
            "status": "PASS" if not failures else "FAIL",
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "raw_path": str(raw_path),
            "raw_sha256": raw_sha,
            "deployment_model_sha256": MODEL_SHA256,
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "selected_step": int(model["identity"]["selected_step"]),
            "scope_note": "Numeric raw/model/score audit only; ROOT separately checks run release and source identity.",
            "sample_alignment": "20,000 transition-left rows; t=20 terminal state excluded from scoring.",
            "alpha_BS_note": "Recovered using solve(J0, nominal_torque - cross(omega, J0*omega)); this is not an independent attitude_bs_step source re-execution.",
            "schedule": {
                "refresh_event_count": int(np.count_nonzero(event)),
                "refresh_matlab_index_first_last": [11, 20000],
                "first_interval_s": float(interval[event][0]),
                "subsequent_interval_s": float(interval[event][1]),
                "legacy_position_event_count": int(np.count_nonzero(np.asarray(mat(f, "log/position_event_flag"), dtype=bool))),
                "legacy_attitude_event_count": int(np.count_nonzero(np.asarray(mat(f, "log/attitude_event_flag"), dtype=bool))),
            },
            "max_abs_deltas": maxima,
            "failure_indices": failures,
            "scores": score_rows,
            "safety": safety,
            "actuator_counts": {
                "motor_saturated_count_by_motor": np.count_nonzero(motor_sat, axis=0).astype(int).tolist(),
                "motor_saturated_transition_count": int(np.count_nonzero(np.any(motor_sat, axis=1))),
                "generalized_clipped_count_by_axis": np.count_nonzero(generalized_clip, axis=0).astype(int).tolist(),
                "generalized_clipped_transition_count": int(np.count_nonzero(np.any(generalized_clip, axis=1))),
                "tilt_limited_transition_count": int(np.count_nonzero(tilt_limited)),
                "cm18_clipped_event_count": int(np.count_nonzero(expected_clip_flag & event)),
                "cm18_clip_held_transition_count": int(np.count_nonzero(expected_clip_flag)),
            },
            "terminal_status": text(f, "log/status"),
            "safety_stop_reason": text(f, "log/safety_stop_reason"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="Completed refresh1k raw_run.mat")
    parser.add_argument("--output", type=Path, required=True, help="New JSON path under this report directory; existing files are never overwritten")
    args = parser.parse_args()
    raw_path = args.raw.expanduser().resolve()
    output = args.output.expanduser()
    output = (ROOT / output).resolve() if not output.is_absolute() else output.resolve()
    need(output.parent == OUTDIR.resolve(), "output JSON must be directly inside reports/.../refresh_interval_v1")
    need(output != raw_path and output != MODEL_PATH.resolve(), "output path must not overwrite raw or deployment model")
    need(not output.exists(), f"refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "schema": "ROOT_CM18_REFRESH1K_NUMERICAL_RAW_AUDIT_V1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "raw_path": str(raw_path),
        "deployment_model_path": str(MODEL_PATH),
    }
    try:
        need(MODEL_PATH.is_file() and sha256(MODEL_PATH).lower() == MODEL_SHA256, "pinned deployment JSON is missing or SHA256 differs")
        model = json.loads(MODEL_PATH.read_text(encoding="utf-8-sig"))
        need(model.get("schema") == "CM18_A1_DEPLOYMENT_PARAMETERS_V1" and
             model.get("identity", {}).get("checkpoint_sha256", "").lower() == CHECKPOINT_SHA256 and
             int(model.get("identity", {}).get("selected_step", -1)) == 30000,
             "deployment schema/checkpoint/selected-step does not match the fixed model")
        result.update({"deployment_model_sha256": MODEL_SHA256, "checkpoint_sha256": CHECKPOINT_SHA256, "selected_step": 30000})
        if not raw_path.is_file():
            result.update({"status": "INCOMPLETE", "reason": "raw_run.mat is absent; no raw was opened and PASS is impossible."})
            code = 2
        else:
            raw_digest = sha256(raw_path)
            result = audit_raw(raw_path, model, raw_digest)
            code = 0 if result["status"] == "PASS" else 1
    except Exception as exc:
        result.update({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
        code = 1
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "report": str(output), "raw_path": str(raw_path)}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
