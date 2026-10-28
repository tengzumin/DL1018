from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np
import scipy.io


ROOT = Path(__file__).resolve().parent
V3 = ROOT.parent / "mlp15_composite_dev_v3"
SCENES = [
    "DL1018_VAL_T1_C08_W15",
    "DL1018_VAL_T2_C05_W15",
    "DL1018_VAL_T3_C02_W15",
    "DL1018_VAL_T1_C05_W12",
    "DL1018_VAL_T2_C02_W12",
    "DL1018_VAL_T3_C00_W13",
]
AXES = ("roll", "pitch", "yaw")
EPSILONS = (1e-5, 5e-6)
SAMPLE_COUNT = 200


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matlab_array(obj) -> np.ndarray:
    arr = np.asarray(obj)
    if arr.ndim > 1:
        arr = arr.transpose(tuple(range(arr.ndim - 1, -1, -1)))
    return arr


def scalar(group, name: str) -> float:
    return float(matlab_array(group[name]).reshape(-1)[0])


def vec(group, name: str) -> np.ndarray:
    return np.asarray(matlab_array(group[name]), dtype=np.float64).reshape(-1)


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -700.0, 700.0)
    return 1.0 / (1.0 + np.exp(-x))


def forward(window: np.ndarray, model: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    z1 = model["fc1_weight"] @ window.reshape(-1, order="F") + model["fc1_bias"]
    h1 = z1 * sigmoid(z1)
    z2 = model["fc2_weight"] @ h1 + model["fc2_bias"]
    hidden = z2 * sigmoid(z2)
    base = (model["head_weight"] @ hidden + model["head_bias"]) * model["target_rms"]
    phi = np.r_[hidden, 1.0]
    phi /= np.linalg.norm(phi)
    return base, hidden, phi


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def bs_nominal(eta: np.ndarray, omega: np.ndarray, ref: np.ndarray,
               ref_rate: np.ndarray, ref_accel: np.ndarray, k1: np.ndarray,
               k2: np.ndarray, J0: np.ndarray, Jdot0: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    roll = float(eta[0])
    pitch = float(np.clip(eta[1], -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4))
    T = np.array([
        [1.0, np.sin(roll) * np.tan(pitch), np.cos(roll) * np.tan(pitch)],
        [0.0, np.cos(roll), -np.sin(roll)],
        [0.0, np.sin(roll) / np.cos(pitch), np.cos(roll) / np.cos(pitch)],
    ])
    eta_rate = T @ omega
    phi, theta = roll, pitch
    phi_dot, theta_dot = eta_rate[0], eta_rate[1]
    sphi, cphi = np.sin(phi), np.cos(phi)
    ttheta, sectheta = np.tan(theta), 1.0 / np.cos(theta)
    Tphi = np.array([
        [0.0, cphi * ttheta, -sphi * ttheta],
        [0.0, -sphi, -cphi],
        [0.0, cphi * sectheta, -sphi * sectheta],
    ])
    Ttheta = np.array([
        [0.0, sphi * sectheta**2, cphi * sectheta**2],
        [0.0, 0.0, 0.0],
        [0.0, sphi * sectheta * ttheta, cphi * sectheta * ttheta],
    ])
    Tdot = Tphi * phi_dot + Ttheta * theta_dot
    e = wrap(ref - eta)
    de = ref_rate - eta_rate
    alpha = ref_rate + k1 * e
    z2 = alpha - eta_rate
    alpha_dot = ref_accel + k1 * de
    nominal_eta_accel = alpha_dot + e + k2 * z2
    nominal_body_alpha = np.linalg.solve(T, nominal_eta_accel - Tdot @ omega)
    gyro = np.cross(omega, J0 @ omega)
    nominal_tau = J0 @ nominal_body_alpha + gyro + Jdot0 @ omega
    return nominal_tau, z2


def bs_analytic_jacobian(eta: np.ndarray, omega: np.ndarray, k1: np.ndarray,
                         k2: np.ndarray, J0: np.ndarray, Jdot0: np.ndarray) -> np.ndarray:
    roll = float(eta[0])
    pitch = float(np.clip(eta[1], -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4))
    phi, theta = roll, pitch
    sphi, cphi = np.sin(phi), np.cos(phi)
    ttheta, sectheta = np.tan(theta), 1.0 / np.cos(theta)
    T = np.array([
        [1.0, sphi * ttheta, cphi * ttheta],
        [0.0, cphi, -sphi],
        [0.0, sphi * sectheta, cphi * sectheta],
    ])
    A = np.array([
        [0.0, cphi * ttheta, -sphi * ttheta],
        [0.0, -sphi, -cphi],
        [0.0, cphi * sectheta, -sphi * sectheta],
    ])
    B = np.array([
        [0.0, sphi * sectheta**2, cphi * sectheta**2],
        [0.0, 0.0, 0.0],
        [0.0, sphi * sectheta * ttheta, cphi * sectheta * ttheta],
    ])
    u, v = T[0], T[1]
    uomega, vomega = u @ omega, v @ omega
    DH = np.outer(A @ omega, u) + uomega * A + np.outer(B @ omega, v) + vomega * B
    matrix = -np.diag(k1 + k2) @ T - DH

    def skew(q):
        return np.array([[0.0, -q[2], q[1]], [q[2], 0.0, -q[0]], [-q[1], q[0], 0.0]])

    return J0 @ np.linalg.solve(T, matrix) - skew(J0 @ omega) + skew(omega) @ J0 + Jdot0


def load_constants_and_model() -> tuple[dict, dict, dict, dict]:
    lock_path = V3 / "LOCKED_CFG.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    snapshot = Path(lock["cfg_snapshot_path"])
    if sha256(snapshot) != lock["cfg_snapshot_sha256"]:
        raise ValueError("fixed cfg snapshot SHA differs from LOCKED_CFG")
    # Read only the fixed controller gains from the prepared snapshot. No inertia
    # or morphology value is read from cfg/plant or reconstructed from arm data.
    with h5py.File(snapshot, "r") as f:
        k1 = np.asarray(f["cfg/control/bs/attitude/k1"], dtype=np.float64).reshape(-1)
        k2 = np.asarray(f["cfg/control/bs/attitude/k2"], dtype=np.float64).reshape(-1)
    if not np.array_equal(k1, np.asarray(lock["K1"], dtype=np.float64)):
        raise ValueError("snapshot K1 differs from fixed LOCKED_CFG K1")
    J0 = np.asarray(lock["J0_kgm2"], dtype=np.float64)
    Jfixed = np.asarray(lock["Pfixed_inertia_kgm2"], dtype=np.float64)
    if not np.array_equal(J0, Jfixed):
        raise ValueError("fixed J0 and Pfixed inertia labels disagree")
    Jdot0 = np.asarray(lock["Pfixed_inertia_dot_for_bs_kgm2_s"], dtype=np.float64)
    if np.any(Jdot0 != 0):
        raise ValueError("expected the fixed controller Jdot0 to be zero")
    model_path = Path(lock["mlp15_full72_model_path"])
    if sha256(model_path) != lock["mlp15_full72_model_sha256"]:
        raise ValueError("full72 MLP SHA differs from fixed LOCKED_CFG")
    mat = scipy.io.loadmat(model_path, squeeze_me=True, struct_as_record=False)
    model = {key: np.asarray(mat[key], dtype=np.float64) for key in (
        "input_mean", "input_std", "target_rms", "fc1_weight", "fc1_bias",
        "fc2_weight", "fc2_bias", "head_weight", "head_bias")}
    for key in ("input_mean", "input_std", "target_rms", "fc1_bias", "fc2_bias", "head_bias"):
        model[key] = model[key].reshape(-1)
    if model["fc1_weight"].shape != (64, 195) or model["fc2_weight"].shape != (32, 64) or model["head_weight"].shape != (3, 32):
        raise ValueError("unexpected full72 MLP shapes")
    constants = {
        "K1": k1, "K2": k2, "J0": J0, "Jdot0": Jdot0,
        "dmax": np.asarray(lock["dmax"], dtype=np.float64),
    }
    sources = {
        "locked_cfg_path": str(lock_path), "locked_cfg_sha256": sha256(lock_path),
        "fixed_cfg_snapshot_path": str(snapshot), "fixed_cfg_snapshot_sha256": sha256(snapshot),
        "full72_model_path": str(model_path), "full72_model_sha256": sha256(model_path),
        "locked_controller_core_path": str(V3 / "candidate_runner_work" / "matlab" / "core" / "attitude_bs_step.m"),
        "locked_controller_core_sha256": sha256(V3 / "candidate_runner_work" / "matlab" / "core" / "attitude_bs_step.m"),
        "mlp_forward_path": str(V3 / "candidate_runner_work" / "matlab" / "runtime" / "mlp15_attitude_forward_v1.m"),
        "mlp_forward_sha256": sha256(V3 / "candidate_runner_work" / "matlab" / "runtime" / "mlp15_attitude_forward_v1.m"),
        "mlp_step_path": str(V3 / "candidate_runner_work" / "matlab" / "runtime" / "mlp15_attitude_step_v1.m"),
        "mlp_step_sha256": sha256(V3 / "candidate_runner_work" / "matlab" / "runtime" / "mlp15_attitude_step_v1.m"),
    }
    return lock, constants, model, sources


def get_scene_data(scene_id: str, model: dict, constants: dict) -> tuple[list[dict], dict]:
    raw_path = V3 / "runs" / scene_id / "raw_run.mat"
    status_path = V3 / "runs" / scene_id / "run_status.json"
    audit_path = V3 / "audits" / f"{scene_id}_COMPOSITE_DEV_AUDIT.json"
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    raw_sha = sha256(raw_path)
    if status["state"] != "COMPLETED" or status["status_value"] != "STABLE":
        raise ValueError(f"scene not completed/stable: {scene_id}")
    if audit["status"] != "PASS_INDEPENDENT_COMPOSITE_DEV_RAW_REPLAY":
        raise ValueError(f"locked raw audit failed: {scene_id}")
    if raw_sha != status["raw_sha256"] or raw_sha != audit["candidate_raw_sha256"]:
        raise ValueError(f"raw SHA mismatch: {scene_id}")

    events: list[dict] = []
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        state = np.asarray(matlab_array(log["state"]), dtype=np.float64)
        time = vec(log, "time")
        ref = np.asarray(matlab_array(log["filtered_attitude_reference"]), dtype=np.float64)
        ref_rate = np.asarray(matlab_array(log["filtered_attitude_rate"]), dtype=np.float64)
        ref_accel = np.asarray(matlab_array(log["command_filter_acceleration_applied_rads2"]), dtype=np.float64)
        raw_nominal = np.asarray(matlab_array(log["attitude_bs_nominal_torque_Nm"]), dtype=np.float64)
        raw_compensation = np.asarray(matlab_array(log["attitude_compensation_applied_torque_Nm"]), dtype=np.float64)
        requested = np.asarray(matlab_array(log["requested_generalized"]), dtype=np.float64)
        arms = np.asarray(matlab_array(log["arms"]["command"]), dtype=np.float64)
        event_flags = np.asarray(matlab_array(log["attitude_event_flag"]), dtype=bool).reshape(-1)
        trace_cells = log["mlp15_attitude_trace"][0, :]
        event_indices = np.flatnonzero(event_flags)

        history = np.zeros((13, 14), dtype=np.float64)
        contexts = []
        for ordinal, raw_index in enumerate(event_indices):
            event_ref = trace_cells[int(raw_index)]
            if not event_ref:
                raise ValueError(f"empty trace at event {raw_index}: {scene_id}")
            z = f[event_ref]
            sample = int(round(scalar(z, "sample_index")))
            if sample != int(raw_index) + 1:
                raise ValueError(f"trace sample index mismatch: {scene_id} {ordinal}")
            feature_logged = vec(z, "feature_raw")
            normalized = (feature_logged - model["input_mean"]) / model["input_std"]
            contexts.append({"raw_index": int(raw_index), "ordinal": ordinal, "history": history.copy(),
                             "trace_ref": event_ref, "time_s": scalar(z, "time_s"), "beta": scalar(z, "beta")})
            history = np.column_stack((history[:, 1:], normalized))

        mature = [c for c in contexts if c["beta"] >= 1.0 - 1e-12]
        if len(mature) < SAMPLE_COUNT:
            raise ValueError(f"not enough mature events for fixed sample: {scene_id}")
        positions = np.rint(np.linspace(0, len(mature) - 1, SAMPLE_COUNT)).astype(int)
        if len(np.unique(positions)) != SAMPLE_COUNT:
            raise ValueError(f"uniform selection produced duplicate events: {scene_id}")
        selected = [mature[i] for i in positions]
        for selection_rank, context in enumerate(selected):
            raw_i = context["raw_index"]
            event_ref = context["trace_ref"]
            z = f[event_ref]
            head = z["causal_head"]
            sample = raw_i + 1
            x = state[raw_i]
            eta, omega = x[6:9].copy(), x[9:12].copy()
            actual_ref = ref[raw_i].copy()
            actual_rate = ref_rate[raw_i].copy()
            actual_accel = ref_accel[raw_i].copy()
            arm = arms[raw_i].copy()
            eta_error = wrap(actual_ref - eta)
            tau, surface = bs_nominal(eta, omega, actual_ref, actual_rate, actual_accel,
                                      constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
            feature = np.r_[eta_error, omega, tau, arm]
            history_before = context["history"]
            window = np.column_stack((history_before, (feature - model["input_mean"]) / model["input_std"]))
            base, _, phi = forward(window, model)
            W_before = np.asarray(matlab_array(head["weight_before"]), dtype=np.float64)
            raw_total = base + model["target_rms"] * (W_before.T @ phi)
            clipped_total = np.minimum(np.maximum(raw_total, -constants["dmax"]), constants["dmax"])
            estimate = constants["J0"] @ (context["beta"] * clipped_total)
            net_tau = tau - estimate
            logged_feature = vec(z, "feature_raw")
            logged_nominal = np.asarray(matlab_array(log["attitude_bs_nominal_torque_Nm"][:, raw_i]), dtype=np.float64).reshape(-1)
            logged_comp = np.asarray(matlab_array(log["attitude_compensation_applied_torque_Nm"][:, raw_i]), dtype=np.float64).reshape(-1)
            logged_requested = np.asarray(matlab_array(log["requested_generalized"][:, raw_i]), dtype=np.float64).reshape(-1)[1:4]
            raw_base = vec(head, "base_residual_rad_s2")
            raw_phi = vec(head, "phi")
            raw_total_logged = vec(z, "raw_residual_rad_s2")
            raw_clipped_logged = vec(z, "clipped_residual_rad_s2")
            logged_estimate = vec(z, "estimateTorque_Nm")
            # Each point stores parity deltas only; no network or head state is updated.
            checks = {
                "nominal_tau_vs_raw_log": float(np.max(np.abs(tau - logged_nominal))),
                "nominal_tau_vs_feature": float(np.max(np.abs(tau - logged_feature[6:9]))),
                "feature_reconstruction": float(np.max(np.abs(feature - logged_feature))),
                "tracking_surface": float(np.max(np.abs(surface - vec(head, "tracking_surface")))),
                "base_residual": float(np.max(np.abs(base - raw_base))),
                "phi": float(np.max(np.abs(phi - raw_phi))),
                "composite_raw_residual": float(np.max(np.abs(raw_total - raw_total_logged))),
                "composite_clipped_residual": float(np.max(np.abs(clipped_total - raw_clipped_logged))),
                "estimate_torque_vs_trace": float(np.max(np.abs(estimate - logged_estimate))),
                "estimate_torque_vs_raw_log": float(np.max(np.abs(estimate - logged_comp))),
                "net_torque_vs_requested": float(np.max(np.abs(net_tau - logged_requested))),
                "net_torque_vs_log_sum": float(np.max(np.abs(net_tau - (logged_nominal - logged_comp)))),
            }
            events.append({
                "scene_id": scene_id, "family": "W15" if "_W15" in scene_id else "HF",
                "selection_rank": selection_rank, "event_ordinal": context["ordinal"] + 1,
                "sample_index": sample, "time_s": context["time_s"], "beta": context["beta"],
                "time_band": "first5" if context["time_s"] < 5.0 else ("last5" if context["time_s"] >= 15.0 else "middle"),
                "eta": eta, "omega": omega, "ref": actual_ref, "ref_rate": actual_rate,
                "ref_accel": actual_accel, "arm": arm, "history": history_before,
                "W_before": W_before, "phi": phi, "base": base, "tau_bs": tau,
                "raw_total": raw_total, "clipped_total": clipped_total, "estimate": estimate,
                "net_tau": net_tau, "checks": checks,
            })
    return events, {"scene_id": scene_id, "raw_sha256": raw_sha, "audit_sha256": sha256(audit_path),
                    "event_count": len(event_indices), "mature_event_count": len(mature),
                    "selected_event_count": len(events), "selection": "rounded linspace positions 0..N-1 over mature events"}


def local_outputs(event: dict, omega: np.ndarray, model: dict, constants: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    tau_bs, _ = bs_nominal(event["eta"], omega, event["ref"], event["ref_rate"], event["ref_accel"],
                           constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
    feature = np.r_[wrap(event["ref"] - event["eta"]), omega, tau_bs, event["arm"]]
    xnorm = (feature - model["input_mean"]) / model["input_std"]
    window = np.column_stack((event["history"], xnorm))
    base, _, phi = forward(window, model)
    total = base + model["target_rms"] * (event["W_before"].T @ phi)
    clipped_base = np.minimum(np.maximum(base, -constants["dmax"]), constants["dmax"])
    clipped_total = np.minimum(np.maximum(total, -constants["dmax"]), constants["dmax"])
    tau_frozen = tau_bs - constants["J0"] @ (event["beta"] * clipped_base)
    tau_composite = tau_bs - constants["J0"] @ (event["beta"] * clipped_total)
    return tau_bs, tau_frozen, tau_composite, {
        "frozen_saturated": bool(np.any(np.abs(base) >= constants["dmax"] - 1e-12)),
        "composite_saturated": bool(np.any(np.abs(total) >= constants["dmax"] - 1e-12)),
        "composite_raw_residual": total,
    }


def jacobians(event: dict, model: dict, constants: dict) -> tuple[dict, dict]:
    output = {}
    for eps in EPSILONS:
        matrices = {mode: np.zeros((3, 3), dtype=np.float64) for mode in ("bs", "frozen", "composite")}
        for col in range(3):
            delta = np.zeros(3)
            delta[col] = eps
            plus = local_outputs(event, event["omega"] + delta, model, constants)[:3]
            minus = local_outputs(event, event["omega"] - delta, model, constants)[:3]
            for mode, j in zip(("bs", "frozen", "composite"), range(3)):
                matrices[mode][:, col] = (plus[j] - minus[j]) / (2.0 * eps)
        output[eps] = matrices
    primary = output[EPSILONS[0]]
    check = output[EPSILONS[1]]
    return primary, {mode: float(np.max(np.abs(primary[mode] - check[mode]))) for mode in primary}


def damping_metrics(J: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sym_neg = -0.5 * (J + J.T)
    return sym_neg, np.linalg.eigvalsh(sym_neg)


def csv_write(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parity_phase(events: list[dict], scene_reports: list[dict], sources: dict, constants: dict) -> dict:
    all_checks = defaultdict(lambda: {"max_abs": -1.0, "scene_id": None, "sample_index": None})
    scene_checks = []
    for report in scene_reports:
        sample_events = [e for e in events if e["scene_id"] == report["scene_id"]]
        for event in sample_events:
            for key, value in event["checks"].items():
                if value > all_checks[key]["max_abs"]:
                    all_checks[key] = {"max_abs": value, "scene_id": event["scene_id"], "sample_index": event["sample_index"]}
        local = {}
        for key in sample_events[0]["checks"]:
            vals = [e["checks"][key] for e in sample_events]
            j = int(np.argmax(vals))
            local[key] = {"max_abs": vals[j], "sample_index": sample_events[j]["sample_index"]}
        scene_checks.append({**report, "max_abs_parity_errors": local})
    max_error = max(x["max_abs"] for x in all_checks.values())
    tolerance = 1e-8
    return {
        "schema": "DL1018_LOCAL_FEEDBACK_PARITY_V1",
        "status": "PASS_ORIGINAL_POINT_PARITY" if max_error <= tolerance else "FAIL_ORIGINAL_POINT_PARITY",
        "parity_tolerance": tolerance,
        "max_abs_error": max_error,
        "checks": dict(all_checks),
        "scene_reports": scene_checks,
        "sample_count_per_scene": SAMPLE_COUNT,
        "K1": constants["K1"].tolist(), "K2": constants["K2"].tolist(),
        "J0_fixed": constants["J0"].tolist(), "Jdot0_fixed": constants["Jdot0"].tolist(),
        "fixed_source_hashes": sources,
        "Plant_started": False, "MATLAB_started": False, "training_started": False, "TEST_read": False,
    }


def full_statistics(events: list[dict], model: dict, constants: dict) -> tuple[list[dict], list[dict], list[dict]]:
    rows = []
    grouped = defaultdict(list)
    for event in events:
        Js, fd_diff = jacobians(event, model, constants)
        ds, eigs = {}, {}
        for mode in ("bs", "frozen", "composite"):
            ds[mode], eigs[mode] = damping_metrics(Js[mode])
        base_norm = np.linalg.norm(Js["bs"], ord="fro")
        rel_frozen = float(np.linalg.norm(Js["frozen"] - Js["bs"], ord="fro") / base_norm)
        rel_composite = float(np.linalg.norm(Js["composite"] - Js["bs"], ord="fro") / base_norm)
        _, _, _, at_point = local_outputs(event, event["omega"], model, constants)
        analytic_bs = bs_analytic_jacobian(event["eta"], event["omega"], constants["K1"],
                                           constants["K2"], constants["J0"], constants["Jdot0"])
        row = {
            k: event[k] for k in ("scene_id", "family", "selection_rank", "event_ordinal", "sample_index", "time_s", "beta", "time_band")
        }
        row.update({
            "lambda_min_bs": float(eigs["bs"][0]), "lambda_min_frozen": float(eigs["frozen"][0]),
            "lambda_min_composite": float(eigs["composite"][0]),
            "nn_increment_fro_over_bs_frozen": rel_frozen,
            "nn_increment_fro_over_bs_composite": rel_composite,
            "fd_epsilon_absdiff_max_bs": fd_diff["bs"],
            "fd_epsilon_absdiff_max_frozen": fd_diff["frozen"],
            "fd_epsilon_absdiff_max_composite": fd_diff["composite"],
            "analytic_bs_vs_fd_absdiff_max": float(np.max(np.abs(analytic_bs - Js["bs"]))),
            "frozen_output_saturated": at_point["frozen_saturated"],
            "composite_output_saturated": at_point["composite_saturated"],
        })
        for mode in ("bs", "frozen", "composite"):
            for i in range(3):
                for j in range(3):
                    row[f"J_{mode}_{i}{j}"] = float(Js[mode][i, j])
                    row[f"SymNeg_{mode}_{i}{j}"] = float(ds[mode][i, j])
            for i, axis in enumerate(AXES):
                row[f"SymNeg_{mode}_{axis}_diagonal"] = float(ds[mode][i, i])
        for col, axis in enumerate(AXES):
            den = np.linalg.norm(Js["bs"][:, col])
            row[f"nn_increment_column_ratio_frozen_{axis}"] = float(np.linalg.norm((Js["frozen"] - Js["bs"])[:, col]) / den) if den else None
            row[f"nn_increment_column_ratio_composite_{axis}"] = float(np.linalg.norm((Js["composite"] - Js["bs"])[:, col]) / den) if den else None
            row[f"composite_damping_delta_{axis}"] = float(ds["composite"][col, col] - ds["bs"][col, col])
        rows.append(row)
        grouped[(event["family"], event["time_band"])].append(row)

    def quantile(values, q):
        a = np.asarray(values, dtype=np.float64)
        return float(np.quantile(a, q)) if len(a) else None

    summary = []
    for (family, band), group in sorted(grouped.items()):
        spec = {
            "family": family, "time_band": band, "axis": "min_eigenvalue",
            "selected_events": len(group),
        }
        for mode in ("bs", "frozen", "composite"):
            vals = [r[f"lambda_min_{mode}"] for r in group]
            spec[f"lambda_min_{mode}_min"] = min(vals)
            spec[f"lambda_min_{mode}_p05"] = quantile(vals, .05)
            spec[f"lambda_min_{mode}_median"] = quantile(vals, .5)
            spec[f"lambda_min_{mode}_p95"] = quantile(vals, .95)
            spec[f"lambda_min_{mode}_negative_percent"] = 100.0 * sum(v < 0 for v in vals) / len(vals)
        for mode in ("frozen", "composite"):
            key = f"nn_increment_fro_over_bs_{mode}"
            vals = [r[key] for r in group]
            spec[f"{key}_median"] = quantile(vals, .5)
            spec[f"{key}_p95"] = quantile(vals, .95)
        for mode in ("bs", "frozen", "composite"):
            vals = [r[f"fd_epsilon_absdiff_max_{mode}"] for r in group]
            spec[f"fd_epsilon_absdiff_max_{mode}_p95"] = quantile(vals, .95)
        spec["frozen_saturated_events"] = sum(bool(r["frozen_output_saturated"]) for r in group)
        spec["composite_saturated_events"] = sum(bool(r["composite_output_saturated"]) for r in group)
        summary.append(spec)
        for axis in AXES:
            axis_row = {"family": family, "time_band": band, "axis": axis, "selected_events": len(group)}
            for mode in ("bs", "frozen", "composite"):
                vals = [r[f"SymNeg_{mode}_{axis}_diagonal"] for r in group]
                axis_row[f"SymNeg_{mode}_diagonal_median"] = quantile(vals, .5)
                axis_row[f"SymNeg_{mode}_diagonal_p05"] = quantile(vals, .05)
                axis_row[f"SymNeg_{mode}_diagonal_p95"] = quantile(vals, .95)
            for mode in ("frozen", "composite"):
                vals = [r[f"nn_increment_column_ratio_{mode}_{axis}"] for r in group]
                axis_row[f"nn_increment_column_ratio_{mode}_median"] = quantile(vals, .5)
                axis_row[f"nn_increment_column_ratio_{mode}_p95"] = quantile(vals, .95)
            vals = [r[f"composite_damping_delta_{axis}"] for r in group]
            axis_row["composite_minus_bs_damping_median"] = quantile(vals, .5)
            axis_row["composite_minus_bs_damping_p05"] = quantile(vals, .05)
            axis_row["composite_minus_bs_damping_p95"] = quantile(vals, .95)
            summary.append(axis_row)

    outliers = []
    for row in rows:
        negative = [mode for mode in ("bs", "frozen", "composite") if row[f"lambda_min_{mode}"] < 0]
        if negative:
            outliers.append({"outlier_kind": "negative_local_damping_eigenvalue", **row,
                             "negative_modes": ",".join(negative)})
    for family, band in sorted(grouped):
        subset = [r for r in rows if r["family"] == family and r["time_band"] == band]
        for kind, ordered in (("largest_composite_increment_ratio", sorted(subset, key=lambda r: r["nn_increment_fro_over_bs_composite"], reverse=True)[:5]),
                              ("smallest_composite_increment_ratio", sorted(subset, key=lambda r: r["nn_increment_fro_over_bs_composite"])[:5])):
            for row in ordered:
                outliers.append({"outlier_kind": kind, **row})
    return rows, summary, outliers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("parity", "full"), default="parity")
    parser.add_argument("--scene", choices=("all", *SCENES), default="all")
    args = parser.parse_args()
    if args.phase == "full" and args.scene != "all":
        parser.error("full statistics always use all six scenes")
    lock, constants, model, sources = load_constants_and_model()
    all_events, scene_reports = [], []
    selected_scenes = SCENES if args.scene == "all" else [args.scene]
    for scene in selected_scenes:
        print(f"load/parity: {scene}", flush=True)
        events, report = get_scene_data(scene, model, constants)
        all_events.extend(events)
        scene_reports.append(report)
    parity = parity_phase(all_events, scene_reports, sources, constants)
    parity_suffix = "all" if args.scene == "all" else args.scene
    parity_path = ROOT / f"local_feedback_parity_{parity_suffix}_v1.json"
    parity_path.write_text(json.dumps(parity, indent=2), encoding="utf-8")
    print(json.dumps({"parity_status": parity["status"], "max_abs_error": parity["max_abs_error"],
                      "checks": parity["checks"]}, indent=2), flush=True)
    if parity["status"] != "PASS_ORIGINAL_POINT_PARITY":
        return 2
    if args.phase == "parity":
        return 0
    rows, summary, outliers = full_statistics(all_events, model, constants)
    csv_write(ROOT / "local_feedback_event_jacobians_v1.csv", rows)
    csv_write(ROOT / "local_feedback_summary_v1.csv", summary)
    csv_write(ROOT / "local_feedback_outliers_v1.csv", outliers)
    result = {
        "schema": "DL1018_LOCAL_FEEDBACK_DIAGNOSIS_RESULT_V1",
        "status": "COMPLETED_LOCAL_JACOBIAN_DIAGNOSTIC",
        "parity_report_sha256": sha256(parity_path),
        "parity_status": parity["status"],
        "max_abs_original_point_parity_error": parity["max_abs_error"],
        "scene_reports": scene_reports,
        "sample_count_per_scene": SAMPLE_COUNT,
        "total_selected_events": len(all_events),
        "epsilon_primary": EPSILONS[0], "epsilon_numeric_check": EPSILONS[1],
        "local_damping_definition": "Sym(-d tau_net / d omega) = -(J+J.T)/2; negative eigenvalues indicate a locally antidamping direction only under frozen-memory assumptions.",
        "nn_increment_definition": "Frobenius/column norm of J_variant - J_BS divided by corresponding J_BS norm; output clipping included.",
        "selection_rule": "Exactly 200 rounded-linspace-position mature events per scene, with no outcome-based selection.",
        "limitations": "Local frozen-state/reference/history/weight sensitivity only; not a stability proof or Plant/closed-loop counterfactual.",
        "report_path": str(ROOT / "REPORT_v1.md"),
        "execution_command": "$env:MKL_THREADING_LAYER='SEQUENTIAL'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; & python -u 'experiments\\dl_attitude_replacement_20261026\\attitude_local_feedback_diagnosis_20261027_v1\\local_feedback_sensitivity.py' --phase full",
        "Plant_started": False, "MATLAB_started": False, "training_started": False, "TEST_read": False,
    }
    result_path = ROOT / "RESULT_v1.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    provenance = {
        "schema": "DL1018_LOCAL_FEEDBACK_DIAGNOSIS_PROVENANCE_V1",
        **sources,
        "fixed_constants": {k: v.tolist() for k, v in constants.items()},
        "script_path": str(Path(__file__).resolve()), "script_sha256": sha256(Path(__file__)),
        "source_v3_release_sha256": sha256(V3 / "RELEASE.json"),
        "source_lock_sha256": sha256(V3 / "SOURCE_LOCK_v3.json"),
        "parity_report_path": str(parity_path), "parity_report_sha256": sha256(parity_path),
        "jacobian_csv_sha256": sha256(ROOT / "local_feedback_event_jacobians_v1.csv"),
        "summary_csv_sha256": sha256(ROOT / "local_feedback_summary_v1.csv"),
        "outliers_csv_sha256": sha256(ROOT / "local_feedback_outliers_v1.csv"),
        "result_sha256": sha256(result_path),
        "report_path": str(ROOT / "REPORT_v1.md"),
        "report_sha256": sha256(ROOT / "REPORT_v1.md"),
        "Plant_started": False, "MATLAB_started": False, "training_started": False, "TEST_read": False,
        "variable_inertia_read_or_reconstructed": False,
    }
    (ROOT / "PROVENANCE_v1.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    status = {
        "schema": "DL1018_LOCAL_FEEDBACK_DIAGNOSIS_STATUS_V1",
        "status": "COMPLETE_PARITY_AND_JACOBIAN_DIAGNOSTIC",
        "Plant_calls": 0, "training_jobs": 0, "TEST_read": False, "MATLAB_started": False,
        "source_v3_modified": False, "fixed_snapshot_read": True,
        "result": "RESULT_v1.json", "report": "REPORT_v1.md",
        "outputs": ["local_feedback_parity_all_v1.json", "local_feedback_event_jacobians_v1.csv",
                    "local_feedback_summary_v1.csv", "local_feedback_outliers_v1.csv", "PROVENANCE_v1.json"],
    }
    (ROOT / "STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
