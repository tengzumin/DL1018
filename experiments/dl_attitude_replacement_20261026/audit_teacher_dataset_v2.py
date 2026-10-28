#!/usr/bin/env python3
"""Independently verify the frozen VAL teacher data against its raw B logs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = Path(__file__).resolve().parent / "dataset_v4_teacher_distill"
MANIFEST = DATASET_DIR / "DATASET_MANIFEST_v2.json"
NPZ = DATASET_DIR / "attitude_rbf_teacher_train_val_v2.npz"
OUTPUT = Path(__file__).resolve().parent / "TEACHER_DATASET_V2_VAL_AUDIT.json"
FEATURES = [
    "attitude_error_euler_rad_x3",
    "body_rate_rad_s_x3",
    "nominal_bs_body_torque_Nm_x3",
    "morph_command_x4",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify() -> dict:
    meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (meta.get("schema") != "DL1018_CAUSAL_TCN_RBF_TEACHER_DATASET_V2"
            or meta.get("status") != "PASS"
            or meta.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or meta.get("feature_order") != FEATURES
            or meta.get("target") != "logged rbf_output_raw at event k, pre-beta, rad/s^2"
            or meta.get("test_data_read") is not False
            or meta.get("nominal_inertia_read") is not False
            or meta.get("plant_truth_read") is not False):
        raise ValueError("dataset manifest does not match the amended TRAIN/VAL-only contract")
    if sha256(NPZ) != meta.get("npz_sha256"):
        raise ValueError("NPZ hash differs from the dataset manifest")
    rows = [row for row in meta["rows"] if row["split"] == "VAL"]
    if len(rows) != 48 or len({row["scene_id"] for row in rows}) != 48:
        raise ValueError("VAL scene identity set is incomplete or duplicated")

    max_x_error = 0.0
    max_y_error = 0.0
    source_classes: dict[str, int] = {}
    with np.load(NPZ, allow_pickle=False) as arrays:
        vx = arrays["val_x"]
        vy = arrays["val_y"]
        if vx.shape != (48, 1999, 13) or vy.shape != (48, 1999, 3):
            raise ValueError(f"unexpected VAL arrays: {vx.shape}, {vy.shape}")
        if not np.isfinite(vx).all() or not np.isfinite(vy).all():
            raise ValueError("VAL arrays contain non-finite values")
        for i, row in enumerate(rows):
            raw_path = Path(row["raw_path"])
            start_path = Path(row["run_start_path"])
            if sha256(raw_path) != row["raw_sha256"] or sha256(start_path) != row["run_start_sha256"]:
                raise ValueError(f"source SHA mismatch: {row['scene_id']}")
            with h5py.File(raw_path, "r") as raw:
                log = raw["log"]
                time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
                state = np.asarray(log["state"], dtype=np.float64).T
                reference = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
                event = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
                nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
                teacher = np.asarray(log["rbf_output_raw"], dtype=np.float64).T
                command = np.asarray(raw["scene"]["arms"]["command"], dtype=np.float64).T
            events = np.flatnonzero(event)
            expected = np.arange(10, 20000, 10, dtype=np.int64)
            if (time.shape != (20001,) or state.shape != (20001, 12)
                    or not np.array_equal(events, expected)):
                raise ValueError(f"event timing or state shape mismatch: {row['scene_id']}")
            error = reference[events] - state[events, 6:9]
            error = np.arctan2(np.sin(error), np.cos(error))
            expected_x = np.concatenate((error, state[events, 9:12],
                                         nominal_torque[events], command[events]), axis=1).astype(np.float32)
            expected_y = teacher[events].astype(np.float32)
            dx = float(np.max(np.abs(vx[i] - expected_x)))
            dy = float(np.max(np.abs(vy[i] - expected_y)))
            max_x_error = max(max_x_error, dx)
            max_y_error = max(max_y_error, dy)
            if dx != 0.0 or dy != 0.0:
                raise ValueError(f"stored VAL arrays differ from raw event signals: {row['scene_id']} ({dx}, {dy})")
            source_classes[row["source_class"]] = source_classes.get(row["source_class"], 0) + 1

    return {
        "schema": "DL1018_CAUSAL_TCN_TEACHER_VAL_AUDIT_V1",
        "status": "PASS",
        "scenes": 48,
        "events_per_scene": 1999,
        "raw_and_run_start_sha_verified": 96,
        "source_classes": source_classes,
        "feature_order": FEATURES,
        "target": meta["target"],
        "max_feature_absolute_difference": max_x_error,
        "max_target_absolute_difference": max_y_error,
        "test_data_read": False,
        "plant_truth_read": False,
        "nominal_inertia_read": False,
        "npz_sha256": sha256(NPZ),
    }


if __name__ == "__main__":
    report = verify()
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
