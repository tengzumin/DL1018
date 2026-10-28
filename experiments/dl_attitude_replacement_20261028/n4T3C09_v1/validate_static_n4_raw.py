from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE = "DL1018_DEV_T3_C09_W09"
ATTEMPT = HERE / "runs" / SCENE / "attempt_01"
OUT = HERE / "audits/RAW_VALIDATION_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scalar(group: h5py.Group, name: str) -> float:
    return float(np.asarray(group[name][()]).reshape(-1)[0])


def main() -> None:
    status_path = ATTEMPT / "run_status.json"
    raw_path = ATTEMPT / "raw_run.mat"
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite {OUT}")
    if (status.get("scene_id") != SCENE or status.get("state") != "COMPLETED" or
            status.get("status_value") != "STABLE" or status.get("transitions") != 20000 or
            status.get("state_samples") != 20001 or status.get("Plant_calls") != 1 or
            status.get("TEST_read") is not False or status.get("VAL_read") is not False or
            sha(raw_path) != status.get("raw_sha256")):
        raise SystemExit("candidate status/raw contract failed")
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        centers = np.asarray(log["stage1_position_applied_static_n4_centers_hz"][()], dtype=np.float64).reshape(-1)
        q = np.asarray(log["stage1_position_applied_static_n4_q"][()], dtype=np.float64).reshape(-1)
        filt_enabled = scalar(log, "stage1_position_applied_static_n4_enabled")
        filt_input = np.asarray(log["stage1_position_applied_static_n4_event_input_mps2"][()], dtype=np.float64)
        filt_raw = np.asarray(log["stage1_position_applied_static_n4_event_output_raw_mps2"][()], dtype=np.float64)
        filt_applied = np.asarray(log["stage1_position_applied_static_n4_event_output_applied_mps2"][()], dtype=np.float64)
        filt_clip = np.asarray(log["stage1_position_applied_static_n4_event_clip_active"][()], dtype=bool)
        residual_enabled = scalar(log, "stage1_position_residual_gru_enabled")
        residual_events = np.asarray(log["stage1_position_residual_gru_event"][()], dtype=bool)
        residual_count = scalar(log, "stage1_position_residual_gru_event_count")
        residual_raw = np.asarray(log["stage1_position_residual_gru_raw_delta_mps2"][()], dtype=np.float64)
        residual_clip = np.asarray(log["stage1_position_residual_gru_clipped_delta_mps2"][()], dtype=np.float64)
        residual_applied = np.asarray(log["stage1_position_residual_gru_applied_correction_mps2"][()], dtype=np.float64)
        state = np.asarray(log["state"][()], dtype=np.float64).T
        action = np.asarray(log["stage1_position_held_applied_acceleration_mps2"][()], dtype=np.float64).T
        events = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        event_count = int(events.sum())
    checks = {
        "stable_20k": status["status_value"] == "STABLE" and status["transitions"] == 20000 and status["state_samples"] == 20001,
        "one_plant_call": status["Plant_calls"] == 1 and status.get("first_plant_step_marker_created") is True,
        "fixed_n4": filt_enabled == 1 and np.array_equal(centers, [2.2, 3.2, 3.7, 4.8]) and np.array_equal(q, [4, 4, 4, 4]),
        "finite_n4_event_logs": np.isfinite(filt_input[:, events]).all() and np.isfinite(filt_raw[:, events]).all() and np.isfinite(filt_applied[:, events]).all(),
        "clip_count_zero": int(filt_clip.sum()) == 0,
        "no_extra_position_gru": residual_enabled == 0 and residual_count == 0 and not residual_events.any() and
            np.count_nonzero(residual_raw) == 0 and np.count_nonzero(residual_clip) == 0 and np.count_nonzero(residual_applied) == 0,
        "finite_state_and_applied_action": np.isfinite(state).all() and np.isfinite(action).all(),
        "scene_scope": SCENE.startswith("DL1018_DEV_") and "VAL" not in SCENE and "TEST" not in SCENE,
    }
    checks = {key: bool(value) for key, value in checks.items()}
    if not all(checks.values()):
        raise SystemExit(f"raw validation failed: {checks}")
    result = {
        "status": "PASS_FIXED_N4_NO_POSITION_GRU_RAW",
        "scene_id": SCENE,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha(raw_path),
        "status_path": str(status_path.resolve()),
        "status_sha256": sha(status_path),
        "transitions": 20000,
        "state_samples": 20001,
        "Plant_calls": 1,
        "stage1_position_event_count": event_count,
        "centers_hz": centers.tolist(),
        "quality_factor_each": q.tolist(),
        "filter_event_clip_count": int(filt_clip.sum()),
        "position_residual_gru_enabled": False,
        "position_residual_gru_event_count": int(residual_count),
        "position_residual_gru_raw_nonzero_count": int(np.count_nonzero(residual_raw)),
        "position_residual_gru_clipped_nonzero_count": int(np.count_nonzero(residual_clip)),
        "position_residual_gru_applied_nonzero_count": int(np.count_nonzero(residual_applied)),
        "checks": checks,
        "TEST_read": False,
        "VAL_read": False,
        "inertia_reconstruction_enabled": False,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "scene_id": SCENE, "raw_sha256": result["raw_sha256"],
                      "position_residual_gru_event_count": residual_count, "filter_clip_count": int(filt_clip.sum())}, indent=2))


if __name__ == "__main__":
    main()
