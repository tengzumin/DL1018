from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np

HERE = Path(__file__).resolve().parents[1]
LOCK_PATH = HERE / "frozen_inputs.json"
SUMMARY_PATH = HERE / "reports" / "probe_round3.json"
REPORT_PATH = HERE / "reports" / "probe_review_round3.json"
TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def matlab_array(group: h5py.Group, name: str) -> np.ndarray:
    a = np.asarray(group[name])
    return a.transpose(tuple(reversed(range(a.ndim)))) if a.ndim >= 2 else a


def matlab_char(ds: h5py.Dataset) -> str:
    a = np.asarray(ds)
    require(a.dtype.kind in "ui", f"expected MATLAB char dataset at {ds.name}, got {a.dtype}")
    return "".join(chr(int(x)) for x in a.reshape(-1) if int(x) != 0)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def finite_array(a: np.ndarray, label: str) -> None:
    require(np.isfinite(a).all(), f"non-finite values in {label}")


def close_err(a: np.ndarray, b: np.ndarray) -> float:
    require(a.shape == b.shape, f"shape mismatch: {a.shape} vs {b.shape}")
    return float(np.max(np.abs(a - b))) if a.size else 0.0


def main() -> int:
    report: dict[str, Any] = {
        "schema": "ROUND3_PROBE_INDEPENDENT_AUDIT_V1",
        "status": "BLOCKED",
        "decision": "AUDIT_ONLY_NO_CONTINUE_AUTHORIZATION",
        "test_accessed": False,
        "checks": {},
        "errors": [],
    }
    try:
        lock_sha = sha(LOCK_PATH)
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"))
        scenes = lock["scenes"]
        require(len(scenes) == 12 and all(s["split"] == "VAL" for s in scenes), "frozen list is not the required 12 VAL scenes")
        sid = scenes[0]["scene_id"]
        require(sid == "DL1018_VAL_T2_C00_W10", f"unexpected first frozen scene: {sid}")
        attempt = HERE / "runs" / sid / "attempt_01"
        raw_path = attempt / "raw_run.mat"
        start_path = attempt / "run_start.mat"
        status_path = attempt / "run_status.json"
        summary_path = SUMMARY_PATH
        raw_sha, start_sha, status_sha, summary_sha = map(sha, (raw_path, start_path, status_path, summary_path))
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        require(status.get("scene_id") == sid and status.get("mode") == "PROBE" and status.get("status") == "STABLE", "candidate status/scene/mode mismatch")
        require(status.get("frozen_inputs_sha256") == lock_sha, "status does not bind current lock")
        require(status.get("raw_sha256") == raw_sha and status.get("run_start_sha256") == start_sha, "status raw/run_start hashes do not match bytes")
        require(status.get("last_transition") == 20000 and status.get("safety_stop_reason", "") == "", "candidate did not finish all 20,000 transitions safely")
        require(status.get("head_type") == "FEATURE" and status.get("update_enabled") is True and status.get("pcf_enabled") is True, "candidate mode contract mismatch")
        require(status.get("eta_mask") == [1, 1, 0], "candidate eta mask differs from frozen XY-only contract")
        require(summary.get("status") == "PROBE_COMPLETE" and summary.get("scene_id") == sid, "probe summary status/scene mismatch")
        require(summary.get("frozen_inputs_sha256") == lock_sha and summary.get("raw_sha256") == raw_sha and summary.get("run_start_sha256") == start_sha and summary.get("status_sha256") == status_sha, "probe summary does not bind current lock/artifacts")

        manifest_path = Path(lock["reuse_manifest"]["path"])
        require(sha(manifest_path) == lock["reuse_manifest"]["sha256"], "reused pair manifest SHA mismatch")
        rows = read_csv(manifest_path)
        on_row = next(r for r in rows if r["scene_id"] == sid and r["role"] == "ON_CANDIDATE")
        b_row = next(r for r in rows if r["scene_id"] == sid and r["role"] == "B_BASELINE")
        off_row = next(r for r in lock["round2_off_raws"] if r["scene_id"] == sid)
        input_rows = {"on": on_row, "b": b_row, "off": off_row}
        paths = {"candidate": raw_path, "on": Path(on_row["raw_path"]), "b": Path(b_row["raw_path"]), "off": Path(off_row["raw_path"])}
        expected_hashes = {"on": on_row["raw_sha256"], "b": b_row["raw_sha256"], "off": off_row["raw_sha256"]}
        for role, p in paths.items():
            require(p.is_file(), f"missing {role} raw input")
        for role, expected in expected_hashes.items():
            require(sha(paths[role]) == expected, f"matched {role} raw SHA mismatch")

        input_identity = status.get("input_identity", {})
        expected_identity = {
            "scene_id": sid,
            "frozen_inputs_sha256": lock_sha,
            "round2_input_lock_sha256": lock["upstream_round2"]["lock_sha256"],
            "on_raw_sha256": on_row["raw_sha256"],
            "b_raw_sha256": b_row["raw_sha256"],
            "off_raw_sha256": off_row["raw_sha256"],
            "model_mat_sha256": lock["model"]["mat_sha256"],
            "model_binding_sha256": lock["model_binding"]["sha256"],
            "normalizer_npz_sha256": lock["normalizer"]["npz_file_sha256"],
            "normalizer_arrays_identity_sha256": lock["normalizer"]["actual_runner_arrays_identity_sha256"],
            "W0_output_W_sha256": lock["model"]["w0_output_W_double_f_order_sha256"],
            "scene_payload_identity_csv_sha256": lock["scene_payload_identity"]["sha256"],
        }
        for key, val in expected_identity.items():
            require(input_identity.get(key) == val, f"run_status input_identity mismatch: {key}")
        require(status.get("model_mat_sha256") == expected_identity["model_mat_sha256"], "status model SHA differs from lock")
        require(status.get("model_binding_sha256") == expected_identity["model_binding_sha256"], "status model binding differs from lock")
        require(status.get("normalizer_npz_sha256") == expected_identity["normalizer_npz_sha256"], "status normalizer SHA differs from lock")
        require(status.get("normalizer_arrays_identity_sha256") == expected_identity["normalizer_arrays_identity_sha256"], "status normalizer arrays identity differs from lock")
        require(status.get("W0_output_W_sha256") == expected_identity["W0_output_W_sha256"], "status W0 identity differs from lock")

        with h5py.File(start_path, "r") as f:
            require(matlab_char(f["id"]) == sid, "run_start id differs from frozen scene")
            start_fields = {k: matlab_char(f["input"][k]) for k in f["input"] if isinstance(f["input"][k], h5py.Dataset) and f["input"][k].dtype.kind in "ui"}
        start_expected = {
            "scene_id": sid,
            "frozen_inputs_sha256": lock_sha,
            "round2_input_lock_sha256": lock["upstream_round2"]["lock_sha256"],
            "on_raw_sha256": on_row["raw_sha256"],
            "b_raw_sha256": b_row["raw_sha256"],
            "off_raw_sha256": off_row["raw_sha256"],
            "model_mat_sha256": expected_identity["model_mat_sha256"],
            "model_binding_sha256": expected_identity["model_binding_sha256"],
            "normalizer_npz_sha256": expected_identity["normalizer_npz_sha256"],
            "normalizer_arrays_identity_sha256": expected_identity["normalizer_arrays_identity_sha256"],
            "W0_output_W_sha256": expected_identity["W0_output_W_sha256"],
            "scene_payload_identity_csv_sha256": expected_identity["scene_payload_identity_csv_sha256"],
        }
        for key, val in start_expected.items():
            require(start_fields.get(key) == val, f"run_start input identity mismatch: {key}")
        for role in ("on", "b", "off"):
            actual_path = start_fields.get(f"{role}_raw_path")
            require(actual_path is not None and os.path.normcase(os.path.normpath(actual_path)) == os.path.normcase(os.path.normpath(str(paths[role]))), f"run_start {role} path differs from frozen source")
        require(status.get("input_identity", {}).get("on_raw_path") == start_fields.get("on_raw_path"), "run_start/status ON path differs")
        require(status.get("input_identity", {}).get("b_raw_path") == start_fields.get("b_raw_path"), "run_start/status B path differs")
        require(status.get("input_identity", {}).get("off_raw_path") == start_fields.get("off_raw_path"), "run_start/status OFF path differs")

        default_cfg = next(x for x in lock["plantFiles"] if x["name"] == "default_config")
        default_cfg_path = Path(default_cfg["path"])
        require(sha(default_cfg_path) == default_cfg["sha256"], "locked default_config.m SHA mismatch")
        default_cfg_text = default_cfg_path.read_text(encoding="utf-8-sig")
        require("'sigma_w',.002,'wmax',60,'dmax',[3;3;3]" in "".join(default_cfg_text.split()), "frozen default_config adaptation constants differ from audit equation")
        baseline_roles = ("on", "b", "off")
        ref_keys = ("time", "transition_time", "reference/position", "reference/velocity", "reference/acceleration", "reference/yaw")
        with h5py.File(paths["candidate"], "r") as cand_file:
            log = cand_file["log"]
            require(matlab_char(log["scene_id"]) == sid, "candidate raw log scene id mismatch")
            time = matlab_array(log, "time").reshape(-1)
            tt = matlab_array(log, "transition_time").reshape(-1)
            state = matlab_array(log, "state")
            controller_time = matlab_array(log, "controller_call_time_s").reshape(-1)
            require(time.shape == (20001,) and tt.shape == (20000,) and state.shape == (20001, 12) and controller_time.shape == (20000,), "candidate state/time/controller shapes mismatch")
            for name, a in (("time", time), ("transition_time", tt), ("state", state), ("controller_call_time_s", controller_time)):
                finite_array(a, name)
            require(np.max(np.abs(np.diff(time) - 0.001)) <= TOL and np.max(np.abs(tt - time[:-1])) <= TOL, "candidate transition clock is not the canonical 1ms grid")
            require(abs(float(time[0])) <= TOL and abs(float(time[-1]) - 20.0) <= TOL and np.min(controller_time) >= 0.0, "candidate time bounds/controller times invalid")
            scene_arrays = {key: matlab_array(log, key) for key in ref_keys}
            finite_array(scene_arrays["reference/position"], "reference position")
            finite_array(scene_arrays["reference/velocity"], "reference velocity")
            finite_array(scene_arrays["reference/acceleration"], "reference acceleration")
            candidate_flags = {key: matlab_array(log, key) for key in ("tilt_limited", "motor_saturated", "generalized_clipped")}
            event_marker = np.asarray(matlab_array(log, "position_head_update_executed")).reshape(-1)
            require(event_marker.shape == (20000,), "per-tick update marker shape mismatch")
            require(np.issubdtype(event_marker.dtype, np.number) or np.issubdtype(event_marker.dtype, np.bool_), "per-tick update marker is not numeric/bool")
            require(np.all(np.isfinite(event_marker)) and np.all(np.isin(event_marker, (0, 1))), "per-tick update marker is not finite binary data")
            event_tick = event_marker.astype(bool)
            event_idx = np.flatnonzero(event_tick)
            n = event_idx.size
            require(n == int(status["update_event_count"]) == int(status["eta_event_count"]), "event counts disagree with status and raw marker")
            require(n == 1968, f"unexpected PROBE update count: {n}")

            surface_all = matlab_array(log, "stage1_position_pcf_event_s_original_mps")
            eta_all = matlab_array(log, "stage1_position_pcf_event_eta_before_mps")
            eta_eff_all = matlab_array(log, "stage1_position_pcf_event_eta_effective_mps")
            mask_all = matlab_array(log, "stage1_position_pcf_event_eta_mask")
            coord_all = matlab_array(log, "stage1_position_pcf_event_s_coord_mps")
            coord_eff_all = matlab_array(log, "stage1_position_pcf_event_s_coord_eff_mps")
            expected_tick_shape = (20000, 3)
            for label, a in (("surface", surface_all), ("eta_before", eta_all), ("eta_effective", eta_eff_all), ("eta_mask", mask_all), ("s_coord", coord_all), ("s_coord_eff", coord_eff_all)):
                require(a.shape == expected_tick_shape, f"{label} per-tick shape mismatch: {a.shape}")
            surface = surface_all[event_idx]
            eta = eta_all[event_idx]
            eta_eff = eta_eff_all[event_idx]
            mask = mask_all[event_idx]
            coord = coord_all[event_idx]
            coord_eff = coord_eff_all[event_idx]
            for label, a in (("surface events", surface), ("eta_before events", eta), ("eta_effective events", eta_eff), ("eta_mask events", mask), ("s_coord events", coord), ("s_coord_eff events", coord_eff)):
                finite_array(a, label)
            expected_mask = np.tile(np.asarray(lock["run"]["eta_mask"], dtype=float), (n, 1))
            err_mask = close_err(mask, expected_mask)
            err_eta = close_err(eta_eff, eta * expected_mask)
            err_coord = close_err(coord, surface - eta_eff)
            err_clip = close_err(coord_eff, np.clip(coord, [-7.0, -8.0, -10.0], [7.0, 8.0, 10.0]))
            same_state_on_xy_err = close_err(coord_eff[:, :2], np.clip(surface - eta, [-7.0, -8.0, -10.0], [7.0, 8.0, 10.0])[:, :2])
            same_state_off_z_err = close_err(coord_eff[:, 2], np.clip(surface[:, 2], -10.0, 10.0))

            phi_all = matlab_array(log, "stage1_position_event_phi_33")
            raw_all = matlab_array(log, "stage1_position_event_raw_acceleration_mps2")
            applied_all = matlab_array(log, "stage1_position_event_applied_acceleration_mps2")
            dt_all = matlab_array(log, "stage1_position_event_dt_s").reshape(-1)
            beta_all = matlab_array(log, "stage1_position_event_beta").reshape(-1)
            require(phi_all.shape == (20000, 33) and raw_all.shape == expected_tick_shape and applied_all.shape == expected_tick_shape and dt_all.shape == (20000,) and beta_all.shape == (20000,), "event output/update tick array shapes mismatch")
            phi, raw, applied = phi_all[event_idx], raw_all[event_idx], applied_all[event_idx]
            dt, beta = dt_all[event_idx], beta_all[event_idx]
            for label, a in (("phi", phi), ("raw output", raw), ("applied output", applied), ("event dt", dt), ("event beta", beta)):
                finite_array(a, label)
            wb_raw = matlab_array(log, "stage1_position_event_weight_before_33x3")
            wa_raw = matlab_array(log, "stage1_position_event_weight_after_33x3")
            require(wb_raw.shape == (33, 3, n) and wa_raw.shape == wb_raw.shape, f"W event shapes mismatch: {wb_raw.shape}, {wa_raw.shape}")
            finite_array(wb_raw, "W before")
            finite_array(wa_raw, "W after")
            require(np.min(dt) > 0.0 and np.max(np.abs(dt - 0.01)) <= TOL and np.all((beta >= 0.0) & (beta <= 1.0)), "event dt/beta outside valid range")
            dmax = np.asarray([3.0, 3.0, 3.0])
            gamma = float(lock["run"]["gamma"])
            sigma_w = 0.002
            wmax = 60.0
            output_err = 0.0
            recurrence_err = 0.0
            continuity_err = 0.0
            max_weight_delta = 0.0
            projection_active = 0
            for j in range(n):
                before = wb_raw[:, :, j]
                phi_j = phi[j]
                raw_calc = before.T @ phi_j
                applied_calc = beta[j] * np.clip(raw_calc, -dmax, dmax)
                output_err = max(output_err, float(np.max(np.abs(raw[j] - raw_calc))), float(np.max(np.abs(applied[j] - applied_calc))))
                unprojected = before + dt[j] * (-gamma * beta[j] * np.outer(phi_j, coord_eff[j]) - sigma_w * before)
                after_calc = np.clip(unprojected, -wmax, wmax)
                recurrence_err = max(recurrence_err, float(np.max(np.abs(wa_raw[:, :, j] - after_calc))))
                max_weight_delta = max(max_weight_delta, float(np.max(np.abs(wa_raw[:, :, j] - before))))
                projection_active += int(np.any(np.abs(after_calc - unprojected) > TOL))
                if j:
                    continuity_err = max(continuity_err, float(np.max(np.abs(before - wa_raw[:, :, j - 1]))))
            require(max(err_mask, err_eta, err_coord, err_clip, same_state_on_xy_err, same_state_off_z_err, output_err, recurrence_err, continuity_err) <= TOL, "independent event equation/weight recurrence check exceeds 1e-12")
            require(max_weight_delta > float(lock["run"]["weight_delta_threshold_unitless"]), "Head weights did not change above frozen threshold")
            require(int(status["update_event_count"]) == n and status.get("max_eta_mask_value_error_unitless") == 0 and status.get("max_eta_mask_identity_error_mps") == 0 and status.get("max_surface_coord_identity_error_mps") == 0 and status.get("max_surface_clip_error_mps") == 0 and status.get("max_output_before_update_error_mps") == 0 and status.get("max_weight_recurrence_error") == 0, "run_status self-audit reports an event mismatch")

        flag_audit: dict[str, Any] = {}
        reference_equality: dict[str, bool] = {}
        initial_state_equality: dict[str, bool] = {}
        for role in baseline_roles:
            with h5py.File(paths[role], "r") as base_file:
                base_log = base_file["log"]
                base_state = matlab_array(base_log, "state")
                initial_state_equality[role] = base_state.shape == state.shape and bool(np.array_equal(base_state[0, :], state[0, :]))
                require(initial_state_equality[role], f"candidate/{role} initial state differs")
                for key in ref_keys:
                    a = scene_arrays[key]
                    b = matlab_array(base_log, key)
                    reference_equality[f"{role}:{key}"] = a.shape == b.shape and bool(np.array_equal(a, b))
                    require(reference_equality[f"{role}:{key}"], f"candidate/{role} paired scene mismatch in {key}")
                if role in ("on", "b"):
                    require("meta" in base_file and "source_scene_id" in base_file["meta"] and "runtime_scene_id" in base_file["meta"], f"{role} raw is missing explicit source/runtime scene identity")
                    base_source = matlab_char(base_file["meta"]["source_scene_id"])
                    base_runtime = matlab_char(base_file["meta"]["runtime_scene_id"])
                    require(base_source == sid and base_runtime == sid + "_ACC_FIX_V1", f"{role} source/runtime scene identity mismatch")
                for key, cand in candidate_flags.items():
                    base = matlab_array(base_log, key)
                    require(base.shape == cand.shape and base.shape[0] == 20000, f"{role}/{key} flag shape mismatch")
                    finite_array(np.asarray(base, dtype=float), f"{role}/{key}")
                    new = np.logical_and(np.asarray(cand) != 0, np.asarray(base) == 0)
                    count = int(np.count_nonzero(new))
                    require(count == 0, f"candidate introduced {count} new {key} events vs {role}")
                    flag_audit[f"{role}:{key}"] = {
                        "candidate_count": int(np.count_nonzero(cand)),
                        "baseline_count": int(np.count_nonzero(base)),
                        "candidate_only_count": count,
                    }

        stable_artifacts = {"frozen_inputs": (LOCK_PATH, lock_sha), "raw": (raw_path, raw_sha), "run_start": (start_path, start_sha), "run_status": (status_path, status_sha), "probe_summary": (summary_path, summary_sha), "reuse_manifest": (manifest_path, lock["reuse_manifest"]["sha256"]), "default_config": (default_cfg_path, default_cfg["sha256"])}
        for label, (path, expected) in stable_artifacts.items():
            require(sha(path) == expected, f"{label} changed during audit")
        for role, expected in expected_hashes.items():
            require(sha(paths[role]) == expected, f"matched {role} raw changed during audit")
        checks = {
            "status_and_hash_binding": "PASS",
            "run_start_identity": "PASS",
            "matched_inputs_and_scene_payload": "PASS",
            "canonical_1ms_time_grid": "PASS",
            "finite_state_and_controller_time": "PASS",
            "head_event_marker_count": n,
            "max_eta_mask_error": err_mask,
            "max_eta_effective_error_mps": err_eta,
            "max_surface_coordinate_error_mps": err_coord,
            "max_surface_clip_error_mps": err_clip,
            "same_state_xy_vs_pcf_on_error_mps": same_state_on_xy_err,
            "same_state_z_vs_pcf_off_error_mps": same_state_off_z_err,
            "max_output_before_update_error_mps2": output_err,
            "max_weight_recurrence_error": recurrence_err,
            "max_event_weight_continuity_error": continuity_err,
            "max_weight_delta": max_weight_delta,
            "weight_projection_active_events": projection_active,
            "safety_flags_by_reference": flag_audit,
            "paired_scene_exact_reference_equality": reference_equality,
            "paired_scene_exact_initial_state_equality": initial_state_equality,
        }
        report.update({
            "status": "PASS",
            "scene_id": sid,
            "mode": "PROBE",
            "frozen_inputs_sha256": lock_sha,
            "raw_sha256": raw_sha,
            "run_start_sha256": start_sha,
            "run_status_sha256": status_sha,
            "probe_summary_sha256": summary_sha,
            "matched_raw_sha256": {role: sha(paths[role]) for role in baseline_roles},
            "attempt_runtime_seconds": summary["attempt_execution_and_raw_persistence_seconds"],
            "attempt_output_bytes": summary["attempt_output_bytes"],
            "test_accessed": False,
            "checks": checks,
            "errors": [],
        })
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        print(f"ROUND3_PROBE_AUDIT_BLOCKED: {report['errors'][-1]}", file=sys.stderr)
    report["audit_script_sha256"] = sha(Path(__file__).resolve())
    REPORT_PATH.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())










