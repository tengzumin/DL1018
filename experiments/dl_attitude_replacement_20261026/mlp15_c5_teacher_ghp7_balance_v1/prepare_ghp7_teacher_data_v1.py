#!/usr/bin/env python3
"""Extract locked legal C5 teacher features for the GHP7 offline diagnostic."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

TASK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TASK_ROOT.parents[2]
RESEARCH_ROOT = PROJECT_ROOT / "experiments/dl_attitude_replacement_20261026"
BASELINE_MANIFEST = RESEARCH_ROOT / "GHP7_BASELINE_REUSE_MANIFEST_v1.json"
BASELINE_SHA = "8a34df2807cfe10486ee1dc5c3d698b6e530d2fdf901ca9d815ae1f5d1f71b25"
OUT_DIR = TASK_ROOT / "data"
TRAIN_PATH = OUT_DIR / "ghp7_g1_g2_train_v1.npz"
HOLDOUT_PATH = OUT_DIR / "ghp7_g3_dev_holdout_v1.npz"
DATA_MANIFEST_PATH = OUT_DIR / "GHP7_TEACHER_DATA_MANIFEST_v1.json"
DMAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
EVENTS = np.arange(10, 20_000, 10, dtype=np.int64)
EXPECTED = {
    "DL1018_GHP7_G1_W00": ("35046519a6485abd2d9370f363cf3f1ecd3c65e1958199ea2071f6282f617e02", "train"),
    "DL1018_GHP7_G1_W12": ("0c6e96231b0fed51ac529eff73d940a7ae56f85bbf3db2f37a7fee3d54427a3f", "train"),
    "DL1018_GHP7_G2_W00": ("bcb0b97af5c9b6d4305f4a6c2cadf210ede130118eb5ab6d976a408c59051f80", "train"),
    "DL1018_GHP7_G2_W12": ("db14af895c39f3ce7c14d2ec305867650b9e1759307459736108ca5c935efdec", "train"),
    "DL1018_GHP7_G3_W00": ("0ee3dc655540b877fa3728194da2a02677dcc00601a29bbfa313813305128bc4", "holdout"),
    "DL1018_GHP7_G3_W12": ("9823a4745a6d221c17958c53fd570345a536268f5b4f373fc0ca795fda368789", "holdout"),
}
FEATURE_ORDER = [
    "wrapped_attitude_error_euler_rad_x3", "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3", "morph_command_x4",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def extract_one(record: dict[str, Any], expected_sha: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    raw_path = Path(record["raw_path"]).resolve(strict=True)
    raw_path.relative_to(PROJECT_ROOT.resolve())
    raw_sha = sha256_file(raw_path)
    if raw_sha != expected_sha or raw_sha != str(record["raw_sha256"]).lower():
        raise ValueError(f"locked C5 raw hash mismatch: {record['scene_id']}")

    status_path = raw_path.parent / "run_status.json"
    status_sha = sha256_file(status_path)
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    if (status.get("state") != "COMPLETED" or status.get("status_value") != "STABLE"
            or status.get("actual_transition_count") != 20_000
            or status.get("actual_state_sample_count") != 20_001
            or Path(status.get("raw_output_path", "")).resolve() != raw_path
            or str(status.get("raw_output_sha256", "")).lower() != raw_sha):
        raise ValueError(f"C5 status/raw binding or completion check failed: {record['scene_id']}")

    with h5py.File(raw_path, "r") as source:
        log = source["log"]
        state = np.asarray(log["state"], dtype=np.float64).T
        reference = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
        flags = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
        nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
        teacher = np.asarray(log["rbf_output_raw"], dtype=np.float64).T
        command = np.asarray(log["arms"]["command"], dtype=np.float64).T
        if "attitude_rbf_feature_13" in log:
            logged_features = np.asarray(log["attitude_rbf_feature_13"], dtype=np.float64).T
        else:
            logged_features = None

    if not np.array_equal(np.flatnonzero(flags), EVENTS):
        raise ValueError(f"unexpected event indices: {record['scene_id']}")
    error = reference[EVENTS] - state[EVENTS, 6:9]
    error = np.arctan2(np.sin(error), np.cos(error))
    features64 = np.concatenate((
        error,
        state[EVENTS, 9:12],
        nominal_torque[EVENTS],
        command[EVENTS],
    ), axis=1)
    features = features64.astype(np.float32)
    targets = teacher[EVENTS].astype(np.float32)
    if features.shape != (1999, 13) or targets.shape != (1999, 3):
        raise ValueError(f"feature/target shape mismatch: {record['scene_id']}")
    if not np.isfinite(features).all() or not np.isfinite(targets).all():
        raise ValueError(f"non-finite teacher sample: {record['scene_id']}")
    if np.any(np.abs(targets.astype(np.float64)) > DMAX + 1e-8):
        raise ValueError(f"teacher label exceeds frozen dmax: {record['scene_id']}")
    feature_error = None
    if logged_features is not None:
        feature_error = float(np.max(np.abs(logged_features[EVENTS] - features64)))
        if feature_error > 1e-10:
            raise ValueError(f"reconstructed features differ from logged trace: {record['scene_id']}")
    return features, targets, {
        "scene_id": record["scene_id"], "raw_path": raw_path.relative_to(PROJECT_ROOT).as_posix(),
        "raw_sha256": raw_sha, "status_path": status_path.relative_to(PROJECT_ROOT).as_posix(),
        "status_sha256": status_sha, "actual_transitions": 20_000,
        "actual_state_samples": 20_001, "event_count": 1999,
        "feature_shape": list(features.shape), "target_shape": list(targets.shape),
        "feature_reconstruction_max_abs": feature_error,
        "application_feasible_in_reused_score": bool(record["application_feasible"]),
        "logger_complete_transitions_flag": bool(status.get("complete_transitions")),
    }


def save_bundle(path: Path, x: np.ndarray, y: np.ndarray, scene_ids: list[str]) -> None:
    temporary = path.with_suffix(".npz.tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, x=x, y=y, scene_ids=np.asarray(scene_ids, dtype=np.str_))
    temporary.replace(path)


def main() -> None:
    if any(path.exists() for path in (TRAIN_PATH, HOLDOUT_PATH, DATA_MANIFEST_PATH)):
        raise FileExistsError("refusing to overwrite existing GHP7 data bundle")
    if sha256_file(BASELINE_MANIFEST) != BASELINE_SHA:
        raise ValueError("GHP7 baseline reuse manifest SHA mismatch")
    baseline = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8-sig"))
    if (baseline.get("status") != "PASS" or baseline.get("test_data_read") is not False
            or baseline.get("raw_files_copied") is not False
            or baseline.get("baselines_reexecuted") is not False):
        raise ValueError("frozen B/C5 reuse manifest failed its read-only identity gate")
    selected = [r for r in baseline["records"]
                if r.get("runner") == "CANDIDATE" and r.get("attitude_arm") == "C5_RBF"]
    if {r["scene_id"] for r in selected} != set(EXPECTED) or len(selected) != 6:
        raise ValueError("C5 teacher raw scene IDs differ from the frozen six-scene list")

    train_x: list[np.ndarray] = []
    train_y: list[np.ndarray] = []
    train_ids: list[str] = []
    holdout_x: list[np.ndarray] = []
    holdout_y: list[np.ndarray] = []
    holdout_ids: list[str] = []
    source_rows = []
    for record in selected:
        scene_id = record["scene_id"]
        expected_sha, split = EXPECTED[scene_id]
        x, y, row = extract_one(record, expected_sha)
        source_rows.append({**row, "split": split})
        if split == "train":
            train_x.append(x); train_y.append(y); train_ids.append(scene_id)
        else:
            holdout_x.append(x); holdout_y.append(y); holdout_ids.append(scene_id)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_bundle(TRAIN_PATH, np.stack(train_x), np.stack(train_y), train_ids)
    save_bundle(HOLDOUT_PATH, np.stack(holdout_x), np.stack(holdout_y), holdout_ids)
    report = {
        "schema": "DL1018_MLP15_C5_GHP7_TEACHER_DATA_V1", "status": "PASS_OFFLINE_EXTRACTION",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_manifest_path": BASELINE_MANIFEST.relative_to(PROJECT_ROOT).as_posix(),
        "baseline_manifest_sha256": BASELINE_SHA, "feature_order": FEATURE_ORDER,
        "target_contract": "C5 logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2",
        "dmax_rad_s2": DMAX.tolist(), "plant_called": False, "TEST48_read": False,
        "raw_files_copied": False, "train_scene_ids": train_ids, "holdout_scene_ids": holdout_ids,
        "train_bundle": {"path": TRAIN_PATH.relative_to(PROJECT_ROOT).as_posix(),
                         "sha256": sha256_file(TRAIN_PATH), "shape_x": list(np.stack(train_x).shape),
                         "shape_y": list(np.stack(train_y).shape)},
        "holdout_bundle": {"path": HOLDOUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
                           "sha256": sha256_file(HOLDOUT_PATH), "shape_x": list(np.stack(holdout_x).shape),
                           "shape_y": list(np.stack(holdout_y).shape)},
        "source_rows": source_rows,
    }
    write_json(DATA_MANIFEST_PATH, report)
    print(json.dumps({"status": report["status"], "train_scenes": len(train_ids),
                      "holdout_scenes": len(holdout_ids), "plant_called": False,
                      "TEST48_read": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
