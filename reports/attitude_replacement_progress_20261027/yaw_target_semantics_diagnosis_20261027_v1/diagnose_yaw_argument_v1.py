from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IDENTITY = ROOT / "reports" / "attitude_replacement_progress_20261027" / "hf_attitude_next_taskbook_luna_v1" / "HF_RAW_INPUT_IDENTITY_v2.csv"
G = 9.8
MAX_TILT = math.radians(30.0)
N_TRANSITIONS = 20_000
ALIGN_TOL = 1e-10


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside_root(path: Path) -> bool:
    root_s = str(ROOT.resolve()).casefold()
    path_s = str(path.resolve()).casefold()
    return os.path.commonpath([root_s, path_s]) == root_s


def wrap(angle: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(angle), np.cos(angle))


def force_to_euler(force: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    """Reproduce baseline_force_to_attitude for an unprojected force direction."""
    fx, fy, fz = force[..., 0], force[..., 1], force[..., 2]
    a = np.cos(yaw) * fx + np.sin(yaw) * fy
    b = np.sin(yaw) * fx - np.cos(yaw) * fy
    roll = np.arctan2(b, np.hypot(fz, a))
    pitch = np.arctan2(a, fz)
    return np.stack((roll, pitch, yaw), axis=-1)


def body_z(euler: np.ndarray) -> np.ndarray:
    """Third body axis in inertial coordinates for ZYX Euler [roll,pitch,yaw]."""
    roll, pitch, yaw = euler[..., 0], euler[..., 1], euler[..., 2]
    return np.stack(
        (
            np.cos(yaw) * np.sin(pitch) * np.cos(roll) + np.sin(yaw) * np.sin(roll),
            np.sin(yaw) * np.sin(pitch) * np.cos(roll) - np.cos(yaw) * np.sin(roll),
            np.cos(pitch) * np.cos(roll),
        ),
        axis=-1,
    )


def angle_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    dot = np.sum(a * b, axis=-1)
    return np.arccos(np.clip(dot, -1.0, 1.0))


def task_attitude(acceleration: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    force = acceleration + np.array([0.0, 0.0, G])
    euler = force_to_euler(force, yaw)
    tilt = np.hypot(euler[:, 0], euler[:, 1])
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, np.finfo(float).tiny))
    euler[:, :2] *= scale[:, None]
    return euler


def geodesic_rmse(a: np.ndarray, b: np.ndarray) -> float:
    ra = Rotation.from_euler("xyz", a)
    rb = Rotation.from_euler("xyz", b)
    theta = (ra.inv() * rb).magnitude()
    return float(np.sqrt(np.mean(theta * theta)))


def self_check() -> None:
    force = np.array([[0.2, -0.1, 9.8], [-0.6, 0.4, 10.1], [0.0, 0.3, 9.2]])
    yaw = np.array([0.0, 0.7, -1.2])
    euler = force_to_euler(force, yaw)
    expected = force / np.linalg.norm(force, axis=1, keepdims=True)
    error = float(np.max(angle_between(body_z(euler), expected)))
    if error > 1e-10:
        raise RuntimeError(f"force/euler direction self-check failed: {error:.3e} rad")


def read_dataset(h5: h5py.File, key: str) -> np.ndarray:
    if key not in h5:
        raise RuntimeError(f"missing locked raw field: {key}")
    value = np.asarray(h5[key][()], dtype=np.float64)
    if not np.all(np.isfinite(value)):
        raise RuntimeError(f"nonfinite values in {key}")
    return value


def read_scene(row: dict[str, str]) -> dict[str, Any]:
    raw = Path(row["raw_path"])
    if not raw.is_file() or not inside_root(raw):
        raise RuntimeError(f"raw missing or outside repository: {raw}")
    if row.get("raw_match", "").lower() != "true":
        raise RuntimeError(f"locked identity CSV does not mark SHA as matching: {raw}")
    expected = row["raw_expected_sha256"].lower()
    observed = sha256_file(raw)
    if observed != expected or observed != row["raw_actual_sha256"].lower():
        raise RuntimeError(f"raw SHA mismatch: {raw}")

    with h5py.File(raw, "r") as h5:
        state = read_dataset(h5, "log/state")
        target = read_dataset(h5, "log/command_filter_target_euler").T
        raw_outer = read_dataset(h5, "log/raw_outer_attitude").T
        time = read_dataset(h5, "log/time").reshape(-1)
        transition = read_dataset(h5, "log/transition_time").reshape(-1)
        acceleration = read_dataset(h5, "scene/reference/acceleration").T
        desired_yaw = read_dataset(h5, "scene/reference/yaw").reshape(-1)

    if state.shape != (12, N_TRANSITIONS + 1):
        raise RuntimeError(f"unexpected state shape {state.shape} in {raw}")
    if target.shape != (N_TRANSITIONS, 3) or raw_outer.shape != target.shape:
        raise RuntimeError(f"unexpected target/raw_outer shapes in {raw}")
    if time.shape != (N_TRANSITIONS + 1,) or transition.shape != (N_TRANSITIONS,):
        raise RuntimeError(f"unexpected time grid shapes in {raw}")
    if acceleration.shape != (N_TRANSITIONS + 1, 3) or desired_yaw.shape != (N_TRANSITIONS + 1,):
        raise RuntimeError(f"unexpected reference shapes in {raw}")
    if np.max(np.abs(time[:N_TRANSITIONS] - transition)) > ALIGN_TOL:
        raise RuntimeError(f"time/transition alignment failed in {raw}")
    if np.max(np.abs(target - raw_outer)) > ALIGN_TOL:
        raise RuntimeError(f"raw_outer/command-target identity failed in {raw}")

    current_yaw = state[8, :N_TRANSITIONS]
    ref_yaw = desired_yaw[:N_TRANSITIONS]
    if np.max(np.abs(wrap(target[:, 2] - ref_yaw))) > ALIGN_TOL:
        raise RuntimeError(f"logged target yaw differs from desired reference yaw in {raw}")
    if np.max(np.hypot(target[:, 0], target[:, 1])) >= MAX_TILT - 1e-8:
        raise RuntimeError(f"tilt projection may have occurred; stop rather than invert it: {raw}")

    # The old helper receives actual yaw, returns roll/pitch/yaw, then its
    # callers replace the output yaw with ref_yaw. Reconstruct the unchanged
    # force direction from those same roll/pitch at the actual yaw.
    old_helper_euler = target.copy()
    old_helper_euler[:, 2] = current_yaw
    requested_b3 = body_z(old_helper_euler)

    # Re-express that same body-z direction at desired yaw.
    corrected = force_to_euler(requested_b3, ref_yaw)
    corrected[:, 2] = ref_yaw
    corrected_b3 = body_z(corrected)

    # Current target uses desired yaw with roll/pitch calculated at current yaw.
    current_target_b3 = body_z(target)
    task = task_attitude(acceleration[:N_TRANSITIONS], ref_yaw)

    return {
        "scene_id": row["scene_id"],
        "method": row["method"],
        "raw_path": str(raw),
        "raw_sha256": observed,
        "current_target_task_so3_rmse_rad": geodesic_rmse(task, target),
        "corrected_target_task_so3_rmse_rad": geodesic_rmse(task, corrected),
        "target_task_so3_change_rad": geodesic_rmse(task, corrected) - geodesic_rmse(task, target),
        "current_target_to_requested_force_axis_rmse_rad": float(
            np.sqrt(np.mean(angle_between(current_target_b3, requested_b3) ** 2))
        ),
        "corrected_target_to_requested_force_axis_rmse_rad": float(
            np.sqrt(np.mean(angle_between(corrected_b3, requested_b3) ** 2))
        ),
        "corrected_force_axis_max_abs_error_rad": float(np.max(angle_between(corrected_b3, requested_b3))),
        "target_shift_so3_rmse_rad": geodesic_rmse(target, corrected),
        "actual_minus_desired_yaw_rmse_rad": float(np.sqrt(np.mean(wrap(current_yaw - ref_yaw) ** 2))),
        "actual_minus_desired_yaw_max_abs_rad": float(np.max(np.abs(wrap(current_yaw - ref_yaw)))),
        "max_logged_target_tilt_rad": float(np.max(np.hypot(target[:, 0], target[:, 1]))),
        "samples": N_TRANSITIONS,
    }


def scene_macro(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    selected = [row for row in rows if row["method"] == method]
    if len(selected) != 28 or len({row["scene_id"] for row in selected}) != 28:
        raise RuntimeError(f"expected 28 distinct scenes for {method}, got {len(selected)}")
    fields = [
        "current_target_task_so3_rmse_rad",
        "corrected_target_task_so3_rmse_rad",
        "target_task_so3_change_rad",
        "current_target_to_requested_force_axis_rmse_rad",
        "corrected_target_to_requested_force_axis_rmse_rad",
        "corrected_force_axis_max_abs_error_rad",
        "target_shift_so3_rmse_rad",
        "actual_minus_desired_yaw_rmse_rad",
        "actual_minus_desired_yaw_max_abs_rad",
    ]
    result: dict[str, Any] = {"scene_count": len(selected)}
    for field in fields:
        values = np.array([float(row[field]) for row in selected], dtype=np.float64)
        result[field + "_equal_scene_mean"] = float(values.mean())
        result[field + "_scene_p95"] = float(np.quantile(values, 0.95))
        result[field + "_scene_max"] = float(values.max())
    result["scenes_improved_task_target"] = sum(
        row["target_task_so3_change_rad"] < -1e-12 for row in selected
    )
    return result


def main() -> None:
    self_check()
    with IDENTITY.open("r", encoding="utf-8-sig", newline="") as stream:
        identity_rows = list(csv.DictReader(stream))
    rows = [
        row for row in identity_rows
        if row["method"] in {"Candidate", "C5"} and row["scene_id"].endswith(tuple(f"W{i:02d}" for i in range(9, 15)))
    ]
    if len(rows) != 56:
        raise RuntimeError(f"expected 56 Candidate/C5 HF identity rows, got {len(rows)}")
    if len({row["scene_id"] for row in rows}) != 28:
        raise RuntimeError("expected exactly 28 unique HF scenes")
    identity_sha = sha256_file(IDENTITY)

    scene_results = [read_scene(row) for row in sorted(rows, key=lambda x: (x["scene_id"], x["method"]))]
    macros = {method: scene_macro(scene_results, method) for method in ("Candidate", "C5")}

    result = {
        "schema": "DL1018_YAW_ARGUMENT_OFFLINE_DIAGNOSTIC_V1",
        "status": "PASS_COMPLETE",
        "question": "same logged force direction re-expressed at desired yaw vs logged roll/pitch computed at actual yaw then combined with desired yaw",
        "scope": {
            "scenes": 28,
            "raw_trajectories": 56,
            "methods": ["Candidate", "C5"],
            "samples_per_trajectory": N_TRANSITIONS,
            "raw_files_copied": 0,
            "Plant_calls": 0,
            "MATLAB_started": False,
            "training_steps": 0,
            "TEST_read": False,
            "inertia_read_or_reconstructed": False,
        },
        "input_identity_csv": str(IDENTITY),
        "input_identity_csv_sha256": identity_sha,
        "gravity_mps2": G,
        "task_tilt_cap_rad": MAX_TILT,
        "macro_equal_scene": macros,
        "scenes": scene_results,
        "interpretation_limit": "target-level algebraic counterfactual on recorded states; no plant propagation, no closed-loop outcome, no causal score claim",
        "script_sha256": sha256_file(Path(__file__).resolve()),
    }
    result_path = HERE / "RESULT_v1.json"
    csv_path = HERE / "PER_SCENE_v1.csv"
    identity_out = HERE / "INPUT_RECHECK_v1.json"
    for path in (result_path, csv_path, identity_out):
        if path.exists():
            raise FileExistsError(path)

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = list(scene_results[0].keys())
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(scene_results)
    input_recheck = {
        "status": "PASS_ALL_56_RAW_IDENTITIES",
        "identity_csv_sha256": identity_sha,
        "raw_count": len(scene_results),
        "raw_identities": [
            {"scene_id": row["scene_id"], "method": row["method"], "raw_sha256": row["raw_sha256"]}
            for row in scene_results
        ],
    }
    identity_out.write_text(json.dumps(input_recheck, ensure_ascii=False, indent=2), encoding="utf-8")

    output_bytes = sum(path.stat().st_size for path in (result_path, csv_path, identity_out))
    if output_bytes > 1024**3:
        raise RuntimeError(f"output budget exceeded: {output_bytes} bytes")
    print(json.dumps({"status": result["status"], "output_bytes": output_bytes, "macro_equal_scene": macros}, ensure_ascii=False))


if __name__ == "__main__":
    main()
