from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parent
C5_ROOT = ROOT.parents[1] / "position_axis_coordinate_c5_20261023"
V3 = ROOT.parents[0] / "mlp15_composite_dev_v3"
MANIFEST = ROOT.parents[0] / "mlp15_c5_teacher_redistill_v1" / "DATASET_MANIFEST_v1.json"
SCENES = [
    "DL1018_VAL_T1_C05_W12",
    "DL1018_VAL_T1_C08_W15",
    "DL1018_VAL_T2_C02_W12",
    "DL1018_VAL_T2_C05_W15",
    "DL1018_VAL_T3_C00_W13",
    "DL1018_VAL_T3_C02_W15",
]


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


def import_local_feedback_helpers():
    helper_path = ROOT.parent / "attitude_local_feedback_diagnosis_20261027_v1" / "local_feedback_sensitivity.py"
    spec = importlib.util.spec_from_file_location("local_feedback_sensitivity", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to import the verified common BS/MLP helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lock, constants, model, sources = module.load_constants_and_model()
    return helper_path, module, lock, constants, model, sources


def load_rbf_config(run_start_path: Path, constants: dict) -> tuple[dict, dict]:
    with h5py.File(run_start_path, "r") as f:
        g = f["runStart/cfg/rbf/attitude"]
        bsg = f["runStart/cfg/control/bs/attitude"]
        k1 = np.asarray(bsg["k1"], dtype=np.float64).reshape(-1)
        k2 = np.asarray(bsg["k2"], dtype=np.float64).reshape(-1)
        if not np.array_equal(k1, constants["K1"]) or not np.array_equal(k2, constants["K2"]):
            raise ValueError("C5 run_start BS gains differ from fixed shared K1/K2 reference")
        opts = f["runStart/opts"]
        if "rbf_attitude_initial_weight" in opts:
            raise ValueError("C5 run_start contains a nonzero RBF initial-weight override; audit required")
        forbidden = {"width_scale", "basis_override", "basis_gamma_scale"} & set(g.keys())
        if forbidden:
            raise ValueError(f"unsupported RBF basis override fields present: {sorted(forbidden)}")
        cfg = {
            "centers": np.asarray(g["centers"], dtype=np.float64).T,
            "input_scale": np.asarray(g["input_scale"], dtype=np.float64).reshape(-1),
            "sigma": scalar(g, "sigma"), "gamma": np.asarray(g["gamma"], dtype=np.float64).reshape(-1),
            "sigma_w": np.asarray(g["sigma_w"], dtype=np.float64).reshape(-1),
            "s_limit": np.asarray(g["s_limit"], dtype=np.float64).reshape(-1),
            "dmax": np.asarray(g["dmax"], dtype=np.float64).reshape(-1),
            "wmax": scalar(g, "wmax"), "beta_rise_time": scalar(g, "beta_rise_time"),
            "rbf_input_dim": int(round(scalar(g, "rbf_input_dim"))),
            "linear_dim": int(round(scalar(g, "linear_dim"))),
        }
        config_audit = {
            "centers_shape_matlab": [cfg["centers"].shape[0], cfg["centers"].shape[1]],
            "input_scale": cfg["input_scale"].tolist(), "sigma": cfg["sigma"],
            "gamma": cfg["gamma"].tolist(), "sigma_w": cfg["sigma_w"].tolist(),
            "s_limit": cfg["s_limit"].tolist(), "dmax": cfg["dmax"].tolist(),
            "wmax": cfg["wmax"], "beta_rise_time": cfg["beta_rise_time"],
            "rbf_input_dim": cfg["rbf_input_dim"], "linear_dim": cfg["linear_dim"],
            "initial_weight_override_absent": True,
            "width_scale_basis_override_basis_gamma_scale_absent": True,
        }
    if cfg["centers"].shape != (6, 81) or cfg["rbf_input_dim"] != 6 or cfg["linear_dim"] != 0:
        raise ValueError(f"unexpected C5 attitude RBF shape/config: {cfg['centers'].shape}")
    return cfg, config_audit


def rbf_basis(z: np.ndarray, cfg: dict) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64).reshape(-1)
    if z.size < cfg["rbf_input_dim"]:
        raise ValueError("RBF input shorter than locked dimension")
    z_scaled = z[:cfg["rbf_input_dim"]] / np.maximum(cfg["input_scale"][:cfg["rbf_input_dim"]], np.finfo(float).eps)
    diff = cfg["centers"] - z_scaled[:, None]
    dist_sq = np.sum(diff * diff, axis=0)
    return np.exp(-dist_sq / (2.0 * cfg["sigma"] ** 2))


def rbf_update(z: np.ndarray, surface: np.ndarray, W: np.ndarray, cfg: dict,
               gamma_scale: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    phi = rbf_basis(z, cfg)
    output_unclipped = W.T @ phi
    output = np.minimum(np.maximum(output_unclipped, -cfg["dmax"]), cfg["dmax"])
    surface_effective = np.minimum(np.maximum(surface, -cfg["s_limit"]), cfg["s_limit"])
    gamma = cfg["gamma"] * gamma_scale
    W_dot = -np.outer(phi, gamma * surface_effective) - W * cfg["sigma_w"][None, :]
    W_after = np.minimum(np.maximum(W + W_dot * dt, -cfg["wmax"]), cfg["wmax"])
    return output_unclipped, output, W_dot, W_after


def local_torques(event: dict, omega: np.ndarray, cfg: dict, constants: dict,
                  model: dict, bs_helper) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    tau_bs, surface = bs_helper.bs_nominal(
        event["eta"], omega, event["ref"], event["ref_rate"], event["ref_accel"],
        constants["K1"], constants["K2"], constants["J0"], constants["Jdot0"])
    e = bs_helper.wrap(event["ref"] - event["eta"])
    z_rbf = np.array([e[0], surface[0], e[1], surface[1], e[2], surface[2]])
    phi_rbf = rbf_basis(z_rbf, cfg)
    raw_rbf = event["W_before"].T @ phi_rbf
    clipped_rbf = np.minimum(np.maximum(raw_rbf, -cfg["dmax"]), cfg["dmax"])
    torque_rbf = constants["J0"] @ (event["beta"] * clipped_rbf)
    net_rbf = tau_bs - torque_rbf

    feature = np.r_[e, omega, tau_bs, event["arm"]]
    xnorm = (feature - model["input_mean"]) / model["input_std"]
    window = np.column_stack((event["mlp_history"], xnorm))
    mlp_base, _, _ = bs_helper.forward(window, model)
    clipped_mlp = np.minimum(np.maximum(mlp_base, -constants["dmax"]), constants["dmax"])
    torque_mlp = constants["J0"] @ (event["beta"] * clipped_mlp)
    net_mlp = tau_bs - torque_mlp
    return tau_bs, net_rbf, net_mlp, {
        "RBF_raw": raw_rbf, "RBF_clipped": clipped_rbf, "RBF_phi_norm": float(np.linalg.norm(phi_rbf)),
        "MLP_base": mlp_base, "MLP_clipped": clipped_mlp,
        "RBF_saturated": bool(np.any(np.abs(raw_rbf) > cfg["dmax"])),
        "MLP_saturated": bool(np.any(np.abs(mlp_base) > constants["dmax"])),
    }


EPSILONS = (1e-5, 5e-6)
AXES = ("roll", "pitch", "yaw")


def local_jacobian(event: dict, cfg: dict, constants: dict, model: dict, bs_helper):
    all_j = {}
    for eps in EPSILONS:
        matrices = {mode: np.zeros((3, 3), dtype=np.float64) for mode in ("bs", "rbf", "mlp")}
        for column in range(3):
            delta = np.zeros(3, dtype=np.float64)
            delta[column] = eps
            plus = local_torques(event, event["omega"] + delta, cfg, constants, model, bs_helper)[:3]
            minus = local_torques(event, event["omega"] - delta, cfg, constants, model, bs_helper)[:3]
            for mode, idx in zip(("bs", "rbf", "mlp"), range(3)):
                matrices[mode][:, column] = (plus[idx] - minus[idx]) / (2.0 * eps)
        all_j[eps] = matrices
    primary = all_j[EPSILONS[0]]
    check = all_j[EPSILONS[1]]
    errors = {mode: float(np.max(np.abs(primary[mode] - check[mode]))) for mode in primary}
    return primary, errors


def damping(J: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sym_neg = -0.5 * (J + J.T)
    return sym_neg, np.linalg.eigvalsh(sym_neg)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def local_jacobian_rows(events_by_scene: dict, configs_by_scene: dict, constants: dict,
                        model: dict, bs_helper) -> tuple[list[dict], list[dict], list[dict]]:
    rows = []
    for scene_id, events in events_by_scene.items():
        cfg = configs_by_scene[scene_id]
        for event in events:
            Js, fd_error = local_jacobian(event, cfg, constants, model, bs_helper)
            Ds, eigs = {}, {}
            for mode in ("bs", "rbf", "mlp"):
                Ds[mode], eigs[mode] = damping(Js[mode])
            base_norm = np.linalg.norm(Js["bs"], ord="fro")
            _, _, _, at_point = local_torques(event, event["omega"], cfg, constants, model, bs_helper)
            row = {key: event[key] for key in (
                "scene_id", "family", "selection_rank", "event_ordinal", "sample_index", "time_s", "time_band", "beta")}
            row.update({
                "lambda_min_bs": float(eigs["bs"][0]), "lambda_min_rbf": float(eigs["rbf"][0]),
                "lambda_min_mlp": float(eigs["mlp"][0]),
                "nn_increment_fro_over_bs_rbf": float(np.linalg.norm(Js["rbf"] - Js["bs"], ord="fro") / base_norm),
                "nn_increment_fro_over_bs_mlp": float(np.linalg.norm(Js["mlp"] - Js["bs"], ord="fro") / base_norm),
                "fd_eps_absdiff_max_bs": fd_error["bs"], "fd_eps_absdiff_max_rbf": fd_error["rbf"],
                "fd_eps_absdiff_max_mlp": fd_error["mlp"],
                "RBF_saturated_at_nominal": at_point["RBF_saturated"],
                "MLP_saturated_at_nominal": at_point["MLP_saturated"],
                "RBF_phi_norm_at_nominal": at_point["RBF_phi_norm"],
            })
            for mode in ("bs", "rbf", "mlp"):
                for i, ax_i in enumerate(AXES):
                    row[f"SymNeg_{mode}_{ax_i}_diagonal"] = float(Ds[mode][i, i])
                    for j in range(3):
                        row[f"J_{mode}_{i}{j}"] = float(Js[mode][i, j])
                        row[f"SymNeg_{mode}_{i}{j}"] = float(Ds[mode][i, j])
            for col, axis in enumerate(AXES):
                den = np.linalg.norm(Js["bs"][:, col])
                for mode in ("rbf", "mlp"):
                    row[f"nn_increment_column_ratio_{mode}_{axis}"] = float(np.linalg.norm((Js[mode] - Js["bs"])[:, col]) / den) if den else None
                    row[f"damping_delta_{mode}_{axis}"] = float(Ds[mode][col, col] - Ds["bs"][col, col])
            rows.append(row)

    def quantile(values, q):
        return float(np.quantile(np.asarray(values, dtype=np.float64), q)) if values else None

    groups = defaultdict(list)
    for row in rows:
        groups[(row["family"], row["time_band"])].append(row)
    summary = []
    for (family, band), group in sorted(groups.items()):
        spec = {"family": family, "time_band": band, "axis": "min_eigenvalue", "selected_events": len(group)}
        for mode in ("bs", "rbf", "mlp"):
            values = [r[f"lambda_min_{mode}"] for r in group]
            spec[f"lambda_min_{mode}_min"] = min(values)
            spec[f"lambda_min_{mode}_p05"] = quantile(values, .05)
            spec[f"lambda_min_{mode}_median"] = quantile(values, .5)
            spec[f"lambda_min_{mode}_p95"] = quantile(values, .95)
            spec[f"lambda_min_{mode}_negative_percent"] = 100.0 * sum(v < 0 for v in values) / len(values)
        for mode in ("rbf", "mlp"):
            for key in (f"nn_increment_fro_over_bs_{mode}", f"fd_eps_absdiff_max_{mode}"):
                values = [r[key] for r in group]
                spec[f"{key}_median"] = quantile(values, .5)
                spec[f"{key}_p95"] = quantile(values, .95)
        spec["frozen_mlp_is_hypothetical_on_C5_state"] = True
        summary.append(spec)
        for axis in AXES:
            axis_row = {"family": family, "time_band": band, "axis": axis, "selected_events": len(group)}
            for mode in ("bs", "rbf", "mlp"):
                vals = [r[f"SymNeg_{mode}_{axis}_diagonal"] for r in group]
                axis_row[f"SymNeg_{mode}_diagonal_median"] = quantile(vals, .5)
                axis_row[f"SymNeg_{mode}_diagonal_p05"] = quantile(vals, .05)
                axis_row[f"SymNeg_{mode}_diagonal_p95"] = quantile(vals, .95)
            for mode in ("rbf", "mlp"):
                vals = [r[f"nn_increment_column_ratio_{mode}_{axis}"] for r in group]
                axis_row[f"nn_increment_column_ratio_{mode}_median"] = quantile(vals, .5)
                axis_row[f"nn_increment_column_ratio_{mode}_p95"] = quantile(vals, .95)
                vals = [r[f"damping_delta_{mode}_{axis}"] for r in group]
                axis_row[f"damping_delta_{mode}_median"] = quantile(vals, .5)
                axis_row[f"damping_delta_{mode}_p05"] = quantile(vals, .05)
                axis_row[f"damping_delta_{mode}_p95"] = quantile(vals, .95)
            summary.append(axis_row)
    outliers = []
    for row in rows:
        negative = [mode for mode in ("bs", "rbf", "mlp") if row[f"lambda_min_{mode}"] < 0]
        if negative:
            outliers.append({"outlier_kind": "negative_local_damping_eigenvalue", **row,
                             "negative_modes": ",".join(negative)})
    return rows, summary, outliers


def run_one_scene(scene_id: str, row: dict, c5_input_lock: dict, constants: dict,
                  model: dict, bs_helper, need_context: bool) -> tuple[dict, list[dict], list[dict], dict]:
    raw_path = Path(row["raw_path"])
    start_path = Path(row["run_start_path"])
    if sha256(raw_path) != row["raw_sha256"] or sha256(start_path) != row["run_start_sha256"]:
        raise ValueError(f"manifest SHA mismatch for {scene_id}")
    if row["status_trace_audit_state"] != "PASS_C5_RAW_ALL_EVENTS" or row["event_count"] != 1999:
        raise ValueError(f"C5 raw inventory did not pass parent audit: {scene_id}")
    cfg, cfg_audit = load_rbf_config(start_path, constants)
    J0, Jdot0 = constants["J0"], constants["Jdot0"]
    maxerr = {}
    worst = {}
    snapshots = []
    event_rows = []
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        state = np.asarray(matlab_array(log["state"]), dtype=np.float64)
        time = vec(log, "time")
        ref = np.asarray(matlab_array(log["filtered_attitude_reference"]), dtype=np.float64)
        ref_rate = np.asarray(matlab_array(log["filtered_attitude_rate"]), dtype=np.float64)
        ref_accel = np.asarray(matlab_array(log["command_filter_acceleration_applied_rads2"]), dtype=np.float64)
        arms = np.asarray(matlab_array(log["arms"]["command"]), dtype=np.float64)
        nominal_log = np.asarray(matlab_array(log["attitude_bs_nominal_torque_Nm"]), dtype=np.float64)
        compensation_log = np.asarray(matlab_array(log["attitude_compensation_applied_torque_Nm"]), dtype=np.float64)
        requested = np.asarray(matlab_array(log["requested_generalized"]), dtype=np.float64)
        update_flag = np.asarray(matlab_array(log["rbf_update_flag"]), dtype=bool).reshape(-1)
        update_dt = np.asarray(matlab_array(log["rbf_update_dt"]), dtype=np.float64).reshape(-1)
        event_dt = np.asarray(matlab_array(log["rbf_event_dt"]), dtype=np.float64).reshape(-1)
        z_log = np.asarray(matlab_array(log["rbf_input_sample"]), dtype=np.float64)
        s_log = np.asarray(matlab_array(log["rbf_attitude_surface_learn"]), dtype=np.float64)
        gamma_scale_log = np.asarray(matlab_array(log["rbf_attitude_gamma_scale"]), dtype=np.float64)
        unclipped_log = np.asarray(matlab_array(log["rbf_output_unclipped"]), dtype=np.float64)
        output_log = np.asarray(matlab_array(log["rbf_output_raw"]), dtype=np.float64)
        held_log = np.asarray(matlab_array(log["rbf_output_held"]), dtype=np.float64)
        basis_norm_log = np.asarray(matlab_array(log["rbf_basis_norm"]), dtype=np.float64).reshape(-1)
        weight_norm_log = np.asarray(matlab_array(log["rbf_weight_norm"]), dtype=np.float64).reshape(-1)
        derivative_norm_log = np.asarray(matlab_array(log["rbf_weight_derivative_norm"]), dtype=np.float64).reshape(-1)
        beta_log = np.asarray(matlab_array(log["attitude_event_beta"]), dtype=np.float64).reshape(-1)
        event_indices = np.flatnonzero(update_flag)
        if len(event_indices) != 1999:
            raise ValueError(f"expected exactly 1999 RBF update events, got {len(event_indices)} in {scene_id}")
        if not (z_log.shape == (20000, 6) and s_log.shape == (20000, 3) and gamma_scale_log.shape == (20000, 3)):
            raise ValueError(f"unexpected logged RBF field shapes in {scene_id}")
        audit = log["rbf_event_audit"]
        audit_count = audit["weight_before"].shape[0]
        if audit_count != 8:
            raise ValueError(f"expected eight stored RBF weight snapshots, got {audit_count}")
        audit_wb = np.asarray(audit["weight_before"], dtype=np.float64).transpose(2, 1, 0)
        audit_wa = np.asarray(audit["weight_after"], dtype=np.float64).transpose(2, 1, 0)
        audit_wd = np.asarray(audit["weight_derivative"], dtype=np.float64).transpose(2, 1, 0)
        audit_wu = np.asarray(audit["weight_unprojected"], dtype=np.float64).transpose(2, 1, 0)
        audit_phi_norm = vec(audit, "phi_norm")
        audit_times = vec(audit, "time")
        audit_dts = vec(audit, "dt")
        audit_inputs = np.asarray(audit["input"], dtype=np.float64)
        audit_outputs = np.asarray(audit["output_raw"], dtype=np.float64)

        W = np.zeros((81, 3), dtype=np.float64)
        mlp_history = np.zeros((13, 14), dtype=np.float64)
        controller_dt = float(time[1] - time[0])
        if controller_dt <= 0 or not np.all(np.isfinite(time[:3])):
            raise ValueError("invalid raw time base")
        beta_by_event = np.minimum((event_indices + 1) * controller_dt / cfg["beta_rise_time"], 1.0)
        mature_positions = np.flatnonzero(beta_by_event >= 1.0 - 1e-12)
        if len(mature_positions) < 200:
            raise ValueError(f"not enough mature RBF events: {scene_id}")
        selected_positions = set(np.rint(np.linspace(0, len(mature_positions) - 1, 200)).astype(int).tolist())
        selected_event_positions = {int(mature_positions[p]): rank for rank, p in enumerate(sorted(selected_positions))}
        point_contexts = []
        for event_index, raw_i in enumerate(event_indices):
            sample = int(raw_i) + 1  # MATLAB sample index used by the source controller.
            eta, omega = state[raw_i, 6:9], state[raw_i, 9:12]
            reference, reference_rate, reference_accel = ref[raw_i], ref_rate[raw_i], ref_accel[raw_i]
            tau_bs, surface = bs_helper.bs_nominal(eta, omega, reference, reference_rate, reference_accel,
                                                   constants["K1"], constants["K2"], J0, Jdot0)
            e = bs_helper.wrap(reference - eta)
            z_rebuilt = np.array([e[0], surface[0], e[1], surface[1], e[2], surface[2]])
            z = z_log[raw_i]
            beta = float(beta_by_event[event_index])
            arm = arms[raw_i].copy()
            mlp_feature = np.r_[e, omega, tau_bs, arm]
            mlp_normalized = (mlp_feature - model["input_mean"]) / model["input_std"]
            learned_surface = s_log[raw_i]
            gamma_scale = gamma_scale_log[raw_i]
            dt = float(update_dt[raw_i])
            if not update_flag[raw_i] or dt <= 0 or not np.all(np.isfinite(np.r_[z, learned_surface, gamma_scale, dt])):
                raise ValueError(f"bad logged RBF update input at {scene_id} sample {sample}")
            out_unclipped, out_clipped, W_dot, W_after = rbf_update(z, learned_surface, W, cfg, gamma_scale, dt)
            estimate_torque = J0 @ (beta * out_clipped)
            net_tau = tau_bs - estimate_torque
            req_tau = requested[raw_i, 1:4]
            comp_tau = compensation_log[raw_i]

            checks = {
                "z_input_from_BS": float(np.max(np.abs(z_rebuilt - z))),
                "output_unclipped": float(np.max(np.abs(out_unclipped - unclipped_log[raw_i]))),
                "output_clipped": float(np.max(np.abs(out_clipped - output_log[raw_i]))),
                "phi_norm": abs(float(np.linalg.norm(rbf_basis(z, cfg))) - float(basis_norm_log[raw_i])),
                "weight_norm_after": abs(float(np.linalg.norm(W_after, ord="fro")) - float(weight_norm_log[raw_i])),
                "weight_derivative_norm": abs(float(np.linalg.norm(W_dot, ord="fro")) - float(derivative_norm_log[raw_i])),
                "nominal_tau_vs_raw": float(np.max(np.abs(tau_bs - nominal_log[raw_i]))),
                "estimate_torque_vs_raw": float(np.max(np.abs(estimate_torque - comp_tau))),
                "estimate_torque_vs_held": float(np.max(np.abs(estimate_torque - held_log[raw_i]))),
                "net_tau_vs_requested": float(np.max(np.abs(net_tau - req_tau))),
            }
            for key, value in checks.items():
                if value > maxerr.get(key, -1.0):
                    maxerr[key] = value
                    worst[key] = {"sample_index": sample, "event_ordinal": event_index + 1}

            if event_index < audit_count:
                audit_checks = {
                    "audit_time": abs(float(time[raw_i]) - float(audit_times[event_index])),
                    "audit_update_dt": abs(dt - float(audit_dts[event_index])),
                    "audit_input": float(np.max(np.abs(z - audit_inputs[event_index]))),
                    "audit_output": float(np.max(np.abs(out_clipped - audit_outputs[event_index]))),
                    "audit_phi_norm": abs(float(np.linalg.norm(rbf_basis(z, cfg))) - float(audit_phi_norm[event_index])),
                    "audit_W_before": float(np.max(np.abs(W - audit_wb[:, :, event_index]))),
                    "audit_W_dot": float(np.max(np.abs(W_dot - audit_wd[:, :, event_index]))),
                    "audit_W_unprojected": float(np.max(np.abs(W + W_dot * dt - audit_wu[:, :, event_index]))),
                    "audit_W_after": float(np.max(np.abs(W_after - audit_wa[:, :, event_index]))),
                }
                for key, value in audit_checks.items():
                    if value > maxerr.get(key, -1.0):
                        maxerr[key] = value
                        worst[key] = {"sample_index": sample, "event_ordinal": event_index + 1}
                snapshots.append({"event_ordinal": event_index + 1, "sample_index": sample,
                                  "time_s": float(time[raw_i]), "audit_status": "PASS" if max(audit_checks.values()) <= 1e-9 else "FAIL",
                                  "max_abs_error": max(audit_checks.values())})

            event_rows.append({
                "scene_id": scene_id, "event_ordinal": event_index + 1, "sample_index": sample,
                "time_s": float(time[raw_i]), "beta": beta, "RBF_output_saturated": bool(np.any(np.abs(out_unclipped) > cfg["dmax"])),
                **{f"error_{key}": float(value) for key, value in checks.items()},
                "phi_norm": float(np.linalg.norm(rbf_basis(z, cfg))),
                "weight_norm_before": float(np.linalg.norm(W, ord="fro")),
                "weight_norm_after": float(np.linalg.norm(W_after, ord="fro")),
                "weight_derivative_norm": float(np.linalg.norm(W_dot, ord="fro")),
            })
            if need_context and event_index in selected_event_positions:
                point_contexts.append({
                    "scene_id": scene_id, "family": "W15" if "_W15" in scene_id else "HF",
                    "selection_rank": selected_event_positions[event_index],
                    "event_ordinal": event_index + 1, "sample_index": sample,
                    "time_s": float(time[raw_i]), "time_band": "first5" if time[raw_i] < 5.0 else ("last5" if time[raw_i] >= 15.0 else "middle"),
                    "beta": beta, "eta": eta.copy(), "omega": omega.copy(),
                    "ref": reference.copy(), "ref_rate": reference_rate.copy(),
                    "ref_accel": reference_accel.copy(), "e": e.copy(), "surface": surface.copy(),
                    "arm": arm.copy(), "mlp_history": mlp_history.copy(),
                    "W_before": W.copy(), "RBF_z": z.copy(),
                    "RBF_output_unclipped": out_unclipped.copy(), "RBF_output_clipped": out_clipped.copy(),
                    "RBF_basis_norm": float(np.linalg.norm(rbf_basis(z, cfg))),
                    "MLP_feature": mlp_feature.copy(),
                })
            mlp_history = np.column_stack((mlp_history[:, 1:], mlp_normalized))
            W = W_after

        threshold = 1e-8
        parity_ok = all(value <= threshold for value in maxerr.values())
        report = {
            "scene_id": scene_id, "raw_path": str(raw_path), "raw_sha256": sha256(raw_path),
            "run_start_path": str(start_path), "run_start_sha256": sha256(start_path),
            "event_count": len(event_indices), "stored_W_snapshot_count": audit_count,
            "mature_event_count": int(sum(min((int(i) + 1) * controller_dt / cfg["beta_rise_time"], 1.0) >= 1.0 for i in event_indices)),
            "rbf_config": cfg_audit, "RBF_initial_weight_zero": True,
            "status": "PASS_RBF_FULL_EVENT_REPLAY" if parity_ok else "FAIL_RBF_FULL_EVENT_REPLAY",
            "parity_tolerance": threshold, "max_abs_errors": maxerr, "worst_event_by_check": worst,
            "first_eight_snapshot_checks": snapshots,
        }
    return report, event_rows, point_contexts, cfg


def validate_source_locks(c5_input_lock_path: Path, c5_input_lock: dict) -> tuple[dict, dict]:
    v3_lock_path = V3 / "SOURCE_LOCK_v3.json"
    v3_lock = json.loads(v3_lock_path.read_text(encoding="utf-8-sig"))
    v3_root = Path(v3_lock["root"])
    inventory = c5_input_lock["active_source_inventory"]
    locked = {}
    entries = {}
    for role, c5_role, relative in (("rbf_basis", "rbf_mimo_basis", "matlab/core/rbf_mimo_basis.m"),
                                    ("rbf_update", "rbf_mimo_update", "matlab/core/rbf_mimo_update.m")):
        v3_matches = [entry for entry in v3_lock["files"]
                      if entry["relative_path"].replace("\\", "/") == relative]
        c5_matches = [entry for entry in inventory if entry["role"] == c5_role]
        if len(v3_matches) != 1 or len(c5_matches) != 1:
            raise ValueError(f"source lock missing/duplicates {role}")
        expected = v3_matches[0]["sha256"]
        if c5_matches[0]["sha256"] != expected:
            raise ValueError(f"C5 and v3 source locks disagree for {role}")
        canonical = ROOT.parents[2] / Path(relative)
        v3_copy = v3_root / Path(relative)
        for path in (canonical, v3_copy):
            actual = sha256(path)
            if actual != expected:
                raise ValueError(f"source-lock SHA changed for {role}: {path}")
        locked[role] = (canonical, expected)
        entries[role] = {"sha256": expected, "canonical_path": str(canonical),
                         "v3_copy_path": str(v3_copy)}
    runner = [entry for entry in inventory if entry["role"] == "runtime_core"
              and Path(entry["path"]).name == "run_dl1018_closed_loop.m"]
    if len(runner) != 1:
        raise ValueError("C5 input lock missing/duplicates the runtime_core runner")
    runner_path, runner_sha = Path(runner[0]["path"]), runner[0]["sha256"]
    if sha256(runner_path) != runner_sha:
        raise ValueError("C5 input-lock SHA changed for runtime_core runner")
    locked["C5_runner"] = (runner_path, runner_sha)
    entries["C5_runner"] = {"sha256": runner_sha, "path": str(runner_path)}
    provenance = {
        "C5_input_lock_path": str(c5_input_lock_path),
        "C5_input_lock_sha256": sha256(c5_input_lock_path),
        "V3_source_lock_path": str(v3_lock_path),
        "V3_source_lock_sha256": sha256(v3_lock_path),
        "V3_source_lock_file_count": len(v3_lock["files"]),
        "verified_sources": entries,
    }
    return locked, provenance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("parity", "full"), default="full")
    parser.add_argument("--scene", choices=("all", *SCENES), default="all")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    c5_input_lock_path = C5_ROOT / "C5_AXIS_COORDINATE_INPUT_LOCK_v1.json"
    c5_input_lock = json.loads(c5_input_lock_path.read_text(encoding="utf-8-sig"))
    helper_path, bs_helper, mlp_lock, constants, model, helper_sources = import_local_feedback_helpers()
    locked_sources, lock_provenance = validate_source_locks(c5_input_lock_path, c5_input_lock)
    by_scene = {row["scene_id"]: row for row in manifest["rows"]}
    selected_scenes = SCENES if args.scene == "all" else [args.scene]
    results, all_event_rows, contexts_by_scene, configs_by_scene = [], [], {}, {}
    for scene in selected_scenes:
        print(f"replay start: {scene}", flush=True)
        if scene not in by_scene:
            raise ValueError(f"scene missing from locked C5 dataset manifest: {scene}")
        report, rows, contexts, cfg = run_one_scene(
            scene, by_scene[scene], c5_input_lock, constants, model, bs_helper,
            need_context=(args.phase == "full"))
        results.append(report)
        all_event_rows.extend(rows)
        contexts_by_scene[scene], configs_by_scene[scene] = contexts, cfg
        print(f"replay done: {scene}, {report['status']}, max_abs={max(report['max_abs_errors'].values()):.3g}", flush=True)

    parity = {
        "schema": "DL1018_C5_RBF_REFERENCE_REPLAY_PARITY_V1",
        "status": "PASS_RBF_FULL_EVENT_REPLAY" if all(r["status"] == "PASS_RBF_FULL_EVENT_REPLAY" for r in results) else "FAIL_RBF_FULL_EVENT_REPLAY",
        "scene_reports": results,
        "RBF_input_order": "[error_roll,surface_roll,error_pitch,surface_pitch,error_yaw,surface_yaw]",
        "output_update_order": "current output uses W_before; then exact logged dt update produces W_after for next event",
        "fixed_J0_K1_K2": {"J0": constants["J0"].tolist(), "Jdot0": constants["Jdot0"].tolist(),
                           "K1": constants["K1"].tolist(), "K2": constants["K2"].tolist()},
        "source_hashes": {
            "dataset_manifest_path": str(MANIFEST), "dataset_manifest_sha256": sha256(MANIFEST),
            **lock_provenance,
            **{f"{role}_path": str(path) for role, (path, _) in locked_sources.items()},
            **{f"{role}_sha256": sha256(path) for role, (path, _) in locked_sources.items()},
            "BS_helper_path": str(helper_path), "BS_helper_sha256": sha256(helper_path),
            "local_feedback_lock_path": str(V3 / "LOCKED_CFG.json"),
            "local_feedback_lock_sha256": sha256(V3 / "LOCKED_CFG.json"),
            "fixed_constants": {k: v.tolist() for k, v in constants.items()},
            "fixed_model_sha256": mlp_lock["mlp15_full72_model_sha256"],
            "helper_sources": helper_sources,
        },
        "Plant_started": False, "MATLAB_started": False, "training_started": False, "TEST_read": False,
        "variable_inertia_read_or_reconstructed": False,
    }
    suffix = "all" if args.scene == "all" else args.scene
    parity_path = ROOT / f"local_feedback_rbf_replay_{suffix}_v1.json"
    parity_path.write_text(json.dumps(parity, indent=2), encoding="utf-8")
    if all_event_rows:
        with (ROOT / f"local_feedback_rbf_event_replay_{suffix}_v1.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(all_event_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_event_rows)
    print(json.dumps({"status": parity["status"], "report": str(parity_path),
                      "scene_results": [{"scene": r["scene_id"], "status": r["status"],
                                         "max_abs": max(r["max_abs_errors"].values()),
                                         "worst": r["worst_event_by_check"]} for r in results]}, indent=2), flush=True)
    if parity["status"] != "PASS_RBF_FULL_EVENT_REPLAY":
        return 2
    if args.phase == "parity":
        return 0
    if args.scene == "all" and len(results) != 6:
        raise ValueError(f"expected six C5 scene parity results, found {len(results)}")
    for scene, contexts in contexts_by_scene.items():
        if len(contexts) != 200:
            raise ValueError(f"expected exactly 200 uniform mature contexts for {scene}; found {len(contexts)}")
    print("local Jacobian evaluation start", flush=True)
    jacobian_rows, summary_rows, outlier_rows = local_jacobian_rows(
        contexts_by_scene, configs_by_scene, constants, model, bs_helper)
    jacobian_path = ROOT / f"local_feedback_rbf_local_jacobians_{suffix}_v1.csv"
    summary_path = ROOT / f"local_feedback_rbf_local_jacobian_summary_{suffix}_v1.csv"
    outlier_path = ROOT / f"local_feedback_rbf_local_jacobian_outliers_{suffix}_v1.csv"
    write_csv(jacobian_path, jacobian_rows)
    write_csv(summary_path, summary_rows)
    write_csv(outlier_path, outlier_rows)
    result = {
        "schema": "DL1018_C5_RBF_LOCAL_JACOBIAN_DIAGNOSIS_V1",
        "status": "PASS_OFFLINE_LOCAL_JACOBIANS",
        "replay_parity_report": str(parity_path), "replay_parity_sha256": sha256(parity_path),
        "scene_count": len(results), "events_per_scene": 200,
        "event_selection": "200 uniformly spaced mature RBF events from the full mature-event index list using rounded linspace positions; no score-based selection",
        "comparison_modes": ["BS-alone", "replayed C5 RBF with frozen W_before", "full72 frozen MLP evaluated hypothetically on the same C5 state/history"],
        "MLP_scope": "hypothetical local evaluation on C5 logged states; not a C5 MLP flight or closed-loop counterfactual",
        "frozen_variables": ["state eta", "reference and derivatives", "arms command", "past 14 MLP feature columns", "RBF W_before"],
        "perturbed_variables": ["current body omega", "nominal BS torque recomputed from omega", "current RBF surface/input recomputed from omega"],
        "epsilon_rad_s": list(EPSILONS),
        "derivative_interpretation": "local frozen-memory torque Jacobian only; negative symmetric-part eigenvalues are not a full stability proof or Plant counterfactual",
        "Plant_calls": 0, "MATLAB_started": False, "training_jobs": 0, "TEST_read": False,
        "variable_inertia_read_or_reconstructed": False,
        "jacobian_csv": str(jacobian_path), "summary_csv": str(summary_path), "outlier_csv": str(outlier_path),
        "jacobian_event_count": len(jacobian_rows), "negative_eigenvalue_event_count": len(outlier_rows),
        "source_hashes": parity["source_hashes"],
    }
    result_path = ROOT / f"local_feedback_rbf_local_jacobian_result_{suffix}_v1.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "result": str(result_path),
                      "jacobian_csv": str(jacobian_path), "summary_csv": str(summary_path),
                      "events": len(jacobian_rows), "negative_events": len(outlier_rows)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
