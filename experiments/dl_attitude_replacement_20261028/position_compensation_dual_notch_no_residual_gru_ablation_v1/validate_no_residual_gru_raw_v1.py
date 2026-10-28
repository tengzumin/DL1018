#!/usr/bin/env python3
"""Validate the disabled position-GRU and fixed-notch fields in a future raw run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE = json.loads((HERE / "TRAIN_SCENE_BINDING_v1.json").read_text(encoding="utf-8-sig"))["selected_scene_id"]
ATTEMPT = HERE / "runs" / SCENE / "attempt_01"
RAW = ATTEMPT / "raw_run.mat"
STATUS = ATTEMPT / "run_status.json"
OUT = HERE / "audits/NO_RESIDUAL_GRU_RAW_VALIDATION_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scalar(raw: h5py.File, key: str) -> float:
    return float(np.asarray(raw["log"][key][()]).reshape(-1)[0])


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    status = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    if (status.get("scene_id") != SCENE or status.get("state") != "COMPLETED" or
            status.get("status_value") != "STABLE" or status.get("Plant_calls") != 1 or
            status.get("TEST_read") is not False or status.get("VAL_data_read") is not False or
            status.get("inertia_reconstruction_enabled") is not False or sha(RAW) != status.get("raw_sha256")):
        raise RuntimeError("Raw/status is incomplete, outside the fixed scene, or outside the allowed scope.")
    with h5py.File(RAW, "r") as raw:
        log = raw["log"]
        enabled = scalar(raw, "stage1_position_residual_gru_enabled")
        events = scalar(raw, "stage1_position_residual_gru_event_count")
        residual_fields = (
            "stage1_position_residual_gru_event", "stage1_position_residual_gru_raw_delta_mps2",
            "stage1_position_residual_gru_clipped_delta_mps2", "stage1_position_residual_gru_applied_correction_mps2",
        )
        residual_max_abs = {key: float(np.max(np.abs(np.asarray(log[key][()], dtype=np.float64)))) for key in residual_fields}
        notch_enabled = scalar(raw, "stage1_position_applied_dual_notch_enabled")
        centers = np.asarray(log["stage1_position_applied_dual_notch_centers_hz"][()], dtype=np.float64).reshape(-1)
        q = np.asarray(log["stage1_position_applied_dual_notch_q"][()], dtype=np.float64).reshape(-1)
    if (enabled != 0 or events != 0 or any(value != 0 for value in residual_max_abs.values()) or
            notch_enabled != 1 or not np.array_equal(centers, [2.2, 3.2]) or not np.array_equal(q, [4.0, 4.0])):
        raise RuntimeError("Raw does not satisfy the locked no-position-GRU/fixed-notch ablation contract.")
    result = {
        "schema": "POSITION_DUAL_NOTCH_NO_POSITION_RESIDUAL_GRU_RAW_VALIDATION_V1",
        "status": "PASS_NO_POSITION_GRU_EVENTS_OR_CORRECTION",
        "study_id": json.loads((HERE / "RELEASE.json").read_text(encoding="utf-8-sig"))["study_id"],
        "scene_id": SCENE, "raw_sha256": sha(RAW), "run_status_sha256": sha(STATUS),
        "Plant_calls": 1, "stage1_position_residual_gru_enabled": False,
        "stage1_position_residual_gru_event_count": 0, "residual_field_max_abs": residual_max_abs,
        "stage1_position_applied_dual_notch_enabled": True,
        "dual_notch_centers_hz": centers.tolist(), "dual_notch_q": q.tolist(),
        "TEST_read": False, "VAL_read": False, "inertia_reconstruction_enabled": False,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
