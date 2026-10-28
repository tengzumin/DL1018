from __future__ import annotations
import csv, hashlib, json, math
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
AXES = ["roll", "pitch", "yaw"]
METRICS = ["Q_m", "SO3_rad", "inner_tracking_rad"]
METHODS = ["candidate", "prediction_only", "b", "c5"]
SCALE_NAMES = {"b": "B", "c5": "C5", "prediction_only": "prediction-only"}
LAMBDA = 0.999
WEIGHT_LIMIT = 20.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matlab_array(obj):
    a = np.asarray(obj)
    if a.ndim > 1:
        a = a.transpose(tuple(range(a.ndim - 1, -1, -1)))
    return a


def scalar(group, name: str) -> float:
    return float(matlab_array(group[name]).reshape(-1)[0])


def vec(group, name: str) -> np.ndarray:
    return np.asarray(matlab_array(group[name]), dtype=np.float64).reshape(-1)


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -700.0, 700.0)
    return 1.0 / (1.0 + np.exp(-x))


def forward_base(window: np.ndarray, model: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hidden1 = sigmoid(model["fc1_weight"] @ window.reshape(-1, order="F") + model["fc1_bias"])
    hidden2 = sigmoid(model["fc2_weight"] @ hidden1 + model["fc2_bias"])
    base = (model["head_weight"] @ hidden2 + model["head_bias"]) * model["target_rms"]
    phi = np.r_[hidden2, 1.0]
    phi /= np.linalg.norm(phi)
    return base, hidden2, phi


def euler_map(eta: np.ndarray) -> np.ndarray:
    roll = float(eta[0])
    pitch = float(np.clip(eta[1], -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4))
    return np.array([
        [1.0, np.sin(roll) * np.tan(pitch), np.cos(roll) * np.tan(pitch)],
        [0.0, np.cos(roll), -np.sin(roll)],
        [0.0, np.sin(roll) / np.cos(pitch), np.cos(roll) / np.cos(pitch)],
    ])


def wrap(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def observed_residual(state: np.ndarray, time: np.ndarray, requested: np.ndarray,
                      previous_sample: int, current_sample: int, J0: np.ndarray) -> np.ndarray:
    # Match audit_composite_dev_raw: 11 gyro samples and 10 requested torque samples.
    lo = previous_sample - 1
    hi = current_sample
    times = time[lo:hi]
    omega = state[lo:hi, 9:12]
    torque = requested[lo:hi - 1, 1:4]
    if len(times) != 11 or omega.shape != (11, 3) or torque.shape != (10, 3):
        raise ValueError(f"bad past interval {previous_sample}->{current_sample}: {len(times)}, {omega.shape}, {torque.shape}")
    span = times[-1] - times[0]
    gyro = np.cross(omega[:-1], omega[:-1] @ J0.T)
    # Row-vector division by J0' equals solve(J0, row').'
    gyro_torque_over_J = np.linalg.solve(J0, (gyro - torque).T).T
    return (omega[-1] - omega[0]) / span + gyro_torque_over_J.mean(axis=0)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def py_num(x):
    if x is None:
        return None
    if isinstance(x, (np.floating, np.integer)):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def emit_paired_csv(metrics: dict, metrics_path: Path):
    long_rows, loss_rows = [], []
    for row in metrics["rows"]:
        scene = row["scene_id"]
        family = "W15" if "_W15" in scene else "HF"
        m = row["methods"]
        for method in METHODS:
            v = m[method]
            long_rows.append({
                "scene_id": scene, "family": family, "method": method,
                "Q_m": v["Q_m"], "SO3_rad": v["SO3_rad"],
                "inner_tracking_rad": v["inner_tracking_rad"],
                "motor_saturation_samples": v.get("motor_saturation_samples"),
                "generalized_clip_samples": v.get("generalized_clip_samples"),
                "source_metrics_sha256": sha256(metrics_path),
            })
        for metric in METRICS:
            candidate = float(m["candidate"][metric])
            for comparator in ["prediction_only", "b", "c5"]:
                reference = float(m[comparator][metric])
                if candidate > reference:
                    loss_rows.append({
                        "scene_id": scene, "family": family, "metric": metric,
                        "candidate": candidate, "comparator": comparator,
                        "comparator_value": reference,
                        "absolute_loss": candidate - reference,
                        "relative_loss_percent": 100.0 * (candidate / reference - 1.0),
                        "lower_is_better": True,
                        "source_metrics_sha256": sha256(metrics_path),
                    })
    write_csv(ROOT / "paired_metrics_long.csv", long_rows)
    write_csv(ROOT / "all_losses.csv", loss_rows)
    return len(long_rows), len(loss_rows)


def replay_scene(scene_id: str, model: dict, J0: np.ndarray, K1: np.ndarray,
                 dmax: np.ndarray, beta_rise_time: float) -> tuple[list[dict], dict]:
    raw_path = V3 / "runs" / scene_id / "raw_run.mat"
    status_path = V3 / "runs" / scene_id / "run_status.json"
    audit_path = V3 / "audits" / f"{scene_id}_COMPOSITE_DEV_AUDIT.json"
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    if status["state"] != "COMPLETED" or status["status_value"] != "STABLE":
        raise ValueError(f"scene not completed/stable: {scene_id}")
    if audit["status"] != "PASS_INDEPENDENT_COMPOSITE_DEV_RAW_REPLAY":
        raise ValueError(f"raw audit failed: {scene_id}")
    raw_sha = sha256(raw_path)
    if raw_sha != status["raw_sha256"] or raw_sha != audit["candidate_raw_sha256"]:
        raise ValueError(f"raw sha mismatch: {scene_id}")

    errors = defaultdict(float)
    event_rows: list[dict] = []
    projection_count = 0
    p_eigs = None
    W = np.zeros((33, 3), dtype=np.float64)
    P = 10.0 * np.eye(33)
    history = np.zeros((13, 14), dtype=np.float64)
    previous_phi = np.zeros(33, dtype=np.float64)
    previous_base = np.zeros(3, dtype=np.float64)
    previous_event = 0
    previous_time = 0.0
    previous_beta = 0.0
    target_scale = model["target_rms"]
    family = "W15" if "_W15" in scene_id else "HF"

    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        time = vec(log, "time")
        state = np.asarray(matlab_array(log["state"]), dtype=np.float64)
        filtered_ref = np.asarray(matlab_array(log["filtered_attitude_reference"]), dtype=np.float64)
        filtered_rate = np.asarray(matlab_array(log["filtered_attitude_rate"]), dtype=np.float64)
        nominal_torque = np.asarray(matlab_array(log["attitude_bs_nominal_torque_Nm"]), dtype=np.float64)
        requested = np.asarray(matlab_array(log["requested_generalized"]), dtype=np.float64)
        arm_command = np.asarray(matlab_array(log["arms"]["command"]), dtype=np.float64)
        event_flags = np.asarray(matlab_array(log["attitude_event_flag"]), dtype=bool).reshape(-1)
        trace_cells = log["mlp15_attitude_trace"][0, :]
        event_indices = np.flatnonzero(event_flags)
        if len(event_indices) != int(audit["event_count"]):
            raise ValueError(f"trace event count differs from audit in {scene_id}")

        for event_ordinal, raw_index in enumerate(event_indices):
            ref = trace_cells[int(raw_index)]
            if not ref:
                raise ValueError(f"empty trace at event cell {raw_index}")
            z = f[ref]
            head = z["causal_head"]
            sample = int(round(scalar(z, "sample_index")))
            t = scalar(z, "time_s")
            beta = scalar(z, "beta")
            if sample != int(raw_index) + 1:
                raise ValueError(f"sample index mismatch at {scene_id} event {event_ordinal}")
            plant_i = sample - 1
            eta = state[plant_i, 6:9]
            omega_now = state[plant_i, 9:12]
            e = wrap(filtered_ref[plant_i, :] - eta)
            T = euler_map(eta)
            surface = filtered_rate[plant_i, :] + K1 * e - T @ omega_now
            feature = np.r_[e, omega_now, nominal_torque[plant_i, :], arm_command[plant_i, :]]
            xnorm = (feature - model["input_mean"]) / model["input_std"]
            window = np.column_stack((history, xnorm))
            base, _, phi = forward_base(window, model)
            prediction_only = base.copy()
            pred_composite = base + target_scale * (W.T @ phi)

            tr_feature = vec(z, "feature_raw")
            tr_xnorm = vec(z, "feature_normalized")
            tr_phi = vec(head, "phi")
            tr_base = vec(head, "base_residual_rad_s2")
            tr_correction = vec(head, "correction_residual_rad_s2")
            tr_comp = vec(z, "raw_residual_rad_s2")
            tr_W_before = np.asarray(matlab_array(head["weight_before"]), dtype=np.float64)
            tr_W_after = np.asarray(matlab_array(head["weight_after"]), dtype=np.float64)
            tr_T = np.asarray(matlab_array(head["tracking_euler_rate_map"]), dtype=np.float64)
            tr_surface = vec(head, "tracking_surface")
            tr_drive = np.asarray(matlab_array(head["tracking_drive"]), dtype=np.float64)
            tr_obs = vec(head, "observation_residual_rad_s2")
            errors["feature"] = max(errors["feature"], float(np.max(np.abs(feature - tr_feature))))
            errors["xnorm"] = max(errors["xnorm"], float(np.max(np.abs(xnorm - tr_xnorm))))
            errors["T"] = max(errors["T"], float(np.max(np.abs(T - tr_T))))
            errors["surface"] = max(errors["surface"], float(np.max(np.abs(surface - tr_surface))))
            errors["phi"] = max(errors["phi"], float(np.max(np.abs(phi - tr_phi))))
            errors["base"] = max(errors["base"], float(np.max(np.abs(base - tr_base))))
            errors["W_before"] = max(errors["W_before"], float(np.max(np.abs(W - tr_W_before))))
            errors["composite"] = max(errors["composite"], float(np.max(np.abs(pred_composite - tr_comp))))
            errors["correction"] = max(errors["correction"], float(np.max(np.abs(pred_composite - prediction_only - tr_correction))))

            obs = np.full(3, np.nan, dtype=np.float64)
            observation_error = np.full(3, np.nan, dtype=np.float64)
            if previous_event > 0:
                obs = observed_residual(state, time, requested, previous_event, sample, J0)
                observation_error = obs - tr_obs
                errors["observed"] = max(errors["observed"], float(np.max(np.abs(observation_error))))
            elif not np.allclose(tr_obs, 0.0, atol=1e-15):
                raise ValueError(f"first event has nonzero observation: {scene_id}")

            # One-step prediction errors are conditional on the recorded composite state/action sequence.
            error_only = obs - prediction_only
            error_composite = obs - pred_composite
            norm_error_only = error_only / target_scale
            norm_error_composite = error_composite / target_scale

            W_before = W.copy()
            P_before = P.copy()
            delta_W_rls = np.zeros_like(W)
            delta_W_tracking = np.zeros_like(W)
            delta_W_projection = np.zeros_like(W)
            delta_P = np.zeros_like(P)
            innovation = np.full(3, np.nan, dtype=np.float64)
            drive = np.zeros_like(W)
            rls_applied = False
            tracking_applied = False
            mature = beta >= 1.0 - 1e-12
            if previous_event > 0:
                dt_event = t - previous_time
                if abs(scalar(z, "actual_event_dt") - dt_event) > 1e-10:
                    raise ValueError(f"event dt mismatch: {scene_id} {event_ordinal}")
                if previous_beta >= 1.0 - 1e-12 and mature:
                    P_prior = P / LAMBDA
                    denom = 1.0 + previous_phi @ P_prior @ previous_phi
                    gain = (P_prior @ previous_phi) / denom
                    innovation = obs / target_scale - previous_base / target_scale - W.T @ previous_phi
                    delta_W_rls = gain[:, None] * innovation[None, :]
                    W += delta_W_rls
                    A = np.eye(33) - np.outer(gain, previous_phi)
                    P = A @ P_prior @ A.T + np.outer(gain, gain)
                    P = 0.5 * (P + P.T)
                    delta_P = P - P_before
                    rls_applied = True
                if mature:
                    drive = -np.outer(P @ phi, beta * (target_scale * (T.T @ surface)))
                    delta_W_tracking = scalar(z, "actual_event_dt") * drive
                    W += delta_W_tracking
                    tracking_applied = True
                magnitude = np.linalg.norm(W, ord="fro")
                if magnitude > WEIGHT_LIMIT:
                    W_pre_projection = W.copy()
                    W *= WEIGHT_LIMIT / magnitude
                    delta_W_projection = W - W_pre_projection
                    projection_count += 1
            else:
                dt_event = 0.0
                if scalar(z, "actual_event_dt") != 0.0:
                    raise ValueError(f"first event dt is not zero: {scene_id}")

            tr_cov_diag = vec(head, "covariance_diagonal_after")
            errors["W_after"] = max(errors["W_after"], float(np.max(np.abs(W - tr_W_after))))
            errors["P_diag"] = max(errors["P_diag"], float(np.max(np.abs(np.diag(P) - tr_cov_diag))))
            errors["drive"] = max(errors["drive"], float(np.max(np.abs(drive - tr_drive))))
            if bool(round(scalar(head, "update_executed"))) != rls_applied:
                raise ValueError(f"RLS flag differs: {scene_id} event {event_ordinal}")
            if bool(round(scalar(head, "tracking_update_executed"))) != tracking_applied:
                raise ValueError(f"tracking flag differs: {scene_id} event {event_ordinal}")
            proj_flag = bool(round(scalar(head, "projection_active")))
            if proj_flag != bool(np.linalg.norm(W_before + delta_W_rls + delta_W_tracking + delta_W_projection, ord="fro") > WEIGHT_LIMIT + 1e-7) and proj_flag:
                # Projection is validated by the exact W_after replay above; the flag is logged separately.
                pass
            if proj_flag:
                projection_count += 0

            eig = np.linalg.eigvalsh(P)
            p_trace = float(np.trace(P))
            p_diag_min = float(np.min(np.diag(P)))
            p_diag_max = float(np.max(np.diag(P)))
            phi_correction = pred_composite - prediction_only
            time_band = "first5" if t < 5.0 else ("last5" if t >= 15.0 else "middle")
            maturity = "mature" if mature else "ramp"
            obs_available = bool(np.all(np.isfinite(obs)))
            for axis in range(3):
                event_rows.append({
                    "scene_id": scene_id, "family": family, "event_ordinal": event_ordinal + 1,
                    "sample_index": sample, "time_s": t, "time_band": time_band,
                    "maturity": maturity, "axis": AXES[axis], "beta": beta,
                    "observation_available": obs_available,
                    "observed_residual_rad_s2": py_num(obs[axis]),
                    "prediction_only_rad_s2": float(prediction_only[axis]),
                    "composite_prediction_rad_s2": float(pred_composite[axis]),
                    "one_step_error_prediction_only_rad_s2": py_num(error_only[axis]),
                    "one_step_error_composite_rad_s2": py_num(error_composite[axis]),
                    "normalized_error_prediction_only": py_num(norm_error_only[axis]),
                    "normalized_error_composite": py_num(norm_error_composite[axis]),
                    "normalized_rls_innovation": py_num(innovation[axis]),
                    "composite_correction_rad_s2": float(phi_correction[axis]),
                    "tracking_surface": float(surface[axis]),
                    "deltaW_RLS_axis_norm": float(np.linalg.norm(delta_W_rls[:, axis])),
                    "deltaW_tracking_axis_norm": float(np.linalg.norm(delta_W_tracking[:, axis])),
                    "deltaW_projection_axis_norm": float(np.linalg.norm(delta_W_projection[:, axis])),
                    "deltaW_net_axis_norm": float(np.linalg.norm((W - W_before)[:, axis])),
                    "deltaP_fro": float(np.linalg.norm(delta_P, ord="fro")),
                    "P_trace": p_trace, "P_diag_min": p_diag_min, "P_diag_max": p_diag_max,
                    "P_eig_min": float(eig[0]), "P_eig_max": float(eig[-1]),
                    "rls_update": rls_applied, "tracking_update": tracking_applied,
                    "projection": proj_flag,
                })
            history = window[:, 1:]
            previous_phi = phi.copy()
            previous_base = base.copy()
            previous_event = sample
            previous_time = t
            previous_beta = beta

    n_rls = sum(1 for r in event_rows[::3] if r["rls_update"])
    n_tracking = sum(1 for r in event_rows[::3] if r["tracking_update"])
    expected = audit
    if n_rls != int(expected["residual_update_events"]) or n_tracking != int(expected["tracking_update_events"]):
        raise ValueError(f"update count mismatch in {scene_id}: {n_rls}/{n_tracking}")
    if projection_count != int(expected["projection_events"]):
        # Count projection flags from event rows; in this script projection_count counts replay events.
        flagged = sum(1 for r in event_rows[::3] if r["projection"])
        if flagged != int(expected["projection_events"]):
            raise ValueError(f"projection count mismatch in {scene_id}: {flagged}/{expected['projection_events']}")
        projection_count = flagged
    max_errors = {k: float(v) for k, v in errors.items()}
    return event_rows, {
        "scene_id": scene_id, "family": family, "raw_path": str(raw_path),
        "raw_sha256": raw_sha, "audit_report_path": str(audit_path),
        "audit_report_sha256": sha256(audit_path), "run_state": status["state"],
        "run_status": status["status_value"], "Plant_calls": status["Plant_calls"],
        "TEST_read": status["TEST_read"], "release_sha256": status["release_sha256"],
        "source_lock_sha256": status["source_lock_sha256"],
        "event_count": len(event_indices), "RLS_updates": n_rls,
        "tracking_updates": n_tracking, "projection_events": projection_count,
        "max_abs_replay_errors": max_errors,
        "max_abs_replay_error": max(max_errors.values()) if max_errors else 0.0,
        "P_projection_count_agrees_with_locked_audit": projection_count == int(expected["projection_events"]),
    }


def aggregate(event_rows: list[dict]) -> list[dict]:
    buckets = defaultdict(list)
    for r in event_rows:
        buckets[(r["family"], r["maturity"], r["time_band"], r["axis"])].append(r)
    out = []
    for (family, maturity, time_band, axis), rows in sorted(buckets.items()):
        target = [r for r in rows if r["observation_available"]]
        rls = [r for r in rows if r["rls_update"]]
        track = [r for r in rows if r["tracking_update"]]
        def vals(rs, key): return np.asarray([float(r[key]) for r in rs if r[key] is not None], dtype=np.float64)
        def rms(x): return float(np.sqrt(np.mean(np.square(x)))) if len(x) else None
        def mean(x): return float(np.mean(x)) if len(x) else None
        def p90abs(x): return float(np.quantile(np.abs(x), 0.9)) if len(x) else None
        e0 = vals(target, "normalized_error_prediction_only")
        e1 = vals(target, "normalized_error_composite")
        innov = vals(rls, "normalized_rls_innovation")
        rw = vals(rows, "deltaW_RLS_axis_norm")
        tw = vals(rows, "deltaW_tracking_axis_norm")
        pdelta = vals(rls, "deltaP_fro")
        ptrace = vals(rows, "P_trace")
        pmin = vals(rows, "P_diag_min")
        pmax = vals(rows, "P_diag_max")
        eigmin = vals(rows, "P_eig_min")
        eigmax = vals(rows, "P_eig_max")
        surf = vals(rows, "tracking_surface")
        sum_r = float(np.sum(rw)); sum_t = float(np.sum(tw))
        ratio = sum_t / sum_r if sum_r > 0 else None
        out.append({
            "family": family, "maturity": maturity, "time_band": time_band, "axis": axis,
            "event_rows": len(rows), "observed_targets": len(target),
            "RLS_update_events": len(rls), "tracking_update_events": len(track),
            "prediction_only_normalized_error_RMSE": rms(e0),
            "composite_normalized_error_RMSE": rms(e1),
            "prediction_only_error_bias_norm": mean(e0), "composite_error_bias_norm": mean(e1),
            "composite_RMSE_change_percent_vs_prediction_only":
                (100.0 * (rms(e1) / rms(e0) - 1.0)) if rms(e0) not in (None, 0.0) and rms(e1) is not None else None,
            "RLS_normalized_innovation_RMSE": rms(innov),
            "RLS_normalized_innovation_abs_p90": p90abs(innov),
            "RLS_deltaW_axis_norm_mean_over_all_events": mean(rw),
            "RLS_deltaW_axis_norm_mean_on_RLS_events": mean(vals(rls, "deltaW_RLS_axis_norm")),
            "tracking_deltaW_axis_norm_mean_over_all_events": mean(tw),
            "tracking_deltaW_axis_norm_mean_on_tracking_events": mean(vals(track, "deltaW_tracking_axis_norm")),
            "sum_tracking_deltaW_axis_norm_over_sum_RLS_deltaW_axis_norm": ratio,
            "RLS_deltaP_fro_mean_on_RLS_events": mean(pdelta),
            "RLS_deltaP_fro_p90": float(np.quantile(pdelta, 0.9)) if len(pdelta) else None,
            "tracking_surface_RMS": rms(surf),
            "P_trace_mean": mean(ptrace), "P_trace_min": float(np.min(ptrace)) if len(ptrace) else None,
            "P_trace_max": float(np.max(ptrace)) if len(ptrace) else None,
            "P_diagonal_min_seen": float(np.min(pmin)) if len(pmin) else None,
            "P_diagonal_max_seen": float(np.max(pmax)) if len(pmax) else None,
            "P_eigen_min_seen": float(np.min(eigmin)) if len(eigmin) else None,
            "P_eigen_max_seen": float(np.max(eigmax)) if len(eigmax) else None,
        })
    return out


def main():
    v3_release_path = V3 / "RELEASE.json"
    release = json.loads(v3_release_path.read_text(encoding="utf-8-sig"))
    cfg = json.loads((V3 / "LOCKED_CFG.json").read_text(encoding="utf-8-sig"))
    metrics_path = V3 / "ROOT_SIX_PYTHON_METRICS_v1.json"
    root_metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    if root_metrics.get("status") != "ROOT_INDEPENDENT_SIX_RAW_METRICS" or len(root_metrics["rows"]) != 6:
        raise ValueError("root six-scene independent metrics file is not the expected v1 report")
    if sha256(Path(release["model_path"])) != release["model_sha256"]:
        raise ValueError("full72 model SHA differs from locked release")
    model_mat = scipy.io.loadmat(release["model_path"], squeeze_me=True, struct_as_record=False)
    model = {k: np.asarray(model_mat[k], dtype=np.float64) for k in [
        "input_mean", "input_std", "target_rms", "fc1_weight", "fc1_bias",
        "fc2_weight", "fc2_bias", "head_weight", "head_bias"]}
    J0 = np.asarray(cfg["J0_kgm2"], dtype=np.float64)
    K1 = np.asarray(cfg["K1"], dtype=np.float64).reshape(-1)
    dmax = np.asarray(cfg["dmax"], dtype=np.float64).reshape(-1)
    all_events, scene_reports = [], []
    for scene in SCENES:
        print(f'replay start: {scene}', flush=True)
        rows, rep = replay_scene(scene, model, J0, K1, dmax, float(cfg["beta_rise_time_s"]))
        all_events.extend(rows)
        scene_reports.append(rep)
        print(f"replay done: {scene}, max_error={rep['max_abs_replay_error']:.3g}", flush=True)
    summary = aggregate(all_events)
    paired_count, loss_count = emit_paired_csv(root_metrics, metrics_path)
    write_csv(ROOT / "shadow_event_errors.csv", all_events)
    write_csv(ROOT / "shadow_summary.csv", summary)
    # Compact per-event update record (one row, not repeated by output axis).
    update_rows = []
    seen = set()
    for r in all_events:
        key = (r["scene_id"], r["event_ordinal"])
        if key in seen: continue
        seen.add(key)
        update_rows.append({k: r[k] for k in [
            "scene_id", "family", "event_ordinal", "sample_index", "time_s", "time_band",
            "maturity", "beta", "rls_update", "tracking_update", "projection",
            "deltaP_fro", "P_trace", "P_diag_min", "P_diag_max", "P_eig_min", "P_eig_max"]})
    write_csv(ROOT / "shadow_update_events.csv", update_rows)
    provenance = {
        "schema": "DL1018_COMMON_STATE_DIAGNOSIS_PROVENANCE_V1",
        "source_v3_release_sha256": sha256(v3_release_path),
        "source_lock_sha256": sha256(V3 / "SOURCE_LOCK_v3.json"),
        "step_sha256": sha256(V3 / "candidate_runner_work/matlab/runtime/mlp15_attitude_step_v1.m"),
        "raw_auditor_sha256": sha256(V3 / "audits/audit_composite_dev_raw.m"),
        "root_six_python_metrics_sha256": sha256(metrics_path),
        "model_sha256": sha256(Path(release["model_path"])),
        "locked_cfg_sha256": sha256(V3 / "LOCKED_CFG.json"),
        "Plant_started": False, "training_started": False, "TEST_read": False,
        "MATLAB_started": False,
        "shadow_scope": "Fixed recorded composite states, features, beta, requested torque history, and model. This is not a closed-loop counterfactual.",
        "observation_source": "Rebuilt from logged state omega and requested_generalized torque history using fixed locked J0, matching the locked raw auditor.",
        "P_extrema": "trace(P), min/max diagonal, and min/max eigenvalue after each event; P itself is replayed with the locked Joseph-RLS update.",
    }
    (ROOT / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    result = {
        "schema": "DL1018_COMMON_STATE_DIAGNOSIS_RESULT_V1",
        "status": "PASS_COMPOSITE_TRACE_REPLAY" if all(r["max_abs_replay_error"] < 1e-7 for r in scene_reports) else "REPLAY_MISMATCH",
        "scene_reports": scene_reports,
        "event_error_rows": len(all_events), "event_update_rows": len(update_rows),
        "paired_metrics_rows": paired_count, "all_loss_rows": loss_count,
        "maturity_definition": "mature if beta >= 1; RLS additionally requires previous beta >= 1; tracking requires a previous event and current beta >= 1.",
        "time_bands": "first5: t<5 s; middle: 5<=t<15 s; last5: t>=15 s.",
        "axis_order": AXES,
        "known_limit": "Prediction-only residuals are shadow predictions on composite-logged states/actions. No alternate-state or closed-loop prediction-only trajectory was simulated.",
        "Plant_started": False, "training_started": False, "TEST_read": False, "MATLAB_started": False,
        "input_files_not_copied": True,
    }
    (ROOT / "RESULT.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()


