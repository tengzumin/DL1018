"""Causal command-governor replay over locked DEV/VAL full72 raw logs.

No Plant is integrated. Only explicit DEV/VAL raw_run.mat files and the
allowlisted datasets below are read; in particular, no wind or TEST data is
loaded. Parent a_req is replayed as an exogenous current input, so candidate
metrics are interface diagnostics, not closed-loop performance estimates.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import h5py
import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[3]
RAW_ROOT = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/runs"
OUT = pathlib.Path(__file__).resolve().parent / "FILTER_PCF_GOVERNOR_DEVHF6_v1.json"

HF6 = [
    "DL1018_DEV_T1_C10_W09",
    "DL1018_VAL_T1_C07_W14",
    "DL1018_DEV_T2_C09_W10",
    "DL1018_VAL_T2_C04_W14",
    "DL1018_DEV_T3_C09_W09",
    "DL1018_VAL_T3_C01_W14",
]

# Other parent-GRU DEV scene IDs form a pooled development budget. This is not a
# separate TRAIN set and may share T1/T2/T3 reference profiles with the HF6 cohort.
HF_DEV = {sid for sid in HF6 if sid.startswith("DL1018_DEV_")}
CALIBRATION_IDS = sorted(
    p.parent.name
    for p in RAW_ROOT.glob("DL1018_DEV_T*_C*_W*/raw_run.mat")
    if p.parent.name not in HF_DEV and "TEST" not in p.parent.name
)

DT_EXPECTED = 1e-3
MASS = 0.695
GRAVITY = 9.8
WN = np.array([18.0, 18.0, 12.0])
ZETA = np.ones(3)
# Locked C5 snapshot (not default_config.m): x/y unbounded; yaw acceleration <= 6.
ACCEL_LIMIT = np.array([np.inf, np.inf, 6.0])
PCF_K2 = np.array([4.0, 4.0, 4.0])
MAX_TILT = np.deg2rad(30.0)
GOVERNOR_GRID = np.linspace(0.0, 1.0, 101)  # alpha=0 position direction; alpha=1 scored task attitude

LOG_FIELDS = (
    "state",
    "command_filter_target_euler",
    "filtered_attitude_reference",
    "filtered_attitude_rate",
    "command_filter_acceleration_request_unclamped_rads2",
    "command_filter_acceleration_applied_rads2",
    "stage1_position_pcf_a_req_mps2",
    "stage1_position_pcf_a_f_mps2",
    "stage1_position_pcf_r_f_mps2",
    "stage1_position_pcf_eta_after_mps",
)


def _mat_array(dataset: h5py.Dataset) -> np.ndarray:
    a = np.asarray(dataset)
    if a.ndim == 2 and a.shape[0] < a.shape[1]:
        return a.T
    return a


def _wrap(angle: np.ndarray | float) -> np.ndarray:
    return np.arctan2(np.sin(angle), np.cos(angle))


def _rot_e3(euler: np.ndarray) -> np.ndarray:
    """R_ZYX(euler) * [0,0,1], for one or many [roll,pitch,yaw] rows."""
    e = np.atleast_2d(euler)
    p, q, y = e.T
    return np.column_stack(
        (
            np.cos(y) * np.sin(q) * np.cos(p) + np.sin(y) * np.sin(p),
            np.sin(y) * np.sin(q) * np.cos(p) - np.cos(y) * np.sin(p),
            np.cos(q) * np.cos(p),
        )
    )


def _force_targets(
    a_req: np.ndarray, measured_yaw: np.ndarray, command_yaw: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Match baseline force conversion, then the runtime's yaw overwrite."""
    specific = np.asarray(a_req, dtype=float) + np.array([0.0, 0.0, GRAVITY])
    measured_yaw = np.asarray(measured_yaw, dtype=float).reshape(-1)
    command_yaw = np.asarray(command_yaw, dtype=float).reshape(-1)
    ax, ay, az = specific.T
    a = np.cos(measured_yaw) * ax + np.sin(measured_yaw) * ay
    b = np.sin(measured_yaw) * ax - np.cos(measured_yaw) * ay
    roll = np.arctan2(b, np.hypot(az, a))
    pitch = np.arctan2(a, az)
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, np.finfo(float).tiny))
    target = np.column_stack((roll * scale, pitch * scale, command_yaw))
    return target, MASS * np.linalg.norm(specific, axis=1)


def _force_target(a_req: np.ndarray, measured_yaw: float, command_yaw: float) -> tuple[np.ndarray, float]:
    target, thrust = _force_targets(
        np.asarray(a_req, dtype=float)[None, :], np.array([measured_yaw]), np.array([command_yaw])
    )
    return target[0], float(thrust[0])


def _eulers_from_e3(body_z: np.ndarray, yaw: float) -> np.ndarray:
    x, y, z = np.asarray(body_z).T
    a = np.cos(yaw) * x + np.sin(yaw) * y
    b = np.sin(yaw) * x - np.cos(yaw) * y
    return np.column_stack((np.arctan2(b, np.hypot(z, a)), np.arctan2(a, z), np.full(len(x), yaw)))


def _filter_step(
    euler: np.ndarray, rate: np.ndarray, target: np.ndarray, dt: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    error = _wrap(target - euler)
    request = WN**2 * error - 2.0 * ZETA * WN * rate
    applied = np.clip(request, -ACCEL_LIMIT, ACCEL_LIMIT)
    next_rate = rate + dt * applied
    next_euler = _wrap(euler + dt * next_rate)
    return next_euler, next_rate, request, applied


def _load_scene(scene_id: str) -> dict[str, Any]:
    if "TEST" in scene_id or not scene_id.startswith(("DL1018_DEV_", "DL1018_VAL_")):
        raise ValueError(f"Disallowed scene id: {scene_id}")
    path = RAW_ROOT / scene_id / "raw_run.mat"
    with h5py.File(path, "r") as f:
        log = f["log"]
        data = {name: _mat_array(log[name]).astype(float) for name in LOG_FIELDS}
        t = _mat_array(f["scene/time"]).reshape(-1).astype(float)
        yaw = _mat_array(f["scene/reference/yaw"]).reshape(-1).astype(float)
        ref_acceleration = _mat_array(f["scene/reference/acceleration"]).astype(float)
    n = len(data["command_filter_target_euler"])
    dt = float(np.median(np.diff(t)))
    if abs(dt - DT_EXPECTED) > 1e-12 or len(t) != n + 1 or len(yaw) != n + 1 or len(ref_acceleration) != n + 1:
        raise ValueError(f"Unexpected time/reference dimensions for {scene_id}")
    data["scene_id"] = scene_id
    data["path"] = str(path)
    data["dt"] = dt
    data["yaw"] = yaw[:n]
    data["reference_acceleration"] = ref_acceleration[:n]
    data["task_euler"], _ = _force_targets(data["reference_acceleration"], yaw[:n], yaw[:n])
    data["n"] = n
    return data


def _pcf_step(
    euler: np.ndarray, eta: np.ndarray, a_req: np.ndarray, thrust: float, dt: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a_f = (thrust / MASS) * _rot_e3(euler)[0] - np.array([0.0, 0.0, GRAVITY])
    r_f = a_req - a_f
    decay = np.exp(-PCF_K2 * dt)
    integral = -np.expm1(-PCF_K2 * dt) / PCF_K2
    eta_next = decay * eta + integral * r_f
    return a_f, r_f, eta_next


def _orientation_error(euler_a: np.ndarray, euler_b: np.ndarray) -> np.ndarray:
    """ZYX attitude geodesic angle between paired Euler rows."""
    def rot(e: np.ndarray) -> np.ndarray:
        p, q, y = e.T
        cp, sp, cq, sq, cy, sy = np.cos(p), np.sin(p), np.cos(q), np.sin(q), np.cos(y), np.sin(y)
        out = np.empty((len(e), 3, 3))
        out[:, 0, :] = np.column_stack((cy * cq, cy * sq * sp - sy * cp, cy * sq * cp + sy * sp))
        out[:, 1, :] = np.column_stack((sy * cq, sy * sq * sp + cy * cp, sy * sq * cp - cy * sp))
        out[:, 2, :] = np.column_stack((-sq, cq * sp, cq * cp))
        return out
    ra, rb = rot(np.atleast_2d(euler_a)), rot(np.atleast_2d(euler_b))
    rel = np.einsum("nij,nkj->nik", ra, rb)
    cosine = np.clip((np.trace(rel, axis1=1, axis2=2) - 1.0) / 2.0, -1.0, 1.0)
    return np.arccos(cosine)


def _summary(x: np.ndarray) -> dict[str, float]:
    a = np.asarray(x, dtype=float).reshape(-1)
    return {
        "rms": float(np.sqrt(np.mean(a * a))),
        "p50": float(np.quantile(a, 0.50)),
        "p95": float(np.quantile(a, 0.95)),
        "max": float(np.max(a)),
    }


def _baseline_replay(data: dict[str, Any]) -> dict[str, np.ndarray | float]:
    n, dt = data["n"], data["dt"]
    logged_target = data["command_filter_target_euler"]
    a_req = data["stage1_position_pcf_a_req_mps2"]
    force_target, thrust = _force_targets(a_req, data["state"][:n, 8], data["yaw"])
    euler = data["state"][0, 6:9].copy()
    rate = np.zeros(3)
    eta = np.zeros(3)
    filt = np.empty((n, 3))
    rates = np.empty((n, 3))
    af = np.empty((n, 3))
    rf = np.empty((n, 3))
    eta_after = np.empty((n, 3))
    for k in range(n):
        filt[k], rates[k] = euler, rate
        af[k], rf[k], eta = _pcf_step(euler, eta, a_req[k], thrust[k], dt)
        eta_after[k] = eta
        euler, rate, _, _ = _filter_step(euler, rate, logged_target[k], dt)
    return {
        "position_target": force_target,
        "thrust": thrust,
        "filter": filt,
        "rate": rates,
        "af": af,
        "rf": rf,
        "eta": eta_after,
    }


def _calibrate(ids: list[str]) -> tuple[float, list[dict[str, Any]]]:
    residuals: list[np.ndarray] = []
    records: list[dict[str, Any]] = []
    for scene_id in ids:
        d = _load_scene(scene_id)
        replay = _baseline_replay(d)
        ref_err = np.max(np.abs(_wrap(replay["filter"] - d["filtered_attitude_reference"])))
        rate_err = np.max(np.abs(replay["rate"] - d["filtered_attitude_rate"]))
        target_err = np.max(np.abs(_wrap(replay["position_target"] - d["command_filter_target_euler"])))
        af_err = np.max(np.abs(replay["af"] - d["stage1_position_pcf_a_f_mps2"]))
        rf_err = np.max(np.abs(replay["rf"] - d["stage1_position_pcf_r_f_mps2"]))
        eta_err = np.max(np.abs(replay["eta"] - d["stage1_position_pcf_eta_after_mps"]))
        parity = max(float(ref_err), float(rate_err), float(target_err), float(af_err), float(rf_err), float(eta_err))
        if parity > 2e-10:
            raise RuntimeError(f"Baseline replay parity failed: {scene_id} max={parity:.4g}")
        residuals.append(np.linalg.norm(replay["rf"], axis=1))
        records.append({"scene_id": scene_id, "max_abs_parity_error": parity})
    all_residual = np.concatenate(residuals)
    epsilon = float(np.quantile(all_residual, 0.95))
    return epsilon, records


def _governor_replay(data: dict[str, Any], epsilon: float) -> dict[str, Any]:
    n, dt = data["n"], data["dt"]
    a_req = data["stage1_position_pcf_a_req_mps2"]
    yaw = data["yaw"]
    euler = data["state"][0, 6:9].copy()
    rate = np.zeros(3)
    eta = np.zeros(3)
    targets = np.empty((n, 3))
    refs = np.empty((n, 3))
    rates = np.empty((n, 3))
    req_acc = np.empty((n, 3))
    app_acc = np.empty((n, 3))
    af = np.empty((n, 3))
    rf = np.empty((n, 3))
    eta_after = np.empty((n, 3))
    alpha = np.empty(n)
    predicted_closure = np.empty(n)
    fallback = np.zeros(n, dtype=bool)
    target_shift = np.empty(n)
    one_step_ref_shift = np.empty(n)
    task_command_error = np.empty(n)
    cone_task_closure = np.empty(n)
    cone_min_tilt = np.empty(n)
    cone_feasible = np.empty(n, dtype=bool)
    for k in range(n):
        position_target, thrust = _force_target(a_req[k], data["state"][k, 8], yaw[k])
        task_target = data["task_euler"][k]
        position_axis = _rot_e3(position_target)[0]
        task_axis = _rot_e3(task_target)[0]
        theta = float(np.arccos(np.clip(np.dot(position_axis, task_axis), -1.0, 1.0)))
        sin_theta = np.sin(theta)
        # Spherical path from the current force target toward the scored task attitude.
        axes = np.empty((len(GOVERNOR_GRID), 3))
        if abs(sin_theta) < 1e-10:
            axes[:] = task_axis
        else:
            axes = (
                (np.sin((1.0 - GOVERNOR_GRID) * theta) / sin_theta)[:, None] * position_axis[None, :]
                + (np.sin(GOVERNOR_GRID * theta) / sin_theta)[:, None] * task_axis[None, :]
            )
        candidate_targets = _eulers_from_e3(axes, yaw[k])
        errors = _wrap(candidate_targets - euler[None, :])
        requests = WN[None, :] ** 2 * errors - 2.0 * ZETA[None, :] * WN[None, :] * rate[None, :]
        applied = np.clip(requests, -ACCEL_LIMIT[None, :], ACCEL_LIMIT[None, :])
        predicted_rate = rate[None, :] + dt * applied
        predicted_euler = _wrap(euler[None, :] + dt * predicted_rate)
        predicted_af = (thrust / MASS) * _rot_e3(predicted_euler) - np.array([0.0, 0.0, GRAVITY])
        predicted_rf = a_req[k][None, :] - predicted_af
        predicted_norm = np.linalg.norm(predicted_rf, axis=1)
        feasible = np.flatnonzero(predicted_norm <= epsilon + 1e-12)
        if len(feasible):
            idx = int(feasible[-1])  # greatest task contribution on the 0.01 grid
        else:
            idx = 0  # retain the original force direction if no grid point is feasible
            fallback[k] = True
        chosen_target = candidate_targets[idx]
        targets[k] = chosen_target
        alpha[k] = GOVERNOR_GRID[idx]
        predicted_closure[k] = predicted_norm[idx]
        target_shift[k] = _orientation_error(chosen_target[None, :], position_target[None, :])[0]
        one_step_ref_shift[k] = _orientation_error(predicted_euler[idx][None, :], predicted_euler[0][None, :])[0]

        # The filter emits the pre-update state on this row; the new target affects
        # next row. PCF consumes this exact pre-update reference and current a_req.
        refs[k], rates[k] = euler, rate
        af[k], rf[k], eta = _pcf_step(euler, eta, a_req[k], thrust, dt)
        eta_after[k] = eta
        task_command_error[k] = _orientation_error(euler[None, :], task_target[None, :])[0]
        euler, rate, req_acc[k], app_acc[k] = _filter_step(euler, rate, chosen_target, dt)

        # Closed-form force-direction cone diagnostic. It is a static upper bound,
        # not available as a per-sample runtime budget or a substitute for replay.
        specific = a_req[k] + np.array([0.0, 0.0, GRAVITY])
        s = float(np.linalg.norm(specific))
        force_axis = specific / max(s, np.finfo(float).tiny)
        theta_force_task = float(np.arccos(np.clip(np.dot(force_axis, task_axis), -1.0, 1.0)))
        cone_task_closure[k] = 2.0 * s * np.sin(theta_force_task / 2.0)
        delta = 2.0 * np.arcsin(min(1.0, epsilon / max(2.0 * s, np.finfo(float).tiny)))
        cone_min_tilt[k] = max(0.0, theta_force_task - delta)
        cone_feasible[k] = theta_force_task <= delta + 1e-12

    target_tilt = np.hypot(targets[:, 0], targets[:, 1])
    ref_tilt = np.hypot(refs[:, 0], refs[:, 1])
    target_accel_saturated = np.any(np.abs(req_acc) > ACCEL_LIMIT[None, :] + 1e-12, axis=1)
    metrics = {
        "alpha_task_mean": float(np.mean(alpha)),
        "alpha_task_fraction": _summary(alpha),
        "fraction_alpha_positive": float(np.mean(alpha > 0.0)),
        "fraction_alpha_full": float(np.mean(alpha >= 1.0)),
        "fallback_no_feasible_grid_point_fraction": float(np.mean(fallback)),
        "target_shift_from_existing_position_command_deg": _summary(np.rad2deg(target_shift)),
        "one_step_filter_output_shift_vs_position_target_deg": _summary(np.rad2deg(one_step_ref_shift)),
        "commanded_task_attitude_error_deg": _summary(np.rad2deg(task_command_error)),
        "post_filter_closure_mps2": _summary(np.linalg.norm(rf, axis=1)),
        "post_filter_closure_fraction_above_fixed_epsilon": float(np.mean(np.linalg.norm(rf, axis=1) > epsilon)),
        "governor_predicted_closure_mps2": _summary(predicted_closure),
        "predicted_closure_fraction_above_fixed_epsilon": float(np.mean(predicted_closure > epsilon + 1e-12)),
        "eta_norm_mps": _summary(np.linalg.norm(eta_after, axis=1)),
        "eta_component_rms_mps": [float(v) for v in np.sqrt(np.mean(eta_after**2, axis=0))],
        "max_target_tilt_deg": float(np.rad2deg(np.max(target_tilt))),
        "max_filtered_reference_tilt_deg": float(np.rad2deg(np.max(ref_tilt))),
        "fraction_target_over_30deg": float(np.mean(target_tilt > MAX_TILT + 1e-10)),
        "fraction_filtered_reference_over_30deg": float(np.mean(ref_tilt > MAX_TILT + 1e-10)),
        "filter_acceleration_request_max_abs_rads2": [float(v) for v in np.max(np.abs(req_acc), axis=0)],
        "filter_acceleration_clipped_fraction": float(np.mean(target_accel_saturated)),
        "filter_rate_max_abs_rads": [float(v) for v in np.max(np.abs(rates), axis=0)],
        "static_task_pose_closure_mps2": _summary(cone_task_closure),
        "static_force_cone_min_task_axis_error_lower_bound_deg": _summary(np.rad2deg(cone_min_tilt)),
        "static_force_cone_contains_task_axis_fraction": float(np.mean(cone_feasible)),
        "actual_to_task_yaw_gap_deg": _summary(np.rad2deg(np.abs(_wrap(data["state"][:n, 8] - yaw)))),
        "task_reference_acceleration_mps2": _summary(np.linalg.norm(data["reference_acceleration"], axis=1)),
        "task_reference_tilt_deg": _summary(np.rad2deg(np.hypot(data["task_euler"][:, 0], data["task_euler"][:, 1]))),
        "task_reference_acceleration_zero_fraction": float(np.mean(np.linalg.norm(data["reference_acceleration"], axis=1) <= 1e-10)),
        "task_reference_acceleration_zero_fraction": float(np.mean(np.linalg.norm(data["reference_acceleration"], axis=1) <= 1e-10)),
    }
    return {
        "target": targets,
        "reference": refs,
        "rate": rates,
        "af": af,
        "rf": rf,
        "eta": eta_after,
        "metrics": metrics,
    }


def _scene_report(data: dict[str, Any], epsilon: float) -> dict[str, Any]:
    baseline = _baseline_replay(data)
    candidate = _governor_replay(data, epsilon)
    replay_target_err = np.max(np.abs(_wrap(baseline["position_target"] - data["command_filter_target_euler"])))
    replay_ref_err = np.max(np.abs(_wrap(baseline["filter"] - data["filtered_attitude_reference"])))
    replay_rate_err = np.max(np.abs(baseline["rate"] - data["filtered_attitude_rate"]))
    replay_af_err = np.max(np.abs(baseline["af"] - data["stage1_position_pcf_a_f_mps2"]))
    replay_rf_err = np.max(np.abs(baseline["rf"] - data["stage1_position_pcf_r_f_mps2"]))
    replay_eta_err = np.max(np.abs(baseline["eta"] - data["stage1_position_pcf_eta_after_mps"]))
    parity = max(float(replay_target_err), float(replay_ref_err), float(replay_rate_err),
                 float(replay_af_err), float(replay_rf_err), float(replay_eta_err))
    if parity > 2e-10:
        raise RuntimeError(f"HF baseline replay parity failed: {data['scene_id']} max={parity:.4g}")
    base_task = data["task_euler"]
    base_task_err = _orientation_error(baseline["filter"], base_task)
    cand_task_err = _orientation_error(candidate["reference"], base_task)
    baseline_closure = np.linalg.norm(baseline["rf"], axis=1)
    candidate_closure = np.linalg.norm(candidate["rf"], axis=1)
    eta_delta = np.linalg.norm(candidate["eta"] - baseline["eta"], axis=1)
    target_shift = _orientation_error(candidate["target"], baseline["position_target"])
    filter_shift = _orientation_error(candidate["reference"], baseline["filter"])
    return {
        "scene_id": data["scene_id"],
        "n_samples": data["n"],
        "dt_s": data["dt"],
        "baseline_replay_max_abs_parity_error": parity,
        "baseline_command_task_error_deg": _summary(np.rad2deg(base_task_err)),
        "governor_command_task_error_deg": _summary(np.rad2deg(cand_task_err)),
        "governor_minus_baseline_task_error_p95_deg": float(np.rad2deg(np.quantile(cand_task_err - base_task_err, 0.95))),
        "baseline_post_filter_closure_mps2": _summary(baseline_closure),
        "governor_post_filter_closure_mps2": _summary(candidate_closure),
        "baseline_post_filter_closure_fraction_above_epsilon": float(np.mean(baseline_closure > epsilon)),
        "governor_post_filter_closure_fraction_above_epsilon": float(np.mean(candidate_closure > epsilon)),
        "governor_eta_delta_from_baseline_mps": _summary(eta_delta),
        "governor_target_shift_from_original_deg": _summary(np.rad2deg(target_shift)),
        "governor_filtered_reference_shift_from_original_deg": _summary(np.rad2deg(filter_shift)),
        "governor": candidate["metrics"],
    }


def main() -> None:
    if len(CALIBRATION_IDS) != 21 or set(HF6) & set(CALIBRATION_IDS):
        raise RuntimeError(f"Unexpected calibration cohort: {len(CALIBRATION_IDS)}")
    epsilon, calibration_parity = _calibrate(CALIBRATION_IDS)
    hf_reports = []
    for scene_id in HF6:
        hf_reports.append(_scene_report(_load_scene(scene_id), epsilon))
    report = {
        "schema": "DL1018_FILTER_PCF_CAUSAL_GOVERNOR_REPLAY_DEVHF6_V1",
        "status": "DIAGNOSTIC_ONLY_NO_PLANT",
        "input_raw_root": str(RAW_ROOT),
        "allowlisted_log_fields": list(LOG_FIELDS),
        "allowlisted_scene_fields": ["scene/time", "scene/reference/yaw", "scene/reference/acceleration"],
        "explicitly_not_read": ["TEST", "wind_force_I", "environment_wind_I", "Plant truth", "future parent residuals"],
        "replay_scope": "Current parent stage1 a_req is replayed as an exogenous input; this is not a changed-state closed loop.",
        "calibration": {
            "scene_ids": CALIBRATION_IDS,
            "scene_count": len(CALIBRATION_IDS),
            "sample_count": len(CALIBRATION_IDS) * 20000,
            "fixed_closure_budget_epsilon_mps2": epsilon,
            "role": "Development calibration from 21 distinct parent-GRU DEV scene IDs; excludes the exact 3 DEV HF6 target IDs and uses no VAL scene IDs. It is not C5 TRAIN and is not a frequency-family holdout; other T1/T2/T3 profiles may be reused across conditions, and the HF6 cohort was known when this diagnostic was specified.",
            "rule": "One pooled 95th percentile of baseline sequential-replay ||r_f|| over these 21 DEV scenes; fixed before the sequential HF replay. No per-time parent residual enters governor decisions.",
            "exact_scene_id_overlap_with_hf6": False,
            "hf6_validation_scene_count": sum(sid.startswith("DL1018_VAL_") for sid in HF6),
            "baseline_replay_parity": calibration_parity,
        },
        "parameters": {
            "dt_s": DT_EXPECTED,
            "mass_kg": MASS,
            "gravity_mps2": GRAVITY,
            "command_filter_wn_rads": WN.tolist(),
            "command_filter_damping": ZETA.tolist(),
            "command_filter_acceleration_limit_rads2": ["unbounded", "unbounded", 6.0],
            "pcf_k2_per_s": PCF_K2.tolist(),
            "max_tilt_deg": float(np.rad2deg(MAX_TILT)),
            "governor_grid_step": 0.01,
            "runtime_yaw_order": "Position roll/pitch are solved with current measured yaw, then command yaw is replaced by current task yaw, exactly as the source does; candidate keeps that mapping to isolate task/position coordination.",
            "task_reference_reconstruction": "baseline_force_to_attitude(scene.reference.acceleration, scene.reference.yaw, P), matching frozen score reference.",
            "governor_target_path": "Spherical interpolation from the existing force target (with its 30 deg cap and source yaw mixing) toward the reconstructed task attitude.",
            "causal_decision": "At k, choose greatest alpha whose one-step predicted filtered-reference closure against current a_req[k] is <= fixed epsilon; choose alpha=0 if no grid point is feasible. Apply normal second-order filter update; PCF at k uses the pre-update filter output, current thrust/a_req, and current eta.",
        },
        "hf6": hf_reports,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT),
        "epsilon_mps2": epsilon,
        "calibration_scenes": len(CALIBRATION_IDS),
        "hf6_scenes": len(hf_reports),
        "worst_baseline_replay_error": max(x["max_abs_parity_error"] for x in calibration_parity),
        "hf6_summary": [
            {
                "scene_id": s["scene_id"],
                "alpha_mean": s["governor"]["alpha_task_mean"],
                "alpha_p50": s["governor"]["alpha_task_fraction"]["p50"],
                "task_error_p95_deg": s["governor_command_task_error_deg"]["p95"],
                "closure_p95_mps2": s["governor_post_filter_closure_mps2"]["p95"],
            }
            for s in hf_reports
        ],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
