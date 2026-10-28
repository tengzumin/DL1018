#!/usr/bin/env python3
"""Summarize the frozen REPAIR03 score and independently replay its saved MLP."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[4]
EXP = ROOT / "experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1"
REPAIR = Path(__file__).resolve().parent
RESULT_PATH = REPAIR / "C5_VAL48_SCORE_RESULT_v1.json"
NPZ_PATH = REPAIR / "C5_VAL48_RESIDUAL_DIAGNOSTIC_v1.npz"
TRAIN_MANIFEST_PATH = EXP / "TRAIN_C5_24_PHYSICAL_RESIDUAL_MANIFEST_v1.json"
WEIGHTS_PATH = EXP / "runs/MLP15_TRAIN_C5_24_PHYSICAL_RESIDUAL_SEED2026102001_REPAIR01/mlp15_attitude_weights_v1.mat"
OUTPUT_PATH = REPAIR / "C5_VAL48_SUMMARY_REPAIR03_v1.json"
WINDOW = 15
BATCH_SIZE = 1024
D_MAX = np.array([45.0, 45.0, 4.7124], dtype=np.float64)
AXES = ("roll_x", "pitch_y", "yaw_z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def silu(x: np.ndarray) -> np.ndarray:
    sigmoid = np.empty_like(x)
    positive = x >= 0
    sigmoid[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
    exp_x = np.exp(x[~positive])
    sigmoid[~positive] = exp_x / (1.0 + exp_x)
    return x * sigmoid


def forward_scene(x: np.ndarray, model: dict[str, np.ndarray]) -> np.ndarray:
    """Match training's left-zero padding and event-major, feature-minor flatten."""
    mean = model["input_mean"].reshape(1, -1)
    std = model["input_std"].reshape(1, -1)
    target_rms = model["target_rms"].reshape(1, -1)
    normalized = (x.astype(np.float64) - mean) / std
    padded = np.concatenate((np.zeros((WINDOW - 1, x.shape[1])), normalized), axis=0)
    out = np.empty((len(x), 3), dtype=np.float64)
    for start in range(0, len(x), BATCH_SIZE):
        stop = min(start + BATCH_SIZE, len(x))
        windows = np.stack([padded[i:i + WINDOW] for i in range(start, stop)])
        h1 = silu(windows.reshape(stop - start, -1) @ model["fc1_weight"].T + model["fc1_bias"])
        h2 = silu(h1 @ model["fc2_weight"].T + model["fc2_bias"])
        out[start:stop] = (h2 @ model["head_weight"].T + model["head_bias"]) * target_rms
    return out


def rmse(x: np.ndarray, axis=None) -> np.ndarray | float:
    result = np.sqrt(np.mean(np.square(x), axis=axis))
    return float(result) if np.ndim(result) == 0 else result


def scene_parts(scene_id: str) -> tuple[str, str, str]:
    match = re.search(r"_(T\d+)_C(\d+)_W(\d+)$", scene_id)
    if not match:
        raise ValueError(f"unexpected scene id: {scene_id}")
    task, condition, wind = match.groups()
    return task, f"C{int(condition):02d}", f"W{int(wind):02d}"


def relative_gain(reference: float, candidate: float) -> float | None:
    # Relative percentages are not meaningful for near-zero scene baselines.
    if abs(reference) < 0.05:
        return None
    return 100.0 * (reference - candidate) / reference


def main() -> None:
    score = read_json(RESULT_PATH)
    manifest = read_json(TRAIN_MANIFEST_PATH)
    if score.get("status") != "PASS_ONE_SHOT_OFFLINE_SCORE" or score.get("TEST_accessed") is not False:
        raise ValueError("REPAIR03 score status/TEST boundary is not clean")
    if score.get("validation_used_for_fit") or score.get("validation_used_for_normalization"):
        raise ValueError("VAL48 was reported as used for fitting or normalization")

    with np.load(NPZ_PATH, allow_pickle=False) as archive:
        x_val = np.asarray(archive["x_val"], dtype=np.float64)
        y_val = np.asarray(archive["y_val"], dtype=np.float64)
        scene_ids = archive["scene_ids"].astype(str).tolist()
    if x_val.shape != (48, 1999, 13) or y_val.shape != (48, 1999, 3) or len(scene_ids) != 48:
        raise ValueError(f"unexpected saved score array shapes: {x_val.shape}, {y_val.shape}")

    mat = loadmat(WEIGHTS_PATH)
    model = {key: np.asarray(mat[key], dtype=np.float64).reshape(-1) if key.endswith("bias")
             else np.asarray(mat[key], dtype=np.float64)
             for key in ("input_mean", "input_std", "target_rms", "fc1_weight", "fc1_bias",
                         "fc2_weight", "fc2_bias", "head_weight", "head_bias")}
    model["input_mean"] = model["input_mean"].reshape(1, 13)
    model["input_std"] = model["input_std"].reshape(1, 13)
    model["target_rms"] = model["target_rms"].reshape(1, 3)
    if model["fc1_weight"].shape != (64, 195) or model["fc2_weight"].shape != (32, 64) or model["head_weight"].shape != (3, 32):
        raise ValueError("frozen MAT weight shapes differ from MLP15")

    raw_prediction = np.stack([forward_scene(x_val[i], model) for i in range(len(scene_ids))])
    clipped_prediction = np.clip(raw_prediction, -D_MAX, D_MAX)
    candidate_error = clipped_prediction - y_val
    zero_error = -y_val
    candidate_axis_scene = rmse(candidate_error, axis=1)
    zero_axis_scene = rmse(zero_error, axis=1)
    candidate_scene = rmse(candidate_error, axis=(1, 2))
    zero_scene = rmse(zero_error, axis=(1, 2))
    task_group, condition_group, wind_group = zip(*(scene_parts(s) for s in scene_ids))
    raw_clip_mask = np.abs(raw_prediction) > D_MAX
    feature_z = (x_val - model["input_mean"].reshape(1, 1, -1)) / model["input_std"].reshape(1, 1, -1)
    any_feature_gt3 = np.any(np.abs(feature_z) > 3.0, axis=2)
    any_feature_gt5 = np.any(np.abs(feature_z) > 5.0, axis=2)

    per_scene = []
    for i, scene_id in enumerate(scene_ids):
        delta = float(zero_scene[i] - candidate_scene[i])
        per_scene.append({
            "scene_id": scene_id, "task_group": task_group[i], "condition_group": condition_group[i],
            "wind_group": wind_group[i], "candidate_scene_rmse_rad_s2": float(candidate_scene[i]),
            "zero_scene_rmse_rad_s2": float(zero_scene[i]), "absolute_gain_rad_s2": delta,
            "relative_gain_percent": relative_gain(float(zero_scene[i]), float(candidate_scene[i])),
            "zero_baseline_near_zero": bool(zero_scene[i] < 0.05),
            "candidate_axis_rmse_rad_s2": dict(zip(AXES, candidate_axis_scene[i].astype(float).tolist())),
            "zero_axis_rmse_rad_s2": dict(zip(AXES, zero_axis_scene[i].astype(float).tolist())),
            "candidate_clip_event_fraction": float(np.mean(np.any(raw_clip_mask[i], axis=1))),
            "feature_event_fraction_any_abs_z_gt_3": float(np.mean(any_feature_gt3[i])),
            "feature_event_fraction_any_abs_z_gt_5": float(np.mean(any_feature_gt5[i])),
            "feature_abs_z_max": float(np.max(np.abs(feature_z[i]))),
        })

    candidate_macro = float(np.mean(candidate_scene))
    zero_macro = float(np.mean(zero_scene))
    candidate_axis_macro = np.mean(candidate_axis_scene, axis=0)
    zero_axis_macro = np.mean(zero_axis_scene, axis=0)
    candidate_axis_pooled = rmse(candidate_error, axis=(0, 1))
    zero_axis_pooled = rmse(zero_error, axis=(0, 1))

    wind_summary = {}
    for group in sorted(set(wind_group)):
        indices = [i for i, g in enumerate(wind_group) if g == group]
        candidate_wind = float(np.mean(candidate_scene[indices]))
        zero_wind = float(np.mean(zero_scene[indices]))
        scene_wins = sum(candidate_scene[i] < zero_scene[i] for i in indices)
        wind_summary[group] = {
            "scene_count": len(indices), "candidate_scene_macro_rmse_rad_s2": candidate_wind,
            "zero_scene_macro_rmse_rad_s2": zero_wind,
            "relative_gain_percent": relative_gain(zero_wind, candidate_wind),
            "scene_wins": int(scene_wins), "scene_losses": len(indices) - int(scene_wins),
            "candidate_clip_event_fraction": float(np.mean(np.any(raw_clip_mask[indices], axis=2))),
            "feature_event_fraction_any_abs_z_gt_3": float(np.mean(any_feature_gt3[indices])),
            "feature_event_fraction_any_abs_z_gt_5": float(np.mean(any_feature_gt5[indices])),
            "feature_abs_z_max": float(np.max(np.abs(feature_z[indices]))),
        }

    feature_names = [
        "wrapped_attitude_error_roll", "wrapped_attitude_error_pitch", "wrapped_attitude_error_yaw",
        "body_rate_roll", "body_rate_pitch", "body_rate_yaw",
        "nominal_bs_torque_roll", "nominal_bs_torque_pitch", "nominal_bs_torque_yaw",
        "morph_command_1", "morph_command_2", "morph_command_3", "morph_command_4",
    ]
    ood_by_feature = {}
    for j, name in enumerate(feature_names):
        zj = feature_z[:, :, j]
        ood_by_feature[name] = {
            "fraction_abs_z_gt_3": float(np.mean(np.abs(zj) > 3.0)),
            "fraction_abs_z_gt_5": float(np.mean(np.abs(zj) > 5.0)),
            "abs_z_p99": float(np.quantile(np.abs(zj), 0.99)),
            "abs_z_max": float(np.max(np.abs(zj))),
        }
    train_ids = manifest["scene_ids"]
    train_parts = [scene_parts(s) for s in train_ids]
    train_tasks = sorted({p[0] for p in train_parts})
    train_conditions = sorted({p[1] for p in train_parts})
    train_winds = sorted({p[2] for p in train_parts})
    train_task_condition = {f"{t}_{c}" for t, c, _ in train_parts}
    val_task_condition = {f"{t}_{c}" for t, c, _ in zip(task_group, condition_group, wind_group)}
    c_high_by_task = {
        task: sorted({c for t, c, _ in train_parts if t == task and int(c[1:]) >= 14})
        for task in train_tasks
    }
    manifest_frequency_fields = [key for key in manifest if "freq" in key.lower()]
    event_dt = float(manifest["event_schedule"]["sample_dt_s"]) * int(manifest["event_schedule"]["event_stride_transitions"])
    event_rate = 1.0 / event_dt

    # Compare this independent NumPy replay against the already-saved JSON, not the scorer.
    reported_by_scene = {row["scene_id"]: row for row in score["per_scene"]}
    max_scene_metric_diff = max(abs(per_scene[i]["candidate_scene_rmse_rad_s2"] -
                                     reported_by_scene[scene_ids[i]]["candidate_scene_rmse_rad_s2"])
                                for i in range(len(scene_ids)))
    reported_candidate = score["candidate_metrics"]
    replay_check = {
        "candidate_scene_macro_rmse_abs_difference": abs(candidate_macro - reported_candidate["scene_macro_rmse_rad_s2"]),
        "candidate_axis_pooled_rmse_max_abs_difference": float(np.max(np.abs(candidate_axis_pooled -
            np.array([reported_candidate["axis_pooled_rmse_rad_s2"][a] for a in AXES])))),
        "candidate_axis_scene_macro_rmse_max_abs_difference": float(np.max(np.abs(candidate_axis_macro -
            np.array([reported_candidate["axis_scene_macro_rmse_rad_s2"][a] for a in AXES])))),
        "per_scene_candidate_rmse_max_abs_difference": max_scene_metric_diff,
        "max_abs_prediction_difference_from_reported_distribution": max(
            abs(float(np.quantile(raw_prediction[:, :, j], 0.99)) -
                float(score["candidate_raw_output_distribution_by_axis"]["p99"][j]))
            for j, axis in enumerate(AXES)),
        "window_contract": "left-pad 14 zero-normalized events; each window is 15 events x 13 features; C-order event-major flatten",
        "forward_method": "independent batched NumPy MLP using frozen MATLAB weights",
    }

    output = {
        "schema": "DL1018_MLP15_C5_VAL48_REPAIR03_SUMMARY_V1",
        "source_result": str(RESULT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "source_npz": str(NPZ_PATH.relative_to(ROOT)).replace("\\", "/"),
        "source_train_manifest": str(TRAIN_MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "source_mat_weights": str(WEIGHTS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "split": "C5_VAL48 reused offline diagnostic; not independent TEST evidence",
        "candidate_scene_macro_rmse_rad_s2": candidate_macro,
        "zero_scene_macro_rmse_rad_s2": zero_macro,
        "scene_macro_relative_gain_percent": relative_gain(zero_macro, candidate_macro),
        "scene_win_count": int(np.sum(candidate_scene < zero_scene)),
        "scene_loss_count": int(np.sum(candidate_scene > zero_scene)),
        "scene_tie_count": int(np.sum(np.isclose(candidate_scene, zero_scene, rtol=0, atol=1e-12))),
        "axis_scene_macro": {
            axis: {"candidate_rmse_rad_s2": float(candidate_axis_macro[j]),
                  "zero_rmse_rad_s2": float(zero_axis_macro[j]),
                  "relative_gain_percent": relative_gain(float(zero_axis_macro[j]), float(candidate_axis_macro[j])),
                  "scene_wins": int(np.sum(candidate_axis_scene[:, j] < zero_axis_scene[:, j])),
                  "scene_losses": int(np.sum(candidate_axis_scene[:, j] > zero_axis_scene[:, j]))}
            for j, axis in enumerate(AXES)
        },
        "axis_pooled": {
            axis: {"candidate_rmse_rad_s2": float(candidate_axis_pooled[j]),
                  "zero_rmse_rad_s2": float(zero_axis_pooled[j]),
                  "relative_gain_percent": relative_gain(float(zero_axis_pooled[j]), float(candidate_axis_pooled[j]))}
            for j, axis in enumerate(AXES)
        },
        "wind_group_summary": wind_summary,
        "severe_scene_regressions_extra_rmse_gt_1_rad_s2": sorted(
            [row for row in per_scene if row["absolute_gain_rad_s2"] < -1.0],
            key=lambda row: row["absolute_gain_rad_s2"]),
        "largest_scene_regressions": sorted(per_scene, key=lambda row: row["absolute_gain_rad_s2"])[:10],
        "largest_scene_improvements": sorted(per_scene, key=lambda row: row["absolute_gain_rad_s2"], reverse=True)[:10],
        "per_scene": per_scene,
        "clipping": {
            "dmax_rad_s2": D_MAX.tolist(),
            "candidate_raw_prediction_clipped_count_by_axis": {
                axis: int(np.sum(np.abs(raw_prediction[:, :, j]) > D_MAX[j])) for j, axis in enumerate(AXES)},
            "candidate_raw_prediction_clipped_fraction_by_axis": {
                axis: float(np.mean(np.abs(raw_prediction[:, :, j]) > D_MAX[j])) for j, axis in enumerate(AXES)},
            "candidate_event_count_clipped_on_any_axis": int(np.sum(np.any(np.abs(raw_prediction) > D_MAX, axis=2))),
            "candidate_event_fraction_clipped_on_any_axis": float(np.mean(np.any(raw_clip_mask, axis=2))),
            "target_outside_dmax_count_by_axis": {
                axis: int(np.sum(np.abs(y_val[:, :, j]) > D_MAX[j])) for j, axis in enumerate(AXES)},
        },
        "train_standardized_feature_excursions": {
            "event_fraction_with_any_abs_z_gt_3": float(np.mean(any_feature_gt3)),
            "event_fraction_with_any_abs_z_gt_5": float(np.mean(any_feature_gt5)),
            "per_feature": ood_by_feature,
            "interpretation": "marginal excursions using frozen TRAIN mean/std; descriptive only, not a multivariate OOD test",
        },
        "train_scene_coverage": {
            "train_scene_count": len(train_ids), "task_groups": train_tasks,
            "task_group_counts": {task: sum(p[0] == task for p in train_parts) for task in train_tasks},
            "condition_codes_present": train_conditions,
            "condition_codes_missing_from_C00_to_C15": sorted(set(f"C{i:02d}" for i in range(16)) - set(train_conditions)),
            "wind_codes_present": train_winds,
            "wind_codes_missing_from_W00_to_W15": sorted(set(f"W{i:02d}" for i in range(16)) - set(train_winds)),
            "task_condition_pairs_covered": len(train_task_condition),
            "task_condition_pairs_possible": len(train_tasks) * 16,
            "task_condition_pairs_missing": sorted(f"{t}_C{c:02d}" for t in train_tasks for c in range(16)
                                                       if f"{t}_C{c:02d}" not in train_task_condition),
            "highest_condition_codes_by_task_ge_C14": c_high_by_task,
            "train_val_task_condition_overlap_count": len(train_task_condition & val_task_condition),
            "manifest_frequency_fields": manifest_frequency_fields,
            "event_interval_s": event_dt, "event_sample_rate_hz": event_rate,
            "event_nyquist_hz": event_rate / 2.0,
            "15_event_window_span_s": (WINDOW - 1) * event_dt,
            "frequency_coverage_conclusion": "manifest records 100 Hz event sampling and 10 ms residual intervals, but no maneuver/reference spectrum field; scene IDs cannot establish high-frequency coverage; content above the 50 Hz event Nyquist limit cannot be resolved by this input stream",
        },
        "independent_numpy_replay_check": replay_check,
        "boundaries": {"scorer_rerun": False, "training_run": False, "Plant_called": False,
                       "TEST_accessed": False, "validation_used_for_fit": False},
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary_path": str(OUTPUT_PATH), "scene_macro_gain_percent": output["scene_macro_relative_gain_percent"],
                      "scene_wins": output["scene_win_count"], "scene_losses": output["scene_loss_count"],
                      "severe_regression_count": len(output["severe_scene_regressions_extra_rmse_gt_1_rad_s2"]),
                      "numpy_replay_check": replay_check}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
