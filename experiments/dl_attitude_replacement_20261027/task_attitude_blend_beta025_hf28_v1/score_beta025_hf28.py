"""Score beta=.25 HF28 Candidate raws against frozen manifest-only B/C5 numbers."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

STUDY = Path(__file__).resolve().parent
ROOT = STUDY.parents[2]
EXEC_MANIFEST = STUDY / "HF28_EXECUTION_MANIFEST_v1.json"
EXPECTED_EXEC_MANIFEST_SHA = "9bf6f1e2e038eb1cd93ea3da928a4e3be8afbb130609f442b3df70b17050ce22"
FROZEN_SCORER = ROOT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1" / "audits" / "score_full72_candidate_v1.py"
FROZEN_SCORER_SHA = "6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16"
GRAVITY = 9.8
MAX_TILT = 0.5235987755982988
WIN_TOL = 1e-12
CSV_OUT = STUDY / "audits" / "HF28_BETA025_PAIRED_SCORE_v1.csv"
JSON_OUT = STUDY / "audits" / "HF28_BETA025_PAIRED_SCORE_v1.json"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_candidate_binding(raw_path: Path, item, release, input_manifest, release_sha: str,
                            execution_sha: str, input_sha: str, code_lock_sha: str) -> str:
    attempt_dir = raw_path.parent
    start = read_json(attempt_dir / "run_start.json")
    status = read_json(attempt_dir / "run_status.json")
    raw_sha = sha(raw_path)
    scene_id = item["scene_id"]
    expected_start = {
        "scene_id": scene_id,
        "candidate": release["candidate"],
        "split": item["split"],
        "release_sha256": release_sha,
        "execution_manifest_sha256": execution_sha,
        "input_manifest_sha256": input_sha,
        "code_lock_sha256": code_lock_sha,
        "payload_sha256": item["scene_payload_sha256"],
        "external_identity_sha256": item["external_identity_sha256"],
        "B_raw_sha256": item["b_raw_sha256"],
        "C5_raw_sha256": item["c5_raw_sha256"],
        "gru_model_sha256": release["model_sha256"],
        "position_model_sha256": input_manifest["position_model_sha256"],
        "c5_snapshot_sha256": input_manifest["c5_snapshot_sha256"],
        "attitude_arm": "GRU_STREAM",
        "geometry_arm": "ACTIVE",
        "task_attitude_blend_beta": 0.25,
        "blend": "shortest_geodesic_SO3_Rpos_exp_beta_log_RposT_Rtask",
        "task_attitude_source": "baseline_force_to_attitude(r.acceleration,r.euler(3),P)",
        "RBF_attitude_output_enabled": False,
        "RBF_attitude_update_enabled": False,
        "inertia_reconstruction_enabled": False,
        "Plant_truth_deployment_input": False,
        "TEST_read": False,
        "closed_loop_entry": "run_mlp15_dev72_closed_loop(scene,cfg,opts)",
    }
    for key, value in expected_start.items():
        if start.get(key) != value:
            raise ValueError(f"run_start identity mismatch for {scene_id}: {key}")
    if (status.get("scene_id") != scene_id or status.get("candidate") != release["candidate"]
            or status.get("state") != "COMPLETED"
            or status.get("release_sha256") != release_sha or status.get("raw_sha256") != raw_sha
            or status.get("Plant_calls") != 1
            or Path(status.get("raw_path", "")).resolve() != raw_path.resolve()
            or status.get("TEST_read") is not False):
        raise ValueError(f"run_status/raw SHA identity mismatch for {scene_id}")
    with h5py.File(raw_path, "r") as raw:
        if "runIdentity" not in raw or not isinstance(raw["runIdentity"], h5py.Group):
            raise ValueError(f"Candidate raw lacks embedded runIdentity for {scene_id}")
    return raw_sha


def frozen_score_raw():
    if sha(FROZEN_SCORER) != FROZEN_SCORER_SHA:
        raise RuntimeError("Frozen full72 scorer SHA-256 mismatch")
    spec = importlib.util.spec_from_file_location("frozen_full72_score_raw", FROZEN_SCORER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import frozen score_raw implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score_raw


def matlab_text(node) -> str:
    value = np.asarray(node[()])
    if value.dtype.kind in "ui":
        chars = [chr(int(code)) for code in value.reshape(-1, order="F") if int(code) != 0]
        return "".join(chars).strip()
    if value.dtype.kind in "SU":
        return "".join(str(item.decode("utf-8") if isinstance(item, bytes) else item)
                       for item in value.reshape(-1, order="F")).replace("\x00", "").strip()
    return ""


def candidate_diagnostics(path: Path):
    with h5py.File(path, "r") as raw:
        if "runIdentity" not in raw:
            raise ValueError("Candidate raw lacks embedded runIdentity")
        log = raw["log"]
        status = matlab_text(log["status"]) if "status" in log else "UNKNOWN"
        reason = matlab_text(log["safety_stop_reason"]) if "safety_stop_reason" in log else "UNKNOWN"
        time = np.asarray(log["time"][()], dtype=np.float64).reshape(-1)
        state = np.asarray(log["state"][()], dtype=np.float64).T
        required = ("motor_command", "filtered_attitude_reference", "command_filter_target_euler",
                    "command_filter_task_attitude_reference_euler", "controller_call_time_s")
        finite = np.isfinite(time).all() and np.isfinite(state).all()
        reference = raw["scene/reference"]
        for name in ("position", "velocity", "acceleration", "yaw", "yaw_rate", "yaw_acceleration"):
            if name not in reference:
                finite = False
            else:
                finite = finite and np.isfinite(np.asarray(reference[name][()], dtype=np.float64)).all()
        for name in required:
            if name not in log:
                finite = False
            else:
                finite = finite and np.isfinite(np.asarray(log[name][()], dtype=np.float64)).all()
        calls = np.asarray(log["controller_call_time_s"][()], dtype=np.float64).reshape(-1) if "controller_call_time_s" in log else np.array([])
        if calls.size == 0 or not np.isfinite(calls).all():
            p50 = p95 = maximum = None
        else:
            p50, p95 = (float(x) for x in np.percentile(calls, [50, 95], method="linear"))
            maximum = float(np.max(calls))
        transitions = int(np.asarray(log["last_transition"][()]).reshape(-1)[0]) if "last_transition" in log else -1
        motor = np.asarray(log["motor_saturated"][()], dtype=bool).T
        clipped = np.asarray(log["generalized_clipped"][()], dtype=bool).T
        tilt = np.asarray(log["tilt_limited"][()], dtype=bool).reshape(-1)
        projection = (np.asarray(log["attitude_head_projection_active"][()], dtype=bool).reshape(-1)
                      if "attitude_head_projection_active" in log else None)
        saturated = (np.asarray(log["attitude_head_output_saturated"][()], dtype=bool).reshape(-1)
                     if "attitude_head_output_saturated" in log else None)
        safety = {
            "motor_saturation_samples": int(np.any(motor, axis=1).sum()),
            "generalized_clip_samples": int(np.any(clipped, axis=1).sum()),
            "tilt_limited_samples": int(tilt.sum()),
            "attitude_head_projection_samples": None if projection is None else int(projection.sum()),
            "attitude_head_output_saturated_samples": None if saturated is None else int(saturated.sum()),
        }
    safe_reason = reason.strip().lower() in ("", "none")
    complete = transitions == 20000 and time.size == 20001 and state.shape == (20001, 12) and status == "STABLE"
    safe_actuators = all(v == 0 for v in safety.values() if v is not None) and all(v == 0 for v in safety.values())
    return {
        "run_status": status, "safety_stop_reason": reason, "transitions": transitions,
        "finite_required_signals": bool(finite), "complete": bool(complete),
        "safe_reason": bool(safe_reason), "safety": safety,
        "safe_actuators": bool(safe_actuators),
        "controller_call_time_p50_s": p50, "controller_call_time_p95_s": p95,
        "controller_call_time_max_s": maximum, "_timing_samples": calls.tolist(),
    }


def compare(candidate, baseline):
    if candidate is None:
        return "UNSCORED"
    delta = candidate - baseline
    if delta < -WIN_TOL:
        return "WIN"
    if delta > WIN_TOL:
        return "LOSS"
    return "TIE"


def main() -> None:
    if sha(EXEC_MANIFEST) != EXPECTED_EXEC_MANIFEST_SHA:
        raise RuntimeError("HF28 execution manifest SHA-256 mismatch")
    manifest = read_json(EXEC_MANIFEST)
    scenes = manifest["scenes"]
    if len(scenes) != 28 or manifest["scene_count"] != 28 or manifest["test_accessed"] is not False:
        raise RuntimeError("Expected the frozen 28-scene HF manifest with TEST sealed")
    ids = [row["scene_id"] for row in scenes]
    if len(set(ids)) != 28 or ids != sorted(ids) or any("TEST" in sid for sid in ids):
        raise RuntimeError("Scene list is duplicated, unsorted, or contains TEST")
    release_path = STUDY / "RELEASE.json"
    release = read_json(release_path)
    input_manifest = read_json(STUDY / "HF28_INPUT_MANIFEST_v1.json")
    release_sha = sha(release_path)
    execution_sha = sha(EXEC_MANIFEST)
    input_sha = sha(STUDY / "HF28_INPUT_MANIFEST_v1.json")
    code_lock_sha = sha(STUDY / "HF28_CODE_LOCK_v1.json")
    if (release.get("status") != "RELEASED" or release.get("root_approval_status") != "APPROVED"
            or release.get("TEST_read") is not False
            or release.get("authorized_Plant_calls") != 28 or release.get("authorized_scenes") != ids
            or release.get("execution_manifest_sha256") != execution_sha
            or release.get("input_manifest_sha256") != input_sha
            or release.get("code_lock_sha256") != code_lock_sha
            or release.get("model_path") != input_manifest.get("gru_model_path")
            or release.get("model_sha256") != input_manifest.get("gru_model_sha256")
            or input_manifest.get("test_accessed") is not False):
        raise RuntimeError("Scoring requires the exact released HF28 manifests with TEST sealed")
    score_raw = frozen_score_raw()
    rows = []
    pooled_timing_samples = []
    for item in scenes:
        scene_id = item["scene_id"]
        raw_path = STUDY / "runs_beta025_hf28" / scene_id / "attempt_01" / "raw_run.mat"
        candidate_score = None
        candidate_raw_sha = ""
        identity_binding_ok = False
        diagnostics = {"run_status": "MISSING_RAW", "safety_stop_reason": "UNKNOWN",
                       "transitions": None, "finite_required_signals": False,
                       "complete": False, "safe_reason": False, "safe_actuators": False,
                       "safety": {"motor_saturation_samples": None,
                                  "generalized_clip_samples": None,
                                  "tilt_limited_samples": None,
                                  "attitude_head_projection_samples": None,
                                  "attitude_head_output_saturated_samples": None},
                       "controller_call_time_p50_s": None,
                       "controller_call_time_p95_s": None,
                       "controller_call_time_max_s": None}
        error = ""
        if raw_path.is_file():
            try:
                candidate_raw_sha = verify_candidate_binding(
                    raw_path, item, release, input_manifest, release_sha, execution_sha, input_sha,
                    code_lock_sha)
                identity_binding_ok = True
                diagnostics = candidate_diagnostics(raw_path)
                pooled_timing_samples.extend(diagnostics["_timing_samples"])
                candidate_score = score_raw(raw_path, gravity=GRAVITY, max_tilt=MAX_TILT)
            except Exception as exc:  # Preserve this scene in the paired table; overall screen then fails.
                candidate_score = None
                error = f"{type(exc).__name__}: {exc}"
        else:
            error = "FileNotFoundError: candidate raw missing"
        q = None if candidate_score is None else candidate_score["Q_m"]
        so3 = None if candidate_score is None else candidate_score["task_SO3_rad"]
        row = {
            "scene_id": scene_id, "split": item["split"], "wind_group": item["wind_group"],
            "Candidate_raw_path": str(raw_path) if raw_path.is_file() else "",
            "Candidate_raw_sha256": candidate_raw_sha,
            "Candidate_identity_binding_ok": identity_binding_ok,
            "Candidate_Q_m": q, "B_Q_m": item["B_Q_m"], "C5_Q_m": item["C5_Q_m"],
            "Candidate_task_SO3_rad": so3, "B_task_SO3_rad": item["B_task_SO3_rad"],
            "C5_task_SO3_rad": item["C5_task_SO3_rad"],
            "Candidate_inner_SO3_rad": None if candidate_score is None else candidate_score["inner_SO3_rad"],
            "Candidate_vs_B_Q": compare(q, item["B_Q_m"]),
            "Candidate_vs_C5_Q": compare(q, item["C5_Q_m"]),
            "Candidate_vs_B_task_SO3": compare(so3, item["B_task_SO3_rad"]),
            "Candidate_vs_C5_task_SO3": compare(so3, item["C5_task_SO3_rad"]),
            "Delta_Candidate_vs_B_Q_m": None if q is None else q - item["B_Q_m"],
            "Delta_Candidate_vs_C5_Q_m": None if q is None else q - item["C5_Q_m"],
            "Delta_Candidate_vs_B_task_SO3_rad": None if so3 is None else so3 - item["B_task_SO3_rad"],
            "Delta_Candidate_vs_C5_task_SO3_rad": None if so3 is None else so3 - item["C5_task_SO3_rad"],
            "run_status": diagnostics["run_status"], "safety_stop_reason": diagnostics["safety_stop_reason"],
            "transitions": diagnostics["transitions"], "finite_required_signals": diagnostics["finite_required_signals"],
            "complete": diagnostics["complete"], "safe_reason": diagnostics["safe_reason"],
            "safe_actuators": diagnostics["safe_actuators"],
            **diagnostics["safety"],
            "controller_call_time_p50_s": diagnostics["controller_call_time_p50_s"],
            "controller_call_time_p95_s": diagnostics["controller_call_time_p95_s"],
            "controller_call_time_max_s": diagnostics["controller_call_time_max_s"],
            "score_error": error,
        }
        rows.append(row)


    # Re-evaluate the screen conditions from row values without dropping failed scenes.
    complete = all(r["Candidate_Q_m"] is not None and r["Candidate_task_SO3_rad"] is not None
                   and r["Candidate_identity_binding_ok"]
                   and r["complete"] and r["safe_reason"] and r["safe_actuators"]
                   and r["run_status"] == "STABLE" and r["transitions"] == 20000
                   and r["finite_required_signals"] and r["safety_stop_reason"].strip().lower() in ("", "none")
                   and all(r[k] == 0 for k in ("motor_saturation_samples", "generalized_clip_samples",
                       "tilt_limited_samples", "attitude_head_projection_samples",
                       "attitude_head_output_saturated_samples")) for r in rows)
    macro = {method: {} for method in ("Candidate", "B", "C5")}
    for metric, key in (("Q_m", "Candidate_Q_m"), ("task_SO3_rad", "Candidate_task_SO3_rad")):
        macro["B"][metric] = float(np.mean([r[f"B_{key.removeprefix('Candidate_')}"] for r in rows]))
        macro["C5"][metric] = float(np.mean([r[f"C5_{key.removeprefix('Candidate_')}"] for r in rows]))
        vals = [r[key] for r in rows]
        macro["Candidate"][metric] = float(np.mean(vals)) if all(v is not None for v in vals) else None
    gates = {
        "all_28_scored_and_safe": complete,
        "HF_position_Q_better_than_B": macro["Candidate"]["Q_m"] is not None and macro["Candidate"]["Q_m"] < macro["B"]["Q_m"],
        "HF_position_Q_at_most_1_05_times_C5": macro["Candidate"]["Q_m"] is not None and macro["Candidate"]["Q_m"] <= 1.05 * macro["C5"]["Q_m"],
        "HF_task_SO3_better_than_B": macro["Candidate"]["task_SO3_rad"] is not None and macro["Candidate"]["task_SO3_rad"] < macro["B"]["task_SO3_rad"],
        "HF_task_SO3_better_than_C5": macro["Candidate"]["task_SO3_rad"] is not None and macro["Candidate"]["task_SO3_rad"] < macro["C5"]["task_SO3_rad"],
    }
    gates["screen_pass"] = all(gates.values())
    win_counts = {}
    for metric, a, b in (("Q_m", "Candidate_Q_m", "B_Q_m"),
                         ("task_SO3_rad", "Candidate_task_SO3_rad", "B_task_SO3_rad")):
        outcomes = [compare(r[a], r[b]) for r in rows]
        win_counts[f"vs_B_{metric}"] = {name.lower(): outcomes.count(name) for name in ("WIN", "LOSS", "TIE", "UNSCORED")}
    for metric, a, b in (("Q_m", "Candidate_Q_m", "C5_Q_m"),
                         ("task_SO3_rad", "Candidate_task_SO3_rad", "C5_task_SO3_rad")):
        outcomes = [compare(r[a], r[b]) for r in rows]
        win_counts[f"vs_C5_{metric}"] = {name.lower(): outcomes.count(name) for name in ("WIN", "LOSS", "TIE", "UNSCORED")}
    if CSV_OUT.exists() or JSON_OUT.exists():
        raise RuntimeError("Refusing to overwrite an existing HF28 score artifact")
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0])
    with CSV_OUT.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    pooled = np.asarray(pooled_timing_samples, dtype=np.float64)
    pooled_timing = {"sample_period_s": 0.001, "sample_count": int(pooled.size),
                     "p50_s": float(np.percentile(pooled, 50, method="linear")) if pooled.size else None,
                     "p95_s": float(np.percentile(pooled, 95, method="linear")) if pooled.size else None,
                     "max_s": float(np.max(pooled)) if pooled.size else None}
    summary = {
        "schema": "DL1018_TASK_ATTITUDE_BLEND_BETA025_HF28_SCORE_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": "GRU32_STREAM_COSINE_TASK_BLEND_BETA025_HF28_V1",
        "scene_count": 28, "scored_candidate_scenes": sum(r["Candidate_Q_m"] is not None for r in rows),
        "manifest_sha256": sha(EXEC_MANIFEST), "frozen_score_raw_source": str(FROZEN_SCORER),
        "frozen_score_raw_sha256": sha(FROZEN_SCORER),
        "score_function_call": "score_raw(candidate_raw, gravity=9.8, max_tilt=0.5235987755982988)",
        "gravity_mps2": GRAVITY, "max_tilt_rad": MAX_TILT, "WIN_TOL": WIN_TOL,
        "macro_means_equal_scene_weight": macro, "paired_win_loss_tie_counts": win_counts,
        "gates": gates,
        "controller_timing_reference_s": pooled_timing,
        "baseline_raw_metrics_recomputed": False, "TEST_read": False,
        "row_count": len(rows), "rows": rows,
    }
    with JSON_OUT.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(f"HF28 paired rows: {len(rows)}")
    print(f"Screen: {'PASS' if gates['screen_pass'] else 'FAIL'}")
    print(f"CSV: {CSV_OUT}")
    print(f"JSON: {JSON_OUT}")


if __name__ == "__main__":
    main()
