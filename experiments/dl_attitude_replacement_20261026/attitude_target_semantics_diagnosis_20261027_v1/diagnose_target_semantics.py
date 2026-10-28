from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import h5py
import numpy as np

PROJECT = pathlib.Path(__file__).resolve().parents[3]
BASE = PROJECT / "experiments/dl_attitude_replacement_20261026"
OUT = pathlib.Path(__file__).resolve().parent
CAUSAL_PATH = BASE / "attitude_head_mechanism_v1/CAUSAL_NOMINAL_TORQUE_RESIDUAL.json"
REPLAY_PATH = BASE / "mlp15_distribution_countercheck_v1/SAME_STATE_REPLAY.json"
REPLAY_SCRIPT = BASE / "mlp15_distribution_countercheck_v1/replay_fixed_c5_states.py"
CAUSAL_SCRIPT = BASE / "attitude_head_mechanism_v1/audit_causal_nominal_torque_residual.m"
MANIFEST_PATH = BASE / "mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json"
DATASET_PATH = BASE / "mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz"
TRAIN_SCRIPT = BASE / "mlp15_c5_teacher_full72_v1/train_mlp15_c5_full72_v1.py"
BUILDER_SCRIPT = BASE / "mlp15_c5_teacher_redistill_v1/build_matched_teacher_dataset_v1.py"
ARCH_HELPER = BASE / "architecture_screen_v1/screen_attitude_architectures_v1.py"
RUN = BASE / "mlp15_c5_teacher_full72_v1/runs/C5_MLP15_FULL72_SEED2026102001"
MODEL_MAT = RUN / "mlp15_attitude_weights_v1.mat"
CHECKPOINT = RUN / "final_step_60000.pt"
TRAIN_CONFIG = RUN / "training_config.json"
RUN_RECEIPT = RUN / "run_receipt.json"
DMAX = np.asarray([45.0, 45.0, 4.7124], dtype=np.float64)
DT = 0.001
BETA_RISE = 2.2


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rms(values: np.ndarray, axis: int = 0) -> np.ndarray:
    return np.sqrt(np.mean(np.asarray(values, dtype=np.float64) ** 2, axis=axis))


def build_model_runtime():
    sys.path.insert(0, str(BASE / "mlp15_c5_teacher_ghp7_balance_v1"))
    import audit_ghp7_balanced_fit_v1 as replay
    MLP15, make_windows = replay.load_model_helpers()
    model, mean, std, target_rms = replay.load_checkpoint(CHECKPOINT, MLP15)
    return replay, model, mean, std, target_rms, make_windows


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only six-scene C5 target semantics audit.")
    parser.add_argument("--overwrite", action="store_true", help="refresh this audit directory's INPUTS/METRICS only")
    args = parser.parse_args()
    for name in ("INPUTS.json", "METRICS.json"):
        if (OUT / name).exists() and not args.overwrite:
            raise FileExistsError(f"{OUT / name} exists; pass --overwrite to refresh this audit output")

    causal = json.loads(CAUSAL_PATH.read_text(encoding="utf-8"))
    replay_report = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    train_config = json.loads(TRAIN_CONFIG.read_text(encoding="utf-8"))
    assert causal["Plant_calls"] == 0 and causal["TEST_read"] is False
    assert causal["inertia_reconstruction_used"] is False
    assert replay_report["Plant_calls"] == 0 and replay_report["TEST_read"] is False
    assert replay_report["data_used_for_training"] is True
    assert sha256(CAUSAL_SCRIPT) == causal["source_script_sha256"]
    assert sha256(REPLAY_SCRIPT) == replay_report["source_script_sha256"]
    assert manifest["target"] == "logged rbf_output_raw at attitude event k; post-dmax/pre-beta; rad/s^2"
    assert manifest["dataset_sha256"] == sha256(DATASET_PATH)
    J0 = np.asarray(manifest["fixed_J0_reference"]["diagonal_kg_m2"], dtype=np.float64)
    assert J0.shape == (3,) and np.all(J0 > 0)

    dataset = np.load(DATASET_PATH, allow_pickle=False)
    scene_ids = [row["scene_id"] for row in causal["rows"]]
    c5_ids = dataset["c5_val_scene_ids"].tolist()
    causal_rows = {row["scene_id"]: row for row in causal["rows"]}
    manifest_rows = {row["scene_id"]: row for row in manifest["rows"]}
    replay_rows = {row["scene_id"]: row for row in replay_report["rows"] if row["model"] == "C5_FULL72"}
    assert len(scene_ids) == 6 and all(sid in c5_ids and sid in replay_rows for sid in scene_ids)

    replay, model, input_mean, input_std, target_rms, make_windows = build_model_runtime()
    assert sha256(MODEL_MAT) == replay_report["models"][0]["MAT_sha256"]
    assert sha256(CHECKPOINT) == replay_report["models"][0]["checkpoint_sha256"]

    arrays: dict[str, dict[str, np.ndarray]] = {}
    scene_results: list[dict[str, Any]] = []
    raw_hashes: dict[str, str] = {}
    feature_errors: dict[str, float] = {}
    residual_audit_errors: dict[str, float] = {}

    for scene_id in scene_ids:
        rec = manifest_rows[scene_id]
        raw_path = pathlib.Path(rec["raw_path"])
        raw_hashes[scene_id] = sha256(raw_path)
        assert raw_hashes[scene_id] == rec["raw_sha256"] == causal_rows[scene_id]["source_raw_sha256"]
        with h5py.File(raw_path, "r") as raw_file:
            log = raw_file["log"]
            state = np.asarray(log["state"], dtype=np.float64).T
            reference = np.asarray(log["filtered_attitude_reference"], dtype=np.float64).T
            time = np.asarray(log["time"], dtype=np.float64).reshape(-1)
            event_indices = np.flatnonzero(np.asarray(log["attitude_event_flag"]).reshape(-1).astype(bool))
            # MATLAB requested_generalized(:,2:4) are Python array rows 1:4.
            issued_torque = np.asarray(log["requested_generalized"], dtype=np.float64)[1:4, :].T
            nominal_torque = np.asarray(log["attitude_bs_nominal_torque_Nm"], dtype=np.float64).T
            teacher_raw_all = np.asarray(log["rbf_output_raw"], dtype=np.float64).T
            teacher_unclipped_all = np.asarray(log["rbf_output_unclipped"], dtype=np.float64).T
            teacher_applied_all = np.asarray(log["attitude_rbf_estimate_acceleration_rads2"], dtype=np.float64).T
            rbf_torque = np.asarray(log["attitude_rbf_compensation_torque_Nm"], dtype=np.float64).T
            applied_torque = np.asarray(log["attitude_compensation_applied_torque_Nm"], dtype=np.float64).T
            morph_command = np.asarray(raw_file["scene/arms/command"], dtype=np.float64).T

        expected_events = np.arange(10, 20_000, 10, dtype=np.int64)
        assert np.array_equal(event_indices, expected_events)
        euler_error = np.arctan2(
            np.sin(reference[event_indices] - state[event_indices, 6:9]),
            np.cos(reference[event_indices] - state[event_indices, 6:9]),
        )
        features = np.concatenate(
            (euler_error, state[event_indices, 9:12], nominal_torque[event_indices], morph_command[event_indices]),
            axis=1,
        )
        data_index = c5_ids.index(scene_id)
        dataset_features = dataset["c5_val_x"][data_index].astype(np.float64)
        dataset_targets = dataset["c5_val_y"][data_index].astype(np.float64)
        feature_errors[scene_id] = float(np.max(np.abs(features - dataset_features)))
        assert feature_errors[scene_id] < 2e-6
        teacher_raw = teacher_raw_all[event_indices]
        assert np.max(np.abs(teacher_raw - dataset_targets)) < 2e-6

        # event_indices are zero-based Plant transition/sample indices k=10,20,...;
        # MATLAB's one-based index is k+1. This is not the event ordinal 0..1998.
        beta = np.minimum((event_indices + 1) * DT / BETA_RISE, 1.0)
        clip_error = float(np.max(np.abs(teacher_raw - np.clip(teacher_unclipped_all[event_indices], -DMAX, DMAX))))
        beta_error = float(np.max(np.abs(teacher_applied_all[event_indices] - beta[:, None] * teacher_raw)))
        torque_map_error = float(np.max(np.abs(rbf_torque[event_indices] - teacher_applied_all[event_indices] * J0[None, :])))
        applied_torque_alias_error = float(np.max(np.abs(applied_torque - rbf_torque)))
        assert clip_error < 1e-12 and beta_error < 1e-10 and torque_map_error < 1e-12
        assert applied_torque_alias_error == 0.0

        prediction, _ = replay.predict(
            model, dataset_features[None, :, :], input_mean, input_std, target_rms, make_windows
        )
        prediction = prediction[0].astype(np.float64)
        fit_error = prediction - teacher_raw
        fit_rmse = rms(fit_error)
        assert np.max(np.abs(fit_rmse - np.asarray(replay_rows[scene_id]["axis_RMSE_rad_s2"]))) < 2e-5

        omega = state[:, 9:12]
        observed_residual = np.empty((len(event_indices), 3), dtype=np.float64)
        applied_interval = np.empty_like(observed_residual)
        for j, k in enumerate(event_indices):
            p = max(0, int(k) - 10)
            gyro = np.cross(omega[p:k], omega[p:k] * J0[None, :], axis=1)
            observed_residual[j] = (
                (omega[k] - omega[p]) / (time[k] - time[p])
                + np.mean((gyro - issued_torque[p:k]) / J0[None, :], axis=0)
            )
            applied_interval[j] = np.mean(applied_torque[p:k] / J0[None, :], axis=0)

        mature_existing = time[event_indices] >= 3.0
        stored = causal_rows[scene_id]
        audit_error = max(
            float(np.max(np.abs(rms(observed_residual[mature_existing]) - stored["mature_observed_residual_RMS_rad_s2"]))),
            float(np.max(np.abs(rms(applied_interval[mature_existing]) - stored["mature_RBF_applied_RMS_rad_s2"]))),
            float(np.max(np.abs(rms((observed_residual - applied_interval)[mature_existing]) - stored["mature_observed_minus_RBF_RMSE_rad_s2"]))),
        )
        assert audit_error < 1e-7
        residual_audit_errors[scene_id] = audit_error

        # A residual for the interval ending at event j is paired with the feature and teacher at j-1,
        # the interval start. The first interval has no prior attitude-event feature and is excluded.
        arrays[scene_id] = {
            "t_start": time[event_indices][:-1],
            "t_end": time[event_indices][1:],
            "beta_start": beta[:-1],
            "raw_start": teacher_raw[:-1],
            "raw_end": teacher_raw[1:],
            "applied_point_start": teacher_applied_all[event_indices][:-1],
            "prediction_start": prediction[:-1],
            "residual_end": observed_residual[1:],
            "applied_interval_end": applied_interval[1:],
        }
        scene_results.append({
            "scene_id": scene_id,
            "raw_sha256": raw_hashes[scene_id],
            "feature_max_abs_diff_vs_npz": feature_errors[scene_id],
            "raw_equals_clip_max_abs_error_at_events": clip_error,
            "beta_apply_max_abs_error": beta_error,
            "fixed_J0_torque_map_max_abs_error": torque_map_error,
            "applied_torque_equals_RBF_torque_max_abs_error": applied_torque_alias_error,
            "base_mlp_fit_axis_rmse": fit_rmse.tolist(),
            "base_mlp_fit_vector_rmse": float(np.sqrt(np.mean(np.sum(fit_error ** 2, axis=1)))),
            "mature_t_end_ge_3s_residual_minus_applied_interval_rmse": rms(
                (observed_residual - applied_interval)[mature_existing]
            ).tolist(),
            "existing_residual_audit_max_abs_error": audit_error,
        })

    category_masks = {
        "all_start_aligned": lambda a: np.ones_like(a["t_start"], dtype=bool),
        "beta_immature_start": lambda a: a["beta_start"] < 1.0,
        "beta_mature_start": lambda a: a["beta_start"] >= 1.0,
        "first_5s_start": lambda a: a["t_start"] < 5.0,
        "last_5s_start": lambda a: a["t_start"] >= 15.0,
        "beta_mature_first_5s_start": lambda a: (a["beta_start"] >= 1.0) & (a["t_start"] < 5.0),
        "beta_mature_last_5s_start": lambda a: (a["beta_start"] >= 1.0) & (a["t_start"] >= 15.0),
        "conservative_mature_t_end_ge_3s": lambda a: a["t_end"] >= 3.0,
    }
    pooled: dict[str, Any] = {}
    per_scene_mature: dict[str, Any] = {}
    for category, mask_fn in category_masks.items():
        parts: dict[str, list[np.ndarray]] = {
            key: [] for key in (
                "base_fit", "residual_minus_raw_start", "residual_minus_applied_point_start",
                "residual_minus_applied_interval", "residual_minus_raw_end", "label_start_to_end_delta",
                "residual_rms_source", "raw_start_rms_source", "applied_start_rms_source",
            )
        }
        count = 0
        for trace in arrays.values():
            mask = mask_fn(trace)
            count += int(mask.sum())
            residual = trace["residual_end"][mask]
            raw_start = trace["raw_start"][mask]
            raw_end = trace["raw_end"][mask]
            applied_start = trace["applied_point_start"][mask]
            pred_start = trace["prediction_start"][mask]
            applied_interval = trace["applied_interval_end"][mask]
            values = {
                "base_fit": pred_start - raw_start,
                "residual_minus_raw_start": residual - raw_start,
                "residual_minus_applied_point_start": residual - applied_start,
                "residual_minus_applied_interval": residual - applied_interval,
                "residual_minus_raw_end": residual - raw_end,
                "label_start_to_end_delta": raw_end - raw_start,
                "residual_rms_source": residual,
                "raw_start_rms_source": raw_start,
                "applied_start_rms_source": applied_start,
            }
            for key, value in values.items():
                parts[key].append(value)
        joined = {key: np.concatenate(value, axis=0) for key, value in parts.items()}
        axis = {key: rms(value).tolist() for key, value in joined.items()}
        ratios = {
            key: (np.asarray(axis[key]) / np.maximum(np.asarray(axis["base_fit"]), 1e-12)).tolist()
            for key in (
                "residual_minus_raw_start", "residual_minus_applied_point_start",
                "residual_minus_applied_interval", "residual_minus_raw_end",
            )
        }
        biases = {
            key: np.mean(joined[key], axis=0).tolist()
            for key in (
                "base_fit", "residual_minus_raw_start", "residual_minus_applied_point_start",
                "residual_minus_applied_interval", "residual_minus_raw_end",
            )
        }
        pooled[category] = {"interval_count": count, "axis_rmse_or_rms": axis, "mismatch_to_base_fit_ratio": ratios, "mean_bias": biases}

    for scene_id, trace in arrays.items():
        mask = trace["beta_start"] >= 1.0
        fit = rms(trace["prediction_start"][mask] - trace["raw_start"][mask])
        raw_delta = rms(trace["residual_end"][mask] - trace["raw_start"][mask])
        applied_delta = rms(trace["residual_end"][mask] - trace["applied_point_start"][mask])
        interval_delta = rms(trace["residual_end"][mask] - trace["applied_interval_end"][mask])
        end_delta = rms(trace["residual_end"][mask] - trace["raw_end"][mask])
        per_scene_mature[scene_id] = {
            "mature_interval_count": int(mask.sum()),
            "base_fit_rmse": fit.tolist(),
            "residual_minus_raw_start_rmse": raw_delta.tolist(),
            "raw_start_mismatch_to_fit_ratio": (raw_delta / np.maximum(fit, 1e-12)).tolist(),
            "residual_minus_applied_start_rmse": applied_delta.tolist(),
            "applied_start_mismatch_to_fit_ratio": (applied_delta / np.maximum(fit, 1e-12)).tolist(),
            "residual_minus_applied_interval_rmse": interval_delta.tolist(),
            "applied_interval_mismatch_to_fit_ratio": (interval_delta / np.maximum(fit, 1e-12)).tolist(),
            "residual_minus_raw_endpoint_rmse": end_delta.tolist(),
            "raw_endpoint_mismatch_to_fit_ratio": (end_delta / np.maximum(fit, 1e-12)).tolist(),
            "raw_start_to_end_label_delta_rmse": rms(trace["raw_end"][mask] - trace["raw_start"][mask]).tolist(),
            "teacher_raw_start_rms": rms(trace["raw_start"][mask]).tolist(),
            "teacher_applied_start_rms": rms(trace["applied_point_start"][mask]).tolist(),
            "residual_rms": rms(trace["residual_end"][mask]).tolist(),
        }

    source_files = [
        CAUSAL_PATH, CAUSAL_SCRIPT, REPLAY_PATH, REPLAY_SCRIPT, MANIFEST_PATH, DATASET_PATH, TRAIN_SCRIPT, BUILDER_SCRIPT,
        ARCH_HELPER, MODEL_MAT, CHECKPOINT, TRAIN_CONFIG, RUN_RECEIPT, pathlib.Path(__file__).resolve(),
    ]
    inputs = {
        "files_sha256": {str(path): sha256(path) for path in source_files},
        "six_original_C5_raw_sha256": raw_hashes,
        "fixed_J0_diagonal_kg_m2": J0.tolist(),
        "teacher_target": "rbf_output_raw = clip(rbf_output_unclipped, +/-[45,45,4.7124]) rad/s^2; post-DMAX/pre-beta.",
        "beta_formula_and_index": (
            "beta=min((k+1)*0.001/2.2,1), where k is the zero-based Plant transition/sample index "
            "of the attitude event (10,20,...,19990); MATLAB uses one-based k+1. k is not event ordinal 0..1998. "
            "Verified at all six logged event traces against beta-applied acceleration."
        ),
        "legal_observation_formula": (
            "R=(omega[k]-omega[p])/(t[k]-t[p]) + mean((cross(omega[i],J0*omega[i])-tau_issued[i])/J0, i=p..k-1); "
            "p=max(0,k-10); tau_issued=requested_generalized columns 2:4 (MATLAB); fixed J0 diagonal only."
        ),
        "clock_alignment": (
            "R interval ending at event j is compared with prediction/raw/applied teacher at prior 10 ms event j-1. "
            "R_j versus end-event label j is reported separately. First interval lacks a prior attitude-event feature."
        ),
        "frozen_model_forward": "MLP15 15x13 event-major flatten, SiLU, existing frozen PyTorch checkpoint/runtime helper.",
        "training_split_caveat": {
            "normalizer_fit_splits": train_config["normalizer_fit_splits"],
            "validation": train_config["validation"],
            "dataset_events": 143928,
            "C5_VAL48_is_in_C5_FULL72_training": True,
            "same_state_fit_is_independent_validation": False,
        },
        "scope": {
            "scenes": 6, "same_recorded_C5_teacher_states": True,
            "Plant_calls": 0, "TEST_read": False, "training_jobs": 0,
            "inertia_reconstruction_used": False,
        },
    }
    max_fit_diff = max(
        float(np.max(np.abs(np.asarray(result["base_mlp_fit_axis_rmse"]) - np.asarray(replay_rows[result["scene_id"]]["axis_RMSE_rad_s2"]))))
        for result in scene_results
    )
    metrics = {
        "schema": "C5_MLP15_TARGET_SEMANTICS_DIAGNOSIS_V1",
        "inputs": inputs,
        "verification": {
            "frozen_forward_max_axis_RMSE_difference_vs_same_state_replay": max_fit_diff,
            "feature_rebuild_max_abs_diff_vs_dataset_by_scene": feature_errors,
            "existing_CAUSAL_audit_max_abs_difference_by_scene": residual_audit_errors,
        },
        "per_scene": scene_results,
        "pooled_categories": pooled,
        "per_scene_beta_mature_start_alignment": per_scene_mature,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "INPUTS.json").write_text(json.dumps(inputs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "METRICS.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"WROTE={OUT}")
    print(f"FROZEN_FORWARD_MAX_AXIS_RMSE_DIFF={max_fit_diff:.12g}")
    for category in ("beta_mature_start", "beta_immature_start", "beta_mature_first_5s_start", "beta_mature_last_5s_start"):
        row = pooled[category]
        print(category, "n=", row["interval_count"],
              "fit=", row["axis_rmse_or_rms"]["base_fit"],
              "R_minus_raw_start=", row["axis_rmse_or_rms"]["residual_minus_raw_start"],
              "ratio=", row["mismatch_to_base_fit_ratio"]["residual_minus_raw_start"],
              "label_delta=", row["axis_rmse_or_rms"]["label_start_to_end_delta"])


if __name__ == "__main__":
    main()
