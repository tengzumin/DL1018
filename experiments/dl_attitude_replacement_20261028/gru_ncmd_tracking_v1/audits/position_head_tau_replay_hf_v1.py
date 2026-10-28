"""Read-only same-trajectory HF replay of the delayed prediction head at tau=0.1 s."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.signal import coherence, csd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
EXP26 = ROOT / "experiments" / "dl_attitude_replacement_20261026"
NCMD = ROOT / "experiments" / "dl_attitude_replacement_20261028" / "gru_ncmd_tracking_v1"
FULL72 = EXP26 / "gru_stream_cosine_tracking_head_full72_v1"
OUT = HERE / "POSITION_HEAD_TAU_REPLAY_HF_V1.json"
MASS = 0.695
H = 0.010
GAMMA = 12.0
LAMBDA = 0.002
WMAX = 60.0
PRED_MAX = 3.0


def readj(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def load_raw(path: Path, expected_sha: str, sid: str, arm: str) -> dict:
    if sha(path).lower() != expected_sha.lower():
        raise RuntimeError(f"raw hash mismatch: {arm}/{sid}")
    with h5py.File(path, "r") as f:
        g = f["log"]
        read = lambda k: np.asarray(g[k][()], dtype=np.float64)
        active = read("stage1_position_event_inference_valid").ravel().astype(bool)
        event_idx = np.flatnonzero(active)
        phi = read("stage1_position_event_phi_33").T
        s_eff = read("stage1_position_pcf_event_s_coord_eff_mps").T
        target = read("stage1_position_delayed_prediction_target_mps2").T
        previous = read("stage1_position_delayed_prediction_prev_index_zero_based").ravel()
        beta = read("stage1_position_event_beta").ravel()
        W0 = read("stage1_position_weight_initial").T
        W_before = read("stage1_position_event_weight_before_33x3").transpose(0, 2, 1)
        W_after = read("stage1_position_event_weight_after_33x3").transpose(0, 2, 1)
        applied_logged = read("stage1_position_event_applied_acceleration_mps2").T
        step_ids = read("stage1_position_event_step_index").ravel()
    n = len(event_idx)
    if phi.shape != (20000, 33) or s_eff.shape != (20000, 3) or target.shape != (20000, 3):
        raise RuntimeError(f"unexpected trace shapes: {arm}/{sid}")
    if W0.shape != (33, 3) or W_before.shape != (n, 33, 3) or W_after.shape != (n, 33, 3):
        raise RuntimeError(f"unexpected weight trace shapes: {arm}/{sid}")
    if len(step_ids) != n:
        raise RuntimeError(f"event index count mismatch: {arm}/{sid}")
    if not np.array_equal(step_ids.astype(np.int64), event_idx.astype(np.int64) + 1):
        raise RuntimeError(f"event step index mismatch: {arm}/{sid}")
    phi_norm_err = float(np.max(np.abs(np.linalg.norm(phi[event_idx], axis=1) - 1.0)))
    if phi_norm_err > 1e-10:
        raise RuntimeError(f"event phi is not unit norm: {arm}/{sid}: {phi_norm_err}")
    # The compact step-index audit is separate from the full transition-index mask.
    return {
        "scene_id": sid, "arm": arm, "raw_path": str(path), "raw_sha256": expected_sha,
        "event_phi_max_unit_norm_error": phi_norm_err,
        "event_idx": event_idx, "phi": phi, "s_eff": s_eff, "target": target,
        "previous": previous, "beta": beta, "W0": W0, "W_before": W_before,
        "W_after": W_after, "applied_logged": applied_logged, "step_ids": step_ids,
    }


def replay(trace: dict, rho: float) -> dict:
    W = trace["W0"].copy()
    pred = np.full((20000, 3), np.nan)
    before_err = 0.0
    after_err = 0.0
    applied_err = 0.0
    event_to_row = {int(k): i for i, k in enumerate(trace["event_idx"])}
    for row, k in enumerate(trace["event_idx"]):
        k = int(k)
        phi = trace["phi"][k]
        beta = trace["beta"][k]
        before_err = max(before_err, float(np.max(np.abs(W - trace["W_before"][row]))))
        raw = W.T @ phi
        pred[k] = beta * np.clip(raw, -PRED_MAX, PRED_MAX)
        applied_err = max(applied_err, float(np.max(np.abs(pred[k] - trace["applied_logged"][k]))))
        grad = np.zeros((33, 3))
        jv = trace["previous"][k]
        y = trace["target"][k]
        if np.isfinite(jv):
            j = int(jv)
            if j not in event_to_row or not np.isfinite(y).all():
                raise RuntimeError(f"bad delayed pair {trace['arm']}/{trace['scene_id']} k={k}, j={j}")
            phi_prev = trace["phi"][j]
            grad = np.outer(phi_prev, W.T @ phi_prev - y)
        candidate = W - H * GAMMA * beta * np.outer(phi, trace["s_eff"][k]) - H * LAMBDA * W - rho * grad
        W = np.clip(candidate, -WMAX, WMAX)
        after_err = max(after_err, float(np.max(np.abs(W - trace["W_after"][row])))) if abs(rho - 0.01) < 1e-14 else after_err
    # Each event's issued output at j is paired with the delayed target available 10 ms later at k.
    pred_future, y_future, pair_idx = [], [], []
    for k in trace["event_idx"]:
        k = int(k)
        jv = trace["previous"][k]
        if np.isfinite(jv):
            j = int(jv)
            if np.isfinite(pred[j]).all() and np.isfinite(trace["target"][k]).all():
                pred_future.append(pred[j])
                y_future.append(trace["target"][k])
                pair_idx.append(j)
    p = np.asarray(pred_future)
    y = np.asarray(y_future)
    pair_idx = np.asarray(pair_idx, dtype=int)
    if len(p) < 1000 or not np.all(np.diff(pair_idx) == 10):
        raise RuntimeError(f"unexpected future target pairing: {trace['arm']}/{trace['scene_id']}")
    err = p - y
    axis = {}
    for a, name in enumerate(("x", "y", "z")):
        pa, ya = p[:, a] - np.mean(p[:, a]), y[:, a] - np.mean(y[:, a])
        ff, pxy = csd(pa, ya, fs=100.0, nperseg=512, noverlap=256, detrend="constant")
        fc, coh = coherence(pa, ya, fs=100.0, nperseg=512, noverlap=256, detrend="constant")
        band = (ff >= 1.0) & (ff <= 3.0)
        corr = float(np.corrcoef(pa, ya)[0, 1]) if np.std(pa) and np.std(ya) else 0.0
        axis[name] = {
            "future_label_rmse_mps2": float(np.sqrt(np.mean((p[:, a] - y[:, a]) ** 2))),
            "zero_lag_correlation": corr,
            "mean_coherence_1_to_3_hz": float(np.mean(coh[band])),
            "phase_label_relative_to_prediction_deg_1_to_3_hz": float(np.angle(np.sum(pxy[band]), deg=True)),
        }
    force = MASS * pred[trace["event_idx"]]
    return {
        "rho": rho,
        "tau_s": H / rho,
        "baseline_reconstruction_max_abs_weight_before": before_err,
        "baseline_reconstruction_max_abs_weight_after": after_err,
        "baseline_reconstruction_max_abs_applied_accel": applied_err,
        "future_pair_count": int(len(p)),
        "future_pair_lead_ms": 10.0,
        "future_label_vector_rmse_xy_mps2": float(np.sqrt(np.mean(np.sum(err[:, :2] ** 2, axis=1)))),
        "future_label_vector_rmse_xyz_mps2": float(np.sqrt(np.mean(np.sum(err ** 2, axis=1)))),
        "force_rms_xy_N": float(np.sqrt(np.mean(np.sum(force[:, :2] ** 2, axis=1)))),
        "force_rms_xyz_N": float(np.sqrt(np.mean(np.sum(force ** 2, axis=1)))),
        "axis": axis,
    }


def main() -> None:
    manifest = readj(NCMD / "SCENE_INPUT_MANIFEST_v1.json")
    rows = [r for r in manifest["records"] if 9 <= int(r["scene_id"].rsplit("W", 1)[1]) <= 14]
    if len(rows) != 6 or any(r["source_split"] not in ("DEV", "VAL") for r in rows):
        raise RuntimeError("Expected exactly six DEV/VAL HF W09-W14 scenes")
    full = readj(FULL72 / "audits" / "FULL72_PAIRED_SCORE_v1.json")
    original = {r["scene_id"]: r for r in full["rows"]}
    traces = []
    per_scene = []
    for rec in rows:
        sid = rec["scene_id"]
        ncmd_path = NCMD / "runs" / sid / "raw_run.mat"
        ns = readj(ncmd_path.parent / "run_status.json")
        if ns.get("state") != "COMPLETED" or ns.get("status_value") != "STABLE":
            raise RuntimeError(f"NCMD not completed/stable: {sid}")
        ncmd_t = load_raw(ncmd_path, ns["raw_sha256"], sid, "GRU_NCMD")
        base = original[sid]["methods"]["Candidate"]
        base_path = Path(base["raw_path"])
        bs = readj(base_path.parent / "run_status.json")
        if bs.get("state") != "COMPLETED" or bs.get("status_value") != "STABLE":
            raise RuntimeError(f"Original GRU not completed/stable: {sid}")
        if str(bs.get("raw_sha256", "")).lower() != str(base["raw_sha256"]).lower():
            raise RuntimeError(f"Original GRU status/score hash mismatch: {sid}")
        base_t = load_raw(base_path, base["raw_sha256"], sid, "GRU_original")
        for trace in (base_t, ncmd_t):
            traces.append(trace)
            baseline = replay(trace, 0.01)
            candidate = replay(trace, 0.1)
            per_scene.append({
                "scene_id": sid, "arm": trace["arm"], "raw_path": trace["raw_path"],
                "raw_sha256": trace["raw_sha256"], "baseline_rho_0_01": baseline,
                "candidate_rho_0_1": candidate,
                "future_xy_label_rmse_change_pct": 100.0 * (candidate["future_label_vector_rmse_xy_mps2"] / baseline["future_label_vector_rmse_xy_mps2"] - 1.0),
                "force_rms_xy_change_pct": 100.0 * (candidate["force_rms_xy_N"] / baseline["force_rms_xy_N"] - 1.0),
            })
    macro = {}
    for arm in ("GRU_original", "GRU_NCMD"):
        rr = [r for r in per_scene if r["arm"] == arm]
        macro[arm] = {
            "mean_scene_future_xy_label_rmse_rho_0_01_mps2": float(np.mean([r["baseline_rho_0_01"]["future_label_vector_rmse_xy_mps2"] for r in rr])),
            "mean_scene_future_xy_label_rmse_rho_0_1_mps2": float(np.mean([r["candidate_rho_0_1"]["future_label_vector_rmse_xy_mps2"] for r in rr])),
            "mean_scene_future_xy_label_rmse_change_pct": float(np.mean([r["future_xy_label_rmse_change_pct"] for r in rr])),
            "mean_scene_force_rms_xy_rho_0_01_N": float(np.mean([r["baseline_rho_0_01"]["force_rms_xy_N"] for r in rr])),
            "mean_scene_force_rms_xy_rho_0_1_N": float(np.mean([r["candidate_rho_0_1"]["force_rms_xy_N"] for r in rr])),
            "mean_scene_force_rms_xy_change_pct": float(np.mean([r["force_rms_xy_change_pct"] for r in rr])),
            "mean_scene_xy_axis_phase_deg_label_relative_to_prediction_1_to_3_hz": {
                a: {
                    "rho_0_01": float(np.mean([r["baseline_rho_0_01"]["axis"][a]["phase_label_relative_to_prediction_deg_1_to_3_hz"] for r in rr])),
                    "rho_0_1": float(np.mean([r["candidate_rho_0_1"]["axis"][a]["phase_label_relative_to_prediction_deg_1_to_3_hz"] for r in rr])),
                } for a in ("x", "y")
            },
        }
    c3 = readj(ROOT / "experiments" / "position_delayed_prediction_c3_dev72_20261023" / "C3_DEV72_SUMMARY_v2.json")
    conditions = sorted(set(r.get("condition", "") for r in c3.get("runs", [])))
    output = {
        "schema": "DL1018_POSITION_HEAD_TAU_REPLAY_HF_V1",
        "status": "PASS_READ_ONLY_SAME_TRAJECTORY_REPLAY",
        "scope": "Six matched DEV/VAL HF W09-W14 scenes, original cosine GRU and GRU_NCMD. No Plant, TEST, wind, J, or Jdot access.",
        "historical_parameter_check": {
            "artifact": "experiments/position_delayed_prediction_c3_dev72_20261023/C3_DEV72_SUMMARY_v2.json",
            "screen_run_count": len(c3.get("runs", [])),
            "conditions_found": conditions,
            "tau_0_1_or_rho_0_1_found_in_that_screen": any("TAU01" in x or "RHO01" in x for x in conditions),
        },
        "equations": {
            "source": "candidate_runner_work/matlab/runtime/delayed_prediction_step_candidate.m",
            "rho_definition": "h/tau, h=0.01 s",
            "update": "W+=clip(W - h*gamma*beta*phi*s_eff' - h*lambda*W - rho*phi_prev*(W'*phi_prev-y_prev)', +/-60)",
            "output": "beta*clip(W'*phi, +/-3); issued force = 0.695*output",
            "counterfactual": "Replay changes rho only from .01 to .1 on fixed saved phi/s_eff/targets; it is not a closed-loop rerun.",
        },
        "fixed_parameters": {"h_s": H, "gamma": GAMMA, "lambda": LAMBDA, "rho_baseline": 0.01,
                             "rho_candidate": 0.1, "tau_baseline_s": 1.0, "tau_candidate_s": 0.1,
                             "weight_clip": WMAX, "prediction_clip_mps2": PRED_MAX, "mass_kg": MASS},
        "baseline_reproduction_maxima": {
            arm: {
                "weight_before": max(r["baseline_rho_0_01"]["baseline_reconstruction_max_abs_weight_before"] for r in per_scene if r["arm"] == arm),
                "weight_after": max(r["baseline_rho_0_01"]["baseline_reconstruction_max_abs_weight_after"] for r in per_scene if r["arm"] == arm),
                "applied_acceleration": max(r["baseline_rho_0_01"]["baseline_reconstruction_max_abs_applied_accel"] for r in per_scene if r["arm"] == arm),
            } for arm in ("GRU_original", "GRU_NCMD")
        },
        "macro_equal_scene_mean": macro,
        "per_scene": per_scene,
    }
    if any(v["weight_before"] > 1e-12 or v["weight_after"] > 1e-12 for v in output["baseline_reproduction_maxima"].values()):
        output["status"] = "FAIL_BASELINE_REPLAY_MISMATCH"
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "output": str(OUT),
                      "baseline_reproduction_maxima": output["baseline_reproduction_maxima"],
                      "macro_equal_scene_mean": macro,
                      "historical_parameter_check": output["historical_parameter_check"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
