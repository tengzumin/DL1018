"""Read-only HF check of issued-thrust pose acceleration versus the C5 label reference."""
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
Ncmd = ROOT / "experiments" / "dl_attitude_replacement_20261028" / "gru_ncmd_tracking_v1"
FULL72 = EXP26 / "gru_stream_cosine_tracking_head_full72_v1"
NCMD = Ncmd
OUT = HERE / "INNER_POSE_DELAYED_LABEL_HF_V1.json"
DT = 0.001
H = 0.010
MASS_KG = 0.695
GRAVITY = 9.8


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def actual_pose_acceleration(euler: np.ndarray, thrust: np.ndarray) -> np.ndarray:
    phi, theta, yaw = euler.T
    cphi, sphi = np.cos(phi), np.sin(phi)
    ctheta, stheta = np.cos(theta), np.sin(theta)
    cyaw, syaw = np.cos(yaw), np.sin(yaw)
    body_z_world = np.column_stack((
        cyaw * stheta * cphi + syaw * sphi,
        syaw * stheta * cphi - cyaw * sphi,
        ctheta * cphi,
    ))
    return (thrust / MASS_KG)[:, None] * body_z_world - np.array([0.0, 0.0, GRAVITY])


def rms2(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(np.asarray(x) ** 2, axis=1))))


def axis_metrics(delta: np.ndarray, label: np.ndarray) -> dict:
    out = {}
    for axis, name in enumerate(("x", "y")):
        d, y = delta[:, axis], label[:, axis]
        d0, y0 = d - np.mean(d), y - np.mean(y)
        corr = float(np.corrcoef(d0, y0)[0, 1]) if np.std(d0) and np.std(y0) else 0.0
        f, pxy = csd(d, y, fs=1.0 / H, nperseg=512, noverlap=256,
                     detrend="constant")
        fc, coh = coherence(d, y, fs=1.0 / H, nperseg=512, noverlap=256,
                            detrend="constant")
        band = (f >= 1.0) & (f <= 3.0)
        out[name] = {
            "delta_pose_rms_mps2": float(np.sqrt(np.mean(d0 ** 2))),
            "label_rms_mps2": float(np.sqrt(np.mean(y0 ** 2))),
            "zero_lag_correlation": corr,
            "coherence_mean_1_to_3_hz": float(np.mean(coh[band])),
            "phase_label_relative_to_delta_pose_deg_1_to_3_hz": float(np.angle(np.sum(pxy[band]), deg=True)),
        }
    return out


def load_signals(raw_path: Path, expected_sha: str, sid: str, arm: str) -> dict:
    if sha(raw_path).lower() != expected_sha.lower():
        raise RuntimeError(f"raw hash mismatch: {arm}/{sid}")
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        read = lambda key: np.asarray(log[key][()], dtype=np.float64)
        state = read("state").T
        req = read("requested_generalized").T
        af = read("stage1_position_pcf_a_f_mps2").T
        pred_ref = read("stage1_position_pcf_prediction_reference_mps2").T
        label = read("stage1_position_delayed_prediction_target_mps2").T
        prev = read("stage1_position_delayed_prediction_prev_index_zero_based").reshape(-1)
    if state.shape != (20001, 12) or req.shape != (20000, 4) or af.shape != (20000, 3):
        raise RuntimeError(f"unexpected raw dimensions: {arm}/{sid}")
    if pred_ref.shape != af.shape or label.shape != af.shape or prev.shape != (20000,):
        raise RuntimeError(f"unexpected label/reference dimensions: {arm}/{sid}")
    if not all(np.isfinite(a).all() for a in (state, req, af, pred_ref)):
        raise RuntimeError(f"non-finite source signal: {arm}/{sid}")
    # C5's active coordinate mask is [1,1,0]: xy label reference is filtered-pose a_f.
    ref_xy_max = float(np.max(np.abs(pred_ref[:, :2] - af[:, :2])))
    if ref_xy_max > 1e-11:
        raise RuntimeError(f"delayed label xy reference differs from filtered-pose af: {arm}/{sid}")
    actual = actual_pose_acceleration(state[:20000, 6:9], req[:, 0])
    valid = np.flatnonzero(np.isfinite(label).all(axis=1))
    if len(valid) < 1000:
        raise RuntimeError(f"too few delayed labels: {arm}/{sid}")
    intervals, ys, ks, js = [], [], [], []
    label_rebuild_error = 0.0
    for k in valid:
        jv = prev[k]
        if not np.isfinite(jv):
            raise RuntimeError(f"missing previous event index: {arm}/{sid}/{k}")
        j = int(jv)
        if j < 0 or k - j != 10:
            raise RuntimeError(f"delayed interval is not 10 samples: {arm}/{sid}/{k}")
        y_rebuild = (state[k, 3:6] - state[j, 3:6] - DT * np.sum(pred_ref[j:k], axis=0)) / H
        label_rebuild_error = max(label_rebuild_error, float(np.max(np.abs(y_rebuild - label[k]))))
        # Event j→k covers transitions [j,k); average the same interval used by the label.
        intervals.append(np.mean(actual[j:k] - af[j:k], axis=0))
        ys.append(label[k])
        ks.append(int(k))
        js.append(j)
    delta = np.asarray(intervals)
    y = np.asarray(ys)
    if label_rebuild_error > 1e-9:
        raise RuntimeError(f"label interval reconstruction mismatch {arm}/{sid}: {label_rebuild_error}")
    dxy, yxy = delta[:, :2], y[:, :2]
    proposed_yxy = yxy - dxy  # swap only the xy integrated reference from a_f to a_actual_pose.
    return {
        "scene_id": sid, "arm": arm, "raw_path": str(raw_path), "raw_sha256": expected_sha,
        "valid_event_count": len(valid), "first_event_index": ks[0], "last_event_index": ks[-1],
        "mean_interval_samples": float(np.mean(np.asarray(ks) - np.asarray(js))),
        "xy_prediction_reference_af_max_abs_mps2": ref_xy_max,
        "delayed_label_reconstruction_max_abs_mps2": label_rebuild_error,
        "xy_label_vector_rms_mps2": rms2(yxy),
        "xy_actual_minus_filtered_pose_vector_rms_mps2": rms2(dxy),
        "xy_delta_to_label_rms_ratio": rms2(dxy) / max(rms2(yxy), 1e-12),
        "xy_label_after_reference_swap_vector_rms_mps2": rms2(proposed_yxy),
        "xy_label_after_reference_swap_rms_ratio": rms2(proposed_yxy) / max(rms2(yxy), 1e-12),
        "xy_axis_correlation_and_1_to_3_hz_phase": axis_metrics(dxy, yxy),
        "available_runtime_inputs": "issued requested_generalized thrust, measured Euler state, and logged/computed pcf a_f; no wind/J/Jdot",
    }


def main() -> None:
    ncmd_manifest = readj(NCMD / "SCENE_INPUT_MANIFEST_v1.json")
    ncmd_rows = [r for r in ncmd_manifest["records"]
                 if 9 <= int(r["scene_id"].rsplit("W", 1)[1]) <= 14]
    if len(ncmd_rows) != 6 or any(r["source_split"] not in ("DEV", "VAL") for r in ncmd_rows):
        raise RuntimeError("Expected exactly six DEV/VAL HF W09-W14 scenes")
    full = readj(FULL72 / "audits" / "FULL72_PAIRED_SCORE_v1.json")
    full_rows = {r["scene_id"]: r for r in full["rows"]}
    results = []
    for rec in ncmd_rows:
        sid = rec["scene_id"]
        # Only completed, stable raws are eligible. Read status metadata, not TEST or plant truth.
        ncmd_run = NCMD / "runs" / sid
        ncmd_status = readj(ncmd_run / "run_status.json")
        if ncmd_status.get("state") != "COMPLETED" or ncmd_status.get("status_value") != "STABLE":
            raise RuntimeError(f"NCMD run is not completed/stable: {sid}")
        base_score = full_rows[sid]["methods"]["Candidate"]
        base_path = Path(base_score["raw_path"])
        base_status = readj(base_path.parent / "run_status.json")
        if base_status.get("state") != "COMPLETED" or base_status.get("status_value") != "STABLE":
            raise RuntimeError(f"Original GRU run is not completed/stable: {sid}")
        if str(base_status.get("raw_sha256", "")).lower() != str(base_score["raw_sha256"]).lower():
            raise RuntimeError(f"Original GRU status/score raw hash mismatch: {sid}")
        c5_path = Path(rec["c5_raw_path"])
        c5_status = readj(Path(rec["c5_status_path"]))
        if c5_status.get("status") != "RUN_COMPLETE_RAW_PENDING_AUDIT" or \
                c5_status.get("log_status") != "STABLE" or c5_status.get("transitions") != 20000:
            raise RuntimeError(f"C5 run is not completed/stable: {sid}")
        if str(c5_status.get("raw_sha256", "")).lower() != str(rec["c5_raw_sha256"]).lower():
            raise RuntimeError(f"C5 status/manifest raw hash mismatch: {sid}")
        results.extend((
            load_signals(base_path, base_score["raw_sha256"], sid, "GRU_original"),
            load_signals(ncmd_run / "raw_run.mat", ncmd_status["raw_sha256"], sid, "GRU_NCMD"),
            load_signals(c5_path, rec["c5_raw_sha256"], sid, "C5"),
        ))
    macro = {}
    for arm in ("GRU_original", "GRU_NCMD", "C5"):
        rows = [r for r in results if r["arm"] == arm]
        macro[arm] = {
            key: float(np.mean([r[key] for r in rows]))
            for key in ("xy_label_vector_rms_mps2", "xy_actual_minus_filtered_pose_vector_rms_mps2",
                        "xy_delta_to_label_rms_ratio", "xy_label_after_reference_swap_vector_rms_mps2",
                        "xy_label_after_reference_swap_rms_ratio")
        }
        for axis in ("x", "y"):
            macro[arm].setdefault("axis_mean", {})[axis] = {
                key: float(np.mean([r["xy_axis_correlation_and_1_to_3_hz_phase"][axis][key] for r in rows]))
                for key in ("zero_lag_correlation", "coherence_mean_1_to_3_hz",
                            "phase_label_relative_to_delta_pose_deg_1_to_3_hz")
            }
    output = {
        "schema": "DL1018_INNER_POSE_DELAYED_LABEL_HF_V1",
        "status": "PASS_READ_ONLY_6HF_RAW_AUDIT",
        "scope": "Only six DEV/VAL HF W09-W14 scenes. Each GRU original, GRU_NCMD, and C5 raw is status-checked COMPLETED/STABLE and raw-SHA bound. No Plant, TEST, wind, J, or Jdot values are read.",
        "fixed_constants": {"mass_kg": MASS_KG, "gravity_mps2": GRAVITY, "sample_dt_s": DT,
                            "delayed_label_horizon_s": H, "label_source": "logged stage1_position_delayed_prediction_target_mps2",
                            "actual_pose_acceleration": "(requested_generalized thrust / 0.695) * R(measured Euler) * e3 - g*e3"},
        "label_mechanism": {
            "runtime_formula": "y=(v[k]-v[j] - sum(predictionReference[j:k])*dt)/0.01, with k-j=10 samples",
            "xy_prediction_reference": "stage1_position_pcf_prediction_reference_mps2 equals stage1_position_pcf_a_f_mps2 for x/y (mask [1,1,0])",
            "counterfactual_relation": "y_actual_pose_xy = y_current_xy - mean((a_actual_pose-af)_xy over [j,k)); this changes the label only and is not a rerun",
            "interpretation": "a_actual_pose-af is a deployable geometric component using issued thrust and measured attitude, but the residual label still contains external disturbance, actuator mismatch, and other dynamics. Correlation/phase is diagnostic, not causal."
        },
        "macro_mean_six_scenes": macro,
        "per_scene": results,
    }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "output": str(OUT), "macro": macro},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
