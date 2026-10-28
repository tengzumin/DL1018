"""Frozen score for the fixed six-scene applied-notch development screen.

Run only after all six authorized candidate scenes have completed. This script
reads raw runs, run identity/status, and locked score manifests; it does not
launch MATLAB or Plant, access TEST data, train, or reconstruct inertia.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
RUNS = STUDY / "runs"
RELEASE_PATH = STUDY / "RELEASE.json"
SOURCE_LOCK_PATH = STUDY / "SOURCE_LOCK_v1.json"
PILOT_RELEASE_SNAPSHOT = HERE / "PILOT_SNAPSHOT_RELEASE.json"
PILOT_LOCK_SNAPSHOT = HERE / "PILOT_SNAPSHOT_SOURCE_LOCK_v1.json"
PILOT_SOURCE_SNAPSHOT = HERE / "PILOT_SOURCE_SNAPSHOT_v1"
BASELINE_SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
OUT_JSON = HERE / "NOTCH_HF6_FROZEN_SCORE_v2.json"
OUT_MD = HERE / "NOTCH_HF6_FROZEN_SCORE_v2.md"

EXPECTED_SCENES = [
    "DL1018_VAL_T3_C01_W14",
    "DL1018_DEV_T1_C10_W09",
    "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T3_C09_W09",
    "DL1018_VAL_T1_C07_W14",
    "DL1018_VAL_T2_C04_W14",
]
BASELINES = ("B", "C5", "Parent_Cosine_GRU")
METRICS = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
MASS_KG = 0.695
DT_S = 0.001
EVENT_DT_S = 0.01
WIN_TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def mat_text(group: h5py.Group, name: str) -> str:
    a = np.asarray(group[name][()]).reshape(-1)
    if a.dtype.kind in "ui":
        return "".join(chr(int(x)) for x in a if int(x))
    if a.dtype.kind == "S":
        return b"".join(a.tolist()).decode("utf-8", errors="ignore").rstrip("\x00")
    return str(a.squeeze())


def scalar(group: h5py.Group, name: str) -> float:
    return float(np.asarray(group[name][()]).squeeze())


def arr3(group: h5py.Group, name: str, n: int) -> np.ndarray:
    a = np.asarray(group[name][()], dtype=float)
    if a.shape == (3, n):
        a = a.T
    if a.shape != (n, 3):
        raise RuntimeError(f"{name}: expected {(n, 3)}, got {a.shape}")
    return a


def verify_lock_files(lock: dict, base: Path, label: str) -> int:
    records = lock.get("files", [])
    require(bool(records), f"{label} source lock has no file records")
    for item in records:
        rel = Path(item["path"])
        path = base / rel
        require(path.is_file(), f"{label} locked source missing: {rel}")
        require(sha(path).lower() == item["sha256"].lower(),
                f"{label} locked source hash mismatch: {rel}")
    return len(records)


def load_source_bindings() -> dict:
    release = readj(RELEASE_PATH)
    current_lock = readj(SOURCE_LOCK_PATH)
    current_release_sha = sha(RELEASE_PATH)
    current_lock_sha = sha(SOURCE_LOCK_PATH)
    require(release.get("status") == "RELEASED", "current notch release is not RELEASED")
    require(release.get("authorized_Plant_calls") == 6, "release budget is not fixed at six scenes")
    require(release.get("authorized_scenes") == EXPECTED_SCENES,
            "release scenes/order differ from the fixed HF6 cohort")
    require(release.get("source_lock_sha256", "").lower() == current_lock_sha.lower(),
            "current RELEASE does not bind current source lock")
    current_source_count = verify_lock_files(current_lock, STUDY, "current generation-2")

    old_release = readj(PILOT_RELEASE_SNAPSHOT)
    old_lock = readj(PILOT_LOCK_SNAPSHOT)
    old_release_sha = sha(PILOT_RELEASE_SNAPSHOT)
    old_lock_sha = sha(PILOT_LOCK_SNAPSHOT)
    archived_release = readj(PILOT_SOURCE_SNAPSHOT / "PILOT_RELEASE.json")
    archived_lock = readj(PILOT_SOURCE_SNAPSHOT / "PILOT_SOURCE_LOCK_v1.json")
    require(sha(PILOT_SOURCE_SNAPSHOT / "PILOT_RELEASE.json").lower() == old_release_sha.lower(),
            "pilot RELEASE snapshot copies differ")
    require(sha(PILOT_SOURCE_SNAPSHOT / "PILOT_SOURCE_LOCK_v1.json").lower() == old_lock_sha.lower(),
            "pilot source-lock snapshot copies differ")
    require(archived_release == old_release and archived_lock == old_lock,
            "pilot archived JSON snapshots differ")
    pilot_source_count = verify_lock_files(old_lock, PILOT_SOURCE_SNAPSHOT, "pilot generation-1 snapshot")
    manifest_path = PILOT_SOURCE_SNAPSHOT / "PILOT_SOURCE_SNAPSHOT_MANIFEST_v1.json"
    manifest_sha = sha(manifest_path)

    require(release.get("applied_acceleration_notch", {}).get("enabled") is True and
            abs(float(release["applied_acceleration_notch"]["center_hz"]) - 3.5) < 1e-12 and
            abs(float(release["applied_acceleration_notch"]["quality_factor"]) - 1.0) < 1e-12,
            "current release notch settings differ from 3.5 Hz / Q=1")
    return {
        "current_release_path": str(RELEASE_PATH),
        "current_release_sha256": current_release_sha,
        "current_source_lock_path": str(SOURCE_LOCK_PATH),
        "current_source_lock_sha256": current_lock_sha,
        "current_source_lock_files_verified": current_source_count,
        "pilot_release_snapshot_path": str(PILOT_RELEASE_SNAPSHOT),
        "pilot_release_snapshot_sha256": old_release_sha,
        "pilot_source_lock_snapshot_path": str(PILOT_LOCK_SNAPSHOT),
        "pilot_source_lock_snapshot_sha256": old_lock_sha,
        "pilot_source_snapshot_manifest_path": str(manifest_path),
        "pilot_source_snapshot_manifest_sha256": manifest_sha,
        "pilot_snapshot_source_files_verified": pilot_source_count,
        "pilot_release_generation": old_release.get("release_generation", 1),
        "current_release_generation": release.get("release_generation", 2),
    }


def completed_candidate_statuses(scene_ids: list[str]) -> dict[str, Path]:
    found: dict[str, list[Path]] = {scene: [] for scene in scene_ids}
    for status_path in RUNS.rglob("run_status.json"):
        try:
            status = readj(status_path)
        except Exception:
            continue
        scene = status.get("scene_id")
        if scene in found and status.get("state") == "COMPLETED":
            found[scene].append(status_path)
    duplicates = {scene: paths for scene, paths in found.items() if len(paths) > 1}
    require(not duplicates, f"multiple completed candidate attempts: {duplicates}")
    missing = [scene for scene, paths in found.items() if not paths]
    require(not missing, "six-scene score waits for completed runs: " + ", ".join(missing))
    return {scene: paths[0] for scene, paths in found.items()}


def validate_status(raw: Path, status_path: Path, status: dict, raw_sha: str, scene: str) -> None:
    complete = status.get("state") == "COMPLETED"
    stable = status.get("status_value", status.get("log_status", "STABLE")) == "STABLE"
    test_value = status.get("TEST_data_read", status.get("test_data_read",
                  status.get("TEST_accessed", status.get("TEST_read", False))))
    require(complete and stable and status.get("scene_id") == scene,
            f"candidate status not complete/stable: {scene}")
    require(status.get("safety_stop_reason", "") == "", f"safety stop in candidate scene: {scene}")
    require(status.get("Plant_calls") == 1 and status.get("transitions") == 20000 and
            status.get("state_samples") == 20001, f"candidate run dimensions/call count differ: {scene}")
    require(test_value is False, f"candidate status reports TEST access: {scene}")
    require(Path(status.get("raw_path", "")).resolve() == raw.resolve() and
            status.get("raw_sha256", "").lower() == raw_sha.lower(),
            f"candidate status/raw identity mismatch: {scene}")


def validate_candidate_identity(scene: str, status_path: Path, bindings: dict) -> dict:
    status = readj(status_path)
    run_dir = status_path.parent
    start_path = run_dir / "run_start.json"
    raw = Path(status.get("raw_path", ""))
    require(start_path.is_file() and raw.is_file(), f"run_start/raw missing: {scene}")
    start = readj(start_path)
    status_sha, start_sha, raw_sha = sha(status_path), sha(start_path), sha(raw)
    validate_status(raw, status_path, status, raw_sha, scene)
    # run_start predates the score helper and binds the scene plus release,
    # source lock, and payload directly; it has no candidate_study_id field.
    require(start.get("scene_id") == scene,
            f"run_start scene identity mismatch: {scene}")
    require(status.get("release_sha256", "").lower() == start.get("release_sha256", "").lower(),
            f"status/run_start release mismatch: {scene}")
    require(start.get("source_lock_sha256", "").lower() == status.get("source_lock_sha256", "").lower(),
            f"status/run_start source-lock mismatch: {scene}")
    if scene == EXPECTED_SCENES[0]:
        expected_release = bindings["pilot_release_snapshot_sha256"]
        expected_lock = bindings["pilot_source_lock_snapshot_sha256"]
        release_kind = "archived_generation_1_pilot"
    else:
        expected_release = bindings["current_release_sha256"]
        expected_lock = bindings["current_source_lock_sha256"]
        release_kind = "current_generation_2_continuation"
    require(start.get("release_sha256", "").lower() == expected_release.lower(),
            f"run release does not match required {release_kind}: {scene}")
    require(start.get("source_lock_sha256", "").lower() == expected_lock.lower(),
            f"run source lock does not match required {release_kind}: {scene}")
    require(start.get("TEST_data_read", start.get("test_data_read", False)) is False,
            f"run_start reports TEST access: {scene}")
    with h5py.File(raw, "r") as f:
        ident = f["runIdentity"]
        require(mat_text(ident, "scene_id") == scene, f"raw runIdentity scene mismatch: {scene}")
        require(mat_text(ident, "release_sha256").lower() == start["release_sha256"].lower(),
                f"raw runIdentity release mismatch: {scene}")
        require(mat_text(ident, "source_lock_sha256").lower() == start["source_lock_sha256"].lower(),
                f"raw runIdentity source-lock mismatch: {scene}")
        require(scalar(ident, "TEST_read") == 0 and
                scalar(ident, "inertia_reconstruction_enabled") == 0,
                f"raw runIdentity forbidden flag set: {scene}")
        # The runIdentity schema intentionally records content hashes, while
        # release generation is a property of the bound release document.
        generation = (bindings["pilot_release_generation"] if scene == EXPECTED_SCENES[0]
                     else bindings["current_release_generation"])
    require(Path(start.get("scene_payload_path", "")).is_file() and
            sha(Path(start["scene_payload_path"])).lower() == start.get("scene_payload_sha256", "").lower(),
            f"scene payload binding mismatch: {scene}")
    return {
        "scene_id": scene,
        "release_kind": release_kind,
        "release_generation_from_bound_release": int(generation),
        "run_dir": str(run_dir),
        "raw_path": str(raw), "raw_sha256": raw_sha,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "run_status_path": str(status_path), "run_status_sha256": status_sha,
        "release_sha256": start["release_sha256"],
        "source_lock_sha256": start["source_lock_sha256"],
        "scene_payload_path": start["scene_payload_path"],
        "scene_payload_sha256": start["scene_payload_sha256"],
        "Plant_calls_in_original_run": status["Plant_calls"],
        "safety_stop_reason": status.get("safety_stop_reason", ""),
        "TEST_data_read": False,
        "inertia_reconstruction_enabled": False,
    }


def candidate_route_audit(record: dict) -> dict:
    raw = Path(record["raw_path"])
    with h5py.File(raw, "r") as f:
        log, ident = f["log"], f["runIdentity"]
        time = np.asarray(log["transition_time"][()], dtype=float).reshape(-1)
        n = len(time)
        event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        inference_valid = np.asarray(log["stage1_position_event_inference_valid"][()], dtype=bool).reshape(-1)
        event_idx = np.flatnonzero(event)
        notch_input = arr3(log, "stage1_position_applied_notch_event_input_mps2", n)
        output_raw = arr3(log, "stage1_position_applied_notch_event_output_raw_mps2", n)
        output_applied = arr3(log, "stage1_position_applied_notch_event_output_applied_mps2", n)
        output_limit = arr3(log, "stage1_position_applied_notch_event_output_limit_mps2", n)
        clip_active = arr3(log, "stage1_position_applied_notch_event_clip_active", n).astype(bool)
        head_event_applied = arr3(log, "stage1_position_event_applied_acceleration_mps2", n)
        head_held_applied = arr3(log, "stage1_position_held_applied_acceleration_mps2", n)
        comp_total = arr3(log, "position_compensation_applied_acceleration_mps2", n)
        comp_force = arr3(log, "position_compensation_applied_force_N", n)
        held_force = arr3(log, "stage1_position_held_force_I_N", n)
        injected_force = arr3(log, "stage1_position_injected_force_I_N", n)
        nominal = arr3(log, "position_nominal_acceleration_mps2", n)
        commanded_force = arr3(log, "position_commanded_force_N", n)
        pcf_a_req = arr3(log, "stage1_position_pcf_a_req_mps2", n)
        b = np.asarray(ident["notch_b"][()], dtype=float).reshape(-1)
        a = np.asarray(ident["notch_a"][()], dtype=float).reshape(-1)
        initial_state = np.asarray(ident["notch_initial_state"][()], dtype=float)
        center_hz = scalar(log, "stage1_position_applied_notch_center_hz")
        quality = scalar(log, "stage1_position_applied_notch_q")
        enabled = scalar(log, "stage1_position_applied_notch_enabled")
        tau = scalar(ident, "position_delayed_prediction_tau_s")
        rho = scalar(ident, "position_delayed_prediction_rho")
        flags = [scalar(log, key) for key in (
            "stage1_position_replacement_enabled",
            "stage1_position_delayed_prediction_enabled",
            "stage1_position_pcf_coordination_enabled")]
        status_value = mat_text(log, "status")
        safety_stop = mat_text(log, "safety_stop_reason")

    require(n == 20000 and len(event_idx) == 1999 and
            np.array_equal(np.diff(event_idx), np.full(1998, 10)),
            f"unexpected Stage1 event cadence: {record['scene_id']}")
    require(abs(time[event_idx[0]] - EVENT_DT_S) < 1e-12 and
            np.max(np.abs(np.diff(time) - DT_S)) < 1e-12,
            f"event clock mismatch: {record['scene_id']}")
    require(enabled == 1 and abs(center_hz - 3.5) < 1e-12 and
            abs(quality - 1.0) < 1e-12 and tau == 1.0 and rho == 0.01 and flags == [1, 1, 1],
            f"notch setting or frozen C5 flags differ: {record['scene_id']}")
    require(np.allclose(initial_state, 0, atol=0, rtol=0),
            f"notch initial state is not zero: {record['scene_id']}")
    for name, values in (("input", notch_input), ("raw", output_raw),
                         ("applied", output_applied), ("limit", output_limit)):
        require(np.isfinite(values[event_idx]).all() and
                not np.isfinite(values[np.setdiff1d(np.arange(n), event_idx)]).any(),
                f"notch event-only sparsity/finite check failed for {name}: {record['scene_id']}")
    valid_idx = event_idx[inference_valid[event_idx]]
    invalid_idx = event_idx[~inference_valid[event_idx]]
    require(np.allclose(notch_input[valid_idx], head_event_applied[valid_idx], atol=1e-12, rtol=0) and
            np.max(np.abs(notch_input[invalid_idx])) <= 1e-12,
            f"notch input is not the current Stage1 head output: {record['scene_id']}")

    state = np.zeros((3, 4))
    expected_raw = np.zeros((len(event_idx), 3))
    for j, k in enumerate(event_idx):
        x = notch_input[k]
        y = b[0]*x + b[1]*state[:, 0] + b[2]*state[:, 1] - a[1]*state[:, 2] - a[2]*state[:, 3]
        expected_raw[j] = y
        state = np.column_stack((x, state[:, 0], y, state[:, 2]))
    recurrence_error = float(np.max(np.abs(expected_raw - output_raw[event_idx])))
    clipped = np.minimum(np.maximum(output_raw[event_idx], -output_limit[event_idx]), output_limit[event_idx])
    clip_error = float(np.max(np.abs(clipped - output_applied[event_idx])))
    clip_flag_error = int(np.count_nonzero(
        (np.abs(output_raw[event_idx] - output_applied[event_idx]) > 1e-12) != clip_active[event_idx]))
    expected_held = np.zeros((n, 3)); held = np.zeros(3)
    for k in range(n):
        if event[k]:
            held = output_applied[k].copy()
        expected_held[k] = held
    errors = {
        "notch_recurrence_raw_mps2": recurrence_error,
        "notch_output_clip_mps2": clip_error,
        "clip_flag_mismatch_count": clip_flag_error,
        "event_output_to_held_zoh_mps2": float(np.max(np.abs(expected_held - head_held_applied))),
        "held_to_total_compensation_mps2": float(np.max(np.abs(head_held_applied - comp_total))),
        "compensation_to_force_N": float(np.max(np.abs(comp_total*MASS_KG - comp_force))),
        "held_force_N": float(np.max(np.abs(comp_total*MASS_KG - held_force))),
        "injected_force_N": float(np.max(np.abs(comp_total*MASS_KG - injected_force))),
        "position_command_from_nominal_minus_comp_mps2": float(np.max(
            np.abs(commanded_force/MASS_KG - (nominal-comp_total)))),
        "PCF_a_req_equals_position_command_mps2": float(np.max(
            np.abs(pcf_a_req-commanded_force/MASS_KG))),
    }
    require(all(math.isfinite(errors[k]) for k in errors if k != "clip_flag_mismatch_count") and
            max(errors[k] for k in errors if k != "clip_flag_mismatch_count") <= 1e-9 and
            clip_flag_error == 0, f"notch/force/PCF path does not close: {record['scene_id']}")
    require(status_value == "STABLE" and not safety_stop,
            f"raw status/safety stop invalid: {record['scene_id']}")
    return {
        "scene_id": record["scene_id"],
        "event_count": int(len(event_idx)),
        "valid_head_event_count": int(len(valid_idx)),
        "pre_ready_zero_input_event_count": int(len(invalid_idx)),
        "first_event_index_zero_based": int(event_idx[0]),
        "first_event_time_s": float(time[event_idx[0]]),
        "last_event_index_zero_based": int(event_idx[-1]),
        "event_period_s": EVENT_DT_S,
        "filter": {"type": "causal_iirnotch", "center_hz": center_hz, "Q": quality,
                   "sample_rate_hz": 100, "b": b.tolist(), "a": a.tolist(),
                   "initial_state_zero": True, "position_tau_s": tau,
                   "position_rho": rho, "C5_flags_replacement_delay_pcf": flags},
        "clip_events_by_axis": np.count_nonzero(clip_active[event_idx], axis=0).astype(int).tolist(),
        "notch_input_abs_peak_mps2_by_axis": np.max(np.abs(notch_input[event_idx]), axis=0).tolist(),
        "notch_raw_output_abs_peak_mps2_by_axis": np.max(np.abs(output_raw[event_idx]), axis=0).tolist(),
        "notch_limit_peak_mps2_by_axis": np.max(output_limit[event_idx], axis=0).tolist(),
        "max_abs_output_to_limit_ratio": float(np.max(np.abs(output_raw[event_idx]) / output_limit[event_idx])),
        "path_reconstruction_max_abs_errors": errors,
    }


def validate_comparator(item: dict, scene: str, name: str) -> dict:
    raw = Path(item["raw_path"])
    require(raw.is_file() and sha(raw).lower() == item["raw_sha256"].lower(),
            f"{name} raw hash mismatch: {scene}")
    status_path_value = item.get("run_status_path") or item.get("status_path")
    status_hash = item.get("run_status_sha256") or item.get("status_sha256")
    require(status_path_value and status_hash, f"{name} status binding missing: {scene}")
    status_path = Path(status_path_value)
    require(status_path.is_file() and sha(status_path).lower() == status_hash.lower(),
            f"{name} status SHA mismatch: {scene}")
    status = readj(status_path)
    complete = status.get("state") == "COMPLETED" or status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT"
    stable = status.get("status_value", status.get("log_status", "STABLE")) == "STABLE"
    test_value = status.get("TEST_data_read", status.get("test_data_read",
                  status.get("TEST_accessed", status.get("TEST_read", False))))
    require(status.get("scene_id") == scene and complete and stable and
            status.get("safety_stop_reason", "") == "" and test_value is False,
            f"{name} status invalid: {scene}")
    require(Path(status.get("raw_path", "")).resolve() == raw.resolve() and
            status.get("raw_sha256", "").lower() == item["raw_sha256"].lower(),
            f"{name} status/raw identity mismatch: {scene}")
    return {"raw_path": str(raw), "raw_sha256": item["raw_sha256"],
            "run_status_path": str(status_path), "run_status_sha256": status_hash}


def score_metrics(scorer, path: Path, constants: dict) -> dict:
    metrics = scorer.score_raw(path, float(constants["gravity_mps2"]), float(constants["max_tilt_rad"]))
    return {
        "Q_mm": 1000.0 * float(metrics["Q_m"]),
        "task_SO3_mrad": 1000.0 * float(metrics["task_SO3_rad"]),
        "inner_SO3_mrad": 1000.0 * float(metrics["inner_SO3_rad"]),
        "safety": metrics["safety"],
    }


def main() -> None:
    require(not OUT_JSON.exists() and not OUT_MD.exists(), "refusing to overwrite an existing HF6 score")
    bindings = load_source_bindings()
    release = readj(RELEASE_PATH)
    baseline_doc = readj(BASELINE_SCORE)
    require(baseline_doc.get("status") == "COMPLETE_12_SCREEN" and
            baseline_doc.get("TEST_read") is False and baseline_doc.get("test_data_read") is False,
            "paired frozen baseline score is not a clean completed non-TEST score")
    metric_path = Path(baseline_doc["metric_source_path"])
    metric_sha = sha(metric_path)
    require(metric_sha.lower() == baseline_doc["metric_source_sha256"].lower(),
            "frozen FULL72 scorer SHA mismatch")
    spec = importlib.util.spec_from_file_location("frozen_full72_score_raw", metric_path)
    require(spec is not None and spec.loader is not None, "cannot import frozen score_raw")
    scorer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scorer
    spec.loader.exec_module(scorer)
    constants = baseline_doc["metric_constants"]
    require(abs(float(constants["gravity_mps2"]) - 9.8) < 1e-12 and
            abs(float(constants["max_tilt_rad"]) - math.pi/6) < 1e-12,
            "frozen metric constants differ from the paired score")

    candidate_paths = completed_candidate_statuses(EXPECTED_SCENES)
    baseline_scenes = {x["scene_id"]: x for x in baseline_doc["scene_results"]}
    require(set(EXPECTED_SCENES).issubset(baseline_scenes), "paired baseline score lacks HF6 scenes")

    per_scene = []
    candidate_source_rows = []
    for scene in EXPECTED_SCENES:
        record = validate_candidate_identity(scene, candidate_paths[scene], bindings)
        route = candidate_route_audit(record)
        method_records = {"Applied_Notch_3p5Hz_Q1": {**record, "route_audit": route}}
        score_row = {"Applied_Notch_3p5Hz_Q1": score_metrics(scorer, Path(record["raw_path"]), constants)}
        for baseline in BASELINES:
            item = baseline_scenes[scene]["methods"][baseline]
            bound = validate_comparator(item, scene, baseline)
            method_records[baseline] = bound
            score_row[baseline] = score_metrics(scorer, Path(bound["raw_path"]), constants)
        deltas = {
            name: {metric: score_row["Applied_Notch_3p5Hz_Q1"][metric] - score_row[name][metric]
                   for metric in ("Q_mm", "task_SO3_mrad", "inner_SO3_mrad")}
            for name in BASELINES
        }
        per_scene.append({"scene_id": scene, "methods": score_row,
                          "bindings": method_records, "notch_minus_comparators": deltas})
        candidate_source_rows.append({k: record[k] for k in (
            "scene_id", "release_kind", "release_generation_from_bound_release", "release_sha256",
            "source_lock_sha256", "raw_sha256", "run_start_sha256", "run_status_sha256")})

    macro = {}
    wins = {}
    method_names = ("Applied_Notch_3p5Hz_Q1",) + BASELINES
    for name in method_names:
        macro[name] = {
            metric: float(np.mean([row["methods"][name][metric] for row in per_scene]))
            for metric in ("Q_mm", "task_SO3_mrad", "inner_SO3_mrad")
        }
    for baseline in BASELINES:
        wins[baseline] = {}
        for metric in ("Q_mm", "task_SO3_mrad", "inner_SO3_mrad"):
            diff = [row["methods"]["Applied_Notch_3p5Hz_Q1"][metric] - row["methods"][baseline][metric]
                    for row in per_scene]
            wins[baseline][metric] = {
                "wins": int(sum(x < -WIN_TOL for x in diff)),
                "ties": int(sum(abs(x) <= WIN_TOL for x in diff)),
                "losses": int(sum(x > WIN_TOL for x in diff)),
            }
    macro_delta = {
        baseline: {metric: macro["Applied_Notch_3p5Hz_Q1"][metric] - macro[baseline][metric]
                   for metric in ("Q_mm", "task_SO3_mrad", "inner_SO3_mrad")}
        for baseline in BASELINES
    }
    release_hashes = sorted(set(row["release_sha256"] for row in candidate_source_rows))
    lock_hashes = sorted(set(row["source_lock_sha256"] for row in candidate_source_rows))
    result = {
        "schema": "DL1018_APPLIED_NOTCH_HF6_FROZEN_SCORE_V2",
        "status": "COMPLETE_HF6_DEVELOPMENT_SCREEN",
        "supersedes": "NOTCH_HF6_FROZEN_SCORE_v1.json (provisional path audit had a sparse-event row-indexing error; scores were unchanged, corrected route closure is reported here)",
        "scope": "Six fixed HF6 scenes rescored with the frozen FULL72 score_raw. Paired methods are separate runs on the same scene; this is a development screen, not independent validation.",
        "independent_validation_claimed": False,
        "fresh_holdout_required_for_winner": True,
        "Plant_calls_started_by_scorer": 0,
        "training_runs_by_scorer": 0,
        "TEST_read_by_scorer": False,
        "inertia_reconstruction_by_scorer": False,
        "authorized_scene_ids": EXPECTED_SCENES,
        "completed_scene_count": len(per_scene),
        "release_and_source_binding": {
            **bindings,
            "candidate_release_hashes_seen_in_runs": release_hashes,
            "candidate_source_lock_hashes_seen_in_runs": lock_hashes,
            "candidate_run_source_bindings": candidate_source_rows,
        },
        "frozen_baseline_score_path": str(BASELINE_SCORE),
        "frozen_baseline_score_sha256": sha(BASELINE_SCORE),
        "frozen_metric_path": str(metric_path),
        "frozen_metric_sha256": metric_sha,
        "scoring_script_path": str(Path(__file__).resolve()),
        "scoring_script_sha256": sha(Path(__file__).resolve()),
        "metric_constants": constants,
        "method_ids": {"candidate": "Applied_Notch_3p5Hz_Q1", "comparators": list(BASELINES)},
        "macro_mean": macro,
        "candidate_minus_comparator_macro": macro_delta,
        "candidate_scene_wins_ties_losses": wins,
        "scene_results": per_scene,
        "interpretation": [
            "The pilot uses the archived generation-1 RELEASE and source lock; the remaining five scenes use the current generation-2 RELEASE and source lock. They are not represented as one identical release hash.",
            "The frozen raw scorer and its constants are bound to the prior completed baseline score. B, C5, and Parent_Cosine_GRU raw and status hashes are validated scene by scene.",
            "The logged causal notch recurrence, output clip, held compensation, force path, position command, and PCF acceleration request are reconstructed from each raw run. Clip counts/limits and scorer safety counters are included per scene.",
            "The HF6 cohort is a development screen only; no independent winner claim is made, and a fresh grouped holdout is required before selection.",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_md(result)
    print(json.dumps({"status": result["status"], "json": str(OUT_JSON), "markdown": str(OUT_MD)}, indent=2))


def write_md(result: dict) -> None:
    lines = [
        "# Applied notch HF6 frozen-score audit", "",
        "Six fixed scenes rescored with the frozen FULL72 `score_raw`. This is a development screen, not independent validation. The scorer made no Plant calls and did not train, read TEST, or reconstruct inertia.", "",
        "## Macro mean", "", "| Method | Q (mm) | task SO(3) (mrad) | inner SO(3) (mrad) |", "|---|---:|---:|---:|"]
    for name, values in result["macro_mean"].items():
        lines.append(f"| {name} | {values['Q_mm']:.3f} | {values['task_SO3_mrad']:.3f} | {values['inner_SO3_mrad']:.3f} |")
    lines.extend(["", "Candidate minus comparator macro mean (negative means lower error):", "",
                  "| Comparator | ΔQ (mm) | Δtask (mrad) | Δinner (mrad) |", "|---|---:|---:|---:|"])
    for name, values in result["candidate_minus_comparator_macro"].items():
        lines.append(f"| {name} | {values['Q_mm']:+.3f} | {values['task_SO3_mrad']:+.3f} | {values['inner_SO3_mrad']:+.3f} |")
    lines.extend(["", "## Per-scene frozen scores", "",
        "| Scene | Method | Q (mm) | task (mrad) | inner (mrad) | clip events X/Y/Z | max raw/limit |", "|---|---|---:|---:|---:|---:|---:|"])
    for row in result["scene_results"]:
        for method, metrics in row["methods"].items():
            route = row["bindings"][method].get("route_audit")
            if route is None:
                clip_text, ratio_text = "—", "—"
            else:
                clips = route["clip_events_by_axis"]
                clip_text = f"{clips[0]}/{clips[1]}/{clips[2]}"
                ratio_text = f"{route['max_abs_output_to_limit_ratio']:.4f}"
            lines.append(f"| {row['scene_id']} | {method} | {metrics['Q_mm']:.3f} | {metrics['task_SO3_mrad']:.3f} | {metrics['inner_SO3_mrad']:.3f} | {clip_text} | {ratio_text} |")
    lines.extend(["", "## Release and source binding", "",
        f"Pilot snapshot RELEASE SHA-256 `{result['release_and_source_binding']['pilot_release_snapshot_sha256']}`; pilot source-lock snapshot SHA-256 `{result['release_and_source_binding']['pilot_source_lock_snapshot_sha256']}`.",
        f"Current continuation RELEASE SHA-256 `{result['release_and_source_binding']['current_release_sha256']}`; source lock SHA-256 `{result['release_and_source_binding']['current_source_lock_sha256']}`. Candidate runs used release hashes `{', '.join(result['release_and_source_binding']['candidate_release_hashes_seen_in_runs'])}` and source-lock hashes `{', '.join(result['release_and_source_binding']['candidate_source_lock_hashes_seen_in_runs'])}`.",
        f"Verified {result['release_and_source_binding']['pilot_snapshot_source_files_verified']} archived pilot source files and {result['release_and_source_binding']['current_source_lock_files_verified']} current locked source files. The pilot and continuation are intentionally reported as different release generations.", "",
        "## Safety and interpretation", "",
        "Per-scene safety counters come from the frozen scorer. Candidate event-level notch clipping and path-reconstruction errors are in the JSON next to each scene; em dashes in comparator clipping columns mean those candidate-specific route logs do not apply to baseline runs. B, C5, and parent GRU comparators are separate runs on the same scene, not paired-state trajectories.",
        "This fixed HF6 set is a development screen. A fresh grouped holdout is required before selecting a winner.", "",
        "Reproduce after all six candidate statuses are complete: `python experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/score_notch_hf6_v1.py`.", ""])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
