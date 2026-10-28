#!/usr/bin/env python3
"""Prepare fixed MATLAB helper-parity inputs from the two bound W09 TRAIN raws."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.io import savemat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_STUDY = ROOT / "experiments/dl_attitude_replacement_20261028/position_compensation_dual_notch_train_replay_v1"
SOURCE_REPORT = SOURCE_STUDY / "TRAIN_FROZEN_DUAL_NOTCH_REPLAY_v1.json"
OUT_MAT = HERE / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.mat"
OUT_JSON = HERE / "DUAL_NOTCH_EVENTWISE_PARITY_INPUTS_v1.json"
REPLAY_PY = SOURCE_STUDY / "replay_dual_notch_train24.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if OUT_MAT.exists() or OUT_JSON.exists():
        raise RuntimeError("Refusing to overwrite parity inputs.")
    report = json.loads(SOURCE_REPORT.read_text(encoding="utf-8-sig"))
    expected_ids = ["DL1018_DEV_T1_C10_W09", "DL1018_DEV_T3_C09_W09"]
    rows = report.get("results", [])
    if report.get("status") != "FAIL_FIXED_FROZEN_REPLAY" or [r.get("scene_id") for r in rows] != expected_ids:
        raise RuntimeError("Frozen report is not the expected two-scene physical TRAIN diagnostic.")

    spec = importlib.util.spec_from_file_location("fixed_w09_replay", REPLAY_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen replay recurrence.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    mat: dict[str, object] = {}
    scene_metadata = []
    for j, row in enumerate(rows, start=1):
        scene_id = row["scene_id"]
        raw_path = Path(row["candidate_raw_path"]).resolve(strict=True)
        raw_sha = sha256(raw_path)
        if raw_sha.lower() != row["candidate_raw_sha256"].lower():
            raise RuntimeError(f"Candidate raw hash changed: {scene_id}")
        with h5py.File(raw_path, "r") as raw:
            log = raw["log"]
            action = np.asarray(log["stage1_position_held_applied_acceleration_mps2"][()], dtype=np.float64).T
            event = np.asarray(log["stage1_position_event"][()], dtype=bool).reshape(-1)
        if action.shape != (20_000, 3) or event.shape != (20_000,) or int(event.sum()) != 1999:
            raise RuntimeError(f"Unexpected frozen TRAIN action/event shape: {scene_id}")
        filtered, clips = module.dual_notch_event_replay(action, event)
        b_rows = [module.notch_coefficients(f)[0] for f in module.NOTCHES]
        a_rows = [module.notch_coefficients(f)[1] for f in module.NOTCHES]
        prefix = f"scene{j}_"
        mat[prefix + "id"] = scene_id
        mat[prefix + "action_mps2"] = action.T
        mat[prefix + "event"] = event.reshape(1, -1).astype(np.uint8)
        mat[prefix + "expected_mps2"] = filtered.T
        mat[prefix + "b"] = np.asarray(b_rows, dtype=np.float64)
        mat[prefix + "a"] = np.asarray(a_rows, dtype=np.float64)
        mat[prefix + "clip_count"] = np.asarray([[clips]], dtype=np.float64)
        scene_metadata.append({
            "scene_id": scene_id,
            "split": "TRAIN_C5_24",
            "fold_id": row["fold_id"],
            "candidate_raw_path": str(raw_path),
            "candidate_raw_sha256": raw_sha,
            "transitions": 20_000,
            "event_count": int(event.sum()),
            "expected_clip_count": clips,
        })

    savemat(OUT_MAT, mat, do_compression=True, long_field_names=True)
    metadata = {
        "schema": "POSITION_COMPENSATION_DUAL_NOTCH_MATLAB_PARITY_INPUTS_V1",
        "status": "PASS_TRAIN_PARITY_INPUTS_READY",
        "study_id": "position_compensation_dual_notch_train_diag_online_noPlant_v1",
        "source_frozen_report_path": str(SOURCE_REPORT.resolve()),
        "source_frozen_report_sha256": sha256(SOURCE_REPORT),
        "frozen_replay_status_preserved": report["status"],
        "mat_path": str(OUT_MAT.resolve()),
        "mat_sha256": sha256(OUT_MAT),
        "parameter_sweep": False,
        "scenes": scene_metadata,
        "Plant_calls": 0,
        "TEST_read": False,
        "VAL_read": False,
        "inertia_reconstruction_enabled": False,
    }
    OUT_JSON.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"mat": str(OUT_MAT.resolve()), "status": metadata["status"], "scenes": scene_metadata}, indent=2))


if __name__ == "__main__":
    main()
