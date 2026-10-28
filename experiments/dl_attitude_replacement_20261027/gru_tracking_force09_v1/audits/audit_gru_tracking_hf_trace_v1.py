"""Read-only trace replay for the six matched HF GRU WN18 raws."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
EXP27 = ROOT / "experiments" / "dl_attitude_replacement_20261027"
WN12 = EXP27 / "task_attitude_filter_wn12_hf_screen_v1"
GRU1 = ROOT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1"
GRU09 = EXP27 / "gru_tracking_force09_v1"
OUT = HERE / "GRU_TRACKING_HF_TRACE_AUDIT_v1.json"
DT = 0.001
D_MAX = np.array([45.0, 45.0, 4.7124])
K1 = np.array([1.5, 1.5, 1.3])
GAMMA = np.array([2.1, 2.25, 1.1])
SIGMA_W = np.array([0.11, 0.12, 0.20])
S_LIMIT = np.array([2.3, 2.3, 1.4])
WMAX = 60.0
BETA_RISE_TIME = 2.2


def readj(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def wrap(x):
    return np.arctan2(np.sin(x), np.cos(x))


def euler_rate_map(eta):
    phi = eta[0]
    theta = np.clip(eta[1], -np.pi / 2 + 1e-4, np.pi / 2 - 1e-4)
    return np.array([[1.0, np.sin(phi) * np.tan(theta), np.cos(phi) * np.tan(theta)],
                     [0.0, np.cos(phi), -np.sin(phi)],
                     [0.0, np.sin(phi) / np.cos(theta), np.cos(phi) / np.cos(theta)]])


def scalar(g, key):
    return float(np.asarray(g[key][()]).reshape(-1)[0])


def matlab_text(g, key):
    raw = np.asarray(g[key][()]).reshape(-1)
    return "".join(chr(int(c)) for c in raw if int(c) != 0)


def audit_raw(raw_path: Path, raw_expected_sha: str, method: str, sid: str, J0: np.ndarray,
              scale_bindings: dict) -> dict:
    if sha(raw_path).lower() != raw_expected_sha.lower():
        raise RuntimeError(f"raw hash changed: {raw_path}")
    with h5py.File(raw_path, "r") as f:
        log, ident = f["log"], f["runIdentity"]
        test_flag = ("test_data_read" in ident and bool(np.asarray(ident["test_data_read"][()]).astype(bool).any())) or \
                    ("TEST_read" in ident and bool(np.asarray(ident["TEST_read"][()]).astype(bool).any()))
        if test_flag:
            raise RuntimeError(f"TEST flag set in {raw_path}")
        position_scale = float(matlab_text(ident, "position_nn_compensation_scale"))
        if any(abs(float(v) - 0.9) > 1e-12 for v in scale_bindings.values()) or abs(position_scale - 0.9) > 1e-12:
            raise RuntimeError(f"Unexpected position NN force scale {position_scale} in {raw_path}")
        state = np.asarray(log["state"][()], float).T
        ref = np.asarray(log["filtered_attitude_reference"][()], float).T
        ref_rate = np.asarray(log["filtered_attitude_rate"][()], float).T
        nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"][()], float).T
        comp = np.asarray(log["attitude_compensation_applied_torque_Nm"][()], float).T
        requested = np.asarray(log["requested_generalized"][()], float).T[:, 1:4]
        arm_cmd = np.asarray(f["scene/arms/command"][()], float)
        times = np.asarray(log["time"][()], float).reshape(-1)
        refs = np.asarray(log["gru_stream_attitude_trace"][()])
        traces = []
        for i, r in enumerate(refs.reshape(-1)):
            if not r:
                continue
            z = f[r]
            if not isinstance(z, h5py.Group) or "is_attitude_event" not in z:
                continue
            if not bool(scalar(z, "is_attitude_event")):
                continue
            traces.append((i, z))
        if not traces:
            raise RuntimeError(f"no GRU tracking events in {raw_path}")
        maxerr = {k: 0.0 for k in ("feature", "T_map", "surface", "drive", "event_dt",
                                   "beta", "raw_equation", "clip", "beta_scale", "torque",
                               "deltaW_dot", "deltaW_step", "update_params", "sample_hold", "torque_sign")}
        event_times = []
        event_idx = []
        event_torque = []
        clip_count = 0
        dW_count = 0
        max_raw_norm = 0.0
        max_clipped_norm = 0.0
        for i, z in traces:
            # MATLAB sample index is one-based; arrays indexed by zero-based i.
            sample_index = int(scalar(z, "sample_index"))
            if sample_index != i + 1:
                raise RuntimeError(f"trace/sample index mismatch {sid}/{method}")
            now = float(times[i])
            prev = event_times[-1] if event_times else float(times[0])
            dt_event = now - prev
            eta, omega = state[i, 6:9], state[i, 9:12]
            T = euler_rate_map(eta)
            e = wrap(ref[i] - eta)
            surface = ref_rate[i] + K1 * e - T @ omega
            feature = np.r_[e, omega, nominal_torque[i], arm_cmd[:, i]]
            feature_trace = np.asarray(z["feature_raw"][()], float).reshape(-1)
            T_trace = np.asarray(z["tracking_euler_rate_map"][()], float).T
            surf_trace = np.asarray(z["tracking_surface"][()], float).reshape(-1)
            drive = T.T @ np.clip(surface, -S_LIMIT, S_LIMIT)
            drive_trace = np.asarray(z["tracking_drive"][()], float).reshape(-1)
            beta = min(sample_index * DT / BETA_RISE_TIME, 1.0)
            beta_trace = scalar(z, "beta")
            dt_trace = scalar(z, "actual_event_dt")
            event_dt_trace = scalar(z, "event_delta_s")
            qbase = np.asarray(z["q_base_rad_s2"][()], float).reshape(-1)
            dwb = np.asarray(z["DeltaW_before"][()], float)  # HDF5 axes: output x 33 features
            phi = np.asarray(z["phi"][()], float).reshape(-1)
            qraw = qbase + dwb @ phi
            qraw_trace = np.asarray(z["raw_residual_rad_s2"][()], float).reshape(-1)
            qclip = np.clip(qraw, -D_MAX, D_MAX)
            qclip_trace = np.asarray(z["clipped_residual_rad_s2"][()], float).reshape(-1)
            beta_q = beta * qclip
            beta_q_trace = np.asarray(z["beta_scaled_residual_rad_s2"][()], float).reshape(-1)
            tau = J0 @ beta_q
            tau_trace = np.asarray(z["estimateTorque_Nm"][()], float).reshape(-1)
            gamma_trace = np.asarray(z["gamma"][()], float).reshape(-1)
            sigma_trace = np.asarray(z["sigma_w"][()], float).reshape(-1)
            s_limit_trace = np.asarray(z["s_limit"][()], float).reshape(-1)
            dw_dot = np.asarray(z["DeltaW_dot"][()], float)  # output x feature, HDF5 axes
            dwdot_expected = -beta * (GAMMA * drive)[:, None] * phi[None, :] - SIGMA_W[:, None] * dwb
            dw_unproj = dwb + dt_event * dwdot_expected
            dw_unproj_trace = np.asarray(z["DeltaW_unprojected"][()], float)
            dw_after = np.clip(dw_unproj, -WMAX, WMAX)
            dw_after_trace = np.asarray(z["DeltaW_after"][()], float)
            for name, diff in (
                ("feature", feature_trace - feature), ("T_map", T_trace - T),
                ("surface", surf_trace - surface), ("drive", drive_trace - drive),
                ("event_dt", np.array([dt_trace - dt_event, event_dt_trace - dt_event])),
                ("beta", np.array([beta_trace - beta])), ("raw_equation", qraw_trace - qraw),
                ("clip", qclip_trace - qclip), ("beta_scale", beta_q_trace - beta_q),
                ("torque", tau_trace - tau), ("deltaW_dot", dw_dot - dwdot_expected),
            ("update_params", np.r_[gamma_trace - GAMMA, sigma_trace - SIGMA_W,
                                    s_limit_trace - S_LIMIT, scalar(z, "wmax") - WMAX]),
                ("deltaW_step", np.r_[ (dw_unproj_trace - dw_unproj).reshape(-1),
                                        (dw_after_trace - dw_after).reshape(-1)])):
                maxerr[name] = max(maxerr[name], float(np.max(np.abs(diff))))
            max_raw_norm = max(max_raw_norm, float(np.linalg.norm(qraw, ord=np.inf)))
            max_clipped_norm = max(max_clipped_norm, float(np.linalg.norm(qclip, ord=np.inf)))
            clip_count += int(np.any(np.abs(qraw - qclip) > 1e-12))
            dW_count += int(np.linalg.norm(dw_after - dwb) > 0)
            event_times.append(now)
            event_idx.append(i)
            event_torque.append(tau)
        expected = np.zeros_like(comp)
        for j, i in enumerate(event_idx):
            stop = event_idx[j + 1] if j + 1 < len(event_idx) else len(comp)
            expected[i:stop] = event_torque[j]
        maxerr["sample_hold"] = float(np.max(np.abs(comp - expected)))
        maxerr["torque_sign"] = float(np.max(np.abs(requested - (nominal_torque - expected))))
        return {
            "scene_id": sid, "method": method, "raw_path": str(raw_path),
            "raw_sha256": raw_expected_sha, "position_scale": position_scale,
            "position_scale_source_bindings": {**scale_bindings, "raw_runIdentity_decoded": position_scale},
            "event_count": len(traces), "first_sample_index": event_idx[0] + 1,
            "last_sample_index": event_idx[-1] + 1,
            "event_interval_mean_s": float(np.mean(np.diff([times[0]] + event_times))),
            "trace_clip_count": clip_count, "weight_update_event_count": dW_count,
            "max_raw_residual_abs_rad_s2": max_raw_norm,
            "max_clipped_residual_abs_rad_s2": max_clipped_norm,
            "max_abs_trace_replay_error": maxerr,
            "max_abs_error": max(maxerr.values()),
        }


def main() -> None:
    wn = readj(WN12 / "MANIFEST.json")
    release_scale = float(readj(GRU09 / "RELEASE.json")["position_nn_compensation_scale"])
    if abs(release_scale - 0.9) > 1e-12:
        raise RuntimeError("Force09 release scale is not the frozen alpha=.9 value")
    hf = [r for r in wn["records"] if 9 <= int(r["scene_id"].rsplit("W", 1)[1]) <= 14]
    if len(hf) != 6 or any(r["source_split"] not in ("DEV", "VAL") for r in hf):
        raise RuntimeError("Unexpected HF scene cohort")
    rows = []
    parent_audits = []
    for rec in hf:
        sid = rec["scene_id"]
        audit_path = GRU1 / "audits" / f"{sid}_GRU_STREAM_TRACKING_HEAD_FULL72_RAW_AUDIT.json"
        base_audit = readj(audit_path)
        if base_audit.get("status") != "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY":
            raise RuntimeError(f"Parent GRU raw replay audit missing for {sid}")
        parent_audits.append({"scene_id": sid, "status": base_audit["status"],
                              "max_actual_event_dt_error_s": base_audit["max_actual_event_dt_error_s"],
                              "max_feature_rebuild_error": base_audit["max_feature_rebuild_error"],
                              "max_euler_rate_map_rebuild_error": base_audit["max_euler_rate_map_rebuild_error"],
                              "max_q_raw_replay_error_rad_s2": base_audit["max_q_raw_replay_error_rad_s2"],
                              "max_torque_equation_error_Nm": base_audit["max_torque_equation_error_Nm"]})
        locked_j0 = np.asarray(base_audit["fixed_J0_kgm2"], float)
        force_run = GRU09 / "runs" / sid / "GRU_FORCE09_ATTEMPT_01"
        status = readj(force_run / "run_status.json")
        if status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE":
            raise RuntimeError(f"Force09 raw incomplete: {sid}")
        run_start = readj(force_run / "run_start.json")
        scale_bindings = {"release": release_scale,
                          "run_start": float(run_start["position_nn_compensation_scale"]),
                          "run_status": float(status["position_nn_compensation_scale"])}
        rows.append(audit_raw(force_run / "raw_run.mat", status["raw_sha256"], "GRU_alpha09", sid,
                              locked_j0, scale_bindings))

    # Verify the tracking law and Euler mapping used here are unchanged from the parent GRU arm.
    source_paths = ("candidate_runner_work/matlab/runtime/gru_stream_tracking_head_step_v1.m",
                    "candidate_runner_work/matlab/core/attitude_bs_step.m")
    source_hashes = {}
    for rel in source_paths:
        a, b = GRU1 / rel, GRU09 / rel
        source_hashes[rel] = {"parent_sha256": sha(a), "force09_sha256": sha(b),
                              "identical": sha(a) == sha(b)}
    result = {
        "schema": "DL1018_GRU_TRACKING_HF_TRACE_AUDIT_V1",
        "status": "PASS_READ_ONLY_TRACE_REPLAY" if max(r["max_abs_error"] for r in rows) < 1e-8 and all(v["identical"] for v in source_hashes.values()) else "TRACE_MISMATCH",
        "audit_revision_note": "The first audit draft interpreted MATLAB uint16 text for position_nn_compensation_scale as a numeric scalar (ASCII codepoint 48). This rerun decodes the text and binds alpha=.9 across RELEASE, run_start, run_status, and raw runIdentity. No runtime source or raw run changed.",
        "cohort": [r["scene_id"] for r in hf],
        "scope": "Six DEV/VAL GRU force09 raws are independently replayed; parent WN18 raw replay audit results are inherited as locked references. Trace replay uses only fixed controller J0, never plant truth J/Jdot; no Plant/TEST.",
        "runtime_source_hash_comparison": source_hashes,
        "law_constants_from_frozen_runtime": {"K1_attitude": K1.tolist(), "dmax_rad_s2": D_MAX.tolist(),
            "beta_rise_time_s": BETA_RISE_TIME, "gamma": GAMMA.tolist(), "sigma_w": SIGMA_W.tolist(),
            "s_limit": S_LIMIT.tolist(), "wmax": WMAX},
        "trace_interpretation": {
            "error_reference": "feature[0:3] reconstructs wrap(filtered_attitude_reference - actual_Euler); feature[3:6] is measured body omega; feature[6:9] is logged BS nominal torque; feature[9:13] is the current arm command.",
            "T_coordinates": "T is recomputed from actual ZYX Euler angles and maps body omega to Euler rates; T^T surface is the body-coordinate tracking drive. Trace replay checks both.",
            "sign": "The fixed law outputs estimateTorque=J0*(beta*clip(q)); the runtime subtracts that residual torque from nominal torque. The trace is tested against that exact equation.",
            "time_order": "Each event output uses DeltaW_before, then updates DeltaW for the next event; event dt is checked against successive event times and held torque against the 1-ms log.",
            "scale_and_clip": "position_nn_compensation_scale=.9 is a separate position-force path change; the GRU attitude residual keeps the same beta ramp, dmax, and fixed J0 mapping."
        },
        "per_scene": rows,
        "parent_WN18_trace_audits": parent_audits,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(OUT),
                      "max_trace_error": max(r["max_abs_error"] for r in rows),
                      "source_hash_comparison": source_hashes,
                      "scene_summary": [{"scene_id": r["scene_id"], "arm": r["method"],
                                         "events": r["event_count"], "clip_count": r["trace_clip_count"],
                                         "max_error": r["max_abs_error"]} for r in rows]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
