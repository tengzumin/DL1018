#!/usr/bin/env python3
"""Read-only 12-scene scorer; writes reports only after all locked inputs pass."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "frozen_inputs.json"
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
IDS = [row["scene_id"] for row in LOCK["scenes"]]
TOL_M = float(LOCK["analysis"]["paired_raw_tolerance_m"])
WEIGHT_DELTA_TOL = float(LOCK["run"]["weight_delta_threshold_unitless"])
SIGNAL_TOL_MPS = float(LOCK["run"]["signal_tolerance_mps"])
EXPECTED_SETUP = {entry["name"]: entry["sha256"].lower() for entry in LOCK["setupFiles"]}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stable_file_identity(path: Path) -> tuple[str, int, int]:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    identity = (digest, after.st_size, after.st_mtime_ns)
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError(f"File changed while hashing: {path}")
    return identity


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def require_close(actual: float, expected: float, label: str) -> None:
    if not np.isfinite(actual) or not np.isfinite(expected) or abs(actual - expected) > TOL_M:
        raise RuntimeError(f"{label} differs from frozen rescore by more than {TOL_M:g} m")


def h5_log_array(log: h5py.Group, name: str) -> np.ndarray:
    if name not in log:
        raise RuntimeError(f"Required raw field is missing: log/{name}")
    value = np.asarray(raw_scan.arr(log, name))
    if value.size == 0:
        raise RuntimeError(f"Required raw field is empty: log/{name}")
    return value


def matlab_text(value: np.ndarray) -> str:
    if isinstance(value, str):
        return value.strip()
    a = np.asarray(value)
    if a.dtype.kind in "SU":
        return "".join(str(x) for x in a.reshape(-1)).strip()
    return "".join(chr(int(x)) for x in a.reshape(-1) if int(x) != 0).strip()


def time_rows(value: np.ndarray, n: int, label: str) -> np.ndarray:
    a = np.asarray(value)
    if a.ndim == 0:
        raise RuntimeError(f"{label} is scalar, expected one value per transition")
    if a.ndim == 1:
        if a.size != n:
            raise RuntimeError(f"{label} length {a.size}, expected {n}")
        return a.reshape(n, 1)
    axes = [axis for axis, size in enumerate(a.shape) if size == n]
    if len(axes) != 1:
        raise RuntimeError(f"{label} has no unique {n}-sample time axis: {a.shape}")
    return np.moveaxis(a, axes[0], 0)


def reference_position(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as f:
        if "log/reference/position" not in f:
            raise RuntimeError(f"Missing log/reference/position input: {path}")
        return np.asarray(f["log/reference/position"], dtype=np.float64)


def source_identity_matches(actual: object, expected: list[dict[str, str]], label: str) -> bool:
    rows = actual if isinstance(actual, list) else [actual]
    if not all(isinstance(row, dict) for row in rows):
        return False
    actual_rows = sorted((str(r.get("name") or Path(r["path"]).stem), str(r.get("path", "")).lower(),
                          str(r.get("sha256", "")).lower()) for r in rows)
    expected_rows = sorted((str(r.get("name") or Path(r["path"]).stem), str(r["path"]).lower(),
                            str(r["sha256"]).lower()) for r in expected)
    if actual_rows != expected_rows:
        raise RuntimeError(f"{label} identity differs from frozen source lock")
    return True


def verify_status_identity(status: dict[str, object], scene_id: str,
                           on_path: Path, on_sha: str, b_path: Path, b_sha: str) -> None:
    normalizer = LOCK["normalizer"]
    expected = {
        "scene_id": scene_id,
        "frozen_inputs_sha256": sha256(LOCK_PATH),
        "model_mat_sha256": LOCK["model"]["mat_sha256"],
        "model_binding_sha256": LOCK["model_binding"]["sha256"],
        "normalizer_npz_sha256": normalizer["npz_file_sha256"],
        "normalizer_report_sha256": normalizer["train_only_report_sha256"],
        "normalizer_arrays_identity_sha256": normalizer["actual_runner_arrays_identity_sha256"],
        "W0_output_W_sha256": LOCK["model"]["w0_output_W_double_f_order_sha256"],
        "scene_payload_identity_csv_sha256": LOCK["scene_payload_identity"]["sha256"],
        "on_raw_sha256": on_sha,
        "b_raw_sha256": b_sha,
    }
    for key, value in expected.items():
        if status.get(key) != value:
            raise RuntimeError(f"OFF run_status identity mismatch for {scene_id}: {key}")
    if status.get("status") != "STABLE" or status.get("pcf_enabled") is not False:
        raise RuntimeError(f"OFF run status/PCF contract is invalid: {scene_id}")
    if status.get("update_enabled") is not True or status.get("head_enabled") is not True:
        raise RuntimeError(f"OFF run did not retain the online FEATURE Head: {scene_id}")
    if int(status.get("last_transition", -1)) != 20000:
        raise RuntimeError(f"OFF run last_transition is incomplete: {scene_id}")
    if (int(status.get("update_event_count", 0)) <= 0
            or float(status.get("max_abs_event_weight_delta_unitless", 0.0)) <= WEIGHT_DELTA_TOL
            or float(status.get("weight_delta_threshold_unitless", np.nan)) != WEIGHT_DELTA_TOL
            or float(status.get("max_abs_eta_before_mps", np.inf)) > SIGNAL_TOL_MPS
            or float(status.get("max_abs_eta_after_mps", np.inf)) > SIGNAL_TOL_MPS
            or float(status.get("max_abs_surface_clip_error_mps", np.inf)) > SIGNAL_TOL_MPS):
        raise RuntimeError(f"OFF online-update/eta/signal invariant failed: {scene_id}")
    identity = status.get("input_identity")
    if not isinstance(identity, dict):
        raise RuntimeError(f"OFF status has no input_identity object: {scene_id}")
    input_expected = {
        "scene_id": scene_id,
        "on_raw_path": str(on_path),
        "on_raw_sha256": on_sha,
        "b_raw_path": str(b_path),
        "b_raw_sha256": b_sha,
        "scene_payload_identity_csv_sha256": LOCK["scene_payload_identity"]["sha256"],
        "model_mat_sha256": LOCK["model"]["mat_sha256"],
        "model_binding_sha256": LOCK["model_binding"]["sha256"],
        "normalizer_npz_sha256": normalizer["npz_file_sha256"],
        "normalizer_report_sha256": normalizer["train_only_report_sha256"],
        "normalizer_arrays_identity_sha256": normalizer["actual_runner_arrays_identity_sha256"],
        "W0_output_W_sha256": LOCK["model"]["w0_output_W_double_f_order_sha256"],
    }
    for key, value in input_expected.items():
        if identity.get(key) != value:
            raise RuntimeError(f"OFF input_identity mismatch for {scene_id}: {key}")
    source_identity_matches(status.get("plant_source_identity"), LOCK["plantFiles"], "Plant")
    source_identity_matches(status.get("runtime_source_identity"), LOCK["runtimeFiles"], "runtime")
    source_identity_matches(identity.get("plant_source_identity"), LOCK["plantFiles"], "input Plant")
    source_identity_matches(identity.get("runtime_source_identity"), LOCK["runtimeFiles"], "input runtime")


def scan_raw(path: Path, role: str, expected_sha: str) -> tuple[dict[str, object], np.ndarray]:
    if any(re.search(r"(^|_)TEST($|_)", part, re.I) for part in path.parts):
        raise RuntimeError(f"Refusing sealed TEST path: {path}")
    before = stable_file_identity(path)
    if before[0] != expected_sha.lower():
        raise RuntimeError(f"Frozen {role} raw SHA differs before scan: {path}")
    scanned = raw_scan.score(path)
    after = stable_file_identity(path)
    if before != after or scanned.get("status") != "scored" or not scanned.get("stable_read"):
        raise RuntimeError(f"{role} raw changed or scanner read was unstable: {path}")
    if (scanned.get("transitions") != 20000 or scanned.get("complete") is not True
            or scanned.get("finite") is not True or scanned.get("time_start") != 0.0
            or scanned.get("time_end") != 19.999 or scanned.get("N_0_20") != 20000):
        raise RuntimeError(f"{role} raw is incomplete/nonfinite or has wrong timebase: {path}")

    with h5py.File(path, "r") as f:
        if "log" not in f:
            raise RuntimeError(f"{role} raw lacks log group: {path}")
        log = f["log"]
        transition_time = h5_log_array(log, "transition_time").reshape(-1)
        state = h5_log_array(log, "state")
        reference = h5_log_array(log, "reference/position")
        controller = h5_log_array(log, "controller_call_time_s").reshape(-1)
        saturated = time_rows(h5_log_array(log, "motor_saturated"), 20000, "motor_saturated")
        clipped = time_rows(h5_log_array(log, "generalized_clipped"), 20000, "generalized_clipped")
        status = matlab_text(h5_log_array(log, "status"))
        last_transition = float(np.asarray(h5_log_array(log, "last_transition")).reshape(-1)[0])
        safety_stop_reason = matlab_text(h5_log_array(log, "safety_stop_reason"))
    after_array_read = stable_file_identity(path)
    if before != after_array_read:
        raise RuntimeError(f"{role} raw changed during direct HDF5 array read: {path}")
    if (transition_time.size != 20000 or not np.isfinite(transition_time).all()
            or transition_time[0] != 0.0 or transition_time[-1] != 19.999
            or np.any(np.diff(transition_time) <= 0)):
        raise RuntimeError(f"{role} transition_time array is incomplete/invalid: {path}")
    if state.ndim != 2 or state.shape[0] != 20001 or state.shape[1] < 9:
        raise RuntimeError(f"{role} state array does not contain all 20,001 samples: {path}")
    if reference.shape != (20001, 3):
        raise RuntimeError(f"{role} reference position shape is incomplete: {path} {reference.shape}")
    if not all(np.isfinite(a).all() for a in (state, reference, controller, saturated, clipped)):
        raise RuntimeError(f"{role} required raw arrays contain NaN/Inf: {path}")
    if controller.size != 20000 or np.any(controller < 0):
        raise RuntimeError(f"controller_call_time_s missing/invalid for {role}: {path}")
    if last_transition != 20000 or status != "STABLE" or safety_stop_reason:
        safe = False
    else:
        safe = True
    methods = {
        "status": status, "last_transition": int(last_transition),
        "finite": True, "complete": True, "safe": safe,
        "safety_stop_reason": safety_stop_reason or "",
        "controller_call_time_mean_s": float(np.mean(controller)),
        "controller_call_time_p95_s": float(np.quantile(controller, 0.95)),
        "controller_call_time_max_s": float(np.max(controller)),
        "motor_saturated_fraction": float(np.mean(np.any(saturated != 0, axis=1))),
        "generalized_clipped_fraction": float(np.mean(np.any(clipped != 0, axis=1))),
        "raw_integrity_status": "PASS_SHA_SIZE_MTIME_AND_ARRAYS",
        "identity_status": "LOCKED_RAW_AND_RESCORING_TABLE",
    }
    if not safe:
        raise RuntimeError(f"{role} safety/status marker failed: {path}; status={status}, last={last_transition}, reason={safety_stop_reason!r}")
    return {**scanned, **methods}, reference


def check_rescore_row(row: dict[str, str], role: str, raw_path: Path,
                      raw_sha: str, scan: dict[str, object]) -> None:
    if role == "ON_CANDIDATE":
        checks = (row.get("raw_path") == str(raw_path),
                  row.get("raw_sha256_expected", "").lower() == raw_sha,
                  row.get("raw_sha256_before", "").lower() == raw_sha,
                  row.get("raw_sha256_after", "").lower() == raw_sha,
                  row.get("raw_index_path") == LOCK["raw_index"]["path"],
                  row.get("raw_index_sha256", "").lower() == LOCK["raw_index"]["sha256"].lower(),
                  row.get("rescore_matches_pair_with_1e-12_m_tolerance", "").lower() == "true")
        prefix = "rmse_"
        q_key = "independent_rescore_q_m"
    else:
        checks = (row.get("resolved_raw_path") == str(raw_path),
                  row.get("resolved_raw_sha256_expected", "").lower() == raw_sha,
                  row.get("raw_sha256_before", "").lower() == raw_sha,
                  row.get("raw_sha256_after", "").lower() == raw_sha,
                  row.get("rescore_matches_pair_with_1e-12_m_tolerance", "").lower() == "true",
                  row.get("raw_scan_sha256", "").lower() == LOCK["scoring_helper"]["sha256"].lower())
        prefix = "rmse_"
        q_key = "independent_rescore_q_m"
    if not all(checks):
        raise RuntimeError(f"Locked {role} rescore row/raw identity mismatch for {row.get('scene_id')}")
    require_close(float(scan["Q_0_20"]), float(row[q_key]), f"{role} independently rescored Q")
    for axis in "xyz":
        for phase in ("0_20", "0_5", "5_20"):
            require_close(float(scan[f"RMSE_{axis}_{phase}"]),
                          float(row[f"{prefix}{axis.lower()}_{phase}_m"]),
                          f"{role} RMSE {axis}/{phase}")


def outcome(delta: float) -> str:
    if delta < -TOL_M:
        return "WIN"
    if delta > TOL_M:
        return "LOSS"
    return "TIE"


def flatten_method(record: dict[str, object], prefix: str, metrics: dict[str, object]) -> None:
    mapping = {
        "q_0_20_m": "Q_0_20",
        "peak_m": "peak",
        "p95_m": "p95",
        "motor_saturated_fraction": "motor_saturated_fraction",
        "generalized_clipped_fraction": "generalized_clipped_fraction",
        "status": "status",
        "last_transition": "last_transition",
        "finite": "finite",
        "complete": "complete",
        "safe": "safe",
        "safety_stop_reason": "safety_stop_reason",
        "raw_integrity_status": "raw_integrity_status",
        "identity_status": "identity_status",
        "controller_call_time_mean_s": "controller_call_time_mean_s",
        "controller_call_time_p95_s": "controller_call_time_p95_s",
        "controller_call_time_max_s": "controller_call_time_max_s",
    }
    for out_key, in_key in mapping.items():
        record[f"{prefix}_{out_key}"] = metrics[in_key]
    for axis in "xyz":
        for phase in ("0_20", "0_5", "5_20"):
            record[f"rmse_{axis}_{prefix}_{phase}_m"] = float(metrics[f"RMSE_{axis}_{phase}"])


def mean(rows: list[dict[str, object]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def group_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "n": len(rows),
        "mean_q_b_m": mean(rows, "b_q_0_20_m"),
        "mean_q_on_m": mean(rows, "on_q_0_20_m"),
        "mean_q_off_m": mean(rows, "off_q_0_20_m"),
        "mean_q_off_minus_on_m": mean(rows, "delta_q_off_minus_on_m"),
        "mean_q_off_minus_b_m": mean(rows, "delta_q_off_minus_b_m"),
        "q_outcomes_off_vs_on": {name: sum(r["q_outcome_off_vs_on"] == name for r in rows)
                                 for name in ("WIN", "TIE", "LOSS")},
        "q_outcomes_off_vs_b": {name: sum(r["q_outcome_off_vs_b"] == name for r in rows)
                                for name in ("WIN", "TIE", "LOSS")},
        "mean_rmse_z_b_0_20_m": mean(rows, "rmse_z_b_0_20_m"),
        "mean_rmse_z_on_0_20_m": mean(rows, "rmse_z_on_0_20_m"),
        "mean_rmse_z_off_0_20_m": mean(rows, "rmse_z_off_0_20_m"),
        "mean_rmse_z_off_minus_on_0_20_m": mean(rows, "delta_rmse_z_off_minus_on_0_20_m"),
        "mean_rmse_z_off_minus_b_0_20_m": mean(rows, "delta_rmse_z_off_minus_b_0_20_m"),
        "z_outcomes_off_vs_on": {name: sum(r["z_outcome_off_vs_on"] == name for r in rows)
                                  for name in ("WIN", "TIE", "LOSS")},
        "z_outcomes_off_vs_b": {name: sum(r["z_outcome_off_vs_b"] == name for r in rows)
                                 for name in ("WIN", "TIE", "LOSS")},
    }


# Bind the scorer, scanner, lock, taskbook, and all setup code before consuming input.
for entry in LOCK["setupFiles"]:
    path = Path(entry["path"])
    if sha256(path) != entry["sha256"].lower():
        raise RuntimeError(f"Locked setup SHA changed: {entry['name']}")
if sha256(HERE / "TASKBOOK_ZH.md") != LOCK["taskbook"]["sha256"].lower():
    raise RuntimeError("Frozen taskbook SHA changed")
manifest_path = Path(LOCK["reuse_manifest"]["path"])
if sha256(manifest_path) != LOCK["reuse_manifest"]["sha256"].lower():
    raise RuntimeError("Frozen reuse manifest SHA-256 changed")
scene_identity_path = Path(LOCK["scene_payload_identity"]["path"])
scene_identity = stable_file_identity(scene_identity_path)
if scene_identity[0] != LOCK["scene_payload_identity"]["sha256"].lower():
    raise RuntimeError("Frozen scene-payload identity CSV SHA-256 changed")
scene_identity_rows = {row["scene_id"]: row for row in csv_rows(scene_identity_path)}
if len(scene_identity_rows) != 12 or set(scene_identity_rows) != set(IDS):
    raise RuntimeError("Scene-payload identity CSV is not the exact frozen twelve-scene VAL set")
upstream = LOCK["upstream_round1"]
for key, path_key in (("lock_sha256", "lock_path"), ("results_sha256", "results_path"),
                      ("summary_sha256", "summary_path")):
    if sha256(Path(upstream[path_key])) != upstream[key].lower():
        raise RuntimeError(f"Frozen Round 1 upstream {key} changed")
upstream_lock = json.loads(Path(upstream["lock_path"]).read_text(encoding="utf-8"))
if (upstream_lock["model"]["mat_sha256"] != LOCK["model"]["mat_sha256"]
        or upstream_lock["model_binding"]["sha256"] != LOCK["model_binding"]["sha256"]
        or upstream_lock["normalizer"]["npz_file_sha256"] != LOCK["normalizer"]["npz_file_sha256"]
        or upstream_lock["normalizer"]["actual_runner_arrays_identity_sha256"]
        != LOCK["normalizer"]["actual_runner_arrays_identity_sha256"]):
    raise RuntimeError("Round 1 and Round 2 model/normalizer contracts differ")
for section in ("plantFiles", "runtimeFiles"):
    old = sorted((str(row.get("name") or Path(row["path"]).stem), str(row["path"]).lower(), str(row["sha256"]).lower())
                 for row in upstream_lock[section])
    new = sorted((str(row.get("name") or Path(row["path"]).stem), str(row["path"]).lower(), str(row["sha256"]).lower())
                 for row in LOCK[section])
    if old != new:
        raise RuntimeError(f"Round 1 and Round 2 {section} identities differ")
rescore_identities: dict[str, tuple[str, int, int]] = {}
rescore_rows: dict[str, list[dict[str, str]]] = {}
for item in LOCK["rescores"]:
    path = Path(item["path"])
    identity = stable_file_identity(path)
    if identity[0] != item["sha256"].lower():
        raise RuntimeError(f"Locked {item['role']} rescore CSV SHA changed")
    rescore_identities[item["role"]] = identity
    rescore_rows[item["role"]] = csv_rows(path)
scanner = LOCK["scoring_helper"]
scanner_path = Path(scanner["path"])
if sha256(scanner_path) != scanner["sha256"].lower():
    raise RuntimeError("Reviewed raw_scan.py SHA-256 changed")
sys.path.insert(0, str(scanner_path.parent))
spec = importlib.util.spec_from_file_location("frozen_round1_raw_scan", scanner_path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot import the reviewed read-only raw scanner")
raw_scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = raw_scan
spec.loader.exec_module(raw_scan)

manifest = csv_rows(manifest_path)
if len(manifest) != 24 or {row["split"] for row in manifest} != {"VAL"}:
    raise RuntimeError("Expected the exact 24-row VAL-only reuse manifest")
rows_by_key = {(row["scene_id"], row["role"]): row for row in manifest}
if len(rows_by_key) != 24 or {key[0] for key in rows_by_key} != set(IDS):
    raise RuntimeError("Duplicate or unexpected scene/role in frozen manifest")
score_by_key: dict[tuple[str, str], dict[str, str]] = {}
role_map = {"ON_CANDIDATE": "ON_CANDIDATE", "B_BASELINE": "B_BASELINE"}
for role, csv_role in role_map.items():
    rows = rescore_rows[csv_role]
    for row in rows:
        if row.get("scene_id") in IDS:
            if row.get("split") != "VAL":
                raise RuntimeError(f"Non-VAL row found in locked {role} rescore")
            key = (row["scene_id"], role)
            if key in score_by_key:
                raise RuntimeError(f"Duplicate {role} rescore row: {key}")
            score_by_key[key] = row
if len(score_by_key) != 24:
    raise RuntimeError("Locked ON/B rescore tables do not contain all 12 frozen VAL scenes")

records: list[dict[str, object]] = []
for scene_id in IDS:
    scene_lock = next(item for item in LOCK["scenes"] if item["scene_id"] == scene_id)
    scene_evidence = scene_identity_rows[scene_id]
    if (scene_evidence.get("status") != "IDENTICAL"
            or int(scene_evidence.get("physical_field_count", -1)) != 14
            or int(scene_evidence.get("time_samples", -1)) != 20001
            or float(scene_evidence.get("max_abs_physical_scene_diff", "nan")) != 0.0):
        raise RuntimeError(f"Frozen 14-field scene identity evidence failed: {scene_id}")
    per_method: dict[str, dict[str, object]] = {}
    ref_arrays: list[np.ndarray] = []
    path_by_role: dict[str, Path] = {}
    sha_by_role: dict[str, str] = {}
    for role, prefix in (("B_BASELINE", "b"), ("ON_CANDIDATE", "on")):
        row = rows_by_key[(scene_id, role)]
        path = Path(row["raw_path"])
        raw_sha = row["raw_sha256"].lower()
        if row["split"] != "VAL":
            raise RuntimeError(f"Non-VAL raw in manifest: {scene_id} {role}")
        scan, ref = scan_raw(path, role, raw_sha)
        check_rescore_row(score_by_key[(scene_id, role)], role, path, raw_sha, scan)
        scan["identity_status"] = "R1_LOCKED_RAW_RESCORE_AND_SCENE_INPUT_IDENTITY"
        expected_evidence_sha = scene_evidence["on_raw_sha256" if role == "ON_CANDIDATE" else "b_raw_sha256"]
        if expected_evidence_sha.lower() != raw_sha:
            raise RuntimeError(f"Scene evidence raw SHA mismatch: {scene_id} {role}")
        per_method[prefix] = scan
        ref_arrays.append(ref)
        path_by_role[role] = path
        sha_by_role[role] = raw_sha

    off_dir = HERE / "runs" / scene_id / "attempt_01"
    off_path = off_dir / "raw_run.mat"
    status_path = off_dir / "run_status.json"
    run_start_path = off_dir / "run_start.mat"
    if not off_path.is_file() or not status_path.is_file() or not run_start_path.is_file():
        raise RuntimeError(f"Missing OFF attempt/raw/status/run_start for {scene_id}")
    status_before = stable_file_identity(status_path)
    run_status = json.loads(status_path.read_text(encoding="utf-8"))
    if stable_file_identity(status_path) != status_before:
        raise RuntimeError(f"run_status changed while reading: {scene_id}")
    on_path = path_by_role["ON_CANDIDATE"]
    b_path = path_by_role["B_BASELINE"]
    verify_status_identity(run_status, scene_id, on_path, sha_by_role["ON_CANDIDATE"],
                           b_path, sha_by_role["B_BASELINE"])
    run_start_identity = stable_file_identity(run_start_path)
    if run_start_identity[0] != str(run_status.get("run_start_sha256", "")).lower():
        raise RuntimeError(f"run_start SHA does not match status for {scene_id}")
    off_sha = str(run_status.get("raw_sha256", "")).lower()
    off_scan, off_ref = scan_raw(off_path, "OFF", off_sha)
    episode_runtime_s = float(run_status.get("episode_runtime_seconds", np.nan))
    attempt_execution_raw_s = float(run_status.get("attempt_execution_and_raw_persistence_seconds", np.nan))
    if not np.isfinite(episode_runtime_s) or episode_runtime_s <= 0:
        raise RuntimeError(f"OFF run_episode-only timing is absent/invalid for {scene_id}")
    if not np.isfinite(attempt_execution_raw_s) or attempt_execution_raw_s <= 0:
        raise RuntimeError(f"OFF attempt execution/raw-persistence timing is absent/invalid for {scene_id}")
    per_method["off"] = off_scan
    ref_arrays.append(off_ref)
    path_by_role["OFF"] = off_path
    sha_by_role["OFF"] = off_sha

    # This checks the logged reference input array only; it never compares state trajectories.
    if any(ref.shape != ref_arrays[0].shape or not np.array_equal(ref, ref_arrays[0])
           for ref in ref_arrays[1:]):
        raise RuntimeError(f"ON/B/OFF reference-position inputs are not elementwise identical: {scene_id}")

    row_out: dict[str, object] = {
        "scene_id": scene_id, "split": "VAL", "task": scene_lock["task"], "band": scene_lock["band"],
        "b_raw_sha256": sha_by_role["B_BASELINE"],
        "on_raw_sha256": sha_by_role["ON_CANDIDATE"],
        "off_raw_sha256": sha_by_role["OFF"],
        "reference_position_input_elementwise_equal": True,
        "off_candidate_episode_runtime_s": episode_runtime_s,
        "off_candidate_attempt_execution_and_raw_persistence_s": attempt_execution_raw_s,
    }
    for role in ("b", "on", "off"):
        flatten_method(row_out, role, per_method[role])
    row_out["delta_q_off_minus_on_m"] = float(row_out["off_q_0_20_m"]) - float(row_out["on_q_0_20_m"])
    row_out["delta_q_off_minus_b_m"] = float(row_out["off_q_0_20_m"]) - float(row_out["b_q_0_20_m"])
    row_out["q_outcome_off_vs_on"] = outcome(float(row_out["delta_q_off_minus_on_m"]))
    row_out["q_outcome_off_vs_b"] = outcome(float(row_out["delta_q_off_minus_b_m"]))
    for phase in ("0_20", "0_5", "5_20"):
        row_out[f"delta_rmse_z_off_minus_on_{phase}_m"] = (
            float(row_out[f"rmse_z_off_{phase}_m"]) - float(row_out[f"rmse_z_on_{phase}_m"]))
        row_out[f"delta_rmse_z_off_minus_b_{phase}_m"] = (
            float(row_out[f"rmse_z_off_{phase}_m"]) - float(row_out[f"rmse_z_b_{phase}_m"]))
    row_out["z_outcome_off_vs_on"] = outcome(row_out["delta_rmse_z_off_minus_on_0_20_m"])
    row_out["z_outcome_off_vs_b"] = outcome(row_out["delta_rmse_z_off_minus_b_0_20_m"])
    records.append(row_out)

# Detect any changes to the frozen rescore tables after they were consumed.
for item in LOCK["rescores"]:
    path = Path(item["path"])
    if stable_file_identity(path) != rescore_identities[item["role"]]:
        raise RuntimeError(f"Locked {item['role']} rescore CSV changed while scoring")
if stable_file_identity(scene_identity_path) != scene_identity:
    raise RuntimeError("Frozen scene-payload identity CSV changed while scoring")
if len(records) != 12 or not all(r["off_safe"] and r["b_safe"] and r["on_safe"] for r in records):
    raise RuntimeError("All 12 B/ON/OFF runs must be safe, complete, finite and identity-verified")

groups = {
    "W09_W11": [r for r in records if r["band"] == "W09_W11"],
    "W12_W14": [r for r in records if r["band"] == "W12_W14"],
    "W15": [r for r in records if r["band"] == "W15"],
    "W00_W08": [r for r in records if r["band"] == "W00_W08"],
}
if any(len(rows) != 3 for rows in groups.values()):
    raise RuntimeError("Each frozen band group must contain exactly three scenes")
hf = groups["W09_W11"] + groups["W12_W14"]
hf_q_improvement_vs_on = mean(hf, "on_q_0_20_m") - mean(hf, "off_q_0_20_m")
hf_q_off_minus_b = mean(hf, "off_q_0_20_m") - mean(hf, "b_q_0_20_m")
hf_z_wins = sum(row["z_outcome_off_vs_on"] == "WIN" for row in hf)
low_q_off_minus_b = mean(groups["W00_W08"], "off_q_0_20_m") - mean(groups["W00_W08"], "b_q_0_20_m")
w15_q_off_minus_b = mean(groups["W15"], "off_q_0_20_m") - mean(groups["W15"], "b_q_0_20_m")
macro_q_improvement_vs_b = mean(records, "b_q_0_20_m") - mean(records, "off_q_0_20_m")
gate = (hf_q_improvement_vs_on > TOL_M and hf_q_off_minus_b <= TOL_M and hf_z_wins >= 4
        and low_q_off_minus_b <= TOL_M and w15_q_off_minus_b <= TOL_M
        and macro_q_improvement_vs_b > TOL_M and len(records) == 12)
candidate_episode = [float(r["off_candidate_episode_runtime_s"]) for r in records]
candidate_attempt = [float(r["off_candidate_attempt_execution_and_raw_persistence_s"]) for r in records]
summary = {
    "schema": "ROUND2_PCF_SCREEN_RESULTS_V2",
    "status": "COMPLETE_12_SCENE_SCREEN",
    "safe_complete_finite_identity_verified_runs": {"B": 12, "PCF_on": 12, "PCF_off": 12},
    "metric_rows": len(records),
    "delta_direction": "PCF_off_minus_PCF_on_and_B",
    "q_comparison_tolerance_m": TOL_M,
    "reference_position_input_rule": "ON/B/OFF logged reference/position arrays must be elementwise exactly equal; this is an input identity check, not a state trajectory comparison.",
    "controller_call_time_s": {
        "definition": "Per-controller-call elapsed time read from log/controller_call_time_s; mean/p95/max is separate from whole-scene wall runtime.",
        "missing_field_policy": "Missing, empty, nonfinite, negative or wrong-length field blocks scoring.",
    },
    "candidate_episode_runtime_s": {
        "definition": "OFF run_status.episode_runtime_seconds; timer surrounds only run_episode_dl1018 and excludes scene/input loading plus MAT/status/report writes.",
        "mean": float(np.mean(candidate_episode)), "p95": float(np.quantile(candidate_episode, 0.95)),
        "max": float(np.max(candidate_episode)), "sum": float(np.sum(candidate_episode)),
    },
    "candidate_attempt_execution_and_raw_persistence_s": {
        "definition": "OFF run_status.attempt_execution_and_raw_persistence_seconds; starts immediately before run_start.mat save and ends after raw_run.mat save, excluding scene/input loading and later status/report writes.",
        "mean": float(np.mean(candidate_attempt)), "p95": float(np.quantile(candidate_attempt, 0.95)),
        "max": float(np.max(candidate_attempt)), "sum": float(np.sum(candidate_attempt)),
    },
    "groups": {name: group_summary(rows) for name, rows in groups.items()},
    "hf_w09_w14_gate": {
        "n": len(hf), "mean_q_on_m": mean(hf, "on_q_0_20_m"),
        "mean_q_off_m": mean(hf, "off_q_0_20_m"),
        "mean_q_improvement_off_vs_on_m": hf_q_improvement_vs_on,
        "mean_q_off_minus_b_m": hf_q_off_minus_b,
        "z_rmse_off_wins_of_6": hf_z_wins,
    },
    "all_12_macro": {
        "mean_q_b_m": mean(records, "b_q_0_20_m"), "mean_q_on_m": mean(records, "on_q_0_20_m"),
        "mean_q_off_m": mean(records, "off_q_0_20_m"),
        "mean_q_improvement_off_vs_b_m": macro_q_improvement_vs_b,
    },
    "micro_sensitivity": {
        "q_outcomes_off_vs_on": {name: sum(r["q_outcome_off_vs_on"] == name for r in records)
                                  for name in ("WIN", "TIE", "LOSS")},
        "q_outcomes_off_vs_b": {name: sum(r["q_outcome_off_vs_b"] == name for r in records)
                                 for name in ("WIN", "TIE", "LOSS")},
        "mean_q_improvement_off_vs_on_m": mean(records, "on_q_0_20_m") - mean(records, "off_q_0_20_m"),
        "mean_q_improvement_off_vs_b_m": macro_q_improvement_vs_b,
    },
    "registered_gate_pass": gate,
    "decision": "SCREEN_PASS_REQUEST_72_REVIEW" if gate else "SCREEN_NOT_PASSED_NO_72_NO_TUNING",
    "claim_limit": "A 12-scene screen can only decide whether to request a separate 72-scene review; it does not independently prove or falsify H2.",
    "rescore_csv_sha256": {role: identity[0] for role, identity in rescore_identities.items()},
}
report_dir = HERE / "reports"
report_dir.mkdir(parents=True, exist_ok=True)
with (report_dir / "round2_screen_results.csv").open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
(report_dir / "round2_screen_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
