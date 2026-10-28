"""Read-only HF spectra, same-state reference replay, and two-loop feature audit."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import csd, coherence, welch

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[4]
EXP = ROOT / "experiments" / "dl_attitude_replacement_20261027"
WN12 = EXP / "task_attitude_filter_wn12_hf_screen_v1"
MLP1 = EXP / "mlp15_nominal_residual_v1" / "closed_loop_candidate_v1"
MLP09 = EXP / "mlp15_nominal_residual_v1" / "closed_loop_force09_v1"
GRU1 = ROOT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1"
GRU09 = EXP / "gru_tracking_force09_v1"
METRIC_PATH = GRU1 / "audits" / "score_full72_candidate_v1.py"
OUT = HERE / "HF_C5_PRESERVING_COUPLING_AUDIT_v1.json"
DT = 0.001
FC_HZ = 18.0 / (2.0 * np.pi)


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_metrics():
    spec = importlib.util.spec_from_file_location("hf_coupling_metrics", METRIC_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(METRIC_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def band_rms(x: np.ndarray, bands: list[tuple[str, float, float]]) -> dict:
    f, p = welch(x - np.mean(x, axis=0, keepdims=True), fs=1.0 / DT,
                 nperseg=4096, noverlap=2048, axis=0)
    return {name: float(np.sqrt(np.trapz(p[(f >= lo) & (f < hi)],
                                         f[(f >= lo) & (f < hi)], axis=0).sum()))
            for name, lo, hi in bands}


def load_raw(path: Path) -> dict:
    with h5py.File(path, "r") as f:
        log, ref = f["log"], f["scene/reference"]
        n = int(log["state"].shape[1] - 1)
        read = lambda ds: np.asarray(ds[()], dtype=float)
        data = {
            "state": read(log["state"]).T[:n],
            "target": read(log["command_filter_target_euler"]).T[:n],
            "filtered": read(log["filtered_attitude_reference"]).T[:n],
            "accel_ref": read(ref["acceleration"]).T[:n],
            "yaw_ref": read(ref["yaw"]).reshape(-1)[:n],
            "pos_ref": read(ref["position"]).T[:n],
            "vel_ref": read(ref["velocity"]).T[:n],
            "nominal_force": read(log["position_bs_nominal_force_N"]).T[:n],
            "comp_force": read(log["position_compensation_applied_force_N"]).T[:n],
            "command_force": read(log["position_commanded_force_N"]).T[:n],
            "feature_input_shape": tuple(log["stage1_position_feature_input"].shape),
            "scale": (float(read(log["stage1_position_compensation_scale"]).reshape(-1)[0])
                      if "stage1_position_compensation_scale" in log else 1.0),
            "filter_wn": (read(f["runIdentity/command_filter_wn_rad_s"]).reshape(-1).tolist()
                          if "command_filter_wn_rad_s" in f["runIdentity"] else [18.0, 18.0, 12.0]),
            "test_data_read": (bool(np.asarray(f["runIdentity/test_data_read"][()]).astype(bool).any())
                               if "test_data_read" in f["runIdentity"] else False),
        }
        # The event trace contains learned-head weights and features only; no truth/J/Jdot fields are read.
        ev = np.asarray(log["stage1_position_event_inference_valid"][()]).reshape(-1).astype(bool)
        idx = np.flatnonzero(ev)
        phi = read(log["stage1_position_phi_33"])[:, idx].T
        wb = read(log["stage1_position_event_weight_before_33x3"])
        wa = read(log["stage1_position_event_weight_after_33x3"])
        raw = read(log["stage1_position_event_raw_acceleration_mps2"])[:, idx].T
        beta = read(log["stage1_position_event_beta"]).reshape(-1)[idx]
        data["event_update"] = {"count": int(idx.size), "phi": phi, "weight_before": wb,
                                "weight_after": wa, "raw": raw, "beta": beta}
    return data


def causal_lp(x: np.ndarray) -> np.ndarray:
    alpha = np.exp(-18.0 * DT)
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = alpha * y[i - 1] + (1.0 - alpha) * x[i]
    return y


def response(f_hz: float) -> dict:
    a = np.exp(-18.0 * DT)
    w = 2.0 * np.pi * f_hz * DT
    h = (1.0 - a) / (1.0 - a * np.exp(-1j * w))
    return {"frequency_hz": f_hz, "magnitude": float(abs(h)),
            "phase_deg": float(np.angle(h, deg=True))}


def target_from_force(force, mass, yaw_mapping, yaw_target):
    f = force / mass
    f[:, 2] += 9.8
    ax = np.cos(yaw_mapping) * f[:, 0] + np.sin(yaw_mapping) * f[:, 1]
    ay = np.sin(yaw_mapping) * f[:, 0] - np.cos(yaw_mapping) * f[:, 1]
    roll = np.arctan2(ay, np.hypot(f[:, 2], ax))
    pitch = np.arctan2(ax, f[:, 2])
    tilt = np.hypot(roll, pitch)
    s = np.minimum(1.0, (np.pi / 6) / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * s, pitch * s, yaw_target))


def target_task(raw, metrics):
    a = raw["accel_ref"].copy()
    a[:, 2] += 9.8
    yaw = raw["yaw_ref"]
    ax = np.cos(yaw) * a[:, 0] + np.sin(yaw) * a[:, 1]
    ay = np.sin(yaw) * a[:, 0] - np.cos(yaw) * a[:, 1]
    roll = np.arctan2(ay, np.hypot(a[:, 2], ax))
    pitch = np.arctan2(ax, a[:, 2])
    tilt = np.hypot(roll, pitch)
    s = np.minimum(1.0, (np.pi / 6) / np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll * s, pitch * s, yaw))


def replay_filter(target: np.ndarray, initial: np.ndarray) -> np.ndarray:
    wn = np.array([18.0, 18.0, 12.0])
    limit = np.array([np.inf, np.inf, 6.0])
    angle, rate = initial.copy(), np.zeros(3)
    out = np.empty_like(target)
    for i, desired in enumerate(target):
        out[i] = angle
        err = np.arctan2(np.sin(desired - angle), np.cos(desired - angle))
        acc = np.clip(wn * wn * err - 2.0 * wn * rate, -limit, limit)
        rate += DT * acc
        angle = np.arctan2(np.sin(angle + DT * rate), np.cos(angle + DT * rate))
    return out


def cross_phase(x: np.ndarray, y: np.ndarray, bands) -> dict:
    result = {}
    for name, lo, hi in bands:
        rows = []
        for axis in range(3):
            f, pxy = csd(x[:, axis], y[:, axis], fs=1.0 / DT,
                         nperseg=4096, noverlap=2048)
            fc, coh = coherence(x[:, axis], y[:, axis], fs=1.0 / DT,
                                nperseg=4096, noverlap=2048)
            mask = (f >= lo) & (f < hi)
            rows.append({"axis": axis, "coherence_mean": float(np.mean(coh[mask])),
                         "phase_deg": float(np.angle(np.sum(pxy[mask]), deg=True))})
        result[name] = rows
    return result


def main() -> None:
    metrics = load_metrics()
    wn = readj(WN12 / "MANIFEST.json")
    hf = [r for r in wn["records"] if 9 <= int(r["scene_id"].rsplit("W", 1)[1]) <= 14]
    if len(hf) != 6 or any(r["source_split"] not in ("DEV", "VAL") for r in hf):
        raise RuntimeError("Expected the exact six WN12 DEV/VAL HF scenes")
    score_files = {
        "MLP_alpha1": readj(MLP1 / "audits/CLOSED_LOOP_SCORE_v1.json"),
        "MLP_alpha09": readj(MLP09 / "audits/CLOSED_LOOP_SCORE_v1.json"),
        "GRU_alpha1": readj(GRU1 / "audits/FULL72_PAIRED_SCORE_v1.json"),
    }
    score_rows = {arm: {r["scene_id"]: r for r in score["rows"]}
                  for arm, score in score_files.items()}
    release09 = readj(GRU09 / "RELEASE.json")
    if release09.get("TEST_read") is not False or release09.get("position_nn_compensation_scale") != 0.9:
        raise RuntimeError("GRU force09 release boundary or scale mismatch")
    bands = [("0p1_1Hz", 0.1, 1.0), ("1Hz_to_fc", 1.0, FC_HZ),
             ("fc_to_10Hz", FC_HZ, 10.0), ("10_to_50Hz", 10.0, 50.0),
             ("50_to_500Hz", 50.0, 500.0)]
    cross_bands = [("0p1_1Hz", 0.1, 1.0), ("1Hz_to_fc", 1.0, FC_HZ),
                   ("fc_to_10Hz", FC_HZ, 10.0), ("10_to_50Hz", 10.0, 50.0)]
    rows = []
    for rec in hf:
        sid = rec["scene_id"]
        baseline_task = score_rows["MLP_alpha1"][sid]["methods"]["B"]["task_SO3_rad"]
        for arm in ("MLP_alpha1", "MLP_alpha09", "GRU_alpha1", "GRU_alpha09"):
            if arm == "GRU_alpha09":
                run = GRU09 / "runs" / sid / "GRU_FORCE09_ATTEMPT_01"
                raw_path, status_path = run / "raw_run.mat", run / "run_status.json"
                status = readj(status_path)
                if status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE":
                    raise RuntimeError(f"Incomplete force09 raw: {sid}")
                raw_sha = status["raw_sha256"]
                actual = metrics.score_raw(raw_path, 9.8, np.pi / 6)
            else:
                r = score_rows[arm][sid]
                m = r.get("methods", {}).get("Candidate", {})
                raw_path = Path(r.get("candidate_raw_path") or m.get("raw_path"))
                raw_sha = r.get("candidate_raw_sha256") or m.get("raw_sha256")
                actual = m
            d = load_raw(raw_path)
            if d["test_data_read"]:
                raise RuntimeError(f"TEST flag is set in {arm}/{sid}")
            if arm.endswith("alpha09") and abs(d["scale"] - 0.9) > 1e-12:
                raise RuntimeError(f"Logged force scale mismatch: {arm}/{sid}")
            n = len(d["state"])
            mass = float(np.median((d["nominal_force"] / d["nominal_accel"])[np.abs(d["nominal_accel"]) > 1e-7])) if "nominal_accel" in d else 0.695
            # Force/acceleration ratio from the logged BS nominal path; no truth/inertia inputs.
            with h5py.File(raw_path, "r") as f:
                nominal_accel = np.asarray(f["log/position_nominal_acceleration_mps2"][()], dtype=float).T[:n]
                ratio = np.divide(d["nominal_force"], nominal_accel,
                                  out=np.full_like(nominal_accel, np.nan),
                                  where=np.abs(nominal_accel) > 1e-7)
                mass_values = ratio[np.isfinite(ratio)]
                mass = float(np.median(mass_values[np.isfinite(mass_values)]))
            task = target_task(d, metrics)
            task_to_unfiltered_target = float(np.sqrt(np.mean(metrics.so3(d["target"], task) ** 2)))
            comp_lp = causal_lp(d["comp_force"])
            target_lp = target_from_force(d["nominal_force"] - comp_lp, mass,
                                          d["state"][:, 8], d["yaw_ref"])
            filt_lp = replay_filter(target_lp, d["state"][0, 6:9])
            task_lp = float(np.sqrt(np.mean(metrics.so3(filt_lp, task) ** 2)))
            task_original = float(np.sqrt(np.mean(metrics.so3(d["filtered"], task) ** 2)))
            err = np.arctan2(np.sin(d["target"] - task), np.cos(d["target"] - task))
            pos_error = d["pos_ref"] - d["state"][:, :3]
            sp = d["event_update"]
            ev_pred = np.einsum("eoc,ec->eo", sp["weight_before"], sp["phi"])
            ev_delta = np.einsum("eoc,ec->eo", sp["weight_after"] - sp["weight_before"], sp["phi"])
            ev_reconstruction = float(np.max(np.abs(ev_pred - sp["raw"])))
            beta = sp["beta"][:, None]
            ev_before_applied = beta * np.clip(sp["raw"], -3.0, 3.0)
            ev_after_applied = beta * np.clip(sp["raw"] + ev_delta, -3.0, 3.0)
            update_effect = float(np.sqrt(np.mean((ev_after_applied - ev_before_applied) ** 2)) /
                                  max(np.sqrt(np.mean(ev_before_applied ** 2)), 1e-12))
            lp_bands = band_rms(comp_lp, bands)
            comp_bands = band_rms(d["comp_force"], bands)
            rows.append({
                "scene_id": sid, "arm": arm, "raw_path": str(raw_path), "raw_sha256_bound": raw_sha,
                "position_feature_input_shape_hdf5": list(d["feature_input_shape"]),
                "position_feature_dim": int(d["feature_input_shape"][0]), "logged_scale": d["scale"],
                "mass_kg_from_nominal_force_acceleration": mass,
                "actual_metrics": {k: float(actual[k]) for k in metrics.MAIN},
                "B_task_SO3_rad": float(baseline_task),
                "task_to_command_filter_target_same_state_SO3_rad": task_to_unfiltered_target,
                "task_to_filtered_current_same_state_SO3_rad": task_original,
                "task_to_filtered_fc2p865_same_state_SO3_rad": task_lp,
                "fc2p865_same_state_change_mrad": 1000.0 * (task_lp - task_original),
                "fc2p865_gap_to_B_actual_task_mrad": 1000.0 * (task_lp - baseline_task),
                "force_compensation_rms_N": float(np.sqrt(np.mean(np.sum(d["comp_force"] ** 2, axis=1)))),
                "compensation_force_band_rms_N": comp_bands,
                "fc2p865_lp_band_rms_N": lp_bands,
                "fc2p865_lp_band_retention_ratio": {k: lp_bands[k] / max(comp_bands[k], 1e-12) for k in comp_bands},
                "position_error_rms_xyz_m": np.sqrt(np.mean(pos_error ** 2, axis=0)).tolist(),
                "target_minus_task_band_rms_rad": band_rms(err[:, :2], bands),
                "compensation_vs_nominal_force_cross_phase": cross_phase(d["nominal_force"], d["comp_force"], cross_bands),
                "position_update_events": sp["count"],
                "update_same_feature_raw_output_rms_fraction": float(np.sqrt(np.mean(ev_delta ** 2)) /
                                                                       max(np.sqrt(np.mean(sp["raw"] ** 2)), 1e-12)),
                "update_same_feature_applied_output_rms_fraction": update_effect,
                "update_raw_reconstruction_max_abs_mps2": ev_reconstruction,
            })

    arms = sorted({r["arm"] for r in rows})
    macro = {}
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        macro[arm] = {
            "scene_count": len(rs),
            "Q_m": float(np.mean([r["actual_metrics"]["Q_m"] for r in rs])),
            "task_SO3_rad": float(np.mean([r["actual_metrics"]["task_SO3_rad"] for r in rs])),
            "inner_SO3_rad": float(np.mean([r["actual_metrics"]["inner_SO3_rad"] for r in rs])),
            "task_to_command_filter_target_same_state_SO3_rad": float(np.mean([r["task_to_command_filter_target_same_state_SO3_rad"] for r in rs])),
            "task_to_filtered_current_same_state_SO3_rad": float(np.mean([r["task_to_filtered_current_same_state_SO3_rad"] for r in rs])),
            "task_to_filtered_fc2p865_same_state_SO3_rad": float(np.mean([r["task_to_filtered_fc2p865_same_state_SO3_rad"] for r in rs])),
            "fc2p865_gap_to_B_actual_task_mrad": float(np.mean([r["fc2p865_gap_to_B_actual_task_mrad"] for r in rs])),
            "compensation_force_band_rms_N": {b[0]: float(np.mean([r["compensation_force_band_rms_N"][b[0]] for r in rs])) for b in bands},
            "fc2p865_lp_band_retention_ratio": {b[0]: float(np.mean([r["fc2p865_lp_band_retention_ratio"][b[0]] for r in rs])) for b in bands},
            "update_same_feature_raw_output_rms_fraction": float(np.mean([r["update_same_feature_raw_output_rms_fraction"] for r in rs])),
            "update_same_feature_applied_output_rms_fraction": float(np.mean([r["update_same_feature_applied_output_rms_fraction"] for r in rs])),
        }
    result = {
        "schema": "DL1018_HF_C5_PRESERVING_COUPLING_AUDIT_V1",
        "status": "PASS_READ_ONLY_HF6_RAW_AUDIT",
        "cohort": [r["scene_id"] for r in hf],
        "scope": "Bound DEV/VAL raws only; no Plant reruns, TEST, truth oracle, inertia reconstruction, J, or Jdot inputs.",
        "filter_test": {"type": "single causal first-order low-pass on compensation force", "fc_hz": FC_HZ,
                        "derivation": "The single replay LP cutoff is anchored to the configured roll/pitch command_filter.wn=18 rad/s, expressed as 18/(2pi)=2.865 Hz. This is only a nominal command-filter scale; it is not the closed-loop attitude bandwidth or a transfer-function match. No parameter sweep.",
                        "discrete_pole": float(np.exp(-18.0 * DT)),
                        "transfer_at_frequencies": [response(f) for f in (0.5, 1.0, FC_HZ, 5.0, 10.0)],
                        "interpretation": "Conditional same-state reference/filter replay only; these comparisons are neither strict achievable lower/upper bounds nor predictions of closed-loop Q."},
        "feature_gap_from_runtime": {
            "active_position_feature_dim": 14,
            "existing_features": "position/rate error surface, Euler attitude, preview thrust, and four arm commands (14 total).",
            "observed_but_not_in_feature14": "command-filter roll/pitch state and rate, plus PCF realization state eta; these are logged/deployable causal states but are not inputs to the position DSSM inference. The update law uses its PCF-adjusted surface, while inference phi is computed from the 14-D feature history.",
            "no_true_inertia_used": True,
        },
        "macro_mean_over_six_scenes": macro,
        "per_scene": rows,
        "conclusion": "Global alpha=.9 reduces the force used both for position correction and tilt generation; it buys small task improvement while losing substantial position accuracy. The dominant compensation spectrum is below 10 Hz, so the >10-Hz ripple is not a sufficient explanation. In the original MLP HF cohort, the command-filter target-to-task conditional metric is 80.93 mrad, the filtered reference-to-task metric is 63.83 mrad, and actual task error is 61.36 mrad; increasing command-filter bandwidth to follow the unfiltered target is therefore not supported as a likely task improvement. The fixed fc=2.865-Hz force LP replay improves the same-state filtered-reference metric but still leaves a 3-4 mrad gap to B; these conditional metrics are not bounds, and this modest replay evidence does not justify a closed-loop LP run. Online same-feature update changes are diagnostic only, not causal replays.",
        "next_single_candidate": "Keep the original C5 force path at alpha=1 and train/evaluate a phase-conditioned causal 3-force-output residual module whose deployable inputs add measured filter state/rate and PCF eta to the existing 14-D history. Use a 10-ms-ahead residual target so the correction accounts for command-filter realization lag; gate by paired Q <= original C5 and HF task <= B. This targets the observed missing dynamic context without using J/Jdot or changing metrics. It is a hypothesis for the next isolated training/screen, not a proven fix.",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(OUT), "macro": macro,
                      "lp_fc_hz": FC_HZ}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
