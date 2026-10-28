#!/usr/bin/env python3
"""Reproduce the read-only T1_C08_W15 attitude discrete check.

Reads only the frozen config/lock and one existing C5 raw MAT file.
Writes one JSON result beside this script. No Plant, MATLAB, model or TEST access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
LOCK_REL = Path("experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/LOCKED_CFG.json")
CFG_REL = Path("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat")
RAW_REL = Path("experiments/position_axis_coordinate_c5_20261023/runs_c5_v1/DL1018_VAL_T1_C08_W15/C5_AXIS_MASK_M110/attempt_01/raw_run.mat")
OUT_JSON = OUT_DIR / "T1_0PLANT_NUMERICAL_CHECK.json"

EXPECTED_RAW_SHA = "c118dd1bd5567e0e7c58b7f5334109187b2cfe743977a6a18a3976d7d0ab23c3"
EXPECTED_LOCK_SHA = "55a794e875ca95e5846a29997e01065ab9700e26ac17eb9cb57ce02d7e05df99"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def max_abs_by_axis(a: np.ndarray) -> list[float]:
    return np.max(np.abs(a), axis=1).astype(float).tolist()


def wrap(a: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(a), np.cos(a))


def euler_T_Tdot(eta: np.ndarray, omega: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    phi = float(eta[0])
    theta_raw = float(eta[1])
    theta = float(np.clip(theta_raw, -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4))
    clamp_active = theta != theta_raw
    sphi, cphi = np.sin(phi), np.cos(phi)
    ttheta, sectheta = np.tan(theta), 1.0 / np.cos(theta)
    T = np.array([
        [1.0, sphi * ttheta, cphi * ttheta],
        [0.0, cphi, -sphi],
        [0.0, sphi * sectheta, cphi * sectheta],
    ])
    eta_rate = T @ omega
    phi_dot, theta_dot = eta_rate[:2]
    T_phi = np.array([
        [0.0, cphi * ttheta, -sphi * ttheta],
        [0.0, -sphi, -cphi],
        [0.0, cphi * sectheta, -sphi * sectheta],
    ])
    T_theta = np.array([
        [0.0, sphi * sectheta**2, cphi * sectheta**2],
        [0.0, 0.0, 0.0],
        [0.0, sphi * sectheta * ttheta, cphi * sectheta * ttheta],
    ])
    return T, T_phi * phi_dot + T_theta * theta_dot, clamp_active


def main() -> int:
    lock_path, cfg_path, raw_path = ROOT / LOCK_REL, ROOT / CFG_REL, ROOT / RAW_REL
    lock_sha, cfg_sha, raw_sha = sha256(lock_path), sha256(cfg_path), sha256(raw_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_cfg_sha = lock["cfg_snapshot_sha256"].lower()
    if lock_sha != EXPECTED_LOCK_SHA:
        raise RuntimeError(f"LOCKED_CFG SHA mismatch: {lock_sha}")
    if cfg_sha != expected_cfg_sha:
        raise RuntimeError(f"prepared CFG SHA mismatch: {cfg_sha}")
    if raw_sha != EXPECTED_RAW_SHA:
        raise RuntimeError(f"T1 raw SHA mismatch: {raw_sha}")

    J0 = np.asarray(lock["J0_kgm2"], dtype=float)
    J0_inv = np.linalg.inv(J0)
    h = float(lock["simulation_sample_time_s"])
    beta_rise = float(lock["beta_rise_time_s"])
    dmax = np.asarray(lock["dmax"], dtype=float)
    with h5py.File(cfg_path, "r") as cfg:
        k1 = np.asarray(cfg["cfg/control/bs/attitude/k1"], dtype=float).reshape(-1)
        k2 = np.asarray(cfg["cfg/control/bs/attitude/k2"], dtype=float).reshape(-1)
        update_hz = float(np.asarray(cfg["opts/attitude_rbf_frequency_hz"]).reshape(-1)[0])
        phase0 = float(np.asarray(cfg["opts/rbf_phase_start"]).reshape(-1)[0])
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        state = np.asarray(log["state"], dtype=float)
        time = np.asarray(log["time"], dtype=float).reshape(-1)
        transition_time = np.asarray(log["transition_time"], dtype=float).reshape(-1)
        ref = np.asarray(log["filtered_attitude_reference"], dtype=float)
        ref_rate = np.asarray(log["filtered_attitude_rate"], dtype=float)
        ref_acc = np.asarray(log["command_filter_acceleration_applied_rads2"], dtype=float)
        requested_generalized = np.asarray(log["requested_generalized"], dtype=float)
        nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=float)
        compensation_torque = np.asarray(log["attitude_rbf_compensation_torque_Nm"], dtype=float)
        event = np.asarray(log["attitude_event_flag"], dtype=bool).reshape(-1)
        update_dt = np.asarray(log["rbf_update_dt"], dtype=float).reshape(-1)

    n = min(ref.shape[1] - 1, state.shape[1] - 1)
    if n != 19999:
        raise RuntimeError(f"unexpected aligned-pair count: {n}")

    # Command-filter semi-implicit updates on the 19,999 logged adjacent pairs.
    rate_error = ref_rate[:, 1:n + 1] - ref_rate[:, :n] - h * ref_acc[:, :n]
    ref_angle_step = wrap(ref[:, 1:n + 1] - ref[:, :n])
    angle_error = ref_angle_step - h * ref_rate[:, 1:n + 1]

    # Build e, nu, s, T and Tdot from logged state and pre-update reference.
    e = np.empty((3, n + 1))
    nu = np.empty((3, n + 1))
    surface = np.empty((3, n + 1))
    Ts, Tdots, clamp_flags = [], [], []
    omega_all = state[9:12, :]
    eta_all = state[6:9, :]
    for k in range(n + 1):
        T, Tdot, clamp_active = euler_T_Tdot(eta_all[:, k], omega_all[:, k])
        Ts.append(T)
        Tdots.append(Tdot)
        clamp_flags.append(clamp_active)
        e[:, k] = wrap(ref[:, k] - eta_all[:, k])
        nu[:, k] = ref_rate[:, k] - T @ omega_all[:, k]
        surface[:, k] = nu[:, k] + k1 * e[:, k]

    # Exact discrete command-port residual d_k^h, using requested torque, never realized torque.
    omega_start = omega_all[:, :n].T
    delta_omega_over_h = ((omega_all[:, 1:n + 1] - omega_all[:, :n]) / h).T
    tau_req = requested_generalized[1:4, :n].T
    gyro = np.cross(omega_start, omega_start @ J0.T)
    d_h = delta_omega_over_h + (gyro - tau_req) @ J0_inv.T
    d_h_rebuild = (tau_req - gyro) @ J0_inv.T + d_h
    d_h_identity_error = delta_omega_over_h - d_h_rebuild

    rho_e = (e[:, 1:n + 1] - e[:, :n]) / h - nu[:, :n]
    Tstack = np.asarray(Ts[:n])
    T_omega = np.einsum("kij,kj->ik", Tstack, omega_start)
    eta_step_over_h = (eta_all[:, 1:n + 1] - eta_all[:, :n]) / h
    rho_e_alt = h * ref_acc[:, :n] + T_omega - eta_step_over_h
    rho_T = np.empty((3, n))
    for k in range(n):
        rho_T[:, k] = (
            Tdots[k] @ omega_all[:, k]
            - ((Ts[k + 1] - Ts[k]) / h) @ omega_all[:, k + 1]
        )

    # C5 teacher compensation is logged in torque units; convert it to J0 acceleration units.
    beta_d_applied = J0_inv @ compensation_torque[:, :n]
    epsilon = beta_d_applied.T - d_h
    T_epsilon = np.einsum("kij,kj->ik", Tstack, epsilon)
    delta_surface_pred = h * (
        -e[:, :n] - k2[:, None] * surface[:, :n]
        + T_epsilon + k1[:, None] * rho_e + rho_T
    )
    delta_surface_measured = surface[:, 1:n + 1] - surface[:, :n]
    surface_recurrence_error = delta_surface_measured - delta_surface_pred

    # Raw command-port sign, as logged by the actual controller command path.
    command_sign_error = requested_generalized[1:4, :n] - (
        nominal_torque[:, :n] - compensation_torque[:, :n]
    )

    # Nominal sample contraction in the fixed 1 s scaling used by the bound.
    t_star_s = 1.0
    A = np.block([
        [-np.diag(k1), np.eye(3) / t_star_s],
        [-t_star_s * np.eye(3), -np.diag(k2)],
    ])
    Phi = np.eye(6) + h * A
    phi_norm = float(np.linalg.norm(Phi, ord=2))
    q_bar = 0.998701

    # Check the raw event schedule and implementation beta index.
    event_indices0 = np.flatnonzero(event)
    event_times = transition_time[event_indices0]
    event_spacings = np.diff(event_times)
    event_update_dt = update_dt[event_indices0]
    first_event_matlab_k = int(event_indices0[0] + 1)
    first_beta = min(first_event_matlab_k * h / beta_rise, 1.0)
    expected_period = 1.0 / update_hz

    checks = {
        "locked_cfg_hash_matches_expected": lock_sha == EXPECTED_LOCK_SHA,
        "prepared_cfg_hash_matches_lock": cfg_sha == expected_cfg_sha,
        "raw_hash_matches_expected": raw_sha == EXPECTED_RAW_SHA,
        "filter_rate_update": float(np.max(np.abs(rate_error))) < 1e-12,
        "filter_semiimplicit_angle_update": float(np.max(np.abs(angle_error))) < 1e-12,
        "d_h_body_rate_identity": float(np.max(np.abs(d_h_identity_error))) < 1e-10,
        "rho_e_alternate_identity": float(np.max(np.abs(rho_e - rho_e_alt))) < 1e-10,
        "full_surface_recurrence": float(np.max(np.abs(surface_recurrence_error))) < 1e-12,
        "command_torque_sign": float(np.max(np.abs(command_sign_error))) < 1e-12,
        "pitch_clamp_inactive": not any(clamp_flags),
        "100_hz_event_clock": (
            len(event_indices0) == 1999
            and abs(event_times[0] - expected_period) < 1e-12
            and abs(event_times[-1] - 19.99) < 1e-12
            and np.allclose(event_spacings, expected_period, rtol=0, atol=1e-12)
            and np.allclose(event_update_dt, expected_period, rtol=0, atol=2e-12)
        ),
        "nominal_phi_contractive": phi_norm <= q_bar and q_bar < 1.0,
    }
    exit_code = 0 if all(checks.values()) else 1

    result = {
        "schema": "T1_C08_W15_0PLANT_NCMD_RECURRENCE_CHECK_V1",
        "status": "PASS" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
        "scope": {
            "Plant_calls": 0,
            "MATLAB_started": False,
            "training_updates": 0,
            "TEST_read": False,
            "true_inertia_reconstruction": False,
            "inputs_used_for_dh": ["raw log/state omega", "raw log/requested_generalized torque", "locked J0"],
        },
        "inputs": {
            "locked_cfg_relpath": LOCK_REL.as_posix(),
            "locked_cfg_sha256": lock_sha,
            "prepared_cfg_relpath": CFG_REL.as_posix(),
            "prepared_cfg_sha256": cfg_sha,
            "raw_relpath": RAW_REL.as_posix(),
            "raw_sha256": raw_sha,
            "script_sha256": sha256(Path(__file__).resolve()),
        },
        "parameters": {
            "J0_kgm2": J0.tolist(),
            "J0_sha256": lock["J0_sha256"],
            "K1": k1.tolist(),
            "K2": k2.tolist(),
            "sample_time_s": h,
            "attitude_update_hz": update_hz,
            "scheduler_phase_start": phase0,
            "event_period_s": expected_period,
            "beta_rise_time_s": beta_rise,
            "dmax_rad_s2": dmax.tolist(),
            "first_event_matlab_sample_index": first_event_matlab_k,
            "first_event_zero_based_state_index": int(event_indices0[0]),
            "first_event_time_s": float(event_times[0]),
            "first_event_beta_from_source_index": first_beta,
        },
        "metrics": {
            "aligned_filter_pairs": n,
            "filter_rate_update_max_abs_by_axis": max_abs_by_axis(rate_error),
            "filter_rate_update_max_abs": float(np.max(np.abs(rate_error))),
            "filter_semiimplicit_angle_max_abs_by_axis": max_abs_by_axis(angle_error),
            "filter_semiimplicit_angle_max_abs": float(np.max(np.abs(angle_error))),
            "d_h_identity_max_abs_by_axis": max_abs_by_axis(d_h_identity_error.T),
            "d_h_identity_max_abs": float(np.max(np.abs(d_h_identity_error))),
            "rho_e_alternate_identity_max_abs": float(np.max(np.abs(rho_e - rho_e_alt))),
            "surface_recurrence_max_abs_by_axis": max_abs_by_axis(surface_recurrence_error),
            "surface_recurrence_max_abs": float(np.max(np.abs(surface_recurrence_error))),
            "surface_recurrence_rms_by_axis": np.sqrt(np.mean(surface_recurrence_error**2, axis=1)).tolist(),
            "command_sign_max_abs_by_axis_Nm": max_abs_by_axis(command_sign_error),
            "command_sign_max_abs_Nm": float(np.max(np.abs(command_sign_error))),
            "pitch_clamp_active_samples": int(sum(clamp_flags)),
            "event_count": int(len(event_indices0)),
            "first_event_time_s": float(event_times[0]),
            "last_event_time_s": float(event_times[-1]),
            "event_spacing_min_s": float(np.min(event_spacings)),
            "event_spacing_max_s": float(np.max(event_spacings)),
            "event_update_dt_max_abs_error_s": float(np.max(np.abs(event_update_dt - expected_period))),
            "nominal_Phi_2_norm_exact_float": phi_norm,
            "nominal_Phi_2_norm_upper_bound_qbar": q_bar,
            "nominal_Phi_eigenvalues": np.sort(np.linalg.eigvals(Phi).real).tolist(),
        },
        "checks": checks,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "exit_code": exit_code, "metrics": result["metrics"]}, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
