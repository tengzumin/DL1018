from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IDENTITY = ROOT / "reports/attitude_replacement_progress_20261027/hf_attitude_next_taskbook_luna_v1/HF_RAW_INPUT_IDENTITY_v2.csv"
PRIOR_RESULT = ROOT / "reports/attitude_replacement_progress_20261027/yaw_target_semantics_diagnosis_20261027_v1/RESULT_v1.json"
RECHECK = ROOT / "reports/attitude_replacement_progress_20261027/yaw_target_semantics_diagnosis_20261027_v1/INPUT_RECHECK_v1.json"

EXPECTED_HASHES = {
    IDENTITY: "71f3d159954198a066ef8cc00151e07a90ef4de92f216db6990a07da045c2c1a",
    PRIOR_RESULT: "4a5d9230e8bf407da93d1a3912f13a1021e5ba3c9cef2a468c1a155692c3dff4",
    RECHECK: "7873fa9fda44349d6a142c27d14294498e099b1d403a1341b19ecab9e742d793",
}
SOURCE_HASHES = {
    ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m": "a1b9e47992da41b49373f409d9333048b6130698d80614817d64bbc1a652ddcc",
    ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/core/command_filter_step.m": "15c7eb27162e1971a1164304830f4afd3af35eb9bd709291e969dbfefd0d262b",
    ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/candidate_runner_work/matlab/core/baseline_force_to_attitude.m": "ef42d1d08af24ed82da307a4d886b0c205e28e754177765a2584e3e9bb0cd039",
    ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/LOCKED_CFG.json": "613aff59c4036ae488cb373afacb3ef1383faa970c8dcd99ffac68462cb6d95f",
    ROOT / "experiments/dl_attitude_replacement_20261026/attitude_task_inner_hf_w09_w14_diagnosis_20261027_v1/HF_W09_W14_attitude_path_by_scene_phase.csv": "87e5780879b5c5ae9ff8be8eb8cae3f99700b939938239dc15c4827ee412daaa",
}

G = 9.8
MAX_TILT = math.radians(30.0)
BETA = 0.25
N_TRANSITIONS = 20_000
DT = 0.001
WN = np.array([18.0, 18.0, 12.0])
ZETA = np.ones(3)
ACCEL_LIMIT = np.array([np.inf, np.inf, 6.0])
ALIGN_TOL = 1e-10
FILTER_ANGLE_TOL = 1e-8
FILTER_RATE_TOL = 1e-8
OUTPUT_CAP = 100 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside_root(path: Path) -> bool:
    return os.path.commonpath([str(ROOT.resolve()).casefold(), str(path.resolve()).casefold()]) == str(ROOT.resolve()).casefold()


def wrap(angle: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(angle), np.cos(angle))


def force_to_euler(force: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    """Match the frozen force-to-attitude adapter for a nonzero vertical force."""
    fx, fy, fz = force[..., 0], force[..., 1], force[..., 2]
    a = np.cos(yaw) * fx + np.sin(yaw) * fy
    b = np.sin(yaw) * fx - np.cos(yaw) * fy
    roll = np.arctan2(b, np.hypot(fz, a))
    pitch = np.arctan2(a, fz)
    return np.stack((roll, pitch, yaw), axis=-1)


def task_attitude(acceleration: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    force = acceleration + np.array([0.0, 0.0, G])
    euler = force_to_euler(force, yaw)
    tilt = np.hypot(euler[:, 0], euler[:, 1])
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, np.finfo(float).tiny))
    euler[:, :2] *= scale[:, None]
    return euler


def geodesic_samples(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ra = Rotation.from_euler("xyz", a)
    rb = Rotation.from_euler("xyz", b)
    return (ra.inv() * rb).magnitude()


def geodesic_rmse(a: np.ndarray, b: np.ndarray) -> float:
    theta = geodesic_samples(a, b)
    return float(np.sqrt(np.mean(theta * theta)))


def geodesic_blend(position_target: np.ndarray, task_target: np.ndarray) -> np.ndarray:
    rp = Rotation.from_euler("xyz", position_target)
    rt = Rotation.from_euler("xyz", task_target)
    relative = rp.inv() * rt
    mixed = rp * Rotation.from_rotvec(BETA * relative.as_rotvec())
    return mixed.as_euler("xyz")


def read_allowed_dataset(h5: h5py.File, key: str) -> np.ndarray:
    allowed = {
        "log/command_filter_target_euler",
        "log/filtered_attitude_reference",
        "log/filtered_attitude_rate",
        "log/transition_time",
        "log/time",
        "scene/reference/acceleration",
        "scene/reference/yaw",
    }
    if key not in allowed:
        raise RuntimeError(f"script attempted to read a non-whitelisted field: {key}")
    if key not in h5:
        raise RuntimeError(f"missing locked raw field: {key}")
    value = np.asarray(h5[key][()], dtype=np.float64)
    if not np.all(np.isfinite(value)):
        raise RuntimeError(f"nonfinite values in {key}")
    return value


def validate_locks() -> tuple[list[dict[str, str]], dict[str, Any]]:
    for path, expected_hash in EXPECTED_HASHES.items():
        observed = sha256_file(path)
        if observed != expected_hash:
            raise RuntimeError(f"locked file SHA mismatch: {path} expected={expected_hash} observed={observed}")
    for path, expected_hash in SOURCE_HASHES.items():
        observed = sha256_file(path)
        if observed != expected_hash:
            raise RuntimeError(f"locked source/config SHA mismatch: {path} expected={expected_hash} observed={observed}")

    with IDENTITY.open("r", newline="", encoding="utf-8-sig") as stream:
        all_rows = list(csv.DictReader(stream))
    def selected_hf_scene(scene_id: str) -> bool:
        match = re.search(r"_W(\d{2})$", scene_id)
        return bool(match and 9 <= int(match.group(1)) <= 14)

    rows = [row for row in all_rows if row.get("method") in {"Candidate", "C5"} and selected_hf_scene(row.get("scene_id", ""))]
    if len(rows) != 56 or len({(r["scene_id"], r["method"]) for r in rows}) != 56:
        raise RuntimeError(f"expected 56 unique locked Candidate/C5 W09-W14 rows; found {len(rows)}")
    if {r["method"] for r in rows} != {"Candidate", "C5"}:
        raise RuntimeError("locked methods do not equal Candidate and C5")
    candidate_scenes = {r["scene_id"] for r in rows if r["method"] == "Candidate"}
    c5_scenes = {r["scene_id"] for r in rows if r["method"] == "C5"}
    if len(candidate_scenes) != 28 or candidate_scenes != c5_scenes:
        raise RuntimeError("Candidate and C5 do not contain the same 28 locked HF scenes")
    if any(r.get("raw_match", "").lower() != "true" or r.get("root_contained", "").lower() != "true" for r in rows):
        raise RuntimeError("identity table does not mark every selected raw as matched and root-contained")

    result = json.loads(PRIOR_RESULT.read_text(encoding="utf-8"))
    recheck = json.loads(RECHECK.read_text(encoding="utf-8"))
    if result.get("status") != "PASS_COMPLETE" or result.get("scope", {}).get("raw_trajectories") != 56:
        raise RuntimeError("prior yaw diagnostic is not complete for the locked 56-raw cohort")
    if recheck.get("status") != "PASS_ALL_56_RAW_IDENTITIES" or recheck.get("raw_count") != 56:
        raise RuntimeError("prior raw identity recheck is not PASS_ALL_56_RAW_IDENTITIES")
    if result.get("input_identity_csv_sha256", "").lower() != EXPECTED_HASHES[IDENTITY]:
        raise RuntimeError("prior result binds a different identity CSV")
    prior_rows = {
        (r["scene_id"], r["method"], str(Path(r["raw_path"]).resolve()).casefold(), r["raw_sha256"].lower())
        for r in result.get("scenes", [])
    }
    csv_rows = {
        (r["scene_id"], r["method"], str(Path(r["raw_path"]).resolve()).casefold(), r["raw_expected_sha256"].lower())
        for r in rows
    }
    if len(prior_rows) != 56 or prior_rows != csv_rows:
        raise RuntimeError("the 56 identity rows do not exactly match the prior locked result")
    recheck_rows = {
        (r["scene_id"], r["method"], r["raw_sha256"].lower())
        for r in recheck.get("raw_identities", [])
    }
    expected_recheck_rows = {(r["scene_id"], r["method"], r["raw_expected_sha256"].lower()) for r in rows}
    if len(recheck_rows) != 56 or recheck_rows != expected_recheck_rows:
        raise RuntimeError("prior input recheck does not exactly match the locked 56 raw identities")
    return rows, {"prior_result": result, "recheck": recheck}


def read_raw(row: dict[str, str]) -> dict[str, Any]:
    raw = Path(row["raw_path"])
    if not raw.is_file() or not inside_root(raw):
        raise RuntimeError(f"raw missing or outside repository: {raw}")
    observed = sha256_file(raw)
    expected = row["raw_expected_sha256"].lower()
    if observed != expected or observed != row["raw_actual_sha256"].lower():
        raise RuntimeError(f"locked raw SHA mismatch: {raw}")

    # This is a selective HDF5 read; no other MATLAB variables are materialized.
    with h5py.File(raw, "r") as h5:
        target = read_allowed_dataset(h5, "log/command_filter_target_euler").T
        filtered = read_allowed_dataset(h5, "log/filtered_attitude_reference").T
        filtered_rate = read_allowed_dataset(h5, "log/filtered_attitude_rate").T
        time = read_allowed_dataset(h5, "log/time").reshape(-1)
        transition = read_allowed_dataset(h5, "log/transition_time").reshape(-1)
        acceleration = read_allowed_dataset(h5, "scene/reference/acceleration").T
        yaw = read_allowed_dataset(h5, "scene/reference/yaw").reshape(-1)

    if target.shape != (N_TRANSITIONS, 3) or filtered.shape != target.shape or filtered_rate.shape != target.shape:
        raise RuntimeError(f"unexpected target/filter shapes in {raw}: {target.shape}, {filtered.shape}, {filtered_rate.shape}")
    if time.shape != (N_TRANSITIONS + 1,) or transition.shape != (N_TRANSITIONS,):
        raise RuntimeError(f"unexpected time shapes in {raw}: {time.shape}, {transition.shape}")
    if acceleration.shape != (N_TRANSITIONS + 1, 3) or yaw.shape != (N_TRANSITIONS + 1,):
        raise RuntimeError(f"unexpected reference shapes in {raw}: {acceleration.shape}, {yaw.shape}")
    if np.max(np.abs(time[:N_TRANSITIONS] - transition)) > ALIGN_TOL:
        raise RuntimeError(f"time/transition alignment failed in {raw}")
    if abs(time[0]) > ALIGN_TOL or abs(time[-1] - 20.0) > ALIGN_TOL:
        raise RuntimeError(f"unexpected 0-20 s time grid in {raw}")
    if np.max(np.abs(np.diff(time) - DT)) > ALIGN_TOL:
        raise RuntimeError(f"unexpected sample period in {raw}")

    return {
        "scene_id": row["scene_id"],
        "method": row["method"],
        "raw_path": str(raw),
        "raw_sha256": observed,
        "target": target,
        "filtered": filtered,
        "filtered_rate": filtered_rate,
        "time": time,
        "transition": transition,
        "acceleration": acceleration[:N_TRANSITIONS],
        "yaw": yaw[:N_TRANSITIONS],
    }


def replay_filter(target: np.ndarray, initial_euler: np.ndarray, initial_rate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    euler = np.empty((N_TRANSITIONS, 3), dtype=np.float64)
    rate = np.empty_like(euler)
    state_euler = initial_euler.copy()
    state_rate = initial_rate.copy()
    for i in range(N_TRANSITIONS):
        euler[i] = state_euler
        rate[i] = state_rate
        error = wrap(target[i] - state_euler)
        requested = WN * WN * error - 2.0 * ZETA * WN * state_rate
        acceleration = np.minimum(np.maximum(requested, -ACCEL_LIMIT), ACCEL_LIMIT)
        state_rate = state_rate + DT * acceleration
        state_euler = wrap(state_euler + DT * state_rate)
    return euler, rate


def process_raw(data: dict[str, Any]) -> dict[str, Any]:
    target = data["target"]
    logged_filter = data["filtered"]
    logged_rate = data["filtered_rate"]
    # Seed from the first logged filter state and require the frozen recurrence
    # to reproduce all original logged states before evaluating the blend.
    base_filter, base_rate = replay_filter(target, logged_filter[0].copy(), logged_rate[0].copy())
    replay_angle_residual = float(np.max(np.abs(wrap(base_filter - logged_filter))))
    replay_rate_residual = float(np.max(np.abs(base_rate - logged_rate)))
    if replay_angle_residual > FILTER_ANGLE_TOL or replay_rate_residual > FILTER_RATE_TOL:
        raise RuntimeError(
            f"original filter replay identity failed for {data['scene_id']} {data['method']}: "
            f"angle={replay_angle_residual:.3e}, rate={replay_rate_residual:.3e}"
        )

    task = task_attitude(data["acceleration"], data["yaw"])
    mixed_target = geodesic_blend(target, task)
    tilt = np.hypot(mixed_target[:, 0], mixed_target[:, 1])
    tilt_over_cap = int(np.count_nonzero(tilt > MAX_TILT + 1e-10))
    mixed_filter, _ = replay_filter(mixed_target, logged_filter[0].copy(), logged_rate[0].copy())

    return {
        "scene_id": data["scene_id"],
        "method": data["method"],
        "raw_sha256": data["raw_sha256"],
        "transition_count": N_TRANSITIONS,
        "time_grid_max_abs_error_s": float(np.max(np.abs(data["time"][:N_TRANSITIONS] - data["transition"]))),
        "filter_replay_max_angle_residual_rad": replay_angle_residual,
        "filter_replay_max_rate_residual_rad_s": replay_rate_residual,
        "task_to_original_command_rmse_rad": geodesic_rmse(task, target),
        "task_to_mixed_command_rmse_rad": geodesic_rmse(task, mixed_target),
        "original_to_mixed_command_rmse_rad": geodesic_rmse(target, mixed_target),
        "task_to_original_filtered_rmse_rad": geodesic_rmse(task, logged_filter),
        "task_to_mixed_filtered_rmse_rad": geodesic_rmse(task, mixed_filter),
        "mixed_command_max_tilt_rad": float(np.max(tilt)),
        "mixed_command_tilt_over_30deg_samples": tilt_over_cap,
        "mixed_command_tilt_over_30deg_fraction": float(tilt_over_cap / N_TRANSITIONS),
    }


def macro(rows: list[dict[str, Any]], method: str, field: str) -> float:
    selected = [row[field] for row in rows if row["method"] == method]
    if len(selected) != 28:
        raise RuntimeError(f"expected 28 scenes for {method}, got {len(selected)}")
    return float(np.mean(selected))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    status_path = HERE / "STATUS_v1.json"
    try:
        rows, _ = validate_locks()
        per_scene: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda r: (r["scene_id"], r["method"])):
            per_scene.append(process_raw(read_raw(row)))

        candidate_blend = macro(per_scene, "Candidate", "task_to_mixed_filtered_rmse_rad")
        threshold = 0.058949
        valid_tilt = all(row["mixed_command_tilt_over_30deg_samples"] == 0 for row in per_scene)
        gate_pass = candidate_blend <= threshold and valid_tilt
        summary = {
            "schema": "DL1018_TASK_ATTITUDE_BLEND_SHADOW_V1",
            "status": "PASS_GATE" if gate_pass else "PASS_DIAGNOSTIC_GATE_REJECTED",
            "beta": BETA,
            "macro_equal_scene_rmse_rad": {
                method: {
                    field: macro(per_scene, method, field)
                    for field in (
                        "task_to_original_command_rmse_rad",
                        "task_to_mixed_command_rmse_rad",
                        "original_to_mixed_command_rmse_rad",
                        "task_to_original_filtered_rmse_rad",
                        "task_to_mixed_filtered_rmse_rad",
                    )
                }
                for method in ("Candidate", "C5")
            },
            "candidate_frozen_threshold_rad": threshold,
            "candidate_gate_pass": gate_pass,
            "mixed_tilt_cap_all_scenes_pass": valid_tilt,
            "scope": {
                "scenes": 28,
                "raw_trajectories": 56,
                "methods": ["Candidate", "C5"],
                "samples_per_trajectory": N_TRANSITIONS,
                "Plant_calls": 0,
                "MATLAB_started": False,
                "training_steps": 0,
                "B_raw_read": False,
                "TEST_read": False,
                "inertia_or_plant_truth_read": False,
                "raw_files_copied": 0,
            },
            "identity_csv_sha256": EXPECTED_HASHES[IDENTITY],
            "prior_result_sha256": EXPECTED_HASHES[PRIOR_RESULT],
            "input_recheck_sha256": EXPECTED_HASHES[RECHECK],
            "reviewed_source_sha256": {str(path.relative_to(ROOT)): value for path, value in SOURCE_HASHES.items()},
            "interpretation_limit": "same-state offline command/filter shadow only; no Plant propagation or closed-loop performance claim",
        }
        with (HERE / "PER_SCENE_v1.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(per_scene[0].keys()))
            writer.writeheader()
            writer.writerows(per_scene)
        write_json(HERE / "RESULT_v1.json", summary)
        script_hash = sha256_file(Path(__file__).resolve())
        write_json(
            status_path,
            {
                "status": summary["status"],
                "script_sha256": script_hash,
                "raw_count": 56,
                "beta": BETA,
                "Plant_calls": 0,
                "MATLAB_started": False,
                "training_steps": 0,
                "B_raw_read": False,
                "TEST_read": False,
                "inertia_or_plant_truth_read": False,
            },
        )
        summary["output_cap_bytes"] = OUTPUT_CAP
        for _ in range(3):
            write_json(HERE / "RESULT_v1.json", summary)
            total_bytes = sum(p.stat().st_size for p in HERE.iterdir() if p.is_file())
            summary["output_bytes_including_status"] = total_bytes
            if total_bytes > OUTPUT_CAP:
                raise RuntimeError(f"output cap exceeded: {total_bytes} > {OUTPUT_CAP}")
        return 0
    except Exception as exc:
        write_json(status_path, {"status": "ABORTED", "reason": str(exc), "script_sha256": sha256_file(Path(__file__).resolve())})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
