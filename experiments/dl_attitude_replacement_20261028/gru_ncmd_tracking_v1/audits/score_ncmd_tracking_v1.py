"""Hash-bound partial/final paired scoring for the fixed 12-scene NCMD-GRU screen."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[2]
WN12 = ROOT / "experiments" / "dl_attitude_replacement_20261027" / "task_attitude_filter_wn12_hf_screen_v1"
SCREEN_PATH = WN12 / "SCREEN12_RESULTS_v1.json"
METRIC_PATH = (ROOT / "experiments" / "dl_attitude_replacement_20261026" /
               "gru_stream_cosine_tracking_head_full72_v1" / "audits" /
               "score_full72_candidate_v1.py")
METRIC_SHA256 = "6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16"
MAIN = ("Q_m", "task_SO3_rad", "inner_SO3_rad")
GROUPS = {
    "ALL12": 12,
    "HF_W09_W14": 6,
    "W15": 3,
    "W00_W08": 3,
    "ZERO_RAW_WIND": 3,
    "NONZERO_RAW_WIND": 9,
}
METHODS = ("Candidate", "Parent_Cosine_GRU", "B", "C5")
BASELINES = ("Parent_Cosine_GRU", "B", "C5")
WIN_TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def bound(path: Path, expected: str, label: str) -> str:
    require(path.is_file(), f"Missing {label}: {path}")
    actual = sha(path)
    require(actual.lower() == str(expected).lower(), f"{label} SHA-256 mismatch: {path}")
    return actual


def load_metrics():
    require(bound(METRIC_PATH, METRIC_SHA256, "frozen FULL72 metric scorer"),
            "unreachable")
    spec = importlib.util.spec_from_file_location("frozen_full72_metrics", METRIC_PATH)
    require(spec is not None and spec.loader is not None, f"Cannot import metric scorer: {METRIC_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def classify(scene_id: str):
    m = re.search(r"_W(\d{2})$", scene_id)
    require(m is not None, f"Cannot parse wind group from {scene_id}")
    w = int(m.group(1))
    return "HF_W09_W14" if 9 <= w <= 14 else ("W15" if w == 15 else "W00_W08")


def classify_actual_raw_wind(raw_path: Path):
    with h5py.File(raw_path, "r") as f:
        wind = np.asarray(f["scene/environment_wind_I"][()], dtype=np.float64)
    require(wind.ndim == 2 and 3 in wind.shape and max(wind.shape) >= 20001 and
            np.isfinite(wind).all(), f"Invalid scene/environment_wind_I in {raw_path}")
    is_zero = bool(np.all(wind == 0.0))
    return {
        "group": "ZERO_RAW_WIND" if is_zero else "NONZERO_RAW_WIND",
        "exact_zero": is_zero,
        "shape_as_stored": list(wind.shape),
        "maximum_absolute_component_mps": float(np.max(np.abs(wind))),
    }


def validate_bindings():
    release_path = STUDY / "RELEASE.json"
    release = readj(release_path)
    require(release.get("schema") == "DL1018_GRU_STREAM_DEV_RELEASE_V1" and
            release.get("variant_schema") == "DL1018_GRU_NCMD_TRACKING_RELEASE_V1" and
            release.get("study_id") == "gru_ncmd_tracking_v1" and
            release.get("candidate_arm_id") == "GRU32_STREAM72_NCMD_TRACKING_S2026102001" and
            release.get("status") == "RELEASED" and
            release.get("authorized_Plant_calls") == 12 and
            float(release.get("position_nn_compensation_scale", -1)) == 1.0 and
            release.get("position_path_changed") is False and
            release.get("TEST_read") is False and release.get("test_data_read") is False and
            release.get("inertia_reconstruction_enabled") is False and
            release.get("Plant_truth_deployment_input") is False,
            "NCMD release identity, budget, position path, or safety boundary is invalid")

    source_manifest_path = STUDY / "SOURCE_HASH_MANIFEST_v1.json"
    source_manifest_sha = bound(source_manifest_path, release["source_hash_manifest_sha256"],
                                "candidate source manifest")
    source_manifest = readj(source_manifest_path)
    require(source_manifest.get("schema") == "DL1018_GRU_NCMD_TRACKING_SOURCE_HASH_MANIFEST_V1" and
            source_manifest.get("source_file_count") == len(source_manifest.get("files", [])),
            "Candidate source manifest schema/count is invalid")
    for row in source_manifest["files"]:
        bound(STUDY / row["path"], row["sha256"], f"candidate source {row['path']}")

    source_lock_path = STUDY / "SOURCE_LOCK_v1.json"
    bound(source_lock_path, release["source_lock_sha256"], "candidate source lock")
    source_lock = readj(source_lock_path)
    require(source_lock.get("schema") == "DL1018_GRU_NCMD_TRACKING_SOURCE_LOCK_V1" and
            str(source_lock.get("model_sha256", "")).lower() ==
            str(release["model_sha256"]).lower(), "Source lock model binding is invalid")
    for artifact in source_lock["study_artifacts"]:
        bound(STUDY / artifact["relative_path"], artifact["sha256"],
              f"locked study artifact {artifact['relative_path']}")

    input_manifest_path = STUDY / "SCENE_INPUT_MANIFEST_v1.json"
    input_manifest_sha = bound(input_manifest_path, release["scene_input_manifest_sha256"],
                               "fixed 12-scene input manifest")
    manifest = readj(input_manifest_path)
    require(manifest.get("schema") == "DL1018_GRU_NCMD_TRACKING_INPUT_MANIFEST_V1" and
            manifest.get("study_id") == release["study_id"] and
            manifest.get("status") == "PASS_FIXED12_INPUT_BINDINGS" and
            manifest.get("scene_count") == 12 and len(manifest.get("records", [])) == 12 and
            manifest.get("TEST_read") is False and manifest.get("Plant_calls") == 0,
            "Fixed input manifest is invalid")
    ids = [r["scene_id"] for r in manifest["records"]]
    require(len(set(ids)) == 12 and set(ids) == set(release["authorized_scenes"]),
            "Input-manifest scenes differ from the exact authorized 12")
    parent_path = Path(release["parent_manifest_path"])
    parent_sha = bound(parent_path, release["parent_manifest_sha256"], "FULL72 parent manifest")
    parent = readj(parent_path)
    require(parent.get("schema") == "GRU_STREAM_COSINE_TRACKING_HEAD_FULL72_MANIFEST_V1" and
            parent.get("candidate") == release["parent_candidate"] and
            parent.get("scene_count") == 72 and parent.get("dev_scene_count") == 24 and
            parent.get("val_scene_count") == 48 and parent.get("TEST_read") is False,
            "Parent scope differs from the locked WN18 FULL72 cosine-GRU study")
    require(str(manifest.get("parent_manifest_sha256", "")).lower() == parent_sha.lower(),
            "Scene manifest does not bind the parent FULL72 manifest")
    parent_release_path = parent_path.parent / "RELEASE.json"
    parent_release = readj(parent_release_path)
    require(parent_release.get("schema") == "DL1018_GRU_STREAM_DEV_RELEASE_V1" and
            parent_release.get("study_id") == release["parent_study_id"] and
            parent_release.get("candidate") == release["parent_candidate"] and
            parent_release.get("status") == "RELEASED" and
            parent_release.get("manifest_sha256", "").lower() == parent_sha.lower() and
            parent_release.get("TEST_read") is False,
            "Parent cosine-GRU release/manifest identity is invalid")
    parent_release_sha = sha(parent_release_path)
    parent_model_sha = bound(Path(parent_release["model_path"]), parent_release["model_sha256"],
                             "parent cosine-GRU model")
    require(str(parent.get("candidate_model_sha256", "")).lower() == parent_model_sha.lower() and
            str(parent.get("candidate_model_path", "")).lower() ==
            str(parent_release["model_path"]).lower(),
            "Parent FULL72 manifest/model differs from its released cosine-GRU model")
    model_path = bound(Path(release["model_path"]), release["model_sha256"],
                       "frozen NCMD GRU model")

    locked_cfg_path = STUDY / "LOCKED_CFG.json"
    bound(locked_cfg_path, release["locked_cfg_sha256"], "locked candidate configuration")
    locked_cfg = readj(locked_cfg_path)
    require(locked_cfg.get("candidate_attitude_model_sha256") == release["model_sha256"] and
            float(locked_cfg.get("position_nn_compensation_scale", -1)) == 1.0 and
            locked_cfg.get("position_nn_compensation_enabled") is False,
            "Locked configuration does not bind the NCMD model and unscaled C5 path")
    c5_lock_sha = str(locked_cfg["c5_input_lock_sha256"])

    screen = readj(SCREEN_PATH)
    require(str(screen.get("metric_scorer_path", "")).lower() == str(METRIC_PATH).lower() and
            str(screen.get("metric_scorer_sha256", "")).lower() == METRIC_SHA256,
            "WN12 screen does not bind the expected frozen metric scorer")
    constants_path = Path(screen["metric_constants_path"])
    bound(constants_path, screen["metric_constants_sha256"], "frozen metric constants")
    constants = readj(constants_path)
    gravity = float(constants["gravity_mps2"])
    max_tilt = float(constants["max_tilt_rad"])
    require(abs(gravity - float(screen["metric_constants"]["gravity_mps2"])) < 1e-12 and
            abs(max_tilt - float(screen["metric_constants"]["max_tilt_rad"])) < 1e-12,
            "Metric constants differ from the WN12 screen binding")
    return (release_path, release, manifest, source_manifest_sha, input_manifest_sha,
            parent_path, parent, parent_sha, parent_release_path, parent_release,
            parent_release_sha, c5_lock_sha, gravity, max_tilt, screen)


def validate_base_row(record: dict, method: str):
    raw_path = Path(record[f"{method.lower()}_raw_path"])
    raw_sha = bound(raw_path, record[f"{method.lower()}_raw_sha256"], f"{method} raw")
    status_path = Path(record[f"{method.lower()}_status_path"])
    status_sha = bound(status_path, record[f"{method.lower()}_status_sha256"], f"{method} status")
    status = readj(status_path)
    test_clear = status.get("TEST_accessed") is False and \
        status.get("TEST_read", False) is False
    require(status.get("scene_id") == record["scene_id"] and
            status.get("status") == "RUN_COMPLETE_RAW_PENDING_AUDIT" and
            status.get("log_status") == "STABLE" and
            status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
            status.get("plant_calls") == 1 and status.get("training_steps") == 0 and
            status.get("optimizer_steps") == 0 and test_clear and
            str(status.get("raw_sha256", "")).lower() == raw_sha.lower(),
            f"{method} source status/input identity failed for {record['scene_id']}")
    return raw_path, raw_sha, status_path, status_sha, status


def candidate_for(record: dict, release: dict, release_sha: str, source_sha: str,
                  input_sha: str, parent_sha: str, c5_lock_sha: str, metrics,
                  gravity: float, max_tilt: float):
    sid = record["scene_id"]
    attempt = STUDY / "runs" / sid
    status_path = attempt / "run_status.json"
    start_path = attempt / "run_start.json"
    marker_path = attempt / "attempt_started.marker"
    if not status_path.is_file():
        state = "IN_PROGRESS" if marker_path.is_file() or start_path.is_file() else "NOT_STARTED"
        return None, {"scene_id": sid, "state": state}

    status = readj(status_path)
    if status.get("state") != "COMPLETED":
        return None, {"scene_id": sid, "state": str(status.get("state", "UNKNOWN")),
                      "status_path": str(status_path), "status_sha256": sha(status_path)}
    require(start_path.is_file(), f"Completed candidate has no run_start: {sid}")
    require(marker_path.is_file(), f"Completed candidate has no attempt marker: {sid}")
    start = readj(start_path)
    marker = readj(marker_path)
    status_sha = sha(status_path)
    start_sha = sha(start_path)
    require(status.get("scene_id") == sid and status.get("Plant_calls") == 1 and
            status.get("test_data_read") is False and
            str(status.get("gru_model_sha256", "")).lower() ==
            str(release["model_sha256"]).lower() and
            str(status.get("source_lock_sha256", "")).lower() ==
            str(release["source_lock_sha256"]).lower(),
            f"Completed candidate status identity failed for {sid}")
    require(marker.get("schema") == "DL1018_GRU_NCMD_TRACKING_ATTEMPT_MARKER_V1" and
            marker.get("scene_id") == sid and marker.get("stage") == "RUNNING" and
            str(marker.get("release_sha256", "")).lower() == release_sha.lower(),
            f"Attempt marker binding failed for {sid}")
    for key, expected in (
        ("release_sha256", release_sha),
        ("source_hash_manifest_sha256", source_sha),
        ("scene_input_manifest_sha256", input_sha),
        ("parent_manifest_sha256", parent_sha),
        ("scene_payload_sha256", record["payload_sha256"]),
        ("b_raw_sha256", record["b_raw_sha256"]),
        ("c5_input_lock_sha256", c5_lock_sha),
        ("gru_model_sha256", release["model_sha256"]),
        ("source_lock_sha256", release["source_lock_sha256"]),
    ):
        require(str(start.get(key, "")).lower() == str(expected).lower(),
                f"run_start {key} binding mismatch for {sid}")
    require(start.get("schema") == "DL1018_GRU_NCMD_TRACKING_RUN_START_V1" and
            start.get("scene_id") == sid and
            start.get("candidate") == release["candidate_arm_id"] and
            start.get("parent_candidate") == release["parent_candidate"] and
            start.get("attitude_arm") == "GRU_STREAM" and
            start.get("geometry_arm") == "ACTIVE" and
            float(start.get("position_nn_compensation_scale", -1)) == 1.0 and
            start.get("inertia_reconstruction_enabled") is False and
            start.get("test_data_read") is False,
            f"run_start scene/model-arm/scale binding failed for {sid}")
    raw_path = Path(status["raw_path"])
    expected_raw = attempt / "raw_run.mat"
    require(raw_path.resolve() == expected_raw.resolve(),
            f"Candidate raw path is outside the exact attempt directory for {sid}")
    raw_sha = bound(raw_path, status["raw_sha256"], f"candidate raw {sid}")
    require(status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
            status.get("status_value") == "STABLE",
            f"Candidate is not a complete stable run for {sid}")
    raw_wind = classify_actual_raw_wind(raw_path)
    require((raw_wind["group"] == "ZERO_RAW_WIND") == (classify(sid) == "W15"),
            f"Raw wind group disagrees with the locked scene ID for {sid}")
    scored = metrics.score_raw(raw_path, gravity, max_tilt)
    scored.update({
        "raw_path": str(raw_path), "raw_sha256": raw_sha,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "run_status_path": str(status_path), "run_status_sha256": status_sha,
        "release_sha256": release_sha,
        "source_hash_manifest_sha256": source_sha,
        "scene_input_manifest_sha256": input_sha,
        "source_lock_sha256": release["source_lock_sha256"],
        "gru_model_sha256": release["model_sha256"],
        "position_nn_compensation_scale": 1.0,
        "actual_raw_wind": raw_wind,
    })
    return scored, {"scene_id": sid, "state": "COMPLETED",
                    "actual_raw_wind_group": raw_wind["group"]}


def parent_cosine_for(record: dict, input_record: dict, release: dict,
                      release_sha: str, manifest_sha: str, parent_release: dict,
                      parent_release_sha: str, c5_lock_sha: str, metrics,
                      gravity: float, max_tilt: float):
    sid = input_record["scene_id"]
    raw_path = Path(record["candidate_raw_path"])
    status_path = Path(record["candidate_status_path"])
    start_path = status_path.parent / "run_start.json"
    marker_path = status_path.parent / "attempt_started.marker"
    if not status_path.is_file():
        return None, {"scene_id": sid, "state": "NOT_STARTED_PARENT_COSINE"}
    status = readj(status_path)
    if status.get("state") != "COMPLETED":
        return None, {"scene_id": sid, "state": str(status.get("state", "UNKNOWN")),
                      "method": "Parent_Cosine_GRU", "status_path": str(status_path)}
    require(start_path.is_file() and marker_path.is_file(),
            f"Completed parent cosine run lacks its start or marker: {sid}")
    start, marker = readj(start_path), readj(marker_path)
    status_sha, start_sha, marker_sha = sha(status_path), sha(start_path), sha(marker_path)
    raw_sha = bound(raw_path, status.get("raw_sha256", ""), f"parent cosine raw {sid}")
    reused = bool(record.get("candidate_reuse", False))
    baseline_release = parent_release
    baseline_release_path = parent_release_path = None
    baseline_manifest_sha = manifest_sha
    baseline_release_sha = parent_release_sha
    baseline_source_lock_sha = parent_release["source_lock_sha256"]
    baseline_locked_cfg_sha = parent_release["locked_cfg_sha256"]
    audit_sha = ""
    if reused:
        # The FULL72 manifest explicitly reuses six earlier scene runs; bind their
        # actual study release/manifest and audit instead of assuming FULL72 paths.
        baseline_study = status_path.parents[2]
        baseline_release_path = baseline_study / "RELEASE.json"
        baseline_manifest_path = baseline_study / "MANIFEST.json"
        baseline_release = readj(baseline_release_path)
        baseline_manifest_sha = bound(baseline_manifest_path,
                                      baseline_release["manifest_sha256"],
                                      f"reused cosine manifest {sid}")
        baseline_source_lock_sha = baseline_release["source_lock_sha256"]
        baseline_locked_cfg_sha = baseline_release["locked_cfg_sha256"]
        bound(baseline_study / "SOURCE_LOCK_v1.json", baseline_source_lock_sha,
              f"reused cosine source lock {sid}")
        bound(Path(baseline_release["model_path"]), baseline_release["model_sha256"],
              f"reused cosine model {sid}")
        baseline_release_sha = str(start.get("release_sha256", ""))
        require(record.get("candidate_parent_status") == "COMPLETED" and
                record.get("candidate_parent_audit_status") ==
                "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and
                baseline_release.get("candidate") == parent_release["candidate"] and
                baseline_release.get("status") == "RELEASED" and
                str(baseline_release.get("model_sha256", "")).lower() ==
                str(parent_release["model_sha256"]).lower(),
                f"Reused cosine lineage does not match the FULL72 parent for {sid}")
        require(str(start.get("manifest_sha256", "")).lower() == baseline_manifest_sha.lower() and
                str(start.get("source_lock_sha256", "")).lower() == baseline_source_lock_sha.lower() and
                str(start.get("locked_cfg_sha256", "")).lower() == baseline_locked_cfg_sha.lower(),
                f"Reused cosine start does not bind its current study artifacts for {sid}")
        audit_path = Path(record["candidate_audit_path"])
        audit = readj(audit_path)
        audit_sha = sha(audit_path)
        require(audit.get("status") == "PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY" and
                audit.get("scene_id") == sid and audit.get("candidate") == parent_release["candidate"] and
                audit.get("TEST_read") is False and audit.get("Plant_calls_by_audit") == 0 and
                audit.get("training_calls_by_audit") == 0 and
                str(audit.get("release_sha256", "")).lower() == baseline_release_sha.lower() and
                str(audit.get("candidate_raw_sha256", "")).lower() == raw_sha.lower() and
                str(audit.get("model_sha256", "")).lower() ==
                str(parent_release["model_sha256"]).lower(),
                f"Reused cosine raw audit binding failed for {sid}")
    require(str(Path(status.get("raw_path", "")).resolve()) == str(raw_path.resolve()) and
            status.get("scene_id") == sid and status.get("Plant_calls") == 1 and
            status.get("transitions") == 20000 and status.get("state_samples") == 20001 and
            status.get("status_value") == "STABLE" and status.get("TEST_read") is False and
            str(status.get("source_lock_sha256", "")).lower() ==
            str(baseline_source_lock_sha).lower() and
            str(record.get("candidate_raw_sha256", "")).lower() in {"", raw_sha.lower()} and
            str(record.get("candidate_status_sha256", "")).lower() in {"", status_sha.lower()},
            f"Parent cosine status/input binding failed for {sid}")
    require(marker.get("scene_id") == sid and marker.get("stage") == "RUNNING" and
            str(marker.get("release_sha256", "")).lower() == baseline_release_sha.lower(),
            f"Parent cosine marker binding failed for {sid}")
    expected_start = {
        "release_sha256": baseline_release_sha,
        "manifest_sha256": baseline_manifest_sha,
        "source_lock_sha256": baseline_source_lock_sha,
        "locked_cfg_sha256": baseline_locked_cfg_sha,
        "b_raw_sha256": input_record["b_raw_sha256"],
        "c5_raw_sha256": input_record["c5_raw_sha256"],
        "payload_sha256": input_record["payload_sha256"],
        "gru_model_sha256": parent_release["model_sha256"],
        "c5_input_lock_sha256": c5_lock_sha,
    }
    require(start.get("schema") == "DL1018_GRU_STREAM_COSINE_TRACKING_HEAD_RUN_START_V1" and
            start.get("scene_id") == sid and start.get("candidate") == baseline_release["candidate"] and
            start.get("attitude_arm") == "GRU_STREAM" and start.get("geometry_arm") == "ACTIVE" and
            start.get("TEST_read") is False and start.get("inertia_reconstruction_enabled") is False and
            start.get("Plant_truth_deployment_input") is False and
            all(str(start.get(k, "")).lower() == str(v).lower()
                for k, v in expected_start.items()),
            f"Parent cosine run_start identity binding failed for {sid}")
    wind = classify_actual_raw_wind(raw_path)
    require((wind["group"] == "ZERO_RAW_WIND") == (classify(sid) == "W15"),
            f"Parent cosine raw wind group disagrees with the scene ID for {sid}")
    scored = metrics.score_raw(raw_path, gravity, max_tilt)
    scored.update({
        "raw_path": str(raw_path), "raw_sha256": raw_sha,
        "run_start_path": str(start_path), "run_start_sha256": start_sha,
        "run_status_path": str(status_path), "run_status_sha256": status_sha,
        "attempt_marker_path": str(marker_path), "attempt_marker_sha256": marker_sha,
        "release_sha256": baseline_release_sha,
        "source_lock_sha256": baseline_source_lock_sha,
        "gru_model_sha256": parent_release["model_sha256"],
        "actual_raw_wind": wind,
        "reuse_from_parent_study": reused,
        "parent_audit_path": str(Path(record["candidate_audit_path"])) if reused else None,
        "parent_audit_sha256": audit_sha or None,
    })
    return scored, {"scene_id": sid, "state": "COMPLETED",
                    "actual_raw_wind_group": wind["group"]}


def macro(rows: list[dict], group: str):
    selected = [r for r in rows if group == "ALL12" or r["wind_group"] == group or
                r["actual_raw_wind_group"] == group]
    out = {"scene_count": len(selected), "expected_scene_count": GROUPS[group],
           "complete": len(selected) == GROUPS[group]}
    out["macro_mean_observed"] = {
        method: {
            key: sum(r["methods"][method][key] for r in selected) / len(selected)
            for key in MAIN
        } for method in METHODS
    } if selected else None
    wins = {}
    for baseline in BASELINES:
        wins[baseline] = {}
        for key in MAIN:
            diffs = [r["methods"]["Candidate"][key] - r["methods"][baseline][key]
                     for r in selected]
            wins[baseline][key] = {
                "win": sum(d < -WIN_TOL for d in diffs),
                "tie": sum(abs(d) <= WIN_TOL for d in diffs),
                "loss": sum(d > WIN_TOL for d in diffs),
            }
    out["per_scene_wins_losses_ties"] = wins
    return out


def write_csv(path: Path, rows: list[dict]):
    fields = ["scene_id", "split", "wind_group", "actual_raw_wind_group",
              "raw_wind_max_abs_component_mps"]
    for method in METHODS:
        fields.extend(f"{method}_{key}" for key in MAIN)
    for baseline in BASELINES:
        fields.extend(f"Candidate_minus_{baseline}_{key}" for key in MAIN)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {"scene_id": row["scene_id"], "split": row["split"],
                    "wind_group": row["wind_group"],
                    "actual_raw_wind_group": row["actual_raw_wind_group"],
                    "raw_wind_max_abs_component_mps":
                        row["actual_raw_wind"]["maximum_absolute_component_mps"]}
            for method in METHODS:
                flat.update({f"{method}_{key}": row["methods"][method][key] for key in MAIN})
            for baseline in ("B", "C5"):
                flat.update({f"Candidate_minus_{baseline}_{key}":
                             row["methods"]["Candidate"][key] - row["methods"][baseline][key]
                             for key in MAIN})
            writer.writerow(flat)


def write_markdown(path: Path, result: dict):
    lines = [
        "# NCMD-GRU tracking paired score",
        "",
        f"Status: **{result['status']}**. Completed scenes: "
        f"{result['completed_scene_count']}/12.",
        "",
        result["scope"],
        "Actual wind groups are read from `scene/environment_wind_I` in each candidate raw MAT; "
        "zero wind means every stored component is exactly zero.",
        "",
        "| Group | n / expected | Complete | Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |",
        "|---|---:|:---:|---|---:|---:|---:|",
    ]
    for group, summary in result["groups"].items():
        means = summary["macro_mean_observed"]
        for method in METHODS:
            m = means[method] if means else None
            values = ["—", "—", "—"] if m is None else [
                f"{m['Q_m']:.9g}", f"{m['task_SO3_rad']:.9g}", f"{m['inner_SO3_rad']:.9g}"]
            lines.append(f"| {group} | {summary['scene_count']} / {summary['expected_scene_count']} | "
                         f"{'yes' if summary['complete'] else 'no'} | {method} | "
                         + " | ".join(values) + " |")
    lines.extend(["", "Actual raw-wind groups:"])
    for name in ("ZERO_RAW_WIND", "NONZERO_RAW_WIND"):
        summary = result["groups"][name]
        lines.append(f"- {name}: {summary['scene_count']}/{summary['expected_scene_count']} scored scenes")
    lines.extend(["", "Pending or failed scenes:"])
    if result["pending_scenes"]:
        lines.extend(f"- {r['scene_id']}: {r['state']}" for r in result["pending_scenes"])
    else:
        lines.append("- none")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                        help="output tag, e.g. partial02 or final12")
    args = parser.parse_args()
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", args.tag) is not None, "Invalid output tag")
    json_out = HERE / f"GRU_NCMD_TRACKING_SCORE_{args.tag}.json"
    csv_out = HERE / f"GRU_NCMD_TRACKING_SCORE_{args.tag}.csv"
    md_out = HERE / f"GRU_NCMD_TRACKING_SCORE_{args.tag}.md"
    for path in (json_out, csv_out, md_out):
        require(not path.exists(), f"Refusing to overwrite existing score artifact: {path}")

    metric_module = load_metrics()
    (release_path, release, manifest, source_sha, input_sha,
     parent_manifest_path, parent_manifest, parent_sha, parent_release_path,
     parent_release, parent_release_sha, c5_lock_sha, gravity, max_tilt, screen) = validate_bindings()
    parent_records = {r["scene_id"]: r for r in parent_manifest["records"]}
    release_sha = sha(release_path)
    rows, pending = [], []
    for record in manifest["records"]:
        sid = record["scene_id"]
        b_path, b_sha, b_status_path, b_status_sha, b_status = validate_base_row(record, "B")
        c5_path, c5_sha, c5_status_path, c5_status_sha, c5_status = validate_base_row(record, "C5")
        candidate, state = candidate_for(record, release, release_sha, source_sha, input_sha,
                                         parent_sha, c5_lock_sha, metric_module, gravity, max_tilt)
        if candidate is None:
            pending.append(state)
            continue
        parent_record = parent_records.get(sid)
        require(parent_record is not None, f"Parent cosine manifest lacks scene {sid}")
        parent_candidate, parent_state = parent_cosine_for(
            parent_record, record, release, release_sha, parent_sha, parent_release,
            parent_release_sha, c5_lock_sha, metric_module, gravity, max_tilt)
        if parent_candidate is None:
            pending.append(parent_state)
            continue
        candidate_wind = candidate["actual_raw_wind"]["group"]
        require(parent_candidate["actual_raw_wind"]["group"] == candidate_wind and
                classify_actual_raw_wind(b_path)["group"] == candidate_wind and
                classify_actual_raw_wind(c5_path)["group"] == candidate_wind,
                f"Candidate/parent/B/C5 actual raw-wind groups differ for {sid}")
        paired = {
            "Candidate": candidate,
            "Parent_Cosine_GRU": parent_candidate,
            "B": metric_module.score_raw(b_path, gravity, max_tilt),
            "C5": metric_module.score_raw(c5_path, gravity, max_tilt),
        }
        paired["B"].update({"raw_path": str(b_path), "raw_sha256": b_sha,
                            "status_path": str(b_status_path), "status_sha256": b_status_sha})
        paired["C5"].update({"raw_path": str(c5_path), "raw_sha256": c5_sha,
                             "status_path": str(c5_status_path), "status_sha256": c5_status_sha})
        rows.append({
            "scene_id": sid, "split": record["source_split"],
            "wind_group": classify(sid),
            "actual_raw_wind_group": candidate["actual_raw_wind"]["group"],
            "actual_raw_wind": candidate["actual_raw_wind"], "methods": paired,
            "input_bindings": {
                "payload_sha256": record["payload_sha256"],
                "b_raw_sha256": b_sha, "b_status_sha256": b_status_sha,
                "c5_raw_sha256": c5_sha, "c5_status_sha256": c5_status_sha,
                "candidate_run_start_sha256": candidate["run_start_sha256"],
                "candidate_run_status_sha256": candidate["run_status_sha256"],
                "parent_cosine_run_start_sha256": parent_candidate["run_start_sha256"],
                "parent_cosine_run_status_sha256": parent_candidate["run_status_sha256"],
            },
        })

    complete = len(rows) == 12 and not pending and {r["scene_id"] for r in rows} == \
        {r["scene_id"] for r in manifest["records"]}
    groups = {name: macro(rows, name) for name in GROUPS}
    if complete:
        for name, expected in GROUPS.items():
            require(groups[name]["scene_count"] == expected,
                    f"Complete 12-scene group count mismatch for {name}")
    result = {
        "schema": "DL1018_GRU_NCMD_TRACKING_PAIRED_SCORE_V1",
        "status": "COMPLETE_12_SCREEN" if complete else "PARTIAL_12_SCREEN",
        "study_id": release["study_id"],
        "candidate_arm_id": release["candidate_arm_id"],
        "completed_scene_count": len(rows),
        "expected_scene_count": 12,
        "pending_scenes": pending,
        "groups": groups,
        "scene_results": rows,
        "release_sha256": release_sha,
        "source_hash_manifest_sha256": source_sha,
        "source_lock_sha256": release["source_lock_sha256"],
        "scene_input_manifest_sha256": input_sha,
        "parent_manifest_sha256": parent_sha,
        "parent_release_path": str(parent_release_path),
        "parent_release_sha256": parent_release_sha,
        "parent_cosine_gru_model_sha256": parent_release["model_sha256"],
        "gru_model_sha256": release["model_sha256"],
        "target_rms_source": release["target_rms_source"],
        "parent_model_scope": release.get("parent_model_scope"),
        "scope": "Fixed 12-scene DEV/VAL development screen; the parent GRU used DEV24+VAL48 "
                 "development evidence, VAL is not independent validation, and this study adds no training.",
        "independent_validation_claimed": False,
        "fresh_holdout_required_for_winner": True,
        "position_nn_compensation_scale": 1.0,
        "command_filter_wn_rad_s": release["command_filter_wn_rad_s"],
        "metric_source_path": str(METRIC_PATH),
        "metric_source_sha256": METRIC_SHA256,
        "metric_constants_path": screen["metric_constants_path"],
        "metric_constants_sha256": screen["metric_constants_sha256"],
        "metric_constants": {"gravity_mps2": gravity, "max_tilt_rad": max_tilt},
        "metric_definitions": {
            "Q_m": "RMS Euclidean position error over all 20001 state samples.",
            "task_SO3_rad": "SO(3) geodesic RMSE against task attitude reconstructed by the frozen FULL72 metric scorer.",
            "inner_SO3_rad": "SO(3) geodesic RMSE against filtered_attitude_reference over 20000 transitions.",
            "macro_mean": "Arithmetic mean of the per-scene metric over completed rows in that group.",
        },
        "raw_wind_grouping": "ZERO_RAW_WIND iff every stored component of candidate raw scene/environment_wind_I equals exactly zero; otherwise NONZERO_RAW_WIND. ID-based W15/HF/W00-W08 groups are reported separately.",
        "run_identity_binding": "Candidate raw is scored only after run_start binds release, source/input manifests, parent manifest, scene payload, B raw, C5 input lock, source lock, NCMD GRU model, and position scale 1. B/C5 raw and status hashes are bound by SCENE_INPUT_MANIFEST_v1.json.",
        "plant_calls_by_scorer": 0,
        "training_runs_by_scorer": 0,
        "TEST_read": False,
        "test_data_read": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(csv_out, rows)
    write_markdown(md_out, result)
    print(json.dumps({"status": result["status"], "completed": len(rows), "expected": 12,
                      "pending": pending, "json": str(json_out), "csv": str(csv_out),
                      "markdown": str(md_out)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
