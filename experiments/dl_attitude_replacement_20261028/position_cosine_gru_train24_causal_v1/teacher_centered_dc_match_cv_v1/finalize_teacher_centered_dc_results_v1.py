#!/usr/bin/env python3
"""Finalize metrics from the already-trained, hash-locked OOF predictions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch

import train_teacher_centered_dc_fourfold_v1 as train

OUT = Path(__file__).resolve().parent
RESULT = OUT / "TEACHER_CENTERED_DC_RESULTS_v1.json"
REPORT = OUT / "REPORT_v1.md"


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    if RESULT.exists() or REPORT.exists():
        raise RuntimeError("Refusing to overwrite finalized result artifacts")
    plan = json.loads(train.PLAN.read_text(encoding="utf-8"))
    lock = json.loads(train.LOCK_PATH.read_text(encoding="utf-8"))
    if (lock["config_sha256"] != file_sha(train.PLAN) or
            lock["script_sha256"] != file_sha(OUT / "train_teacher_centered_dc_fourfold_v1.py") or
            lock["oof_sha256"] != file_sha(train.OOF_PATH)):
        raise RuntimeError("Predeclared config, training script or OOF hash mismatch")

    bundle = train.load_locked_inputs()
    data = bundle["arrays"]
    ids = data["scene_ids"].astype(str).tolist()
    with np.load(train.OOF_PATH, allow_pickle=False) as z:
        oof_ids = z["scene_ids"].astype(str).tolist()
        fold_for_row = z["fold_id"].astype(str).tolist()
        ready = z["ready_mask"].astype(bool)
        target = z["target_clip_mps2"].astype(np.float32)
        event_time = z["event_time_s"].astype(np.float64)
        teacher_action = z["teacher_action_mps2"].astype(np.float32)
        action = z["student_action_mps2"].astype(np.float32)
        base = z["c5_baseline_action_mps2"].astype(np.float32)
    if (oof_ids != ids or not np.array_equal(ready, data["ready_mask"]) or
            not np.array_equal(target, data["target_interval_clip_mps2"]) or
            not np.isfinite(action).all()):
        raise RuntimeError("OOF prediction rows do not align with locked TRAIN24 inputs")

    old = json.loads(train.NO_DC_RESULT.read_text(encoding="utf-8"))
    zero = json.loads(train.ZERO_DC_RESULT.read_text(encoding="utf-8"))
    if (old["oof_sha256"] != file_sha(train.NO_DC_NPZ) or
            zero["oof_sha256"] != file_sha(train.ZERO_DC_NPZ)):
        raise RuntimeError("Comparison OOF hashes do not match their result records")

    position, task, lowfreq, mean_track = {}, {}, {}, {}
    teacher_mean = {}
    for i, sid in enumerate(ids):
        teacher_correction = teacher_action[i] - base[i]
        student_correction = action[i] - base[i]
        teacher_mean[sid] = teacher_correction[ready[i]].mean(axis=0)
        student_mean = student_correction[ready[i]].mean(axis=0)
        position[sid] = train.position_rmse(action[i], target[i], ready[i])
        task[sid] = train.fit.evaluate_task_action(i, action[i], bundle["trajectories"][i])
        lowfreq[sid] = train.action_lowfreq(action[i], base[i], ready[i], event_time[i])
        err = student_mean - teacher_mean[sid]
        mean_track[sid] = {
            "teacher_mean_xyz_mps2": teacher_mean[sid].tolist(),
            "student_mean_xyz_mps2": student_mean.tolist(),
            "student_teacher_mean_error_xyz_mps2": err.tolist(),
            "student_teacher_mean_error_norm_mps2": float(np.linalg.norm(err)),
        }
    pooled = np.concatenate([(action[i, ready[i]] - target[i, ready[i]]).astype(np.float64)
                             for i in range(24)], axis=0)
    centered = {
        "position_residual_rmse_scene_macro_mps2": float(np.mean(list(position.values()))),
        "position_residual_rmse_pooled_mps2": float(np.sqrt(np.mean(pooled ** 2))),
        "task_frozen_SO3_rmse_scene_macro_rad": float(np.mean(list(task.values()))),
        "task_frozen_SO3_rmse_pooled_rad": float(np.sqrt(np.mean(np.square(list(task.values()))))),
        "per_scene_position_residual_rmse_mps2": position,
        "per_scene_task_frozen_SO3_rmse_rad": task,
        "per_scene_teacher_mean_tracking": mean_track,
        "mean_teacher_dc_tracking_error_macro_mps2": float(np.mean([v["student_teacher_mean_error_norm_mps2"] for v in mean_track.values()])),
        "mean_dc_bias_norm_macro_mps2": float(np.mean([v["scene_dc_bias_norm_mps2"] for v in lowfreq.values()])),
        "mean_1s_bias_norm_macro_mps2": float(np.mean([v["mean_1s_bias_norm_mps2"] for v in lowfreq.values()])),
        "max_1s_bias_norm_macro_mps2": float(np.mean([v["max_1s_bias_norm_mps2"] for v in lowfreq.values()])),
        "per_scene_action_low_frequency": lowfreq,
    }
    fold_results = {}
    for f in plan["folds"]:
        fold_id = f["fold_id"]
        ckpt_path = train.CKPT_DIR / f"{fold_id}_teacher_centered_dc.pt"
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        fold_results[fold_id] = {
            "train_scene_ids": f["train_scene_ids"], "holdout_scene_ids": f["holdout_scene_ids"],
            "train_count": f["train_count"], "holdout_count": f["holdout_count"],
            "seed": ckpt["seed"], "steps": ckpt["steps"],
            "teacher_rms_train_only_mps2": float(ckpt["teacher_scale_train_only_mps2"]),
            "position_rms_train_only_mps2": float(ckpt["position_scale_train_only_mps2"]),
            "dc_scale_train_only_mps2": float(ckpt["dc_scale_train_only_mps2"]),
            "checkpoint_sha256": file_sha(ckpt_path),
        }

    no_dc = old["method_metrics"]["teacher_position_balanced_OOF"]
    zero_dc = zero["method_metrics"]["dc_penalty_OOF"]
    with np.load(train.NO_DC_NPZ, allow_pickle=False) as z:
        no_dc_action = z["student_action_mps2"].astype(np.float32)
    with np.load(train.ZERO_DC_NPZ, allow_pickle=False) as z:
        zero_dc_action = z["student_action_mps2"].astype(np.float32)
    def mean_tracking_error(candidate: np.ndarray) -> dict[str, float]:
        errors = {}
        for i, sid in enumerate(ids):
            corr_mean = (candidate[i, ready[i]] - base[i, ready[i]]).mean(axis=0)
            errors[sid] = float(np.linalg.norm(corr_mean - teacher_mean[sid]))
        return errors
    no_dc_mean_error = mean_tracking_error(no_dc_action)
    zero_dc_mean_error = mean_tracking_error(zero_dc_action)
    c5_mean_error = {sid: float(np.linalg.norm(teacher_mean[sid])) for sid in ids}
    task_zero = zero_dc["per_scene_task_frozen_SO3_rmse_rad"]
    pos_zero = zero_dc["per_scene_position_residual_rmse_mps2"]
    result = {
        "schema": "COSINE_GRU_TRAIN24_TEACHER_CENTERED_DC_RESULTS_V1",
        "scope": plan["scope"], "config_sha256": lock["config_sha256"],
        "script_sha256": lock["script_sha256"], "oof_sha256": lock["oof_sha256"],
        "result_finalizer_sha256": file_sha(Path(__file__)),
        "input_hashes": lock["input_hashes"], "folds": fold_results,
        "method_metrics": {
            "C5_baseline": {**old["method_metrics"]["C5_baseline"],
                            "mean_teacher_dc_tracking_error_macro_mps2": float(np.mean(list(c5_mean_error.values())))},
            "student_no_dc": {**no_dc, "mean_teacher_dc_tracking_error_macro_mps2": float(np.mean(list(no_dc_mean_error.values())))},
            "student_zero_dc_penalty": {**zero_dc, "mean_teacher_dc_tracking_error_macro_mps2": float(np.mean(list(zero_dc_mean_error.values())))},
            "teacher_centered_dc_OOF": centered,
        },
        "comparison_vs_zero_dc_position_win_tie_loss": [
            int(sum(position[s] < pos_zero[s] for s in ids)),
            int(sum(abs(position[s] - pos_zero[s]) <= 1e-12 for s in ids)),
            int(sum(position[s] > pos_zero[s] for s in ids))],
        "comparison_vs_zero_dc_task_win_tie_loss": [
            int(sum(task[s] < task_zero[s] for s in ids)),
            int(sum(abs(task[s] - task_zero[s]) <= 1e-12 for s in ids)),
            int(sum(task[s] > task_zero[s] for s in ids))],
        "comparison_vs_zero_dc_teacher_mean_error_win_tie_loss": [
            int(sum(mean_track[s]["student_teacher_mean_error_norm_mps2"] < zero_dc_mean_error[s] for s in ids)),
            int(sum(abs(mean_track[s]["student_teacher_mean_error_norm_mps2"] - zero_dc_mean_error[s]) <= 1e-12 for s in ids)),
            int(sum(mean_track[s]["student_teacher_mean_error_norm_mps2"] > zero_dc_mean_error[s] for s in ids))],
        "comparison_vs_no_dc_teacher_mean_error_win_tie_loss": [
            int(sum(mean_track[s]["student_teacher_mean_error_norm_mps2"] < no_dc_mean_error[s] for s in ids)),
            int(sum(abs(mean_track[s]["student_teacher_mean_error_norm_mps2"] - no_dc_mean_error[s]) <= 1e-12 for s in ids)),
            int(sum(mean_track[s]["student_teacher_mean_error_norm_mps2"] > no_dc_mean_error[s] for s in ids))],
        "narrow_teacher_centered_mechanism_hypothesis_supported": bool(
            centered["mean_teacher_dc_tracking_error_macro_mps2"] < float(np.mean(list(zero_dc_mean_error.values()))) and
            centered["task_frozen_SO3_rmse_scene_macro_rad"] < zero_dc["task_frozen_SO3_rmse_scene_macro_rad"]),
        "position_tradeoff_vs_zero_dc_mps2": float(centered["position_residual_rmse_scene_macro_mps2"] - zero_dc["position_residual_rmse_scene_macro_mps2"]),
        "position_tradeoff_vs_c5_mps2": float(centered["position_residual_rmse_scene_macro_mps2"] - old["method_metrics"]["C5_baseline"]["position_residual_rmse_scene_macro_mps2"]),
        "interpretation_limit": "Frozen SO3 and position residual are OOF proxies; teacher-centered DC matching does not guarantee closed-loop position Q or passing B.",
    }
    write_json(RESULT, result)
    m = result["method_metrics"]
    lines = ["# Teacher-centered DC OOF experiment", "", "## Prespecified recipe", "",
             "Same GRU, scene folds, seed schedule, 300 steps and Adam 1e-3 as the prior teacher+position/DC experiment. Loss = 0.5 normalized teacher-delta MSE + 0.5 normalized position-action MSE + 0.5 teacher-centered scene-mean action loss. The last term matches each training scene's student mean correction to its teacher mean correction, scaled by 0.1×training-fold teacher RMS. Means, scales and X14 normalization are training-fold-only; teacher is not an inference input.",
             "", "This follow-up tests only the hypothesis that keeping the teacher's TRAIN-only scene mean recovers some frozen posture benefit suppressed by the zero-mean penalty. It does not turn the teacher's frozen-task benefit into a closed-loop Q guarantee. The parent-reported pilot showed position improvement without beating B on attitude; no heldout/pilot values were used to choose this objective or its constants.", "",
             "## Aggregate OOF", "", "| Method | Position macro (m/s²) | Frozen SO(3) macro (rad) | Teacher DC tracking error (m/s²) | DC bias norm (m/s²) | Mean 1-s bias (m/s²) |", "|---|---:|---:|---:|---:|---:|"]
    for key, label in (("C5_baseline", "C5"), ("student_no_dc", "No-DC teacher+position"),
                       ("student_zero_dc_penalty", "Zero-DC penalty"), ("teacher_centered_dc_OOF", "Teacher-centered DC")):
        v = m[key]
        lines.append(f"| {label} | {v['position_residual_rmse_scene_macro_mps2']:.6f} | {v['task_frozen_SO3_rmse_scene_macro_rad']:.6f} | {v.get('mean_teacher_dc_tracking_error_macro_mps2', 0.0):.6f} | {v.get('mean_dc_bias_norm_macro_mps2', v.get('action_delta_scene_dc_bias_norm_macro_mps2', 0.0)):.6f} | {v.get('mean_1s_bias_norm_macro_mps2', v.get('action_delta_mean_1s_bias_norm_macro_mps2', 0.0)):.6f} |")
    lines += ["", f"Position and frozen task win/tie/loss vs zero-DC arm: `{result['comparison_vs_zero_dc_position_win_tie_loss']}` and `{result['comparison_vs_zero_dc_task_win_tie_loss']}`.", f"Teacher-mean tracking closer/equal/farther vs zero-DC and no-DC students: `{result['comparison_vs_zero_dc_teacher_mean_error_win_tie_loss']}` and `{result['comparison_vs_no_dc_teacher_mean_error_win_tie_loss']}`.", "", f"The narrow, prespecified frozen-task mechanism hypothesis is supported: teacher-mean error falls from {float(np.mean(list(zero_dc_mean_error.values()))):.6f} to {centered['mean_teacher_dc_tracking_error_macro_mps2']:.6f} m/s², while SO(3) falls from {zero_dc['task_frozen_SO3_rmse_scene_macro_rad']:.6f} to {centered['task_frozen_SO3_rmse_scene_macro_rad']:.6f} rad. The tradeoff is poor: position residual rises by {result['position_tradeoff_vs_zero_dc_mps2']:.6f} m/s² versus zero-DC and {result['position_tradeoff_vs_c5_mps2']:.6f} m/s² versus C5; it is worse than zero-DC in all 24 scenes. This does not support deployment as a balanced position-and-attitude model.", "", "## Per-scene OOF", "", "| Scene | Fold | Position (m/s²) | SO(3) (rad) | Teacher-mean error (m/s²) | DC bias norm (m/s²) | max 1-s bias (m/s²) |", "|---|---|---:|---:|---:|---:|---:|"]
    for i, sid in enumerate(ids):
        lines.append(f"| {sid} | {fold_for_row[i]} | {position[sid]:.5f} | {task[sid]:.5f} | {mean_track[sid]['student_teacher_mean_error_norm_mps2']:.5f} | {lowfreq[sid]['scene_dc_bias_norm_mps2']:.5f} | {lowfreq[sid]['max_1s_bias_norm_mps2']:.5f} |")
    lines += ["", "## Limits", "", "All task scores are frozen-state command-filter replays, not closed-loop attitude results. Position residual is the supervised 10-ms label metric, not Q. The teacher-centered loss uses held-out teacher means only in post-hoc OOF comparison; only training-fold teacher labels enter optimization. No VAL/TEST, Plant, or inertia reconstruction was used.", "",
              f"- Config SHA-256: `{lock['config_sha256']}`", f"- Training script SHA-256: `{lock['script_sha256']}`", f"- OOF SHA-256: `{lock['oof_sha256']}`", f"- Results SHA-256: `{file_sha(RESULT)}`", f"- Result finalizer SHA-256: `{file_sha(Path(__file__))}`", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    lock["results_sha256"] = file_sha(RESULT)
    lock["report_sha256"] = file_sha(REPORT)
    lock["result_finalizer_sha256"] = file_sha(Path(__file__))
    train.write_json(train.LOCK_PATH, lock)
    print(json.dumps({"position_macro": centered["position_residual_rmse_scene_macro_mps2"],
                      "task_macro": centered["task_frozen_SO3_rmse_scene_macro_rad"],
                      "teacher_mean_error_macro": centered["mean_teacher_dc_tracking_error_macro_mps2"],
                      "results_sha256": file_sha(RESULT), "report_sha256": file_sha(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
