"""Audit the frozen TCN labels against B's logged attitude-RBF action.

Read-only over the locked VAL48 raw logs and dataset.  The controller J0 values
come from the MATLAB R2025b receipt produced by the project's fixed-controller
parameter path.  No TEST files, Plant calls, or time-varying inertia estimates
are used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np


TASK_DIR = Path(__file__).resolve().parent
DATASET_DIR = TASK_DIR / "dataset_v3_corrected"
MANIFEST_PATH = DATASET_DIR / "DATASET_MANIFEST_v1.json"
NPZ_PATH = DATASET_DIR / "attitude_residual_train_val_v1.npz"
J0_AUDIT_PATH = TASK_DIR / "CONTROLLER_J0_AUDIT_VAL48_v1.json"
OUT_PATH = TASK_DIR / "SUPERVISION_TARGET_AUDIT_v1.json"
EXPECTED_EVENTS = 1999


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rms(value: np.ndarray) -> np.ndarray:
    return np.sqrt(np.mean(np.square(value, dtype=np.float64), axis=0))


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    j0_audit = json.loads(J0_AUDIT_PATH.read_text(encoding="utf-8"))
    if (manifest.get("status") != "PASS" or manifest.get("test_data_read") is not False
            or manifest.get("split_counts") != {"TRAIN": 768, "VAL": 48}
            or j0_audit.get("status") != "PASS" or j0_audit.get("test_data_read") is not False
            or j0_audit.get("plant_invoked") is not False):
        raise ValueError("frozen TRAIN/VAL-only dataset or fixed-controller J0 receipt is invalid")
    rows = [row for row in manifest["rows"] if row["split"] == "VAL"]
    j0_rows = {row["scene_id"]: row for row in j0_audit["records"]}
    if len(rows) != 48 or set(j0_rows) != {row["scene_id"] for row in rows}:
        raise ValueError("VAL48 rows differ between data and controller-J0 receipts")

    with np.load(NPZ_PATH, allow_pickle=False) as data:
        val_x = np.asarray(data["val_x"], dtype=np.float64)
        val_y = np.asarray(data["val_y"], dtype=np.float64)
    if val_x.shape != (48, EXPECTED_EVENTS, 13) or val_y.shape != (48, EXPECTED_EVENTS, 3):
        raise ValueError(f"unexpected VAL feature/target shapes: {val_x.shape}, {val_y.shape}")

    per_scene: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        raw_path = Path(row["raw_path"])
        start_path = Path(row["run_start_path"])
        if sha256(raw_path) != row["raw_sha256"].lower():
            raise ValueError(f"VAL raw SHA mismatch: {row['scene_id']}")
        if sha256(start_path) != row["run_start_sha256"].lower():
            raise ValueError(f"VAL run-start SHA mismatch: {row['scene_id']}")

        j0 = np.asarray(j0_rows[row["scene_id"]]["controller_fixed_J0"], dtype=np.float64)
        j_cfg = np.asarray(row["nominal_inertia_kg_m2"], dtype=np.float64)
        beta_rise = float(j0_rows[row["scene_id"]]["beta_rise_time_s"])
        if (j0.shape != (3, 3) or j_cfg.shape != (3, 3) or beta_rise <= 0
                or not np.all(np.isfinite(j0))):
            raise ValueError(f"invalid fixed controller parameters: {row['scene_id']}")

        with h5py.File(raw_path, "r") as raw:
            log = raw["log"]
            event_flags = np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool)
            event_indices = np.flatnonzero(event_flags)
            expected = np.arange(10, 20000, 10, dtype=np.int64)
            if not np.array_equal(event_indices, expected):
                raise ValueError(f"event schedule mismatch: {row['scene_id']}")
            state = np.asarray(log["state"], dtype=np.float64).T
            transition_time = np.asarray(log["transition_time"], dtype=np.float64).reshape(-1)
            nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64)[:, event_indices].T
            teacher_raw = np.asarray(log["rbf_output_raw"], dtype=np.float64)[:, event_indices].T
            teacher_applied_torque = np.asarray(
                log["attitude_rbf_compensation_torque_Nm"], dtype=np.float64
            )[:, event_indices].T

        if state.shape != (20001, 12) or teacher_raw.shape != (EXPECTED_EVENTS, 3):
            raise ValueError(f"raw array shape mismatch: {row['scene_id']}")

        omega = state[event_indices, 9:12]
        gyro = np.cross(omega, omega @ j0.T)
        alpha_bs_actual = np.linalg.solve(j0, (nominal_torque - gyro).T).T
        alpha_bs_stored = val_x[index, :, 6:9]
        alpha_measured = (
            state[event_indices + 10, 9:12] - state[event_indices, 9:12]
        ) / 0.010
        current_label = val_y[index]
        beta = np.minimum(transition_time[event_indices] / beta_rise, 1.0)
        expected_teacher_torque = (beta[:, None] * teacher_raw) @ j0.T

        stored_alpha_error = alpha_bs_stored - alpha_bs_actual
        feature_error_rms = rms(stored_alpha_error)
        actual_alpha_rms = rms(alpha_bs_actual)
        current_label_error = current_label - (alpha_measured - alpha_bs_stored)
        teacher_rms = rms(teacher_raw)
        label_rms = rms(current_label)
        teacher_ratio = float(np.linalg.norm(teacher_rms) / max(np.linalg.norm(label_rms), 1e-30))
        torque_map_error = expected_teacher_torque - teacher_applied_torque
        torque_map_relative_error = float(
            np.linalg.norm(torque_map_error) / max(np.linalg.norm(teacher_applied_torque), 1e-30)
        )
        inertia_relative_error = float(
            np.linalg.norm(j_cfg - j0) / max(np.linalg.norm(j0), 1e-30)
        )
        per_scene.append({
            "scene_id": row["scene_id"],
            "source_class": row["source_class"],
            "cfg_plant_inertia_kg_m2": j_cfg.tolist(),
            "controller_fixed_J0_kg_m2": j0.tolist(),
            "cfg_vs_controller_J0_relative_error": inertia_relative_error,
            "stored_vs_actual_BS_accel_feature_rms_rad_s2": feature_error_rms.tolist(),
            "actual_BS_accel_feature_rms_rad_s2": actual_alpha_rms.tolist(),
            "stored_label_reconstruction_max_abs_rad_s2": float(np.max(np.abs(current_label_error))),
            "teacher_RBF_pre_beta_output_rms_rad_s2": teacher_rms.tolist(),
            "current_residual_target_rms_rad_s2": label_rms.tolist(),
            "teacher_to_target_rms_ratio": teacher_ratio,
            "fixed_J0_beta_teacher_to_logged_torque_relative_error": torque_map_relative_error,
        })

    ratios = np.asarray([float(row["teacher_to_target_rms_ratio"]) for row in per_scene])
    j0_relative = np.asarray([float(row["cfg_vs_controller_J0_relative_error"]) for row in per_scene])
    feature_rms = np.asarray(
        [row["stored_vs_actual_BS_accel_feature_rms_rad_s2"] for row in per_scene], dtype=np.float64
    )
    teacher_rms = np.asarray(
        [row["teacher_RBF_pre_beta_output_rms_rad_s2"] for row in per_scene], dtype=np.float64
    )
    label_rms = np.asarray([row["current_residual_target_rms_rad_s2"] for row in per_scene], dtype=np.float64)
    map_errors = np.asarray(
        [float(row["fixed_J0_beta_teacher_to_logged_torque_relative_error"]) for row in per_scene]
    )
    result = {
        "schema": "DL1018_TCN_SUPERVISION_TARGET_RBF_AUDIT_V1",
        "status": "MISMATCH_CONFIRMED",
        "dataset_manifest_sha256": sha256(MANIFEST_PATH),
        "dataset_npz_sha256": sha256(NPZ_PATH),
        "controller_J0_audit_sha256": sha256(J0_AUDIT_PATH),
        "split": "VAL48",
        "scenes": len(rows),
        "events": len(rows) * EXPECTED_EVENTS,
        "raw_sha_verified": len(rows),
        "run_start_sha_verified": len(rows),
        "test_data_read": False,
        "plant_invoked": False,
        "controller_J0_source": "MATLAB simulation_parameters at nominal arm lengths then controller_parameters(...,'fixed')",
        "cfg_plant_inertia_vs_fixed_controller_J0_relative_error_median": float(np.median(j0_relative)),
        "cfg_plant_inertia_vs_fixed_controller_J0_relative_error_min": float(np.min(j0_relative)),
        "stored_BS_accel_feature_error_rms_macro_rad_s2": np.mean(feature_rms, axis=0).tolist(),
        "teacher_RBF_pre_beta_output_rms_macro_rad_s2": np.mean(teacher_rms, axis=0).tolist(),
        "current_residual_target_rms_macro_rad_s2": np.mean(label_rms, axis=0).tolist(),
        "teacher_to_target_ratio_scene_median": float(np.median(ratios)),
        "teacher_to_target_ratio_scene_p95": float(np.quantile(ratios, 0.95)),
        "teacher_to_target_ratio_scene_max": float(np.max(ratios)),
        "teacher_to_target_ratio_scene_mean": float(np.mean(ratios)),
        "max_ratio_scene_id": per_scene[int(np.argmax(ratios))]["scene_id"],
        "teacher_action_mapping_relative_error_median": float(np.median(map_errors)),
        "teacher_action_mapping_relative_error_max": float(np.max(map_errors)),
        "recommended_supervision": "logged rbf_output_raw at attitude events (pre-beta, rad/s^2); apply only the frozen C5 beta and fixed controller J0 at runtime",
        "per_scene": per_scene,
        "interpretation": (
            "The current dataset reconstructs alpha_bs with cfg.plant.inertia, while the deployed fixed controller uses "
            "the distributed-mass nominal controller inertia. The current target is measured acceleration residual after "
            "B's attitude RBF ran, not the RBF action that the new TCN replaces. The logged pre-beta RBF action maps to "
            "the applied torque with the fixed controller J0 and beta; no time-varying inertia estimate is needed. "
            "Do not release the current checkpoint as a direct RBF replacement."
        ),
    }
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "per_scene"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
