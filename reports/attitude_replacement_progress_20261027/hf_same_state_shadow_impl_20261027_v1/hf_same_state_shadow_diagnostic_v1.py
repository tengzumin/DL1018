#!/usr/bin/env python3
"""Approved read-only same-state GRU/RBF shadow replay. Do not run before ROOT review."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat


HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parent / "hf_attitude_next_taskbook_luna_v1"
SCORE_REL = Path("experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/FULL72_PAIRED_SCORE_v1.json")
RELEASE_REL = Path("experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/RELEASE.json")
LOCKED_CFG_REL = Path("experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/LOCKED_CFG.json")
C5_LOCK_REL = Path("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json")
C5_BATCH_REL = Path("experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_BATCH_STATUS_v3.json")
CSV_REL = Path("reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2.csv")
TASKBOOK_REL = Path("reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_SAME_STATE_SHADOW_DIAGNOSTIC_TASKBOOK_v2_ZH.md")
SUMMARY_REL = Path("reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2_summary.json")
APPROVAL_REL = Path("reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/ROOT_APPROVAL_OFFLINE_SHADOW_v1.md")
AMENDMENT_REL = Path("reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/ROOT_AMENDMENT_OFFLINE_SHADOW_v1.md")

EXPECTED_SHA = {
    TASKBOOK_REL.as_posix(): "b48c9998ac7675b22ebe8e3e01b278d14f57ad2256520a4bcf068be58ba8a67d",
    CSV_REL.as_posix(): "71f3d159954198a066ef8cc00151e07a90ef4de92f216db6990a07da045c2c1a",
    SUMMARY_REL.as_posix(): "32d27dc83b4e9ac79c9f2f847b6eb2825ea403ead8172330e418015223c73eb5",
    APPROVAL_REL.as_posix(): "5a9551b4b4d19e879b26e811d45b1cfff18d3b416d9f5113006fef1726b28b5a",
    AMENDMENT_REL.as_posix(): "1c403f15df3fc08e04651346dcd51db9734e9dae0d15169bcaaa85db2b6c3062",
    LOCKED_CFG_REL.as_posix(): "613aff59c4036ae488cb373afacb3ef1383faa970c8dcd99ffac68462cb6d95f",
    SCORE_REL.as_posix(): "d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff",
    C5_LOCK_REL.as_posix(): "82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75",
    C5_BATCH_REL.as_posix(): "20cc9caca553ebf676fd7b39087fe0a2640fcd976aaf7c8cdb0030c76b5bea22",
    "c5_snapshot": "e417b56e68a73f7af6f40a5e7928631db1b4f3c05de1c3abd24828053760749d",
    "candidate_snapshot": "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a",
    "c5_effective_config": "cec90417369c7a44580b0315b2473ae86eb62550012188340b1dd5f3a796522f",
    "c5_position_model": "6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e",
    "gru_model": "b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567",
    "j0": "8cd498cac86940c800e5c4c1e622e19ed2630bebbd3bbe880d3ae4ad1b689f75",
    "candidate_release": "b453e50d1ef3affce66b0d05dda4848ef0aaf6d58476361d9c3006febd6ef047",
}

FILTER_TOL_RAD = 1e-10
FILTER_TOL_RATE = 1e-8
RBF_TOL_ACCEL = 1e-9
TORQUE_TOL_NM = 1e-10
MEMORY_TOL = 1e-9
MAX_OUTPUT_BYTES = 5 * 1024**3
EXPECTED_EVENTS = 1999
REUSE_PREFLIGHT = "DL1018_VAL_T1_C02_W09"
NEW_PREFLIGHT = "DL1018_DEV_T1_C10_W09"
COMMON_RAW_FIELDS = {
    "time", "transition_time", "state", "initial_state", "arms",
    "command_filter_target_euler", "filtered_attitude_reference",
    "filtered_attitude_rate", "attitude_event_flag",
}
GRU_RAW_FIELDS = {
    "gru_stream_attitude_trace", "gru_stream_attitude_model_sha256",
    "attitude_bs_nominal_torque_Nm", "attitude_compensation_applied_torque_Nm",
}
C5_RAW_FIELDS = {
    "rbf_event_audit", "rbf_event_count", "rbf_event_dt", "rbf_input_sample",
    "rbf_output_raw", "rbf_output_held", "rbf_output_unclipped",
    "rbf_update_dt", "rbf_update_flag", "rbf_weight_norm",
    "attitude_rbf_estimate_acceleration_rads2",
    "attitude_rbf_compensation_torque_Nm", "attitude_nominal_torque_Nm",
}


class StopScene(RuntimeError):
    def __init__(self, message: str, checks: list[dict[str, str]] | None = None):
        super().__init__(message)
        self.checks = checks or []


class StopRun(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def assert_sha(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise StopRun(f"missing {label}: {path}")
    actual = sha256(path)
    if actual.lower() != expected.lower():
        raise StopRun(f"{label} SHA mismatch: expected={expected}, actual={actual}, path={path}")
    return actual


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def import_file(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StopRun(f"cannot import frozen reference helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matlab_tree(decoder, node):
    """Use the existing HDF5 MATLAB decoder; never load unapproved MAT variables."""
    return decoder.h5_tree(node)


def numeric(value: Any, name: str, dtype=np.float64) -> np.ndarray:
    if isinstance(value, tuple) and value and value[0] == "__matlab_char__":
        raise StopScene(f"{name} is char, expected numeric")
    try:
        result = np.asarray(value, dtype=dtype)
    except (TypeError, ValueError) as exc:
        raise StopScene(f"cannot decode numeric field {name}: {exc}") from exc
    if result.dtype.kind not in "biuf" or not np.all(np.isfinite(result)):
        raise StopScene(f"non-finite or non-numeric field: {name}")
    return result


def rows(value: Any, width: int, name: str) -> np.ndarray:
    arr = numeric(value, name)
    if arr.ndim == 1 and width == 1:
        arr = arr[:, None]
    if arr.ndim != 2 or arr.shape[1] != width:
        raise StopScene(f"{name} shape {arr.shape}; expected (samples,{width})")
    return arr


def vector(value: Any, name: str) -> np.ndarray:
    arr = numeric(value, name).squeeze()
    if arr.ndim != 1:
        raise StopScene(f"{name} shape {arr.shape}; expected a vector")
    return arr


def masked_rows(value: Any, width: int, mask: np.ndarray, name: str) -> np.ndarray:
    """Validate logged rows only where the corresponding event mask is true."""
    try:
        arr = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise StopScene(f"cannot decode numeric field {name}: {exc}") from exc
    if arr.ndim != 2 or arr.shape[1] != width or arr.shape[0] != len(mask):
        raise StopScene(f"{name} shape {arr.shape}; expected ({len(mask)},{width})")
    if not np.all(np.isfinite(arr[mask])):
        raise StopScene(f"{name} contains non-finite values on event rows")
    return arr[mask]


def scalar(value: Any, name: str) -> float:
    arr = numeric(value, name).reshape(-1)
    if arr.size != 1:
        raise StopRun(f"{name} is not scalar")
    return float(arr[0])


def matlab_text(value: Any, name: str) -> str:
    if isinstance(value, tuple) and len(value) == 3 and value[0] == "__matlab_char__":
        return str(value[2])
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    if isinstance(value, str):
        return value
    raise StopRun(f"{name} did not decode as MATLAB char")


def field_dict(raw_path: Path, decoder, method: str, include_trace: bool) -> dict[str, Any]:
    wanted = COMMON_RAW_FIELDS | (GRU_RAW_FIELDS if method == "Candidate" else C5_RAW_FIELDS)
    if include_trace and method == "Candidate":
        wanted.add("gru_stream_attitude_trace")
    with h5py.File(raw_path, "r") as f:
        if "log" not in f or not isinstance(f["log"], h5py.Group):
            raise StopScene(f"missing HDF5 log group: {raw_path}")
        log = f["log"]
        missing = sorted(wanted - set(log.keys()))
        if missing:
            raise StopScene(f"missing raw fields {missing}: {raw_path}")
        out = {name: matlab_tree(decoder, log[name]) for name in wanted
               if name != "arms" and (name != "gru_stream_attitude_trace" or include_trace)}
        out["arms"] = matlab_tree(decoder, log["arms"])
    return out


def nested_command(arms: Any) -> np.ndarray:
    if not isinstance(arms, dict) or "command" not in arms:
        raise StopScene("raw arms.command unavailable")
    return rows(arms["command"], 4, "arms.command")


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def filter_replay(data: dict[str, Any], cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    time = vector(data["time"], "time")
    transition_time = vector(data["transition_time"], "transition_time")
    state = rows(data["state"], 12, "state")
    initial_state = vector(data["initial_state"], "initial_state")
    target = rows(data["command_filter_target_euler"], 3, "command_filter_target_euler")
    logged_ref = rows(data["filtered_attitude_reference"], 3, "filtered_attitude_reference")
    logged_rate = rows(data["filtered_attitude_rate"], 3, "filtered_attitude_rate")
    n = len(transition_time)
    if len(time) != len(state) or len(time) != n + 1:
        raise StopScene(f"time/state/transition lengths disagree: {len(time)}/{len(state)}/{n}")
    expected_time = np.arange(20001, dtype=np.float64) * 0.001
    if len(time) != expected_time.size or not np.allclose(time, expected_time, rtol=0, atol=1e-12):
        raise StopScene("raw time grid differs from locked 0..20 s, 1 ms schedule")
    if not (len(target) == len(logged_ref) == len(logged_rate) == n):
        raise StopScene("target/filter arrays do not align to transition_time")
    if len(initial_state) != 12 or not np.allclose(state[0], initial_state, rtol=0, atol=1e-12):
        raise StopScene("initial_state differs from first logged state")
    if not np.allclose(transition_time, time[:-1], rtol=0, atol=1e-12):
        raise StopScene("transition_time does not match causal state sample times")
    dtv = np.diff(time)
    if not np.allclose(dtv, 0.001, rtol=0, atol=1e-12):
        raise StopScene("Plant time grid is not locked 1 ms")
    if not np.all(np.isfinite(state)) or not np.all(np.isfinite(target)):
        raise StopScene("state/target contains non-finite values")
    filt = cfg["control"]["command_filter"]
    wn = np.asarray(filt["wn"], dtype=np.float64).reshape(3)
    damping = np.asarray(filt["damping"], dtype=np.float64).reshape(3)
    limit = np.asarray(filt["acceleration_limit"], dtype=np.float64).reshape(3)
    if not np.allclose(wn, [18, 18, 12], rtol=0, atol=0) or not np.allclose(damping, 1, rtol=0, atol=0):
        raise StopRun("C5 snapshot command-filter parameters differ from lock")
    if not (np.isinf(limit[0]) and np.isinf(limit[1]) and limit[2] == 6):
        raise StopRun("command-filter acceleration limits differ from lock")

    euler = initial_state[6:9].copy()
    rate = np.zeros(3, dtype=np.float64)
    refs = np.empty((n, 3), dtype=np.float64)
    rates = np.empty((n, 3), dtype=np.float64)
    accels = np.empty((n, 3), dtype=np.float64)
    for i in range(n):
        refs[i] = euler
        rates[i] = rate
        error = wrap(target[i] - euler)
        requested = wn * wn * error - 2.0 * damping * wn * rate
        accel = np.minimum(np.maximum(requested, -limit), limit)
        accels[i] = accel
        rate = rate + 0.001 * accel
        euler = wrap(euler + 0.001 * rate)
    angle_err = np.abs(wrap(refs - logged_ref))
    rate_err = np.abs(rates - logged_rate)
    if float(np.max(angle_err)) > FILTER_TOL_RAD or float(np.max(rate_err)) > FILTER_TOL_RATE:
        raise StopScene(f"causal filter parity failed: angle={np.max(angle_err):.3g}, rate={np.max(rate_err):.3g}")
    return refs, rates, accels


def attitude_terms(state_row: np.ndarray, ref: np.ndarray, ref_rate: np.ndarray,
                   ref_accel: np.ndarray, cfg: dict[str, Any], j0: np.ndarray) -> dict[str, np.ndarray]:
    eta = state_row[6:9]
    omega = state_row[9:12]
    phi = eta[0]
    theta = float(np.clip(eta[1], -math.pi / 2 + 1e-4, math.pi / 2 - 1e-4))
    sp, cp = math.sin(phi), math.cos(phi)
    st, ct = math.sin(theta), math.cos(theta)
    tt, sec = st / ct, 1.0 / ct
    T = np.array([[1.0, sp * tt, cp * tt], [0.0, cp, -sp], [0.0, sp * sec, cp * sec]])
    eta_rate = T @ omega
    phi_dot, theta_dot = eta_rate[:2]
    Tdot = np.array([
        [0.0, cp * phi_dot * tt + sp * sec * sec * theta_dot,
         -sp * phi_dot * tt + cp * sec * sec * theta_dot],
        [0.0, -sp * phi_dot, -cp * phi_dot],
        [0.0, cp * phi_dot * sec + sp * sec * tt * theta_dot,
         -sp * phi_dot * sec + cp * sec * tt * theta_dot],
    ])
    bs = cfg["control"]["bs"]["attitude"]
    k1 = np.asarray(bs["k1"], dtype=np.float64).reshape(3)
    k2 = np.asarray(bs["k2"], dtype=np.float64).reshape(3)
    error = wrap(ref - eta)
    rate_error = ref_rate - eta_rate
    alpha = ref_rate + k1 * error
    surface = alpha - eta_rate
    alpha_dot = ref_accel + k1 * rate_error
    nominal_eta_accel = alpha_dot + error + k2 * surface
    nominal_body_accel = np.linalg.solve(T, nominal_eta_accel - Tdot @ omega)
    nominal_moment = j0 @ nominal_body_accel + np.cross(omega, j0 @ omega)
    return {"error": error, "surface": surface, "T": T, "nominal_moment": nominal_moment}


def event_data(host: dict[str, Any], refs: np.ndarray, rates: np.ndarray, accels: np.ndarray,
               cfg: dict[str, Any], j0: np.ndarray) -> dict[str, Any]:
    state = rows(host["state"], 12, "state")[:-1]
    commands_all = nested_command(host["arms"])
    if len(commands_all) != len(refs) + 1:
        raise StopScene(f"arms.command has {len(commands_all)} state rows; expected {len(refs) + 1}")
    commands = commands_all[:-1]  # arms are logged on state knots; only q[:-1] belongs to transitions.
    event_flag = vector(host["attitude_event_flag"], "attitude_event_flag").astype(bool)
    if len(event_flag) != len(refs) or len(commands) != len(refs):
        raise StopScene("event/transition/arms arrays do not align after causal q[:-1] trim")
    if int(np.count_nonzero(event_flag)) != EXPECTED_EVENTS:
        raise StopScene(f"expected {EXPECTED_EVENTS} attitude events, found {np.count_nonzero(event_flag)}")
    ix = np.flatnonzero(event_flag)
    expected_ix = np.arange(10, len(event_flag), 10, dtype=np.int64)
    if len(event_flag) != 20000 or not np.array_equal(ix, expected_ix):
        raise StopScene("attitude events differ from locked 100 Hz schedule at t=0.01..19.99 s")
    feats, terms, beta, dt_event = [], [], [], []
    previous_time = 0.0
    beta_rise = scalar(cfg["rbf"]["attitude"]["beta_rise_time"], "rbf.attitude.beta_rise_time")
    transition_time = vector(host["transition_time"], "transition_time")
    for i in ix:
        k = int(i + 1)  # MATLAB one-based sample index, matches beta=min(k*dt/rise,1).
        now = float(transition_time[i])
        dt = now - previous_time
        if not dt > 0:
            raise StopScene("non-positive event dt")
        previous_time = now
        t = attitude_terms(state[i], refs[i], rates[i], accels[i], cfg, j0)
        feature = np.r_[t["error"], state[i, 9:12], t["nominal_moment"], commands[i]]
        if feature.shape != (13,) or not np.all(np.isfinite(feature)):
            raise StopScene("invalid 13D GRU feature")
        feats.append(feature)
        terms.append(t)
        beta.append(min(k * 0.001 / beta_rise, 1.0))
        dt_event.append(dt)
    return {"index": ix, "sample_index": ix + 1, "time": transition_time[ix], "features": np.asarray(feats),
            "terms": terms, "beta": np.asarray(beta), "dt": np.asarray(dt_event),
            "event_flag": event_flag, "state": state, "commands": commands}


def gru_replay(gru_ref, ev: dict[str, Any], model: dict[str, np.ndarray], cfg: dict[str, Any],
               j0: np.ndarray) -> dict[str, np.ndarray]:
    # Reuse the audited single-step Python forward; carry only causal hidden state.
    mean = np.asarray(model["input_mean"], dtype=np.float64).reshape(13)
    std = np.asarray(model["input_std"], dtype=np.float64).reshape(13)
    hidden = np.zeros(32, dtype=np.float64)
    base_rows, hidden_rows, normalized_rows = [], [], []
    for current_feature in ev["features"]:
        feature_normalized = (current_feature - mean) / std
        q_base, hidden = gru_ref.forward_one(feature_normalized, hidden, model, np.float64)
        base_rows.append(q_base); hidden_rows.append(hidden.copy()); normalized_rows.append(feature_normalized)
    base, hidden_after = np.asarray(base_rows), np.asarray(hidden_rows)
    dmax = np.asarray(cfg["rbf"]["attitude"]["dmax"], dtype=np.float64).reshape(3)
    gamma = np.asarray(cfg["rbf"]["attitude"]["gamma"], dtype=np.float64).reshape(3)
    sigma_w = np.asarray(cfg["rbf"]["attitude"]["sigma_w"], dtype=np.float64).reshape(3)
    s_limit = np.asarray(cfg["rbf"]["attitude"]["s_limit"], dtype=np.float64).reshape(3)
    wmax = scalar(cfg["rbf"]["attitude"]["wmax"], "rbf.attitude.wmax")
    delta = np.zeros((33, 3), dtype=np.float64)
    hidden_before_all, delta_before_all, delta_after_all = [], [], []
    raw, clipped, beta_scaled, torque, projection = [], [], [], [], []
    for i, term in enumerate(ev["terms"]):
        h = hidden_after[i]
        phi = np.r_[h, 1.0]
        hidden_before_all.append(np.zeros(32) if i == 0 else hidden_after[i - 1])
        delta_before_all.append(delta.copy())
        q = base[i] + delta.T @ phi
        qc = np.clip(q, -dmax, dmax)
        bq = ev["beta"][i] * qc
        torque.append(j0 @ bq)
        s_eff = np.clip(term["surface"], -s_limit, s_limit)
        drive = term["T"].T @ s_eff
        d_dot = -ev["beta"][i] * np.outer(phi, gamma * drive) - delta * sigma_w
        unprojected = delta + ev["dt"][i] * d_dot
        delta = np.clip(unprojected, -wmax, wmax)
        delta_after_all.append(delta.copy())
        raw.append(q); clipped.append(qc); beta_scaled.append(bq)
        projection.append(np.any(np.abs(unprojected) > wmax))
    return {"base": base, "hidden_after": hidden_after, "feature_normalized": np.asarray(normalized_rows),
            "hidden_before": np.asarray(hidden_before_all),
            "raw": np.asarray(raw), "clipped": np.asarray(clipped),
            "beta_scaled": np.asarray(beta_scaled), "torque": np.asarray(torque),
            "delta_before": np.asarray(delta_before_all), "delta_after": np.asarray(delta_after_all),
            "projection": np.asarray(projection, dtype=bool)}


def rbf_basis(z: np.ndarray, c: dict[str, Any]) -> np.ndarray:
    centers = np.asarray(c["centers"], dtype=np.float64)
    scale = np.asarray(c["input_scale"], dtype=np.float64).reshape(6)
    if int(scalar(c.get("rbf_input_dim", 6), "rbf.attitude.rbf_input_dim")) != 6 or \
            int(scalar(c.get("linear_dim", 0), "rbf.attitude.linear_dim")) != 0:
        raise StopScene("C5 RBF basis must be exactly six-dimensional with no linear tail")
    if centers.ndim != 2 or centers.shape[0] != 6 or len(z) != 6:
        raise StopScene(f"C5 RBF center/input shape mismatch: centers={centers.shape}")
    scaled = z / np.maximum(scale, np.finfo(np.float64).eps)
    diff = centers - scaled[:, None]
    phi = np.exp(-np.sum(diff * diff, axis=0) / (2.0 * scalar(c["sigma"], "rbf.attitude.sigma") ** 2))
    width = float(c.get("width_scale", 1.0))
    if width != 1.0:
        raw = phi ** (1.0 / width**2)
        raw_norm, base_norm = np.linalg.norm(raw), np.linalg.norm(phi)
        if raw_norm <= 1e-12 or base_norm <= 1e-12:
            raise StopScene("RBF width scaling fallback is unsupported")
        phi = raw * (base_norm / raw_norm)
    return phi


def rbf_replay(ev: dict[str, Any], cfg: dict[str, Any], opts: dict[str, Any],
               j0: np.ndarray) -> dict[str, np.ndarray]:
    c = cfg["rbf"]["attitude"]
    if "rbf_attitude_initial_weight" in opts:
        raise StopScene("locked opts contains rbf_attitude_initial_weight")
    fusion = opts.get("attitude_fusion_v3_6", {})
    if isinstance(fusion, dict) and bool(scalar(fusion.get("enabled", 0), "attitude_fusion.enabled")):
        raise StopScene("C5 attitude fusion option is active")
    if int(scalar(opts.get("rbf_attitude_output_delay_events", 0), "rbf_attitude_output_delay_events")) != 0:
        raise StopScene("non-zero C5 RBF output delay is not supported by the lock")
    scale = scalar(opts.get("rbf_attitude_gamma_scale", c.get("gamma_scale", 1.0)), "rbf_attitude_gamma_scale")
    dt_scale = scalar(opts.get("rbf_attitude_update_dt_scale", 1.0), "rbf_attitude_update_dt_scale")
    if not math.isclose(dt_scale, 1.0, rel_tol=0, abs_tol=1e-12):
        raise StopScene("C5 RBF update dt scale differs from locked unit scale")
    gamma = np.asarray(c["gamma"], dtype=np.float64).reshape(3) * scale
    sigma_w = np.asarray(c["sigma_w"], dtype=np.float64).reshape(3)
    s_limit = np.asarray(c["s_limit"], dtype=np.float64).reshape(3)
    dmax = np.asarray(c["dmax"], dtype=np.float64).reshape(3)
    wmax = scalar(c["wmax"], "rbf.attitude.wmax")
    W = np.zeros((np.asarray(c["centers"]).shape[1], 3), dtype=np.float64)
    raw, unclipped, clipped, torque = [], [], [], []
    rbf_inputs, W_before_all, W_dot_all, W_unprojected_all, W_after_all = [], [], [], [], []
    wnorm_after, projection = [], []
    for i, term in enumerate(ev["terms"]):
        z = np.array([term["error"][0], term["surface"][0],
                      term["error"][1], term["surface"][1],
                      term["error"][2], term["surface"][2]])
        phi = rbf_basis(z, c)
        W_before = W.copy()
        y = W_before.T @ phi
        yc = np.clip(y, -dmax, dmax)
        torque.append(j0 @ (ev["beta"][i] * yc))
        s_eff = np.clip(term["surface"], -s_limit, s_limit)
        basis_gamma = np.asarray(c.get("basis_gamma_scale", np.ones_like(phi)), dtype=np.float64).reshape(-1)
        if basis_gamma.size != phi.size or np.any(basis_gamma <= 0) or not np.all(np.isfinite(basis_gamma)):
            raise StopScene("C5 RBF basis gamma scale shape/value mismatch")
        W_dot = -np.outer(phi * basis_gamma, gamma * s_eff) - W_before * sigma_w
        W_unprojected = W_before + W_dot * (ev["dt"][i] * dt_scale)
        W = np.clip(W_unprojected, -wmax, wmax)
        raw.append(y); unclipped.append(y); clipped.append(yc)
        rbf_inputs.append(z.copy()); W_before_all.append(W_before); W_dot_all.append(W_dot)
        W_unprojected_all.append(W_unprojected); W_after_all.append(W.copy())
        wnorm_after.append(np.linalg.norm(W, ord="fro"))
        projection.append(np.any(np.abs(W_unprojected) > wmax))
    return {"raw": np.asarray(raw), "unclipped": np.asarray(unclipped),
            "clipped": np.asarray(clipped), "torque": np.asarray(torque),
            "input": np.asarray(rbf_inputs), "weight_before": np.asarray(W_before_all),
            "weight_dot": np.asarray(W_dot_all), "weight_unprojected": np.asarray(W_unprojected_all),
            "weight_after": np.asarray(W_after_all),
            "weight_norm_after": np.asarray(wnorm_after),
            "projection": np.asarray(projection, dtype=bool)}


def unwrap_scalar(value: Any) -> Any:
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    return value


def trace_records(tree: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    def visit(node):
        if isinstance(node, dict):
            if "sample_index" in node:
                raw_ix = numeric(unwrap_scalar(node["sample_index"]), "trace.sample_index").reshape(-1)
                if raw_ix.size == 1 and raw_ix[0] > 0:
                    found.append(node)
                    return
            for child in node.values():
                visit(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child)
    visit(tree)
    return found


def trace_field(rec: dict[str, Any], key: str, shape: tuple[int, ...] | None = None) -> np.ndarray:
    if key not in rec:
        raise StopScene(f"GRU trace missing {key}")
    arr = numeric(unwrap_scalar(rec[key]), f"trace.{key}")
    if shape is not None:
        if arr.size != int(np.prod(shape)):
            raise StopScene(f"GRU trace {key} shape mismatch: {arr.shape}")
        arr = arr.reshape(shape)
    return arr


def verify_gru_native(host: dict[str, Any], ev: dict[str, Any], replay: dict[str, np.ndarray],
                      row: dict[str, str], decoder) -> dict[str, float]:
    tree = host.get("gru_stream_attitude_trace")
    records = trace_records(tree)
    by_sample = {}
    for rec in records:
        ix_raw = float(trace_field(rec, "sample_index").reshape(-1)[0])
        if not ix_raw.is_integer():
            raise StopScene(f"GRU trace sample_index is non-integer: {ix_raw}")
        ix = int(ix_raw)
        if ix in by_sample:
            raise StopScene(f"duplicate GRU trace sample_index {ix}")
        by_sample[ix] = rec
    if len(by_sample) != EXPECTED_EVENTS:
        raise StopScene(f"GRU trace event count {len(by_sample)} != {EXPECTED_EVENTS}")
    maxima = {"accel": 0.0, "torque_nm": 0.0, "memory": 0.0, "time_s": 0.0, "event_dt_s": 0.0}
    for j, sample_index in enumerate(ev["sample_index"]):
        rec = by_sample.get(int(sample_index))
        if rec is None:
            raise StopScene(f"GRU trace missing sample {sample_index}")
        sample_logged = float(trace_field(rec, "sample_index").reshape(-1)[0])
        if sample_logged != float(sample_index):
            raise StopScene(f"GRU trace sample_index={sample_logged}, expected {sample_index}")
        pairs = [
            ("feature_raw", ev["features"][j], (13,)),
            ("feature_normalized", replay["feature_normalized"][j], (13,)),
            ("q_base_rad_s2", replay["base"][j], (3,)),
            ("raw_residual_rad_s2", replay["raw"][j], (3,)),
            ("clipped_residual_rad_s2", replay["clipped"][j], (3,)),
            ("beta_scaled_residual_rad_s2", replay["beta_scaled"][j], (3,)),
            ("estimateTorque_Nm", replay["torque"][j], (3,)),
            ("hidden_after", replay["hidden_after"][j], (32,)),
            ("hidden_before", np.zeros(32) if j == 0 else replay["hidden_after"][j - 1], (32,)),
            ("DeltaW_before", replay["delta_before"][j], (33, 3)),
            ("DeltaW_after", replay["delta_after"][j], (33, 3)),
        ]
        for name, expected, shp in pairs:
            actual = trace_field(rec, name, shp)
            err = float(np.max(np.abs(actual - expected)))
            if name in ("estimateTorque_Nm",):
                maxima["torque_nm"] = max(maxima["torque_nm"], err)
            elif name in ("hidden_after", "DeltaW_after"):
                maxima["memory"] = max(maxima["memory"], err)
            else:
                maxima["accel"] = max(maxima["accel"], err)
        dt_logged = float(trace_field(rec, "actual_event_dt").reshape(-1)[0])
        maxima["event_dt_s"] = max(maxima["event_dt_s"], abs(dt_logged - float(ev["dt"][j])))
        time_logged = float(trace_field(rec, "time_s").reshape(-1)[0])
        maxima["time_s"] = max(maxima["time_s"], abs(time_logged - float(ev["time"][j])))
        event_count = int(trace_field(rec, "event_count").reshape(-1)[0])
        if event_count != j + 1:
            raise StopScene(f"GRU trace event_count={event_count}, expected {j + 1}")
        if int(trace_field(rec, "is_attitude_event").reshape(-1)[0]) != 1:
            raise StopScene("GRU trace marks an expected event as non-event")
        projection = bool(int(trace_field(rec, "tracking_weight_projection_active").reshape(-1)[0]))
        if projection != bool(replay["projection"][j]):
            raise StopScene(f"GRU projection marker mismatch at sample {sample_index}")
        if bool(int(trace_field(rec, "output_precedes_tracking_update").reshape(-1)[0])) is not True:
            raise StopScene("GRU trace does not certify output-before-update ordering")
        update_norm = float(trace_field(rec, "tracking_update_norm").reshape(-1)[0])
        expected_update_norm = float(np.linalg.norm(replay["delta_after"][j] - replay["delta_before"][j], ord="fro"))
        maxima["memory"] = max(maxima["memory"], abs(update_norm - expected_update_norm))
        beta_logged = float(trace_field(rec, "beta").reshape(-1)[0])
        maxima["accel"] = max(maxima["accel"], abs(beta_logged - float(ev["beta"][j])))
    if (maxima["accel"] > RBF_TOL_ACCEL or maxima["torque_nm"] > TORQUE_TOL_NM or
            maxima["memory"] > MEMORY_TOL or maxima["time_s"] > 1e-12 or maxima["event_dt_s"] > 1e-12):
        raise StopScene(f"GRU native parity failed: {maxima}")
    # Candidate raw audit status/hash were already bound by the identity table.
    if row.get("audit_status") != "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY":
        raise StopScene("candidate raw audit status is not PASS")
    held = np.zeros((len(ev["event_flag"]), 3), dtype=np.float64)
    for j, i in enumerate(ev["index"]):
        held[i:] = replay["torque"][j]
    logged_torque = rows(host["attitude_compensation_applied_torque_Nm"], 3,
                         "attitude_compensation_applied_torque_Nm")
    if float(np.max(np.abs(logged_torque - held))) > TORQUE_TOL_NM:
        raise StopScene("candidate held GRU torque closure failed")
    return maxima


def verify_rbf_native(host: dict[str, Any], ev: dict[str, Any], replay: dict[str, np.ndarray]) -> dict[str, Any]:
    flags = vector(host["rbf_update_flag"], "rbf_update_flag").astype(bool)
    if len(flags) != len(ev["event_flag"]) or not np.array_equal(flags, ev["event_flag"]):
        raise StopScene("C5 RBF update flags differ from attitude events")
    if np.count_nonzero(flags) != EXPECTED_EVENTS:
        raise StopScene("C5 RBF update count is not 1999")
    logged_raw = rows(host["rbf_output_raw"], 3, "rbf_output_raw")[flags]
    logged_unclipped = masked_rows(host["rbf_output_unclipped"], 3, flags, "rbf_output_unclipped")
    logged_torque = rows(host["attitude_rbf_compensation_torque_Nm"], 3, "attitude_rbf_compensation_torque_Nm")
    logged_held = rows(host["rbf_output_held"], 3, "rbf_output_held")
    logged_input = rows(host["rbf_input_sample"], 6, "rbf_input_sample")[flags]
    logged_w_norm = vector(host["rbf_weight_norm"], "rbf_weight_norm")[flags]
    logged_event_time = vector(host["transition_time"], "transition_time")[flags]
    event_count = int(scalar(host["rbf_event_count"], "rbf_event_count"))
    if event_count != EXPECTED_EVENTS:
        raise StopScene(f"C5 rbf_event_count={event_count}, expected {EXPECTED_EVENTS}")
    audit = host["rbf_event_audit"]
    if not isinstance(audit, dict):
        raise StopScene("C5 rbf_event_audit did not decode as a struct")

    def audit_matrix(name: str, shape: tuple[int, ...]) -> np.ndarray:
        if name not in audit:
            raise StopScene(f"C5 rbf_event_audit missing {name}")
        arr = numeric(audit[name], f"rbf_event_audit.{name}")
        if arr.shape != shape:
            raise StopScene(f"C5 rbf_event_audit.{name} shape {arr.shape}, expected MATLAB shape {shape}")
        return arr

    def audit_vector(name: str) -> np.ndarray:
        if name not in audit:
            raise StopScene(f"C5 rbf_event_audit missing {name}")
        arr = numeric(audit[name], f"rbf_event_audit.{name}").squeeze()
        if arr.ndim != 1 or not 0 < arr.size <= 8:
            raise StopScene(f"C5 rbf_event_audit.{name} shape {arr.shape}; expected 1..8 stored snapshots")
        return arr

    snapshot_count = audit_vector("time").size
    expected_snapshots = min(8, EXPECTED_EVENTS)
    if snapshot_count != expected_snapshots:
        raise StopScene(f"C5 rbf_event_audit stores {snapshot_count} snapshots, expected {expected_snapshots}")
    n_events = snapshot_count
    n_basis = replay["weight_before"].shape[1]
    audit_time = audit_vector("time")
    audit_dt = audit_vector("dt")
    if audit_dt.size != n_events:
        raise StopScene(f"C5 rbf_event_audit.dt stores {audit_dt.size} values, expected {n_events}")
    audit_input = audit_matrix("input", (6, n_events))
    audit_output = audit_matrix("output_raw", (3, n_events))
    audit_w_before = audit_matrix("weight_before", (n_basis, 3, n_events))
    audit_w_dot = audit_matrix("weight_derivative", (n_basis, 3, n_events))
    audit_w_unprojected = audit_matrix("weight_unprojected", (n_basis, 3, n_events))
    audit_w_after = audit_matrix("weight_after", (n_basis, 3, n_events))
    errs = {
        "accel": float(np.max(np.abs(logged_raw - replay["clipped"]))),
        "unclipped": float(np.max(np.abs(logged_unclipped - replay["unclipped"]))),
        "weight_norm": float(np.max(np.abs(logged_w_norm - replay["weight_norm_after"]))),
        "per_step_input": float(np.max(np.abs(logged_input - replay["input"]))),
        "event_time": float(np.max(np.abs(logged_event_time - ev["time"]))),
        "audit_time": float(np.max(np.abs(audit_time - ev["time"][:n_events]))),
        "audit_dt": float(np.max(np.abs(audit_dt - ev["dt"][:n_events]))),
        "audit_input": float(np.max(np.abs(audit_input.T - replay["input"][:n_events]))),
        "audit_output": float(np.max(np.abs(audit_output.T - replay["clipped"][:n_events]))),
        "audit_weight_before": float(np.max(np.abs(np.transpose(audit_w_before, (2, 0, 1)) - replay["weight_before"][:n_events]))),
        "audit_weight_dot": float(np.max(np.abs(np.transpose(audit_w_dot, (2, 0, 1)) - replay["weight_dot"][:n_events]))),
        "audit_weight_unprojected": float(np.max(np.abs(np.transpose(audit_w_unprojected, (2, 0, 1)) - replay["weight_unprojected"][:n_events]))),
        "audit_weight_after": float(np.max(np.abs(np.transpose(audit_w_after, (2, 0, 1)) - replay["weight_after"][:n_events]))),
    }
    held = np.zeros_like(logged_torque)
    for j, i in enumerate(ev["index"]):
        held[i:] = replay["torque"][j]
    event_dt = vector(host["rbf_event_dt"], "rbf_event_dt")[flags]
    update_dt = vector(host["rbf_update_dt"], "rbf_update_dt")[flags]
    errs["event_dt"] = float(np.max(np.abs(event_dt - ev["dt"])))
    errs["update_dt"] = float(np.max(np.abs(update_dt - ev["dt"])))
    errs["torque_nm"] = float(np.max(np.abs(logged_torque - held)))
    errs["held_output_nm"] = float(np.max(np.abs(logged_held - held)))
    errs["audit_snapshot_count"] = snapshot_count
    errs["weight_snapshot_count_unobserved"] = EXPECTED_EVENTS - snapshot_count
    if (errs["accel"] > RBF_TOL_ACCEL or errs["unclipped"] > RBF_TOL_ACCEL or
            errs["weight_norm"] > MEMORY_TOL or errs["torque_nm"] > TORQUE_TOL_NM or
            errs["held_output_nm"] > TORQUE_TOL_NM or errs["event_time"] > 1e-12 or
            errs["event_dt"] > 1e-12 or errs["update_dt"] > 1e-12 or
            errs["per_step_input"] > MEMORY_TOL or errs["audit_time"] > 1e-12 or errs["audit_dt"] > 1e-12 or
            errs["audit_input"] > MEMORY_TOL or errs["audit_output"] > RBF_TOL_ACCEL or
            errs["audit_weight_before"] > MEMORY_TOL or errs["audit_weight_dot"] > MEMORY_TOL or
            errs["audit_weight_unprojected"] > MEMORY_TOL or errs["audit_weight_after"] > MEMORY_TOL):
        raise StopScene(f"C5 RBF native parity failed: {errs}")
    return errs


def check_root_path(path: Path, root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise StopRun(f"{label} escapes repository root: {path}") from exc


def approved_files(root: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    for rel, digest in EXPECTED_SHA.items():
        if rel in ("c5_snapshot", "candidate_snapshot", "c5_effective_config", "c5_position_model", "gru_model", "j0", "candidate_release"):
            continue
        assert_sha(root / Path(rel), digest, rel)
    csv_path = root / CSV_REL
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        items = list(csv.DictReader(f))
    if len(items) != 56:
        raise StopRun(f"identity CSV rows={len(items)}, expected 56")
    rows_by_scene: dict[str, dict[str, dict[str, str]]] = {}
    for r in items:
        scene, method = r["scene_id"], r["method"]
        if method not in ("Candidate", "C5") or "TEST" in scene or not scene.endswith(tuple(f"W{i:02d}" for i in range(9, 15))):
            raise StopRun(f"unexpected identity row: {scene}/{method}")
        if method in rows_by_scene.setdefault(scene, {}):
            raise StopRun(f"duplicate identity row: {scene}/{method}")
        rows_by_scene[scene][method] = r
        raw, status = Path(r["raw_path"]), Path(r["status_path"])
        check_root_path(raw, root, "raw")
        check_root_path(status, root, "status")
        assert_sha(raw, r["raw_expected_sha256"], f"{scene}/{method} raw")
        assert_sha(status, r["status_expected_sha256"], f"{scene}/{method} status")
        if r["field_check"] != "PASS" or r["missing_fields"]:
            raise StopRun(f"preflight field inventory no longer passes: {scene}/{method}")
        if method == "Candidate":
            audit_path = Path(r["audit_path"])
            check_root_path(audit_path, root, "candidate audit")
            assert_sha(audit_path, r["audit_expected_sha256"], f"{scene} candidate audit")
            if r["audit_status"] != "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY":
                raise StopRun(f"candidate audit status not PASS: {scene}")
        elif not r["lock_binding"].startswith("PASS_"):
            raise StopRun(f"C5 lock/status binding not PASS: {scene}")
    if len(rows_by_scene) != 28 or any(set(pair) != {"Candidate", "C5"} for pair in rows_by_scene.values()):
        raise StopRun("identity CSV is not exactly 28 complete candidate/C5 pairs")
    return items, rows_by_scene


def load_locked_cfg(root: Path, decoder, lock: dict[str, Any], locked_json: dict[str, Any]):
    ref = lock["upstream_refs"]["c5_prepared_snapshot"]
    snapshot = Path(ref["path"])
    check_root_path(snapshot, root, "C5 input-lock prepared snapshot")
    if str(ref.get("sha256", "")).lower() != EXPECTED_SHA["c5_snapshot"]:
        raise StopRun("C5 input-lock snapshot SHA differs from lock entry")
    assert_sha(snapshot, EXPECTED_SHA["c5_snapshot"], "C5 prepared snapshot")
    if not h5py.is_hdf5(snapshot):
        raise StopRun("C5 prepared cfg/opts MAT is not v7.3/HDF5; decoder fallback not authorized")
    cfg = decoder.matlab_section(snapshot, "cfg")
    opts = decoder.matlab_section(snapshot, "opts")
    if not isinstance(cfg, dict) or not isinstance(opts, dict):
        raise StopRun("C5 cfg/opts snapshot did not decode to structs")
    candidate_snapshot = Path(locked_json["cfg_snapshot_path"])
    check_root_path(candidate_snapshot, root, "candidate LOCKED_CFG prepared snapshot")
    if str(locked_json.get("cfg_snapshot_sha256", "")).lower() != EXPECTED_SHA["candidate_snapshot"]:
        raise StopRun("candidate LOCKED_CFG snapshot SHA differs from release lock")
    assert_sha(candidate_snapshot, EXPECTED_SHA["candidate_snapshot"], "candidate prepared cfg snapshot")
    candidate_cfg = decoder.matlab_section(candidate_snapshot, "cfg")
    candidate_opts = decoder.matlab_section(candidate_snapshot, "opts")

    def require_numeric_match(label: str, left: Any, right: Any) -> None:
        try:
            a = np.asarray(left, dtype=np.float64)
            b = np.asarray(right, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise StopRun(f"prepared snapshot field {label} is not numeric: {exc}") from exc
        if a.shape != b.shape or np.any(np.isnan(a)) or np.any(np.isnan(b)) or not np.array_equal(a, b):
            raise StopRun(f"prepared snapshots differ in {label}")

    for label, path in (
        ("plant.dt", ("plant", "dt")),
        ("plant.inertia", ("plant", "inertia")),
        ("command_filter.wn", ("control", "command_filter", "wn")),
        ("command_filter.damping", ("control", "command_filter", "damping")),
        ("command_filter.acceleration_limit", ("control", "command_filter", "acceleration_limit")),
        ("attitude_bs.k1", ("control", "bs", "attitude", "k1")),
        ("attitude_bs.k2", ("control", "bs", "attitude", "k2")),
    ):
        left, right = cfg, candidate_cfg
        for key in path:
            left, right = left[key], right[key]
        require_numeric_match(label, left, right)
    if matlab_text(cfg.get("controller_morphology_mode"), "C5 controller_morphology_mode") != "fixed" or \
            matlab_text(candidate_cfg.get("controller_morphology_mode"), "candidate controller_morphology_mode") != "fixed":
        raise StopRun("prepared snapshot controller morphology is not fixed")
    c5_rbf, candidate_rbf = cfg["rbf"]["attitude"], candidate_cfg["rbf"]["attitude"]
    if set(c5_rbf) != set(candidate_rbf):
        raise StopRun("prepared snapshots have different attitude RBF config fields")
    for key in sorted(c5_rbf):
        require_numeric_match(f"rbf.attitude.{key}", c5_rbf[key], candidate_rbf[key])
    option_defaults = {"rbf_attitude_output_delay_events": 0, "rbf_attitude_update_dt_scale": 1.0}
    for key in ("formal_rbf_baseline", "rbf_attitude_enabled", "rbf_attitude_output_enabled",
                "rbf_attitude_update_enabled", "rbf_attitude_gamma_scale", *option_defaults):
        left = opts.get(key, option_defaults.get(key, "<MISSING>"))
        right = candidate_opts.get(key, option_defaults.get(key, "<MISSING>"))
        if left == "<MISSING>" or right == "<MISSING>":
            if left != right:
                raise StopRun(f"prepared snapshots differ in option {key}")
            continue
        require_numeric_match(f"opts.{key}", left, right)
    if "rbf_attitude_initial_weight" in opts or "rbf_attitude_initial_weight" in candidate_opts:
        raise StopRun("prepared snapshot contains an RBF attitude initial-weight override")
    if not bool(scalar(opts.get("formal_rbf_baseline", 0), "formal_rbf_baseline")):
        raise StopRun("C5 options do not bind formal fixed RBF baseline")
    for key in ("rbf_attitude_enabled", "rbf_attitude_output_enabled", "rbf_attitude_update_enabled"):
        if not bool(scalar(opts.get(key, 0), key)):
            raise StopRun(f"C5 option {key} is disabled")
    if matlab_text(cfg.get("controller_morphology_mode"), "controller_morphology_mode") != "fixed":
        raise StopRun("C5 cfg controller morphology is not fixed")
    if abs(scalar(cfg["plant"]["dt"], "cfg.plant.dt") - 0.001) > 1e-12:
        raise StopRun("C5 cfg Plant dt differs from 1 ms lock")
    j0 = np.asarray(locked_json["J0_kgm2"], dtype=np.float64)
    if locked_json.get("J0_sha256", "").lower() != EXPECTED_SHA["j0"]:
        raise StopRun("LOCKED_CFG embedded J0 SHA differs from approval")
    if hashlib.sha256(j0.astype("<f8").tobytes(order="F")).hexdigest() != EXPECTED_SHA["j0"]:
        raise StopRun("fixed J0 byte identity differs from lock")
    if not np.allclose(np.asarray(locked_json["Pfixed_inertia_dot_for_bs_kgm2_s"]), 0, rtol=0, atol=0):
        raise StopRun("Jdot0 must be exactly zero")
    c5_cfg_path = root / Path("configs/effective_config.mat")
    assert_sha(c5_cfg_path, EXPECTED_SHA["c5_effective_config"], "C5 effective config")
    return cfg, opts, j0


def load_models_and_locks(root: Path, decoder, rows_by_scene):
    score = load_json(root / SCORE_REL)
    release = load_json(root / RELEASE_REL)
    c5_lock = load_json(root / C5_LOCK_REL)
    c5_batch = load_json(root / C5_BATCH_REL)
    locked_cfg_json = load_json(root / LOCKED_CFG_REL)
    assert_sha(root / RELEASE_REL, EXPECTED_SHA["candidate_release"], "candidate RELEASE")
    assert_sha(root / LOCKED_CFG_REL, EXPECTED_SHA[LOCKED_CFG_REL.as_posix()], "GRU LOCKED_CFG")
    if score["input_bindings"]["release_sha256"] != EXPECTED_SHA["candidate_release"]:
        raise StopRun("candidate release SHA in score changed")
    if release["model_sha256"] != EXPECTED_SHA["gru_model"]:
        raise StopRun("GRU model SHA in RELEASE changed")
    expected_candidate = "GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001"
    if (release.get("study_id") != "gru_stream_cosine_tracking_head_full72_v1" or
            release.get("candidate") != expected_candidate or score.get("candidate") != expected_candidate):
        raise StopRun("release/score candidate identity differs from frozen GRU32 checkpoint")
    score_rows = {r["scene_id"]: r for r in score["rows"] if "HF_W09_W14" in r.get("groups", [])}
    if set(score_rows) != set(rows_by_scene) or len(score_rows) != 28:
        raise StopRun("identity CSV scene set differs from approved FULL72 HF rows")
    c5_lock_rows = {r["scene_id"]: r for r in c5_lock["scenes"]}
    c5_batch_rows = {r["scene_id"]: r for r in c5_batch["records"]}
    def canon(s: str) -> str:
        return os.path.normcase(os.path.normpath(s))
    for sid, pair in rows_by_scene.items():
        for method, score_name in (("Candidate", "Candidate"), ("C5", "C5")):
            identity = pair[method]
            locked = score_rows[sid]["methods"][score_name]
            if canon(identity["raw_path"]) != canon(locked["raw_path"]):
                raise StopRun(f"CSV/score raw path disagreement: {sid}/{method}")
            if identity["raw_expected_sha256"].lower() != locked["raw_sha256"].lower():
                raise StopRun(f"CSV/score raw SHA disagreement: {sid}/{method}")
            if identity["status_expected_sha256"].lower() != locked["status_sha256"].lower():
                raise StopRun(f"CSV/score status SHA disagreement: {sid}/{method}")
            if method == "Candidate":
                if identity["audit_expected_sha256"].lower() != locked["audit_sha256"].lower():
                    raise StopRun(f"CSV/score audit SHA disagreement: {sid}/Candidate")
        cr = pair["C5"]
        lockrow = c5_lock_rows[sid]
        if lockrow.get("candidate_action") == "REUSE_AUDITED_C5_SCREEN":
            bind = lockrow.get("C5_reuse", {})
        else:
            bind = c5_batch_rows.get(sid, {})
        if canon(cr["raw_path"]) != canon(bind.get("raw_path", "")) or canon(cr["status_path"]) != canon(bind.get("run_status_path", "")):
            raise StopRun(f"CSV/C5 lock or batch paths disagree: {sid}")
        if cr["raw_expected_sha256"].lower() != str(bind.get("raw_sha256", "")).lower() or cr["status_expected_sha256"].lower() != str(bind.get("run_status_sha256", "")).lower():
            raise StopRun(f"CSV/C5 lock or batch hashes disagree: {sid}")
    model_path = Path(release["model_path"])
    assert_sha(model_path, EXPECTED_SHA["gru_model"], "frozen GRU model")
    c5_model = next(Path(x["path"]) for x in c5_lock["shared_input_files"] if x["role"] == "model_mat")
    assert_sha(c5_model, EXPECTED_SHA["c5_position_model"], "DSSM14 model")
    effective = next(x for x in c5_lock["shared_input_files"] if x["role"] == "effective_config_mat")
    if canon(effective["path"]) != canon(str(root / "configs/effective_config.mat")) or effective["sha256"].lower() != EXPECTED_SHA["c5_effective_config"]:
        raise StopRun("C5 effective config path/SHA differs from input lock")
    source_paths = {x["path"]: x["sha256"] for x in c5_lock["active_source_inventory"]}
    for name, digest in source_paths.items():
        assert_sha(Path(name), digest, f"C5 source {Path(name).name}")

    model_ref = import_file(root / Path("experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/trained_model_parity_reference.py"), "frozen_gru_parity_ref")
    GRU_REF = model_ref
    model = GRU_REF.model_from_mat(loadmat(model_path))
    required = {"input_mean", "input_std", "target_rms", "gru_weight_ih", "gru_weight_hh", "gru_bias_ih", "gru_bias_hh", "head_weight", "head_bias"}
    if not required.issubset(model):
        raise StopRun("GRU model is missing frozen forward fields")
    if np.asarray(model["gru_weight_ih"]).shape != (96, 13) or np.asarray(model["gru_weight_hh"]).shape != (96, 32):
        raise StopRun("GRU model gate shapes mismatch")
    cfg, opts, j0 = load_locked_cfg(root, decoder, c5_lock, locked_cfg_json)
    return GRU_REF, model, cfg, opts, j0, c5_lock, c5_batch, score


def load_host(row: dict[str, str], decoder, method: str) -> dict[str, Any]:
    return field_dict(Path(row["raw_path"]), decoder, method, include_trace=(method == "Candidate"))


def compare_trace_vector(rec, name, expected, shape=None) -> float:
    actual = trace_field(rec, name, shape)
    return float(np.max(np.abs(actual - expected)))


def scene_check(checks: list[dict[str, str]], name: str, fn):
    try:
        result = fn()
    except (StopScene, StopRun) as exc:
        checks.append({"check": name, "status": "FAIL", "detail": str(exc)})
        raise StopScene(str(exc), list(checks)) from exc
    checks.append({"check": name, "status": "PASS"})
    return result


def run_scene(scene: str, scene_rows: dict[str, dict[str, str]], decoder,
              gru_ref, model, cfg, opts, j0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, str]] = []
    candidate_row, c5_row = scene_rows["Candidate"], scene_rows["C5"]
    cand = scene_check(checks, "candidate_raw_fields", lambda: load_host(candidate_row, decoder, "Candidate"))
    c5 = scene_check(checks, "c5_raw_fields", lambda: load_host(c5_row, decoder, "C5"))

    def check_model_sha():
        raw_sha = matlab_text(cand["gru_stream_attitude_model_sha256"], "gru_stream_attitude_model_sha256")
        if raw_sha.lower() != EXPECTED_SHA["gru_model"]:
            raise StopScene("candidate raw GRU model SHA field differs from frozen model")
    scene_check(checks, "candidate_raw_gru_model_sha", check_model_sha)
    cand_ref, cand_rate, cand_acc = scene_check(checks, "candidate_causal_filter", lambda: filter_replay(cand, cfg))
    c5_ref, c5_rate, c5_acc = scene_check(checks, "c5_causal_filter", lambda: filter_replay(c5, cfg))
    cand_ev = scene_check(checks, "candidate_event_features", lambda: event_data(cand, cand_ref, cand_rate, cand_acc, cfg, j0))
    c5_ev = scene_check(checks, "c5_event_features", lambda: event_data(c5, c5_ref, c5_rate, c5_acc, cfg, j0))

    def check_pair_alignment():
        if not np.array_equal(cand_ev["sample_index"], c5_ev["sample_index"]):
            raise StopScene("candidate/C5 event sample indices differ")
        if not np.allclose(cand_ev["time"], c5_ev["time"], rtol=0, atol=1e-12):
            raise StopScene("candidate/C5 event times differ")
        if not np.allclose(cand_ev["dt"], c5_ev["dt"], rtol=0, atol=1e-12):
            raise StopScene("candidate/C5 event dt differs")
    scene_check(checks, "same_scene_event_alignment", check_pair_alignment)

    cand_gru = scene_check(checks, "candidate_gru_replay", lambda: gru_replay(gru_ref, cand_ev, model, cfg, j0))
    c5_gru = scene_check(checks, "c5_state_gru_replay", lambda: gru_replay(gru_ref, c5_ev, model, cfg, j0))
    cand_rbf = scene_check(checks, "candidate_state_c5_rbf_replay", lambda: rbf_replay(cand_ev, cfg, opts, j0))
    c5_rbf = scene_check(checks, "c5_native_rbf_replay", lambda: rbf_replay(c5_ev, cfg, opts, j0))
    gru_native = scene_check(checks, "candidate_gru_native_parity", lambda: verify_gru_native(cand, cand_ev, cand_gru, candidate_row, decoder))
    rbf_native = scene_check(checks, "c5_rbf_native_parity", lambda: verify_rbf_native(c5, c5_ev, c5_rbf))

    event_rows = []
    for host_name, ev, gru, rbf in (("candidate", cand_ev, cand_gru, cand_rbf), ("C5", c5_ev, c5_gru, c5_rbf)):
        for i, idx in enumerate(ev["index"]):
            event_rows.append({
                "scene_id": scene, "host": host_name,
                "time_s": float(vector((cand if host_name == "candidate" else c5)["transition_time"], "transition_time")[idx]),
                "sample_index_1based": int(ev["sample_index"][i]), "actual_event_dt_s": float(ev["dt"][i]),
                "beta": float(ev["beta"][i]),
                "gru_q_raw_roll": gru["raw"][i, 0], "gru_q_raw_pitch": gru["raw"][i, 1], "gru_q_raw_yaw": gru["raw"][i, 2],
                "gru_q_clip_roll": gru["clipped"][i, 0], "gru_q_clip_pitch": gru["clipped"][i, 1], "gru_q_clip_yaw": gru["clipped"][i, 2],
                "gru_beta_scaled_roll": gru["beta_scaled"][i, 0], "gru_beta_scaled_pitch": gru["beta_scaled"][i, 1], "gru_beta_scaled_yaw": gru["beta_scaled"][i, 2],
                "gru_torque_roll_Nm": gru["torque"][i, 0], "gru_torque_pitch_Nm": gru["torque"][i, 1], "gru_torque_yaw_Nm": gru["torque"][i, 2],
                "rbf_q_raw_roll": rbf["raw"][i, 0], "rbf_q_raw_pitch": rbf["raw"][i, 1], "rbf_q_raw_yaw": rbf["raw"][i, 2],
                "rbf_q_clip_roll": rbf["clipped"][i, 0], "rbf_q_clip_pitch": rbf["clipped"][i, 1], "rbf_q_clip_yaw": rbf["clipped"][i, 2],
                "rbf_beta_scaled_roll": ev["beta"][i] * rbf["clipped"][i, 0], "rbf_beta_scaled_pitch": ev["beta"][i] * rbf["clipped"][i, 1], "rbf_beta_scaled_yaw": ev["beta"][i] * rbf["clipped"][i, 2],
                "rbf_torque_roll_Nm": rbf["torque"][i, 0], "rbf_torque_pitch_Nm": rbf["torque"][i, 1], "rbf_torque_yaw_Nm": rbf["torque"][i, 2],
                "delta_torque_roll_Nm": gru["torque"][i, 0] - rbf["torque"][i, 0],
                "delta_torque_pitch_Nm": gru["torque"][i, 1] - rbf["torque"][i, 1],
                "delta_torque_yaw_Nm": gru["torque"][i, 2] - rbf["torque"][i, 2],
                "delta_beta_scaled_roll_rad_s2": gru["beta_scaled"][i, 0] - ev["beta"][i] * rbf["clipped"][i, 0],
                "delta_beta_scaled_pitch_rad_s2": gru["beta_scaled"][i, 1] - ev["beta"][i] * rbf["clipped"][i, 1],
                "delta_beta_scaled_yaw_rad_s2": gru["beta_scaled"][i, 2] - ev["beta"][i] * rbf["clipped"][i, 2],
                "gru_hidden_norm": float(np.linalg.norm(gru["hidden_after"][i])),
                "gru_deltaW_norm": float(np.linalg.norm(gru["delta_after"][i], ord="fro")),
                "rbf_W_norm": float(rbf["weight_norm_after"][i]),
                "gru_projection": bool(gru["projection"][i]), "rbf_projection": bool(rbf["projection"][i]),
            })
    return event_rows, {"scene_id": scene, "status": "PASS_NATIVE_PARITY_AND_SHADOW",
                        "candidate_raw_status": candidate_row["status_value"],
                        "candidate_audit_status": candidate_row["audit_status"],
                        "c5_raw_status": c5_row["status_value"],
                        "c5_audit_status": c5_row["audit_status"],
                        "local_checks": checks,
                        "gru_native_max_abs": gru_native, "rbf_native_max_abs": rbf_native,
                        "event_count": EXPECTED_EVENTS, "host_trajectories": 2,
                        "c5_weight_snapshots_observed": rbf_native["audit_snapshot_count"],
                        "c5_weight_snapshots_unobserved": rbf_native["weight_snapshot_count_unobserved"],
                        "c5_full_weight_matrices_logged_only_for_first_8_events": True,
                        "weight_snapshot_disclosure": "Only the first eight full C5 weight matrices are present in raw audit; remaining-event weights are reconstructed, not directly observed."}


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def summary_metrics(event_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for host in ("candidate", "C5"):
        rows_host = [r for r in event_rows if r["host"] == host]
        for quantity, unit, suffix, prefix in (("torque_difference", "Nm", "Nm", "delta_torque"),
                                               ("beta_scaled_residual_difference", "rad/s^2", "rad_s2", "delta_beta_scaled")):
            for axis in ("roll", "pitch", "yaw"):
                x = np.asarray([r[f"{prefix}_{axis}_{suffix}"] for r in rows_host], dtype=np.float64) if rows_host else np.asarray([])
                if not len(x):
                    continue
                out.append({"host": host, "quantity": quantity, "unit": unit, "axis": axis, "n": len(x),
                            "signed_mean": float(np.mean(x)), "rmse": float(np.sqrt(np.mean(x*x))),
                            "p95_abs": float(np.percentile(np.abs(x), 95)), "max_abs": float(np.max(np.abs(x)))})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute-approved", action="store_true", help="Required to run; omit for help/review only.")
    args = parser.parse_args()
    if not args.execute_approved:
        parser.error("execution is disabled until ROOT review: pass --execute-approved only after explicit release")
    root = args.repo_root.resolve()
    if not root.is_dir():
        raise StopRun(f"repo root does not exist: {root}")
    outdir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    outdir = outdir.resolve()
    check_root_path(outdir, root, "output directory")
    if outdir.exists():
        raise StopRun(f"output directory must be new and empty; refusing overwrite: {outdir}")
    outdir.mkdir(parents=True, exist_ok=False)

    decoder = import_file(root / Path("reports/paper14_v2/phase1/audit_w15_position_replay.py"), "locked_matlab_decoder")
    items, rows_by_scene = approved_files(root)
    GRU_REF, model, cfg, opts, j0, c5_lock, c5_batch, score = load_models_and_locks(root, decoder, rows_by_scene)
    write_json(outdir / "INPUT_PREFLIGHT.json", {
        "status": "PASS_IDENTITY_LOCKS",
        "entrypoint_path": str(Path(__file__).resolve()),
        "entrypoint_sha256": sha256(Path(__file__).resolve()),
        "entrypoint_argv": list(sys.argv),
        "taskbook_sha256": EXPECTED_SHA[TASKBOOK_REL.as_posix()],
        "identity_csv_sha256": EXPECTED_SHA[CSV_REL.as_posix()],
        "root_amendment_sha256": EXPECTED_SHA[AMENDMENT_REL.as_posix()],
        "score_sha256": EXPECTED_SHA[SCORE_REL.as_posix()],
        "c5_lock_sha256": EXPECTED_SHA[C5_LOCK_REL.as_posix()],
        "c5_batch_sha256": EXPECTED_SHA[C5_BATCH_REL.as_posix()],
        "raw_status_rows": len(items), "candidate_rows": 28, "c5_rows": 28,
        "gru_model_sha256": EXPECTED_SHA["gru_model"], "fixed_j0_sha256": EXPECTED_SHA["j0"],
        "c5_position_model_sha256": EXPECTED_SHA["c5_position_model"],
        "c5_input_lock_snapshot_sha256": EXPECTED_SHA["c5_snapshot"],
        "candidate_locked_cfg_snapshot_sha256": EXPECTED_SHA["candidate_snapshot"],
        "TEST_read": False, "Plant_calls": 0, "MATLAB_started": False, "training_steps": 0,
    })

    event_all: list[dict[str, Any]] = []
    scene_reports: list[dict[str, Any]] = []
    # Approved initial parity gate: one locked reuse and one new C5 raw first.
    for sid in (REUSE_PREFLIGHT, NEW_PREFLIGHT):
        try:
            event_rows, report = run_scene(sid, rows_by_scene[sid], decoder, GRU_REF, model, cfg, opts, j0)
            event_all.extend(event_rows); scene_reports.append(report)
        except StopScene as exc:
            report = {"scene_id": sid, "status": "FEASIBILITY_ONLY", "reason": str(exc),
                      "local_checks": exc.checks,
                      "weight_snapshot_disclosure": "Only the first eight full C5 weight matrices are stored; later-event matrices are reconstructed, not directly observed.",
                      "candidate_raw_status": rows_by_scene[sid]["Candidate"]["status_value"],
                      "c5_raw_status": rows_by_scene[sid]["C5"]["status_value"]}
            scene_reports.append(report)
            write_json(outdir / "PREFLIGHT_STOP.json", report)
            return 2
    write_json(outdir / "PREFLIGHT_PASS.json", {"status": "PASS_REUSE_AND_NEW_RAW", "scenes": scene_reports})

    for sid in sorted(rows_by_scene):
        if sid in (REUSE_PREFLIGHT, NEW_PREFLIGHT):
            continue
        try:
            event_rows, report = run_scene(sid, rows_by_scene[sid], decoder, GRU_REF, model, cfg, opts, j0)
            event_all.extend(event_rows); scene_reports.append(report)
        except StopScene as exc:
            scene_reports.append({"scene_id": sid, "status": "FEASIBILITY_ONLY", "reason": str(exc),
                                 "local_checks": exc.checks,
                                 "weight_snapshot_disclosure": "Only the first eight full C5 weight matrices are stored; later-event matrices are reconstructed, not directly observed.",
                                 "candidate_raw_status": rows_by_scene[sid]["Candidate"]["status_value"],
                                 "c5_raw_status": rows_by_scene[sid]["C5"]["status_value"]})

    table = outdir / "SAME_STATE_ACTIONS_v1.csv.gz"
    if event_all:
        with gzip.open(table, "wt", encoding="utf-8", newline="", compresslevel=6) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(event_all[0]))
            writer.writeheader(); writer.writerows(event_all)
    if sum(p.stat().st_size for p in outdir.iterdir() if p.is_file()) > MAX_OUTPUT_BYTES:
        raise StopRun("generated output exceeds 5 GiB; no raw inputs are copied")
    pass_scenes = [r for r in scene_reports if r["status"] == "PASS_NATIVE_PARITY_AND_SHADOW"]
    result = {
        "status": "PASS_COMPLETE" if len(pass_scenes) == 28 else "PARTIAL_FEASIBILITY_ONLY",
        "scene_count": len(scene_reports), "passed_scene_count": len(pass_scenes),
        "results": scene_reports, "action_summary": summary_metrics(event_all),
        "weight_snapshot_disclosure": "C5 full weight matrices were logged only for each scene's first eight events; remaining-event weights are reconstructed from the locked zero-initialized replay.",
        "action_table": table.name if table.exists() else None,
        "output_bytes": sum(p.stat().st_size for p in outdir.iterdir() if p.is_file()),
        "output_limit_bytes": MAX_OUTPUT_BYTES, "raw_files_copied": 0,
        "Plant_calls": 0, "MATLAB_started": False, "training_steps": 0, "TEST_read": False,
        "interpretation": "conditional same-state action comparison only; no counterfactual closed-loop SO(3) claim",
    }
    write_json(outdir / "RESULT_v1.json", result)
    return 0 if len(pass_scenes) == 28 else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StopRun, StopScene) as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
